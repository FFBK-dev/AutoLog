#!/usr/bin/env python3
"""
Simple batch thumbnail standardization - no prompts, just runs
"""

import sys
import os
import warnings
import time
from pathlib import Path
from datetime import datetime
from PIL import Image
import requests

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "server_path": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail"
}

# Settings
THUMBNAIL_MAX_SIZE = (588, 588)
THUMBNAIL_QUALITY = 85
DELAY_BETWEEN_RECORDS = 0.3  # Increased from 0.2 to 0.3s for better rate limiting
BATCH_SIZE = 100

def fetch_records(token, limit=None):
    """Fetch records with server paths."""
    print(f"\n🔍 Fetching records from FileMaker...")
    
    all_records = []
    offset = 1
    
    while True:
        try:
            response = requests.get(
                config.url(f"layouts/Stills/records"),
                headers=config.api_headers(token),
                params={'_offset': offset, '_limit': BATCH_SIZE},
                verify=False,
                timeout=60
            )
            
            if response.status_code != 200:
                break
            
            data = response.json()
            records = data['response']['data']
            
            if not records:
                break
            
            for record in records:
                field_data = record['fieldData']
                stills_id = field_data.get(FIELD_MAPPING['stills_id'])
                server_path = field_data.get(FIELD_MAPPING['server_path'])
                
                if stills_id and server_path:
                    all_records.append({
                        'stills_id': stills_id,
                        'record_id': record['recordId'],
                        'server_path': server_path
                    })
            
            offset += BATCH_SIZE
            
            if limit and len(all_records) >= limit:
                all_records = all_records[:limit]
                break
            
            time.sleep(0.5)  # Delay between batch fetches
            
        except Exception as e:
            print(f"❌ Error fetching: {e}")
            break
    
    print(f"✅ Found {len(all_records)} records with server paths")
    return all_records

def standardize_one(record_info, token):
    """Standardize a single thumbnail."""
    stills_id = record_info['stills_id']
    record_id = record_info['record_id']
    server_path = record_info['server_path']
    
    try:
        if not os.path.exists(server_path):
            return {'success': False, 'error': 'File not found', 'skipped': True}
        
        with Image.open(server_path) as img:
            # Convert to RGB if needed
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Create thumbnail
            thumb_img = img.copy()
            thumb_img.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
            
            # Save temp
            temp_thumb = f"/tmp/batch_thumb_{stills_id}.jpg"
            thumb_img.save(temp_thumb, 'JPEG', quality=THUMBNAIL_QUALITY)
            
            thumb_size = thumb_img.size
            thumb_file_size = os.path.getsize(temp_thumb)
            
            # Upload
            config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], temp_thumb)
            
            # Cleanup
            os.remove(temp_thumb)
            
            return {
                'success': True,
                'thumb_size': thumb_size,
                'thumb_file_size': thumb_file_size
            }
    
    except Exception as e:
        return {'success': False, 'error': str(e)}

def process_batch(records, token):
    """Process all records."""
    print(f"\n{'='*80}")
    print(f"PROCESSING {len(records)} RECORDS")
    print(f"{'='*80}")
    print(f"Delay between records: {DELAY_BETWEEN_RECORDS}s")
    
    stats = {'successful': 0, 'failed': 0, 'skipped': 0}
    start_time = datetime.now()
    
    for i, record_info in enumerate(records):
        stills_id = record_info['stills_id']
        
        print(f"\n[{i+1}/{len(records)}] {stills_id}...", end=' ', flush=True)
        
        result = standardize_one(record_info, token)
        
        if result['success']:
            stats['successful'] += 1
            if 'thumb_size' in result:
                print(f"✅ {result['thumb_size'][0]}x{result['thumb_size'][1]} ({result['thumb_file_size']:,}b)")
            else:
                print(f"✅")
        elif result.get('skipped'):
            stats['skipped'] += 1
            print(f"⏭️  {result.get('error', 'skipped')}")
        else:
            stats['failed'] += 1
            print(f"❌ {result.get('error', 'failed')}")
        
        # Rate limiting delay
        time.sleep(DELAY_BETWEEN_RECORDS)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    print(f"\n{'='*80}")
    print(f"COMPLETED")
    print(f"{'='*80}")
    print(f"✅ Successful: {stats['successful']}")
    print(f"❌ Failed: {stats['failed']}")
    print(f"⏭️  Skipped: {stats['skipped']}")
    print(f"⏱️  Duration: {duration:.1f}s ({len(records)/duration:.1f} records/sec)")
    
    return stats

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=20, help='Number of records (default: 20)')
    args = parser.parse_args()
    
    print("="*80)
    print(f"THUMBNAIL STANDARDIZATION TEST - {args.limit} RECORDS")
    print("="*80)
    print(f"Settings: {THUMBNAIL_MAX_SIZE[0]}px max, {THUMBNAIL_QUALITY}% quality")
    
    token = config.get_token()
    records = fetch_records(token, limit=args.limit)
    
    if not records:
        print("❌ No records to process")
        sys.exit(1)
    
    stats = process_batch(records, token)
    
    print(f"\n✅ Test complete!")
    if stats['failed'] == 0:
        print(f"   Ready to process remaining ~{8800 - args.limit} records")
    else:
        print(f"   ⚠️  Some failures - review before continuing")

