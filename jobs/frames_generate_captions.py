#!/usr/bin/env python3
import sys, os, subprocess, json, base64, time
import warnings
from pathlib import Path
import requests
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.openai_client import global_openai_client

__ARGS__ = ["frame_id", "token"]

FIELD_MAPPING = {
    "frame_id": "FRAMES_ID",
    "frame_parent_id": "FRAMES_ParentID", 
    "frame_caption": "FRAMES_Caption",
    "frame_status": "FRAMES_Status",
    "frame_timecode": "FRAMES_TC_IN",
    "footage_id": "INFO_FTG_ID",
    "footage_metadata": "INFO_Metadata",
    "footage_source": "INFO_Source", 
    "footage_filename": "INFO_Filename",
    "footage_filepath": "SPECS_Filepath_Server",
    "footage_ai_prompt": "AI_Prompt",
    "globals_api_key_1": "SystemGlobals_AutoLog_OpenAI_API_Key_1",
    "globals_api_key_2": "SystemGlobals_AutoLog_OpenAI_API_Key_2",
    "globals_api_key_3": "SystemGlobals_AutoLog_OpenAI_API_Key_3",
    "globals_api_key_4": "SystemGlobals_AutoLog_OpenAI_API_Key_4",
    "globals_api_key_5": "SystemGlobals_AutoLog_OpenAI_API_Key_5"
}

# Load prompts from global prompts.json
prompts_path = Path(__file__).resolve().parent.parent / "prompts" / "prompts.json"
try:
    with open(prompts_path, 'r') as f:
        PROMPTS = json.load(f)
except Exception as e:
    print(f"❌ Error loading prompts.json: {e}")
    sys.exit(1)

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

def generate_thumbnail_from_timecode(file_path, timecode_formatted, frame_id):
    """Generate thumbnail from video file using timecode for captioning."""
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
        
        # Create temp thumbnail for captioning
        temp_dir = "/private/tmp"
        os.makedirs(temp_dir, exist_ok=True)
        thumb_filename = f"caption_{frame_id}.jpg"
        thumb_path = os.path.join(temp_dir, thumb_filename)
        
        # Generate thumbnail at specific timecode
        cmd = [
            ffmpeg_cmd, "-y", "-ss", str(total_seconds),
            "-i", file_path, "-frames:v", "1", thumb_path,
            "-loglevel", "quiet"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"  -> FFmpeg error: {result.stderr}")
            return None
        
        if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) == 0:
            print(f"  -> Thumbnail not created")
            return None
        
        print(f"  -> Generated thumbnail for captioning")
        return thumb_path
        
    except Exception as e:
        print(f"  -> Error generating thumbnail: {e}")
        return None

