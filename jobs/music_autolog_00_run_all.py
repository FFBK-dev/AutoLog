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
import concurrent.futures
import threading
import os

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# No arguments - automatically discovers pending items
__ARGS__ = []

JOBS_DIR = Path(__file__).resolve().parent

# Debug mode support
DEBUG_MODE = os.getenv('AUTOLOG_DEBUG', 'false').lower() == 'true'

FIELD_MAPPING = {
    # Core identification
    "music_id": "INFO_MUSIC_ID",
    "status": "AutoLog_Status",
    "dev_console": "AI_DevConsole",
    
    # File paths
    "filepath_import": "SPECS_Filepath_Import",
    "filepath_server": "SPECS_Filepath_Server",
    
    # File specs (Step 2)
    "file_format": "SPECS_File_Format",
    "sample_rate": "SPECS_File_Sample_Rate",
    "duration": "SPECS_Duration",
    
    # Music metadata (Step 3)
    "song_name": "INFO_Song_Name",
    "artist": "INFO_Artist",
    "album": "INFO_Album",
    "composer": "PUBLISHING_Composer",
    "performed_by": "INFO_PerformedBy",
    "genre": "INFO_Genre",
    "release_year": "INFO_Release_Year",
    "track_number": "INFO_Track_Number",
    "isrc_upc": "INFO_ISRC_UPC_Code",
    "copyright": "INFO_Copyright",
    "cue_type": "INFO_Cue_Type",
    "url": "SPECS_URL",
    
    # Raw metadata storage
    "metadata": "INFO_Metadata",
    
    # Import tracking
    "imported_by": "SPECS_File_Imported_By",
    "import_timestamp": "SPECS_File_Import_Timestamp",
}

# Define the complete workflow with status updates
WORKFLOW_STEPS = [
    {
        "step_num": 1,
        "status_before": "0 - Pending File Info",
        "status_after": "1 - File Renamed",
        "script": "music_autolog_01_rename_file.py",
        "description": "Rename File with ID Prefix"
    },
    {
        "step_num": 2,
        "status_before": "1 - File Renamed",
        "status_after": "2 - Specs Extracted",
        "script": "music_autolog_02_extract_specs.py",
        "description": "Extract File Specs"
    },
    {
        "step_num": 3,
        "status_before": "2 - Specs Extracted",
        "status_after": "3 - Metadata Parsed",
        "script": "music_autolog_03_parse_metadata.py",
        "description": "Parse Metadata"
    },
    {
        "step_num": 4,
        "status_before": "3 - Metadata Parsed",
        "status_after": "4 - Notion Queried",
        "script": "music_autolog_04_query_notion.py",
        "description": "Query Notion Database",
        "final_status": "5 - Complete"
    }
]

