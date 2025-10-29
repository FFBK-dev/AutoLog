# jobs/stills_autolog_02_copy_to_server.py
import sys, os, json, time, requests, subprocess
import warnings
from pathlib import Path
import cv2
import numpy as np
import shutil

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Set PIL's maximum image size to handle very large images (1 billion pixels)
# This prevents the "decompression bomb DOS attack" error for legitimate large images
from PIL import Image, ImageFile
Image.MAX_IMAGE_PIXELS = 1000000000  # 1 billion pixels

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

ImageFile.LOAD_TRUNCATED_IMAGES = True
__ARGS__ = ["stills_id"]
AVID_MAX_DIMENSION = 15000

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "import_path": "SPECS_Filepath_Import",
    "server_path": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail",
    "file_format": "SPECS_File_Format",
    "globals_drive": "SystemGlobals_Stills_ServerDrive",
    "globals_subfolder": "SystemGlobals_Stills_Subfolderpath"
}

def get_system_globals(token):
    return config.get_system_globals(token)

def flatten_and_convert_to_rgb(img):
    """
    Comprehensive image processing to ensure flattened RGB output.
    Handles: PSDs, layered TIFs, CMYK, LAB, grayscale, 16-bit, RGBA, etc.
    """
    print(f"  -> Image mode: {img.mode}, Format: {img.format}, Size: {img.size}")
    
    # Handle multi-layered images (PSD, layered TIFF)
    layers = getattr(img, 'layers', [])
    # Ensure layers is a list/tuple before calling len()
    if hasattr(layers, '__len__') and not isinstance(layers, (str, bytes)) and len(layers) > 1:
        print(f"  -> Detected multi-layered image with {len(layers)} layers - flattening")
        # Flatten by converting to RGB which automatically composites layers
        img = img.convert('RGB')
        print(f"  -> Layers flattened successfully")
        return img
    
    # If image has seek method, try to composite all frames/layers
    if hasattr(img, 'seek'):
        try:
            # Check if there are multiple frames/layers
            img.seek(1)
            print(f"  -> Multiple frames/layers detected - compositing")
            img.seek(0)
            # Create composite by converting to RGB
            img = img.convert('RGB')
            print(f"  -> Frames composited successfully")
            return img
        except EOFError:
            # Only one frame/layer, continue normal processing
            img.seek(0)
    
    # Handle 16-bit images (both grayscale and color)
    if img.mode in ('I;16', 'I;16L', 'I;16B'):
        print(f"  -> Detected 16-bit image - converting to 8-bit RGB")
        # Convert 16-bit to 8-bit by scaling
        img_array = np.array(img)
        img_8bit = (img_array / 256).astype(np.uint8)
        # Convert to RGB
        img = Image.fromarray(img_8bit, mode='L').convert('RGB')
        print(f"  -> 16-bit conversion complete")
        return img
    
    # Handle CMYK images (common in print-ready files)
    if img.mode == 'CMYK':
        print(f"  -> Converting CMYK to RGB")
        img = img.convert('RGB')
        print(f"  -> CMYK conversion complete")
        return img
    
    # Handle LAB color space
    if img.mode == 'LAB':
        print(f"  -> Converting LAB to RGB")
        img = img.convert('RGB')
        print(f"  -> LAB conversion complete")
        return img
    
    # Handle RGBA (with alpha channel) - flatten alpha
    if img.mode == 'RGBA':
        print(f"  -> Converting RGBA to RGB (removing alpha channel)")
        # Create white background
        background = Image.new('RGB', img.size, (255, 255, 255))
        # Paste image on white background using alpha channel as mask
        background.paste(img, mask=img.split()[3])  # 3 is the alpha channel
        img = background
        print(f"  -> Alpha channel removed, image flattened on white background")
        return img
    
    # Handle palette mode images
    if img.mode == 'P':
        print(f"  -> Converting palette mode to RGB")
        img = img.convert('RGB')
        print(f"  -> Palette conversion complete")
        return img
    
    # Handle grayscale images
    if img.mode in ('L', '1'):
        print(f"  -> Converting grayscale to RGB")
        img = img.convert('RGB')
        print(f"  -> Grayscale conversion complete")
        return img
    
    # Handle any other exotic modes
    if img.mode != 'RGB':
        print(f"  -> Converting {img.mode} to RGB")
        try:
            img = img.convert('RGB')
            print(f"  -> Conversion to RGB complete")
        except Exception as e:
            print(f"  -> Warning: Standard conversion failed ({e}), attempting forced conversion")
            # Force conversion by going through numpy array
            img_array = np.array(img)
            if len(img_array.shape) == 2:
                # Single channel - convert to RGB by repeating
                img_rgb = np.stack([img_array, img_array, img_array], axis=2)
                img = Image.fromarray(img_rgb.astype(np.uint8), mode='RGB')
            else:
                # Multi-channel - take first 3 channels or pad to 3
                if img_array.shape[2] >= 3:
                    img = Image.fromarray(img_array[:,:,:3].astype(np.uint8), mode='RGB')
                else:
                    # Pad to 3 channels
                    img_rgb = np.zeros((*img_array.shape[:2], 3), dtype=np.uint8)
                    img_rgb[:,:,:img_array.shape[2]] = img_array
                    img = Image.fromarray(img_rgb, mode='RGB')
            print(f"  -> Forced conversion successful")
        return img
    
    print(f"  -> Image already in RGB mode")
    return img

