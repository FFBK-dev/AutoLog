#!/usr/bin/env python3
"""
Analyze stuck records AF0011-AF0017 and their frame statuses.

This will help us understand why the polling system isn't advancing
these records from step 5 to step 6.
"""

import sys
import requests
import json
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def analyze_stuck_records():
    """Analyze the specific stuck records and their frames."""
    
    stuck_footage_ids = ["AF0011", "AF0012", "AF0013", "AF0014", "AF0015", "AF0016", "AF0017"]
    
    print("🔍 Analyzing Stuck Records")
    print("=" * 50)
    
    try:
        token = config.get_token()
        print("✅ FileMaker connection established")
        
        for footage_id in stuck_footage_ids:
            print(f"\n📹 Analyzing {footage_id}")
            print("-" * 30)
            
            try:
                # Get the footage record
                footage_record_id = config.find_record_id(token, "FOOTAGE", {"INFO_FTG_ID": f"=={footage_id}"})
                
                if footage_record_id:
                    footage_response = requests.get(
                        config.url(f"layouts/FOOTAGE/records/{footage_record_id}"),
                        headers=config.api_headers(token),
                        verify=False,
                        timeout=30
                    )
                    
                    if footage_response.status_code == 200:
                        footage_data = footage_response.json()['response']['data'][0]['fieldData']
                        footage_status = footage_data.get('AutoLog_Status', 'Unknown')
                        
                        print(f"  📊 Footage Status: {footage_status}")
                        
                        # Expected status for stuck records should be "5 - Processing Frame Info"
                        if footage_status != "5 - Processing Frame Info":
                            print(f"  ⚠️ WARNING: Expected '5 - Processing Frame Info', got '{footage_status}'")
                        
                        # Get all frames for this footage
                        frame_query = {
                            "query": [{"FRAMES_ParentID": footage_id}],
                            "limit": 100
                        }
                        
                        frame_response = requests.post(
                            config.url("layouts/FRAMES/_find"),
                            headers=config.api_headers(token),
                            json=frame_query,
                            verify=False,
                            timeout=30
                        )
                        
                        if frame_response.status_code == 200:
                            frames = frame_response.json()['response']['data']
                            
                            print(f"  📋 Found {len(frames)} frames")
                            
                            # Analyze frame statuses
                            status_counts = {}
                            ready_count = 0
                            problem_frames = []
                            
                            for frame in frames:
                                frame_data = frame['fieldData']
                                frame_id = frame_data.get('FRAME_ID', 'Unknown')
                                frame_status = frame_data.get('FRAMES_Status', 'Unknown')
                                caption = frame_data.get('FRAMES_Caption', '').strip()
                                transcript = frame_data.get('FRAMES_Transcript', '').strip()
                                
                                # Count statuses
                                status_counts[frame_status] = status_counts.get(frame_status, 0) + 1
                                
                                # Check if frame is ready according to our logic
                                if frame_status == '4 - Audio Transcribed' or caption:
                                    ready_count += 1
                                else:
                                    problem_frames.append({
                                        'frame_id': frame_id,
                                        'status': frame_status,
                                        'has_caption': bool(caption),
                                        'has_transcript': bool(transcript),
                                        'caption_length': len(caption),
                                        'transcript_length': len(transcript)
                                    })
                            
                            print(f"  📊 Frame Status Breakdown:")
                            for status, count in sorted(status_counts.items()):
                                print(f"    {status}: {count}")
                            
                            print(f"  ✅ Frames ready for step 6: {ready_count}/{len(frames)}")
                            
                            if ready_count == len(frames):
                                print(f"  🎯 ALL FRAMES READY - Should proceed to step 6!")
                                print(f"  🚨 BUG: Polling system not detecting completion correctly")
                            else:
                                print(f"  ⏳ {len(frames) - ready_count} frames still not ready")
                                print(f"  🔍 Problem frames:")
                                for pf in problem_frames[:5]:  # Show first 5
                                    print(f"    {pf['frame_id']}: {pf['status']} (caption: {pf['caption_length']} chars, transcript: {pf['transcript_length']} chars)")
                                if len(problem_frames) > 5:
                                    print(f"    ... and {len(problem_frames) - 5} more")
                        
                        elif frame_response.status_code == 404:
                            print(f"  📭 No frames found for {footage_id}")
                        else:
                            print(f"  ❌ Error getting frames: {frame_response.status_code}")
                    
                    else:
                        print(f"  ❌ Error getting footage record: {footage_response.status_code}")
                else:
                    print(f"  ❌ Footage record not found")
                    
            except Exception as e:
                print(f"  ❌ Error analyzing {footage_id}: {e}")
        
        # Test the frame completion logic directly
        print(f"\n🧪 Testing Frame Completion Logic")
        print("-" * 40)
        
        # Test with first stuck record
        test_footage_id = stuck_footage_ids[0]
        print(f"Testing with {test_footage_id}...")
        
        # Simulate the check_frame_completion function
        try:
            response = requests.post(
                config.url("layouts/FRAMES/_find"),
                headers=config.api_headers(token),
                json={
                    "query": [{"FRAMES_ParentID": test_footage_id}],
                    "limit": 100
                },
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                frame_records = response.json()['response']['data']
                
                ready_frames = 0
                total_frames = len(frame_records)
                status_breakdown = {}
                
                for frame_record in frame_records:
                    frame_data = frame_record['fieldData']
                    status = frame_data.get('FRAMES_Status', 'Unknown')
                    caption = frame_data.get('FRAMES_Caption', '').strip()
                    
                    # Count status breakdown for reporting
                    status_breakdown[status] = status_breakdown.get(status, 0) + 1
                    
                    # Frame is ready if it has reached "4 - Audio Transcribed" 
                    # OR has caption content (meaning it's completed the processing steps)
                    if status == '4 - Audio Transcribed' or caption:
                        ready_frames += 1
                
                all_ready = (ready_frames == total_frames)
                
                print(f"  📊 Frame completion check result:")
                print(f"    Ready frames: {ready_frames}/{total_frames}")
                print(f"    All ready: {all_ready}")
                print(f"    Status breakdown: {status_breakdown}")
                
                if all_ready:
                    print(f"  🎯 Frame completion logic says: READY TO PROCEED")
                    print(f"  🚨 This confirms the polling system has a bug!")
                else:
                    print(f"  ⏳ Frame completion logic says: NOT READY")
                    print(f"  🔍 This explains why polling isn't advancing")
            
        except Exception as e:
            print(f"  ❌ Error testing frame completion logic: {e}")
        
        print(f"\n📋 Summary")
        print("-" * 20)
        print(f"Analyzed {len(stuck_footage_ids)} stuck records")
        print(f"Check the output above to see:")
        print(f"1. Current footage status (should be '5 - Processing Frame Info')")
        print(f"2. Frame status breakdown")
        print(f"3. Whether frames are actually ready for step 6")
        print(f"4. If there's a bug in the polling logic")
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_stuck_records() 