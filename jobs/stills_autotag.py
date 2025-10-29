#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import requests
import json
import base64
import os
import concurrent.futures

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.openai_client import global_openai_client

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "description": "INFO_Description",
    "server_path": "SPECS_Filepath_Server",
    "tags_list": "TAGS_List",
    "dev_console": "AI_DevConsole",
    "globals_api_key_1": "SystemGlobals_AutoLog_OpenAI_API_Key_1",
    "globals_api_key_2": "SystemGlobals_AutoLog_OpenAI_API_Key_2",
    "globals_api_key_3": "SystemGlobals_AutoLog_OpenAI_API_Key_3",
    "globals_api_key_4": "SystemGlobals_AutoLog_OpenAI_API_Key_4",
    "globals_api_key_5": "SystemGlobals_AutoLog_OpenAI_API_Key_5"
}

def load_tags():
    """Load the approved tags list from the tags file with descriptions."""
    tags_path = Path(__file__).resolve().parent.parent / "tags" / "stills-tags.tab"
    try:
        with open(tags_path, 'r') as f:
            # Read all lines and parse tab-separated format: tag_name\tdescription
            tags = []
            for line in f.readlines():
                line = line.strip()
                if line:
                    # Split by tab to get name and description
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        tag_name = parts[0].strip()
                        tag_description = parts[1].strip()
                        tags.append({'name': tag_name, 'description': tag_description})
                    elif len(parts) == 1:
                        # Tag without description
                        tag_name = parts[0].strip()
                        tags.append({'name': tag_name, 'description': ''})
        print(f"  -> Loaded {len(tags)} approved tags with descriptions")
        return tags
    except Exception as e:
        print(f"  -> WARNING: Failed to load tags file: {e}")
        return []

def encode_image_to_base64(image_path):
    """Encode image to base64 for OpenAI Vision API."""
    try:
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
            if not image_data:
                raise ValueError("Image file is empty.")
            
            base64_image = base64.b64encode(image_data).decode('utf-8')
            print(f"  -> Image encoded: {len(base64_image)} chars")
            return base64_image
            
    except Exception as e:
        print(f"❌ Error encoding image: {e}")
        return None

def analyze_with_openai(image_path, description, tags, client, stills_id):
    """Send image and description to OpenAI with tag list for analysis."""
    try:
        print(f"🤖 Analyzing image with OpenAI Vision API for {stills_id}...")
        
        # Encode image
        base64_image = encode_image_to_base64(image_path)
        if not base64_image:
            return None
        
        # Format tags for prompt
        tag_list = []
        for tag in tags:
            if tag['description']:
                tag_list.append(f"- {tag['name']}: {tag['description']}")
            else:
                tag_list.append(f"- {tag['name']}")
        
        tags_text = "\n".join(tag_list)
        
        # Create prompt
        system_prompt = """You are an expert at analyzing historical images and metadata to assign appropriate tags.
Your task is to analyze the provided image and its description, then select up to 4 most relevant tags from the provided list.

CRITICAL INSTRUCTIONS:
1. Do not invent new tags - it is critical to ONLY use tags from the provided list
2. Choose tags based on what you actually see in the image and read in the description
3. Select NO MORE than 4 tags that best match the image content and description
4. If fewer than 4 tags are appropriate, return fewer tags

Return your answer as a JSON object with exactly one field:
- `tags`: [Array of exact tag names from the approved list. Select up to 4 most relevant tags.]"""

        user_prompt = f"""Analyze this historical image and its description, then select up to 4 most relevant tags from the list below.

IMAGE DESCRIPTION:
{description if description else "No description provided"}

APPROVED TAGS LIST:
{tags_text}

Return ONLY a JSON object with a "tags" field containing an array of tag names."""

        # Build messages for OpenAI
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high"
                        }
                    }
                ]
            }
        ]
        
        # Call OpenAI API
        print(f"  -> Sending request to OpenAI...")
        
        response = client.chat_completions_create(
            model="gpt-4.1",
            messages=messages,
            response_format={"type": "json_object"},
            estimated_tokens=3000
        )
        
        # Extract response
        if not response.choices or not response.choices[0].message:
            print("❌ No response from OpenAI")
            return None
        
        content_raw = response.choices[0].message.content.strip()
        print(f"📝 Raw content from OpenAI: {content_raw}")
        
        # Parse JSON
        try:
            content = json.loads(content_raw)
            selected_tags = content.get('tags', [])
            
            if selected_tags:
                print(f"🏷️  Selected Tags: {', '.join(selected_tags)}")
                print(f"🏷️  Total Tag Count: {len(selected_tags)}")
            else:
                print(f"⚠️  No tags returned in response")
            
            return selected_tags
            
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON response: {e}")
            return None
        
    except Exception as e:
        print(f"❌ Error analyzing with OpenAI: {e}")
        import traceback
        traceback.print_exc()
        return None

