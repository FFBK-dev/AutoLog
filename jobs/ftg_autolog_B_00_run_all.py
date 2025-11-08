#!/usr/bin/env python3
"""
Footage AI Processing Flow - Part B (Queued & Complex)

Discovers footage at "3 - Ready for AI" and queues for processing:
1. Assess & Sample Frames
2. Gemini Multi-Image Analysis
3. Create Frame Records
4. Audio Transcription (if audio present)

Requires user prompt before processing. Ends at "7 - Avid Description".
"""

import sys
import warnings
import requests
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from jobs.ftg_autolog_B_queue_jobs import queue_ftg_ai_batch

__ARGS__ = []  # No arguments - finds ready items automatically

FIELD_MAPPING = {
    "status": "AutoLog_Status",
    "footage_id": "INFO_FTG_ID"
}

def find_ready_for_ai(token):
    """Find all footage records at '3 - Ready for AI' status."""
    print("🔍 Searching for items ready for AI processing...")
    
    query = {
        "query": [{
            FIELD_MAPPING["status"]: "3 - Ready for AI"
        }],
        "limit": 100
    }
    
    try:
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
            footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"], '')
            if footage_id:
                footage_ids.append(footage_id)
        
        if footage_ids:
            print(f"✅ Found {len(footage_ids)} items ready for AI: {', '.join(footage_ids[:10])}")
            if len(footage_ids) > 10:
                print(f"   ... and {len(footage_ids) - 10} more")
        
        return footage_ids
        
    except Exception as e:
        print(f"❌ Error finding ready items: {e}")
        return []


if __name__ == "__main__":
    try:
        print("🚀 Footage AI Processing Flow - Part B\n")
        
        # Get FileMaker token
        token = config.get_token()
        
        # Find items ready for AI
        footage_ids = find_ready_for_ai(token)
        
        if not footage_ids:
            print("\n✅ No items ready for AI processing\n")
            sys.exit(0)
        
        # Queue all items in batch
        print(f"\n📥 Queueing {len(footage_ids)} items for AI processing...")
        job_ids = queue_ftg_ai_batch(footage_ids, token)
        
        print(f"   ✅ Queued {len(job_ids)} items\n")
        print(f"{'='*60}")
        print(f"✅ Successfully queued {len(job_ids)} items for AI processing!")
        print(f"{'='*60}\n")
        print(f"💡 Monitor: ./workers/start_ftg_ai_workers.sh status\n")
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

