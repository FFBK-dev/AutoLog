#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import requests
import time
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def reset_footage_status(footage_id, token):
    """Reset a footage record status to '0 - Pending File Info'."""
    try:
        print(f"🔄 Resetting {footage_id} status...")
        
        # Find the footage record
        record_id = config.find_record_id(token, "FOOTAGE", {"INFO_FTG_ID": f"=={footage_id}"})
        if not record_id:
            print(f"  ❌ Could not find footage record for {footage_id}")
            return False
        
        # Reset status to pending
        payload = {"fieldData": {"AutoLog_Status": "0 - Pending File Info"}}
        response = requests.patch(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            json=payload,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"  ✅ Reset {footage_id} status to '0 - Pending File Info'")
            return True
        else:
            print(f"  ❌ Failed to reset {footage_id}: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error resetting {footage_id}: {e}")
        return False

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

def monitor_processing(footage_ids, token, max_monitoring_time=1800):  # 30 minutes
    """Monitor the processing of footage IDs."""
    print(f"🔍 Starting monitoring for {len(footage_ids)} footage IDs...")
    print(f"⏱️ Will monitor for up to {max_monitoring_time} seconds")
    
    start_time = time.time()
    check_count = 0
    
    while time.time() - start_time < max_monitoring_time:
        check_count += 1
        current_time = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n📊 Check #{check_count} at {current_time}:")
        print("-" * 60)
        
        all_complete = True
        for footage_id in footage_ids:
            status = get_footage_status(footage_id, token)
            frame_count = get_frame_count(footage_id, token)
            
            status_emoji = "✅" if status in ["7 - Generating Embeddings", "8 - Applying Tags", "9 - Complete"] else "⏳"
            print(f"{status_emoji} {footage_id}: {status} ({frame_count} frames)")
            
            if status not in ["7 - Generating Embeddings", "8 - Applying Tags", "9 - Complete"]:
                all_complete = False
        
        if all_complete:
            print(f"\n🎉 All footage IDs completed processing!")
            return True
        
        # Wait before next check
        time.sleep(30)  # Check every 30 seconds
    
    print(f"\n⏰ Monitoring timeout reached after {max_monitoring_time} seconds")
    return False

def main():
    """Main test function."""
    try:
        token = config.get_token()
        footage_ids = [f"AF{str(i).zfill(4)}" for i in range(1, 11)]  # AF0001 to AF0010
        
        print(f"🧪 Starting simple test for {len(footage_ids)} footage IDs")
        print(f"📋 Test IDs: {footage_ids}")
        print("=" * 60)
        
        # Step 1: Reset all footage statuses
        print("\n🔄 STEP 1: Resetting footage statuses to '0 - Pending File Info'...")
        reset_success = 0
        for footage_id in footage_ids:
            if reset_footage_status(footage_id, token):
                reset_success += 1
        
        print(f"✅ Reset {reset_success}/{len(footage_ids)} footage statuses")
        
        # Step 2: Verify initial state
        print("\n📋 STEP 2: Verifying initial state...")
        for footage_id in footage_ids:
            status = get_footage_status(footage_id, token)
            frame_count = get_frame_count(footage_id, token)
            print(f"  {footage_id}: {status} ({frame_count} frames)")
        
        # Step 3: Start the workflow
        print(f"\n🚀 STEP 3: Starting workflow processing...")
        print("Running: python3 jobs/footage_autolog_00_run_all.py")
        
        import subprocess
        workflow_process = subprocess.Popen(
            ["python3", "jobs/footage_autolog_00_run_all.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Step 4: Monitor processing
        print(f"\n🔍 STEP 4: Monitoring processing...")
        monitoring_success = monitor_processing(footage_ids, token)
        
        # Step 5: Final status check
        print(f"\n📊 STEP 5: Final status check...")
        final_results = []
        for footage_id in footage_ids:
            status = get_footage_status(footage_id, token)
            frame_count = get_frame_count(footage_id, token)
            final_results.append({
                "footage_id": footage_id,
                "status": status,
                "frame_count": frame_count
            })
            print(f"  {footage_id}: {status} ({frame_count} frames)")
        
        # Summary
        print(f"\n📈 TEST SUMMARY:")
        print(f"  Total footage IDs: {len(footage_ids)}")
        print(f"  Status resets: {reset_success}/{len(footage_ids)}")
        print(f"  Monitoring completed: {'Yes' if monitoring_success else 'No'}")
        
        completed_count = len([r for r in final_results if r["status"] in ["7 - Generating Embeddings", "8 - Applying Tags", "9 - Complete"]])
        print(f"  Final completion: {completed_count}/{len(footage_ids)}")
        
        # Show any stuck items
        stuck_items = [r for r in final_results if r["status"] not in ["7 - Generating Embeddings", "8 - Applying Tags", "9 - Complete"]]
        if stuck_items:
            print(f"\n⚠️ STUCK ITEMS:")
            for item in stuck_items:
                print(f"  {item['footage_id']}: {item['status']} ({item['frame_count']} frames)")
        
        return monitoring_success
        
    except Exception as e:
        print(f"❌ Critical error in test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 