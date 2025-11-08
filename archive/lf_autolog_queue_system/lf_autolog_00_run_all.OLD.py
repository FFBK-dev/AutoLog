#!/usr/bin/env python3
"""
LF AutoLog Workflow Controller (Gemini Experiment)

Polling-based workflow specifically for LF (Live Footage) items using Gemini API.
Processes records independently through experimental multi-image analysis pipeline.
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
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Explicitly load .env file from project root (fixes subprocess .env loading)
from dotenv import load_dotenv
project_root = Path(__file__).resolve().parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    logging.warning(f"⚠️ .env file not found at {env_path}")

import config

def tprint(message):
    """Print with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}", flush=True)

# No arguments - polls for LF items
__ARGS__ = []

JOBS_DIR = Path(__file__).resolve().parent

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "status": "AutoLog_Status"
}

# LF-specific polling targets (uses same status names as footage_autolog for compatibility)
# Skips "4 - Scraping URL" since Gemini workflow doesn't need URL scraping
POLLING_TARGETS = [
    {
        "name": "Step 1: Get File Info",
        "status": "0 - Pending File Info",
        "next_status": "1 - File Info Complete",
        "script": "lf_autolog_01_get_file_info.py",
        "timeout": 300,
        "max_workers": 8  # Increased for rapid imports
    },
    {
        "name": "Step 2: Generate Parent Thumbnail",
        "status": "1 - File Info Complete",
        "next_status": "2 - Thumbnails Complete",
        "script": "lf_autolog_02_generate_thumbnails.py",
        "timeout": 300,
        "max_workers": 8  # Increased for rapid imports
    },
    {
        "name": "Step 3: Assess and Sample Frames",
        "status": "2 - Thumbnails Complete",
        "next_status": "Awaiting User Input",  # Normal flow STOPS here for manual review
        "script": "lf_autolog_03_assess_and_sample.py",
        "timeout": 600,  # Longer for scene detection
        "max_workers": 6  # Increased to clear backlog faster
    },
    {
        "name": "Step 3 (Force Resume): Assess and Sample Frames",
        "status": "Force Resume",  # Force Resume reprocesses from here
        "next_status": "3 - Creating Frames",  # But CONTINUES to Gemini (no halt)
        "script": "lf_autolog_03_assess_and_sample.py",
        "timeout": 600,
        "max_workers": 6  # Increased to clear backlog faster
    },
    # NOTE: Steps 4-6 only run if user manually changes status from "Awaiting User Input" OR uses Force Resume
    {
        "name": "Step 4: Gemini Multi-Image Analysis",
        "status": "3 - Creating Frames",  # Manual status change required
        "next_status": "5 - Processing Frame Info",  # Skip "4 - Scraping URL"
        "script": "lf_autolog_04_gemini_analysis.py",
        "timeout": 300,  # Gemini API call
        "max_workers": 2  # Conservative for API limits
    },
    {
        "name": "Step 5: Create Frame Records",
        "status": "5 - Processing Frame Info",
        "next_status": "6 - Generating Description",  # Use recognized status
        "script": "lf_autolog_05_create_frames.py",
        "timeout": 600,
        "max_workers": 3
    },
    {
        "name": "Step 6: Audio Transcription",
        "status": "6 - Generating Description",
        "next_status": "7 - Avid Description",  # Final status where workflow stops
        "script": "lf_autolog_06_transcribe_audio.py",
        "timeout": 300,
        "max_workers": 4
    }
]


