#!/usr/bin/env python3
import sys
import warnings
import json
import requests
from pathlib import Path
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["payload_file"]  # Expect path to JSON payload file

# Field mappings for different layouts
STILLS_FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "info_description": "INFO_Description", 
    "info_date": "INFO_Date",
    "info_source": "INFO_Source",
    "tags_list": "TAGS_List"
}

FOOTAGE_FIELD_MAPPING = {
    "file_name": "INFO_Filename",
    "ftg_id": "INFO_FTG_ID",
    "info_description": "INFO_Description",
    "info_title": "INFO_Title",
    "info_location": "INFO_Location",
    "info_source": "INFO_Source",
    "info_date": "INFO_Date", 
    "tags_list": "TAGS_List"
}

def get_stills_metadata(stills_ids, token):
    """Fetch metadata for stills records by ID."""
    results = []
    
    for stills_id in stills_ids:
        try:
            # Find record by stills_id
            record_id = config.find_record_id(token, "Stills", {STILLS_FIELD_MAPPING["stills_id"]: stills_id})
            
            if not record_id:
                results.append({
                    "identifier": stills_id,
                    "found": False,
                    "error": "Record not found"
                })
                continue
            
            # Get record data
            response = requests.get(
                config.url(f"layouts/Stills/records/{record_id}"),
                headers=config.api_headers(token),
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                token = config.get_token()  # Refresh token
                response = requests.get(
                    config.url(f"layouts/Stills/records/{record_id}"),
                    headers=config.api_headers(token),
                    verify=False,
                    timeout=30
                )
            
            response.raise_for_status()
            record_data = response.json()['response']['data'][0]['fieldData']
            
            # Extract requested fields
            metadata = {
                "identifier": stills_id,
                "found": True,
                "info_description": record_data.get(STILLS_FIELD_MAPPING["info_description"], ""),
                "info_date": record_data.get(STILLS_FIELD_MAPPING["info_date"], ""),
                "info_source": record_data.get(STILLS_FIELD_MAPPING["info_source"], ""),
                "tags_list": record_data.get(STILLS_FIELD_MAPPING["tags_list"], "")
            }
            
            results.append(metadata)
            
        except Exception as e:
            results.append({
                "identifier": stills_id,
                "found": False,
                "error": str(e)
            })
    
    return results

def get_footage_metadata(file_names, token, layout_name):
    """Fetch metadata for footage records by file name."""
    results = []
    
    for file_name in file_names:
        try:
            # Find record by file name
            record_id = config.find_record_id(token, layout_name, {FOOTAGE_FIELD_MAPPING["file_name"]: file_name})
            
            if not record_id:
                results.append({
                    "identifier": file_name,
                    "found": False,
                    "error": "Record not found"
                })
                continue
            
            # Get record data
            response = requests.get(
                config.url(f"layouts/{layout_name}/records/{record_id}"),
                headers=config.api_headers(token),
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                token = config.get_token()  # Refresh token
                response = requests.get(
                    config.url(f"layouts/{layout_name}/records/{record_id}"),
                    headers=config.api_headers(token),
                    verify=False,
                    timeout=30
                )
            
            response.raise_for_status()
            record_data = response.json()['response']['data'][0]['fieldData']
            
            # Extract requested fields
            metadata = {
                "identifier": file_name,
                "found": True,
                "ftg_id": record_data.get(FOOTAGE_FIELD_MAPPING["ftg_id"], ""),
                "info_description": record_data.get(FOOTAGE_FIELD_MAPPING["info_description"], ""),
                "info_title": record_data.get(FOOTAGE_FIELD_MAPPING["info_title"], ""),
                "info_location": record_data.get(FOOTAGE_FIELD_MAPPING["info_location"], ""),
                "info_source": record_data.get(FOOTAGE_FIELD_MAPPING["info_source"], ""),
                "info_date": record_data.get(FOOTAGE_FIELD_MAPPING["info_date"], ""),
                "tags_list": record_data.get(FOOTAGE_FIELD_MAPPING["tags_list"], "")
            }
            
            results.append(metadata)
            
        except Exception as e:
            results.append({
                "identifier": file_name,
                "found": False,
                "error": str(e)
            })
    
    return results

def main():
    """Main function to process metadata bridge requests."""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No payload file provided"}))
        return False
    
    try:
        # Read and parse the JSON payload from file
        payload_file = sys.argv[1]
        with open(payload_file, 'r') as f:
            payload = json.load(f)
        
        # Extract parameters
        media_type = payload.get('media_type')
        identifiers = payload.get('identifiers', [])
        
        # Get FileMaker token
        token = config.get_token()
        
        # Process based on media type
        if media_type == 'stills':
            results = get_stills_metadata(identifiers, token)
        elif media_type in ['archival', 'live_footage']:
            # Both archival and live footage are in the same Footage layout
            results = get_footage_metadata(identifiers, token, "Footage")
        else:
            print(json.dumps({"error": f"Unsupported media type: {media_type}"}))
            return False
        
        # Return structured response
        response = {
            "media_type": media_type,
            "requested_identifiers": identifiers,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
        
        print(json.dumps(response, indent=2))
        return True
        
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON payload: {str(e)}"}))
        return False
    except Exception as e:
        print(json.dumps({"error": f"Processing error: {str(e)}"}))
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(json.dumps({"error": f"Critical error: {str(e)}"}))
        sys.exit(1) 