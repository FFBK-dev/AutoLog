#!/usr/bin/env python3
import subprocess
import sys
import time
from pathlib import Path
import requests
import traceback
from datetime import datetime
import warnings
import json
import openai
import concurrent.futures
import threading
import os # Added for debug mode

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.local_metadata_evaluator import evaluate_metadata_local

# No longer takes arguments - will automatically find pending items
__ARGS__ = []

JOBS_DIR = Path(__file__).resolve().parent  # Same directory as this script

# Add a debug flag at the top
DEBUG_MODE = os.getenv('AUTOLOG_DEBUG', 'false').lower() == 'true'

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "status": "AutoLog_Status",
    "metadata": "INFO_Metadata",
    "url": "SPECS_URL",
    "dev_console": "AI_DevConsole",
    "description_orig": "INFO_Description_Original",
    "copyright": "INFO_Copyright",
    "source": "INFO_Source",
    "archival_id": "INFO_Archival_ID",
    "globals_api_key_1": "SystemGlobals_AutoLog_OpenAI_API_Key_1",
    "globals_api_key_2": "SystemGlobals_AutoLog_OpenAI_API_Key_2",
    "globals_api_key_3": "SystemGlobals_AutoLog_OpenAI_API_Key_3",
    "globals_api_key_4": "SystemGlobals_AutoLog_OpenAI_API_Key_4",
    "globals_api_key_5": "SystemGlobals_AutoLog_OpenAI_API_Key_5"
}

# Define the complete workflow with status updates
WORKFLOW_STEPS = [
    {
        "step_num": 1,
        "status_before": "0 - Pending File Info",
        "status_after": "1 - File Info Complete",
        "script": "stills_autolog_01_get_file_info.py",
        "description": "Get File Info"
    },
    {
        "step_num": 2,
        "status_before": "1 - File Info Complete",
        "status_after": "2 - Server Copy Complete",
        "script": "stills_autolog_02_copy_to_server.py",
        "description": "Copy to Server"
    },
    {
        "step_num": 3,
        "status_before": "2 - Server Copy Complete",
        "status_after": "3 - Metadata Parsed",
        "script": "stills_autolog_03_parse_metadata.py",
        "description": "Parse Metadata"
    },
    {
        "step_num": 4,
        "status_before": "3 - Metadata Parsed",
        "status_after": "4 - Scraping URL",
        "script": "stills_autolog_04_scrape_url.py",
        "description": "Scrape URL",
        "conditional": True,  # Only run if metadata is insufficient
        "evaluate_metadata_first": True  # New flag to check metadata quality first
    },
    {
        "step_num": 5,
        "status_before": None,  # Variable - could be step 3 or 4 status
        "status_after": "5 - Generating Description",
        "script": "stills_autolog_05_generate_description.py",
        "description": "Generate Description"
    },
    {
        "step_num": 6,
        "status_before": "5 - Generating Description",
        "status_after": "6 - Generating Embeddings",
        "script": "stills_autolog_06_generate_embeddings.py",
        "description": "Generate Embeddings"
    },
    {
        "step_num": 7,
        "status_before": "6 - Generating Embeddings",
        "status_after": "7 - Applying Tags",
        "script": "stills_autolog_07_apply_tags.py",
        "description": "Apply Tags"
    },
    {
        "step_num": 8,
        "status_before": "7 - Applying Tags",
        "status_after": "9 - Complete",
        "script": "stills_autolog_08_fuse_embeddings.py",
        "description": "Fuse Embeddings"
    }
]

def load_prompts():
    """Load prompts from prompts.json file."""
    prompts_path = Path(__file__).resolve().parent.parent / "prompts" / "prompts.json"
    with open(prompts_path, 'r') as f:
        return json.load(f)

