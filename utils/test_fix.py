#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
import requests

def test_frame_completion_detection(footage_id, token):
    """Test the fixed frame completion detection logic."""
    print(f"🧪 Testing fixed frame completion detection for {footage_id}")
    print("=" * 60)
    
    try:
        # Get all frames for this footage
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
        
        if response.status_code != 200:
            print(f"❌ Error getting frames: {response.status_code}")
            return False
        
        frame_records = response.json()['response']['data']
        if not frame_records:
            print(f"❌ No frames found for {footage_id}")
            return False
        
        print(f"📋 Found {len(frame_records)} frames")
        print()
        
        # Test the new detection logic
        total_frames = len(frame_records)
        ready_frames = 0
        incomplete_frames = []
        
        print("📊 Frame Analysis:")
        print("-" * 80)
        
        for i, frame_record in enumerate(frame_records):
            frame_id = frame_record['fieldData'].get('FRAME_ID', 'Unknown')
            status = frame_record['fieldData'].get('FRAMES_Status', 'Unknown')
            caption = frame_record['fieldData'].get('FRAMES_Caption', '').strip()
            transcript = frame_record['fieldData'].get('FRAMES_Transcript', '').strip()
            
            # New logic: Frame is ready if status is correct OR has content
            is_ready = (status in ['4 - Audio Transcribed', '5 - Generating Embeddings', '6 - Embeddings Complete'] or 
                       (caption and transcript))
            
            if is_ready:
                ready_frames += 1
                status_emoji = "✅"
            else:
                incomplete_frames.append(f"{frame_id}:{status} (caption:{len(caption)},transcript:{len(transcript)})")
                status_emoji = "❌"
            
            # Only show first 10 frames to avoid spam
            if i < 10:
                print(f"{status_emoji} Frame {i+1}: {frame_id} | Status: {status:25} | Caption: {len(caption):3d} chars | Transcript: {len(transcript):3d} chars")
        
        if len(frame_records) > 10:
            print(f"... and {len(frame_records) - 10} more frames")
        
        print()
        print("📈 Detection Results:")
        print(f"  Total frames: {total_frames}")
        print(f"  Ready frames: {ready_frames}")
        print(f"  Incomplete frames: {len(incomplete_frames)}")
        print(f"  Detection result: {'✅ READY' if ready_frames == total_frames else '❌ NOT READY'}")
        
        return ready_frames == total_frames
        
    except Exception as e:
        print(f"❌ Error in frame completion detection: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_workflow_on_footage(footage_id):
    """Run the workflow on a specific footage ID."""
    print(f"🚀 Running workflow on {footage_id}...")
    
    import subprocess
    result = subprocess.run(
        ["python3", "jobs/footage_autolog_00_run_all.py"],
        capture_output=True,
        text=True,
        timeout=300  # 5 minutes timeout
    )
    
    print("Workflow Output:")
    print("-" * 40)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    print(f"Exit code: {result.returncode}")
    return result.returncode == 0

def main():
    token = config.get_token()
    footage_id = "AF0002"
    
    print(f"🧪 Testing frame completion detection fix")
    print(f"📋 Test footage: {footage_id}")
    print("=" * 60)
    
    # Step 1: Test the detection logic
    print("\n🔍 STEP 1: Testing frame completion detection...")
    detection_result = test_frame_completion_detection(footage_id, token)
    
    if detection_result:
        print(f"\n✅ Frame completion detection working correctly!")
        
        # Step 2: Run the workflow
        print(f"\n🚀 STEP 2: Running workflow...")
        workflow_success = run_workflow_on_footage(footage_id)
        
        if workflow_success:
            print(f"\n🎉 SUCCESS: Workflow completed successfully!")
        else:
            print(f"\n❌ FAILURE: Workflow failed")
    else:
        print(f"\n❌ Frame completion detection still not working correctly")
    
    return detection_result

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 