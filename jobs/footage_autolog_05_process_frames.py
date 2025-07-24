#!/usr/bin/env python3
import sys, os, time, subprocess
import warnings
from pathlib import Path
import requests
import concurrent.futures
import threading
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

def tprint(message):
    """Print with timestamp for performance debugging."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}")

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "frame_parent_id": "FRAMES_ParentID",
    "frame_status": "FRAMES_Status",
    "frame_id": "FRAMES_ID"
}

# Frame processing statuses
FRAME_STATUSES = {
    "PENDING_THUMBNAIL": "1 - Pending Thumbnail",
    "THUMBNAIL_COMPLETE": "2 - Thumbnail Complete", 
    "CAPTION_GENERATED": "3 - Caption Generated",
    "AUDIO_TRANSCRIBED": "4 - Audio Transcribed"
}

def estimate_frame_processing_timeout(footage_id, token):
    """Estimate timeout based on video duration and frame count."""
    try:
        # Get video duration and frame count from FileMaker
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        if not record_id:
            return 1800  # Default 30 minutes
        
        response = requests.get(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code != 200:
            return 1800
        
        record_data = response.json()['response']['data'][0]['fieldData']
        duration_str = record_data.get('SPECS_File_Duration_Timecode', '')
        frame_count_str = record_data.get('SPECS_File_Frames', '')
        
        # Parse duration
        total_seconds = 0
        if duration_str:
            duration_parts = duration_str.split(':')
            if len(duration_parts) == 3:
                hours, minutes, seconds = map(int, duration_parts)
                total_seconds = hours * 3600 + minutes * 60 + seconds
            elif len(duration_parts) == 2:
                minutes, seconds = map(int, duration_parts)
                total_seconds = minutes * 60 + seconds
        
        # Parse frame count
        frame_count = 0
        try:
            frame_count = int(frame_count_str) if frame_count_str else 0
        except:
            pass
        
        # Estimate processing time: base + per-frame overhead
        base_time = 300  # 5 minutes base
        per_frame_time = 2  # 2 seconds per frame for AI processing
        estimated_time = base_time + (frame_count * per_frame_time)
        
        # Cap at reasonable limits
        min_timeout = 900   # 15 minutes minimum
        max_timeout = 3600  # 1 hour maximum
        
        final_timeout = max(min_timeout, min(estimated_time, max_timeout))
        
        print(f"  -> 📹 Video {footage_id}: {duration_str} duration, {frame_count} frames -> {final_timeout}s timeout")
        return final_timeout
        
    except Exception as e:
        print(f"  -> ⚠️ Could not estimate timeout for {footage_id}: {e}")
        return 1800  # Default 30 minutes

def find_frames_for_footage(token, footage_id):
    """Find all frame records for a given footage ID."""
    print(f"  -> Finding frame records for footage: {footage_id}")
    
    try:
        query = {
            "query": [{FIELD_MAPPING["frame_parent_id"]: footage_id}],
            "limit": 1000  # Allow for many frames per footage
        }
        
        response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False
        )
        
        if response.status_code == 404:
            print(f"  -> No frame records found for footage {footage_id}")
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        print(f"  -> Found {len(records)} frame records")
        return records
        
    except Exception as e:
        print(f"  -> Error finding frame records: {e}")
        return []

def get_frames_by_status(frames, status):
    """Filter frames by status."""
    return [frame for frame in frames if frame['fieldData'].get(FIELD_MAPPING["frame_status"]) == status]

def update_frame_status(token, record_id, new_status):
    """Update the status of a frame record with retry logic."""
    try:
        update_data = {FIELD_MAPPING["frame_status"]: new_status}
        current_token = token
        
        # Retry logic for session issues
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = config.update_record(current_token, "FRAMES", record_id, update_data)
                return response.status_code == 200
            except Exception as e:
                if "500" in str(e) and attempt < max_retries - 1:
                    print(f"  -> Retry {attempt + 1}/{max_retries} after 500 error on frame {record_id}")
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                    current_token = config.get_token()  # Refresh token only on error
                else:
                    raise  # Re-raise if not a 500 error or max retries reached
        
        return False
        
    except Exception as e:
        print(f"  -> Error updating frame status: {e}")
        return False

def run_frame_script_with_retry(script_name, frame_id, token, timeout=300, max_retries=2):
    """Run a frame processing script with retry logic."""
    script_path = Path(__file__).parent / script_name
    
    if not script_path.exists():
        print(f"  -> ERROR: Frame script not found: {script_name}")
        return False
    
    for attempt in range(max_retries + 1):
        try:
            print(f"    -> Running {script_name} for frame {frame_id} (attempt {attempt + 1}/{max_retries + 1}, timeout: {timeout}s)")
            result = subprocess.run(
                ["python3", str(script_path), frame_id, token],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return True
            
            # Show error output for debugging
            print(f"    -> STDOUT: {result.stdout}")
            print(f"    -> STDERR: {result.stderr}")
            
            if attempt < max_retries:
                print(f"    -> ⚠️ Attempt {attempt + 1} failed, retrying in 5 seconds...")
                time.sleep(5)
            else:
                print(f"    -> ❌ All {max_retries + 1} attempts failed for frame {frame_id}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"    -> ⚠️ Frame script timed out: {script_name} for {frame_id} after {timeout}s")
            if attempt < max_retries:
                print(f"    -> Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print(f"    -> ❌ All attempts timed out for frame {frame_id}")
                return False
        except Exception as e:
            print(f"    -> ⚠️ Frame script error: {script_name} for {frame_id} - {e}")
            if attempt < max_retries:
                print(f"    -> Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print(f"    -> ❌ All attempts failed for frame {frame_id}")
                return False
    
    return False

def is_frame_ready_for_next_step(frame_data):
    """Check if a frame is ready to proceed to the next step."""
    status = frame_data.get(FIELD_MAPPING["frame_status"], "")
    caption = frame_data.get("FRAMES_Caption", "").strip()
    transcript = frame_data.get("FRAMES_Transcript", "").strip()
    
    # Frame is ready if:
    # 1. Status is "4 - Audio Transcribed" or higher, OR
    # 2. Has caption (for caption step), OR  
    # 3. Has transcript (for audio step), OR
    # 4. Status indicates it's already completed this step
    
    if status in ["4 - Audio Transcribed", "5 - Generating Embeddings", "6 - Embeddings Complete"]:
        return True
    
    # For caption step: ready if has caption or status is "3 - Caption Generated" or higher
    if "caption" in frame_data.get("_processing_step", ""):
        return caption or status in ["3 - Caption Generated", "4 - Audio Transcribed", "5 - Generating Embeddings", "6 - Embeddings Complete"]
    
    # For audio step: ready if has transcript or status is "4 - Audio Transcribed" or higher
    if "audio" in frame_data.get("_processing_step", ""):
        return transcript or status in ["4 - Audio Transcribed", "5 - Generating Embeddings", "6 - Embeddings Complete"]
    
    return False

def process_frame_thumbnails(token, frames):
    """Process thumbnail generation for frames with parallel processing and retry logic."""
    pending_frames = get_frames_by_status(frames, FRAME_STATUSES["PENDING_THUMBNAIL"])
    
    if not pending_frames:
        print(f"  -> No frames pending thumbnail generation")
        return True
    
    tprint(f"  -> Processing {len(pending_frames)} frame thumbnails in parallel...")
    
    # Process frames in parallel with high concurrency for speed
    max_workers = min(12, len(pending_frames))  # Up to 12 parallel workers for thumbnails
    successful = 0
    
    def process_single_thumbnail(frame):
        frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame['recordId'])
        tprint(f"    -> Processing thumbnail for frame {frame_id}")
        
        if run_frame_script_with_retry("frames_generate_thumbnails.py", frame_id, token, timeout=180, max_retries=3):
            tprint(f"    -> ✅ Thumbnail generated for frame {frame_id}")
            return True
        else:
            tprint(f"    -> ❌ Thumbnail failed for frame {frame_id} after retries")
            return False
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_frame = {executor.submit(process_single_thumbnail, frame): frame for frame in pending_frames}
        
        for future in concurrent.futures.as_completed(future_to_frame):
            if future.result():
                successful += 1
    
    print(f"  -> Frame thumbnails: {successful}/{len(pending_frames)} completed")
    return successful > 0

def process_frame_captions(token, frames):
    """Process caption generation for frames with parallel processing and retry logic."""
    # Refresh frame data to get updated statuses
    footage_id = frames[0]['fieldData'].get(FIELD_MAPPING["frame_parent_id"])
    frames = find_frames_for_footage(token, footage_id)
    
    # Get frames that need caption processing (including stuck frames)
    caption_needed_frames = []
    for frame in frames:
        frame_data = frame['fieldData']
        status = frame_data.get(FIELD_MAPPING["frame_status"])
        caption = frame_data.get("FRAMES_Caption", "").strip()
        
        # Need caption if:
        # 1. Status is "2 - Thumbnail Complete" or lower, and doesn't have caption
        # 2. OR status is "3 - Caption Generated" but no caption content (stuck frame)
        if ((status in [FRAME_STATUSES["THUMBNAIL_COMPLETE"], FRAME_STATUSES["PENDING_THUMBNAIL"]] and not caption) or
            (status == "3 - Caption Generated" and not caption)):
            frame_data["_processing_step"] = "caption"  # Mark for caption processing
            caption_needed_frames.append(frame)
    
    if not caption_needed_frames:
        print(f"  -> No frames need caption generation")
        return True
    
    print(f"  -> Processing {len(caption_needed_frames)} frame captions in parallel...")
    
    # Process frames in parallel with high concurrency for speed
    max_workers = min(8, len(caption_needed_frames))  # Up to 8 parallel workers for AI operations
    successful = 0
    
    def process_single_caption(frame):
        frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame['recordId'])
        print(f"    -> Processing caption for frame {frame_id}")
        
        if run_frame_script_with_retry("frames_generate_captions.py", frame_id, token, timeout=120, max_retries=3):
            print(f"    -> ✅ Caption generated for frame {frame_id}")
            return True
        else:
            print(f"    -> ❌ Caption failed for frame {frame_id} after retries")
            return False
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_frame = {executor.submit(process_single_caption, frame): frame for frame in caption_needed_frames}
        
        for future in concurrent.futures.as_completed(future_to_frame):
            if future.result():
                successful += 1
    
    print(f"  -> Frame captions: {successful}/{len(caption_needed_frames)} completed")
    return successful > 0

def check_video_has_audio(file_path):
    """Quick check if video file has audio streams using ffprobe."""
    try:
        # Find ffmpeg tools
        ffprobe_paths = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', 'ffprobe']
        ffprobe_cmd = None
        
        for path in ffprobe_paths:
            if os.path.exists(path) or path == 'ffprobe':
                ffprobe_cmd = path
                break
        
        if not ffprobe_cmd:
            # Fallback to ffmpeg if ffprobe not found
            ffmpeg_paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
            for path in ffmpeg_paths:
                if os.path.exists(path) or path == 'ffmpeg':
                    # Use ffmpeg to probe for audio
                    result = subprocess.run([path, "-i", file_path], 
                                          capture_output=True, text=True, timeout=10)
                    return "Audio:" in result.stderr
            return None  # Can't detect, proceed with transcription
        
        # Use ffprobe to check for audio streams
        result = subprocess.run([
            ffprobe_cmd, "-v", "quiet", "-select_streams", "a", 
            "-show_entries", "stream=codec_type", "-of", "csv=p=0", file_path
        ], capture_output=True, text=True, timeout=10)
        
        # If we get output, there are audio streams
        has_audio = bool(result.stdout.strip())
        return has_audio
        
    except Exception as e:
        # If we can't detect, assume it has audio and let transcription handle it
        print(f"    -> Warning: Could not detect audio streams ({e}), proceeding with transcription")
        return None

def process_frame_audio_with_precheck(token, frames):
    """Process audio transcription with fast audio detection pre-check."""
    # Refresh frame data to get updated statuses
    footage_id = frames[0]['fieldData'].get(FIELD_MAPPING["frame_parent_id"])
    frames = find_frames_for_footage(token, footage_id)
    
    # Get footage file path for audio detection
    try:
        footage_record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        footage_response = requests.get(
            config.url(f"layouts/FOOTAGE/records/{footage_record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        footage_filepath = footage_response.json()['response']['data'][0]['fieldData'].get('SPECS_Filepath_Server')
    except Exception as e:
        print(f"  -> Warning: Could not get footage filepath for audio detection: {e}")
        footage_filepath = None
    
    # Quick audio detection
    has_audio = None
    if footage_filepath and os.path.exists(footage_filepath):
        print(f"  -> 🔍 Quick audio detection for {footage_id}...")
        has_audio = check_video_has_audio(footage_filepath)
        if has_audio is True:
            print(f"  -> ✅ Video has audio streams - will process transcription")
        elif has_audio is False:
            print(f"  -> 📵 Video has NO audio streams - will skip transcription and mark as silent")
        else:
            print(f"  -> ⚠️ Could not detect audio - will attempt transcription")
    
    # Get frames that need audio processing (including stuck frames)
    audio_needed_frames = []
    skip_audio_frames = []  # Frames to mark as silent without processing
    
    for frame in frames:
        frame_data = frame['fieldData']
        status = frame_data.get(FIELD_MAPPING["frame_status"])
        caption = frame_data.get("FRAMES_Caption", "").strip()
        transcript = frame_data.get("FRAMES_Transcript", "").strip()
        
        # Need audio if:
        # 1. Has caption but no transcript, and status is "3 - Caption Generated" or lower
        # 2. OR status is "4 - Audio Transcribed" but no transcript content (stuck frame)
        frame_needs_audio = ((caption and not transcript and status in ["3 - Caption Generated", "2 - Thumbnail Complete", "1 - Pending Thumbnail"]) or
                           (status == "4 - Audio Transcribed" and not transcript))
        
        if frame_needs_audio:
            if has_audio is False:
                # Video has no audio - mark frame as silent without processing
                skip_audio_frames.append(frame)
            else:
                # Video has audio or unknown - process normally
                frame_data["_processing_step"] = "audio"
                audio_needed_frames.append(frame)
    
    # Fast-track silent frames (no audio processing needed)
    if skip_audio_frames:
        print(f"  -> 📵 Fast-tracking {len(skip_audio_frames)} frames as silent (no audio streams)")
        silent_success = 0
        
        for frame in skip_audio_frames:
            frame_record_id = frame['recordId']
            frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame_record_id)
            
            try:
                # Update frame with empty transcript and "Audio Transcribed" status
                update_data = {
                    "FRAMES_Transcript": "",
                    FIELD_MAPPING["frame_status"]: "4 - Audio Transcribed"
                }
                
                if update_frame_status_with_transcript(token, frame_record_id, update_data):
                    print(f"    -> ✅ Marked frame {frame_id} as silent")
                    silent_success += 1
                else:
                    print(f"    -> ❌ Failed to mark frame {frame_id} as silent")
            except Exception as e:
                print(f"    -> ❌ Error marking frame {frame_id} as silent: {e}")
        
        print(f"  -> Silent frames: {silent_success}/{len(skip_audio_frames)} marked")
    
    # Process remaining frames that need actual audio transcription
    if not audio_needed_frames:
        print(f"  -> No frames need audio transcription")
        return True
    
    print(f"  -> Processing {len(audio_needed_frames)} frame audio transcriptions in parallel...")
    
    # Process frames in parallel with high concurrency for speed
    max_workers = min(6, len(audio_needed_frames))  # Up to 6 parallel workers for audio transcription
    successful = 0
    
    def process_single_audio(frame):
        frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame['recordId'])
        print(f"    -> Processing audio for frame {frame_id}")
        
        if run_frame_script_with_retry("frames_transcribe_audio.py", frame_id, token, timeout=180, max_retries=3):
            print(f"    -> ✅ Audio transcribed for frame {frame_id}")
            return True
        else:
            print(f"    -> ❌ Audio transcription failed for frame {frame_id} after retries")
            return False
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_frame = {executor.submit(process_single_audio, frame): frame for frame in audio_needed_frames}
        
        for future in concurrent.futures.as_completed(future_to_frame):
            if future.result():
                successful += 1
    
    print(f"  -> Frame audio: {successful}/{len(audio_needed_frames)} completed")
    return successful > 0

# Backward compatibility alias
process_frame_audio = process_frame_audio_with_precheck

def update_frame_status_with_transcript(token, record_id, update_data):
    """Update frame with both transcript and status."""
    try:
        # Retry logic for session issues
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.patch(
                    config.url(f"layouts/FRAMES/records/{record_id}"),
                    headers=config.api_headers(token),
                    json={"fieldData": update_data},
                    verify=False,
                    timeout=30
                )
                return response.status_code == 200
            except Exception as e:
                if "500" in str(e) and attempt < max_retries - 1:
                    print(f"    -> Retry {attempt + 1}/{max_retries} after 500 error on frame {record_id}")
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                    token = config.get_token()  # Refresh token only on error
                else:
                    raise  # Re-raise if not a 500 error or max retries reached
        
        return False
        
    except Exception as e:
        print(f"    -> Error updating frame: {e}")
        return False

def wait_for_all_frames_complete(token, footage_id, max_wait_time=1800):
    """Wait for all frames to reach completion with faster, more aggressive logic."""
    print(f"  -> Waiting for all frames to complete processing...")
    
    start_time = time.time()
    last_check_time = start_time
    
    while time.time() - start_time < max_wait_time:
        current_time = time.time()
        
        # Check every 10 seconds for faster response (was 30)
        if current_time - last_check_time < 10:
            time.sleep(2)
            continue
        
        last_check_time = current_time
        frames = find_frames_for_footage(token, footage_id)
        
        if not frames:
            print(f"  -> No frames found for footage {footage_id}")
            return False
        
        # Count frames that are ready for next step
        ready_frames = 0
        stuck_frames = []
        stuck_details = []
        
        for frame in frames:
            frame_data = frame['fieldData']
            status = frame_data.get(FIELD_MAPPING["frame_status"])
            caption = frame_data.get("FRAMES_Caption", "").strip()
            transcript = frame_data.get("FRAMES_Transcript", "").strip()
            
            # Frame is ready for Step 6 if:
            # 1. Status is "4 - Audio Transcribed" or higher (audio step complete, regardless of transcript content), OR
            # 2. Has caption content (caption step complete)
            # Note: This matches the completion criteria used throughout the codebase
            if (status in ["4 - Audio Transcribed", "5 - Generating Embeddings", "6 - Embeddings Complete"] or
                caption):  # Has caption (caption step done)
                ready_frames += 1
            else:
                frame_id = frame_data.get(FIELD_MAPPING["frame_id"], frame['recordId'])
                stuck_frames.append(frame_id)
                stuck_details.append(f"{frame_id}:{status} (caption:{len(caption)},transcript:{len(transcript)})")
        
        if ready_frames == len(frames):
            print(f"  -> ✅ All {len(frames)} frames completed processing")
            print(f"     - {ready_frames} frames ready for next step")
            return True
        
        elapsed = current_time - start_time
        print(f"  -> Progress: {ready_frames}/{len(frames)} frames completed (elapsed: {elapsed:.0f}s)")
        
        # Show stuck frames more frequently and with more detail
        if stuck_frames:
            print(f"  -> ⚠️ {len(stuck_frames)} frames still processing: {stuck_frames[:5]}{'...' if len(stuck_frames) > 5 else ''}")
            
            # Show detailed stuck frame analysis more frequently
            if elapsed > 300:  # After 5 minutes (was 15)
                print(f"  -> 🔍 Stuck frame details:")
                for detail in stuck_details[:5]:  # Show first 5 stuck frames
                    print(f"     - {detail}")
            
            # After 10 minutes, suggest retry for stuck frames
            if elapsed > 600:
                print(f"  -> 🔄 Some frames appear stuck. Consider running step 5 again to retry stuck frames.")
    
    print(f"  -> ⚠️ Timeout waiting for frames to complete after {max_wait_time}s")
    return False

def detect_and_retry_stuck_frames(token, footage_id):
    """Detect frames stuck at intermediate steps and retry them."""
    print(f"  -> 🔍 Detecting stuck frames for {footage_id}...")
    
    frames = find_frames_for_footage(token, footage_id)
    if not frames:
        return False
    
    stuck_frames = []
    for frame in frames:
        frame_data = frame['fieldData']
        status = frame_data.get(FIELD_MAPPING["frame_status"])
        caption = frame_data.get("FRAMES_Caption", "").strip()
        transcript = frame_data.get("FRAMES_Transcript", "").strip()
        
        # Detect stuck frames:
        # 1. Status "2 - Thumbnail Complete" but no caption (stuck at caption step)
        # 2. Status "3 - Caption Generated" but no caption content (stuck at caption step)
        # 3. Status "4 - Audio Transcribed" but no transcript content (stuck at audio step)
        if ((status == "2 - Thumbnail Complete" and not caption) or
            (status == "3 - Caption Generated" and not caption) or
            (status == "4 - Audio Transcribed" and not transcript)):
            frame_id = frame_data.get(FIELD_MAPPING["frame_id"], frame['recordId'])
            stuck_frames.append((frame_id, status, "caption" if not caption else "audio"))
    
    if not stuck_frames:
        print(f"  -> ✅ No stuck frames detected")
        return True
    
    print(f"  -> 🔄 Found {len(stuck_frames)} stuck frames, retrying...")
    
    # Retry stuck frames
    successful_retries = 0
    for frame_id, status, step in stuck_frames:
        print(f"    -> Retrying {step} for stuck frame {frame_id} (status: {status})")
        
        if step == "caption":
            if run_frame_script_with_retry("frames_generate_captions.py", frame_id, token, timeout=120, max_retries=3):
                print(f"    -> ✅ Caption retry successful for {frame_id}")
                successful_retries += 1
            else:
                print(f"    -> ❌ Caption retry failed for {frame_id}")
        elif step == "audio":
            if run_frame_script_with_retry("frames_transcribe_audio.py", frame_id, token, timeout=180, max_retries=3):
                print(f"    -> ✅ Audio retry successful for {frame_id}")
                successful_retries += 1
            else:
                print(f"    -> ❌ Audio retry failed for {frame_id}")
    
    print(f"  -> 🔄 Retry results: {successful_retries}/{len(stuck_frames)} successful")
    return successful_retries > 0

# Removed mark_frames_ready_for_embeddings function - no longer needed
# Step 05 completes when all frames reach "4 - Audio Transcribed"
# Step 06 (Generate Embeddings) will process frames with "4 - Audio Transcribed" status

def process_frames_continuous_flow(token, frames, footage_id, estimated_timeout):
    """
    CONTINUOUS FLOW: Frames immediately proceed to next step when ready.
    No waiting for all frames to complete each step.
    """
    print(f"\n=== CONTINUOUS FLOW FRAME PROCESSING ===")
    print(f"  -> Frames flow independently through: Thumbnail → Caption → Audio")
    
    # Pre-check for audio to optimize processing
    footage_filepath = None
    try:
        footage_record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        footage_response = requests.get(
            config.url(f"layouts/FOOTAGE/records/{footage_record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        footage_filepath = footage_response.json()['response']['data'][0]['fieldData'].get('SPECS_Filepath_Server')
    except Exception as e:
        print(f"  -> Warning: Could not get footage filepath: {e}")
    
    # Quick audio detection
    has_audio = None
    if footage_filepath and os.path.exists(footage_filepath):
        print(f"  -> 🔍 Quick audio detection for {footage_id}...")
        has_audio = check_video_has_audio(footage_filepath)
        if has_audio is True:
            print(f"  -> ✅ Video has audio streams")
        elif has_audio is False:
            print(f"  -> 📵 Video has NO audio streams - will fast-track")
        else:
            print(f"  -> ⚠️ Could not detect audio")
    
    # Continuous flow processor
    max_workers = 15  # Higher concurrency for continuous flow
    completed_frames = set()
    start_time = time.time()
    
    def process_frame_continuously(frame):
        """Process a single frame through all steps."""
        frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame['recordId'])
        frame_record_id = frame['recordId']
        
        try:
            tprint(f"[FLOW] Starting frame {frame_id}")
            
            # Step 1: Thumbnail (if needed)
            current_status = frame['fieldData'].get(FIELD_MAPPING["frame_status"])
            if current_status == "1 - Pending Thumbnail":
                tprint(f"[FLOW] {frame_id}: Generating thumbnail...")
                if not run_frame_script_with_retry("frames_generate_thumbnails.py", frame_id, token, timeout=180, max_retries=2):
                    tprint(f"[FLOW] {frame_id}: ❌ Thumbnail failed")
                    return False
                tprint(f"[FLOW] {frame_id}: ✅ Thumbnail complete")
            
            # Refresh frame data to get updated status
            time.sleep(1)  # Brief pause for DB update
            current_frame = get_updated_frame_data(token, footage_id, frame_id)
            if not current_frame:
                tprint(f"[FLOW] {frame_id}: ❌ Could not get updated data")
                return False
            
            current_status = current_frame['fieldData'].get(FIELD_MAPPING["frame_status"])
            caption = current_frame['fieldData'].get("FRAMES_Caption", "").strip()
            
            # Step 2: Caption (if needed)
            if current_status in ["2 - Thumbnail Complete", "1 - Pending Thumbnail"] and not caption:
                tprint(f"[FLOW] {frame_id}: Generating caption...")
                if not run_frame_script_with_retry("frames_generate_captions.py", frame_id, token, timeout=120, max_retries=2):
                    tprint(f"[FLOW] {frame_id}: ❌ Caption failed")
                    return False
                tprint(f"[FLOW] {frame_id}: ✅ Caption complete")
            
            # Refresh frame data again
            time.sleep(1)  # Brief pause for DB update
            current_frame = get_updated_frame_data(token, footage_id, frame_id)
            if not current_frame:
                tprint(f"[FLOW] {frame_id}: ❌ Could not get updated data after caption")
                return False
            
            current_status = current_frame['fieldData'].get(FIELD_MAPPING["frame_status"])
            caption = current_frame['fieldData'].get("FRAMES_Caption", "").strip()
            transcript = current_frame['fieldData'].get("FRAMES_Transcript", "").strip()
            
            # Step 3: Audio (if needed)
            needs_audio = (caption and not transcript and current_status in ["3 - Caption Generated", "2 - Thumbnail Complete"])
            
            if needs_audio:
                if has_audio is False:
                    # Fast-track silent video
                    tprint(f"[FLOW] {frame_id}: Fast-tracking as silent...")
                    update_data = {
                        "FRAMES_Transcript": "",
                        FIELD_MAPPING["frame_status"]: "4 - Audio Transcribed"
                    }
                    if update_frame_status_with_transcript(token, frame_record_id, update_data):
                        tprint(f"[FLOW] {frame_id}: ✅ Marked as silent")
                    else:
                        tprint(f"[FLOW] {frame_id}: ❌ Failed to mark as silent")
                        return False
                else:
                    # Process audio normally
                    tprint(f"[FLOW] {frame_id}: Transcribing audio...")
                    if not run_frame_script_with_retry("frames_transcribe_audio.py", frame_id, token, timeout=180, max_retries=2):
                        tprint(f"[FLOW] {frame_id}: ❌ Audio failed")
                        return False
                    tprint(f"[FLOW] {frame_id}: ✅ Audio complete")
            
            tprint(f"[FLOW] {frame_id}: ✅ COMPLETE")
            return True
            
        except Exception as e:
            tprint(f"[FLOW] {frame_id}: ❌ Error - {e}")
            return False
    
    # Process all frames in parallel with continuous flow
    print(f"  -> 🚀 Launching {len(frames)} frames with continuous flow processing...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_frame = {
            executor.submit(process_frame_continuously, frame): frame 
            for frame in frames
        }
        
        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_frame):
            frame = future_to_frame[future]
            frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame['recordId'])
            
            try:
                success = future.result()
                if success:
                    completed_count += 1
                    completed_frames.add(frame_id)
                    progress_pct = (completed_count / len(frames)) * 100
                    elapsed = time.time() - start_time
                    tprint(f"[FLOW] Progress: {completed_count}/{len(frames)} ({progress_pct:.1f}%) - {frame_id}: ✅ ({elapsed:.1f}s elapsed)")
                else:
                    tprint(f"[FLOW] Progress: {completed_count}/{len(frames)} - {frame_id}: ❌")
            except Exception as e:
                tprint(f"[FLOW] Progress: {completed_count}/{len(frames)} - {frame_id}: ❌ (Exception: {e})")
    
    success_rate = (completed_count / len(frames)) * 100
    total_time = time.time() - start_time
    
    print(f"\n=== CONTINUOUS FLOW COMPLETE ===")
    print(f"  -> {completed_count}/{len(frames)} frames completed ({success_rate:.1f}%)")
    print(f"  -> Total time: {total_time:.1f}s")
    print(f"  -> Average per frame: {total_time/len(frames):.1f}s")
    
    return completed_count > 0

def get_updated_frame_data(token, footage_id, frame_id):
    """Get fresh frame data from FileMaker."""
    try:
        query = {
            "query": [
                {FIELD_MAPPING["frame_parent_id"]: footage_id},
                {FIELD_MAPPING["frame_id"]: frame_id}
            ],
            "limit": 1
        }
        
        response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False,
            timeout=10
        )
        
        if response.status_code == 200:
            records = response.json()['response']['data']
            return records[0] if records else None
        
        return None
        
    except Exception as e:
        print(f"    -> Error getting updated frame data for {frame_id}: {e}")
        return None

def monitor_and_process_frames_continuously(token, footage_id, estimated_timeout):
    """
    SMART FRAME MONITOR: Continuously polls for frames ready for processing.
    Handles failures, retries, and works with workflow interruptions.
    """
    print(f"\n=== SMART FRAME MONITORING AND PROCESSING ===")
    print(f"  -> Monitoring frames for {footage_id} with aggressive polling")
    
    # Pre-check for audio to optimize processing
    footage_filepath = None
    try:
        footage_record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        footage_response = requests.get(
            config.url(f"layouts/FOOTAGE/records/{footage_record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        footage_filepath = footage_response.json()['response']['data'][0]['fieldData'].get('SPECS_Filepath_Server')
    except Exception as e:
        print(f"  -> Warning: Could not get footage filepath: {e}")
    
    # Quick audio detection
    has_audio = None
    if footage_filepath and os.path.exists(footage_filepath):
        print(f"  -> 🔍 Quick audio detection for {footage_id}...")
        has_audio = check_video_has_audio(footage_filepath)
        if has_audio is True:
            print(f"  -> ✅ Video has audio streams")
        elif has_audio is False:
            print(f"  -> 📵 Video has NO audio streams - will fast-track")
        else:
            print(f"  -> ⚠️ Could not detect audio")
    
    start_time = time.time()
    last_activity = start_time
    poll_interval = 3  # Aggressive 3-second polling
    max_idle_time = 60  # If no progress for 60s, try interventions
    retry_attempts = {}  # Track retry attempts per frame
    completed_frames = set()
    
    print(f"  -> Starting monitoring loop (poll every {poll_interval}s)")
    
    while time.time() - start_time < estimated_timeout:
        current_time = time.time()
        
        # Get current frame status
        frames = find_frames_for_footage(token, footage_id)
        if not frames:
            print(f"  -> No frames found for {footage_id}, ending monitoring")
            break
        
        # Check for frames ready for each step
        frames_needing_captions = []
        frames_needing_audio = []
        frames_stuck = []
        total_ready = 0
        
        for frame in frames:
            frame_data = frame['fieldData']
            frame_id = frame_data.get(FIELD_MAPPING["frame_id"], frame['recordId'])
            status = frame_data.get(FIELD_MAPPING["frame_status"])
            caption = frame_data.get("FRAMES_Caption", "").strip()
            transcript = frame_data.get("FRAMES_Transcript", "").strip()
            
            # Check if frame is complete
            # Frame is ready for Step 6 if:
            # 1. Status is "4 - Audio Transcribed" or higher (audio step complete, regardless of transcript content), OR
            # 2. Has caption content (caption step complete)
            # Note: This matches the completion criteria used in the polling workflow
            if (status in ["4 - Audio Transcribed", "5 - Generating Embeddings", "6 - Embeddings Complete"] or
                caption):  # Has caption (caption step done)
                total_ready += 1
                completed_frames.add(frame_id)
                continue
            
            # Frame needs caption
            if status == "2 - Thumbnail Complete" and not caption:
                frames_needing_captions.append(frame)
            # Frame needs caption retry (has status but no content)
            elif status == "3 - Caption Generated" and not caption:
                frames_stuck.append((frame, "caption"))
            # Frame needs audio
            elif caption and not transcript and status in ["3 - Caption Generated", "2 - Thumbnail Complete"]:
                if has_audio is False:
                    # Silent video - fast track
                    frames_needing_audio.append((frame, "silent"))
                else:
                    frames_needing_audio.append((frame, "audio"))
            # Frame needs audio retry (has status but no content)
            elif status == "4 - Audio Transcribed" and not transcript and has_audio is not False:
                frames_stuck.append((frame, "audio"))
        
        # Check if all frames are complete
        if total_ready == len(frames):
            elapsed = current_time - start_time
            print(f"  -> ✅ All {len(frames)} frames completed in {elapsed:.1f}s")
            return True
        
        progress_changed = False
        
        # Process frames needing captions
        if frames_needing_captions:
            tprint(f"  -> 📝 Processing {len(frames_needing_captions)} frames needing captions")
            if process_frames_parallel(frames_needing_captions, "caption", token, max_workers=8):
                progress_changed = True
                last_activity = current_time
        
        # Process frames needing audio (including silent fast-tracking)
        if frames_needing_audio:
            audio_frames = [f for f, t in frames_needing_audio if t == "audio"]
            silent_frames = [f for f, t in frames_needing_audio if t == "silent"]
            
            if silent_frames:
                tprint(f"  -> 📵 Fast-tracking {len(silent_frames)} silent frames")
                if fast_track_silent_frames(silent_frames, token):
                    progress_changed = True
                    last_activity = current_time
            
            if audio_frames:
                tprint(f"  -> 🔊 Processing {len(audio_frames)} frames needing audio")
                if process_frames_parallel(audio_frames, "audio", token, max_workers=6):
                    progress_changed = True
                    last_activity = current_time
        
        # Handle stuck frames with retry logic
        if frames_stuck and current_time - last_activity > max_idle_time:
            tprint(f"  -> 🔧 Retrying {len(frames_stuck)} stuck frames")
            for frame, step_type in frames_stuck:
                frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame['recordId'])
                retry_key = f"{frame_id}_{step_type}"
                
                if retry_attempts.get(retry_key, 0) < 3:  # Max 3 retries per frame per step
                    retry_attempts[retry_key] = retry_attempts.get(retry_key, 0) + 1
                    tprint(f"    -> Retry {retry_attempts[retry_key]}/3 for {frame_id} ({step_type})")
                    
                    if step_type == "caption":
                        if run_frame_script_with_retry("frames_generate_captions.py", frame_id, token, timeout=120, max_retries=1):
                            progress_changed = True
                            last_activity = current_time
                    elif step_type == "audio":
                        if run_frame_script_with_retry("frames_transcribe_audio.py", frame_id, token, timeout=180, max_retries=1):
                            progress_changed = True
                            last_activity = current_time
        
        # Progress reporting
        elapsed = current_time - start_time
        progress_pct = (total_ready / len(frames)) * 100
        
        if elapsed % 15 < poll_interval:  # Report every 15 seconds
            tprint(f"  -> Progress: {total_ready}/{len(frames)} ({progress_pct:.1f}%) - {elapsed:.0f}s elapsed")
            if frames_needing_captions:
                tprint(f"    -> {len(frames_needing_captions)} frames waiting for captions")
            if frames_needing_audio:
                tprint(f"    -> {len(frames_needing_audio)} frames waiting for audio")
            if frames_stuck:
                tprint(f"    -> {len(frames_stuck)} frames stuck/retrying")
        
        # Check for parent footage status changes (e.g., "Awaiting User Input")
        try:
            parent_response = requests.get(
                config.url(f"layouts/FOOTAGE/records/{footage_record_id}"),
                headers=config.api_headers(token),
                verify=False,
                timeout=10
            )
            if parent_response.status_code == 200:
                parent_status = parent_response.json()['response']['data'][0]['fieldData'].get("AutoLog_Status", "")
                if parent_status == "Awaiting User Input":
                    print(f"  -> ⏸️ Parent footage is 'Awaiting User Input' - pausing frame monitoring")
                    return False  # Let parent workflow handle this
        except:
            pass  # Continue monitoring if we can't check parent status
        
        # Sleep before next poll
        time.sleep(poll_interval)
    
    # Timeout reached
    print(f"  -> ⏰ Frame monitoring timeout after {estimated_timeout}s")
    return total_ready == len(frames)

def process_frames_parallel(frames, step_type, token, max_workers=6):
    """Process multiple frames in parallel for a specific step."""
    if not frames:
        return True
    
    successful = 0
    script_map = {
        "caption": "frames_generate_captions.py",
        "audio": "frames_transcribe_audio.py"
    }
    
    script_name = script_map.get(step_type)
    if not script_name:
        return False
    
    def process_single_frame(frame):
        frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame['recordId'])
        return run_frame_script_with_retry(script_name, frame_id, token, 
                                         timeout=120 if step_type == "caption" else 180, 
                                         max_retries=2)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(frames))) as executor:
        future_to_frame = {executor.submit(process_single_frame, frame): frame for frame in frames}
        
        for future in concurrent.futures.as_completed(future_to_frame):
            if future.result():
                successful += 1
    
    return successful > 0

def fast_track_silent_frames(frames, token):
    """Fast-track frames for silent videos by marking them as audio transcribed."""
    successful = 0
    
    for frame in frames:
        frame_record_id = frame['recordId']
        frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame_record_id)
        
        try:
            update_data = {
                "FRAMES_Transcript": "",
                FIELD_MAPPING["frame_status"]: "4 - Audio Transcribed"
            }
            
            if update_frame_status_with_transcript(token, frame_record_id, update_data):
                successful += 1
            
        except Exception as e:
            print(f"    -> Error fast-tracking frame {frame_id}: {e}")
    
    return successful > 0

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
        tprint(f"Starting frame processing for footage {footage_id}")
        
        # Step 1: Find all frame records for this footage
        frames = find_frames_for_footage(token, footage_id)
        
        if not frames:
            print(f"⚠️ No frame records found for footage {footage_id}")
            print(f"✅ Frame processing completed (no frames to process)")
            sys.exit(0)
        
        print(f"Found {len(frames)} frame records to process")
        
        # Step 2: BULK SILENCE DETECTION - Handle silent videos immediately
        print(f"\n=== BULK SILENCE DETECTION ===")
        
        # Get footage file path for audio detection
        footage_filepath = None
        try:
            footage_record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
            footage_response = requests.get(
                config.url(f"layouts/FOOTAGE/records/{footage_record_id}"),
                headers=config.api_headers(token),
                verify=False,
                timeout=30
            )
            footage_filepath = footage_response.json()['response']['data'][0]['fieldData'].get('SPECS_Filepath_Server')
        except Exception as e:
            print(f"  -> Warning: Could not get footage filepath for bulk detection: {e}")
        
        # Quick bulk audio detection
        if footage_filepath and os.path.exists(footage_filepath):
            print(f"  -> 🔍 Checking if {footage_id} is silent...")
            has_audio = check_video_has_audio(footage_filepath)
            
            if has_audio is False:
                print(f"  -> 📵 Video is SILENT - bulk updating ALL frames!")
                
                # Count frames that need bulk update
                frames_needing_update = []
                for frame in frames:
                    frame_data = frame['fieldData']
                    status = frame_data.get(FIELD_MAPPING["frame_status"])
                    transcript = frame_data.get("FRAMES_Transcript", "").strip()
                    
                    # Update if not already at "4 - Audio Transcribed" with empty transcript
                    if status != "4 - Audio Transcribed" or transcript:
                        frames_needing_update.append(frame)
                
                if frames_needing_update:
                    print(f"  -> 🔄 Bulk updating {len(frames_needing_update)} frames as silent...")
                    
                    bulk_success = 0
                    for frame in frames_needing_update:
                        frame_record_id = frame['recordId']
                        frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], frame_record_id)
                        
                        try:
                            # Update frame with empty transcript and "Audio Transcribed" status
                            update_data = {
                                "FRAMES_Transcript": "",
                                FIELD_MAPPING["frame_status"]: "4 - Audio Transcribed"
                            }
                            
                            payload = {"fieldData": update_data}
                            response = requests.patch(
                                config.url(f"layouts/FRAMES/records/{frame_record_id}"),
                                headers=config.api_headers(token),
                                json=payload,
                                verify=False,
                                timeout=30
                            )
                            
                            if response.status_code == 200:
                                print(f"    -> ✅ {frame_id}: Marked as silent")
                                bulk_success += 1
                            else:
                                print(f"    -> ❌ {frame_id}: Update failed ({response.status_code})")
                                
                        except Exception as e:
                            print(f"    -> ❌ {frame_id}: Error updating: {e}")
                    
                    print(f"  -> 🎉 BULK UPDATE COMPLETE: {bulk_success}/{len(frames_needing_update)} frames updated")
                    
                    if bulk_success == len(frames_needing_update):
                        print(f"✅ Silent video optimization: ALL {len(frames)} frames marked as completed!")
                        print(f"🚀 {footage_id} ready for Step 6: Generate Description")
                        sys.exit(0)  # Successfully completed via bulk update
                    else:
                        print(f"⚠️ Bulk update partially failed - continuing with individual processing...")
                else:
                    print(f"  -> ✅ All frames already marked as silent - nothing to update")
                    print(f"✅ Frame processing completed for silent video {footage_id}")
                    sys.exit(0)
                    
            elif has_audio is True:
                print(f"  -> 🔊 Video HAS audio streams - proceeding with individual frame processing")
            else:
                print(f"  -> ⚠️ Could not detect audio - proceeding with individual frame processing")
        else:
            print(f"  -> ⚠️ File not accessible for bulk detection - proceeding with individual processing")
        
        # Step 3: Individual frame processing (for videos with audio or detection failures)
        # Estimate timeout based on video characteristics
        estimated_timeout = estimate_frame_processing_timeout(footage_id, token)
        tprint(f"  -> Estimated processing timeout: {estimated_timeout}s")
        
        # Use smart frame monitoring for maximum responsiveness
        print(f"\n🚀 Using SMART FRAME MONITORING for maximum responsiveness")
        if not monitor_and_process_frames_continuously(token, footage_id, estimated_timeout):
            print(f"❌ Smart frame monitoring failed or was interrupted")
            sys.exit(1)
        
        # Step 4: Final verification
        print(f"\n=== STEP 5: Frame Processing Complete ===")
        final_frames = find_frames_for_footage(token, footage_id)
        completed_count = len([f for f in final_frames if f['fieldData'].get(FIELD_MAPPING["frame_status"]) == "4 - Audio Transcribed"])
        print(f"✅ {completed_count}/{len(final_frames)} frames completed and ready for embeddings")
        
        print(f"✅ Frame processing completed successfully for footage {footage_id}")
        print(f"🔄 Step 5 complete - workflow controller will handle transition to step 6")
        
    except Exception as e:
        print(f"❌ Error processing frames for footage {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 