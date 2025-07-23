#!/usr/bin/env python3
"""
Targeted Reset Script for Problematic Footage IDs

This script specifically handles the problematic footage IDs AF0040-AF0054:
1. Resets their status to "0 - Pending File Info"
2. Removes all child frame records
3. Restarts processing to test the new timeout system
"""

import sys
import requests
import json
import time
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def get_footage_record_id(footage_id, token):
    """Get the FileMaker record ID for a footage ID."""
    try:
        response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"INFO_FTG_ID": f"=={footage_id}"}],
                "limit": 1
            },
            verify=False,
            timeout=30
        )
        
        if response.status_code == 404:
            print(f"  -> ❌ Footage {footage_id} not found")
            return None
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        if not records:
            print(f"  -> ❌ Footage {footage_id} not found")
            return None
        
        return records[0]['recordId']
        
    except Exception as e:
        print(f"  -> ❌ Error finding footage {footage_id}: {e}")
        return None

def reset_footage_status(footage_id, record_id, token, new_status="0 - Pending File Info"):
    """Reset a footage record to a specific status."""
    try:
        print(f"  -> 🔄 Resetting {footage_id} to status: {new_status}")
        
        payload = {"fieldData": {"AutoLog_Status": new_status}}
        response = requests.patch(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            json=payload,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"  -> ✅ Successfully reset {footage_id}")
            return True
        else:
            print(f"  -> ❌ Failed to reset {footage_id}: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  -> ❌ Error resetting {footage_id}: {e}")
        return False

def find_and_delete_child_frames(footage_id, token):
    """Find and delete all child frame records for a footage ID."""
    try:
        print(f"  -> 🔍 Finding child frames for {footage_id}")
        
        # Find all frame records for this footage
        query = {
            "query": [{"FRAMES_ParentID": footage_id}],
            "limit": 1000
        }
        
        response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 404:
            print(f"  -> 📋 No child frames found for {footage_id}")
            return 0
        
        response.raise_for_status()
        frame_records = response.json()['response']['data']
        
        if not frame_records:
            print(f"  -> 📋 No child frames found for {footage_id}")
            return 0
        
        print(f"  -> 🗑️ Found {len(frame_records)} child frames to delete")
        
        # Delete each frame record
        deleted_count = 0
        for frame_record in frame_records:
            frame_record_id = frame_record['recordId']
            frame_id = frame_record['fieldData'].get('FRAMES_ID', frame_record_id)
            
            try:
                delete_response = requests.delete(
                    config.url(f"layouts/FRAMES/records/{frame_record_id}"),
                    headers=config.api_headers(token),
                    verify=False,
                    timeout=30
                )
                
                if delete_response.status_code == 200:
                    deleted_count += 1
                    print(f"    -> ✅ Deleted frame {frame_id}")
                else:
                    print(f"    -> ❌ Failed to delete frame {frame_id}: {delete_response.status_code}")
                    
            except Exception as e:
                print(f"    -> ❌ Error deleting frame {frame_id}: {e}")
        
        print(f"  -> ✅ Successfully deleted {deleted_count}/{len(frame_records)} child frames")
        return deleted_count
        
    except Exception as e:
        print(f"  -> ❌ Error finding/deleting child frames for {footage_id}: {e}")
        return 0

def clear_dev_console(footage_id, record_id, token):
    """Clear the AI_DevConsole field to remove old error messages."""
    try:
        print(f"  -> 🧹 Clearing dev console for {footage_id}")
        
        payload = {"fieldData": {"AI_DevConsole": ""}}
        response = requests.patch(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            json=payload,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"  -> ✅ Cleared dev console for {footage_id}")
            return True
        else:
            print(f"  -> ⚠️ Failed to clear dev console for {footage_id}: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  -> ⚠️ Error clearing dev console for {footage_id}: {e}")
        return False

