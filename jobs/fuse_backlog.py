import sys, os, json, time
from pathlib import Path
import subprocess
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import warnings

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "status": "AutoLog_Status",
    "img_embedding": "AI_ImageEmbedding",
    "txt_embedding": "AI_TextEmbedding_CLIP",
    "fused_embedding": "AI_FusedEmbedding"
}

SLEEP_BETWEEN_RECORDS = 1  # Delay between individual record processing
TOKEN_REFRESH_INTERVAL = 300  # Refresh token every 5 minutes
MAX_CONNECTIONS = 5  # Limit concurrent connections to FileMaker
PROCESS_BATCH_SIZE = 25  # Process this many at a time before brief pause

class FileMakerSession:
    """Managed session for FileMaker API with connection limits and cleanup."""
    
    def __init__(self):
        self.session = None
        self.token = None
        self.token_time = 0
        self.create_session()
    
    def create_session(self):
        """Create a new session with connection limits and retry strategy."""
        if self.session:
            self.session.close()
        
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        # Configure HTTP adapter with connection limits
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=MAX_CONNECTIONS,
            pool_maxsize=MAX_CONNECTIONS,
            pool_block=True  # Block when pool is full instead of creating new connections
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Ensure connections are closed after use
        self.session.headers.update({'Connection': 'close'})
        
        print(f"🔄 Created new session with max {MAX_CONNECTIONS} connections")
    
    def get_token(self):
        """Get token with caching to avoid too many auth requests."""
        current_time = time.time()
        
        if not self.token or (current_time - self.token_time) > TOKEN_REFRESH_INTERVAL:
            self.token = config.get_token()
            self.token_time = current_time
            print(f"🔑 Refreshed FileMaker token")
        
        return self.token
    
    def make_request(self, method, url, **kwargs):
        """Make a request with proper session management."""
        kwargs.setdefault('verify', False)
        kwargs.setdefault('timeout', 30)
        
        # Add token to headers
        headers = kwargs.get('headers', {})
        headers.update(config.api_headers(self.get_token()))
        kwargs['headers'] = headers
        
        try:
            response = self.session.request(method, url, **kwargs)
            return response
        except Exception as e:
            print(f"❌ Request failed: {e}")
            raise
    
    def cleanup(self):
        """Explicit cleanup of session resources."""
        if self.session:
            self.session.close()
            self.session = None
            print("🧹 Session cleaned up")

def fetch_all_records(fm_session):
    """Fetch ALL records from FileMaker using the proven working approach."""
    print("📥 Fetching ALL records from FileMaker...")
    
    all_records = []
    
    # Get all records with any status using wildcard (this works!)
    print("📥 Fetching all records with any status...")
    offset = 0
    limit = 1000
    
    while True:
        try:
            # Build query - don't include offset if it's 0 (FileMaker requires offset > 0)
            query = {
                "query": [{"AutoLog_Status": "*"}],  # Wildcard works!
                "limit": limit
            }
            
            # Only add offset if it's greater than 0
            if offset > 0:
                query["offset"] = offset
            
            response = fm_session.make_request(
                'POST',
                config.url("layouts/Stills/_find"),
                json=query
            )
            
            if response.status_code == 200:
                batch_records = response.json().get('response', {}).get('data', [])
                
                if not batch_records:
                    break  # No more records
                
                all_records.extend(batch_records)
                print(f"📥 Fetched {len(batch_records)} records (total: {len(all_records)})")
                
                if len(batch_records) < limit:
                    break  # Last batch
                
                offset += limit
                
            elif response.status_code == 401:
                print("🔑 Token expired, refreshing...")
                fm_session.token = None  # Force token refresh
                continue
                
            elif response.status_code == 404:
                print("📝 No more records found")
                break
                
            else:
                print(f"❌ Unexpected response: HTTP {response.status_code}")
                print(f"Response: {response.text[:300]}...")
                break
                
        except Exception as e:
            print(f"❌ Error fetching records at offset {offset}: {e}")
            break
    
    print(f"✅ Fetched {len(all_records)} total records from FileMaker")
    return all_records

