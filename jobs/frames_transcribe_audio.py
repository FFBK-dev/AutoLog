#!/usr/bin/env python3
import sys, os, subprocess, time
import warnings
from pathlib import Path
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Import Whisper for audio transcription
try:
    import whisper
except ImportError:
    print("❌ Whisper library not found. Please install: pip install openai-whisper")
    sys.exit(1)

__ARGS__ = ["frame_id", "token"]

FIELD_MAPPING = {
    "frame_id": "FRAMES_ID",
    "frame_parent_id": "FRAMES_ParentID", 
    "frame_transcript": "FRAMES_Transcript",
    "frame_status": "FRAMES_Status",
    "frame_timecode": "FRAMES_TC_IN",
    "footage_id": "INFO_FTG_ID",
    "footage_filepath": "SPECS_Filepath_Server"
}

# Load Whisper model once (base model for good speed/accuracy balance)
whisper_model = None

def get_whisper_model():
    """Get or load Whisper model."""
    global whisper_model
    if whisper_model is None:
        print("  -> Loading Whisper model...")
        whisper_model = whisper.load_model("base")
    return whisper_model

def get_frame_record(token, frame_id):
    """Get frame record by FRAMES_ID."""
    try:
        query = {
            "query": [{FIELD_MAPPING["frame_id"]: frame_id}],
            "limit": 1
        }
        
        response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False
        )
        
        if response.status_code == 404:
            return None, None
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        if records:
            return records[0], records[0]['recordId']
        return None, None
        
    except Exception as e:
        print(f"Error finding frame record: {e}")
        return None, None

def get_footage_record(token, footage_id):
    """Get footage record by INFO_FTG_ID."""
    try:
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        record_data = config.get_record(token, "FOOTAGE", record_id)
        return record_data, record_id
        
    except Exception as e:
        print(f"Error getting footage record: {e}")
        return None, None

def extract_audio_segment(file_path, timecode_formatted, frame_id, duration=5):
    """Extract 5-second audio segment from video."""
    try:
        # Convert HH:MM:SS:FF to seconds for FFmpeg
        time_parts = timecode_formatted.split(':')
        if len(time_parts) == 4:
            hours, minutes, seconds, frames = map(int, time_parts)
            # Assume 24fps for frame conversion (could be improved)
            total_seconds = hours * 3600 + minutes * 60 + seconds + frames / 24.0
        else:
            # Fallback if format is different
            total_seconds = float(timecode_formatted) if '.' in timecode_formatted else float(timecode_formatted.replace(':', ''))
        
        # Find ffmpeg
        ffmpeg_paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
        ffmpeg_cmd = None
        
        for path in ffmpeg_paths:
            if os.path.exists(path) or path == 'ffmpeg':
                ffmpeg_cmd = path
                break
        
        if not ffmpeg_cmd:
            raise RuntimeError("FFmpeg not found")
        
        # First check if video has audio streams
        probe_cmd = [ffmpeg_cmd, "-i", file_path]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        has_audio = "Audio:" in probe_result.stderr
        
        if not has_audio:
            print(f"  -> No audio stream found in video")
            return None, True  # Return True for "silent"
        
        # Create temp audio file
        temp_dir = "/private/tmp"
        os.makedirs(temp_dir, exist_ok=True)
        audio_filename = f"audio_{frame_id}.wav"
        audio_path = os.path.join(temp_dir, audio_filename)
        
        # Extract audio segment
        cmd = [
            ffmpeg_cmd, "-y", 
            "-ss", str(total_seconds), 
            "-i", file_path,
            "-t", str(duration),  # 5 seconds
            "-vn",  # No video
            "-acodec", "pcm_s16le", 
            "-ar", "16000",  # 16kHz sample rate for Whisper
            "-ac", "1",  # Mono
            audio_path,
            "-loglevel", "quiet"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f"  -> FFmpeg error: {result.stderr}")
            return None, False
        
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            print(f"  -> No audio extracted")
            return None, True  # Likely silent
        
        return audio_path, False
        
    except Exception as e:
        print(f"  -> Error extracting audio: {e}")
        return None, False

