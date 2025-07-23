#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
import requests

def check_footage_status(footage_id, token):
    """Check status and frame count for a footage ID."""
    try:
        record_id = config.find_record_id(token, "FOOTAGE", {"INFO_FTG_ID": f"=={footage_id}"})
        if not record_id:
            return f"{footage_id}: NOT_FOUND"
        
        response = requests.get(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()['response']['data'][0]['fieldData']
            status = data.get('AutoLog_Status', 'UNKNOWN')
            
            # Get frame count
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
            
            frame_count = 0
            if frame_response.status_code == 200:
                frame_records = frame_response.json()['response']['data']
                frame_count = len(frame_records)
            
            return f"{footage_id}: {status} ({frame_count} frames)"
        else:
            return f"{footage_id}: ERROR_{response.status_code}"
            
    except Exception as e:
        return f"{footage_id}: ERROR_{str(e)}"

def main():
    token = config.get_token()
    footage_ids = ['AF0001', 'AF0002', 'AF0003', 'AF0004', 'AF0005']
    
    print("Current status of test footage IDs:")
    print("-" * 50)
    
    for footage_id in footage_ids:
        status = check_footage_status(footage_id, token)
        print(status)

if __name__ == "__main__":
    main() 