#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import requests

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

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

def analyze_frame_content(frames):
    """Analyze frame content in detail."""
    print(f"📋 Detailed Frame Analysis:")
    print("=" * 80)
    
    for i, frame in enumerate(frames, 1):
        frame_id = frame['fieldData'].get('FRAMES_ID', 'Unknown')
        status = frame['fieldData'].get('FRAMES_Status', 'Unknown')
        caption = frame['fieldData'].get('FRAMES_Caption', '').strip()
        transcript = frame['fieldData'].get('FRAMES_Transcript', '').strip()
        
        print(f"\n📸 Frame {i}: {frame_id}")
        print(f"   Status: {status}")
        print(f"   Caption: {'✅ Present' if caption else '❌ Missing'} ({len(caption)} chars)")
        print(f"   Transcript: {'✅ Present' if transcript else '❌ Missing'} ({len(transcript)} chars)")
        
        if caption:
            print(f"   Caption preview: {caption[:100]}{'...' if len(caption) > 100 else ''}")
        if transcript:
            print(f"   Transcript preview: {transcript[:100]}{'...' if len(transcript) > 100 else ''}")
        
        # Check if frame is ready
        is_ready = (status in ['4 - Audio Transcribed', '5 - Generating Embeddings', '6 - Embeddings Complete'] or 
                   (caption and transcript))
        print(f"   Ready: {'✅ YES' if is_ready else '❌ NO'}")

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("❌ Usage: python check_frame_details.py <FOOTAGE_ID>")
        print("Example: python check_frame_details.py AF0002")
        return
    
    footage_id = sys.argv[1]
    print(f"🔍 Checking frame details for {footage_id}")
    
    try:
        token = config.get_token()
        frames = get_frame_details(footage_id, token)
        
        if not frames:
            print(f"❌ No frames found for {footage_id}")
            return
        
        print(f"📊 Found {len(frames)} frames")
        analyze_frame_content(frames)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 