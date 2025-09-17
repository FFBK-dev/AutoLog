#!/usr/bin/env python3
# jobs/stills_upscale_image.py
import sys, os, json, time, requests
import warnings
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageFile

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Add the parent directory to the path to import your existing config
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

ImageFile.LOAD_TRUNCATED_IMAGES = True
__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "server_path": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail",
    "dimensions": "SPECS_File_Dimensions",
    "size": "SPECS_File_Size",
    "file_format": "SPECS_File_Format"
}

def download_fsrcnn_model():
    """Download FSRCNN x4 model if not already present."""
    model_dir = Path.home() / ".opencv" / "dnn_superres"
    model_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = model_dir / "FSRCNN_x4.pb"
    
    if not model_path.exists():
        print(f"  -> Downloading FSRCNN x4 model...")
        # Use the correct FSRCNN model URL
        model_url = "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x4.pb"
        
        try:
            import urllib.request
            urllib.request.urlretrieve(model_url, model_path)
            print(f"  -> Model downloaded to: {model_path}")
        except Exception as e:
            print(f"  -> Failed to download model: {e}")
            print(f"  -> Please manually download FSRCNN_x4.pb to: {model_path}")
            return None
    
    return str(model_path)

def upscale_image_opencv(image_path, output_path, target_min_width=4000):
    """Upscale image using OpenCV DNN FSRCNN to reach target minimum width."""
    try:
        # Load the image with enhanced decompression
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        original_height, original_width = img.shape[:2]
        channels = img.shape[2] if len(img.shape) > 2 else 1
        print(f"  -> Original image size: {original_width}x{original_height} ({channels} channels)")
        
        # Calculate required scale factor to reach target minimum width
        required_scale = max(4, target_min_width / original_width)
        scale_factor = int(required_scale) if required_scale == int(required_scale) else int(required_scale) + 1
        
        print(f"  -> Target minimum width: {target_min_width}px")
        print(f"  -> Required scale factor: {scale_factor}x")
        
        # Convert grayscale to RGB if needed (FSRCNN expects 3 channels)
        if channels == 1:
            print(f"  -> Converting grayscale to RGB for FSRCNN compatibility")
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif channels == 4:  # RGBA
            print(f"  -> Converting RGBA to RGB for FSRCNN compatibility")
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        
        # Simple, safe artifact removal
        print(f"  -> Applying light artifact removal...")
        
        # Just apply very light bilateral filtering to reduce artifacts
        # Keep it minimal to avoid color distortion
        img = cv2.bilateralFilter(img, 5, 20, 20)
        
        # Get model path
        model_path = download_fsrcnn_model()
        if not model_path:
            raise ValueError("FSRCNN model not available")
        
        # Create DNN super resolution object
        sr = cv2.dnn_superres.DnnSuperResImpl_create()
        
        # Read the model
        print(f"  -> Loading FSRCNN model from: {model_path}")
        sr.readModel(model_path)
        sr.setModel("fsrcnn", scale_factor)
        
        # Debug: Check image shape before upsampling
        print(f"  -> Image shape before upsampling: {img.shape}")
        print(f"  -> Image dtype: {img.dtype}")
        
        # Upscale the image
        print(f"  -> Upscaling with FSRCNN x{scale_factor}...")
        try:
            upscaled = sr.upsample(img)
        except Exception as e:
            print(f"  -> FSRCNN failed, falling back to enhanced bicubic interpolation: {e}")
            # Enhanced fallback with multiple passes for better quality
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
        
        # Get new dimensions
        new_height, new_width = upscaled.shape[:2]
        print(f"  -> Upscaled image size: {new_width}x{new_height}")
        
        # Simple post-processing to avoid color artifacts
        print(f"  -> Applying minimal post-processing...")
        
        # Just apply very light bilateral filtering if needed
        # Keep processing minimal to preserve original colors
        upscaled = cv2.bilateralFilter(upscaled, 3, 15, 15)
        
        # Add subtle film grain as final step
        print(f"  -> Adding adaptive film grain...")
        
        # Convert to float32 for grain processing
        upscaled_float = upscaled.astype(np.float32) / 255.0
        
        # Generate film grain noise
        height, width, channels = upscaled_float.shape
        
        # Analyze image to determine if it's monochromatic (grayscale/sepia)
        # Calculate color variance across channels
        b_channel, g_channel, r_channel = cv2.split(upscaled_float)
        color_variance = np.var([np.mean(r_channel), np.mean(g_channel), np.mean(b_channel)])
        
        grain_intensity = 0.03  # More noticeable film grain
        
        # If image is essentially monochromatic (low color variance), use monochromatic grain
        if color_variance < 0.001:  # Very low color variance = grayscale/sepia
            print(f"  -> Detected monochromatic image, applying luminance-based grain")
            
            # Generate single noise pattern
            noise_pattern = np.random.normal(0, grain_intensity, (height, width))
            
            # Apply the same noise to all channels to maintain color consistency
            noise = np.stack([noise_pattern, noise_pattern, noise_pattern], axis=2)
            
        else:
            print(f"  -> Detected color image, applying multi-channel grain")
            
            # Generate noise for each channel with slight variations (for color images)
            noise_r = np.random.normal(0, grain_intensity * 1.0, (height, width))
            noise_g = np.random.normal(0, grain_intensity * 0.8, (height, width))
            noise_b = np.random.normal(0, grain_intensity * 1.2, (height, width))
            
            # Stack the noise channels
            noise = np.stack([noise_b, noise_g, noise_r], axis=2)  # BGR order for OpenCV
        
        # Apply grain to the image
        upscaled_with_grain = upscaled_float + noise
        
        # Clamp values to valid range
        upscaled_with_grain = np.clip(upscaled_with_grain, 0, 1)
        
        # Convert back to uint8
        upscaled = (upscaled_with_grain * 255).astype(np.uint8)
        
        # Save the upscaled image with high quality
        cv2.imwrite(output_path, upscaled, [cv2.IMWRITE_JPEG_QUALITY, 97])
        print(f"  -> Upscaled image saved with film grain and quality 97: {output_path}")
        
        return upscaled
        
    except Exception as e:
        print(f"  -> Error during upscaling: {e}")
        raise

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
        print(f"🔄 Upscaling server image with FSRCNN x4 for {stills_id}")
        
        # Find the record and get current data
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        
        # Get server path - this script requires the server path to exist
        server_path = record_data.get(FIELD_MAPPING["server_path"])
        if not server_path:
            raise ValueError(f"No server path found for {stills_id} - file must be copied to server first")
        
        if not os.path.exists(server_path):
            raise FileNotFoundError(f"Server file not found: {server_path}")
        
        print(f"  -> Upscaling server image: {server_path}")
        
        # Create temporary path for upscaled image
        temp_upscaled_path = f"/tmp/upscaled_{stills_id}.jpg"
        
        # Upscale the server image using OpenCV FSRCNN
        upscaled_img = upscale_image_opencv(server_path, temp_upscaled_path, target_min_width=8000)
        
        # Verify the upscaled file exists
        if not os.path.exists(temp_upscaled_path):
            raise FileNotFoundError(f"Upscaled file was not created: {temp_upscaled_path}")
        
        print(f"  -> Upscaled file created: {temp_upscaled_path}")
        print(f"  -> Upscaled file size: {os.path.getsize(temp_upscaled_path)} bytes")
        
        # Replace the original server file with the upscaled version
        print(f"  -> Replacing server file: {server_path}")
        
        # Use copy and delete instead of os.replace for cross-device compatibility
        import shutil
        shutil.copy2(temp_upscaled_path, server_path)
        os.remove(temp_upscaled_path)
        print(f"  -> Server file replaced with upscaled version")
        
        # Verify the replacement worked
        if os.path.exists(server_path):
            print(f"  -> Server file size after replacement: {os.path.getsize(server_path)} bytes")
        else:
            raise FileNotFoundError(f"Server file was not replaced: {server_path}")
        
        # Update file specifications and create thumbnail from the upscaled image using PIL
        with Image.open(server_path) as img:
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Update file specifications to reflect the upscaled image
            new_dimensions = f"{img.width}x{img.height}"
            new_file_size_mb = f"{os.path.getsize(server_path) / (1024*1024):.2f} Mb"
            
            # Get the original file format from the FileMaker record (set by step 01)
            # instead of deriving it from server path (which is always .jpg)
            original_file_format = record_data.get(FIELD_MAPPING["file_format"], "UNKNOWN")
            
            # Remove any existing upscaled notation to avoid double notation
            if original_file_format.endswith(" (upscaled)"):
                original_file_format = original_file_format.replace(" (upscaled)", "")
            
            # Add (upscaled) notation since this is an upscaling script
            file_format = original_file_format + " (upscaled)"
            
            print(f"  -> Updated dimensions: {new_dimensions}")
            print(f"  -> Updated file size: {new_file_size_mb}")
            print(f"  -> File format: {file_format}")
            
            # Update the record with new specifications
            field_data = {
                FIELD_MAPPING["dimensions"]: new_dimensions,
                FIELD_MAPPING["size"]: new_file_size_mb,
                FIELD_MAPPING["file_format"]: file_format
            }
            
            config.update_record(token, "Stills", record_id, field_data)
            print(f"  -> File specifications updated in FileMaker")
            
            # Create thumbnail (588x588 to match existing pattern)
            thumb_img = img.copy()
            thumb_img.thumbnail((588, 588), Image.Resampling.LANCZOS)
            
            # Save thumbnail to temporary file
            thumb_path = f"/tmp/thumb_upscaled_{stills_id}.jpg"
            thumb_img.save(thumb_path, 'JPEG', quality=85)
            
            print(f"  -> Created thumbnail from upscaled image: {thumb_img.size}")
            
            # Upload thumbnail using config function
            config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], thumb_path)
            
            # Clean up temporary file
            os.remove(thumb_path)
            
        print(f"✅ SUCCESS [upscale_image]: {stills_id}")
        sys.exit(0)
        
    except Exception as e:
        sys.stderr.write(f"❌ ERROR [upscale_image] on {stills_id}: {e}\n")
        sys.exit(1) 