#!/usr/bin/env python3
"""
LF AutoLog Recovery Script

Finds items stuck at intermediate statuses and re-queues them at the appropriate step.
Useful for recovering from system issues or race conditions.

Usage:
    python3 lf_autolog_recovery.py
"""

import sys
import warnings
import requests
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from jobs.lf_queue_jobs import (
    q_step2, job_step2_thumbnail,
    q_step3, job_step3_assess,
    q_step4, job_step4_gemini,
    q_step5, job_step5_create_frames,
    q_step6, job_step6_transcribe_audio
)

FIELD_MAPPING = {
    "status": "AutoLog_Status",
    "footage_id": "INFO_FTG_ID"
}

# Map statuses to their next queue/job
RECOVERY_MAP = {
    "1 - File Info Complete": (q_step2, job_step2_thumbnail, "Step 2: Thumbnails"),
    "2 - Thumbnails Complete": (q_step3, job_step3_assess, "Step 3: Assess & Sample"),
    "3 - Creating Frames": (q_step4, job_step4_gemini, "Step 4: Gemini Analysis"),
    "5 - Processing Frame Info": (q_step5, job_step5_create_frames, "Step 5: Create Frames"),
    "6 - Generating Description": (q_step6, job_step6_transcribe_audio, "Step 6: Audio Transcription")
}

def find_stuck_items(token, status):
    """Find all LF items stuck at a given status."""
    try:
        query = {
            "query": [{
                FIELD_MAPPING["status"]: status,
                FIELD_MAPPING["footage_id"]: "LF*"
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
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        # Extract footage IDs
        footage_ids = []
        for record in records:
            footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"], "")
            if footage_id.startswith("LF"):
                footage_ids.append(footage_id)
        
        return footage_ids
        
    except Exception as e:
        print(f"  ❌ Error finding items at '{status}': {e}")
        return []

def queue_items(queue, job_func, footage_ids, token, step_name):
    """Queue items at a specific step."""
    queued = 0
    for footage_id in footage_ids:
        try:
            queue.enqueue(job_func, footage_id, token)
            print(f"    ✅ Queued {footage_id} at {step_name}")
            queued += 1
        except Exception as e:
            print(f"    ❌ Failed to queue {footage_id}: {e}")
    
    return queued

if __name__ == "__main__":
    try:
        print("🔧 LF AutoLog Recovery - Finding Stuck Items\n")
        
        token = config.get_token()
        
        total_recovered = 0
        
        # Check each intermediate status
        for status, (queue, job_func, step_name) in RECOVERY_MAP.items():
            print(f"🔍 Checking for items stuck at: {status}")
            
            stuck_ids = find_stuck_items(token, status)
            
            if stuck_ids:
                print(f"  📋 Found {len(stuck_ids)} stuck items")
                queued = queue_items(queue, job_func, stuck_ids, token, step_name)
                total_recovered += queued
                print(f"  ✅ Re-queued {queued}/{len(stuck_ids)} items")
            else:
                print(f"  ✓ No stuck items")
            
            print()
        
        if total_recovered > 0:
            print(f"✅ Recovery complete! Re-queued {total_recovered} items total\n")
            print(f"💡 Monitor: ./workers/start_lf_workers.sh status")
        else:
            print(f"✅ No stuck items found - all queues are healthy!\n")
        
    except Exception as e:
        print(f"❌ Recovery error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

