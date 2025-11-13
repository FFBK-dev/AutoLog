#!/usr/bin/env python3
"""
Regenerate Stills Thumbnails - Batch Job

Regenerates thumbnails for all Stills records using current methodology.
Reads from server files (SPECS_Filepath_Server) and creates 588x588 thumbnails.

This ensures all thumbnails are created with consistent methodology for
accurate embedding matching with REVERSE_IMAGE_SEARCH.
"""

import sys
import os
import warnings
import time
import concurrent.futures
from pathlib import Path
from PIL import Image, ImageFile

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Set PIL's maximum image size to handle very large images
Image.MAX_IMAGE_PIXELS = 1000000000
ImageFile.LOAD_TRUNCATED_IMAGES = True

__ARGS__ = []  # No arguments - processes all records

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "server_path": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail",
    "status": "AutoLog_Status"
}

def regenerate_thumbnail(record_id, stills_id, server_path, token):
    """Regenerate thumbnail for a single Stills record.
    
    Matches stills_autolog_02_copy_to_server.py methodology:
    - Server file is already JPEG quality 95
    - Just open it and create thumbnail directly
    """
    temp_path = None
    
    try:
        # Check if server file exists
        if not os.path.exists(server_path):
            print(f"  ⚠️  {stills_id}: Server file not found")
            return 'skipped'
        
        # Open server file (already JPEG quality 95) and create thumbnail
        # This EXACTLY matches stills_autolog_02_copy_to_server.py line 417-422
        with Image.open(server_path) as final_img:
            thumb_img = final_img.copy()
            thumb_img.thumbnail((588, 588), Image.Resampling.LANCZOS)
            
            temp_path = f"/tmp/thumb_{stills_id}_{int(time.time())}.jpg"
            thumb_img.save(temp_path, 'JPEG', quality=85)
        
        # Upload thumbnail with retry logic
        for attempt in range(3):
            try:
                config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], temp_path)
                
                # Set status to "6 - Generating Embeddings" to trigger embedding generation
                try:
                    import requests
                    payload = {"fieldData": {FIELD_MAPPING["status"]: "6 - Generating Embeddings"}}
                    response = requests.patch(
                        config.url(f"layouts/Stills/records/{record_id}"),
                        headers=config.api_headers(token),
                        json=payload,
                        verify=False,
                        timeout=30
                    )
                    response.raise_for_status()
                except Exception as status_error:
                    print(f"  ⚠️  {stills_id}: Thumbnail uploaded but status update failed - {status_error}")
                    return True  # Still count as success since thumbnail was uploaded
                
                print(f"  ✅ {stills_id}: Thumbnail regenerated + status set to 6")
                return True
            except Exception as upload_error:
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))  # Exponential backoff: 1s, 2s
                    continue
                else:
                    print(f"  ❌ {stills_id}: Upload failed after 3 attempts - {upload_error}")
                    return False
        
    except Exception as e:
        print(f"  ❌ {stills_id}: Error - {e}")
        return False
        
    finally:
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

def get_all_stills_records(token, limit=100, offset=1):
    """Get a batch of Stills records."""
    try:
        import requests
        
        # FileMaker requires offset > 0, so omit it for first batch
        if offset <= 1:
            url = config.url(f"layouts/Stills/records?_limit={limit}")
        else:
            url = config.url(f"layouts/Stills/records?_limit={limit}&_offset={offset}")
        
        response = requests.get(
            url,
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()['response']['data']
            print(f"    → Retrieved {len(data)} records from API")
            return data
        else:
            print(f"    ❌ API returned status {response.status_code}")
            return []
            
    except Exception as e:
        print(f"    ❌ Error fetching records: {e}")
        import traceback
        traceback.print_exc()
        return []

def process_batch(records, token):
    """Process a batch of records."""
    results = {'success': 0, 'failed': 0, 'skipped': 0}
    
    for record in records:
        record_id = record['recordId']
        field_data = record['fieldData']
        
        stills_id = field_data.get(FIELD_MAPPING["stills_id"])
        server_path = field_data.get(FIELD_MAPPING["server_path"])
        
        if not stills_id:
            results['skipped'] += 1
            continue
        
        if not server_path:
            print(f"  ⚠️  {stills_id}: No server path")
            results['skipped'] += 1
            continue
        
        # Regenerate thumbnail
        result = regenerate_thumbnail(record_id, stills_id, server_path, token)
        if result == True:
            results['success'] += 1
        elif result == 'skipped':
            results['skipped'] += 1
        else:
            results['failed'] += 1
        
        # Delay to avoid overwhelming the server
        time.sleep(0.3)  # Increased from 0.1 to 0.3 seconds
    
    return results

if __name__ == "__main__":
    try:
        print("="*60)
        print("STILLS - Regenerate All Thumbnails")
        print("="*60)
        print("This will regenerate thumbnails for ALL Stills records")
        print("using current methodology from server files.")
        print()
        
        # Check for --yes flag and optional start offset
        start_offset = 1
        if len(sys.argv) > 1 and sys.argv[1] == '--yes':
            print("Proceeding with --yes flag...")
            # Check for optional start offset
            if len(sys.argv) > 2:
                start_offset = int(sys.argv[2])
                print(f"Starting from offset: {start_offset}")
        else:
            print("Run with --yes flag to proceed:")
            print("  python3 jobs/stills_regenerate_thumbnails.py --yes [start_offset]")
            print("  Example: python3 jobs/stills_regenerate_thumbnails.py --yes 1425")
            sys.exit(0)
        
        token = config.get_token()
        print("🔑 Authentication token obtained")
        
        # Process in batches
        batch_size = 100
        offset = start_offset  # Start from specified offset
        total_results = {'success': 0, 'failed': 0, 'skipped': 0}
        
        print(f"\n🚀 Starting batch processing (batch size: {batch_size})")
        print("="*60)
        
        batch_num = 1
        while True:
            print(f"\n📦 Batch {batch_num} (offset {offset})...")
            records = get_all_stills_records(token, limit=batch_size, offset=offset)
            
            if not records:
                print(f"  No more records found")
                break
            
            print(f"  Processing {len(records)} records...")
            batch_results = process_batch(records, token)
            
            # Update totals
            total_results['success'] += batch_results['success']
            total_results['failed'] += batch_results['failed']
            total_results['skipped'] += batch_results['skipped']
            
            print(f"  Batch complete: ✅ {batch_results['success']} | ❌ {batch_results['failed']} | ⚠️  {batch_results['skipped']}")
            
            # If we got fewer records than batch size, we're done
            if len(records) < batch_size:
                break
            
            offset += batch_size
            batch_num += 1
        
        # Final summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Total records processed: {total_results['success'] + total_results['failed'] + total_results['skipped']}")
        print(f"✅ Successfully regenerated: {total_results['success']}")
        print(f"❌ Failed: {total_results['failed']}")
        print(f"⚠️  Skipped (no server file): {total_results['skipped']}")
        print()
        
        if total_results['success'] > 0:
            print("✅ Thumbnail regeneration complete!")
            print("   All thumbnails now use consistent methodology.")
        
        sys.exit(0)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