def should_process_record(record):
    """Determine if a record should be processed for fusion."""
    field_data = record.get('fieldData', {})
    
    # Get current status
    status = field_data.get(FIELD_MAPPING["status"], "")
    
    # Skip if already complete
    if status == "9 - Complete":
        return False, "Already complete"
    
    # Check if we have the required embeddings
    img_embedding = field_data.get(FIELD_MAPPING["img_embedding"], "")
    txt_embedding = field_data.get(FIELD_MAPPING["txt_embedding"], "")
    
    if not img_embedding or not txt_embedding:
        return False, "Missing required embeddings"
    
    # Check if already has fused embedding (might be a re-run)
    fused_embedding = field_data.get(FIELD_MAPPING["fused_embedding"], "")
    if fused_embedding and status == "9 - Complete":
        return False, "Already has fused embedding"
    
    # Ready to process
    return True, "Ready for fusion"

def process_all_records(fm_session, job_script_path, records):
    """Process all records in memory with minimal FileMaker API calls."""
    total_processed = 0
    total_errors = 0
    total_skipped = 0
    
    # Filter records that need processing
    records_to_process = []
    for record in records:
        should_process, reason = should_process_record(record)
        if should_process:
            records_to_process.append(record)
        else:
            total_skipped += 1
    
    print(f"🧠 Smart filtering complete:")
    print(f"   📋 Records to process: {len(records_to_process)}")
    print(f"   ⏭️ Records to skip: {total_skipped}")
    
    if not records_to_process:
        print("✅ No records need processing!")
        return total_processed, total_errors, total_skipped
    
    print(f"🚀 Starting to process {len(records_to_process)} records...")
    
    for i, record in enumerate(records_to_process):
        try:
            record_id = record['recordId']
            stills_id = record['fieldData'][FIELD_MAPPING["stills_id"]]
            
            print(f"📋 Processing {i+1}/{len(records_to_process)}: {stills_id}")
            
            # Call the individual job script
            result = subprocess.run([
                sys.executable, str(job_script_path), stills_id
            ], capture_output=True, text=True, timeout=90)
            
            if result.returncode == 0:
                # Success - update status to "9 - Complete"
                update_payload = {"fieldData": {FIELD_MAPPING["status"]: "9 - Complete"}}
                
                response = fm_session.make_request(
                    'PATCH',
                    config.url(f"layouts/Stills/records/{record_id}"),
                    json=update_payload
                )
                response.raise_for_status()
                
                print(f"✅ {stills_id}: Fused embedding updated and status set to 9 - Complete")
                total_processed += 1
            else:
                # Error occurred in the job script
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                print(f"❌ {stills_id}: {error_msg}")
                total_errors += 1
                
        except subprocess.TimeoutExpired:
            print(f"⏱️ {stills_id}: Job script timed out after 90 seconds")
            total_errors += 1
        except Exception as e:
            stills_id = record.get('fieldData', {}).get(FIELD_MAPPING['stills_id'], 'UNKNOWN')
            print(f"❌ {stills_id}: {e}")
            total_errors += 1
        
        # Brief pause between records
        time.sleep(SLEEP_BETWEEN_RECORDS)
        
        # Take a longer break every batch to avoid overwhelming FileMaker
        if (i + 1) % PROCESS_BATCH_SIZE == 0:
            print(f"😴 Brief pause after {i+1} records...")
            time.sleep(3)
    
    return total_processed, total_errors, total_skipped

if __name__ == "__main__":
    fm_session = FileMakerSession()
    
    try:
        # Get the path to the individual job script
        job_script_path = Path(__file__).parent / "stills_autolog_08_fuse_embeddings.py"
        
        print(f"🚀 Starting ONE-SHOT processing of ALL records")
        print(f"⏱️ {SLEEP_BETWEEN_RECORDS}s between records, 3s pause every {PROCESS_BATCH_SIZE} records")
        print(f"🧠 Smart filtering: Will skip already complete records and those missing embeddings")
        
        # ONE-SHOT: Fetch all records upfront
        all_records = fetch_all_records(fm_session)
        
        if not all_records:
            print("❌ No records found in database")
            exit(1)
        
        # Process all records in memory
        total_processed, total_errors, total_skipped = process_all_records(
            fm_session, job_script_path, all_records
        )
        
        print(f"\n🎉 ONE-SHOT processing complete!")
        print(f"📊 Final results:")
        print(f"   ✅ Processed: {total_processed}")
        print(f"   ❌ Errors: {total_errors}")
        print(f"   ⏭️ Skipped: {total_skipped}")
        print(f"   📋 Total records: {len(all_records)}")
        
    except KeyboardInterrupt:
        print("\n🛑 Process interrupted by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
    finally:
        print("🧹 Cleaning up session...")
        fm_session.cleanup() 