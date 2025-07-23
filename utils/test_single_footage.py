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

def get_frame_details(footage_id, token):
    """Get detailed frame information."""
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
            return []
        
        if response.status_code == 200:
            frame_records = response.json()['response']['data']
            return frame_records
        else:
            return []
            
    except Exception as e:
        print(f"Error getting frames: {e}")
        return []

def analyze_frames(frames):
    """Analyze frame statuses and content."""
    if not frames:
        return {"total": 0, "ready": 0, "status_ready": 0, "status_breakdown": {}, "content_ready": 0}
    
    status_counts = {}
    content_ready = 0
    status_ready = 0
    
    for frame in frames:
        status = frame['fieldData'].get('FRAMES_Status', 'Unknown')
        caption = frame['fieldData'].get('FRAMES_Caption', '').strip()
        transcript = frame['fieldData'].get('FRAMES_Transcript', '').strip()
        
        # Count by status
        status_counts[status] = status_counts.get(status, 0) + 1
        
        # Check if status indicates ready
        if status in ['4 - Audio Transcribed', '5 - Generating Embeddings', '6 - Embeddings Complete']:
            status_ready += 1
        
        # Check if content is ready
        if caption and transcript:
            content_ready += 1
    
    return {
        "total": len(frames),
        "ready": content_ready,
        "status_ready": status_ready,
        "status_breakdown": status_counts,
        "content_ready": content_ready
    }

def run_workflow_step(step_num, footage_id, token):
    """Run a specific workflow step."""
    print(f"🚀 Running step {step_num} for {footage_id}...")
    
    import subprocess
    
    if step_num == 5:
        script = "footage_autolog_05_process_frames.py"
    else:
        print(f"❌ Step {step_num} not implemented in this test")
        return False
    
    cmd = ["python3", f"jobs/{script}", footage_id, token]
    print(f"  -> Running: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    
    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    print(f"Exit code: {result.returncode}")
    return result.returncode == 0

def monitor_frame_completion(footage_id, token, max_wait_time=1800):
    """Monitor frame completion with detailed analysis."""
    print(f"🔍 Monitoring frame completion for {footage_id}...")
    print(f"⏱️ Will monitor for up to {max_wait_time} seconds")
    
    start_time = time.time()
    check_count = 0
    
    while time.time() - start_time < max_wait_time:
        check_count += 1
        current_time = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n📊 Check #{check_count} at {current_time}:")
        print("-" * 60)
        
        # Get current footage status
        footage_status = get_footage_status(footage_id, token)
        print(f"📹 Footage Status: {footage_status}")
        
        # Get frame details
        frames = get_frame_details(footage_id, token)
        analysis = analyze_frames(frames)
        
        print(f"📋 Frame Analysis:")
        print(f"  Total frames: {analysis['total']}")
        print(f"  Status-ready frames: {analysis['status_ready']}")
        print(f"  Content-ready frames: {analysis['content_ready']}")
        
        if analysis['status_breakdown']:
            print(f"  Status breakdown:")
            for status, count in sorted(analysis['status_breakdown'].items()):
                print(f"    {status}: {count}")
        
        # Check if all frames are ready
        all_ready = False
        if analysis['total'] > 0:
            # Frame is ready if status is "4 - Audio Transcribed" or higher, OR has both caption and transcript
            ready_count = 0
            for frame in frames:
                status = frame['fieldData'].get('FRAMES_Status', 'Unknown')
                caption = frame['fieldData'].get('FRAMES_Caption', '').strip()
                transcript = frame['fieldData'].get('FRAMES_Transcript', '').strip()
                
                if (status in ['4 - Audio Transcribed', '5 - Generating Embeddings', '6 - Embeddings Complete'] or 
                    (caption and transcript)):
                    ready_count += 1
            
            all_ready = (ready_count == analysis['total'])
            print(f"  Ready frames: {ready_count}/{analysis['total']}")
            print(f"  All ready: {'✅ YES' if all_ready else '❌ NO'}")
        
        if all_ready:
            print(f"\n🎉 All frames are ready! {footage_id} can proceed to step 6")
            return True
        
        # Wait before next check
        time.sleep(30)  # Check every 30 seconds
    
    print(f"\n⏰ Monitoring timeout reached after {max_wait_time} seconds")
    return False

def main():
    """Main test function."""
    try:
        token = config.get_token()
        
        # Get footage ID from command line argument
        if len(sys.argv) < 2:
            print("❌ Usage: python test_single_footage.py <FOOTAGE_ID>")
            print("Example: python test_single_footage.py AF0002")
            return False
        
        footage_id = sys.argv[1]
        
        print(f"🧪 Testing single footage workflow")
        print(f"📋 Test footage: {footage_id}")
        print("=" * 60)
        
        # Step 1: Check initial state
        print("\n📋 STEP 1: Checking initial state...")
        initial_status = get_footage_status(footage_id, token)
        initial_frames = get_frame_details(footage_id, token)
        print(f"  Status: {initial_status}")
        print(f"  Frames: {len(initial_frames)}")
        
        # Step 2: Run step 5 (frame processing)
        print(f"\n🚀 STEP 2: Running step 5 (frame processing)...")
        step5_success = run_workflow_step(5, footage_id, token)
        
        if not step5_success:
            print(f"❌ Step 5 failed")
            return False
        
        # Step 3: Monitor frame completion
        print(f"\n🔍 STEP 3: Monitoring frame completion...")
        completion_success = monitor_frame_completion(footage_id, token)
        
        # Step 4: Final analysis
        print(f"\n📊 STEP 4: Final analysis...")
        final_status = get_footage_status(footage_id, token)
        final_frames = get_frame_details(footage_id, token)
        final_analysis = analyze_frames(final_frames)
        
        print(f"  Final footage status: {final_status}")
        print(f"  Final frame count: {final_analysis['total']}")
        print(f"  Final ready frames: {final_analysis['content_ready']}")
        
        if completion_success:
            print(f"\n🎉 SUCCESS: Frame completion detected correctly!")
        else:
            print(f"\n❌ FAILURE: Frame completion not detected")
        
        return completion_success
        
    except Exception as e:
        print(f"❌ Critical error in test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 