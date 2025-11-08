#!/usr/bin/env python3
import sys, warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
import requests

def audit_range(start_id, end_id):
    """Audit footage records in a specific range."""
    print(f"🔍 Auditing footage records from {start_id} to {end_id}")
    
    token = config.get_token()
    
    # Extract numeric parts
    start_num = int(start_id.replace('LF', ''))
    end_num = int(end_id.replace('LF', ''))
    
    issues_found = 0
    duplicates_found = 0
    missing_thumbnails = 0
    
    for num in range(start_num, end_num + 1):
        footage_id = f"LF{num:04d}"
        
        try:
            # Find frame records for this footage
            query = {
                "query": [{"INFO_ParentRecord": footage_id}],
                "limit": 100
            }
            
            response = requests.post(
                config.url("layouts/FRAMES/records/_find"),
                headers=config.api_headers(token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 404:
                continue  # No frames found, skip
            
            if response.status_code == 401:
                token = config.get_token()
                continue
                
            response.raise_for_status()
            frames = response.json()['response']['data']
            
            if not frames:
                continue
                
            # Check for duplicates by timecode
            timecodes = {}
            for frame in frames:
                timecode = frame['fieldData'].get('INFO_Timecode', '')
                if timecode in timecodes:
                    timecodes[timecode].append(frame)
                else:
                    timecodes[timecode] = [frame]
            
            # Report duplicates
            for timecode, frame_list in timecodes.items():
                if len(frame_list) > 1:
                    print(f"❌ {footage_id}: {len(frame_list)} duplicate frames at timecode {timecode}")
                    duplicates_found += len(frame_list) - 1
                    issues_found += 1
            
            # Check for missing thumbnails
            missing_thumb_count = 0
            for frame in frames:
                thumbnail_field = frame['fieldData'].get('INFO_Thumbnail', '')
                if not thumbnail_field or thumbnail_field == '':
                    missing_thumb_count += 1
            
            if missing_thumb_count > 0:
                print(f"⚠️ {footage_id}: {missing_thumb_count} frames missing thumbnails")
                missing_thumbnails += missing_thumb_count
                issues_found += 1
                
        except Exception as e:
            print(f"❌ Error checking {footage_id}: {e}")
            continue
    
    print(f"\n📊 AUDIT SUMMARY for {start_id}-{end_id}:")
    print(f"   Issues found: {issues_found}")
    print(f"   Duplicate frames: {duplicates_found}")
    print(f"   Missing thumbnails: {missing_thumbnails}")
    
    return issues_found, duplicates_found, missing_thumbnails

if __name__ == "__main__":
    audit_range("LF0650", "LF0925") 