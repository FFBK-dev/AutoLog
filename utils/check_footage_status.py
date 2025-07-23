#!/usr/bin/env python3
"""
Quick Status Check for Problematic Footage IDs

Check the current status of AF0040-AF0054 to see where they're getting stuck.
"""

import sys
from pathlib import Path
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def check_footage_status(footage_id, token):
    """Check the current status of a footage ID."""
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
            return f"❌ {footage_id}: Not found"
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        if not records:
            return f"❌ {footage_id}: Not found"
        
        record = records[0]
        status = record['fieldData'].get('AutoLog_Status', 'Unknown')
        dev_console = record['fieldData'].get('AI_DevConsole', '')
        
        # Check for child frames
        frame_response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"FRAMES_ParentID": footage_id}],
                "limit": 10
            },
            verify=False,
            timeout=30
        )
        
        frame_count = 0
        if frame_response.status_code == 200:
            frame_records = frame_response.json()['response']['data']
            frame_count = len(frame_records)
        
        result = f"📹 {footage_id}: {status} ({frame_count} frames)"
        
        if dev_console:
            # Show last error if any
            lines = dev_console.split('\n')
            if lines:
                last_line = lines[-1].strip()
                if last_line and len(last_line) > 50:
                    last_line = last_line[:50] + "..."
                result += f"\n    Console: {last_line}"
        
        return result
        
    except Exception as e:
        return f"❌ {footage_id}: Error - {e}"

def main():
    """Check status of all problematic footage IDs."""
    print("🔍 Checking Status of Problematic Footage IDs")
    print("=" * 50)
    
    try:
        token = config.get_token()
        print("✅ FileMaker connection established")
    except Exception as e:
        print(f"❌ Could not get FileMaker token: {e}")
        return
    
    # Generate the list of problematic IDs
    problematic_ids = [f"AF{str(i).zfill(4)}" for i in range(40, 55)]  # AF0040 to AF0054
    
    print(f"📋 Checking {len(problematic_ids)} footage IDs...")
    print()
    
    for footage_id in problematic_ids:
        status = check_footage_status(footage_id, token)
        print(status)
        print()

if __name__ == "__main__":
    main() 