#!/usr/bin/env python3
"""
Debug Stuck Item

Get detailed information about a stuck item to understand what's happening.
"""

import sys
from pathlib import Path
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def get_detailed_footage_info(footage_id, token):
    """Get detailed information about a footage item."""
    try:
        response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"INFO_FTG_ID": f"=={footage_id}"}],
                "limit": 1
            },
            verify=False,
            timeout=30
        )
        
        if response.status_code == 404:
            print(f"❌ {footage_id}: Not found")
            return
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        if not records:
            print(f"❌ {footage_id}: Not found")
            return
        
        record = records[0]
        field_data = record['fieldData']
        
        print(f"📹 Detailed Info for {footage_id}")
        print("=" * 50)
        print(f"Status: {field_data.get('AutoLog_Status', 'Unknown')}")
        print(f"Duration: {field_data.get('SPECS_File_Duration_Timecode', 'Unknown')}")
        print(f"Frames: {field_data.get('SPECS_File_Frames', 'Unknown')}")
        print(f"Filepath: {field_data.get('SPECS_Filepath_Server', 'Unknown')}")
        print()
        
        # Show dev console
        dev_console = field_data.get('AI_DevConsole', '')
        if dev_console:
            print("🔍 Dev Console (last 10 lines):")
            lines = dev_console.split('\n')
            for line in lines[-10:]:
                if line.strip():
                    print(f"  {line}")
        else:
            print("🔍 Dev Console: Empty")
        
        print()
        
        # Check frame statuses
        frame_response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"FRAMES_ParentID": footage_id}],
                "limit": 100
            },
            verify=False,
            timeout=30
        )
        
        if frame_response.status_code == 200:
            frame_records = frame_response.json()['response']['data']
            print(f"📋 Frame Status Summary ({len(frame_records)} frames):")
            
            status_counts = {}
            for frame_record in frame_records:
                status = frame_record['fieldData'].get('FRAMES_Status', 'Unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            for status, count in status_counts.items():
                print(f"  {status}: {count} frames")
        else:
            print("📋 No frames found")
        
        print()

def main():
    """Debug a stuck item."""
    print("🔍 Debug Stuck Item")
    print("=" * 30)
    
    try:
        token = config.get_token()
        print("✅ FileMaker connection established")
    except Exception as e:
        print(f"❌ Could not get FileMaker token: {e}")
        return
    
    # Check AF0040 as an example
    get_detailed_footage_info("AF0040", token)

if __name__ == "__main__":
    main() 