def submit_for_processing(footage_id):
    """Submit a footage ID for processing via the API."""
    try:
        print(f"  -> 🚀 Submitting {footage_id} for processing")
        
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
            estimated_timeout = result.get('estimated_timeout', 'unknown')
            print(f"  -> ✅ Job submitted successfully: {job_id}")
            print(f"  -> ⏱️ Estimated timeout: {estimated_timeout}s")
            return job_id
        else:
            print(f"  -> ❌ Failed to submit job: {response.status_code}")
            print(f"  -> Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"  -> ❌ Error submitting {footage_id}: {e}")
        return None

def monitor_job_progress(job_id, max_wait_time=300):
    """Monitor a job's progress in real-time."""
    print(f"  -> 📊 Monitoring job: {job_id}")
    print(f"  -> ⏱️ Will monitor for up to {max_wait_time} seconds")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait_time:
        try:
            response = requests.get(f"http://localhost:8081/job/{job_id}", timeout=10)
            if response.status_code == 200:
                job_info = response.json()
                current_status = job_info.get('status', 'unknown')
                
                if current_status != last_status:
                    print(f"    -> Status: {current_status}")
                    last_status = current_status
                
                if current_status in ['completed', 'failed']:
                    print(f"    -> Job finished with status: {current_status}")
                    return current_status
                
                # Show progress if available
                progress = job_info.get('progress', {})
                if progress:
                    is_stuck = progress.get('is_stuck', False)
                    if is_stuck:
                        print(f"    -> ⚠️ Job appears to be stuck")
                    
                    recent_progress = progress.get('recent_progress', [])
                    if recent_progress:
                        latest = recent_progress[-1]
                        print(f"    -> Latest: {latest.get('line', 'No output')}")
            
        except Exception as e:
            print(f"    -> ❌ Could not get job info: {e}")
        
        time.sleep(10)
    
    print(f"    -> ⏱️ Monitoring timeout reached")
    return 'timeout'

def main():
    """Main reset and reprocessing function."""
    print("🔧 Targeted Reset for Problematic Footage IDs")
    print("=" * 60)
    print("Processing: AF0040-AF0054")
    print()
    
    # Get FileMaker token
    try:
        token = config.get_token()
        print("✅ FileMaker connection established")
    except Exception as e:
        print(f"❌ Could not get FileMaker token: {e}")
        return
    
    # Generate the list of problematic IDs
    problematic_ids = [f"AF{str(i).zfill(4)}" for i in range(40, 55)]  # AF0040 to AF0054
    
    print(f"📋 Found {len(problematic_ids)} problematic IDs to process")
    print()
    
    results = {
        'successful_resets': [],
        'failed_resets': [],
        'submitted_jobs': [],
        'failed_submissions': []
    }
    
    # Process each ID
    for i, footage_id in enumerate(problematic_ids, 1):
        print(f"🔄 Processing {i}/{len(problematic_ids)}: {footage_id}")
        
        # Step 1: Get record ID
        record_id = get_footage_record_id(footage_id, token)
        if not record_id:
            results['failed_resets'].append(footage_id)
            print()
            continue
        
        # Step 2: Clear dev console
        clear_dev_console(footage_id, record_id, token)
        
        # Step 3: Delete child frames
        deleted_frames = find_and_delete_child_frames(footage_id, token)
        
        # Step 4: Reset status to pending
        if reset_footage_status(footage_id, record_id, token, "0 - Pending File Info"):
            results['successful_resets'].append(footage_id)
            
            # Step 5: Submit for processing
            job_id = submit_for_processing(footage_id)
            if job_id:
                results['submitted_jobs'].append((footage_id, job_id))
                
                # Step 6: Monitor progress (optional)
                monitor_choice = input(f"    -> Monitor progress for {footage_id}? (y/n): ").strip().lower()
                if monitor_choice == 'y':
                    monitor_job_progress(job_id, max_wait_time=600)  # 10 minutes monitoring
            else:
                results['failed_submissions'].append(footage_id)
        else:
            results['failed_resets'].append(footage_id)
        
        print()
    
    # Summary
    print("📊 Processing Summary")
    print("=" * 40)
    print(f"✅ Successful resets: {len(results['successful_resets'])}")
    print(f"❌ Failed resets: {len(results['failed_resets'])}")
    print(f"🚀 Submitted jobs: {len(results['submitted_jobs'])}")
    print(f"❌ Failed submissions: {len(results['failed_submissions'])}")
    
    if results['successful_resets']:
        print(f"\n✅ Successfully reset: {', '.join(results['successful_resets'])}")
    
    if results['failed_resets']:
        print(f"\n❌ Failed to reset: {', '.join(results['failed_resets'])}")
    
    if results['submitted_jobs']:
        print(f"\n🚀 Submitted for processing:")
        for footage_id, job_id in results['submitted_jobs']:
            print(f"  -> {footage_id}: {job_id}")
    
    if results['failed_submissions']:
        print(f"\n❌ Failed to submit: {', '.join(results['failed_submissions'])}")
    
    print(f"\n🎯 Next steps:")
    print(f"1. Monitor the submitted jobs using: python3 utils/job_monitor.py")
    print(f"2. Check individual job progress: GET /job/{job_id}")
    print(f"3. Watch for the new timeout and retry logic in action")

if __name__ == "__main__":
    main() 