def get_footage_dev_console(record_id, token):
    """Get the current AI_DevConsole content from a footage record."""
    try:
        response = requests.get(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        response.raise_for_status()
        record_data = response.json()['response']['data'][0]['fieldData']
        return record_data.get("AI_DevConsole", "")
    except Exception as e:
        print(f"  -> WARNING: Failed to get footage AI_DevConsole: {e}")
        return ""

def write_to_footage_dev_console(record_id, token, message):
    """Write a message to the AI_DevConsole field of a footage record."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console_entry = f"[{timestamp}] {message}"
        
        # Get current console content to append rather than overwrite
        current_console = get_footage_dev_console(record_id, token)
        
        # Append new message
        if current_console:
            new_console = current_console + "\n\n" + console_entry
        else:
            new_console = console_entry
        
        # Update the AI_DevConsole field
        field_data = {"AI_DevConsole": new_console}
        config.update_record(token, "FOOTAGE", record_id, field_data)
        
    except Exception as e:
        print(f"  -> WARNING: Failed to write to footage AI_DevConsole: {e}")

def setup_openai_client(token):
    """Set up OpenAI client with API keys from SystemGlobals."""
    try:
        # Get all API keys from SystemGlobals
        system_globals = config.get_system_globals(token)
        
        # Collect all available API keys
        api_keys = []
        for i in range(1, 6):  # Keys 1 through 5
            key = system_globals.get(FIELD_MAPPING[f"globals_api_key_{i}"])
            if key and key.strip():
                api_keys.append(key)
        
        if not api_keys:
            raise ValueError("No OpenAI API keys found in SystemGlobals")
        
        print(f"  -> Found {len(api_keys)} OpenAI API keys")
        
        # Configure the global client with all available keys
        global_openai_client.set_api_keys(api_keys)
        return global_openai_client
        
    except Exception as e:
        print(f"  -> Error setting up OpenAI client: {e}")
        return None

def generate_caption(footage_data, thumb_path, token):
    """Generate caption using OpenAI and prompts.json."""
    try:
        # Set up OpenAI client with API keys from SystemGlobals
        client = setup_openai_client(token)
        if not client:
            return None
        
        # Get footage context for prompt
        info_ftg_id = footage_data.get(FIELD_MAPPING["footage_id"], "")
        info_metadata = footage_data.get(FIELD_MAPPING["footage_metadata"], "")
        info_source = footage_data.get(FIELD_MAPPING["footage_source"], "")
        info_filename = footage_data.get(FIELD_MAPPING["footage_filename"], "")
        
        print(f"  -> Using metadata: {len(info_metadata)} chars")
        print(f"  -> Metadata preview: {info_metadata[:100]}...")
        print(f"  -> Source: {info_source}")
        print(f"  -> Filename: {info_filename}")
        
        # Get AI_Prompt from footage data
        info_ai_prompt = footage_data.get(FIELD_MAPPING["footage_ai_prompt"], "")
        
        # Debug: Print AI_Prompt value
        print(f"  -> AI_Prompt from footage: '{info_ai_prompt}' (length: {len(info_ai_prompt)})")
        
        # Dynamic prompt selection based on FTG ID
        if info_ftg_id.startswith("AF"):
            prompt_template = PROMPTS["caption_AF"]
            prompt_text = prompt_template.format(
                AI_Prompt=info_ai_prompt,
                INFO_Metadata=info_metadata,
                INFO_Source=info_source,
                INFO_Filename=info_filename
            )
            print(f"  -> Using AF caption prompt template")
        elif info_ftg_id.startswith("LF"):
            prompt_template = PROMPTS["caption_LF"]
            prompt_text = prompt_template.format(
                AI_Prompt=info_ai_prompt,
                INFO_Metadata=info_metadata
            )
            print(f"  -> Using LF caption prompt template")
        else:
            print(f"  -> ⚠️ Unknown footage type: {info_ftg_id}")
            prompt_text = "Generate a descriptive caption for this video frame."
        
        print(f"  -> Final prompt length: {len(prompt_text)} chars")
        print(f"  -> ═══ FULL PROMPT BEING USED ═══")
        print(f"{prompt_text}")
        print(f"  -> ═══ END OF PROMPT ═══")
        
        # Log the prompt to parent footage record's AI_DevConsole (only once per footage)
        # This helps with prompt engineering visibility for frame caption generation
        try:
            footage_record_id = config.find_record_id(token, "FOOTAGE", {"INFO_FTG_ID": f"=={info_ftg_id}"})
            if footage_record_id:
                # Check if prompt has already been logged for this footage to avoid duplicates
                current_console = get_footage_dev_console(footage_record_id, token)
                if not current_console or "AI Prompt Engineering - Frame Caption Generation" not in current_console:
                    prompt_log_message = f"AI Prompt Engineering - Frame Caption Generation\n{prompt_text}"
                    write_to_footage_dev_console(footage_record_id, token, prompt_log_message)
                    print(f"  -> Logged prompt to footage console for engineering visibility")
                else:
                    print(f"  -> Prompt already logged to footage console, skipping duplicate")
        except Exception as e:
            print(f"  -> WARNING: Failed to log prompt to footage console: {e}")
        
        # Read and encode image
        with open(thumb_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")
        
        # Create messages for OpenAI
        messages = [
            {"role": "system", "content": prompt_text},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    }
                ]
            }
        ]
        
        # Call OpenAI API using global client
        response = client.chat_completions_create(
            model="gpt-4o",
            messages=messages,
            estimated_tokens=1000  # Conservative estimate for caption generation
        )
        
        caption = response.choices[0].message.content.strip()
        
        # Remove common markdown formatting
        caption_clean = caption.replace("*", "").replace("_", "").replace("-", "").strip()
        
        return caption_clean
        
    except Exception as e:
        print(f"  -> Error generating caption: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: frames_generate_captions.py <frame_id> <token>")
        sys.exit(1)
    
    frame_id = sys.argv[1]
    token = sys.argv[2]
    
    try:
        print(f"Generating caption for frame {frame_id}")
        
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
        
        # Get footage record for context
        footage_data, footage_record_id = get_footage_record(token, footage_id)
        if not footage_data:
            print(f"❌ Footage record not found: {footage_id}")
            sys.exit(1)
        
        file_path = footage_data.get(FIELD_MAPPING["footage_filepath"])
        if not file_path or not os.path.exists(file_path):
            print(f"❌ Video file not found: {file_path}")
            sys.exit(1)
        
        print(f"  -> Using metadata: {len(footage_data.get(FIELD_MAPPING['footage_metadata'], ''))} chars")
        print(f"  -> Footage type: {footage_data.get(FIELD_MAPPING['footage_id'], 'Unknown')}")
        
        # Generate thumbnail from video for captioning
        thumb_path = generate_thumbnail_from_timecode(file_path, timecode, frame_id)
        if not thumb_path:
            print(f"❌ Failed to generate thumbnail for captioning")
            sys.exit(1)
        
        # Generate caption using scraped metadata
        caption = generate_caption(footage_data, thumb_path, token)
        if not caption:
            print(f"❌ Failed to generate caption")
            # Clean up
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
            sys.exit(1)
        
        print(f"  -> Generated caption: {caption[:100]}...")
        
        # Update frame record
        update_data = {
            FIELD_MAPPING["frame_caption"]: caption,
            FIELD_MAPPING["frame_status"]: "3 - Caption Generated"
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
            print(f"✅ Caption generated and saved for frame {frame_id}")
        else:
            print(f"❌ Failed to update frame record")
            sys.exit(1)
        
        # Clean up temp file
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        
    except Exception as e:
        print(f"❌ Error processing frame {frame_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 