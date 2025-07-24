#!/usr/bin/env python3
"""
Polling-Based Stills AutoLog Workflow Controller

This script implements a continuous polling approach where:
1. Records are polled by status and advanced independently
2. Retries are seamless (just pick up on next poll)
3. Multiple records can progress in parallel without conflicts
4. No complex sequential workflows - each record moves at its own pace
5. Simpler than footage workflow - no parent-child dependencies

Advantages over sequential workflow:
- More resilient to individual failures
- Better parallel processing
- Seamless retries
- Cleaner status-based progression
- No workflow state management
"""

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
import logging

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.local_metadata_evaluator import evaluate_metadata_local

def tprint(message):
    """Print with timestamp for performance debugging."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}", flush=True)

# No arguments - continuously polls for records
__ARGS__ = []

JOBS_DIR = Path(__file__).resolve().parent

# Field mappings for Stills layout
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
    "reviewed_checkbox": "INFO_Reviewed_Checkbox",
    "globals_api_key_1": "SystemGlobals_AutoLog_OpenAI_API_Key_1",
    "globals_api_key_2": "SystemGlobals_AutoLog_OpenAI_API_Key_2",
    "globals_api_key_3": "SystemGlobals_AutoLog_OpenAI_API_Key_3",
    "globals_api_key_4": "SystemGlobals_AutoLog_OpenAI_API_Key_4",
    "globals_api_key_5": "SystemGlobals_AutoLog_OpenAI_API_Key_5"
}

def find_records_by_status(token, status_list):
    """Find all records with specified status(es)."""
    if isinstance(status_list, str):
        status_list = [status_list]
    
    all_records = []
    
    for status in status_list:
        try:
            query = {
                "query": [{FIELD_MAPPING["status"]: status}],
                "limit": 100
            }
            
            response = requests.post(
                config.url("layouts/Stills/_find"),
                headers=config.api_headers(token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 404:
                continue  # No records with this status
            
            response.raise_for_status()
            records = response.json()['response']['data']
            
            for record in records:
                stills_id = record['fieldData'].get(FIELD_MAPPING["stills_id"])
                if stills_id:
                    all_records.append({
                        "stills_id": stills_id,
                        "record_id": record['recordId'],
                        "current_status": status,
                        "record_data": record['fieldData']
                    })
        
        except Exception as e:
            tprint(f"❌ Error finding records with status '{status}': {e}")
            continue
    
    return all_records

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

def evaluate_metadata_quality(record_data, token, record_id=None):
    """Evaluate metadata quality using local analysis with simplified 40-point scale."""
    try:
        # Combine all metadata
        combined_metadata = combine_metadata(record_data)
        
        if not combined_metadata.strip():
            console_msg = "Metadata Evaluation: NO METADATA AVAILABLE - Cannot evaluate quality"
            if record_id:
                write_to_dev_console(record_id, token, console_msg)
            return False
        
        # Use simplified local evaluator
        evaluation = evaluate_metadata_local(combined_metadata)
        
        is_sufficient = evaluation.get("sufficient", False)
        reason = evaluation.get("reason", "No reason provided")
        confidence = evaluation.get("confidence", "medium")
        score = evaluation.get("score", 0.0)
        
        # Write evaluation results to AI_DevConsole
        if record_id:
            console_msg = f"Metadata Evaluation: {'✅ PASSED' if is_sufficient else '❌ FAILED'}\n"
            console_msg += f"Score: {score:.0f}/50 (Threshold: 10+)\n"
            console_msg += f"Confidence: {confidence}\n"
            console_msg += f"Details: {reason}"
            write_to_dev_console(record_id, token, console_msg)
        
        return is_sufficient
        
    except Exception as e:
        tprint(f"❌ Error in metadata evaluation: {e}")
        
        # Write error to console
        if record_id:
            console_msg = f"Metadata Evaluation: ❌ ERROR\nException: {str(e)}\nUsing fallback evaluation..."
            write_to_dev_console(record_id, token, console_msg)
        
        # Simple fallback: 30+ characters is reasonable
        combined_length = sum(len(str(record_data.get(FIELD_MAPPING.get(field, field), ''))) 
                            for field in ["metadata", "description_orig", "copyright", "source", "archival_id"])
        fallback_result = combined_length > 30
        
        if record_id:
            fallback_msg = f"Fallback Result: {'✅ PASSED' if fallback_result else '❌ FAILED'} (length check)\nCombined metadata: {combined_length} chars ({'>' if fallback_result else '≤'}30 threshold)"
            write_to_dev_console(record_id, token, fallback_msg)
        
        return fallback_result

def write_to_dev_console(record_id, token, message):
    """Write a message to the AI_DevConsole field."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console_entry = f"[{timestamp}] {message}"
        
        # Update the AI_DevConsole field
        field_data = {FIELD_MAPPING["dev_console"]: console_entry}
        config.update_record(token, "Stills", record_id, field_data)
        
    except Exception as e:
        tprint(f"⚠️ WARNING: Failed to write to AI_DevConsole: {e}")