def check_audio_silence(audio_path):
    """Check if audio file is mostly silent."""
    try:
        # Find ffmpeg
        ffmpeg_paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
        ffmpeg_cmd = None
        
        for path in ffmpeg_paths:
            if os.path.exists(path) or path == 'ffmpeg':
                ffmpeg_cmd = path
                break
        
        if not ffmpeg_cmd:
            return False
        
        # Use volumedetect filter to check audio levels
        result = subprocess.run(
            [ffmpeg_cmd, "-i", audio_path, "-af", "volumedetect", 
             "-f", "null", "-", "-loglevel", "quiet"],
            stderr=subprocess.PIPE, text=True, capture_output=True
        )
        
        vol_output = result.stderr
        mean_volume_line = next((line for line in vol_output.splitlines() if "mean_volume:" in line), None)
        
        if mean_volume_line:
            mean_volume_db = float(mean_volume_line.split("mean_volume:")[1].split(" dB")[0].strip())
            return mean_volume_db < -50  # Consider silence if below -50dB
        
    except Exception:
        pass  # If we can't check, assume not silent
    
    return False

def transcribe_audio(audio_path):
    """Transcribe audio using Whisper."""
    try:
        model = get_whisper_model()
        
        # Check for silence first
        if check_audio_silence(audio_path):
            print(f"  -> Audio is silent")
            return ""
        
        # Transcribe with Whisper
        result = model.transcribe(audio_path, language="en")
        transcript = result.get("text", "").strip()
        
        print(f"  -> Transcribed: '{transcript[:50]}{'...' if len(transcript) > 50 else ''}'")
        return transcript
        
    except Exception as e:
        print(f"  -> Error transcribing audio: {e}")
        return ""

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: frames_transcribe_audio.py <frame_id> <token>")
        sys.exit(1)
    
    frame_id = sys.argv[1]
    token = sys.argv[2]
    
    try:
        print(f"Transcribing audio for frame {frame_id}")
        
        # Get frame record
        frame_data, frame_record_id = get_frame_record(token, frame_id)
        if not frame_data:
            print(f"❌ Frame record not found: {frame_id}")
            sys.exit(1)
        
        frame_fields = frame_data['fieldData']
        footage_id = frame_fields.get(FIELD_MAPPING["frame_parent_id"])
        timecode = frame_fields.get(FIELD_MAPPING["frame_timecode"])
        
        if not footage_id or not timecode:
            print(f"❌ Missing required frame data: footage_id={footage_id}, timecode={timecode}")
            sys.exit(1)
        
        # Get footage record for file path
        footage_data, footage_record_id = get_footage_record(token, footage_id)
        if not footage_data:
            print(f"❌ Footage record not found: {footage_id}")
            sys.exit(1)
        
        file_path = footage_data.get(FIELD_MAPPING["footage_filepath"])
        if not file_path or not os.path.exists(file_path):
            print(f"❌ Video file not found: {file_path}")
            sys.exit(1)
        
        print(f"  -> Extracting 5-second audio from {timecode}")
        
        # Extract audio segment
        audio_path, is_silent = extract_audio_segment(file_path, timecode, frame_id)
        
        transcript = ""
        if is_silent:
            print(f"  -> Video has no audio or is silent")
            transcript = ""
        elif audio_path:
            # Transcribe audio
            transcript = transcribe_audio(audio_path)
            
            # Clean up temp file
            if os.path.exists(audio_path):
                os.remove(audio_path)
        else:
            print(f"❌ Failed to extract audio")
            sys.exit(1)
        
        # Update frame record
        update_data = {
            FIELD_MAPPING["frame_transcript"]: transcript,
            FIELD_MAPPING["frame_status"]: "4 - Audio Transcribed"
        }
        
        # Retry logic for session issues
        max_retries = 3
        for attempt in range(max_retries):
            try:
                success = config.update_record(token, "FRAMES", frame_record_id, update_data)
                break  # Success, exit retry loop
            except Exception as e:
                if "500" in str(e) and attempt < max_retries - 1:
                    print(f"  -> Retry {attempt + 1}/{max_retries} after 500 error")
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                    token = config.get_token()  # Refresh token only on error
                else:
                    raise  # Re-raise if not a 500 error or max retries reached
        if success:
            if transcript:
                print(f"✅ Audio transcribed for frame {frame_id}")
            else:
                print(f"✅ Frame {frame_id} marked as silent")
        else:
            print(f"❌ Failed to update frame record")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error processing frame {frame_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 