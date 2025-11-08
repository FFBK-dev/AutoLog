#!/usr/bin/env python3
"""
Find records that are currently stuck at step 5 waiting for frame completion.
"""

import sys
import requests
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def find_currently_stuck():
    """Find records currently stuck at step 5 with frames at step 4."""
    
    print("🔍 Finding Currently Stuck Records")
    print("=" * 40)
    
    try:
        token = config.get_token()
        
        # Find footage records at "5 - Processing Frame Info"
        query = {
            "query": [{"AutoLog_Status": "5 - Processing Frame Info"}],
            "limit": 50
        }
        
        response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 404:
            print("📋 No records found at '5 - Processing Frame Info' status")
            return
        
        if response.status_code != 200:
            print(f"❌ Error finding records: {response.status_code}")
            return
        
        footage_records = response.json()['response']['data']
        print(f"📋 Found {len(footage_records)} records at '5 - Processing Frame Info'")
        
        for record in footage_records:
            footage_id = record['fieldData'].get('INFO_FTG_ID', 'Unknown')
            print(f"\n📹 Checking {footage_id}")
            
            # Get frames for this footage
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
                
                # Check frame completion
                status_counts = {}
                ready_count = 0
                
                for frame in frames:
                    frame_data = frame['fieldData']
                    frame_status = frame_data.get('FRAMES_Status', 'Unknown')
                    caption = frame_data.get('FRAMES_Caption', '').strip()
                    
                    status_counts[frame_status] = status_counts.get(frame_status, 0) + 1
                    
                    # Ready if status is "4 - Audio Transcribed" OR has caption
                    if frame_status == '4 - Audio Transcribed' or caption:
                        ready_count += 1
                
                all_ready = (ready_count == len(frames))
                
                print(f"  📊 Frames: {ready_count}/{len(frames)} ready")
                print(f"  📊 Status breakdown: {status_counts}")
                
                if all_ready:
                    print(f"  🚨 STUCK: All frames ready but not advancing to step 6!")
                else:
                    print(f"  ⏳ Waiting: {len(frames) - ready_count} frames not ready yet")
            
            elif frame_response.status_code == 404:
                print(f"  📭 No frames found")
            else:
                print(f"  ❌ Error getting frames: {frame_response.status_code}")
    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    find_currently_stuck() 