def process_single_item(stills_id, token):
    """Process a single stills_id for auto-tagging."""
    try:
        print(f"\n{'='*60}")
        print(f"Processing: {stills_id}")
        print(f"{'='*60}")
        
        # Find record
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        
        description = record_data.get(FIELD_MAPPING["description"], '')
        server_path = record_data.get(FIELD_MAPPING["server_path"], '')
        
        print(f"✅ Found record")
        print(f"  -> Record ID: {record_id}")
        print(f"  -> Description: {description[:100]}..." if len(description) > 100 else f"  -> Description: {description}")
        print(f"  -> File path: {server_path}")
        
        # Check if file exists
        if not server_path or not os.path.exists(server_path):
            raise ValueError(f"Image file not found at: {server_path}")
        
        # Get system globals for OpenAI API keys
        system_globals = config.get_system_globals(token)
        
        api_keys = []
        for i in range(1, 6):
            key = system_globals.get(FIELD_MAPPING[f"globals_api_key_{i}"])
            if key and key.strip():
                api_keys.append(key)
        
        if not api_keys:
            raise ValueError("No OpenAI API keys found in SystemGlobals")
        
        print(f"🔑 Found {len(api_keys)} OpenAI API key(s)")
        
        # Configure OpenAI client
        global_openai_client.set_api_keys(api_keys)
        
        # Load tags
        tags = load_tags()
        if not tags:
            raise ValueError("Failed to load tags from stills-tags.tab")
        
        # Analyze with OpenAI
        selected_tags = analyze_with_openai(
            server_path,
            description,
            tags,
            global_openai_client,
            stills_id
        )
        
        if selected_tags:
            # Format tags for FileMaker (comma-separated)
            tags_for_fm = ", ".join(selected_tags)
            
            # Update FileMaker
            update_data = {
                FIELD_MAPPING["tags_list"]: tags_for_fm
            }
            
            config.update_record(token, "Stills", record_id, update_data)
            
            print(f"\n✅ SUCCESS: {stills_id}")
            print(f"   Tags written to FileMaker: {tags_for_fm}")
            return True
        else:
            print(f"\n❌ FAILED: {stills_id} - No tags returned")
            return False
        
    except Exception as e:
        print(f"\n❌ ERROR processing {stills_id}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stills_autotag.py <stills_id> [<stills_id2> ...]")
        sys.exit(1)
    
    input_string = sys.argv[1]
    
    # Get token
    token = config.get_token()
    
    # Parse input - support multiple formats
    try:
        # First try JSON parsing
        parsed_ids = json.loads(input_string)
        if isinstance(parsed_ids, list):
            stills_ids = [str(id).strip() for id in parsed_ids]
        else:
            stills_ids = [str(parsed_ids).strip()]
    except json.JSONDecodeError:
        # Try comma-separated values
        if ',' in input_string:
            stills_ids = [id.strip() for id in input_string.split(',') if id.strip()]
        # Try line-separated values (newlines or carriage returns)
        elif '\n' in input_string or '\r' in input_string:
            # Handle both \n and \r\n and \r
            cleaned_input = input_string.replace('\r\n', '\n').replace('\r', '\n')
            stills_ids = [id.strip() for id in cleaned_input.split('\n') if id.strip()]
        # Try space-separated values
        elif ' ' in input_string and not input_string.startswith('S') or len(input_string.split()) > 1:
            stills_ids = [id.strip() for id in input_string.split() if id.strip()]
        else:
            # Single ID as string
            stills_ids = [input_string.strip()]
    
    # Filter out empty strings
    stills_ids = [id for id in stills_ids if id]
    
    print(f"🚀 Starting auto-tagging for {len(stills_ids)} item(s)")
    if len(stills_ids) > 1:
        print(f"📋 Parsed IDs: {stills_ids[:5]}{'...' if len(stills_ids) > 5 else ''}")
    else:
        print(f"📋 Processing single ID: {stills_ids[0]}")
    
    # Process items
    if len(stills_ids) == 1:
        # Single item
        stills_id = stills_ids[0]
        success = process_single_item(stills_id, token)
        sys.exit(0 if success else 1)
    else:
        # Multiple items - process in parallel
        successful = 0
        failed = 0
        
        def process_item_wrapper(stills_id):
            try:
                return process_single_item(stills_id, token)
            except Exception as e:
                print(f"ERROR processing {stills_id}: {e}")
                return False
        
        # Use ThreadPoolExecutor for parallel processing
        max_workers = min(5, len(stills_ids))  # Limit concurrency for API calls
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_stills_id = {
                executor.submit(process_item_wrapper, stills_id): stills_id 
                for stills_id in stills_ids
            }
            
            for future in concurrent.futures.as_completed(future_to_stills_id):
                stills_id = future_to_stills_id[future]
                try:
                    success = future.result()
                    if success:
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    print(f"❌ Exception processing {stills_id}: {e}")
        
        # Print summary
        total = len(stills_ids)
        print(f"\n{'='*60}")
        print(f"Batch Auto-Tagging Complete")
        print(f"{'='*60}")
        print(f"Total: {total}, Successful: {successful}, Failed: {failed}")
        print(f"Success rate: {(successful / total * 100):.1f}%")
        
        # Exit with success if all items succeeded
        sys.exit(0 if failed == 0 else 1)

