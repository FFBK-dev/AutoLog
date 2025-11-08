#!/usr/bin/env python3
"""
Script to fix frames stuck at "4 - Audio Transcribed" when parent is at "9 - Complete"
These frames should be moved to "5 - Generating Embeddings"
"""

import sys
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
import requests

# Field mappings
FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "status": "AutoLog_Status", 
    "frame_parent_id": "FRAMES_ParentID",
    "frame_status": "FRAMES_Status",
    "frame_id": "FRAMES_ID",
}

def fix_completed_frames():
    """Fix frames that are stuck at '4 - Audio Transcribed' when parent is at '9 - Complete'."""
    try:
        token = config.get_token()
        
        print("🔧 Fixing completed frames...")
        
        # Get all footage records
        footage_response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json={"query": [{"INFO_FTG_ID": "*"}], "limit": 1000},
            verify=False,
            timeout=30
        )
        
        if footage_response.status_code != 200:
            print(f"❌ Error fetching footage: {footage_response.status_code}")
            return
        
        footage_records = footage_response.json()['response']['data']
        footage_status_map = {}
        
        for record in footage_records:
            footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
            status = record['fieldData'].get(FIELD_MAPPING["status"], "Unknown")
            if footage_id:
                footage_status_map[footage_id] = status
        
        # Get all frame records
        frames_response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json={"query": [{"FRAMES_ID": "*"}], "limit": 1000},
            verify=False,
            timeout=30
        )
        
        if frames_response.status_code != 200:
            print(f"❌ Error fetching frames: {frames_response.status_code}")
            return
        
        frame_records = frames_response.json()['response']['data']
        
        # Find frames that need fixing
        frames_to_fix = []
        
        for record in frame_records:
            frame_id = record['fieldData'].get(FIELD_MAPPING["frame_id"])
            frame_status = record['fieldData'].get(FIELD_MAPPING["frame_status"], "Unknown")
            parent_id = record['fieldData'].get(FIELD_MAPPING["frame_parent_id"])
            parent_status = footage_status_map.get(parent_id, "Unknown Parent")
            
            # Check if frame is stuck at "4 - Audio Transcribed" but parent is at "9 - Complete"
            if (frame_status == "4 - Audio Transcribed" and 
                parent_status == "9 - Complete"):
                frames_to_fix.append({
                    "frame_id": frame_id,
                    "record_id": record['recordId'],
                    "frame_status": frame_status,
                    "parent_id": parent_id,
                    "parent_status": parent_status
                })
        
        if not frames_to_fix:
            print("✅ No frames found to fix")
            return
        
        print(f"🔧 Found {len(frames_to_fix)} frames to fix:")
        for frame in frames_to_fix:
            print(f"  -> {frame['frame_id']}: {frame['frame_status']} (Parent: {frame['parent_id']} - {frame['parent_status']})")
        
        # Ask for confirmation
        response = input(f"\nProceed to fix {len(frames_to_fix)} frames? (y/N): ")
        if response.lower() != 'y':
            print("❌ Operation cancelled")
            return
        
        # Fix the frames
        fixed_count = 0
        failed_count = 0
        
        for frame in frames_to_fix:
            try:
                # Update frame status to "5 - Generating Embeddings"
                payload = {"fieldData": {FIELD_MAPPING["frame_status"]: "5 - Generating Embeddings"}}
                response = requests.patch(
                    config.url(f"layouts/FRAMES/records/{frame['record_id']}"),
                    headers=config.api_headers(token),
                    json=payload,
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 401:
                    # Refresh token and retry
                    token = config.get_token()
                    response = requests.patch(
                        config.url(f"layouts/FRAMES/records/{frame['record_id']}"),
                        headers=config.api_headers(token),
                        json=payload,
                        verify=False,
                        timeout=30
                    )
                
                response.raise_for_status()
                print(f"✅ {frame['frame_id']}: Fixed (4 - Audio Transcribed → 5 - Generating Embeddings)")
                fixed_count += 1
                
            except Exception as e:
                print(f"❌ {frame['frame_id']}: Failed to fix - {e}")
                failed_count += 1
        
        print(f"\n📊 Fix Summary:")
        print(f"  -> Fixed: {fixed_count}")
        print(f"  -> Failed: {failed_count}")
        
        if fixed_count > 0:
            print(f"✅ Successfully fixed {fixed_count} frames!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_completed_frames() 