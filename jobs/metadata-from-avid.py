#!/usr/bin/env python3
import sys
import warnings
import json
import requests
from pathlib import Path
from datetime import datetime
import time
from typing import Dict, List, Optional

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["payload_file"]  # Expect path to JSON payload file

def log_progress(message):
    """Print progress messages to stderr to avoid mixing with JSON output."""
    print(message, file=sys.stderr)

# Import the caching system from metadata-to-avid
# Cache for record ID mappings to reduce FileMaker API calls
class RecordIDCache:
    def __init__(self, ttl_seconds=300):  # 5 minute cache
        self.cache = {}
        self.ttl = ttl_seconds
    
    def _get_cache_key(self, layout: str, field_value: str) -> str:
        return f"{layout}:{field_value}"
    
    def get(self, layout: str, field_value: str) -> Optional[str]:
        key = self._get_cache_key(layout, field_value)
        if key in self.cache:
            record_id, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return record_id
            else:
                del self.cache[key]
        return None
    
    def set(self, layout: str, field_value: str, record_id: str):
        key = self._get_cache_key(layout, field_value)
        self.cache[key] = (record_id, time.time())
    
    def clear_expired(self):
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if current_time - timestamp >= self.ttl
        ]
        for key in expired_keys:
            del self.cache[key]

# Global cache instance
record_cache = RecordIDCache()

def batch_find_record_ids(token: str, layout: str, field_name: str, identifiers: List[str]) -> Dict[str, Optional[str]]:
    """
    Efficiently find multiple record IDs in a single API call using FileMaker's OR query syntax.
    
    Args:
        token: Authentication token
        layout: Layout name
        field_name: Field to search in
        identifiers: List of identifiers to find
    
    Returns:
        Dictionary mapping identifier -> record_id (None if not found)
    """
    log_progress(f"🔍 Batch lookup: Finding {len(identifiers)} records in {layout}")
    
    # Check cache first
    results = {}
    uncached_identifiers = []
    
    for identifier in identifiers:
        cached_id = record_cache.get(layout, identifier)
        if cached_id:
            results[identifier] = cached_id
        else:
            uncached_identifiers.append(identifier)
    
    if not uncached_identifiers:
        log_progress(f"✅ All {len(identifiers)} records found in cache")
        return results
    
    log_progress(f"🔄 Looking up {len(uncached_identifiers)} uncached records (found {len(results)} in cache)")
    
    try:
        # Build OR query for batch lookup
        query_conditions = [{field_name: identifier} for identifier in uncached_identifiers]
        
        response = requests.post(
            config.url(f"layouts/{layout}/_find"),
            headers=config.api_headers(token),
            json={
                "query": query_conditions,
                "limit": len(uncached_identifiers) + 10  # Small buffer
            },
            verify=False,
            timeout=30
        )
        
        if response.status_code == 401:
            token = config.get_token()  # Refresh token
            response = requests.post(
                config.url(f"layouts/{layout}/_find"),
                headers=config.api_headers(token),
                json={
                    "query": query_conditions,
                    "limit": len(uncached_identifiers) + 10
                },
                verify=False,
                timeout=30
            )
        
        if response.status_code == 404:
            # No records found - mark all as None
            for identifier in uncached_identifiers:
                results[identifier] = None
            log_progress(f"📋 No records found for any identifier")
            return results
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        # Create mapping from API results
        found_identifiers = set()
        for record in records:
            identifier = record['fieldData'].get(field_name)
            if identifier in uncached_identifiers:
                record_id = record['recordId']
                results[identifier] = record_id
                record_cache.set(layout, identifier, record_id)
                found_identifiers.add(identifier)
        
        # Mark not found items as None
        for identifier in uncached_identifiers:
            if identifier not in found_identifiers:
                results[identifier] = None
        
        log_progress(f"✅ Batch lookup complete: {len(found_identifiers)}/{len(uncached_identifiers)} found")
        return results
        
    except Exception as e:
        log_progress(f"❌ Batch lookup failed: {e}")
        # Fallback to individual lookups with cache
        for identifier in uncached_identifiers:
            try:
                record_id = config.find_record_id(token, layout, {field_name: identifier})
                results[identifier] = record_id
                record_cache.set(layout, identifier, record_id)
            except:
                results[identifier] = None
        return results

def convert_checkbox_to_text(value):
    """Convert FileMaker checkbox value to Yes/No text for Avid."""
    if value == "0":
        return "Yes"
    elif value == "1" or not value:
        return "No"
    else:
        return "No"  # Default to No for any other value

def convert_text_to_checkbox(value):
    """Convert Yes/No text from Avid to FileMaker checkbox value."""
    if isinstance(value, str):
        if value.lower().strip() == "yes":
            return "0"
        elif value.lower().strip() == "no":
            return "1"
    return "1"  # Default to No (1) for any other value

