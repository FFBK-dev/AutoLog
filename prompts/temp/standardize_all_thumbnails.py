#!/usr/bin/env python3
"""
Comprehensive Thumbnail Standardization for Entire Database
Safely processes all records to ensure consistent thumbnails for reliable embeddings
"""

import sys
import os
import warnings
import time
import json
from pathlib import Path
from datetime import datetime
from PIL import Image

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
import requests

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "server_path": "SPECS_Filepath_Server",
    "thumbnail": "SPECS_Thumbnail"
}

# STANDARD THUMBNAIL SETTINGS
THUMBNAIL_MAX_SIZE = (588, 588)
THUMBNAIL_QUALITY = 85
THUMBNAIL_RESAMPLING = Image.Resampling.LANCZOS

# PROCESSING SETTINGS
BATCH_SIZE = 100  # Records per batch fetch
DELAY_BETWEEN_RECORDS = 0.2  # Seconds between processing each record
DELAY_BETWEEN_BATCHES = 2.0  # Seconds between batch fetches

# PROGRESS TRACKING
PROGRESS_FILE = "/tmp/thumbnail_standardization_progress.json"

def load_progress():
    """Load progress from previous run if it exists."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_progress(progress):
    """Save progress to allow resuming."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def get_all_record_ids(token, offset=1, limit=None):
    """Get all record IDs with server paths."""
    print(f"\n{'='*80}")
    print("FETCHING RECORD LIST")
    print(f"{'='*80}")
    
    all_records = []
    current_offset = offset
    
    while True:
        print(f"\nFetching batch at offset {current_offset}...")
        
        try:
            response = requests.get(
                config.url(f"layouts/Stills/records"),
                headers=config.api_headers(token),
                params={
                    '_offset': current_offset,
                    '_limit': BATCH_SIZE
                },
                verify=False,
                timeout=60
            )
            
            if response.status_code != 200:
                print(f"   ⚠️  Error fetching batch: {response.status_code}")
                break
            
            data = response.json()
            records = data['response']['data']
            
            if not records:
                print(f"   ℹ️  No more records")
                break
            
            # Extract relevant info
            for record in records:
                field_data = record['fieldData']
                stills_id = field_data.get(FIELD_MAPPING['stills_id'])
                server_path = field_data.get(FIELD_MAPPING['server_path'])
                record_id = record['recordId']
                
                # Only include records with server paths
                if stills_id and server_path:
                    all_records.append({
                        'stills_id': stills_id,
                        'record_id': record_id,
                        'server_path': server_path
                    })
            
            print(f"   ✅ Found {len(records)} records ({len(all_records)} total with server paths)")
            
            current_offset += BATCH_SIZE
            
            # Optional limit for testing
            if limit and len(all_records) >= limit:
                all_records = all_records[:limit]
                break
            
            # Delay between batches
            time.sleep(DELAY_BETWEEN_BATCHES)
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            break
    
    return all_records

def standardize_thumbnail(record_info, token):
    """Standardize a single thumbnail."""
    stills_id = record_info['stills_id']
    record_id = record_info['record_id']
    server_path = record_info['server_path']
    
    try:
        # Check if server file exists
        if not os.path.exists(server_path):
            return {
                'stills_id': stills_id,
                'success': False,
                'error': 'Server file not found',
                'skipped': True
            }
        
        # Open and process the image
        with Image.open(server_path) as img:
            original_size = img.size
            
            # Convert mode if needed
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Create thumbnail
            thumb_img = img.copy()
            thumb_img.thumbnail(THUMBNAIL_MAX_SIZE, THUMBNAIL_RESAMPLING)
            
            # Save to temp file
            temp_thumb = f"/tmp/batch_thumb_{stills_id}.jpg"
            thumb_img.save(temp_thumb, 'JPEG', quality=THUMBNAIL_QUALITY)
            
            thumb_size = thumb_img.size
            thumb_file_size = os.path.getsize(temp_thumb)
            
            # Upload to FileMaker
            config.upload_to_container(token, "Stills", record_id, FIELD_MAPPING['thumbnail'], temp_thumb)
            
            # Clean up
            os.remove(temp_thumb)
            
            return {
                'stills_id': stills_id,
                'success': True,
                'original_size': original_size,
                'thumb_size': thumb_size,
                'thumb_file_size': thumb_file_size,
                'skipped': False
            }
        
    except Exception as e:
        return {
            'stills_id': stills_id,
            'success': False,
            'error': str(e),
            'skipped': False
        }

