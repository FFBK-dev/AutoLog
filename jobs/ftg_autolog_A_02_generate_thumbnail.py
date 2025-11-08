#!/usr/bin/env python3
"""
LF AutoLog Step 2: Generate Parent Thumbnail
Creates a single thumbnail for the parent FOOTAGE record only.
"""

import sys
import os
import subprocess
import warnings
from pathlib import Path

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


def find_ffmpeg():
    """Find ffmpeg executable."""
    ffmpeg_paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
    for path in ffmpeg_paths:
        if os.path.exists(path) or path == 'ffmpeg':
            return path
    raise RuntimeError("FFmpeg not found")


def get_video_duration(file_path):
    """Get video duration using ffprobe."""
    try:
        ffprobe_paths = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', 'ffprobe']
        ffprobe_cmd = None
        
        for path in ffprobe_paths:
            if os.path.exists(path) or path == 'ffprobe':
                ffprobe_cmd = path
                break
        
        if not ffprobe_cmd:
            return None
        
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
        
        return None
        
    except Exception as e:
        print(f"  -> Error getting duration: {e}")
        return None


def calculate_optimal_timecode(duration):
    """Calculate optimal timecode based on video duration (matches old flow)."""
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


def generate_parent_thumbnail(video_path, footage_id):
    """Generate thumbnail from optimal timecode (matches old flow logic)."""
    try:
        ffmpeg_cmd = find_ffmpeg()
        
        # Calculate optimal timecode
        duration = get_video_duration(video_path)
        timecode = calculate_optimal_timecode(duration)
        print(f"  -> Using calculated timecode: {timecode}")
        
        # Create thumbnail
        temp_dir = "/private/tmp"
        os.makedirs(temp_dir, exist_ok=True)
        thumb_path = os.path.join(temp_dir, f"thumb_{footage_id}.jpg")
        
        # Generate thumbnail command (matches old flow exactly)
        cmd = [
            ffmpeg_cmd,
            '-y',  # Overwrite output file
            '-ss', timecode,  # Seek to timecode
            '-i', video_path,  # Input file
            '-frames:v', '1',  # Extract one frame
            '-q:v', '2',  # High quality
            '-vf', 'scale=640:360',  # Scale to reasonable size
            '-strict', 'unofficial',  # Allow non-standard YUV range
            '-pix_fmt', 'yuv420p',  # Use standard pixel format
            '-update', '1',  # Update existing file (fixes image2 muxer warning)
            thumb_path,  # Output file
            '-loglevel', 'error'  # Show errors but not info
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            print(f"  -> FFmpeg error: {result.stderr}")
            
            # If the first attempt fails, try with a fallback timecode
            if timecode != "00:00:00.1":
                print(f"  -> Retrying with fallback timecode: 00:00:00.1")
                cmd[2] = "00:00:00.1"  # Update timecode in command
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                
                if result.returncode != 0:
                    print(f"  -> FFmpeg error on retry: {result.stderr}")
                    return None
        
        # Check if thumbnail was created
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            file_size = os.path.getsize(thumb_path)
            print(f"  -> ✅ Generated parent thumbnail: {file_size/1024:.1f}KB")
            return thumb_path
        else:
            print(f"  -> ❌ Thumbnail file not created or empty")
            return None
            
    except subprocess.TimeoutExpired:
        print(f"  -> ❌ Thumbnail generation timed out")
        return None
    except Exception as e:
        print(f"  -> ❌ Error generating thumbnail: {e}")
        return None


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
        print(f"Starting parent thumbnail generation for {footage_id}")
        
        # Get the current record to find the file path
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        record_data = config.get_record(token, "FOOTAGE", record_id)
        file_path = record_data[FIELD_MAPPING["filepath"]]
        
        print(f"Processing file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            # Try mounting volume
            if not config.ensure_volume_mounted(file_path):
                raise FileNotFoundError(f"Footage file not accessible: {file_path}")
        
        # Generate thumbnail
        thumb_path = generate_parent_thumbnail(file_path, footage_id)
        
        if not thumb_path:
            raise RuntimeError("Failed to generate thumbnail")
        
        # Upload to FileMaker
        print(f"  -> Uploading thumbnail to FileMaker...")
        
        upload_url = config.url(f"layouts/FOOTAGE/records/{record_id}/containers/{FIELD_MAPPING['thumbnail']}/1")
        
        with open(thumb_path, "rb") as f:
            files = {"upload": (f"thumb_{footage_id}.jpg", f, "image/jpeg")}
            upload_resp = config.requests.post(
                upload_url,
                headers={"Authorization": f"Bearer {token}"},
                files=files,
                verify=False
            )
        
        if upload_resp.status_code == 200:
            print(f"  -> ✅ Thumbnail uploaded successfully")
        else:
            print(f"  -> ❌ Thumbnail upload failed: {upload_resp.status_code}")
            raise RuntimeError("Thumbnail upload failed")
        
        # Update status to "2 - Thumbnail Ready"
        status_update = {FIELD_MAPPING["status"]: "2 - Thumbnail Ready"}
        status_resp = config.update_record(token, "FOOTAGE", record_id, status_update)
        
        if status_resp.status_code == 200:
            print(f"  -> ✅ Status updated to: 2 - Thumbnail Ready")
        else:
            print(f"  -> ⚠️ Status update failed: {status_resp.status_code}")
        
        # Clean up temp file
        try:
            os.remove(thumb_path)
        except:
            pass
        
        print(f"✅ Parent thumbnail generation completed for {footage_id}")
        
    except Exception as e:
        print(f"❌ Error generating parent thumbnail for {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

