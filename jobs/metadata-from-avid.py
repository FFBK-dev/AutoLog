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

# Field mappings for different layouts (reverse direction - Avid → FileMaker)
STILLS_FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "info_description": "INFO_Description", 
    "info_date": "INFO_Date",
    "info_source": "INFO_Source",
    "tags_list": "TAGS_List",
    "autolog_status": "AutoLog_Status"
}

FOOTAGE_FIELD_MAPPING = {
    "file_name": "INFO_Filename",
    "ftg_id": "INFO_FTG_ID",
    "info_description": "INFO_Description",
    "info_title": "INFO_Title",
    "info_location": "INFO_Location",
    "info_source": "INFO_Source",
    "info_date": "INFO_Date", 
    "tags_list": "TAGS_List",
    "autolog_status": "AutoLog_Status"
}

def update_stills_metadata(assets, token):
    """Update metadata for stills records by ID."""
    results = []
    processed_count = 0
    
    for asset in assets:
        try:
            identifier = asset.get("identifier")
            metadata = asset.get("metadata", {})
            
            if not identifier:
                results.append({
                    "identifier": "unknown",
                    "success": False,
                    "error": "Missing identifier"
                })
                continue
            
            # Find record by stills_id
            record_id = config.find_record_id(token, "Stills", {STILLS_FIELD_MAPPING["stills_id"]: identifier})
            
            if not record_id:
                results.append({
                    "identifier": identifier,
                    "success": False,
                    "error": "Record not found"
                })
                continue
            
            # Prepare field data for update
            field_data = {}
            
            # Map metadata fields to FileMaker fields
            if metadata.get("description"):
                field_data[STILLS_FIELD_MAPPING["info_description"]] = metadata["description"]
            
            if metadata.get("date"):
                field_data[STILLS_FIELD_MAPPING["info_date"]] = metadata["date"]
            
            if metadata.get("source"):
                field_data[STILLS_FIELD_MAPPING["info_source"]] = metadata["source"]
            
            if metadata.get("tags"):
                field_data[STILLS_FIELD_MAPPING["tags_list"]] = metadata["tags"]
            
            # Note: INFO_Name and INFO_Title fields don't exist in FileMaker Stills layout
            # These fields are skipped to avoid "Field is missing" errors
            
            # Update record if we have data to update
            if field_data:
                # Set status to trigger embedding regeneration since metadata changed
                field_data[STILLS_FIELD_MAPPING["autolog_status"]] = "6 - Generating Embeddings"
                
                payload = {"fieldData": field_data}
                
                response = requests.patch(
                    config.url(f"layouts/Stills/records/{record_id}"),
                    headers=config.api_headers(token),
                    json=payload,
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 401:
                    token = config.get_token()  # Refresh token
                    response = requests.patch(
                        config.url(f"layouts/Stills/records/{record_id}"),
                        headers=config.api_headers(token),
                        json=payload,
                        verify=False,
                        timeout=30
                    )
                
                response.raise_for_status()
                processed_count += 1
                
                results.append({
                    "identifier": identifier,
                    "success": True,
                    "fields_updated": list(field_data.keys())
                })
            else:
                results.append({
                    "identifier": identifier,
                    "success": True,
                    "fields_updated": [],
                    "message": "No metadata to update"
                })
            
        except Exception as e:
            results.append({
                "identifier": identifier if 'identifier' in locals() else "unknown",
                "success": False,
                "error": str(e)
            })
    
    return results, processed_count

def update_footage_metadata(assets, token, layout_name):
    """Update metadata for footage records by file name."""
    results = []
    processed_count = 0
    
    for asset in assets:
        try:
            identifier = asset.get("identifier")
            metadata = asset.get("metadata", {})
            
            if not identifier:
                results.append({
                    "identifier": "unknown",
                    "success": False,
                    "error": "Missing identifier"
                })
                continue
            
            # Find record by file name
            record_id = config.find_record_id(token, layout_name, {FOOTAGE_FIELD_MAPPING["file_name"]: identifier})
            
            if not record_id:
                results.append({
                    "identifier": identifier,
                    "success": False,
                    "error": "Record not found"
                })
                continue
            
            # Prepare field data for update
            field_data = {}
            
            # Map metadata fields to FileMaker fields
            if metadata.get("description"):
                field_data[FOOTAGE_FIELD_MAPPING["info_description"]] = metadata["description"]
            
            if metadata.get("title"):
                field_data[FOOTAGE_FIELD_MAPPING["info_title"]] = metadata["title"]
            
            if metadata.get("location"):
                field_data[FOOTAGE_FIELD_MAPPING["info_location"]] = metadata["location"]
            
            if metadata.get("source"):
                field_data[FOOTAGE_FIELD_MAPPING["info_source"]] = metadata["source"]
            
            if metadata.get("date"):
                field_data[FOOTAGE_FIELD_MAPPING["info_date"]] = metadata["date"]
            
            if metadata.get("tags"):
                field_data[FOOTAGE_FIELD_MAPPING["tags_list"]] = metadata["tags"]
            
            # Note: INFO_Name field doesn't exist in FileMaker Footage layout
            # INFO_Title DOES exist in Footage layout, so it will be updated
            # This field is skipped to avoid "Field is missing" errors
            
            # Update record if we have data to update
            if field_data:
                # Set status to trigger embedding regeneration since metadata changed
                field_data[FOOTAGE_FIELD_MAPPING["autolog_status"]] = "7 - Generating Embeddings"
                
                payload = {"fieldData": field_data}
                
                response = requests.patch(
                    config.url(f"layouts/{layout_name}/records/{record_id}"),
                    headers=config.api_headers(token),
                    json=payload,
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 401:
                    token = config.get_token()  # Refresh token
                    response = requests.patch(
                        config.url(f"layouts/{layout_name}/records/{record_id}"),
                        headers=config.api_headers(token),
                        json=payload,
                        verify=False,
                        timeout=30
                    )
                
                response.raise_for_status()
                processed_count += 1
                
                results.append({
                    "identifier": identifier,
                    "success": True,
                    "fields_updated": list(field_data.keys())
                })
            else:
                results.append({
                    "identifier": identifier,
                    "success": True,
                    "fields_updated": [],
                    "message": "No metadata to update"
                })
            
        except Exception as e:
            results.append({
                "identifier": identifier if 'identifier' in locals() else "unknown",
                "success": False,
                "error": str(e)
            })
    
    return results, processed_count

def main():
    """Main function to process metadata export from Avid to FileMaker."""
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
        assets = payload.get('assets', [])
        
        if not assets:
            print(json.dumps({"error": "No assets provided in payload"}))
            return False
        
        # Get FileMaker token
        token = config.get_token()
        
        # Process based on media type
        if media_type == 'stills':
            results, processed_count = update_stills_metadata(assets, token)
        elif media_type in ['archival', 'live_footage']:
            # Both archival and live footage are in the same Footage layout
            results, processed_count = update_footage_metadata(assets, token, "Footage")
        else:
            print(json.dumps({"error": f"Unsupported media type: {media_type}"}))
            return False
        
        # Calculate success rate
        successful_updates = sum(1 for result in results if result.get("success", False))
        total_assets = len(assets)
        
        # Return structured response
        response = {
            "success": successful_updates > 0,
            "message": f"Metadata exported successfully. {successful_updates}/{total_assets} assets updated, embedding regeneration triggered.",
            "processed_count": processed_count,
            "successful_count": successful_updates,
            "total_count": total_assets,
            "media_type": media_type,
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