# Field mappings for different layouts (reverse direction - Avid → FileMaker)
STILLS_FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "info_description": "INFO_Description", 
    "info_date": "INFO_Date",
    "info_source": "INFO_Source",
    "tags_list": "TAGS_List",
    "info_reviewed_checkbox": "INFO_Reviewed_Checkbox",
    "avid_bins": "INFO_AvidBins",
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
    "info_color_mode": "INFO_ColorMode",
    "info_audio_type": "INFO_AudioType",
    "info_avid_description": "INFO_AvidDescription",
    "info_ff_project": "INFO_FF_Project",
    "info_reviewed_checkbox": "INFO_Reviewed_Checkbox",
    "avid_bins": "INFO_AvidBins",
    "time_of_day": "SPECS_TimeOfDay",
    "autolog_status": "AutoLog_Status"
}

def update_stills_metadata(assets, token):
    """Update metadata for stills records by ID using optimized batch processing."""
    log_progress(f"🚀 Updating {len(assets)} stills records")
    record_cache.clear_expired()  # Clean up expired cache entries
    
    results = []
    processed_count = 0
    
    # Step 1: Extract all identifiers and batch lookup record IDs
    identifiers = []
    asset_by_identifier = {}
    
    for asset in assets:
        identifier = asset.get("identifier")
        if identifier:
            identifiers.append(identifier)
            asset_by_identifier[identifier] = asset
        else:
            results.append({
                "identifier": "unknown",
                "success": False,
                "error": "Missing identifier"
            })
    
    if not identifiers:
        return results, processed_count
    
    # Batch lookup all record IDs
    record_id_mapping = batch_find_record_ids(
        token, "Stills", STILLS_FIELD_MAPPING["stills_id"], identifiers
    )
    
    # Step 2: Process found records in chunks
    found_assets = [(identifier, record_id, asset_by_identifier[identifier]) 
                   for identifier, record_id in record_id_mapping.items() if record_id]
    
    if found_assets:
        log_progress(f"📊 Updating {len(found_assets)} found records")
        
        # Process in chunks to avoid overwhelming FileMaker
        chunk_size = 10  # Smaller chunks for updates (more intensive than reads)
        for i in range(0, len(found_assets), chunk_size):
            chunk = found_assets[i:i + chunk_size]
            log_progress(f"📦 Processing update chunk {i//chunk_size + 1}: {len(chunk)} records")
            
            for identifier, record_id, asset in chunk:
                try:
                    metadata = asset.get("metadata", {})
                    
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
                    
                    if metadata.get("reviewed_checkbox"):
                        field_data[STILLS_FIELD_MAPPING["info_reviewed_checkbox"]] = convert_text_to_checkbox(metadata["reviewed_checkbox"])
                    
                    if metadata.get("avid_bins"):
                        field_data[STILLS_FIELD_MAPPING["avid_bins"]] = metadata["avid_bins"]
                    
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
                    log_progress(f"❌ Error updating record {record_id} for {identifier}: {e}")
                    results.append({
                        "identifier": identifier,
                        "success": False,
                        "error": str(e)
                    })
            
            # Small delay between chunks to be nice to FileMaker
            if i + chunk_size < len(found_assets):
                time.sleep(0.2)  # Slightly longer delay for updates
    
    # Step 3: Add not found records
    for identifier, record_id in record_id_mapping.items():
        if not record_id:
            results.append({
                "identifier": identifier,
                "success": False,
                "error": "Record not found"
            })
    
    log_progress(f"✅ Update completed: {processed_count} records successfully updated")
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
            
            if metadata.get("color_mode"):
                field_data[FOOTAGE_FIELD_MAPPING["info_color_mode"]] = metadata["color_mode"]
            
            if metadata.get("audio_type"):
                field_data[FOOTAGE_FIELD_MAPPING["info_audio_type"]] = metadata["audio_type"]
            
            if metadata.get("avid_description"):
                field_data[FOOTAGE_FIELD_MAPPING["info_avid_description"]] = metadata["avid_description"]
            
            if metadata.get("ff_project"):
                field_data[FOOTAGE_FIELD_MAPPING["info_ff_project"]] = metadata["ff_project"]
            
            if metadata.get("reviewed_checkbox"):
                field_data[FOOTAGE_FIELD_MAPPING["info_reviewed_checkbox"]] = convert_text_to_checkbox(metadata["reviewed_checkbox"])
            
            if metadata.get("avid_bins"):
                field_data[FOOTAGE_FIELD_MAPPING["avid_bins"]] = metadata["avid_bins"]
            
            if metadata.get("time_of_day"):
                field_data[FOOTAGE_FIELD_MAPPING["time_of_day"]] = metadata["time_of_day"]
            
            # Note: INFO_Name field doesn't exist in FileMaker Footage layout
            # INFO_Title DOES exist in Footage layout, so it will be updated
            # This field is skipped to avoid "Field is missing" errors
            
            # Update record if we have data to update
            if field_data:
                # Set status to trigger embedding regeneration since metadata changed
                field_data[FOOTAGE_FIELD_MAPPING["autolog_status"]] = "8 - Generating Embeddings"
                
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
        
        # Get FileMaker token (redirect status messages to stderr)
        original_stdout = sys.stdout
        sys.stdout = sys.stderr
        token = config.get_token()
        sys.stdout = original_stdout
        
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