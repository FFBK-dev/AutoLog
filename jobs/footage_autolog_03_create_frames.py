#!/usr/bin/env python3
import sys, os, subprocess, math
import warnings
from pathlib import Path
import requests
import json

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    # FOOTAGE Layout Fields (for looking up parent record)
    "footage_id": "INFO_FTG_ID",
    "filepath": "SPECS_Filepath_Server",
    # FRAMES Layout Fields (for creating frame records)
    "frame_parent_id": "FRAMES_ParentID",
    "frame_status": "FRAMES_Status",
    "frame_timecode": "FRAMES_TC_IN",
    "frame_id": "FRAMES_ID",
    "frame_thumbnail": "FRAMES_Thumbnail",
    "frame_framerate": "FOOTAGE::SPECS_File_Framerate"  # Related field from parent
}

def get_video_info(file_path):
    """Get video duration and framerate using FFprobe."""
    print(f"  -> Getting video info for: {file_path}")
    
    try:
        # Find ffprobe
        ffprobe_paths = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', 'ffprobe']
        ffprobe_cmd = None
        
        for path in ffprobe_paths:
            if os.path.exists(path) or path == 'ffprobe':
                ffprobe_cmd = path
                break
        
        if not ffprobe_cmd:
            raise RuntimeError("FFprobe not found in any expected location")
        
        # Get duration and streams info using ffprobe
        cmd = [
            ffprobe_cmd,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f"  -> FFprobe error: {result.stderr}")
            return None, None
        
        # Parse JSON output
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])
        
        # Find video stream and get framerate
        framerate = 30.0  # Default fallback
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                # Parse framerate from r_frame_rate (e.g., "24/1" or "30000/1001")
                if 'r_frame_rate' in stream:
                    rate_str = stream['r_frame_rate']
                    if '/' in rate_str:
                        num, den = rate_str.split('/')
                        framerate = float(num) / float(den)
                    else:
                        framerate = float(rate_str)
                break
        
        print(f"  -> Video duration: {duration:.2f} seconds")
        print(f"  -> Video framerate: {framerate:.2f} fps")
        return duration, framerate
        
    except subprocess.TimeoutExpired:
        print(f"  -> FFprobe timed out")
        return None, None
    except Exception as e:
        print(f"  -> Error getting video info: {e}")
        return None, None

