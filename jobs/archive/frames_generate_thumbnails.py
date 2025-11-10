#!/usr/bin/env python3
import sys, os, subprocess, tempfile
import warnings
from pathlib import Path
import requests
import concurrent.futures
import time

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# No arguments - automatically discovers pending frame thumbnails
__ARGS__ = []

FIELD_MAPPING = {
    "frame_id": "FRAMES_ID",
    "parent_id": "FRAMES_ParentID",
    "status": "FRAMES_Status",
    "timecode": "FRAMES_TC_IN",
    "thumbnail": "FRAMES_Thumbnail",
    "footage_filepath": "Footage::SPECS_Filepath_Server"
}

def find_pending_frame_thumbnails(token):
    """Find all frames with '1 - Pending Thumbnail' status."""
    try:
        print(f"🔍 Searching for frames with '1 - Pending Thumbnail' status...")
        
        query = {
            "query": [{FIELD_MAPPING["status"]: "1 - Pending Thumbnail"}],
            "limit": 100  # Process in reasonable batches
        }
        
        response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False
        )
        
        if response.status_code == 404:
            print(f"📋 No pending frame thumbnails found")
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        print(f"📋 Found {len(records)} frames pending thumbnail generation")
        return records
        
    except Exception as e:
        print(f"❌ Error finding pending frames: {e}")
        return []

def generate_frame_thumbnail(file_path, output_path, timecode):
    """Generate a thumbnail for a specific frame at timecode."""
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
        
        # Convert timecode to proper format if needed
        if isinstance(timecode, (int, float)):
            timecode = str(float(timecode))
        
        # Generate thumbnail command
        cmd = [
            ffmpeg_cmd,
            '-y',  # Overwrite output file
            '-ss', timecode,  # Seek to specific timecode
            '-i', file_path,  # Input file
            '-frames:v', '1',  # Extract one frame
            '-q:v', '2',  # High quality
            '-vf', 'scale=640:360',  # Scale to reasonable size
            output_path,  # Output file
            '-loglevel', 'quiet'  # Suppress output
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            return False, f"FFmpeg error: {result.stderr}"
        
        # Check if thumbnail was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, None
        else:
            return False, "Thumbnail file not created or empty"
        
    except subprocess.TimeoutExpired:
        return False, "FFmpeg timed out"
    except Exception as e:
        return False, f"Error generating thumbnail: {e}"

def upload_frame_thumbnail(token, record_id, file_path, filename):
    """Upload frame thumbnail to FileMaker container field."""
    try:
        upload_url = config.url(f"layouts/FRAMES/records/{record_id}/containers/Thumbnail/1")
        
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
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"  -> Error uploading thumbnail: {e}")
        return False

def update_frame_status(token, record_id, new_status):
    """Update the status of a frame record."""
    try:
        payload = {"fieldData": {FIELD_MAPPING["status"]: new_status}}
        response = requests.patch(
            config.url(f"layouts/FRAMES/records/{record_id}"),
            headers=config.api_headers(token),
            json=payload,
            verify=False
        )
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"  -> Error updating frame status: {e}")
        return False

def process_single_frame_thumbnail(token, frame_record):
    """Process thumbnail generation for a single frame."""
    try:
        record_id = frame_record['recordId']
        field_data = frame_record['fieldData']
        
        frame_id = field_data.get(FIELD_MAPPING["frame_id"], record_id)
        parent_id = field_data.get(FIELD_MAPPING["parent_id"])
        timecode = field_data.get(FIELD_MAPPING["timecode"])
        footage_filepath = field_data.get(FIELD_MAPPING["footage_filepath"])
        
        print(f"  📸 Processing frame {frame_id} at {timecode}s")
        
        # Validate required fields
        if not timecode:
            print(f"    ❌ Missing timecode for frame {frame_id}")
            return False
        
        if not footage_filepath:
            print(f"    ❌ Missing footage filepath for frame {frame_id}")
            return False
        
        if not os.path.exists(footage_filepath):
            print(f"    ❌ Footage file not found: {footage_filepath}")
            return False
        
        # Generate thumbnail
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
            temp_thumbnail_path = temp_file.name
        
        try:
            success, error = generate_frame_thumbnail(footage_filepath, temp_thumbnail_path, timecode)
            
            if not success:
                print(f"    ❌ Failed to generate thumbnail: {error}")
                return False
            
            # Upload thumbnail
            thumbnail_filename = f"frame_thumbnail_{frame_id}.jpg"
            if upload_frame_thumbnail(token, record_id, temp_thumbnail_path, thumbnail_filename):
                # Update status
                if update_frame_status(token, record_id, "2 - Thumbnail Created"):
                    print(f"    ✅ Frame {frame_id} thumbnail completed")
                    return True
                else:
                    print(f"    ❌ Failed to update status for frame {frame_id}")
                    return False
            else:
                print(f"    ❌ Failed to upload thumbnail for frame {frame_id}")
                return False
                
        finally:
            # Clean up temporary file
            if os.path.exists(temp_thumbnail_path):
                os.remove(temp_thumbnail_path)
                
    except Exception as e:
        print(f"    ❌ Error processing frame {frame_id}: {e}")
        return False

def run_frame_thumbnail_processing(token, max_workers=4):
    """Process all pending frame thumbnails in parallel."""
    frame_records = find_pending_frame_thumbnails(token)
    
    if not frame_records:
        return True, "No pending frame thumbnails found"
    
    print(f"🎬 Processing {len(frame_records)} frame thumbnails...")
    
    successful = 0
    failed = 0
    
    # Process frames in parallel with limited concurrency
    actual_max_workers = min(max_workers, len(frame_records))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        # Submit all tasks
        future_to_frame = {
            executor.submit(process_single_frame_thumbnail, token, frame_record): frame_record
            for frame_record in frame_records
        }
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_frame):
            frame_record = future_to_frame[future]
            try:
                result = future.result()
                if result:
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                frame_id = frame_record['fieldData'].get(FIELD_MAPPING["frame_id"], "unknown")
                print(f"    ❌ Exception processing frame {frame_id}: {e}")
    
    print(f"✅ Frame thumbnails completed: {successful} successful, {failed} failed")
    return successful > 0, f"Processed {successful}/{len(frame_records)} frame thumbnails"

if __name__ == "__main__":
    try:
        print("🚀 Starting frame thumbnail generation")
        
        token = config.get_token()
        
        # Run frame thumbnail processing
        success, message = run_frame_thumbnail_processing(token)
        
        if success:
            print(f"✅ {message}")
        else:
            print(f"⚠️ {message}")
            
    except Exception as e:
        print(f"❌ Critical error in frame thumbnail processing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 