def process_all_records(records, token, start_index=0, dry_run=False):
    """Process all records with progress tracking."""
    print(f"\n{'='*80}")
    print(f"PROCESSING {len(records)} RECORDS")
    print(f"{'='*80}")
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
    
    print(f"Starting at index {start_index}")
    print(f"Delay between records: {DELAY_BETWEEN_RECORDS}s")
    
    stats = {
        'total': len(records),
        'processed': 0,
        'successful': 0,
        'failed': 0,
        'skipped': 0,
        'start_time': datetime.now().isoformat(),
        'start_index': start_index
    }
    
    results = []
    
    for i in range(start_index, len(records)):
        record_info = records[i]
        stills_id = record_info['stills_id']
        
        print(f"\n[{i+1}/{len(records)}] Processing {stills_id}...")
        
        if dry_run:
            print(f"   [DRY RUN] Would process: {record_info['server_path'][:60]}...")
            result = {'stills_id': stills_id, 'success': True, 'skipped': False}
        else:
            result = standardize_thumbnail(record_info, token)
        
        results.append(result)
        stats['processed'] += 1
        
        if result['success']:
            stats['successful'] += 1
            if not result.get('skipped'):
                print(f"   ✅ Success")
                if not dry_run and 'thumb_size' in result:
                    print(f"      Thumbnail: {result['thumb_size'][0]}x{result['thumb_size'][1]} ({result['thumb_file_size']:,} bytes)")
            else:
                stats['skipped'] += 1
                print(f"   ⏭️  Skipped: {result.get('error', 'Unknown')}")
        else:
            stats['failed'] += 1
            print(f"   ❌ Failed: {result.get('error', 'Unknown')}")
        
        # Progress update every 10 records
        if (i + 1) % 10 == 0:
            elapsed = (datetime.now() - datetime.fromisoformat(stats['start_time'])).total_seconds()
            rate = stats['processed'] / elapsed if elapsed > 0 else 0
            remaining = len(records) - (i + 1)
            eta_seconds = remaining / rate if rate > 0 else 0
            
            print(f"\n📊 Progress: {i+1}/{len(records)} ({(i+1)/len(records)*100:.1f}%)")
            print(f"   ✅ Successful: {stats['successful']}")
            print(f"   ❌ Failed: {stats['failed']}")
            print(f"   ⏭️  Skipped: {stats['skipped']}")
            print(f"   ⚡ Rate: {rate:.1f} records/second")
            print(f"   ⏱️  ETA: {eta_seconds/60:.1f} minutes")
            
            # Save progress
            if not dry_run:
                progress = {
                    'last_index': i,
                    'stats': stats,
                    'timestamp': datetime.now().isoformat()
                }
                save_progress(progress)
        
        # Delay between records
        if not dry_run:
            time.sleep(DELAY_BETWEEN_RECORDS)
    
    stats['end_time'] = datetime.now().isoformat()
    return stats, results

