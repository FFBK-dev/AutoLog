#!/usr/bin/env python3
"""
Footage Auto-Tagger (Simple)
Tags footage based on existing frame captions and transcripts.
Does NOT generate descriptions - only assigns tags.
"""
import sys, os, json
import warnings
from pathlib import Path
import requests
# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.openai_client import global_openai_client

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "tags_list": "TAGS_List",
    "frame_parent_id": "FRAMES_ParentID",
    "frame_caption": "FRAMES_Caption",
    "frame_transcript": "FRAMES_Transcript",
    "frame_timecode": "FRAMES_TC_IN"
}

def load_tags():
    """Load the approved tags list from the tags file with descriptions."""
    tags_path = Path(__file__).resolve().parent.parent / "tags" / "footage-tags.tab"
    try:
        with open(tags_path, 'r') as f:
            tags = []
            for line in f.readlines():
                line = line.strip()
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        tag_name = parts[0].strip()
                        tag_description = parts[1].strip()
                        tags.append({'name': tag_name, 'description': tag_description})
                    elif len(parts) == 1:
                        tag_name = parts[0].strip()
                        tags.append({'name': tag_name, 'description': ''})
        print(f"  -> Loaded {len(tags)} approved footage tags")
        return tags
    except Exception as e:
        print(f"  -> ERROR: Failed to load footage tags file: {e}")
        return []

def setup_openai_client(token):
    """Set up global OpenAI client with API keys from system globals."""
    try:
        system_globals = config.get_system_globals(token)
        
        api_keys = []
        for i in range(1, 6):
            key = system_globals.get(f"SystemGlobals_AutoLog_OpenAI_API_Key_{i}")
            if key and key.strip():
                api_keys.append(key)
        
        if not api_keys:
            raise ValueError("No OpenAI API keys found in SystemGlobals")
        
        print(f"🔑 Found {len(api_keys)} OpenAI API keys")
        
        global_openai_client.set_api_keys(api_keys)
        return global_openai_client
        
    except Exception as e:
        print(f"  -> ERROR: Failed to setup OpenAI client: {e}")
        raise

def find_frames_for_footage(token, footage_id):
    """Find all frame records for a given footage ID."""
    print(f"  -> Finding frame records for footage: {footage_id}")
    
    try:
        query = {
            "query": [{FIELD_MAPPING["frame_parent_id"]: footage_id}],
            "limit": 1000
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
        print(f"  -> ERROR: Failed to find frame records: {e}")
        return []

def generate_tags_from_frames(client, frames_data, tags):
    """Generate tags based on frame captions and transcripts."""
    try:
        print(f"  -> Analyzing {len(frames_data)} frames for tagging...")
        
        # Build summary of frame content
        frame_summaries = []
        for frame in frames_data[:20]:  # Limit to first 20 frames for prompt efficiency
            caption = frame.get(FIELD_MAPPING["frame_caption"], "").strip()
            transcript = frame.get(FIELD_MAPPING["frame_transcript"], "").strip()
            timecode = frame.get(FIELD_MAPPING["frame_timecode"], "")
            
            summary_parts = []
            if caption:
                summary_parts.append(f"Visual: {caption}")
            if transcript:
                summary_parts.append(f"Audio: {transcript}")
            
            if summary_parts:
                frame_summaries.append(f"[{timecode}] {' | '.join(summary_parts)}")
        
        if not frame_summaries:
            print(f"  -> No frame content available for tagging")
            return []
        
        frame_content = "\n".join(frame_summaries)
        
        # Format tags for prompt
        tags_list_items = []
        for tag in tags:
            if tag['description']:
                tags_list_items.append(f"- {tag['name']}: {tag['description']}")
            else:
                tags_list_items.append(f"- {tag['name']}")
        tags_list_text = "\n".join(tags_list_items)
        
        # Create prompt for tagging
        prompt_text = f"""You are an expert at analyzing video footage and assigning appropriate tags.

Your task is to analyze the frame-by-frame content provided and select up to 4 most relevant tags from the approved list.

CRITICAL INSTRUCTIONS:
1. Do not invent new tags - ONLY use tags from the provided list
2. Choose tags based on what you observe in the frame content (visual descriptions and audio transcripts)
3. Select NO MORE than 4 tags that best match the footage content
4. If fewer than 4 tags are appropriate, return fewer tags
5. Focus on the most prominent and consistent elements across the frames

FRAME-BY-FRAME CONTENT:
{frame_content}

APPROVED TAGS LIST:
{tags_list_text}

Return your answer as a JSON object with exactly one field:
- `tags`: [Array of exact tag names from the approved list. Select up to 4 most relevant tags. Format as: ["tag1", "tag2", "tag3", "tag4"] or fewer if appropriate.]"""

        # Make OpenAI API call
        print(f"  -> Calling OpenAI API for tag generation...")
        response = client.chat_completions_create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt_text}
            ],
            response_format={"type": "json_object"}
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        try:
            data = json.loads(response_text)
            returned_tags = data.get('tags', [])
            
            # Ensure tags is a list
            if isinstance(returned_tags, str):
                returned_tags = [tag.strip() for tag in returned_tags.split(',') if tag.strip()]
            elif not isinstance(returned_tags, list):
                returned_tags = []
            
            print(f"🏷️  TAGS RETURNED: {', '.join(returned_tags) if returned_tags else 'None'}")
            print(f"🏷️  TOTAL TAG COUNT: {len(returned_tags)}")
            
            return returned_tags
            
        except json.JSONDecodeError as e:
            print(f"  -> ERROR: Failed to parse JSON response: {e}")
            return []
        
    except Exception as e:
        print(f"❌ Error generating tags: {e}")
        return []

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <footage_id>")
        sys.exit(1)
    
    footage_id = sys.argv[1]
    
    try:
        print(f"🚀 Starting tagging for footage {footage_id}")
        
        # Get token
        token = config.get_token()
        
        # Get the current footage record
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        
        # Get all frame records for this footage
        frame_records = find_frames_for_footage(token, footage_id)
        
        if not frame_records:
            print(f"⚠️ No frame records found for footage {footage_id}")
            print(f"Cannot tag without frame data")
            sys.exit(1)
        
        # Extract frame data
        frames_data = [record['fieldData'] for record in frame_records]
        
        # Load approved tags
        tags = load_tags()
        
        if not tags:
            print(f"❌ No tags loaded - cannot proceed")
            sys.exit(1)
        
        # Set up OpenAI client
        client = setup_openai_client(token)
        
        # Generate tags
        returned_tags = generate_tags_from_frames(client, frames_data, tags)
        
        if not returned_tags:
            print(f"⚠️ No tags were generated")
            # Still update with empty string to clear any existing tags
            tags_for_fm = ""
        else:
            # Format tags for FileMaker (comma-separated)
            tags_for_fm = ", ".join(returned_tags)
        
        # Update only the TAGS_List field
        field_data = {
            FIELD_MAPPING["tags_list"]: tags_for_fm
        }
        
        update_response = config.update_record(token, "FOOTAGE", record_id, field_data)
        
        if update_response.status_code == 200:
            print(f"✅ Successfully updated tags for footage {footage_id}")
            print(f"  -> Tags: {tags_for_fm if tags_for_fm else 'None'}")
            sys.exit(0)
        else:
            print(f"❌ Failed to update footage record: {update_response.status_code}")
            print(f"Response: {update_response.text}")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error tagging footage {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

