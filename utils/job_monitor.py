#!/usr/bin/env python3
"""
Job Monitor Utility

This script helps monitor and recover stuck jobs in the FileMaker automation system.
It provides tools to:
1. Check for stuck jobs
2. Reset stuck items
3. Monitor job progress
4. Force retry failed items
"""

import sys
import requests
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def get_api_status():
    """Get current API status and job information."""
    try:
        response = requests.get("http://localhost:8081/status", timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ API status request failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Could not connect to API: {e}")
        return None

def get_job_info(job_id):
    """Get detailed information about a specific job."""
    try:
        response = requests.get(f"http://localhost:8081/job/{job_id}", timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Job info request failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Could not get job info: {e}")
        return None

def find_stuck_footage_items(token):
    """Find footage items that appear to be stuck in processing."""
    try:
        print("🔍 Searching for potentially stuck footage items...")
        
        # Look for items stuck in processing states
        stuck_statuses = [
            "5 - Processing Frame Info",
            "6 - Generating Description"
        ]
        
        stuck_items = []
        
        for status in stuck_statuses:
            print(f"  -> Checking items with status: {status}")
            
            query = {
                "query": [{"AutoLog_Status": status}],
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
                print(f"    -> No items found with status: {status}")
                continue
            
            response.raise_for_status()
            records = response.json()['response']['data']
            
            for record in records:
                footage_id = record['fieldData'].get('INFO_FTG_ID')
                record_id = record['recordId']
                dev_console = record['fieldData'].get('AI_DevConsole', '')
                
                # Check if there's a recent error or if it's been stuck for a while
                is_stuck = False
                if dev_console:
                    # Look for timeout or error messages in the last hour
                    if any(keyword in dev_console.lower() for keyword in ['timeout', 'error', 'failed']):
                        is_stuck = True
                
                if is_stuck:
                    stuck_items.append({
                        'footage_id': footage_id,
                        'record_id': record_id,
                        'status': status,
                        'dev_console': dev_console
                    })
        
        return stuck_items
        
    except Exception as e:
        print(f"❌ Error finding stuck items: {e}")
        return []

def reset_stuck_item(footage_id, record_id, token, target_status="5 - Processing Frame Info"):
    """Reset a stuck item to a specific status."""
    try:
        print(f"🔄 Resetting {footage_id} to status: {target_status}")
        
        # Update the footage status
        payload = {"fieldData": {"AutoLog_Status": target_status}}
        response = requests.patch(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            json=payload,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"  -> ✅ Successfully reset {footage_id}")
            
            # If resetting to frame processing, also reset frame statuses
            if target_status == "5 - Processing Frame Info":
                print(f"  -> 🔄 Resetting frame statuses for {footage_id}...")
                
                # Find all frame records for this footage
                frame_query = {
                    "query": [{"FRAMES_ParentID": footage_id}],
                    "limit": 1000
                }
                
                frame_response = requests.post(
                    config.url("layouts/FRAMES/_find"),
                    headers=config.api_headers(token),
                    json=frame_query,
                    verify=False,
                    timeout=30
                )
                
                if frame_response.status_code == 200:
                    frame_records = frame_response.json()['response']['data']
                    
                    for frame_record in frame_records:
                        frame_record_id = frame_record['recordId']
                        frame_payload = {"fieldData": {"FRAMES_Status": "2 - Thumbnail Complete"}}
                        
                        frame_update_response = requests.patch(
                            config.url(f"layouts/FRAMES/records/{frame_record_id}"),
                            headers=config.api_headers(token),
                            json=frame_payload,
                            verify=False,
                            timeout=30
                        )
                        
                        if frame_update_response.status_code != 200:
                            print(f"    -> ⚠️ Warning: Failed to reset frame {frame_record_id}")
                    
                    print(f"  -> ✅ Reset {len(frame_records)} frame records")
            
            return True
        else:
            print(f"  -> ❌ Failed to reset {footage_id}: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  -> ❌ Error resetting {footage_id}: {e}")
        return False

def retry_failed_item(footage_id, token):
    """Retry processing a failed item."""
    try:
        print(f"🔄 Retrying processing for {footage_id}")
        
        # Submit the job to the API
        payload = {"footage_id": footage_id}
        response = requests.post(
            "http://localhost:8081/run/footage_autolog_00_run_all",
            json=payload,
            headers={"X-API-Key": "supersecret"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            print(f"  -> ✅ Job submitted successfully: {job_id}")
            return job_id
        else:
            print(f"  -> ❌ Failed to submit job: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"  -> ❌ Error retrying {footage_id}: {e}")
        return None

def monitor_job_progress(job_id, max_wait_time=300):
    """Monitor a job's progress in real-time."""
    print(f"📊 Monitoring job progress: {job_id}")
    print(f"⏱️ Will monitor for up to {max_wait_time} seconds")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait_time:
        job_info = get_job_info(job_id)
        
        if not job_info:
            print("  -> ❌ Could not get job info")
            time.sleep(10)
            continue
        
        current_status = job_info.get('status', 'unknown')
        
        if current_status != last_status:
            print(f"  -> Status: {current_status}")
            last_status = current_status
        
        if current_status in ['completed', 'failed']:
            print(f"  -> Job finished with status: {current_status}")
            return current_status
        
        # Show progress if available
        progress = job_info.get('progress', {})
        if progress:
            is_stuck = progress.get('is_stuck', False)
            if is_stuck:
                print(f"  -> ⚠️ Job appears to be stuck")
            
            recent_progress = progress.get('recent_progress', [])
            if recent_progress:
                latest = recent_progress[-1]
                print(f"  -> Latest: {latest.get('line', 'No output')}")
        
        time.sleep(10)
    
    print(f"  -> ⏱️ Monitoring timeout reached")
    return 'timeout'

def main():
    """Main monitoring and recovery interface."""
    print("🔧 FileMaker Automation Job Monitor")
    print("=" * 50)
    
    # Get API status
    api_status = get_api_status()
    if api_status:
        print(f"📊 API Status:")
        print(f"  -> Total submitted: {api_status.get('total_submitted', 0)}")
        print(f"  -> Total completed: {api_status.get('total_completed', 0)}")
        print(f"  -> Currently running: {api_status.get('currently_running', 0)}")
        print(f"  -> Stuck jobs: {api_status.get('stuck_jobs', 0)}")
        
        if api_status.get('stuck_jobs', 0) > 0:
            print(f"⚠️ Found {api_status.get('stuck_jobs')} stuck jobs!")
    else:
        print("❌ Could not get API status")
        return
    
    print()
    
    # Get token for FileMaker operations
    try:
        token = config.get_token()
    except Exception as e:
        print(f"❌ Could not get FileMaker token: {e}")
        return
    
    # Find stuck items
    stuck_items = find_stuck_footage_items(token)
    
    if stuck_items:
        print(f"🔍 Found {len(stuck_items)} potentially stuck items:")
        for i, item in enumerate(stuck_items[:10]):  # Show first 10
            print(f"  {i+1}. {item['footage_id']} - {item['status']}")
            if item['dev_console']:
                console_preview = item['dev_console'][:100] + "..." if len(item['dev_console']) > 100 else item['dev_console']
                print(f"     Console: {console_preview}")
        
        if len(stuck_items) > 10:
            print(f"     ... and {len(stuck_items) - 10} more items")
        
        print()
        
        # Interactive recovery
        while True:
            print("Options:")
            print("1. Reset all stuck items to '5 - Processing Frame Info'")
            print("2. Reset all stuck items to '0 - Pending File Info' (full restart)")
            print("3. Retry specific item")
            print("4. Monitor specific job")
            print("5. Exit")
            
            choice = input("\nEnter your choice (1-5): ").strip()
            
            if choice == "1":
                print("\n🔄 Resetting all stuck items to frame processing...")
                success_count = 0
                for item in stuck_items:
                    if reset_stuck_item(item['footage_id'], item['record_id'], token, "5 - Processing Frame Info"):
                        success_count += 1
                print(f"✅ Successfully reset {success_count}/{len(stuck_items)} items")
                
            elif choice == "2":
                print("\n🔄 Resetting all stuck items to pending (full restart)...")
                success_count = 0
                for item in stuck_items:
                    if reset_stuck_item(item['footage_id'], item['record_id'], token, "0 - Pending File Info"):
                        success_count += 1
                print(f"✅ Successfully reset {success_count}/{len(stuck_items)} items")
                
            elif choice == "3":
                footage_id = input("Enter footage ID to retry: ").strip()
                if footage_id:
                    job_id = retry_failed_item(footage_id, token)
                    if job_id:
                        print(f"Job submitted: {job_id}")
                        monitor_choice = input("Monitor this job? (y/n): ").strip().lower()
                        if monitor_choice == 'y':
                            monitor_job_progress(job_id)
                
            elif choice == "4":
                job_id = input("Enter job ID to monitor: ").strip()
                if job_id:
                    monitor_job_progress(job_id)
                
            elif choice == "5":
                print("👋 Goodbye!")
                break
                
            else:
                print("❌ Invalid choice. Please enter 1-5.")
            
            print()
    else:
        print("✅ No stuck items found!")
        print("All footage items appear to be processing normally.")

if __name__ == "__main__":
    main() 