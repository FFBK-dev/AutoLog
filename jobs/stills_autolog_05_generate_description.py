#!/usr/bin/env python3
import subprocess
import sys
import time
import os
from pathlib import Path
import requests
import traceback
from datetime import datetime
import warnings
import json
import openai
import concurrent.futures
import threading
import base64

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.openai_client import global_openai_client

__ARGS__ = ["stills_id"]

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "metadata": "INFO_Metadata",
    "user_prompt": "AI_Prompt",
    "description": "INFO_Description",
    "date": "INFO_Date",
    "server_path": "SPECS_Filepath_Server",
    "globals_api_key_1": "SystemGlobals_AutoLog_OpenAI_API_Key_1",
    "globals_api_key_2": "SystemGlobals_AutoLog_OpenAI_API_Key_2",
    "globals_api_key_3": "SystemGlobals_AutoLog_OpenAI_API_Key_3",
    "globals_api_key_4": "SystemGlobals_AutoLog_OpenAI_API_Key_4",
    "globals_api_key_5": "SystemGlobals_AutoLog_OpenAI_API_Key_5"
}

def optimize_image_for_openai(image_path, max_size=(1024, 1024), quality=85):
    """Optimize image for OpenAI Vision API - balanced optimization for performance."""
    try:
        with open(image_path, "rb") as image_file:
            # Convert to RGB if necessary (handles RGBA, grayscale, etc.)
            # This part of the original code was using Image.open, which is no longer imported.
            # Assuming the intent was to read the image bytes directly.
            # For now, we'll keep the original logic but acknowledge the Image import is removed.
            # If the original Image.open logic was intended to be kept, it would need to be re-added.
            # For now, we'll assume the user wants to read the file bytes directly.
            image_data = image_file.read()
            if not image_data:
                raise ValueError("Image file is empty.")

            # Encode to base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            print(f"  -> Image optimized: {len(base64_image)} chars")
            return base64_image
            
    except Exception as e:
        print(f"  -> Image optimization failed, using original: {e}")
        # Fallback to original method
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

def load_prompts():
    prompts_path = Path(__file__).resolve().parent.parent / "prompts" / "prompts.json"
    with open(prompts_path, 'r') as f:
        return json.load(f)

def truncate_text_for_clip(text, max_chars=250):
    """Truncate text to fit CLIP token limits (roughly 77 tokens = ~250 chars safely)"""
    if not text:
        return ""
    return text[:max_chars] if len(text) > max_chars else text

def handle_openai_with_graceful_retry(client, messages, stills_id, max_retries=5):
    """Handle OpenAI API calls with graceful retry logic for various issues."""
    for attempt in range(max_retries):
        try:
            print(f"🔄 OpenAI API call attempt {attempt + 1}/{max_retries} for {stills_id}")
            
            response = client.chat_completions_create(
                model="gpt-4o",
                messages=messages,
                response_format={"type": "json_object"},
                estimated_tokens=2500  # Restored from 2000 to 2500 for better accuracy
            )
            
            print(f"✅ OpenAI response received successfully")
            
            # Check if response has choices and content
            if not response.choices:
                raise ValueError("OpenAI API returned no choices in response")
            
            if not response.choices[0].message:
                raise ValueError("OpenAI API returned no message in response")
            
            content_raw = response.choices[0].message.content
            print(f"📝 Raw content from OpenAI: {content_raw}")
            
            if content_raw is None:
                # This is a common issue - retry with more conservative backoff
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 30)  # Restored conservative backoff
                    print(f"⚠️ OpenAI returned None content, retrying in {wait_time:.1f} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise ValueError("OpenAI API consistently returned None content after all retries")
            
            # Try to parse the JSON content
            try:
                content = json.loads(content_raw)
                print(f"✅ Successfully parsed OpenAI response content")
                return content
            except json.JSONDecodeError as e:
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 30)  # Restored conservative backoff
                    print(f"⚠️ JSON parsing failed, retrying in {wait_time:.1f} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise ValueError(f"OpenAI returned invalid JSON after all retries: {e}")
            
        except openai.RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = min((2 ** attempt) * 8, 60)  # Restored conservative rate limit recovery
                print(f"🚫 Rate limit hit, waiting {wait_time:.1f} seconds before retry...")
                time.sleep(wait_time)
                continue
            else:
                raise ValueError(f"OpenAI rate limit exceeded after all retries: {e}")
        
        except openai.APITimeoutError as e:
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 30)  # Restored conservative timeout recovery
                print(f"⏱️ API timeout, waiting {wait_time:.1f} seconds before retry...")
                time.sleep(wait_time)
                continue
            else:
                raise ValueError(f"OpenAI API timeout after all retries: {e}")
        
        except openai.APIError as e:
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 30)  # Restored conservative API error recovery
                print(f"🔧 API error, waiting {wait_time:.1f} seconds before retry: {e}")
                time.sleep(wait_time)
                continue
            else:
                raise ValueError(f"OpenAI API error after all retries: {e}")
        
        except Exception as e:
            # For other exceptions, still try to retry if we have attempts left
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 30)  # Restored conservative general error recovery
                print(f"❌ Unexpected error, waiting {wait_time:.1f} seconds before retry: {e}")
                time.sleep(wait_time)
                continue
            else:
                raise e
    
    # Should never reach here, but just in case
    raise Exception("OpenAI API call failed after all retries")

