#!/usr/bin/env python3
import sys
import warnings
import requests
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from jobs.lf_queue_jobs import queue_lf_batch, queue_force_resume_batch

__ARGS__ = []  # No arguments - finds pending items automatically

FIELD_MAPPING = {
    "status": "AutoLog_Status",
    "footage_id": "INFO_FTG_ID"
}

def find_pending_lf_items(token):
    """Find all LF records at '0 - Pending File Info' status."""
    print("🔍 Searching for pending LF items (0 - Pending File Info)...")
    
    query = {
        "query": [{
            FIELD_MAPPING["status"]: "0 - Pending File Info",
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
    
    if footage_ids:
        print(f"✅ Found {len(footage_ids)} pending items: {', '.join(footage_ids)}")
    
    return footage_ids

def find_force_resume_items(token):
    """Find all LF records at 'Force Resume' status."""
    print("🔍 Searching for Force Resume LF items...")
    
    query = {
        "query": [{
            FIELD_MAPPING["status"]: "Force Resume",
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
    
    if footage_ids:
        print(f"🔄 Found {len(footage_ids)} Force Resume items: {', '.join(footage_ids)}")
    
    return footage_ids

if __name__ == "__main__":
    try:
        print("🚀 LF AutoLog Queue System - Finding Pending Items\n")
        
        # Get FileMaker token
        token = config.get_token()
        
        # Find pending items (start from Step 1)
        pending_ids = find_pending_lf_items(token)
        
        # Find force resume items (restart from Step 3)
        force_resume_ids = find_force_resume_items(token)
        
        if not pending_ids and not force_resume_ids:
            print("\n✅ No items to queue")
            sys.exit(0)
        
        print("")  # Blank line before queueing
        
        # Queue pending items at Step 1
        if pending_ids:
            print(f"📥 Queueing {len(pending_ids)} pending items at Step 1...")
            job_ids_pending = queue_lf_batch(pending_ids, token)
            print(f"   ✅ Queued {len(job_ids_pending)} items")
        
        # Queue force resume items at Step 3
        if force_resume_ids:
            print(f"🔄 Queueing {len(force_resume_ids)} Force Resume items at Step 3...")
            job_ids_resume = queue_force_resume_batch(force_resume_ids, token)
            print(f"   ✅ Queued {len(job_ids_resume)} items")
        
        total_queued = len(pending_ids) + len(force_resume_ids)
        print(f"\n✅ Successfully queued {total_queued} items total!")
        print(f"\n💡 Monitor: ./workers/start_lf_workers.sh status\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