def format_error_message(music_id, step_name, error_details, error_type="Processing Error"):
    """Format error messages for the AI_DevConsole field in a user-friendly way."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Clean up error details
    clean_error = error_details.strip()
    if clean_error.startswith("Error:"):
        clean_error = clean_error[6:].strip()
    if clean_error.startswith("FATAL ERROR:"):
        clean_error = clean_error[12:].strip()
    
    # Generous truncation for FileMaker (1000 chars)
    if len(clean_error) > 1000:
        clean_error = clean_error[:997] + "..."
    
    return f"[{timestamp}] {error_type} - {step_name}\nMusic ID: {music_id}\nIssue: {clean_error}"

def write_error_to_console(record_id, token, error_message, max_retries=3):
    """Safely write error message to the AI_DevConsole field with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            payload = {"fieldData": {FIELD_MAPPING["dev_console"]: error_message}}
            response = requests.patch(
                config.url(f"layouts/Music/records/{record_id}"), 
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
                config.url(f"layouts/Music/records/{record_id}"), 
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
                config.url(f"layouts/Music/records/{record_id}"), 
                headers=config.api_headers(current_token), 
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                print(f"  -> Token expired, refreshing token (attempt {attempt + 1}/{max_retries})")
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return response.json()['response']['data'][0], current_token
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout getting record data (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error getting record data (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except Exception as e:
            print(f"  -> Error getting record data (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to get record data after {max_retries} attempts")
    return None, current_token

def run_workflow_step(step, music_id, record_id, token):
    """Run a single workflow step."""
    step_num = step["step_num"]
    script_name = step["script"]
    description = step["description"]
    is_final_step = step.get("final_status") is not None
    
    print(f"--- Step {step_num}: {description} ---")
    print(f"  -> Processing music_id: {music_id}")
    
    # For non-final steps, update status BEFORE running
    if not is_final_step and step.get("status_after"):
        print(f"  -> Updating status to: {step['status_after']} (before running step)")
        if not update_status(record_id, token, step["status_after"]):
            print(f"  -> WARNING: Failed to update status to '{step['status_after']}', but continuing workflow")
        else:
            print(f"  -> Status updated successfully")
    elif is_final_step:
        print(f"  -> Final step - will update to '{step['final_status']}' after completion")
    
    # Run the script
    script_path = JOBS_DIR / script_name
    
    if not script_path.exists():
        print(f"  -> FATAL ERROR: Script not found: {script_path}")
        error_msg = format_error_message(
            music_id,
            description,
            f"Script not found: {script_name}",
            "Configuration Error"
        )
        write_error_to_console(record_id, token, error_msg)
        return False
    
    try:
        print(f"  -> Running script: {script_name} for {music_id}")
        print(f"🔄 Initiating subprocess: {description} (Step {step_num}) on ID {music_id}")
        
        # Debug mode - real-time output
        if DEBUG_MODE:
            print(f"  -> DEBUG MODE: Running subprocess with real-time output")
            result = subprocess.run(
                ["python3", str(script_path), music_id, token], 
                timeout=300  # 5 minute timeout
            )
            success = result.returncode == 0
            if success:
                print(f"✅ Subprocess completed: {description} (Step {step_num}) on ID {music_id}")
                print(f"  -> SUCCESS: {script_name} completed for {music_id}")
                # Handle final status update
                if is_final_step and step.get("final_status"):
                    print(f"  -> Updating final status to: {step['final_status']}")
                    if not update_status(record_id, token, step["final_status"]):
                        print(f"  -> WARNING: Failed to update status to '{step['final_status']}', but step completed successfully")
                    else:
                        print(f"  -> Status updated successfully")
                return True
            else:
                print(f"❌ Subprocess failed: {description} (Step {step_num}) on ID {music_id}")
                print(f"  -> FAILURE: {script_name} failed with exit code {result.returncode} for {music_id}")
                error_msg = format_error_message(
                    music_id,
                    description,
                    f"Script failed with exit code {result.returncode}",
                    "Processing Error"
                )
                write_error_to_console(record_id, token, error_msg)
                return False
        else:
            # Normal mode - capture output
            print(f"  -> Executing: python3 {script_path} {music_id} {token[:10]}...")
            result = subprocess.run(
                ["python3", str(script_path), music_id, token], 
                capture_output=True, 
                text=True,
                timeout=300  # 5 minute timeout
            )
        
        if result.returncode == 0:
            print(f"✅ Subprocess completed: {description} (Step {step_num}) on ID {music_id}")
            print(f"  -> SUCCESS: {script_name} completed for {music_id}")
            
            # Handle final status update
            if is_final_step and step.get("final_status"):
                print(f"  -> Updating final status to: {step['final_status']}")
                if not update_status(record_id, token, step["final_status"]):
                    print(f"  -> WARNING: Failed to update status to '{step['final_status']}', but step completed successfully")
                else:
                    print(f"  -> Status updated successfully")
            
            return True
        else:
            print(f"❌ Subprocess failed: {description} (Step {step_num}) on ID {music_id}")
            print(f"  -> FAILURE: {script_name} failed with exit code {result.returncode} for {music_id}")
            print(f"  -> RAW STDERR OUTPUT:")
            if result.stderr:
                print(result.stderr)
            print(f"  -> RAW STDOUT OUTPUT:")
            if result.stdout:
                print(result.stdout)
            
            # Extract meaningful error
            stderr_output = result.stderr.strip() if result.stderr else ""
            stdout_output = result.stdout.strip() if result.stdout else ""
            
            # Filter urllib3 warnings
            def filter_warnings_for_storage(text):
                if not text:
                    return ""
                lines = text.split('\n')
                filtered = []
                for line in lines:
                    is_urllib3_warning = (
                        line.strip().startswith('warnings.warn(') and 
                        any(pattern in line for pattern in [
                            '/urllib3/__init__.py',
                            'NotOpenSSLWarning',
                            'urllib3 v2 only supports OpenSSL'
                        ])
                    )
                    if not is_urllib3_warning:
                        filtered.append(line)
                return '\n'.join(filtered).strip()
            
            stderr_filtered = filter_warnings_for_storage(stderr_output)
            stdout_filtered = filter_warnings_for_storage(stdout_output)
            
            if stderr_filtered:
                error_details = stderr_filtered
            elif stdout_filtered:
                error_details = stdout_filtered
            else:
                error_details = f"Script failed with exit code {result.returncode}"
            
            print(f"  -> Writing error to FileMaker: {error_details[:200]}...")
            
            error_msg = format_error_message(
                music_id,
                description,
                error_details,
                "Processing Error"
            )
            write_error_to_console(record_id, token, error_msg)
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  -> TIMEOUT: {script_name} timed out after 5 minutes for {music_id}")
        error_msg = format_error_message(
            music_id,
            description,
            f"Script timed out after 5 minutes: {script_name}",
            "Timeout Error"
        )
        write_error_to_console(record_id, token, error_msg)
        return False
        
    except Exception as e:
        print(f"  -> SYSTEM ERROR: {e}")
        traceback.print_exc()
        error_msg = format_error_message(
            music_id,
            description,
            f"System error running {script_name}: {str(e)}",
            "System Error"
        )
        write_error_to_console(record_id, token, error_msg)
        return False

def run_complete_workflow_with_record_id(music_id, record_id, token):
    """Run the complete AutoLog workflow for a single music_id with pre-fetched record_id."""
    workflow_start_time = time.time()
    print(f"=== Starting Music AutoLog workflow for {music_id} (record_id: {record_id}) ===")
    
    # Minimal random delay for batch processing
    import random
    time.sleep(random.uniform(0.001, 0.01))
    
    try:
        # Run each workflow step
        for step in WORKFLOW_STEPS:
            step_start_time = time.time()
            success = run_workflow_step(step, music_id, record_id, token)
            step_duration = time.time() - step_start_time
            
            if not success:
                print(f"=== Workflow STOPPED at step {step['step_num']}: {step['description']} ===")
                print(f"  -> Step duration: {step_duration:.2f} seconds")
                print(f"  -> Total workflow duration: {time.time() - workflow_start_time:.2f} seconds")
                return False
            
            print(f"  -> Step {step['step_num']} completed in {step_duration:.2f} seconds")
            
            # Minimal delays for file operations
            if step.get("step_num") in [1, 2]:
                time.sleep(0.02)
        
        total_duration = time.time() - workflow_start_time
        print(f"=== Workflow COMPLETED successfully for {music_id} in {total_duration:.2f} seconds ===")
        return True
        
    except Exception as e:
        total_duration = time.time() - workflow_start_time
        print(f"=== FATAL ERROR in workflow for {music_id} after {total_duration:.2f} seconds: {e} ===")
        traceback.print_exc()
        
        try:
            error_msg = format_error_message(
                music_id,
                "Workflow Controller",
                f"Critical system error: {str(e)}",
                "Critical Error"
            )
            write_error_to_console(record_id, token, error_msg)
        except:
            pass
        
        return False

def run_complete_workflow(music_id, token):
    """Run the complete AutoLog workflow for a single music_id."""
    workflow_start_time = time.time()
    print(f"=== Starting Music AutoLog workflow for {music_id} ===")
    
    # Small random delay for batch processing
    import random
    time.sleep(random.uniform(0.1, 0.5))
    
    try:
        # Get record ID with retry logic
        record_id = None
        for attempt in range(3):
            try:
                record_id = config.find_record_id(token, "Music", {FIELD_MAPPING["music_id"]: f"=={music_id}"})
                print(f"Found record ID: {record_id}")
                break
            except Exception as e:
                print(f"  -> Record lookup attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    print(f"  -> Failed to find record ID for {music_id} after 3 attempts")
                    return False
        
        if not record_id:
            print(f"  -> No record ID found for {music_id}")
            return False
        
        # Run each workflow step
        for step in WORKFLOW_STEPS:
            step_start_time = time.time()
            success = run_workflow_step(step, music_id, record_id, token)
            step_duration = time.time() - step_start_time
            
            if not success:
                print(f"=== Workflow STOPPED at step {step['step_num']}: {step['description']} ===")
                print(f"  -> Step duration: {step_duration:.2f} seconds")
                print(f"  -> Total workflow duration: {time.time() - workflow_start_time:.2f} seconds")
                return False
            
            print(f"  -> Step {step['step_num']} completed in {step_duration:.2f} seconds")
            
            # Minimal delays for file operations
            if step.get("step_num") in [1, 2]:
                time.sleep(0.02)
        
        total_duration = time.time() - workflow_start_time
        print(f"=== Workflow COMPLETED successfully for {music_id} in {total_duration:.2f} seconds ===")
        return True
        
    except Exception as e:
        total_duration = time.time() - workflow_start_time
        print(f"=== FATAL ERROR in workflow for {music_id} after {total_duration:.2f} seconds: {e} ===")
        traceback.print_exc()
        
        try:
            record_id = config.find_record_id(token, "Music", {FIELD_MAPPING["music_id"]: f"=={music_id}"})
            error_msg = format_error_message(
                music_id,
                "Workflow Controller",
                f"Critical system error: {str(e)}",
                "Critical Error"
            )
            write_error_to_console(record_id, token, error_msg)
        except:
            pass
        
        return False

def run_batch_workflow(music_ids, token, max_workers=16):
    """Run the complete AutoLog workflow for multiple music_ids in parallel."""
    sorted_music_ids = sorted(music_ids)
    
    print(f"=== Starting BATCH Music AutoLog workflow for {len(sorted_music_ids)} items ===")
    print(f"=== Processing in order: {sorted_music_ids[:5]}{'...' if len(sorted_music_ids) > 5 else ''} ===")
    
    # Pre-fetch all record IDs
    print(f"=== Pre-fetching record IDs for {len(sorted_music_ids)} items ===")
    music_to_record_id = {}
    failed_lookups = []
    
    for music_id in sorted_music_ids:
        try:
            record_id = config.find_record_id(token, "Music", {FIELD_MAPPING["music_id"]: f"=={music_id}"})
            music_to_record_id[music_id] = record_id
            print(f"  -> {music_id}: {record_id}")
        except Exception as e:
            print(f"  -> {music_id}: FAILED - {e}")
            failed_lookups.append(music_id)
    
    if failed_lookups:
        print(f"⚠️ {len(failed_lookups)} items failed record lookup: {failed_lookups}")
        sorted_music_ids = [mid for mid in sorted_music_ids if mid not in failed_lookups]
    
    if not sorted_music_ids:
        print(f"❌ No items can be processed - all record lookups failed")
        return {"total_items": 0, "successful": 0, "failed": len(failed_lookups), "results": []}
    
    # Concurrency settings
    if len(sorted_music_ids) > 50:
        actual_max_workers = 12
        print(f"=== Large batch detected ({len(sorted_music_ids)} items) - using {actual_max_workers} workers ===")
    elif len(sorted_music_ids) > 20:
        actual_max_workers = 14
        print(f"=== Medium batch detected ({len(sorted_music_ids)} items) - using {actual_max_workers} workers ===")
    else:
        actual_max_workers = min(max_workers, len(sorted_music_ids))
        print(f"=== Using {actual_max_workers} concurrent workers ===")
    
    results = {
        "total_items": len(sorted_music_ids) + len(failed_lookups),
        "successful": 0,
        "failed": len(failed_lookups),
        "results": [{"music_id": mid, "success": False, "error": "Record lookup failed"} for mid in failed_lookups],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    def process_single_item(music_id):
        """Process a single music_id and return result."""
        try:
            print(f"[BATCH] Starting workflow for {music_id}")
            record_id = music_to_record_id[music_id]
            success = run_complete_workflow_with_record_id(music_id, record_id, token)
            result = {
                "music_id": music_id,
                "success": success,
                "completed_at": datetime.now().isoformat(),
                "error": None
            }
            print(f"[BATCH] {'✅ SUCCESS' if success else '❌ FAILED'}: {music_id}")
            return result
        except Exception as e:
            result = {
                "music_id": music_id,
                "success": False,
                "completed_at": datetime.now().isoformat(),
                "error": str(e)
            }
            print(f"[BATCH] ❌ ERROR: {music_id} - {e}")
            return result
    
    # Process items in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        future_to_music_id = {}
        for music_id in sorted_music_ids:
            future = executor.submit(process_single_item, music_id)
            future_to_music_id[future] = music_id
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_music_id):
            result = future.result()
            results["results"].append(result)
            
            if result["success"]:
                results["successful"] += 1
            else:
                results["failed"] += 1
            
            completed = len(results["results"])
            print(f"[BATCH] Progress: {completed}/{len(sorted_music_ids)} completed ({results['successful']} successful, {results['failed']} failed)")
    
    results["end_time"] = datetime.now().isoformat()
    
    # Calculate total duration
    start_time = datetime.fromisoformat(results["start_time"])
    end_time = datetime.fromisoformat(results["end_time"])
    duration = (end_time - start_time).total_seconds()
    
    # Print final summary
    print(f"=== BATCH Music AutoLog workflow COMPLETED ===")
    print(f"Total items: {results['total_items']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")
    print(f"Success rate: {(results['successful'] / results['total_items'] * 100):.1f}%")
    print(f"Total duration: {duration:.2f} seconds")
    print(f"Average per item: {duration / results['total_items']:.2f} seconds")
    print(f"⚡ Throughput: {results['total_items'] / duration * 60:.1f} items/minute")
    
    if results["failed"] > 0:
        print(f"Failed items:")
        for result in results["results"]:
            if not result["success"]:
                error_msg = result["error"] if result["error"] else "Unknown error"
                print(f"  - {result['music_id']}: {error_msg}")
    
    return results

def find_pending_items(token):
    """Find all items with '0 - Pending File Info' status."""
    try:
        print(f"🔍 Searching for items with '0 - Pending File Info' status...")
        
        query = {
            "query": [{FIELD_MAPPING["status"]: "0 - Pending File Info"}],
            "limit": 100
        }
        
        response = requests.post(
            config.url("layouts/Music/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False
        )
        
        if response.status_code == 404:
            print(f"📋 No pending items found")
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        # Extract music_ids from the records
        music_ids = []
        for record in records:
            music_id = record['fieldData'].get(FIELD_MAPPING["music_id"])
            if music_id:
                music_ids.append(music_id)
            else:
                print(f"⚠️ Warning: Record {record['recordId']} has no music_id")
        
        print(f"📋 Found {len(music_ids)} pending items: {music_ids[:10]}{'...' if len(music_ids) > 10 else ''}")
        return music_ids
        
    except Exception as e:
        print(f"❌ Error finding pending items: {e}")
        return []

if __name__ == "__main__":
    try:
        token = config.get_token()
        
        # Find all pending items automatically
        music_ids = find_pending_items(token)
        
        if not music_ids:
            print(f"✅ No pending items found - nothing to process")
            sys.exit(0)
        
        # Process single item or batch
        if len(music_ids) == 1:
            success = run_complete_workflow(music_ids[0], token)
            print(f"SUCCESS [complete_workflow]: {music_ids[0]}" if success else f"FAILURE [complete_workflow]: {music_ids[0]}")
            sys.exit(0 if success else 1)
        else:
            # Batch processing
            results = run_batch_workflow(music_ids, token)
            
            # Output results as JSON
            print(f"BATCH_RESULTS: {json.dumps(results, indent=2)}")
            
            sys.exit(0 if results["failed"] == 0 else 1)
            
    except Exception as e:
        print(f"Critical startup error: {e}")
        sys.exit(1)