def find_lf_records_by_status(token, status_list):
    """Find LF footage records with specified status(es)."""
    if isinstance(status_list, str):
        status_list = [status_list]
    
    all_records = []
    
    for status in status_list:
        try:
            # Query for all records with this status
            # We'll filter for LF items in Python (FileMaker Data API doesn't support wildcards)
            query = {
                "query": [{
                    FIELD_MAPPING["status"]: status
                }],
                "limit": 100
            }
            
            response = requests.post(
                config.url("layouts/FOOTAGE/_find"),
                headers=config.api_headers(token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 404:
                continue
            
            response.raise_for_status()
            records = response.json()['response']['data']
            
            for record in records:
                footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
                if footage_id and footage_id.startswith("LF"):
                    all_records.append({
                        "footage_id": footage_id,
                        "record_id": record['recordId'],
                        "current_status": status,
                        "record_data": record['fieldData']
                    })
        
        except Exception as e:
            tprint(f"❌ Error finding LF records with status '{status}': {e}")
            continue
    
    return all_records


def update_status(record_id, token, new_status, max_retries=3):
    """Update record status with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            payload = {"fieldData": {FIELD_MAPPING["status"]: new_status}}
            response = requests.patch(
                config.url(f"layouts/FOOTAGE/records/{record_id}"),
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


def run_single_script(script_name, footage_id, token, timeout=300):
    """Run a single script for a footage ID."""
    script_path = JOBS_DIR / script_name
    
    if not script_path.exists():
        return False, f"Script not found: {script_name}"
    
    try:
        result = subprocess.run(
            ["python3", str(script_path), footage_id, token],
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


def process_polling_target(target, token):
    """Process all records for a specific polling target."""
    target_name = target["name"]
    source_status = target["status"]
    next_status = target["next_status"]
    script_name = target["script"]
    timeout = target.get("timeout", 300)
    max_workers = target.get("max_workers", 3)
    
    tprint(f"🔍 Polling: {target_name}")
    
    # Find LF records ready for this step
    records = find_lf_records_by_status(token, source_status)
    
    if not records:
        tprint(f"  -> No LF records found")
        return 0
    
    tprint(f"  -> Found {len(records)} LF records to process")
    
    # Process records in parallel
    def process_single_record(record):
        footage_id = record["footage_id"]
        record_id = record["record_id"]
        current_status = record["current_status"]
        
        try:
            # Special handling for Force Resume
            if current_status == "Force Resume":
                tprint(f"  -> 🚀 FORCE RESUME: {footage_id}")
                
                # Write to AI_DevConsole to log Force Resume
                try:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    console_msg = f"[{timestamp}] FORCE RESUME triggered by user - regenerating Gemini analysis and all frame data"
                    
                    payload = {"fieldData": {"AI_DevConsole": console_msg}}
                    requests.patch(
                        config.url(f"layouts/FOOTAGE/records/{record_id}"),
                        headers=config.api_headers(token),
                        json=payload,
                        verify=False,
                        timeout=30
                    )
                    tprint(f"  -> {footage_id}: Logged Force Resume to AI_DevConsole")
                except Exception as e:
                    tprint(f"  -> {footage_id}: Warning - could not write to dev console: {e}")
            else:
                tprint(f"  -> Starting {footage_id}")
            
            # Update status to processing state
            if not update_status(record_id, token, next_status):
                tprint(f"  -> {footage_id}: Failed to update status")
                return False
            
            # Run the script
            success, error_msg = run_single_script(script_name, footage_id, token, timeout)
            
            if success:
                tprint(f"  -> ✅ {footage_id}: Completed")
                return True
            else:
                tprint(f"  -> ❌ {footage_id}: {error_msg}")
                return False
                
        except Exception as e:
            tprint(f"  -> ❌ {footage_id}: Exception - {e}")
            return False
    
    # Use ThreadPoolExecutor for parallel processing
    actual_max_workers = min(max_workers, len(records))
    successful = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        futures = [executor.submit(process_single_record, record) for record in records]
        
        for future in concurrent.futures.as_completed(futures):
            try:
                if future.result():
                    successful += 1
            except Exception as e:
                tprint(f"  -> Future exception: {e}")
    
    tprint(f"📊 {target_name}: {successful}/{len(records)} completed")
    return successful


def run_polling_workflow(token, poll_duration=3600, poll_interval=30):
    """Run polling workflow for LF items."""
    tprint(f"🚀 Starting LF AutoLog Gemini Experiment Workflow")
    tprint(f"📊 Poll duration: {poll_duration}s, interval: {poll_interval}s")
    tprint(f"🔬 Processing LF items only with Gemini multi-image analysis")
    
    start_time = time.time()
    poll_count = 0
    total_successful = 0
    total_failed = 0
    
    # Terminal states for LF workflow (matches footage_autolog terminal states)
    terminal_states = [
        "7 - Avid Description",
        "8 - Generating Embeddings",
        "9 - Applying Tags",
        "10 - Complete",
        "Awaiting User Input"
    ]
    
    while time.time() - start_time < poll_duration:
        poll_count += 1
        cycle_start = time.time()
        
        tprint(f"\n=== POLL CYCLE {poll_count} ===")
        
        cycle_successful = 0
        
        try:
            # Process each step in sequence
            for target in POLLING_TARGETS:
                successful = process_polling_target(target, token)
                cycle_successful += successful
            
            total_successful += cycle_successful
            
        except Exception as e:
            tprint(f"❌ Error in poll cycle: {e}")
            total_failed += 1
        
        cycle_duration = time.time() - cycle_start
        tprint(f"📊 Cycle {poll_count}: {cycle_successful} completed ({cycle_duration:.1f}s)")
        
        # Check if all LF records have reached terminal states
        try:
            pending_count = 0
            for target in POLLING_TARGETS:
                records = find_lf_records_by_status(token, target["status"])
                pending_count += len(records)
            
            if pending_count == 0:
                tprint(f"🎉 No more LF records to process - stopping early!")
                break
        except:
            pass
        
        # Sleep until next poll cycle
        time.sleep(poll_interval)
    
    total_duration = time.time() - start_time
    tprint(f"\n=== LF AUTOLOG SESSION COMPLETE ===")
    tprint(f"Total duration: {total_duration:.1f}s")
    tprint(f"Poll cycles: {poll_count}")
    tprint(f"Successful operations: {total_successful}")
    tprint(f"Failed operations: {total_failed}")
    
    return {
        "successful": total_successful,
        "failed": total_failed,
        "poll_cycles": poll_count
    }


if __name__ == "__main__":
    try:
        # Mount required volumes
        tprint(f"🔧 Mounting network volumes...")
        
        try:
            if config.mount_volume("footage"):
                tprint(f"✅ Footage volume mounted")
            else:
                tprint(f"⚠️ Failed to mount footage volume")
        except Exception as e:
            tprint(f"❌ Error mounting volume: {e}")
        
        token = config.get_token()
        
        # Run polling workflow
        poll_duration = int(os.getenv('POLL_DURATION', 3600))  # 1 hour default
        poll_interval = int(os.getenv('POLL_INTERVAL', 10))    # 10 seconds for faster response
        
        results = run_polling_workflow(token, poll_duration, poll_interval)
        
        tprint(f"✅ LF AutoLog workflow completed successfully")
        sys.exit(0)
        
    except KeyboardInterrupt:
        tprint(f"🛑 LF AutoLog workflow interrupted by user")
        sys.exit(0)
    except Exception as e:
        tprint(f"❌ Critical error in LF AutoLog workflow: {e}")
        traceback.print_exc()
        sys.exit(1)

