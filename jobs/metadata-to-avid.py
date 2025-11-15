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

# Connection Pool Manager for high-volume requests
class ConnectionPoolManager:
    def __init__(self, max_pool_size=10, max_retries=5):
        import requests.adapters
        self.session = requests.Session()
        self.max_retries = max_retries
        
        # Configure connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=max_pool_size,
            pool_maxsize=max_pool_size,
            max_retries=requests.packages.urllib3.util.retry.Retry(
                total=max_retries,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504]
            )
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.05  # 50ms minimum between requests
    
    def make_request(self, method: str, url: str, **kwargs):
        """Make a rate-limited request using the connection pool."""
        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 30
        
        # Ensure verify=False is set
        kwargs['verify'] = False
        
        response = self.session.request(method, url, **kwargs)
        self.last_request_time = time.time()
        return response
    
    def close(self):
        """Close the session and clean up connections."""
        if self.session:
            self.session.close()

# Global instances
record_cache = RecordIDCache()
connection_pool = ConnectionPoolManager(max_pool_size=20)  # Larger pool for 200-item loads

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
        # Build OR query for batch lookup - split into smaller chunks for large requests
        max_chunk_size = 50  # FileMaker performs better with smaller OR queries
        all_records = []
        
        for i in range(0, len(uncached_identifiers), max_chunk_size):
            chunk = uncached_identifiers[i:i + max_chunk_size]
            query_conditions = [{field_name: identifier} for identifier in chunk]
            
            log_progress(f"  🔍 Querying chunk {i//max_chunk_size + 1}: {len(chunk)} identifiers")
            
            response = connection_pool.make_request(
                'POST',
                config.url(f"layouts/{layout}/_find"),
                headers=config.api_headers(token),
                json={
                    "query": query_conditions,
                    "limit": len(chunk) + 10  # Small buffer
                },
                timeout=45  # Longer timeout for larger queries
            )
            
            if response.status_code == 401:
                log_progress(f"  🔑 Token expired, refreshing...")
                token = config.get_token()  # Refresh token
                response = connection_pool.make_request(
                    'POST',
                    config.url(f"layouts/{layout}/_find"),
                    headers=config.api_headers(token),
                    json={
                        "query": query_conditions,
                        "limit": len(chunk) + 10
                    },
                    timeout=45
                )
            
            if response.status_code == 404:
                # No records found in this chunk - continue to next chunk
                log_progress(f"  📋 No records found in chunk {i//max_chunk_size + 1}")
                continue
            
            response.raise_for_status()
            chunk_records = response.json()['response']['data']
            all_records.extend(chunk_records)
            
            # Small delay between chunks for large requests
            if len(uncached_identifiers) > max_chunk_size and i + max_chunk_size < len(uncached_identifiers):
                time.sleep(0.1)
        
        # Process all collected records
        if not all_records:
            # No records found - mark all as None
            for identifier in uncached_identifiers:
                results[identifier] = None
            log_progress(f"📋 No records found for any identifier")
            return results
        
        # Create mapping from API results
        found_identifiers = set()
        for record in all_records:
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

# Field mappings for different layouts
STILLS_FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "info_description": "INFO_Description", 
    "info_date": "INFO_Date",
    "info_source": "INFO_Source",
    "tags_list": "TAGS_List",
    "info_reviewed_checkbox": "INFO_Reviewed_Checkbox",
    "avid_bins": "INFO_AvidBins"
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
    "avid_bins": "INFO_AvidBins"
}

