#!/usr/bin/env python3
"""
Submit Reset Footage IDs for Processing

This script submits the already-reset footage IDs (AF0040-AF0054) for processing
to test the new timeout and retry logic.
"""

import requests
import time

def submit_for_processing(footage_id):
    """Submit a footage ID for processing via the API."""
    try:
        print(f"🚀 Submitting {footage_id} for processing")
        
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
            print(f"  ✅ Job submitted successfully: {job_id}")
            print(f"  ⏱️ Estimated timeout: {estimated_timeout}s")
            return job_id
        else:
            print(f"  ❌ Failed to submit job: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error submitting {footage_id}: {e}")
        return None

def monitor_job_progress(job_id, max_wait_time=300):
    """Monitor a job's progress in real-time."""
    print(f"  📊 Monitoring job: {job_id}")
    print(f"  ⏱️ Will monitor for up to {max_wait_time} seconds")
    
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
    """Main submission function."""
    print("🚀 Submitting Reset Footage IDs for Processing")
    print("=" * 50)
    print("Processing: AF0040-AF0054")
    print()
    
    # Generate the list of problematic IDs
    problematic_ids = [f"AF{str(i).zfill(4)}" for i in range(40, 55)]  # AF0040 to AF0054
    
    print(f"📋 Found {len(problematic_ids)} IDs to submit")
    print()
    
    results = {
        'submitted_jobs': [],
        'failed_submissions': []
    }
    
    # Process each ID
    for i, footage_id in enumerate(problematic_ids, 1):
        print(f"🔄 Processing {i}/{len(problematic_ids)}: {footage_id}")
        
        # Submit for processing
        job_id = submit_for_processing(footage_id)
        if job_id:
            results['submitted_jobs'].append((footage_id, job_id))
            
            # Monitor progress (optional)
            monitor_choice = input(f"    -> Monitor progress for {footage_id}? (y/n): ").strip().lower()
            if monitor_choice == 'y':
                monitor_job_progress(job_id, max_wait_time=600)  # 10 minutes monitoring
        else:
            results['failed_submissions'].append(footage_id)
        
        print()
    
    # Summary
    print("📊 Submission Summary")
    print("=" * 30)
    print(f"🚀 Submitted jobs: {len(results['submitted_jobs'])}")
    print(f"❌ Failed submissions: {len(results['failed_submissions'])}")
    
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