def combine_metadata(record_data):
    """Combine all available metadata into a single text for evaluation."""
    metadata_parts = []
    
    # Add EXIF metadata
    raw_metadata = record_data.get(FIELD_MAPPING["metadata"], '')
    if raw_metadata:
        metadata_parts.append(f"EXIF/Technical Metadata:\n{raw_metadata}")
    
    # Add original description
    description = record_data.get(FIELD_MAPPING["description_orig"], '')
    if description:
        metadata_parts.append(f"Original Description:\n{description}")
    
    # Add copyright/attribution
    copyright = record_data.get(FIELD_MAPPING["copyright"], '')
    if copyright:
        metadata_parts.append(f"Copyright/Attribution:\n{copyright}")
    
    # Add source information
    source = record_data.get(FIELD_MAPPING["source"], '')
    if source:
        metadata_parts.append(f"Source Archive:\n{source}")
    
    # Add archival ID
    archival_id = record_data.get(FIELD_MAPPING["archival_id"], '')
    if archival_id:
        metadata_parts.append(f"Archival ID:\n{archival_id}")
    
    # Add URL (for reference)
    url = record_data.get(FIELD_MAPPING["url"], '')
    if url:
        metadata_parts.append(f"Source URL:\n{url}")
    
    return "\n\n".join(metadata_parts)

def evaluate_metadata_quality(record_data, token):
    """Evaluate metadata quality using local analysis."""
    try:
        # Combine all metadata
        combined_metadata = combine_metadata(record_data)
        
        if not combined_metadata.strip():
            print(f"  -> No metadata available for evaluation")
            return False
        
        print(f"  -> Evaluating combined metadata ({len(combined_metadata)} chars)")
        
        # Use local evaluator instead of OpenAI
        evaluation = evaluate_metadata_local(combined_metadata)
        
        is_sufficient = evaluation.get("sufficient", False)
        reason = evaluation.get("reason", "No reason provided")
        confidence = evaluation.get("confidence", "medium")
        score = evaluation.get("score", 0.0)
        
        print(f"  -> Local AI Evaluation: {'GOOD' if is_sufficient else 'BAD'}")
        print(f"     Score: {score:.2f}")
        print(f"     Reason: {reason}")
        print(f"     Confidence: {confidence}")
        
        return is_sufficient
        
    except Exception as e:
        print(f"  -> ERROR in local metadata evaluation: {e}")
        # Fall back to basic heuristics if local evaluation fails
        combined_metadata = combine_metadata(record_data)
        
        # More lenient fallback: check for minimum length and any basic content
        # Historical photos often have minimal metadata, so be more forgiving
        if len(combined_metadata) > 50:  # Lowered from 100 to 50
            print(f"  -> Fallback: Using basic length check - GOOD (historical photos often have minimal metadata)")
            return True
        else:
            print(f"  -> Fallback: Using basic length check - BAD (truly insufficient metadata)")
            return False

