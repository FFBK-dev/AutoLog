#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import requests
import time
from datetime import datetime

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def get_footage_status(footage_id, token):
    """Get current status of a footage record."""
    try:
        record_id = config.find_record_id(token, "FOOTAGE", {"INFO_FTG_ID": f"=={footage_id}"})
        if not record_id:
            return "NOT_FOUND"
        
        response = requests.get(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()['response']['data'][0]['fieldData']
            return data.get('AutoLog_Status', 'UNKNOWN')
        else:
            return f"ERROR_{response.status_code}"
            
    except Exception as e:
        return f"ERROR_{str(e)}"

def get_frame_count(footage_id, token):
    """Get count of child frames for a footage ID."""
    try:
        response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"FRAMES_ParentID": footage_id}],
                "limit": 100
            },
            verify=False,
            timeout=30
        )
        
        if response.status_code == 404:
            return 0
        
        if response.status_code == 200:
            frame_records = response.json()['response']['data']
            return len(frame_records)
        else:
            return -1
            
    except Exception as e:
        return -1

def monitor_processing(footage_id, token, max_monitoring_time=1800):
    """Monitor the processing of a single footage ID."""
    print(f"🔍 Starting monitoring for {footage_id}...")
    print(f"⏱️ Will monitor for up to {max_monitoring_time} seconds")
    
    start_time = time.time()
    check_count = 0
    
    while time.time() - start_time < max_monitoring_time:
        check_count += 1
        current_time = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n📊 Check #{check_count} at {current_time}:")
        print("-" * 60)
        
        status = get_footage_status(footage_id, token)
        frame_count = get_frame_count(footage_id, token)
        
        status_emoji = "✅" if status in ["7 - Generating Embeddings", "8 - Applying Tags", "9 - Complete"] else "⏳"
        print(f"{status_emoji} {footage_id}: {status} ({frame_count} frames)")
        
        if status in ["7 - Generating Embeddings", "8 - Applying Tags", "9 - Complete"]:
            print(f"\n🎉 {footage_id} completed processing!")
            return True
        
        # Special monitoring for step 5
        if status == "5 - Processing Frame Info":
            print(f"  🔍 Currently at step 5 - monitoring frame completion...")
        
        # Wait before next check
        time.sleep(30)  # Check every 30 seconds
    
    print(f"\n⏰ Monitoring timeout reached after {max_monitoring_time} seconds")
    return False

def main():
    """Main test function."""
    try:
        token = config.get_token()
        footage_id = "AF0001"
        
        print(f"🧪 Testing complete workflow on {footage_id}")
        print("=" * 60)
        
        # Step 1: Check initial state
        print("\n📋 STEP 1: Checking initial state...")
        initial_status = get_footage_status(footage_id, token)
        initial_frames = get_frame_count(footage_id, token)
        print(f"  Status: {initial_status}")
        print(f"  Frames: {initial_frames}")
        
        # Step 2: Run the complete workflow
        print(f"\n🚀 STEP 2: Running complete workflow...")
        print("Running: python3 jobs/footage_autolog_00_run_all.py")
        
        import subprocess
        workflow_process = subprocess.Popen(
            ["python3", "jobs/footage_autolog_00_run_all.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Step 3: Monitor processing
        print(f"\n🔍 STEP 3: Monitoring processing...")
        monitoring_success = monitor_processing(footage_id, token)
        
        # Step 4: Final status check
        print(f"\n📊 STEP 4: Final status check...")
        final_status = get_footage_status(footage_id, token)
        final_frames = get_frame_count(footage_id, token)
        print(f"  {footage_id}: {final_status} ({final_frames} frames)")
        
        # Summary
        print(f"\n📈 TEST SUMMARY:")
        print(f"  Initial status: {initial_status}")
        print(f"  Final status: {final_status}")
        print(f"  Initial frames: {initial_frames}")
        print(f"  Final frames: {final_frames}")
        print(f"  Monitoring completed: {'Yes' if monitoring_success else 'No'}")
        
        if final_status in ["7 - Generating Embeddings", "8 - Applying Tags", "9 - Complete"]:
            print(f"\n🎉 SUCCESS: {footage_id} completed successfully!")
        else:
            print(f"\n❌ FAILURE: {footage_id} got stuck at {final_status}")
        
        return monitoring_success
        
    except Exception as e:
        print(f"❌ Critical error in test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 