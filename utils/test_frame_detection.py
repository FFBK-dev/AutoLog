#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import requests
import time

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def test_frame_completion_detection(footage_id, token):
    """Test the frame completion detection logic directly."""
    print(f"🔍 Testing frame completion detection for {footage_id}")
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
            return
        
        frame_records = response.json()['response']['data']
        if not frame_records:
            print(f"❌ No frames found for {footage_id}")
            return
        
        print(f"📋 Found {len(frame_records)} frames")
        print()
        
        # Analyze each frame
        status_counts = {}
        content_analysis = {
            "complete": 0,
            "missing_caption": 0,
            "missing_transcript": 0,
            "missing_both": 0
        }
        
        print("📊 Frame Analysis:")
        print("-" * 80)
        
        for i, frame_record in enumerate(frame_records[:10]):  # Show first 10 frames
            frame_id = frame_record['fieldData'].get('FRAME_ID', 'Unknown')
            status = frame_record['fieldData'].get('FRAMES_Status', 'Unknown')
            caption = frame_record['fieldData'].get('FRAMES_Caption', '').strip()
            transcript = frame_record['fieldData'].get('FRAMES_Transcript', '').strip()
            
            # Count by status
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # Analyze content
            if caption and transcript:
                content_analysis["complete"] += 1
                content_status = "✅ COMPLETE"
            elif not caption and not transcript:
                content_analysis["missing_both"] += 1
                content_status = "❌ MISSING BOTH"
            elif not caption:
                content_analysis["missing_caption"] += 1
                content_status = "⚠️ MISSING CAPTION"
            else:
                content_analysis["missing_transcript"] += 1
                content_status = "⚠️ MISSING TRANSCRIPT"
            
            print(f"Frame {i+1:2d}: {frame_id} | Status: {status:25} | Content: {content_status}")
            print(f"         Caption: {len(caption):3d} chars | Transcript: {len(transcript):3d} chars")
        
        if len(frame_records) > 10:
            print(f"... and {len(frame_records) - 10} more frames")
        
        print()
        print("📈 Summary:")
        print("-" * 40)
        
        # Status summary
        print("Status Breakdown:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")
        
        print()
        print("Content Analysis:")
        print(f"  Complete (caption + transcript): {content_analysis['complete']}")
        print(f"  Missing caption only: {content_analysis['missing_caption']}")
        print(f"  Missing transcript only: {content_analysis['missing_transcript']}")
        print(f"  Missing both: {content_analysis['missing_both']}")
        
        # Test the detection logic
        print()
        print("🧪 Detection Logic Test:")
        print("-" * 40)
        
        content_ready_frames = content_analysis["complete"]
        total_frames = len(frame_records)
        
        print(f"Content-ready frames: {content_ready_frames}/{total_frames}")
        print(f"Detection result: {'✅ READY' if content_ready_frames == total_frames else '❌ NOT READY'}")
        
        if content_ready_frames < total_frames:
            print(f"❌ REASON: {total_frames - content_ready_frames} frames missing required content")
        
        return content_ready_frames == total_frames
        
    except Exception as e:
        print(f"❌ Error in frame completion detection: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    token = config.get_token()
    footage_ids = ['AF0002', 'AF0003', 'AF0004', 'AF0005']
    
    for footage_id in footage_ids:
        print(f"\n{'='*80}")
        ready = test_frame_completion_detection(footage_id, token)
        print(f"\n🎯 RESULT: {footage_id} is {'READY' if ready else 'NOT READY'} for step 6")
        print(f"{'='*80}")

if __name__ == "__main__":
    main() 