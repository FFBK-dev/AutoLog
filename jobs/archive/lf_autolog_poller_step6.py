#!/usr/bin/env python3
"""
LF AutoLog Poller - Step 6: Audio Transcription Mapping

Independent polling loop for mapping audio transcriptions to frame records.
Polls every 20 seconds (background process, less urgent).
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

# Step configuration
STEP_CONFIG = {
    "name": "Step 6: Audio Transcription Mapping",
    "status": "6 - Generating Description",
    "next_status": "7 - Avid Description",  # Final status for LF workflow
    "script": "lf_autolog_06_transcribe_audio.py",
    "timeout": 300,
    "max_workers": 4,
    "poll_interval": 20  # Background process, less urgent
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


def find_lf_records(token, status):
    """Find LF footage records with specified status."""
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
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        lf_records = []
        for record in records:
            footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
            if footage_id and footage_id.startswith("LF"):
                lf_records.append({
                    "footage_id": footage_id,
                    "record_id": record['recordId'],
                    "current_status": status
                })
        
        return lf_records
        
    except Exception as e:
        tprint(f"❌ Error finding records: {e}")
        return []


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
    
    try:
        # Run script FIRST (status unchanged while working)
        success = run_script(footage_id, token)
        
        if success:
            # Only update status if work completed successfully (final status)
            if update_status(record_id, token, STEP_CONFIG["next_status"]):
                tprint(f"  -> ✅ {footage_id}: Workflow completed!")
            else:
                tprint(f"  -> ⚠️ {footage_id}: Audio mapped but status update failed")
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
    tprint(f"🎯 Final step: Records move to '7 - Avid Description'")
    
    try:
        token = config.get_token()
        
        while True:
            # Find records
            records = find_lf_records(token, STEP_CONFIG["status"])
            
            if records:
                tprint(f"🔍 Found {len(records)} LF records ready for audio mapping")
                
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

