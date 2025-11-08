#!/usr/bin/env python3
"""
LF AutoLog Poller - Step 3: Assess and Sample Frames

Independent polling loop for intelligent frame sampling and assessment.
Handles both normal flow (→ Awaiting User Input) and Force Resume (→ Continue to Gemini).
Polls every 30 seconds (slower process, less urgent).
"""

import subprocess
import sys
import time
from pathlib import Path
import requests
from datetime import datetime
import warnings
import concurrent.futures
import os

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Explicitly load .env file
from dotenv import load_dotenv
project_root = Path(__file__).resolve().parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

import config

# Step configuration - handles TWO input statuses
STEP_CONFIG = {
    "name": "Step 3: Assess and Sample Frames",
    "status": ["2 - Thumbnails Complete", "Force Resume"],  # Multiple input statuses
    "next_status_map": {
        "2 - Thumbnails Complete": "Awaiting User Input",  # Normal flow stops
        "Force Resume": "3 - Creating Frames"  # Force Resume continues
    },
    "script": "lf_autolog_03_assess_and_sample.py",
    "timeout": 600,
    "max_workers": 6,
    "poll_interval": 30  # Slower process, less urgent
}

JOBS_DIR = Path(__file__).resolve().parent
FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "status": "AutoLog_Status"
}

def tprint(message):
    """Print with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}", flush=True)


def find_lf_records(token, status_list):
    """Find LF footage records with specified status(es)."""
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
                        "current_status": status  # Preserve which status it came from
                    })
            
        except Exception as e:
            tprint(f"❌ Error finding records with status '{status}': {e}")
            continue
    
    return all_records


def update_status(record_id, token, new_status):
    """Update record status."""
    try:
        payload = {"fieldData": {FIELD_MAPPING["status"]: new_status}}
        response = requests.patch(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            json=payload,
            verify=False,
            timeout=30
        )
        response.raise_for_status()
        return True
    except:
        return False


def run_script(footage_id, token):
    """Run the script for a footage ID."""
    script_path = JOBS_DIR / STEP_CONFIG["script"]
    
    try:
        result = subprocess.run(
            ["python3", str(script_path), footage_id, token],
            capture_output=True,
            text=True,
            timeout=STEP_CONFIG["timeout"]
        )
        return result.returncode == 0
    except:
        return False


def process_single_record(record, token):
    """Process a single record."""
    footage_id = record["footage_id"]
    record_id = record["record_id"]
    current_status = record["current_status"]
    
    try:
        # Determine next status based on where record came from
        next_status = STEP_CONFIG["next_status_map"][current_status]
        
        # Special handling for Force Resume
        if current_status == "Force Resume":
            tprint(f"  -> 🚀 FORCE RESUME: {footage_id}")
        
        # Run script FIRST (status unchanged while working)
        success = run_script(footage_id, token)
        
        if success:
            # Only update status if work completed successfully
            if update_status(record_id, token, next_status):
                status_msg = "→ Awaiting Input" if next_status == "Awaiting User Input" else "→ Continuing"
                tprint(f"  -> ✅ {footage_id}: Completed {status_msg}")
            else:
                tprint(f"  -> ⚠️ {footage_id}: Work done but status update failed")
        else:
            # Record stays at current status for retry
            tprint(f"  -> ❌ {footage_id}: Failed")
        
        return success
        
    except Exception as e:
        tprint(f"  -> ❌ {footage_id}: {e}")
        return False


def main():
    """Main polling loop."""
    tprint(f"🚀 Starting {STEP_CONFIG['name']} Poller")
    tprint(f"📊 Polling every {STEP_CONFIG['poll_interval']}s, max_workers={STEP_CONFIG['max_workers']}")
    tprint(f"🔀 Handles: Normal flow + Force Resume")
    
    try:
        token = config.get_token()
        
        while True:
            # Find records with either status
            records = find_lf_records(token, STEP_CONFIG["status"])
            
            if records:
                normal_count = len([r for r in records if r["current_status"] == "2 - Thumbnails Complete"])
                resume_count = len([r for r in records if r["current_status"] == "Force Resume"])
                tprint(f"🔍 Found {len(records)} LF records ({normal_count} normal, {resume_count} force resume)")
                
                # Process in parallel
                with concurrent.futures.ThreadPoolExecutor(max_workers=STEP_CONFIG["max_workers"]) as executor:
                    futures = {
                        executor.submit(process_single_record, record, token): record
                        for record in records
                    }
                    
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            tprint(f"  -> ❌ Error: {e}")
            
            # Wait for next poll
            time.sleep(STEP_CONFIG["poll_interval"])
            
    except KeyboardInterrupt:
        tprint(f"🛑 {STEP_CONFIG['name']} Poller stopped")
    except Exception as e:
        tprint(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

