#!/usr/bin/env python3
import sys, os, json
import warnings
from pathlib import Path
import requests
from datetime import datetime
# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.openai_client import global_openai_client

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "description": "INFO_Description",
    "date": "INFO_Date",
    "filename": "INFO_Filename",
    "metadata": "INFO_Metadata",
    "duration": "SPECS_File_Duration_Timecode",
    "ai_prompt": "AI_Prompt",
    "audio_type": "INFO_AudioType",
    "location": "INFO_Location",
    "frame_parent_id": "FRAMES_ParentID",
    "frame_status": "FRAMES_Status",
    "frame_id": "FRAMES_ID",
    "frame_caption": "FRAMES_Caption",
    "frame_transcript": "FRAMES_Transcript",
    "frame_timecode": "FRAMES_TC_IN",
    "frame_framerate": "FOOTAGE::SPECS_File_Framerate"
}

def load_prompts():
    """Load prompts from prompts.json file."""
    prompts_path = Path(__file__).resolve().parent.parent / "prompts" / "prompts.json"
    with open(prompts_path, 'r') as f:
        return json.load(f)

def setup_openai_client(token):
    """Set up global OpenAI client with API keys from system globals."""
    try:
        # Get system globals to retrieve API keys
        system_globals = config.get_system_globals(token)
        
        # Gather all available API keys
        api_keys = []
        for i in range(1, 6):  # Keys 1 through 5
            key = system_globals.get(f"SystemGlobals_AutoLog_OpenAI_API_Key_{i}")
            if key and key.strip():
                api_keys.append(key)
        
        if not api_keys:
            raise ValueError("No OpenAI API keys found in SystemGlobals")
        
        print(f"🔑 Found {len(api_keys)} OpenAI API keys")
        
        # Configure the global client with all available keys
        global_openai_client.set_api_keys(api_keys)
        return global_openai_client
        
    except Exception as e:
        print(f"  -> Error setting up OpenAI client: {e}")
        raise

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