def format_error_message(stills_id, step_name, error_details, error_type="Processing Error"):
    """Format error messages for the AI_DevConsole field in a user-friendly way."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Clean up error details but don't truncate aggressively
    clean_error = error_details.strip()
    if clean_error.startswith("Error:"):
        clean_error = clean_error[6:].strip()
    if clean_error.startswith("FATAL ERROR:"):
        clean_error = clean_error[12:].strip()
    
    # Increase truncation limit and be more generous with error details
    # FileMaker can handle much more than 200 characters
    if len(clean_error) > 1000:
        clean_error = clean_error[:997] + "..."
    
    return f"[{timestamp}] {error_type} - {step_name}\nStills ID: {stills_id}\nIssue: {clean_error}"

def write_error_to_console(record_id, token, error_message, max_retries=3):
    """Safely write error message to the AI_DevConsole field with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            payload = {"fieldData": {FIELD_MAPPING["dev_console"]: error_message}}
            response = requests.patch(
                config.url(f"layouts/Stills/records/{record_id}"), 
                headers=config.api_headers(current_token), 
                json=payload, 
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                print(f"  -> Token expired during error console write, refreshing token (attempt {attempt + 1}/{max_retries})")
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return True
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout writing to error console (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error writing to error console (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except Exception as e:
            print(f"  -> Error writing to error console (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to write error to console after {max_retries} attempts")
    return False

def update_status(record_id, token, new_status, max_retries=3):
    """Update the AutoLog_Status field with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            payload = {"fieldData": {FIELD_MAPPING["status"]: new_status}}
            response = requests.patch(
                config.url(f"layouts/Stills/records/{record_id}"), 
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

def get_current_record_data(record_id, token, max_retries=3):
    """Get current record data from FileMaker with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                config.url(f"layouts/Stills/records/{record_id}"), 
                headers=config.api_headers(current_token), 
                verify=False,
                timeout=30  # Add timeout to prevent hanging
            )
            
            if response.status_code == 401:
                print(f"  -> Token expired, refreshing token (attempt {attempt + 1}/{max_retries})")
                current_token = config.get_token()  # Refresh token
                continue
            
            response.raise_for_status()
            return response.json()['response']['data'][0], current_token
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout getting record data (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error getting record data (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
                
        except Exception as e:
            print(f"  -> Error getting record data (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to get record data after {max_retries} attempts")
    return None, current_token

def batch_update_record(record_id, token, updates):
    """Update multiple fields in a single API call to reduce overhead."""
    try:
        payload = {"fieldData": updates}
        response = requests.patch(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            json=payload, 
            verify=False
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to batch update record: {e}")
        return False

def run_workflow_step(step, stills_id, record_id, token):
    """Run a single workflow step."""
    step_num = step["step_num"]
    script_name = step["script"]
    description = step["description"]
    
    print(f"--- Step {step_num}: {description} ---")
    print(f"  -> Processing stills_id: {stills_id}")
    
    # Handle dynamic status checking for step 5 (could come from step 3 or 4)
    if step_num == 5 and step.get("status_before") is None:
        # Get current record data to check actual status
        record_data, token = get_current_record_data(record_id, token)
        if record_data:
            current_status = record_data['fieldData'].get(FIELD_MAPPING["status"], '')
            print(f"  -> Current status: {current_status}")
            # Step 5 can proceed from either "3 - Metadata Parsed" or "4 - Scraping URL"
            if current_status not in ["3 - Metadata Parsed", "4 - Scraping URL"]:
                print(f"  -> WARNING: Unexpected status '{current_status}' for step 5")
        else:
            print(f"  -> WARNING: Could not get record data for status check")
            print(f"  -> Assuming status is valid and proceeding with step 5")
        # Don't update status before step 5 - use whatever the current status is
    else:
        # Update status before running step (if specified)
        if step.get("status_before"):
            print(f"  -> Updating status to: {step['status_before']}")
            if not update_status(record_id, token, step["status_before"]):
                print(f"  -> WARNING: Failed to update status to '{step['status_before']}', but continuing workflow")
                # Don't return False - continue with the step even if status update fails
            else:
                print(f"  -> Status updated successfully")
    
    # Handle conditional steps with metadata evaluation
    if step.get("conditional") and step.get("evaluate_metadata_first"):
        print(f"  -> Evaluating metadata quality for conditional step")
        # Get current record data to check metadata quality
        record_data, token = get_current_record_data(record_id, token)
        if not record_data:
            print(f"  -> WARNING: Could not get record data for {stills_id}")
            print(f"  -> Assuming metadata is BAD and attempting to continue workflow")
            # If we can't get record data, assume metadata is bad and try to continue
            # This prevents the workflow from stopping due to temporary API issues
            print(f"  -> Continuing to step 5 (AI can work with whatever metadata exists)")
            return True
        
        # Evaluate metadata quality first
        metadata_quality_good = evaluate_metadata_quality(record_data['fieldData'], token)
        
        if metadata_quality_good:
            print(f"  -> SKIP: Metadata quality is GOOD, URL scraping not needed for {stills_id}")
            # Skip URL scraping - don't update status, keep current status so step 5 can proceed
            current_status = record_data['fieldData'].get(FIELD_MAPPING['status'], 'Unknown')
            print(f"  -> Status remains: {current_status} (URL scraping skipped)")
            return True
        else:
            print(f"  -> Metadata quality is BAD, checking if URL scraping is possible for {stills_id}")
            # Check if URL exists before proceeding
            url = record_data['fieldData'].get(FIELD_MAPPING["url"], '')
            if not url:
                print(f"  -> SKIP: No URL found for scraping, but continuing workflow anyway for {stills_id}")
                print(f"  -> AI can still generate descriptions from available metadata")
                # Keep current status (3 - Metadata Parsed) and let step 5 proceed
                current_status = record_data['fieldData'].get(FIELD_MAPPING['status'], 'Unknown')
                print(f"  -> Status remains: {current_status} (URL scraping skipped, continuing workflow)")
                return True
            else:
                print(f"  -> URL found for {stills_id}: {url}")
                # Continue with URL scraping - the script will run normally below
    
    # Handle other conditional steps (legacy)
    elif step.get("conditional"):
        if step_num == 4:  # Legacy URL scraping step
            print(f"  -> Checking for URL in legacy conditional step")
            # Get current record data to check for URL
            record_data, token = get_current_record_data(record_id, token)
            if not record_data:
                print(f"  -> WARNING: Could not get record data for {stills_id}")
                print(f"  -> Assuming no URL and continuing workflow")
                return True
            
            url = record_data['fieldData'].get(FIELD_MAPPING["url"], '')
            if not url:
                print(f"  -> SKIP: No URL found for scraping for {stills_id}")
                return True
            else:
                print(f"  -> URL found for {stills_id}: {url}")
    
    # Handle steps that require good metadata (legacy - now handled above)
    if step.get("requires_good_metadata"):
        print(f"  -> Checking metadata quality requirement")
        # Get current record data to check metadata quality
        record_data, token = get_current_record_data(record_id, token)
        if not record_data:
            print(f"  -> WARNING: Could not get record data for {stills_id}")
            print(f"  -> Assuming metadata is BAD and continuing workflow anyway")
            print(f"  -> AI can work with whatever metadata exists")
            return True
        
        # Evaluate metadata quality inline
        if not evaluate_metadata_quality(record_data['fieldData'], token):
            print(f"  -> HALT: Metadata quality is BAD for {stills_id}, not 'GOOD'")
            # Set status to awaiting user input
            if not update_status(record_id, token, "Awaiting User Input"):
                print(f"  -> ERROR: Failed to update status to 'Awaiting User Input'")
            return False
        else:
            print(f"  -> Metadata quality is GOOD for {stills_id}, proceeding")
    
    # Run the script
    script_path = JOBS_DIR / script_name
    
    if not script_path.exists():
        print(f"  -> FATAL ERROR: Script not found: {script_path}")
        error_msg = format_error_message(
            stills_id,
            description,
            f"Script not found: {script_name}",
            "Configuration Error"
        )
        write_error_to_console(record_id, token, error_msg)
        return False
    
    try:
        print(f"  -> Running script: {script_name} for {stills_id}")
        
        # In debug mode, show output in real-time
        if DEBUG_MODE:
            print(f"  -> DEBUG MODE: Running subprocess with real-time output")
            result = subprocess.run(
                ["python3", str(script_path), stills_id, token], 
                timeout=300  # 5 minute timeout
            )
            # In debug mode, just check return code
            success = result.returncode == 0
            if success:
                print(f"  -> SUCCESS: {script_name} completed for {stills_id}")
                # Update status after successful completion (only if status_after is not None)
                if step["status_after"] is not None:
                    print(f"  -> Updating status to: {step['status_after']}")
                    if not update_status(record_id, token, step["status_after"]):
                        print(f"  -> WARNING: Failed to update status to '{step['status_after']}', but step completed successfully")
                    else:
                        print(f"  -> Status updated successfully")
                return True
            else:
                print(f"  -> FAILURE: {script_name} failed with exit code {result.returncode} for {stills_id}")
                error_msg = format_error_message(
                    stills_id,
                    description,
                    f"Script failed with exit code {result.returncode}",
                    "Processing Error"
                )
                write_error_to_console(record_id, token, error_msg)
                return False
        else:
            # Normal mode - capture output but show full tracebacks on error
            print(f"  -> Executing: python3 {script_path} {stills_id} {token[:10]}...")
            result = subprocess.run(
                ["python3", str(script_path), stills_id, token], 
                capture_output=True, 
                text=True,
                timeout=300  # 5 minute timeout
            )
        
        if result.returncode == 0:
            print(f"  -> SUCCESS: {script_name} completed for {stills_id}")
            
            # Update status after successful completion (only if status_after is not None)
            if step["status_after"] is not None:
                print(f"  -> Updating status to: {step['status_after']}")
                if not update_status(record_id, token, step["status_after"]):
                    print(f"  -> WARNING: Failed to update status to '{step['status_after']}', but step completed successfully")
                else:
                    print(f"  -> Status updated successfully")
            
            return True
        else:
            print(f"  -> FAILURE: {script_name} failed with exit code {result.returncode} for {stills_id}")
            print(f"  -> RAW STDERR OUTPUT:")
            if result.stderr:
                print(result.stderr)
            print(f"  -> RAW STDOUT OUTPUT:")
            if result.stdout:
                print(result.stdout)
            
            # Extract meaningful error from stderr/stdout
            stderr_output = result.stderr.strip() if result.stderr else ""
            stdout_output = result.stdout.strip() if result.stdout else ""
            
            # Filter out ONLY urllib3 warnings for FileMaker storage, but keep everything else
            def filter_warnings_for_storage(text):
                if not text:
                    return ""
                
                # Keep original text for display, but filter for storage
                lines = text.split('\n')
                filtered = []
                
                for line in lines:
                    # Only filter out very specific urllib3 warnings - be extremely precise
                    is_urllib3_warning = False
                    
                    # Only filter lines that are EXACTLY urllib3 warnings (not legitimate errors)
                    if line.strip().startswith('warnings.warn(') and any(pattern in line for pattern in [
                        '/urllib3/__init__.py',
                        'NotOpenSSLWarning',
                        'urllib3 v2 only supports OpenSSL',
                        'github.com/urllib3/urllib3/issues'
                    ]):
                        is_urllib3_warning = True
                    elif line.strip().startswith('/Users/') and '/urllib3/' in line and 'NotOpenSSLWarning' in line:
                        is_urllib3_warning = True
                    elif 'urllib3 v2 only supports OpenSSL' in line and 'LibreSSL' in line:
                        is_urllib3_warning = True
                    
                    # Keep everything except very specific urllib3 warnings
                    if not is_urllib3_warning:
                        filtered.append(line)
                
                return '\n'.join(filtered).strip()
            
            # Filter for storage but keep full output for console display
            stderr_filtered = filter_warnings_for_storage(stderr_output)
            stdout_filtered = filter_warnings_for_storage(stdout_output)
            
            # Get the most relevant error information for FileMaker storage
            if stderr_filtered:
                error_details = stderr_filtered
            elif stdout_filtered:
                error_details = stdout_filtered
            else:
                error_details = f"Script failed with exit code {result.returncode}"
            
            # Show what we're storing in FileMaker
            print(f"  -> Writing error to FileMaker: {error_details[:200]}...")
            
            error_msg = format_error_message(
                stills_id,
                description,
                error_details,
                "Processing Error"
            )
            write_error_to_console(record_id, token, error_msg)
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  -> TIMEOUT: {script_name} timed out after 5 minutes for {stills_id}")
        error_msg = format_error_message(
            stills_id,
            description,
            f"Script timed out after 5 minutes: {script_name}",
            "Timeout Error"
        )
        write_error_to_console(record_id, token, error_msg)
        return False
        
    except Exception as e:
        print(f"  -> SYSTEM ERROR: {e}")
        traceback.print_exc()  # Show full traceback for system errors
        error_msg = format_error_message(
            stills_id,
            description,
            f"System error running {script_name}: {str(e)}",
            "System Error"
        )
        write_error_to_console(record_id, token, error_msg)
        return False

def run_complete_workflow_with_record_id(stills_id, record_id, token):
    """Run the complete AutoLog workflow for a single stills_id with pre-fetched record_id."""
    workflow_start_time = time.time()
    print(f"=== Starting AutoLog workflow for {stills_id} (record_id: {record_id}) ===")
    
    # Ultra-minimal random delay since session management is proven stable with 100% success
    import random
    time.sleep(random.uniform(0.001, 0.01))  # Reduced from 0.01-0.05s to 0.001-0.01s
    
    try:
        # Run each workflow step
        for step in WORKFLOW_STEPS:
            step_start_time = time.time()
            success = run_workflow_step(step, stills_id, record_id, token)
            step_duration = time.time() - step_start_time
            
            if not success:
                print(f"=== Workflow STOPPED at step {step['step_num']}: {step['description']} ===")
                print(f"  -> Step duration: {step_duration:.2f} seconds")
                print(f"  -> Total workflow duration: {time.time() - workflow_start_time:.2f} seconds")
                return False
            
            print(f"  -> Step {step['step_num']} completed in {step_duration:.2f} seconds")
            
            # Minimal delays - session management is proven stable
            if step.get("step_num") == 5:
                print(f"  -> Brief delay after description generation to allow calculated fields to update")
                time.sleep(0.1)  # Reduced from 0.2s to 0.1s - minimal delay for calculation fields
            elif step.get("step_num") in [1, 2]:
                # File operations need minimal completion time
                time.sleep(0.02)  # Reduced from 0.05s to 0.02s
            # Most operations are immediate - no delay needed
        
        # Mark as complete
        if not update_status(record_id, token, "9 - Complete"):
            print(f"  -> Warning: Failed to update final status to 'Complete'")
        else:
            print(f"  -> Final status updated to: 9 - Complete")
        
        total_duration = time.time() - workflow_start_time
        print(f"=== Workflow COMPLETED successfully for {stills_id} in {total_duration:.2f} seconds ===")
        return True
        
    except Exception as e:
        total_duration = time.time() - workflow_start_time
        print(f"=== FATAL ERROR in workflow for {stills_id} after {total_duration:.2f} seconds: {e} ===")
        traceback.print_exc()
        
        # Try to write error to console
        try:
            error_msg = format_error_message(
                stills_id,
                "Workflow Controller",
                f"Critical system error: {str(e)}",
                "Critical Error"
            )
            write_error_to_console(record_id, token, error_msg)
        except:
            pass
        
        return False

def run_complete_workflow(stills_id, token):
    """Run the complete AutoLog workflow for a single stills_id."""
    workflow_start_time = time.time()
    print(f"=== Starting AutoLog workflow for {stills_id} ===")
    
    # Add a small random delay to stagger connection attempts in batch processing
    import random
    time.sleep(random.uniform(0.1, 0.5))
    
    try:
        # Get record ID with retry logic
        record_id = None
        for attempt in range(3):  # Try 3 times
            try:
                record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
                print(f"Found record ID: {record_id}")
                break
            except Exception as e:
                print(f"  -> Record lookup attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:  # If not the last attempt
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                    continue
                else:
                    print(f"  -> Failed to find record ID for {stills_id} after 3 attempts")
                    return False
        
        if not record_id:
            print(f"  -> No record ID found for {stills_id}")
            return False
        
        # Run each workflow step
        for step in WORKFLOW_STEPS:
            step_start_time = time.time()
            success = run_workflow_step(step, stills_id, record_id, token)
            step_duration = time.time() - step_start_time
            
            if not success:
                print(f"=== Workflow STOPPED at step {step['step_num']}: {step['description']} ===")
                print(f"  -> Step duration: {step_duration:.2f} seconds")
                print(f"  -> Total workflow duration: {time.time() - workflow_start_time:.2f} seconds")
                return False
            
            print(f"  -> Step {step['step_num']} completed in {step_duration:.2f} seconds")
            
            # Optimized delays - system proven stable with 100% success rate
            if step.get("step_num") == 5:
                print(f"  -> Brief delay after description generation to allow calculated fields to update")
                time.sleep(0.1)  # Reduced from 0.2s to 0.1s - minimal delay for calculation fields
            elif step.get("step_num") in [1, 2]:
                # File operations need minimal completion time
                time.sleep(0.02)  # Reduced from 0.05s to 0.02s
            # All other operations are immediate - no delay needed
        
        # Mark as complete
        if not update_status(record_id, token, "9 - Complete"):
            print(f"  -> Warning: Failed to update final status to 'Complete'")
        else:
            print(f"  -> Final status updated to: 9 - Complete")
        
        total_duration = time.time() - workflow_start_time
        print(f"=== Workflow COMPLETED successfully for {stills_id} in {total_duration:.2f} seconds ===")
        return True
        
    except Exception as e:
        total_duration = time.time() - workflow_start_time
        print(f"=== FATAL ERROR in workflow for {stills_id} after {total_duration:.2f} seconds: {e} ===")
        traceback.print_exc()
        
        # Try to write error to console if we have a record ID
        try:
            record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
            error_msg = format_error_message(
                stills_id,
                "Workflow Controller",
                f"Critical system error: {str(e)}",
                "Critical Error"
            )
            write_error_to_console(record_id, token, error_msg)
        except:
            pass
        
        return False

def run_batch_workflow(stills_ids, token, max_workers=16):  # Increased from 12 to 16
    """Run the complete AutoLog workflow for multiple stills_ids in parallel."""
    # Sort stills_ids to process them in order for better predictability
    sorted_stills_ids = sorted(stills_ids)
    
    print(f"=== Starting BATCH AutoLog workflow for {len(sorted_stills_ids)} items ===")
    print(f"=== Processing in order: {sorted_stills_ids[:5]}{'...' if len(sorted_stills_ids) > 5 else ''} ===")
    
    # Pre-fetch all record IDs to avoid concurrent database lookups
    print(f"=== Pre-fetching record IDs for {len(sorted_stills_ids)} items ===")
    stills_to_record_id = {}
    failed_lookups = []
    
    for i, stills_id in enumerate(sorted_stills_ids):
        try:
            # Remove delay since session management is proven stable
            # No delay needed between lookups now
            
            record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
            stills_to_record_id[stills_id] = record_id
            print(f"  -> {stills_id}: {record_id}")
        except Exception as e:
            print(f"  -> {stills_id}: FAILED - {e}")
            failed_lookups.append(stills_id)
    
    if failed_lookups:
        print(f"⚠️ {len(failed_lookups)} items failed record lookup: {failed_lookups}")
        # Remove failed lookups from processing list
        sorted_stills_ids = [sid for sid in sorted_stills_ids if sid not in failed_lookups]
    
    if not sorted_stills_ids:
        print(f"❌ No items can be processed - all record lookups failed")
        return {"total_items": 0, "successful": 0, "failed": len(failed_lookups), "results": []}
    
    # More aggressive concurrency settings - optimized for OpenAI multi-key capacity
    if len(sorted_stills_ids) > 50:
        actual_max_workers = 12  # Increased from 8 to 12 for large batches
        print(f"=== Large batch detected ({len(sorted_stills_ids)} items) - using {actual_max_workers} workers ===")
    elif len(sorted_stills_ids) > 20:
        actual_max_workers = 14  # Increased from 10 to 14 for medium batches
        print(f"=== Medium batch detected ({len(sorted_stills_ids)} items) - using {actual_max_workers} workers ===")
    else:
        actual_max_workers = min(max_workers, len(sorted_stills_ids))
        print(f"=== Using {actual_max_workers} concurrent workers ===")
    
    results = {
        "total_items": len(sorted_stills_ids) + len(failed_lookups),
        "successful": 0,
        "failed": len(failed_lookups),  # Count failed lookups
        "results": [{"stills_id": sid, "success": False, "error": "Record lookup failed"} for sid in failed_lookups],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    def process_single_item(stills_id):
        """Process a single stills_id and return result."""
        try:
            print(f"[BATCH] Starting workflow for {stills_id}")
            # Pass the pre-fetched record_id to avoid database lookup
            record_id = stills_to_record_id[stills_id]
            success = run_complete_workflow_with_record_id(stills_id, record_id, token)
            result = {
                "stills_id": stills_id,
                "success": success,
                "completed_at": datetime.now().isoformat(),
                "error": None
            }
            print(f"[BATCH] {'✅ SUCCESS' if success else '❌ FAILED'}: {stills_id}")
            return result
        except Exception as e:
            result = {
                "stills_id": stills_id,
                "success": False,
                "completed_at": datetime.now().isoformat(),
                "error": str(e)
            }
            print(f"[BATCH] ❌ ERROR: {stills_id} - {e}")
            return result
    
    # For large batches (40+), add progress reporting milestones
    progress_milestones = [10, 20, 30, 40, 50] if len(sorted_stills_ids) >= 10 else []
    
    # Process items in parallel with minimal rate limiting
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        # Submit all jobs with minimal delay
        future_to_stills_id = {}
        for i, stills_id in enumerate(sorted_stills_ids):
            # Remove delay between job submissions - session management is proven
            # No delay needed
            
            future = executor.submit(process_single_item, stills_id)
            future_to_stills_id[future] = stills_id
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_stills_id):
            result = future.result()
            results["results"].append(result)
            
            if result["success"]:
                results["successful"] += 1
            else:
                results["failed"] += 1
            
            # Print progress with milestones for large batches
            completed = len(results["results"])
            
            # Check for milestone progress
            if completed in progress_milestones:
                success_rate = (results['successful'] / completed * 100) if completed > 0 else 0
                print(f"[BATCH] MILESTONE: {completed}/{len(sorted_stills_ids)} completed ({results['successful']} successful, {results['failed']} failed) - Success rate: {success_rate:.1f}%")
            else:
                print(f"[BATCH] Progress: {completed}/{len(sorted_stills_ids)} completed ({results['successful']} successful, {results['failed']} failed)")
    
    results["end_time"] = datetime.now().isoformat()
    
    # Calculate total duration
    start_time = datetime.fromisoformat(results["start_time"])
    end_time = datetime.fromisoformat(results["end_time"])
    duration = (end_time - start_time).total_seconds()
    
    # Print final summary
    print(f"=== BATCH AutoLog workflow COMPLETED ===")
    print(f"Total items: {results['total_items']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")
    print(f"Success rate: {(results['successful'] / results['total_items'] * 100):.1f}%")
    print(f"Total duration: {duration:.2f} seconds")
    print(f"Average per item: {duration / results['total_items']:.2f} seconds")
    print(f"⚡ Throughput: {results['total_items'] / duration * 60:.1f} items/minute")  # Added throughput metric
    
    # List any failures
    if results["failed"] > 0:
        print(f"Failed items:")
        for result in results["results"]:
            if not result["success"]:
                error_msg = result["error"] if result["error"] else "Unknown error"
                print(f"  - {result['stills_id']}: {error_msg}")
    
    return results

def find_pending_items(token):
    """Find all items with '0 - Pending File Info' status."""
    try:
        print(f"🔍 Searching for items with '0 - Pending File Info' status...")
        
        # Query FileMaker for records with pending status
        query = {
            "query": [{FIELD_MAPPING["status"]: "0 - Pending File Info"}],
            "limit": 100  # Reasonable batch size to avoid overwhelming the system
        }
        
        response = requests.post(
            config.url("layouts/Stills/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False
        )
        
        if response.status_code == 404:
            print(f"📋 No pending items found")
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        # Extract stills_ids from the records
        stills_ids = []
        for record in records:
            stills_id = record['fieldData'].get(FIELD_MAPPING["stills_id"])
            if stills_id:
                stills_ids.append(stills_id)
            else:
                print(f"⚠️ Warning: Record {record['recordId']} has no stills_id")
        
        print(f"📋 Found {len(stills_ids)} pending items: {stills_ids[:10]}{'...' if len(stills_ids) > 10 else ''}")
        return stills_ids
        
    except Exception as e:
        print(f"❌ Error finding pending items: {e}")
        return []

if __name__ == "__main__":
    try:
        token = config.get_token()
        
        # Find all pending items automatically
        stills_ids = find_pending_items(token)
        
        if not stills_ids:
            print(f"✅ No pending items found - nothing to process")
            sys.exit(0)
        
        # Process single item or batch
        if len(stills_ids) == 1:
            # Single item - use original logic
            success = run_complete_workflow(stills_ids[0], token)
            print(f"SUCCESS [complete_workflow]: {stills_ids[0]}" if success else f"FAILURE [complete_workflow]: {stills_ids[0]}")
            sys.exit(0 if success else 1)
        else:
            # Batch processing
            results = run_batch_workflow(stills_ids, token)
            
            # Output results as JSON for easy parsing by client
            print(f"BATCH_RESULTS: {json.dumps(results, indent=2)}")
            
            # Exit with success if all items succeeded, otherwise partial failure
            sys.exit(0 if results["failed"] == 0 else 1)
            
    except Exception as e:
        print(f"Critical startup error: {e}")
        sys.exit(1) 