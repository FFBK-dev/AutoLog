#!/usr/bin/env python3
import sys, os, subprocess, tempfile
import warnings
from pathlib import Path
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "filepath": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail"
}

def get_video_duration(file_path):
    """Get video duration using ffprobe."""
    try:
        # Find ffprobe
        ffprobe_paths = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', 'ffprobe']
        ffprobe_cmd = None
        
        for path in ffprobe_paths:
            if os.path.exists(path) or path == 'ffprobe':
                ffprobe_cmd = path
                break
        
        if not ffprobe_cmd:
            print(f"  -> Warning: ffprobe not found, using default timecode")
            return None
        
        # Get duration using ffprobe
        cmd = [
            ffprobe_cmd,
            '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            print(f"  -> Video duration: {duration:.2f} seconds")
            return duration
        else:
            print(f"  -> Warning: Could not determine video duration, using default timecode")
            return None
            
    except Exception as e:
        print(f"  -> Warning: Error getting video duration: {e}, using default timecode")
        return None

def calculate_optimal_timecode(duration):
    """Calculate optimal timecode based on video duration."""
    if duration is None:
        return "00:00:01"  # Default fallback
    
    # For very short videos (< 3 seconds), use 25% of duration
    if duration < 3.0:
        optimal_seconds = max(0.1, duration * 0.25)
        return f"00:00:{optimal_seconds:.1f}"
    
    # For short videos (3-10 seconds), use 20% of duration
    elif duration < 10.0:
        optimal_seconds = duration * 0.20
        return f"00:00:{optimal_seconds:.1f}"
    
    # For medium videos (10-60 seconds), use 15% of duration
    elif duration < 60.0:
        optimal_seconds = duration * 0.15
        return f"00:00:{optimal_seconds:.1f}"
    
    # For longer videos, use 10% of duration but cap at 30 seconds
    else:
        optimal_seconds = min(30.0, duration * 0.10)
        return f"00:00:{optimal_seconds:.1f}"

def generate_footage_thumbnail(file_path, output_path, timecode=None):
    """Generate a thumbnail for the footage at optimal timecode."""
    print(f"  -> Generating footage thumbnail from: {file_path}")
    
    try:
        # Find ffmpeg
        ffmpeg_paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
        ffmpeg_cmd = None
        
        for path in ffmpeg_paths:
            if os.path.exists(path) or path == 'ffmpeg':
                ffmpeg_cmd = path
                break
        
        if not ffmpeg_cmd:
            raise RuntimeError("FFmpeg not found in any expected location")
        
        # Calculate optimal timecode if not provided
        if timecode is None:
            duration = get_video_duration(file_path)
            timecode = calculate_optimal_timecode(duration)
            print(f"  -> Using calculated timecode: {timecode}")
        
        # Generate thumbnail command
        cmd = [
            ffmpeg_cmd,
            '-y',  # Overwrite output file
            '-ss', timecode,  # Seek to timecode
            '-i', file_path,  # Input file
            '-frames:v', '1',  # Extract one frame
            '-q:v', '2',  # High quality
            '-vf', 'scale=640:360',  # Scale to reasonable size
            '-strict', 'unofficial',  # Allow non-standard YUV range
            '-pix_fmt', 'yuv420p',  # Use standard pixel format
            '-update', '1',  # Update existing file (fixes image2 muxer warning)
            output_path,  # Output file
            '-loglevel', 'error'  # Show errors but not info
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            print(f"  -> FFmpeg error: {result.stderr}")
            
            # If the first attempt fails, try with a fallback timecode
            if timecode != "00:00:00.1":
                print(f"  -> Retrying with fallback timecode: 00:00:00.1")
                cmd[3] = "00:00:00.1"  # Update timecode in command
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                
                if result.returncode != 0:
                    print(f"  -> FFmpeg error on retry: {result.stderr}")
                    return False
            
        # Check if thumbnail was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"  -> Thumbnail generated successfully: {output_path}")
            return True
        else:
            print(f"  -> Thumbnail file not created or empty")
            return False
        
    except subprocess.TimeoutExpired:
        print(f"  -> FFmpeg timed out")
        return False
    except Exception as e:
        print(f"  -> Error generating thumbnail: {e}")
        return False

def upload_thumbnail_to_filemaker(token, layout, record_id, field_name, file_path, filename):
    """Upload thumbnail to FileMaker container field."""
    print(f"  -> Uploading thumbnail to FileMaker: {filename}")
    
    try:
        # Construct upload URL
        # Format: /layouts/{layout}/records/{recordId}/containers/{fieldName}/{repetition}
        upload_url = config.url(f"layouts/{layout}/records/{record_id}/containers/{field_name}/1")
        
        # Prepare file for upload
        with open(file_path, 'rb') as f:
            files = {"upload": (filename, f, "image/jpeg")}
            headers = {"Authorization": f"Bearer {token}"}
            
            response = requests.post(
                upload_url,
                headers=headers,
                files=files,
                verify=False,
                timeout=60
            )
        
        if response.status_code == 200:
            print(f"  -> Thumbnail uploaded successfully")
            return True
        else:
            print(f"  -> Upload failed: {response.status_code}")
            print(f"  -> Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"  -> Error uploading thumbnail: {e}")
        return False



if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    footage_id = sys.argv[1]
    
    # Flexible token handling
    if len(sys.argv) == 2:
        token = config.get_token()
        print(f"Direct mode: Created new FileMaker session for {footage_id}")
    elif len(sys.argv) == 3:
        token = sys.argv[2]
        print(f"Subprocess mode: Using provided token for {footage_id}")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py footage_id [token]\n")
        sys.exit(1)
    
    try:
        print(f"Starting thumbnail generation for footage {footage_id}")
        
        # Get the current record to find the file path
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        record_data = config.get_record(token, "FOOTAGE", record_id)
        file_path = record_data[FIELD_MAPPING["filepath"]]
        
        print(f"Processing file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Footage file not found: {file_path}")
        
        # Generate footage-level thumbnail
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
            temp_thumbnail_path = temp_file.name
        
        try:
            if generate_footage_thumbnail(file_path, temp_thumbnail_path):
                # Upload thumbnail to FileMaker
                thumbnail_filename = f"thumbnail_{footage_id}.jpg"
                
                if upload_thumbnail_to_filemaker(
                    token, 
                    "FOOTAGE", 
                    record_id, 
                    FIELD_MAPPING["thumbnail"],  # Use full field name for container field
                    temp_thumbnail_path, 
                    thumbnail_filename
                ):
                    print(f"✅ Footage thumbnail generated and uploaded for {footage_id}")
                else:
                    print(f"❌ Failed to upload footage thumbnail")
                    sys.exit(1)
            else:
                print(f"❌ Failed to generate footage thumbnail")
                sys.exit(1)
                
        finally:
            # Clean up temporary file
            if os.path.exists(temp_thumbnail_path):
                os.remove(temp_thumbnail_path)
        
        print(f"✅ Footage thumbnail generation completed for {footage_id}")
        print(f"   Frame thumbnail triggering will be handled client-side")
        
    except Exception as e:
        print(f"❌ Error processing footage {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 