def update_status(record_id, token, new_status, max_retries=3):
    """Update record status with retry logic."""
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
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return True
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
    
    return False

def run_single_script(script_name, stills_id, token, timeout=300):
    """Run a single script for a stills ID."""
    script_path = JOBS_DIR / script_name
    
    if not script_path.exists():
        return False, f"Script not found: {script_name}"
    
    try:
        result = subprocess.run(
            ["python3", str(script_path), stills_id, token],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        success = result.returncode == 0
        error_msg = result.stderr.strip() if result.stderr else None
        
        return success, error_msg
        
    except subprocess.TimeoutExpired:
        return False, f"Script timed out after {timeout}s"
    except Exception as e:
        return False, f"System error: {str(e)}"

def check_all_records_terminal(token, terminal_states):
    """Check if all stills records have reached terminal states."""
    try:
        # Check all stills records
        response = requests.post(
            config.url("layouts/Stills/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"INFO_STILLS_ID": "*"}],
                "limit": 1000
            },
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            records = response.json()['response']['data']
            non_terminal = 0
            
            for record in records:
                current_status = record['fieldData'].get(FIELD_MAPPING["status"], "Unknown")
                if current_status not in terminal_states and current_status != "Unknown":
                    non_terminal += 1
            
            if non_terminal > 0:
                tprint(f"📊 Completion check: {non_terminal} stills records still processing")
                return False
        
        tprint(f"✅ Completion check: All records have reached terminal states!")
        return True
        
    except Exception as e:
        tprint(f"❌ Error in completion check: {e}")
        return False

def run_polling_workflow(token, poll_duration=3600, poll_interval=10):
    """Run fast concurrent polling - process ALL records individually every 10 seconds."""
    tprint(f"🚀 Starting fast concurrent stills polling workflow")
    tprint(f"📊 Poll duration: {poll_duration}s, interval: {poll_interval}s")
    tprint(f"📋 Will stop early if all records reach completion or 'Awaiting User Input'")
    
    start_time = time.time()
    poll_count = 0
    
    # Statistics tracking
    poll_stats = {
        "successful": 0,
        "failed": 0,
        "poll_cycles": 0,
        "last_activity": start_time
    }
    
    # Define terminal states that allow early completion
    terminal_states = ["6 - Generating Embeddings", "Awaiting User Input"]
    
    # Check if all records are already complete before starting
    try:
        all_complete = check_all_records_terminal(token, terminal_states)
        if all_complete:
            tprint(f"🎉 All records already completed or awaiting user input - no polling needed!")
            poll_stats["poll_cycles"] = 0
            return poll_stats
    except Exception as e:
        tprint(f"⚠️ Error in initial completion check: {e}")
    
    while time.time() - start_time < poll_duration:
        poll_count += 1
        cycle_start = time.time()
        
        tprint(f"\n=== POLL CYCLE {poll_count} ===")
        
        cycle_successful = 0
        cycle_failed = 0
        
        try:
            # Get ALL stills records that need processing
            response = requests.post(
                config.url("layouts/Stills/_find"),
                headers=config.api_headers(token),
                json={
                    "query": [{"INFO_STILLS_ID": "*"}],
                    "limit": 1000
                },
                verify=False,
                timeout=30
            )
            
            all_tasks = []
            
            # Process stills records
            if response.status_code == 200:
                records = response.json()['response']['data']
                
                for record in records:
                    stills_id = record['fieldData'].get(FIELD_MAPPING["stills_id"])
                    current_status = record['fieldData'].get(FIELD_MAPPING["status"], "Unknown")
                    
                    # Include all statuses except final completion and unknown
                    if stills_id and current_status not in ["6 - Generating Embeddings", "Unknown"]:
                        all_tasks.append({
                            "stills_id": stills_id,
                            "record_id": record['recordId'],
                            "current_status": current_status,
                            "record_data": record['fieldData']
                        })
            
            tprint(f"📊 Found {len(all_tasks)} stills records to process")
            
            # Process ALL records concurrently
            def process_single_task(task):
                """Process a single stills record to its next step."""
                try:
                    return process_stills_task(task, token)
                except Exception as e:
                    tprint(f"❌ Error processing stills {task.get('stills_id', 'unknown')}: {e}")
                    return False
            
            # Run ALL tasks in parallel with high concurrency
            if all_tasks:
                max_workers = min(30, len(all_tasks))  # High concurrency for stills
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(process_single_task, task) for task in all_tasks]
                    
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            if future.result():
                                cycle_successful += 1
                            else:
                                cycle_failed += 1
                        except Exception as e:
                            cycle_failed += 1
            
        except Exception as e:
            tprint(f"❌ Error in poll cycle: {e}")
            cycle_failed += 1
        
        # Update stats
        poll_stats["successful"] += cycle_successful
        poll_stats["failed"] += cycle_failed
        poll_stats["poll_cycles"] += 1
        
        if cycle_successful > 0 or cycle_failed > 0:
            poll_stats["last_activity"] = time.time()
        
        cycle_duration = time.time() - cycle_start
        
        tprint(f"Poll cycle {poll_count} complete ({cycle_duration:.1f}s)")
        tprint(f"Cycle results: {cycle_successful} successful, {cycle_failed} failed")
        
        # Check if all records have reached terminal states
        try:
            all_complete = check_all_records_terminal(token, terminal_states)
            if all_complete:
                tprint(f"🎉 All records have reached completion or 'Awaiting User Input' - stopping polling early!")
                break
        except Exception as e:
            tprint(f"⚠️ Error checking completion status: {e}")
        
        # Sleep until next poll cycle
        time.sleep(poll_interval)
    
    total_duration = time.time() - start_time
    tprint(f"\n=== STILLS POLLING SESSION COMPLETE ===")
    
    # Determine if we stopped early or reached timeout
    if total_duration < poll_duration - poll_interval:
        tprint(f"🎉 Stopped early - all records completed or awaiting user input")
    else:
        tprint(f"⏰ Reached maximum poll duration ({poll_duration}s)")
    
    tprint(f"Total duration: {total_duration:.1f}s")
    tprint(f"Poll cycles: {poll_stats['poll_cycles']}")
    tprint(f"Successful operations: {poll_stats['successful']}")
    tprint(f"Failed operations: {poll_stats['failed']}")
    
    return poll_stats

def process_stills_task(task, token):
    """Process a single stills record to its next step(s) - chain when possible."""
    stills_id = task["stills_id"]
    current_status = task["current_status"]
    record_data = task["record_data"]
    
    tprint(f"🖼️ {stills_id}: {current_status}")
    
    # Track how many steps we complete in this cycle
    steps_completed = 0
    max_steps_per_cycle = 5  # All 5 steps of stills workflow
    
    while steps_completed < max_steps_per_cycle:
        # Special case: Metadata evaluation AFTER step 4 (URL scraping)
        if current_status == "4 - Scraping URL":
            # Get fresh record data to include any scraped content
            try:
                response = requests.get(
                    config.url(f"layouts/Stills/records/{task['record_id']}"),
                    headers=config.api_headers(token),
                    verify=False,
                    timeout=10
                )
                
                if response.status_code == 200:
                    fresh_record_data = response.json()['response']['data'][0]['fieldData']
                else:
                    fresh_record_data = record_data
            except:
                fresh_record_data = record_data
            
            # Evaluate metadata quality (including any scraped content)
            metadata_quality_good = evaluate_metadata_quality(fresh_record_data, token, task["record_id"])
            
            if metadata_quality_good:
                tprint(f"✅ {stills_id}: Metadata quality GOOD after URL step - proceeding to description generation")
                success = run_stills_script(stills_id, "stills_autolog_05_generate_description.py", "5 - Generating Description", "6 - Generating Embeddings", token, task["record_id"])
                if success:
                    steps_completed += 1
                    current_status = "6 - Generating Embeddings"
                    break  # Final step completed
                else:
                    break
            else:
                tprint(f"⚠️ {stills_id}: Metadata quality BAD after URL step - setting to Awaiting User Input")
                update_status(task["record_id"], token, "Awaiting User Input")
                steps_completed += 1
                break  # Handled (waiting for user)
        
        # Special case: Handle user-resumed items
        elif current_status == "Awaiting User Input":
            metadata_quality_good = evaluate_metadata_quality(record_data, token, task["record_id"])
            
            if not metadata_quality_good:
                tprint(f"⏳ {stills_id}: Metadata still insufficient - keeping in Awaiting User Input")
                break
            
            tprint(f"🔄 {stills_id}: Resuming from user input - metadata quality improved")
            success = run_stills_script(stills_id, "stills_autolog_05_generate_description.py", "5 - Generating Description", "6 - Generating Embeddings", token, task["record_id"])
            if success:
                steps_completed += 1
                current_status = "6 - Generating Embeddings"
                break  # Final step completed
            else:
                break
        
        # Standard progression - these can chain together
        else:
            status_map = {
                "0 - Pending File Info": ("stills_autolog_01_get_file_info.py", "1 - File Info Complete"),
                "1 - File Info Complete": ("stills_autolog_02_copy_to_server.py", "2 - Server Copy Complete"),
                "2 - Server Copy Complete": ("stills_autolog_03_parse_metadata.py", "3 - Metadata Parsed"),
                "3 - Metadata Parsed": ("stills_autolog_04_scrape_url.py", "4 - Scraping URL"),
            }
            
            if current_status in status_map:
                script, next_status = status_map[current_status]
                
                # Special handling for URL scraping (step 4) - only run if URL exists
                if current_status == "3 - Metadata Parsed":
                    url = record_data.get(FIELD_MAPPING["url"], '')
                    has_url = bool(url and url.strip())
                    
                    if not has_url:
                        tprint(f"  -> {stills_id}: No URL found - skipping URL scraping step")
                        # Skip URL scraping and proceed directly to metadata evaluation
                        metadata_quality_good = evaluate_metadata_quality(record_data, token, task["record_id"])
                        
                        if metadata_quality_good:
                            tprint(f"✅ {stills_id}: Metadata quality GOOD (no URL) - proceeding to description generation")
                            success = run_stills_script(stills_id, "stills_autolog_05_generate_description.py", "5 - Generating Description", "6 - Generating Embeddings", token, task["record_id"])
                            if success:
                                steps_completed += 1
                                current_status = "6 - Generating Embeddings"
                                break  # Final step completed
                        else:
                            tprint(f"⚠️ {stills_id}: Metadata quality BAD (no URL) - setting to Awaiting User Input")
                            update_status(task["record_id"], token, "Awaiting User Input")
                            steps_completed += 1
                            break  # Handled (waiting for user)
                        continue
                    else:
                        tprint(f"  -> {stills_id}: URL found - proceeding with URL scraping")
                
                success = run_stills_script(stills_id, script, next_status, None, token, task["record_id"])
                if success:
                    steps_completed += 1
                    current_status = next_status
                    tprint(f"⚡ {stills_id}: Chaining to next step → {next_status}")
                    # Continue to next iteration for possible chaining
                    continue
                else:
                    break
            else:
                # No more steps to process
                break
    
    if steps_completed > 1:
        tprint(f"🚀 {stills_id}: Completed {steps_completed} steps in this cycle!")
    
    return steps_completed > 0

def run_stills_script(stills_id, script_name, next_status, final_status, token, record_id):
    """Run a stills script and update status."""
    try:
        # Update status immediately
        update_status(record_id, token, next_status)
        
        # Run script
        success, error_msg = run_single_script(script_name, stills_id, token, 300)
        
        if success:
            tprint(f"✅ {stills_id}: {script_name} completed")
            
            # Update to final status if specified (for step 5)
            if final_status:
                update_status(record_id, token, final_status)
                tprint(f"🔄 {stills_id}: Moved to {final_status}")
            
            return True
        else:
            tprint(f"❌ {stills_id}: {script_name} failed: {error_msg}")
            return False
            
    except Exception as e:
        tprint(f"❌ {stills_id}: Exception in {script_name}: {e}")
        return False

if __name__ == "__main__":
    try:
        token = config.get_token()
        
        # Run polling workflow
        # Default: 1 hour duration, 10-second intervals for fast response
        poll_duration = int(os.getenv('POLL_DURATION', 3600))  # 1 hour default
        poll_interval = int(os.getenv('POLL_INTERVAL', 10))    # 10 seconds default
        
        results = run_polling_workflow(token, poll_duration, poll_interval)
        
        # Exit successfully
        tprint(f"✅ Stills polling workflow completed successfully")
        sys.exit(0)
        
    except KeyboardInterrupt:
        tprint(f"🛑 Stills polling workflow interrupted by user")
        sys.exit(0)
    except Exception as e:
        tprint(f"❌ Critical error in stills polling workflow: {e}")
        traceback.print_exc()
        sys.exit(1) 