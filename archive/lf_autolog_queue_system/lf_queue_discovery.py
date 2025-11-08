#!/usr/bin/env python3
"""
LF AutoLog Queue Discovery Poller (Optional)

This script continuously polls FileMaker for LF records at "0 - Pending File Info"
and automatically queues them for processing via the Redis job queue.

Usage:
  python3 lf_queue_discovery.py

Or start via API:
  curl -X POST http://localhost:8081/run/lf_discovery -H "X-API-Key: YOUR_KEY"
"""

import sys
import os
import time
import warnings
from pathlib import Path
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Setup paths
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Import queue jobs
from jobs.lf_queue_jobs import q_step1, job_step1_file_info

# Configuration
POLL_INTERVAL = 30  # Check every 30 seconds
MAX_BATCH_SIZE = 20  # Queue up to 20 items per poll

def tprint(message):
    """Thread-safe print with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def find_pending_lf_items(token):
    """
    Find all LF records at "0 - Pending File Info" status.
    
    Returns:
        List of footage_ids ready to be queued
    """
    import requests
    
    try:
        query = {
            "query": [{
                config.FIELD_MAPPING.get("status", "AutoLog_Status"): "0 - Pending File Info",
                config.FIELD_MAPPING.get("footage_id", "INFO_FTG_ID"): "LF*"
            }],
            "limit": MAX_BATCH_SIZE
        }
        
        response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 404:
            # No records found
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        # Extract footage IDs (filter for LF prefix just in case)
        footage_ids = []
        for record in records:
            footage_id = record['fieldData'].get(
                config.FIELD_MAPPING.get("footage_id", "INFO_FTG_ID"), ""
            )
            if footage_id.startswith("LF"):
                footage_ids.append(footage_id)
        
        return footage_ids
        
    except Exception as e:
        tprint(f"⚠️ Error finding pending items: {e}")
        return []

def queue_items(footage_ids, token):
    """
    Queue items for processing.
    
    Returns:
        Number of items successfully queued
    """
    queued_count = 0
    
    for footage_id in footage_ids:
        try:
            job = q_step1.enqueue(job_step1_file_info, footage_id, token)
            tprint(f"📥 Queued: {footage_id} → Job ID: {job.id}")
            queued_count += 1
        except Exception as e:
            tprint(f"❌ Failed to queue {footage_id}: {e}")
    
    return queued_count

def run_discovery_loop():
    """
    Main discovery loop.
    Continuously polls FileMaker and queues new items.
    """
    tprint("🚀 LF AutoLog Discovery Poller Started")
    tprint(f"📋 Polling interval: {POLL_INTERVAL}s")
    tprint(f"📦 Max batch size: {MAX_BATCH_SIZE}")
    tprint("")
    
    # Get initial token
    token = config.get_token()
    token_refresh_count = 0
    
    try:
        while True:
            try:
                # Refresh token every 100 iterations (~50 minutes)
                if token_refresh_count >= 100:
                    tprint("🔄 Refreshing FileMaker token...")
                    token = config.get_token()
                    token_refresh_count = 0
                
                # Find pending items
                footage_ids = find_pending_lf_items(token)
                
                if footage_ids:
                    tprint(f"🔍 Found {len(footage_ids)} pending LF items")
                    queued_count = queue_items(footage_ids, token)
                    
                    if queued_count > 0:
                        tprint(f"✅ Successfully queued {queued_count}/{len(footage_ids)} items")
                        tprint(f"📊 Current queue depth: {len(q_step1)}")
                    else:
                        tprint(f"⚠️ Failed to queue any items (check logs)")
                else:
                    # No items found - silent operation
                    pass
                
                token_refresh_count += 1
                
            except KeyboardInterrupt:
                raise  # Re-raise to exit cleanly
            except Exception as e:
                tprint(f"❌ Error in discovery loop: {e}")
                # Try to refresh token on error
                try:
                    token = config.get_token()
                    token_refresh_count = 0
                except:
                    pass
            
            # Wait before next poll
            time.sleep(POLL_INTERVAL)
    
    except KeyboardInterrupt:
        tprint("")
        tprint("⏹️ Discovery poller stopped by user")
        sys.exit(0)

if __name__ == "__main__":
    try:
        run_discovery_loop()
    except Exception as e:
        tprint(f"❌ Critical error: {e}")
        sys.exit(1)