def format_timecode(seconds, framerate):
    """Convert seconds to HH:MM:SS:FF format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    frames = int((seconds % 1) * framerate)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"

def generate_frame_thumbnail(file_path, timecode_seconds, frame_id):
    """Generate thumbnail for a frame at specific timecode."""
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
        
        # Create temp thumbnail
        temp_dir = "/private/tmp"
        os.makedirs(temp_dir, exist_ok=True)
        thumb_filename = f"frame_{frame_id}.jpg"
        thumb_path = os.path.join(temp_dir, thumb_filename)
        
        # Generate thumbnail at specific timecode
        cmd = [
            ffmpeg_cmd, "-y", "-ss", str(timecode_seconds),
            "-i", file_path, "-frames:v", "1", thumb_path,
            "-loglevel", "quiet"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"    -> FFmpeg error generating thumbnail: {result.stderr}")
            return None
        
        if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) == 0:
            print(f"    -> Thumbnail file not created or empty")
            return None
        
        return thumb_path
        
    except subprocess.TimeoutExpired:
        print(f"    -> FFmpeg timed out generating thumbnail")
        return None
    except Exception as e:
        print(f"    -> Error generating thumbnail: {e}")
        return None

def create_frame_record(token, footage_id, file_path, timecode_seconds, framerate, frame_number):
    """Create a single FRAMES record with thumbnail."""
    try:
        # Generate frame ID in ParentID_### format
        frame_id = f"{footage_id}_{frame_number:03d}"
        
        # Format timecode properly
        timecode_formatted = format_timecode(timecode_seconds, framerate)
        
        # Create record payload
        payload = {
            "fieldData": {
                FIELD_MAPPING["frame_parent_id"]: footage_id,
                FIELD_MAPPING["frame_timecode"]: timecode_formatted,
                FIELD_MAPPING["frame_status"]: "1 - Pending Thumbnail",
                FIELD_MAPPING["frame_id"]: frame_id,
                FIELD_MAPPING["frame_framerate"]: framerate
            }
        }
        
        response = requests.post(
            config.url("layouts/FRAMES/records"),
            headers=config.api_headers(token),
            json=payload,
            verify=False
        )
        
        if response.status_code in [200, 201]:  # FileMaker returns 200 for successful record creation
            record_id = response.json()['response']['recordId']
            print(f"    -> Created frame {frame_id} at {timecode_formatted} (record {record_id})")
            
            # Generate and upload thumbnail
            thumb_path = generate_frame_thumbnail(file_path, timecode_seconds, frame_id)
            
            if thumb_path:
                # Upload thumbnail to container field
                upload_url = config.url(f"layouts/FRAMES/records/{record_id}/containers/{FIELD_MAPPING['frame_thumbnail']}/1")
                
                with open(thumb_path, "rb") as f:
                    files = {"upload": (f"frame_{frame_id}.jpg", f, "image/jpeg")}
                    upload_resp = requests.post(
                        upload_url, 
                        headers={"Authorization": f"Bearer {token}"}, 
                        files=files, 
                        verify=False
                    )
                
                if upload_resp.status_code == 200:
                    print(f"    -> ✅ Thumbnail uploaded for frame {frame_id}")
                    
                    # Update status to show thumbnail is complete
                    config.update_record(token, "FRAMES", record_id, {
                        FIELD_MAPPING["frame_status"]: "2 - Thumbnail Complete"
                    })
                else:
                    print(f"    -> ❌ Failed to upload thumbnail for frame {frame_id}: {upload_resp.status_code}")
                
                # Clean up temp file
                try:
                    os.remove(thumb_path)
                except:
                    pass
            else:
                print(f"    -> ❌ Failed to generate thumbnail for frame {frame_id}")
            
            return True, record_id
        else:
            print(f"    -> Failed to create frame {frame_id}: {response.status_code}")
            return False, None
            
    except Exception as e:
        print(f"    -> Error creating frame record: {e}")
        return False, None

def create_all_frame_records(token, footage_id, file_path, duration, framerate, interval=5):
    """Create FRAMES records for every interval seconds of video."""
    print(f"  -> Creating frame records every {interval} seconds for {duration:.2f}s video")
    
    # Calculate number of frames needed
    num_frames = math.ceil(duration / interval)
    print(f"  -> Will create {num_frames} frame records")
    
    successful_creates = 0
    created_records = []
    
    for i in range(num_frames):
        timecode_seconds = i * interval
        
        # Don't exceed video duration
        if timecode_seconds > duration:
            timecode_seconds = duration
        
        timecode_formatted = format_timecode(timecode_seconds, framerate)
        print(f"    -> Creating frame {i+1}/{num_frames} at {timecode_formatted} ({timecode_seconds}s)")
        
        success, record_id = create_frame_record(token, footage_id, file_path, timecode_seconds, framerate, i+1)
        
        if success:
            successful_creates += 1
            created_records.append({
                'record_id': record_id,
                'timecode': timecode_seconds,
                'frame_number': i+1
            })
        else:
            print(f"    -> Failed to create frame at {timecode_seconds}s")
    
    print(f"  -> Successfully created {successful_creates}/{num_frames} frame records")
    return created_records



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
        print(f"Starting frame record creation for footage {footage_id}")
        
        # Get the current record to find the file path
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        record_data = config.get_record(token, "FOOTAGE", record_id)
        file_path = record_data[FIELD_MAPPING["filepath"]]
        
        print(f"Processing file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Footage file not found: {file_path}")
        
        # Get video duration and framerate
        duration, framerate = get_video_info(file_path)
        if duration is None or framerate is None:
            raise RuntimeError("Could not determine video duration and framerate")
        
        # Create frame records with thumbnails
        created_records = create_all_frame_records(token, footage_id, file_path, duration, framerate)
        
        if not created_records:
            raise RuntimeError("Failed to create any frame records")
        
        print(f"✅ Frame record creation completed for footage {footage_id}")
        print(f"   Created {len(created_records)} frame records with thumbnails")
        print(f"   Video: {duration:.2f}s at {framerate:.2f}fps")
        
    except Exception as e:
        print(f"❌ Error creating frame records for footage {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 