def get_image_dimensions_alternative(import_path):
    """Get image dimensions using alternative methods when PIL fails."""
    print(f"  -> Attempting alternative dimension extraction for: {import_path}")
    
    # Method 1: Try using exiftool to get dimensions
    try:
        exiftool_paths = ['/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool', 'exiftool']
        exiftool_cmd = None
        
        for path in exiftool_paths:
            if os.path.exists(path) or path == 'exiftool':
                exiftool_cmd = path
                break
        
        if exiftool_cmd:
            result = subprocess.run([exiftool_cmd, '-j', '-ImageWidth', '-ImageHeight', import_path], 
                                  capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                metadata = json.loads(result.stdout)[0]
                width = metadata.get('ImageWidth')
                height = metadata.get('ImageHeight')
                if width and height:
                    print(f"  -> Successfully extracted dimensions via exiftool: {width}x{height}")
                    return int(width), int(height)
    except Exception as e:
        print(f"  -> Exiftool dimension extraction failed: {e}")
    
    # Method 2: Try using sips (macOS built-in)
    try:
        result = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', import_path], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            width = None
            height = None
            for line in lines:
                if 'pixelWidth:' in line:
                    width = line.split(':')[1].strip()
                elif 'pixelHeight:' in line:
                    height = line.split(':')[1].strip()
            if width and height:
                print(f"  -> Successfully extracted dimensions via sips: {width}x{height}")
                return int(width), int(height)
    except Exception as e:
        print(f"  -> Sips dimension extraction failed: {e}")
    
    # Method 3: Try using identify (ImageMagick)
    try:
        result = subprocess.run(['identify', '-format', '%wx%h', import_path], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            dimensions = result.stdout.strip()
            if 'x' in dimensions:
                width, height = dimensions.split('x')
                print(f"  -> Successfully extracted dimensions via identify: {width}x{height}")
                return int(width), int(height)
    except Exception as e:
        print(f"  -> Identify dimension extraction failed: {e}")
    
    print(f"  -> All alternative dimension extraction methods failed")
    return None, None

def upscale_small_image(image_path, target_min_dimension=1000):
    """Upscale image using OpenCV to reach target minimum dimension."""
    try:
        print(f"  -> Upscaling small image to minimum {target_min_dimension}px")
        
        # Load the image with enhanced decompression
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        original_height, original_width = img.shape[:2]
        channels = img.shape[2] if len(img.shape) > 2 else 1
        print(f"  -> Original image size: {original_width}x{original_height} ({channels} channels)")
        
        # Calculate required scale factor to reach target minimum dimension
        current_min_dimension = min(original_width, original_height)
        required_scale = max(2, target_min_dimension / current_min_dimension)
        scale_factor = int(required_scale) if required_scale == int(required_scale) else int(required_scale) + 1
        
        print(f"  -> Target minimum dimension: {target_min_dimension}px")
        print(f"  -> Required scale factor: {scale_factor}x")
        
        # Convert grayscale to RGB if needed
        if channels == 1:
            print(f"  -> Converting grayscale to RGB")
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif channels == 4:  # RGBA
            print(f"  -> Converting RGBA to RGB")
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        
        # Simple, safe artifact removal
        print(f"  -> Applying light artifact removal...")
        img = cv2.bilateralFilter(img, 5, 20, 20)
        
        # Enhanced fallback with multiple passes for better quality
        print(f"  -> Upscaling with multi-pass bicubic interpolation x{scale_factor}...")
        current_img = img.copy()
        remaining_scale = scale_factor
        
        while remaining_scale > 1:
            # Use smaller steps to avoid quality loss
            step_scale = min(2, remaining_scale)
            new_width = int(current_img.shape[1] * step_scale)
            new_height = int(current_img.shape[0] * step_scale)
            
            current_img = cv2.resize(current_img, (new_width, new_height), 
                                   interpolation=cv2.INTER_CUBIC)
            remaining_scale /= step_scale
        
        upscaled = current_img
        
        # Simple post-processing to avoid color artifacts
        print(f"  -> Applying minimal post-processing...")
        upscaled = cv2.bilateralFilter(upscaled, 3, 15, 15)
        
        # Add adaptive film grain
        print(f"  -> Adding adaptive film grain...")
        
        # Convert to float32 for grain processing
        upscaled_float = upscaled.astype(np.float32) / 255.0
        
        # Generate film grain noise
        height, width, channels = upscaled_float.shape
        
        # Analyze image to determine if it's monochromatic (grayscale/sepia)
        b_channel, g_channel, r_channel = cv2.split(upscaled_float)
        color_variance = np.var([np.mean(r_channel), np.mean(g_channel), np.mean(b_channel)])
        
        grain_intensity = 0.02
        
        # If image is essentially monochromatic, use monochromatic grain
        if color_variance < 0.001:
            print(f"  -> Detected monochromatic image, applying luminance-based grain")
            noise_pattern = np.random.normal(0, grain_intensity, (height, width))
            noise = np.stack([noise_pattern, noise_pattern, noise_pattern], axis=2)
        else:
            print(f"  -> Detected color image, applying multi-channel grain")
            noise_r = np.random.normal(0, grain_intensity * 1.0, (height, width))
            noise_g = np.random.normal(0, grain_intensity * 0.8, (height, width))
            noise_b = np.random.normal(0, grain_intensity * 1.2, (height, width))
            noise = np.stack([noise_b, noise_g, noise_r], axis=2)
        
        # Apply grain to the image
        upscaled_with_grain = upscaled_float + noise
        upscaled_with_grain = np.clip(upscaled_with_grain, 0, 1)
        upscaled = (upscaled_with_grain * 255).astype(np.uint8)
        
        # Get new dimensions
        new_height, new_width = upscaled.shape[:2]
        print(f"  -> Upscaled image size: {new_width}x{new_height}")
        
        # Save the upscaled image
        cv2.imwrite(image_path, upscaled, [cv2.IMWRITE_JPEG_QUALITY, 97])
        print(f"  -> Upscaled image saved with film grain")
        
        return True
        
    except Exception as e:
        print(f"  -> Error during upscaling: {e}")
        return False

def calculate_destination_path(stills_id: str, globals_data: dict) -> str:
    server_drive = globals_data.get(FIELD_MAPPING["globals_drive"])
    subfolder_path = globals_data.get(FIELD_MAPPING["globals_subfolder"])
    if not server_drive or not subfolder_path:
        raise ValueError("Stills server drive or subfolder path is not set in SystemGlobals.")
    stills_root = f"/Volumes/{server_drive}/{subfolder_path}"
    
    num = int(stills_id.replace('S', ''))
    
    # Special handling for first range: starts at 1, not 0
    if num < 500:
        range_start = 1
        range_end = 499
    else:
        range_start = (num // 500) * 500
        range_end = range_start + 499
    
    folder_name = f"S{range_start:05d}-S{range_end:05d}"
    
    destination_folder = os.path.join(stills_root, folder_name)
    
    # Thread-safe directory creation
    try:
        os.makedirs(destination_folder, exist_ok=True)
    except OSError as e:
        # Another thread might have created it, check if it exists
        if not os.path.exists(destination_folder):
            raise e
    
    return os.path.join(destination_folder, f"{stills_id}.jpg")

if __name__ == "__main__":
    if len(sys.argv) < 2: 
        sys.exit(1)
    
    stills_id = sys.argv[1]
    
    # Flexible token handling - detect call mode
    if len(sys.argv) == 2:
        # Direct API call mode - create own token/session
        token = config.get_token()
        print(f"Direct mode: Created new FileMaker session for {stills_id}")
    elif len(sys.argv) == 3:
        # Subprocess mode - use provided token from parent process
        token = sys.argv[2]
        print(f"Subprocess mode: Using provided token for {stills_id}")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py stills_id [token]\n")
        sys.exit(1)
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        import_path = record_data[FIELD_MAPPING["import_path"]]
        
        system_globals = get_system_globals(token)
        was_upscaled = False

        # Enhanced image processing with fallback methods
        original_width, original_height = None, None
        img = None
        
        try:
            print(f"  -> Attempting to open image with PIL: {import_path}")
            img = Image.open(import_path)
            original_width, original_height = img.size
            print(f"  -> Successfully extracted dimensions via PIL: {original_width}x{original_height}")
        except Exception as e:
            print(f"  -> PIL failed to open image: {e}")
            print(f"  -> Attempting alternative dimension extraction methods...")
            original_width, original_height = get_image_dimensions_alternative(import_path)
            
            if original_width and original_height:
                print(f"  -> Using alternative dimensions: {original_width}x{original_height}")
                # Create a minimal image for processing
                img = Image.new('RGB', (original_width, original_height), (255, 255, 255))
            else:
                print(f"  -> All dimension extraction methods failed, using default size")
                original_width, original_height = 1920, 1080  # Default fallback
                img = Image.new('RGB', (original_width, original_height), (255, 255, 255))
        
        # Comprehensive image processing: flatten layers and convert to RGB
        print(f"🔄 Processing image: flattening and converting to RGB")
        img = flatten_and_convert_to_rgb(img)
        print(f"✅ Image processing complete: {img.mode} mode, {img.size[0]}x{img.size[1]}")
        
        if max(img.size) > AVID_MAX_DIMENSION:
            img.thumbnail((AVID_MAX_DIMENSION, AVID_MAX_DIMENSION), Image.Resampling.LANCZOS)
        
        destination_path = calculate_destination_path(stills_id, system_globals)
        img.save(destination_path, 'JPEG', quality=95)
        
        # Check if image needs upscaling (under 1000px in any dimension)
        if min(original_width, original_height) < 1000:
            print(f"🔄 Image under 1000px detected - triggering automatic upscaling")
            
            # Upscale the server file directly
            if upscale_small_image(destination_path, target_min_dimension=1000):
                was_upscaled = True
                print(f"✅ Automatic upscaling completed successfully")
            else:
                print(f"⚠️ Automatic upscaling failed, continuing with original image")
        
        # Create thumbnail from the final server image (may be upscaled)
        try:
            with Image.open(destination_path) as final_img:
                thumb_img = final_img.copy()
                thumb_img.thumbnail((588, 588), Image.Resampling.LANCZOS)
                
                thumb_path = f"/tmp/thumb_{stills_id}.jpg"
                thumb_img.save(thumb_path, 'JPEG', quality=85)
                
                # Upload thumbnail using config function
                config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], thumb_path)
                os.remove(thumb_path)
        except Exception as e:
            print(f"  -> Warning: Could not create thumbnail: {e}")
            # Create a simple placeholder thumbnail
            placeholder = Image.new('RGB', (588, 588), (200, 200, 200))
            thumb_path = f"/tmp/thumb_{stills_id}.jpg"
            placeholder.save(thumb_path, 'JPEG', quality=85)
            
            try:
                config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], thumb_path)
                os.remove(thumb_path)
            except Exception as thumb_error:
                print(f"  -> Warning: Could not upload placeholder thumbnail: {thumb_error}")

        # Prepare payload with server path and file format
        # Get the original file format from the FileMaker record (set by step 01)
        # instead of deriving it from destination path (which is always .jpg)
        original_file_format = record_data.get(FIELD_MAPPING["file_format"], "UNKNOWN")
        
        # Add (upscaled) notation if the image was upscaled
        if was_upscaled:
            file_format = original_file_format + " (upscaled)"
        else:
            file_format = original_file_format
        
        payload = {
            FIELD_MAPPING["server_path"]: destination_path,
            FIELD_MAPPING["file_format"]: file_format
        }
        config.update_record(token, "Stills", record_id, payload)
        
        success_message = f"SUCCESS [copy_to_server]: {stills_id}"
        if was_upscaled:
            success_message += " (with automatic upscaling)"
        
        print(success_message)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"ERROR [copy_to_server] on {stills_id}: {e}\n")
        sys.exit(1)