def get_stills_metadata(stills_ids, token):
    """Fetch metadata for stills records by ID using optimized batch processing."""
    total_count = len(stills_ids)
    log_progress(f"🚀 Processing {total_count} stills records")
    record_cache.clear_expired()  # Clean up expired cache entries
    
    # Step 1: Batch lookup all record IDs
    record_id_mapping = batch_find_record_ids(
        token, "Stills", STILLS_FIELD_MAPPING["stills_id"], stills_ids
    )
    
    # Step 2: Batch fetch record data for found records
    results = []
    found_record_ids = [(stills_id, record_id) for stills_id, record_id in record_id_mapping.items() if record_id]
    
    if found_record_ids:
        log_progress(f"📊 Fetching metadata for {len(found_record_ids)} found records")
        
        # Dynamic chunk size based on total load
        if total_count <= 50:
            chunk_size = 25  # Standard chunk size
        elif total_count <= 100:
            chunk_size = 20  # Smaller chunks for medium loads
        else:
            chunk_size = 15  # Even smaller chunks for large loads (200+ items)
        
        log_progress(f"📦 Using chunk size: {chunk_size} (optimized for {total_count} items)")
        
        for i in range(0, len(found_record_ids), chunk_size):
            chunk = found_record_ids[i:i + chunk_size]
            chunk_num = i//chunk_size + 1
            total_chunks = (len(found_record_ids) + chunk_size - 1) // chunk_size
            log_progress(f"📦 Processing chunk {chunk_num}/{total_chunks}: {len(chunk)} records")
            
            for stills_id, record_id in chunk:
                try:
                    # Get record data using connection pool
                    response = connection_pool.make_request(
                        'GET',
                        config.url(f"layouts/Stills/records/{record_id}"),
                        headers=config.api_headers(token),
                        timeout=30
                    )
                    
                    if response.status_code == 401:
                        token = config.get_token()  # Refresh token
                        response = connection_pool.make_request(
                            'GET',
                            config.url(f"layouts/Stills/records/{record_id}"),
                            headers=config.api_headers(token),
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
                        "tags_list": record_data.get(STILLS_FIELD_MAPPING["tags_list"], ""),
                        "info_reviewed_checkbox": convert_checkbox_to_text(record_data.get(STILLS_FIELD_MAPPING["info_reviewed_checkbox"], "")),
                        "info_avid_bins": record_data.get(STILLS_FIELD_MAPPING["avid_bins"], "")
                    }
                    
                    results.append(metadata)
                    
                except Exception as e:
                    log_progress(f"❌ Error fetching record {record_id} for {stills_id}: {e}")
                    results.append({
                        "identifier": stills_id,
                        "found": False,
                        "error": str(e)
                    })
            
            # Progress tracking
            processed_so_far = min(i + chunk_size, len(found_record_ids))
            progress_percent = (processed_so_far / len(found_record_ids)) * 100
            log_progress(f"📈 Progress: {processed_so_far}/{len(found_record_ids)} ({progress_percent:.1f}%)")
            
            # Dynamic delay between chunks based on load size
            if i + chunk_size < len(found_record_ids):
                if total_count > 100:
                    time.sleep(0.2)  # Longer delay for large loads
                else:
                    time.sleep(0.1)  # Standard delay
    
    # Step 3: Add not found records
    for stills_id, record_id in record_id_mapping.items():
        if not record_id:
            results.append({
                "identifier": stills_id,
                "found": False,
                "error": "Record not found"
            })
    
    log_progress(f"✅ Completed: {len([r for r in results if r['found']])}/{len(stills_ids)} records found")
    return results

def get_footage_metadata(file_names, token, layout_name):
    """Fetch metadata for footage records by file name using optimized batch processing."""
    log_progress(f"🚀 Processing {len(file_names)} footage records in {layout_name}")
    record_cache.clear_expired()  # Clean up expired cache entries
    
    # Step 1: Batch lookup all record IDs
    record_id_mapping = batch_find_record_ids(
        token, layout_name, FOOTAGE_FIELD_MAPPING["file_name"], file_names
    )
    
    # Step 2: Batch fetch record data for found records
    results = []
    found_record_ids = [(file_name, record_id) for file_name, record_id in record_id_mapping.items() if record_id]
    
    if found_record_ids:
        log_progress(f"📊 Fetching metadata for {len(found_record_ids)} found records")
        
        # Process in chunks to avoid overwhelming FileMaker
        chunk_size = 25  # Process 25 records at a time
        for i in range(0, len(found_record_ids), chunk_size):
            chunk = found_record_ids[i:i + chunk_size]
            log_progress(f"📦 Processing chunk {i//chunk_size + 1}: {len(chunk)} records")
            
            for file_name, record_id in chunk:
                try:
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
                        "tags_list": record_data.get(FOOTAGE_FIELD_MAPPING["tags_list"], ""),
                        "info_color_mode": record_data.get(FOOTAGE_FIELD_MAPPING["info_color_mode"], ""),
                        "info_audio_type": record_data.get(FOOTAGE_FIELD_MAPPING["info_audio_type"], ""),
                        "info_avid_description": record_data.get(FOOTAGE_FIELD_MAPPING["info_avid_description"], ""),
                        "info_ff_project": record_data.get(FOOTAGE_FIELD_MAPPING["info_ff_project"], ""),
                        "info_reviewed_checkbox": convert_checkbox_to_text(record_data.get(FOOTAGE_FIELD_MAPPING["info_reviewed_checkbox"], "")),
                        "info_avid_bins": record_data.get(FOOTAGE_FIELD_MAPPING["avid_bins"], "")
                    }
                    
                    results.append(metadata)
                    
                except Exception as e:
                    log_progress(f"❌ Error fetching record {record_id} for {file_name}: {e}")
                    results.append({
                        "identifier": file_name,
                        "found": False,
                        "error": str(e)
                    })
            
            # Small delay between chunks to be nice to FileMaker
            if i + chunk_size < len(found_record_ids):
                time.sleep(0.1)
    
    # Step 3: Add not found records
    for file_name, record_id in record_id_mapping.items():
        if not record_id:
            results.append({
                "identifier": file_name,
                "found": False,
                "error": "Record not found"
            })
    
    log_progress(f"✅ Completed: {len([r for r in results if r['found']])}/{len(file_names)} records found")
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
        
        # Get FileMaker token (redirect status messages to stderr)
        original_stdout = sys.stdout
        sys.stdout = sys.stderr
        token = config.get_token()
        sys.stdout = original_stdout
        
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