def get_current_dev_console(record_id, token, layout):
    """Get the current AI_DevConsole content from a record."""
    try:
        response = requests.get(
            config.url(f"layouts/{layout}/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        response.raise_for_status()
        record_data = response.json()['response']['data'][0]['fieldData']
        return record_data.get("AI_DevConsole", "")
    except Exception as e:
        print(f"  -> WARNING: Failed to get AI_DevConsole: {e}")
        return ""

def write_to_dev_console(record_id, token, message):
    """Write a message to the AI_DevConsole field."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console_entry = f"[{timestamp}] {message}"
        
        # Get current console content to append rather than overwrite
        current_console = get_current_dev_console(record_id, token, "FOOTAGE")
        
        # Append new message
        if current_console:
            new_console = current_console + "\n\n" + console_entry
        else:
            new_console = console_entry
        
        # Update the AI_DevConsole field
        field_data = {"AI_DevConsole": new_console}
        config.update_record(token, "FOOTAGE", record_id, field_data)
        
    except Exception as e:
        print(f"  -> WARNING: Failed to write to AI_DevConsole: {e}")

def update_status(record_id, token, new_status, max_retries=3):
    """Update the AutoLog_Status field with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            payload = {"fieldData": {"AutoLog_Status": new_status}}
            response = requests.patch(
                config.url(f"layouts/FOOTAGE/records/{record_id}"), 
                headers=config.api_headers(current_token), 
                json=payload, 
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                print(f"  -> Token expired during status update, refreshing token (attempt {attempt + 1}/{max_retries})")
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return True
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout updating status (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error updating status (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except Exception as e:
            print(f"  -> Error updating status (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to update status to '{new_status}' after {max_retries} attempts")
    return False

def update_frame_statuses_for_footage(footage_id, token, new_status, max_retries=3):
    """Update status for all frame records belonging to a specific footage parent."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            print(f"  -> Updating frame statuses to '{new_status}' for footage {footage_id}")
            
            # Find all frame records for this footage
            query = {
                "query": [{FIELD_MAPPING["frame_parent_id"]: footage_id}],
                "limit": 1000
            }
            
            response = requests.post(
                config.url("layouts/FRAMES/_find"),
                headers=config.api_headers(current_token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 404:
                print(f"  -> No frame records found for footage {footage_id}")
                return True
            
            response.raise_for_status()
            records = response.json()['response']['data']
            
            if not records:
                print(f"  -> No frame records found for footage {footage_id}")
                return True
            
            print(f"  -> Found {len(records)} frame records to update")
            
            # Update each frame record
            updated_count = 0
            for record in records:
                frame_record_id = record['recordId']
                try:
                    payload = {"fieldData": {FIELD_MAPPING["frame_status"]: new_status}}
                    frame_response = requests.patch(
                        config.url(f"layouts/FRAMES/records/{frame_record_id}"),
                        headers=config.api_headers(current_token),
                        json=payload,
                        verify=False,
                        timeout=30
                    )
                    
                    if frame_response.status_code == 401:
                        current_token = config.get_token()
                        # Retry this frame
                        frame_response = requests.patch(
                            config.url(f"layouts/FRAMES/records/{frame_record_id}"),
                            headers=config.api_headers(current_token),
                            json=payload,
                            verify=False,
                            timeout=30
                        )
                    
                    frame_response.raise_for_status()
                    updated_count += 1
                    
                except Exception as e:
                    print(f"  -> Warning: Failed to update frame {frame_record_id}: {e}")
                    continue
            
            print(f"  -> Successfully updated {updated_count}/{len(records)} frame records")
            return True
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout updating frame statuses (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error updating frame statuses (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except Exception as e:
            print(f"  -> Error updating frame statuses (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to update frame statuses after {max_retries} attempts")
    return False

def generate_video_description(client, frames_data, footage_data, prompts):
    """Generate comprehensive video description from frames data."""
    try:
        footage_id = footage_data.get(FIELD_MAPPING["footage_id"], "")
        filename = footage_data.get(FIELD_MAPPING["filename"], "")
        metadata = footage_data.get(FIELD_MAPPING["metadata"], "")
        duration = footage_data.get(FIELD_MAPPING["duration"], "")
        
        print(f"  -> Generating description for {footage_id} ({len(frames_data)} frames)")
        
        # Sort frames by timecode (convert HH:MM:SS:FF to seconds for sorting)
        def timecode_to_seconds(tc_str, framerate=30.0):
            """Convert HH:MM:SS:FF timecode to seconds using actual framerate."""
            try:
                if not tc_str or tc_str == "0":
                    return 0
                parts = tc_str.split(':')
                if len(parts) == 4:  # HH:MM:SS:FF
                    hours, minutes, seconds, frames = map(int, parts)
                    return hours * 3600 + minutes * 60 + seconds + (frames / framerate)
                return 0
            except:
                return 0
        
        frames_sorted = sorted(frames_data, key=lambda x: timecode_to_seconds(
            x.get(FIELD_MAPPING["frame_timecode"], "0"), 
            float(x.get(FIELD_MAPPING["frame_framerate"], 30.0))
        ))
        
        # Count frames with content
        frames_with_audio = sum(1 for frame in frames_sorted if frame.get(FIELD_MAPPING["frame_transcript"], "").strip())
        frames_with_visuals = sum(1 for frame in frames_sorted if frame.get(FIELD_MAPPING["frame_caption"], "").strip())
        
        # Count frames with content
        frames_with_audio = sum(1 for frame in frames_sorted if frame.get(FIELD_MAPPING["frame_transcript"], "").strip())
        frames_with_visuals = sum(1 for frame in frames_sorted if frame.get(FIELD_MAPPING["frame_caption"], "").strip())
        
        if frames_with_visuals == 0:
            return "No Visual Content", "This video appears to lack visual content data.", "", "MOS", "", ""
        
        # Build CSV data for analysis
        csv_lines = ["Frame,Timecode,Visual Description,Audio Transcript"]
        for frame in frames_sorted:
            frame_id = frame.get(FIELD_MAPPING["frame_id"], "")
            timecode = frame.get(FIELD_MAPPING["frame_timecode"], "0")
            caption = frame.get(FIELD_MAPPING["frame_caption"], "").replace("\n", " ").strip()
            transcript = frame.get(FIELD_MAPPING["frame_transcript"], "").replace("\n", " ").strip()
            csv_lines.append(f"{frame_id},{timecode},{caption},{transcript}")
        
        csv_data = "\n".join(csv_lines)
        
        # Determine if video is silent
        is_silent = frames_with_audio == 0
        silent_note = "[SILENT VIDEO - NO AUDIO]" if is_silent else "[AUDIO PRESENT]"
        
        # Get AI_Prompt from footage data
        ai_prompt = footage_data.get(FIELD_MAPPING["ai_prompt"], "")
        
        # Select appropriate prompt based on footage type
        if footage_id.startswith("AF"):
            prompt_template = prompts.get("description_AF", "Generate a description for this historical footage.")
            prompt_text = prompt_template.format(
                AI_Prompt=ai_prompt,
                INFO_Metadata=metadata,
                INFO_Source=footage_data.get("INFO_Source", ""),
                INFO_Filename=filename,
                INFO_Duration=duration,
                AUDIO_STATUS=silent_note,
                FRAME_DATA=csv_data
            )
        elif footage_id.startswith("LF"):
            prompt_template = prompts.get("description_LF", "Generate a description for this live footage.")
            prompt_text = prompt_template.format(
                AI_Prompt=ai_prompt,
                INFO_Metadata=metadata,
                INFO_Duration=duration,
                AUDIO_STATUS=silent_note,
                FRAME_DATA=csv_data
            )
        else:
            prompt_text = f"Generate a concise, descriptive title and comprehensive description for this video footage based on the frame-by-frame analysis provided.\n\n{silent_note}\n\nFrame-level data:\n{csv_data}"
        
        # Log the prompt to AI_DevConsole for prompt engineering visibility
        footage_record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        if footage_record_id:
            prompt_log_message = f"AI Prompt Engineering - Video Description Generation\n{prompt_text}"
            write_to_dev_console(footage_record_id, token, prompt_log_message)

        # Make OpenAI API call
        print(f"  -> Calling OpenAI API for description generation...")
        response = client.chat_completions_create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": prompt_text}
            ]
        )
        
        final_response = response.choices[0].message.content.strip()
        
        # Parse title, description, date, audio_type, and location from JSON response
        title, description, date, audio_type, location = parse_json_response(final_response)
        
        print(f"  -> Generated title: {title}")
        print(f"  -> Generated description: {len(description)} characters")
        print(f"  -> Generated date: {date}")
        print(f"  -> Generated audio_type: {audio_type}")
        print(f"  -> Generated location: {location}")
        
        return title, description, date, audio_type, location, csv_data
        
    except Exception as e:
        print(f"❌ Error generating video description: {e}")
        return "", "", "", "MOS", "", ""

def parse_json_response(response_text):
    """Parse title, description, date, audio_type, and location from JSON API response."""
    title = ""
    description = ""
    date = ""
    audio_type = "MOS"  # Default to MOS
    location = ""  # Default to empty
    
    try:
        print(f"  -> Raw API response: {response_text[:200]}...")  # Debug output
        
        # First, try to extract JSON from markdown code blocks
        json_text = response_text.strip()
        
        # Remove markdown code block formatting if present
        if '```json' in json_text:
            # Extract content between ```json and ```
            start_marker = '```json'
            end_marker = '```'
            start_idx = json_text.find(start_marker)
            if start_idx != -1:
                start_idx += len(start_marker)
                end_idx = json_text.find(end_marker, start_idx)
                if end_idx != -1:
                    json_text = json_text[start_idx:end_idx].strip()
        elif '```' in json_text:
            # Handle generic code blocks
            parts = json_text.split('```')
            if len(parts) >= 3:
                json_text = parts[1].strip()
        
        # Try to find JSON object in the text
        if not json_text.startswith('{'):
            # Look for JSON object within the text
            start_idx = json_text.find('{')
            end_idx = json_text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_text = json_text[start_idx:end_idx+1]
        
        print(f"  -> Extracted JSON text: {json_text[:200]}...")  # Debug output
        
        # Try to parse as JSON
        try:
            data = json.loads(json_text)
            title = data.get('title', '').strip()
            description = data.get('description', '').strip()
            date = data.get('date', '').strip()
            audio_type = data.get('audio_type', 'MOS').strip()
            location = data.get('location', '').strip()
            
            print(f"  -> JSON parsing successful: title='{title[:50]}...', description='{description[:50]}...', date='{date}', audio_type='{audio_type}', location='{location}'")
            
        except json.JSONDecodeError as e:
            print(f"  -> JSON decode failed: {e}")
            print(f"  -> Falling back to text parsing...")
            
            # Fallback to text parsing
            lines = response_text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if line.lower().startswith('title:'):
                    title = line[6:].strip()
                elif line.lower().startswith('description:'):
                    description = line[12:].strip()
                elif line.lower().startswith('date:'):
                    date = line[5:].strip()
                elif line.lower().startswith('audio_type:'):
                    audio_type = line[11:].strip()
                elif line.lower().startswith('location:'):
                    location = line[9:].strip()
                elif not title and not line.lower().startswith(('description:', 'date:', 'audio_type:', 'location:')):
                    title = line
                elif title and not description and not line.lower().startswith(('date:', 'audio_type:', 'location:')):
                    description = line
        
        # Clean up prefixes and quotes
        title = title.replace('Title:', '').replace('title:', '').strip().strip('"\'')
        description = description.replace('Description:', '').replace('description:', '').strip().strip('"\'')
        date = date.replace('Date:', '').replace('date:', '').strip().strip('"\'')
        audio_type = audio_type.replace('Audio_type:', '').replace('audio_type:', '').strip().strip('"\'')
        location = location.replace('Location:', '').replace('location:', '').strip().strip('"\'')
        
        # Ensure we have something
        if not title:
            title = "Untitled Video"
        if not description:
            description = "No description available"
        if not audio_type or audio_type.lower() not in ['mos', 'sound']:
            audio_type = "MOS"  # Default fallback
        # Location can remain empty if not provided
            
        print(f"  -> Final parsed values: title='{title}', description='{description[:50]}...', date='{date}', audio_type='{audio_type}', location='{location}'")
            
    except Exception as e:
        print(f"  -> Error parsing response: {e}")
        print(f"  -> Using fallback values")
        title = "Untitled Video"
        description = response_text.strip() if response_text.strip() else "No description available"
        date = ""
        audio_type = "MOS"
        location = ""
    
    return title, description, date, audio_type, location

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    footage_id = sys.argv[1]
    
    # Support both old (2 args) and new (3 args) calling patterns
    if len(sys.argv) == 2:
        # Direct API call mode - create own token/session and set final status
        token = config.get_token()
        continue_workflow = True  # When called as individual endpoint, set status to "7 - Generating Embeddings"
        print(f"🔄 Individual endpoint mode - will set final status to '7 - Generating Embeddings'")
    elif len(sys.argv) == 3:
        # Subprocess mode - use provided token from parent process, don't set final status
        token = sys.argv[2]
        continue_workflow = False  # When called as part of main workflow, don't set final status
        print(f"📋 Subprocess mode - step 06 only")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py footage_id [token]\n")
        sys.exit(1)
    
    try:
        print(f"Starting description generation for footage {footage_id}")
        
        # Get the current footage record
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        footage_data = config.get_record(token, "FOOTAGE", record_id)
        
        # Get all frame records for this footage
        frame_records = find_frames_for_footage(token, footage_id)
        
        if not frame_records:
            print(f"⚠️ No frame records found for footage {footage_id}")
            # Set a basic description
            field_data = {
                FIELD_MAPPING["description"]: "Video footage with no frame data available for analysis.",
                FIELD_MAPPING["date"]: "",
                FIELD_MAPPING["audio_type"]: "MOS"  # Default to MOS when no frame data
            }
            config.update_record(token, "FOOTAGE", record_id, field_data)
            print(f"✅ Set basic description for footage {footage_id}")
            sys.exit(0)
        
        # Extract frame data
        frames_data = [record['fieldData'] for record in frame_records]
        
        # Load prompts
        prompts = load_prompts()
        
        # Set up OpenAI client
        client = setup_openai_client(token)
        
        # Generate description
        title, description, date, audio_type, location, csv_data = generate_video_description(client, frames_data, footage_data, prompts)
        
        if not description:
            print(f"❌ Failed to generate description")
            sys.exit(1)
        
        # Update the footage record with title, description, date, audio_type, location, and video events
        field_data = {
            FIELD_MAPPING["description"]: description,
            FIELD_MAPPING["date"]: date,
            FIELD_MAPPING["audio_type"]: audio_type,
            "INFO_Video_Events": csv_data  # Store the frame-by-frame analysis
        }
        
        # Add location if provided
        if location:
            field_data[FIELD_MAPPING["location"]] = location
        
        # Add title if we have a title field (check if it exists)
        if "INFO_Title" in footage_data:
            field_data["INFO_Title"] = title
        
        update_response = config.update_record(token, "FOOTAGE", record_id, field_data)
        
        if update_response.status_code == 200:
            print(f"✅ Successfully updated footage {footage_id} with generated description")
            print(f"  -> Title: {title}")
            print(f"  -> Description: {len(description)} characters")
            print(f"  -> Date: {date}")
            print(f"  -> Audio Type: {audio_type}")
            print(f"  -> Location: {location if location else 'Not specified'}")
            print(f"  -> Video Events: {len(csv_data)} characters (frame-by-frame CSV data)")
            
            # Set final status when called as individual endpoint
            if continue_workflow:
                print(f"=== Setting final status for {footage_id} ===")
                
                # Update footage status to "7 - Generating Embeddings"
                if update_status(record_id, token, "7 - Generating Embeddings"):
                    print(f"✅ Footage status updated to '7 - Generating Embeddings'")
                    print(f"SUCCESS [generate_description + final status]: {footage_id}")
                else:
                    print(f"⚠️ Failed to update footage status, but description generation succeeded")
                    print(f"SUCCESS [generate_description]: {footage_id}")
            else:
                print(f"SUCCESS [generate_description]: {footage_id}")
        else:
            print(f"❌ Failed to update footage record: {update_response.status_code}")
            print(f"Response: {update_response.text}")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error generating description for footage {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 