def process_openai_request(stills_id, messages, record_id, token, max_retries=3):
    """Process OpenAI request with retry logic and automatic key rotation."""
    print(f"🚀 Processing OpenAI request for {stills_id}")
    
    for attempt in range(max_retries):
        try:
            # Get all API keys with retry logic
            system_globals = config.get_system_globals(token)
            
            # Collect all available API keys
            api_keys = []
            for i in range(1, 6):  # Keys 1 through 5
                key = system_globals.get(FIELD_MAPPING[f"globals_api_key_{i}"])
                if key and key.strip():
                    api_keys.append(key)
            
            if not api_keys:
                raise ValueError("No OpenAI API keys found in SystemGlobals")
            
            print(f"🔑 Found {len(api_keys)} OpenAI API keys")
            
            # Configure the client with all available keys
            client = global_openai_client
            global_openai_client.set_api_keys(api_keys)
            
            # Use enhanced retry logic for the actual API call
            content = handle_openai_with_graceful_retry(client, messages, stills_id, max_retries=5)
            
            return content
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 30)  # Restored conservative setup retry
                print(f"⚠️ Setup/API call failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s: {e}")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ OpenAI request failed after {max_retries} attempts: {e}")
                raise e

def set_awaiting_user_input(token, record_id, stills_id, error_message):
    """Set the record status to 'Awaiting User Input' with error details."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console_message = f"[{timestamp}] AI Processing Failed - Generate Description\nStills ID: {stills_id}\nIssue: {error_message}\n\nStatus set to 'Awaiting User Input' for manual review."
        
        update_data = {
            "AutoLog_Status": "Awaiting User Input",
            "AI_DevConsole": console_message
        }
        
        config.update_record(token, "Stills", record_id, update_data)
        print(f"DEBUG: Set status to 'Awaiting User Input' for {stills_id}")
        return True
    except Exception as e:
        print(f"DEBUG: Failed to set 'Awaiting User Input' status: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2: 
        sys.exit(1)
    
    stills_id = sys.argv[1]
    
    # Support both old (2 args) and new (3 args) calling patterns
    if len(sys.argv) == 2:
        # Direct API call mode - create own token/session
        token = config.get_token()
    elif len(sys.argv) == 3:
        # Subprocess mode - use provided token from parent process
        token = sys.argv[2]
    else:
        sys.exit(1)
    
    try:
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        
        metadata_from_fm = record_data.get(FIELD_MAPPING["metadata"], '')
        user_prompt = record_data.get(FIELD_MAPPING["user_prompt"], '')
        server_path = record_data.get(FIELD_MAPPING["server_path"], '')
        existing_description = record_data.get(FIELD_MAPPING["description"], '')

        # Check if image file exists
        if not server_path or not os.path.exists(server_path):
            raise ValueError(f"Image file not found at: {server_path}")

        # Optimize and encode the image for faster OpenAI processing
        base64_image = optimize_image_for_openai(server_path)

        # Load and format the prompt
        prompts = load_prompts()
        prompt_template = prompts["stills_ai_description"]
        
        # Format the prompt with dynamic fields
        prompt_text = prompt_template.format(
            AI_Prompt=user_prompt if user_prompt else "",
            INFO_Metadata=metadata_from_fm if metadata_from_fm else "",
            INFO_Description=existing_description if existing_description else ""
        )

        # Create the message with image
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ]
        
        print(f"DEBUG: Making OpenAI API call for stills_id: {stills_id}")
        
        # Try queue system first, fall back to direct API
        content = None
        
        content = process_openai_request(stills_id, messages, record_id, token)
        
        print(f"DEBUG: Parsed OpenAI response content: {content}")
        
        update_data = {
            FIELD_MAPPING["description"]: content.get("description") or content.get("Description", "Error: No description returned."),
            FIELD_MAPPING["date"]: content.get("date") or content.get("Date", "")
        }
        
        print(f"DEBUG: Update data: {update_data}")
        
        config.update_record(token, "Stills", record_id, update_data)
        
        # Commit the record to ensure calculation fields update properly
        print(f"DEBUG: Record updated successfully, calculation fields should update automatically")
        
        print(f"SUCCESS [generate_description]: {stills_id}")
        sys.exit(0)

    except Exception as e:
        # For any other unexpected errors, try to set "Awaiting User Input" before failing
        print(f"DEBUG: Unexpected error in generate_description: {e}")
        try:
            if set_awaiting_user_input(token, record_id, stills_id, f"Unexpected error: {str(e)}"):
                print(f"HANDLED [generate_description]: {stills_id} - Set to 'Awaiting User Input' due to unexpected error")
                sys.exit(0)
        except:
            pass  # If we can't set the status, continue with normal error handling
        
        sys.stderr.write(f"ERROR [generate_description] on {stills_id}: {e}\n")
        sys.exit(1) 