def print_final_report(stats, results):
    """Print comprehensive final report."""
    print(f"\n{'='*80}")
    print("FINAL REPORT")
    print(f"{'='*80}")
    
    start = datetime.fromisoformat(stats['start_time'])
    end = datetime.fromisoformat(stats['end_time'])
    duration = (end - start).total_seconds()
    
    print(f"\n⏱️  Duration: {duration/60:.1f} minutes ({duration:.1f} seconds)")
    print(f"⚡ Average rate: {stats['processed']/duration:.1f} records/second")
    
    print(f"\n📊 Results:")
    print(f"   Total records: {stats['total']}")
    print(f"   Processed: {stats['processed']}")
    print(f"   Successful: {stats['successful']} ({stats['successful']/stats['processed']*100:.1f}%)")
    print(f"   Failed: {stats['failed']} ({stats['failed']/stats['processed']*100 if stats['processed'] > 0 else 0:.1f}%)")
    print(f"   Skipped: {stats['skipped']} ({stats['skipped']/stats['processed']*100 if stats['processed'] > 0 else 0:.1f}%)")
    
    # Show failures if any
    if stats['failed'] > 0:
        print(f"\n❌ Failed Records:")
        failed = [r for r in results if not r['success'] and not r.get('skipped')]
        for r in failed[:20]:  # Show first 20
            print(f"   - {r['stills_id']}: {r.get('error', 'Unknown')}")
        if len(failed) > 20:
            print(f"   ... and {len(failed) - 20} more")
    
    # Show skipped if any
    if stats['skipped'] > 0:
        print(f"\n⏭️  Skipped Records (no server file):")
        skipped = [r for r in results if r.get('skipped')]
        for r in skipped[:20]:  # Show first 20
            print(f"   - {r['stills_id']}")
        if len(skipped) > 20:
            print(f"   ... and {len(skipped) - 20} more")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Standardize all thumbnails in the database')
    parser.add_argument('--dry-run', action='store_true', help='Run without making changes')
    parser.add_argument('--resume', action='store_true', help='Resume from last saved progress')
    parser.add_argument('--limit', type=int, help='Limit number of records (for testing)')
    parser.add_argument('--start-offset', type=int, default=1, help='Starting record offset')
    
    args = parser.parse_args()
    
    print("="*80)
    print("COMPREHENSIVE THUMBNAIL STANDARDIZATION")
    print("="*80)
    print(f"\nSettings:")
    print(f"  Max dimension: {THUMBNAIL_MAX_SIZE[0]} pixels")
    print(f"  JPEG quality: {THUMBNAIL_QUALITY}%")
    print(f"  Resampling: LANCZOS")
    print(f"  Delay between records: {DELAY_BETWEEN_RECORDS}s")
    print(f"  Dry run: {args.dry_run}")
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
    
    # Get FileMaker token
    token = config.get_token()
    
    # Check for resume
    start_index = 0
    records = None
    
    if args.resume:
        progress = load_progress()
        if progress:
            print(f"\n📂 Found saved progress from {progress['timestamp']}")
            print(f"   Last processed index: {progress['last_index']}")
            response = input("Resume from this point? (y/n): ")
            if response.lower() == 'y':
                start_index = progress['last_index'] + 1
                print(f"   Resuming from index {start_index}")
    
    # Fetch all records
    if not records:
        records = get_all_record_ids(token, offset=args.start_offset, limit=args.limit)
    
    print(f"\n✅ Found {len(records)} records with server paths")
    
    if len(records) == 0:
        print("\n❌ No records to process")
        sys.exit(0)
    
    # Confirm before proceeding
    if not args.dry_run:
        print(f"\n⚠️  This will standardize thumbnails for {len(records)} records")
        print(f"   Estimated time: {len(records) * DELAY_BETWEEN_RECORDS / 60:.1f} minutes")
        response = input("\nProceed? (y/n): ")
        if response.lower() != 'y':
            print("Aborted")
            sys.exit(0)
    
    # Process all records
    stats, results = process_all_records(records, token, start_index=start_index, dry_run=args.dry_run)
    
    # Print final report
    print_final_report(stats, results)
    
    # Clean up progress file on successful completion
    if not args.dry_run and stats['processed'] == len(records):
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            print(f"\n✅ Progress file cleaned up")
    
    print(f"\n{'='*80}")
    print("NEXT STEP: Regenerate all embeddings in FileMaker")
    print(f"{'='*80}")

