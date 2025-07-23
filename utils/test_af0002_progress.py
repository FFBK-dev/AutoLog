#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import requests
import time

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "status": "AutoLog_Status",
    "dev_console": "AI_DevConsole"
}

def get_footage_status(footage_id, token):
    """Get current status of a footage record."""
    try:
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
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

def analyze_frames_with_improved_logic(frames):
    """Analyze frame statuses using the improved completion logic."""
    if not frames:
        return {"total": 0, "ready": 0, "status_breakdown": {}}
    
    status_counts = {}
    ready_frames = 0
    
    print(f"📋 Frame Analysis (Improved Logic):")
    print("=" * 60)
    
    for i, frame in enumerate(frames, 1):
        frame_id = frame['fieldData'].get('FRAMES_ID', 'Unknown')
        status = frame['fieldData'].get('FRAMES_Status', 'Unknown')
        caption = frame['fieldData'].get('FRAMES_Caption', '').strip()
        transcript = frame['fieldData'].get('FRAMES_Transcript', '').strip()
        
        # Count by status
        status_counts[status] = status_counts.get(status, 0) + 1
        
        # Improved ready logic: frame is ready if:
        # 1. Status is "4 - Audio Transcribed" or higher (audio step complete, regardless of transcript content), OR
        # 2. Has caption content (caption step complete)
        # Note: Status "4 - Audio Transcribed" means we've checked for audio, even if none was found
        is_ready = (status in ['4 - Audio Transcribed', '5 - Generating Embeddings', '6 - Embeddings Complete'] or 
                   caption)  # Has caption
        
        if is_ready:
            ready_frames += 1
        
        print(f"  Frame {i}: {frame_id}")
        print(f"    Status: {status}")
        print(f"    Caption: {'✅ Present' if caption else '❌ Missing'} ({len(caption)} chars)")
        print(f"    Transcript: {'✅ Present' if transcript else '❌ Missing'} ({len(transcript)} chars)")
        print(f"    Ready: {'✅ YES' if is_ready else '❌ NO'}")
        print()
    
    return {
        "total": len(frames),
        "ready": ready_frames,
        "status_breakdown": status_counts
    }

def run_step_5(footage_id, token):
    """Run step 5 (frame processing) for the footage."""
    print(f"🚀 Running step 5 for {footage_id}...")
    
    import subprocess
    
    cmd = ["python3", "jobs/footage_autolog_05_process_frames.py", footage_id, token]
    print(f"  -> Running: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    
    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    print(f"Exit code: {result.returncode}")
    return result.returncode == 0

def main():
    """Test AF0002 progress with improved logic."""
    footage_id = "AF0002"
    
    try:
        token = config.get_token()
        
        print(f"🧪 Testing AF0002 progress with improved frame completion logic")
        print("=" * 70)
        
        # Step 1: Check initial state
        print(f"\n📋 STEP 1: Checking initial state...")
        initial_status = get_footage_status(footage_id, token)
        initial_frames = get_frame_details(footage_id, token)
        initial_analysis = analyze_frames_with_improved_logic(initial_frames)
        
        print(f"📹 Footage Status: {initial_status}")
        print(f"📊 Frame Summary: {initial_analysis['ready']}/{initial_analysis['total']} ready")
        
        # Step 2: Run step 5 if needed
        if initial_status == "5 - Processing Frame Info":
            print(f"\n🚀 STEP 2: Running step 5 (frame processing)...")
            step5_success = run_step_5(footage_id, token)
            
            if not step5_success:
                print(f"❌ Step 5 failed")
                return False
            
            # Wait a moment for processing to complete
            print(f"⏳ Waiting 10 seconds for processing to complete...")
            time.sleep(10)
        else:
            print(f"📋 Step 5 not needed - current status: {initial_status}")
        
        # Step 3: Check final state
        print(f"\n📊 STEP 3: Checking final state...")
        final_status = get_footage_status(footage_id, token)
        final_frames = get_frame_details(footage_id, token)
        final_analysis = analyze_frames_with_improved_logic(final_frames)
        
        print(f"📹 Final Footage Status: {final_status}")
        print(f"📊 Final Frame Summary: {final_analysis['ready']}/{final_analysis['total']} ready")
        
        # Step 4: Analysis
        print(f"\n📈 ANALYSIS:")
        print(f"  Status change: {initial_status} -> {final_status}")
        print(f"  Ready frames: {initial_analysis['ready']} -> {final_analysis['ready']}")
        
        if final_analysis['ready'] == final_analysis['total']:
            print(f"✅ SUCCESS: All frames are ready! {footage_id} should be able to proceed to step 6")
        else:
            print(f"❌ ISSUE: {final_analysis['total'] - final_analysis['ready']} frames still not ready")
        
        return final_analysis['ready'] == final_analysis['total']
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 