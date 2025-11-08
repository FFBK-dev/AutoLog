#!/usr/bin/env python3
"""
Production batch thumbnail standardization with comprehensive logging and API monitoring
"""

import sys
import os
import warnings
import time
import json
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
DELAY_BETWEEN_RECORDS = 0.3
BATCH_SIZE = 100

# Logging
LOG_FILE = "/tmp/thumbnail_standardization.log"
PROGRESS_FILE = "/tmp/thumbnail_standardization_progress.json"

# API error tracking
API_ERROR_THRESHOLD = 5  # Stop if we get 5 consecutive API errors

def log(message, to_file=True, to_console=True):
    """Log to both file and console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    
    if to_console:
        print(log_message)
    
    if to_file:
        with open(LOG_FILE, 'a') as f:
            f.write(log_message + '\n')

def save_progress(current_index, stats):
    """Save progress for resuming."""
    progress = {
        'last_index': current_index,
        'stats': stats,
        'timestamp': datetime.now().isoformat()
    }
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def load_progress():
    """Load saved progress."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def fetch_records(token, limit=None):
    """Fetch records with server paths."""
    log("🔍 Fetching records from FileMaker...")
    
    all_records = []
    offset = 1
    consecutive_errors = 0
    
    while True:
        try:
            response = requests.get(
                config.url(f"layouts/Stills/records"),
                headers=config.api_headers(token),
                params={'_offset': offset, '_limit': BATCH_SIZE},
                verify=False,
                timeout=60
            )
            
            # Check for API errors
            if response.status_code == 401:
                log(f"⚠️  Token expired, refreshing...")
                token = config.get_token()
                continue
            elif response.status_code == 429:
                log(f"⚠️  Rate limit hit at offset {offset}, waiting 10 seconds...")
                time.sleep(10)
                continue
            elif response.status_code == 503:
                log(f"⚠️  Server busy at offset {offset}, waiting 5 seconds...")
                time.sleep(5)
                continue
            elif response.status_code != 200:
                consecutive_errors += 1
                log(f"❌ API Error {response.status_code} at offset {offset} (consecutive: {consecutive_errors})")
                if consecutive_errors >= API_ERROR_THRESHOLD:
                    log(f"❌ STOPPING: Too many consecutive API errors ({consecutive_errors})")
                    break
                time.sleep(2)
                continue
            
            # Reset error counter on success
            consecutive_errors = 0
            
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
            
            time.sleep(0.5)
            
        except requests.exceptions.Timeout:
            consecutive_errors += 1
            log(f"⚠️  Timeout at offset {offset} (consecutive: {consecutive_errors})")
            if consecutive_errors >= API_ERROR_THRESHOLD:
                log(f"❌ STOPPING: Too many consecutive timeouts")
                break
            time.sleep(3)
            continue
            
        except Exception as e:
            consecutive_errors += 1
            log(f"❌ Error fetching at offset {offset}: {e} (consecutive: {consecutive_errors})")
            if consecutive_errors >= API_ERROR_THRESHOLD:
                log(f"❌ STOPPING: Too many consecutive errors")
                break
            time.sleep(2)
            continue
    
    log(f"✅ Found {len(all_records)} records with server paths")
    return all_records, token

def standardize_one(record_info, token):
    """Standardize a single thumbnail with API error handling."""
    stills_id = record_info['stills_id']
    record_id = record_info['record_id']
    server_path = record_info['server_path']
    
    try:
        if not os.path.exists(server_path):
            return {'success': False, 'error': 'File not found', 'skipped': True, 'api_error': False}
        
        with Image.open(server_path) as img:
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            thumb_img = img.copy()
            thumb_img.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
            
            temp_thumb = f"/tmp/batch_thumb_{stills_id}.jpg"
            thumb_img.save(temp_thumb, 'JPEG', quality=THUMBNAIL_QUALITY)
            
            thumb_size = thumb_img.size
            thumb_file_size = os.path.getsize(temp_thumb)
            
            # Upload with error detection
            try:
                response = requests.post(
                    config.url(f"layouts/Stills/records/{record_id}/containers/{FIELD_MAPPING['thumbnail']}/1"),
                    headers={"Authorization": f"Bearer {token}"},
                    files={'upload': open(temp_thumb, 'rb')},
                    verify=False,
                    timeout=30
                )
                
                # Check for API errors
                if response.status_code == 401:
                    os.remove(temp_thumb)
                    return {'success': False, 'error': 'Token expired', 'api_error': True}
                elif response.status_code == 429:
                    os.remove(temp_thumb)
                    return {'success': False, 'error': 'Rate limited', 'api_error': True}
                elif response.status_code == 503:
                    os.remove(temp_thumb)
                    return {'success': False, 'error': 'Server busy', 'api_error': True}
                elif response.status_code != 200:
                    os.remove(temp_thumb)
                    return {'success': False, 'error': f'API error {response.status_code}', 'api_error': True}
                
                os.remove(temp_thumb)
                
                return {
                    'success': True,
                    'thumb_size': thumb_size,
                    'thumb_file_size': thumb_file_size,
                    'api_error': False
                }
                
            except requests.exceptions.Timeout:
                if os.path.exists(temp_thumb):
                    os.remove(temp_thumb)
                return {'success': False, 'error': 'Upload timeout', 'api_error': True}
            except Exception as upload_error:
                if os.path.exists(temp_thumb):
                    os.remove(temp_thumb)
                return {'success': False, 'error': f'Upload failed: {upload_error}', 'api_error': True}
    
    except Exception as e:
        return {'success': False, 'error': str(e), 'api_error': False}

def process_batch(records, token, start_index=0):
    """Process all records with monitoring."""
    log(f"{'='*80}")
    log(f"PROCESSING {len(records)} RECORDS (starting at index {start_index})")
    log(f"{'='*80}")
    log(f"Delay between records: {DELAY_BETWEEN_RECORDS}s")
    log(f"Log file: {LOG_FILE}")
    
    stats = {'successful': 0, 'failed': 0, 'skipped': 0, 'api_errors': 0}
    start_time = datetime.now()
    consecutive_api_errors = 0
    
    for i in range(start_index, len(records)):
        record_info = records[i]
        stills_id = record_info['stills_id']
        
        # Console output (without timestamp for cleaner display)
        print(f"[{i+1}/{len(records)}] {stills_id}...", end=' ', flush=True)
        
        result = standardize_one(record_info, token)
        
        if result['success']:
            stats['successful'] += 1
            consecutive_api_errors = 0
            msg = f"✅ {result['thumb_size'][0]}x{result['thumb_size'][1]} ({result['thumb_file_size']:,}b)"
            print(msg)
            log(f"[{i+1}/{len(records)}] {stills_id} {msg}", to_console=False)
            
        elif result.get('api_error'):
            stats['api_errors'] += 1
            consecutive_api_errors += 1
            msg = f"⚠️  API: {result.get('error', 'unknown')}"
            print(msg)
            log(f"[{i+1}/{len(records)}] {stills_id} {msg}", to_console=False)
            
            # Check if we should stop
            if consecutive_api_errors >= API_ERROR_THRESHOLD:
                log(f"❌ STOPPING: {consecutive_api_errors} consecutive API errors")
                log(f"   Last error: {result.get('error')}")
                log(f"   Progress saved - can resume with --resume flag")
                save_progress(i, stats)
                return stats, False  # False = stopped due to errors
            
            # Wait longer on API errors
            time.sleep(2)
            
        elif result.get('skipped'):
            stats['skipped'] += 1
            consecutive_api_errors = 0
            msg = f"⏭️  {result.get('error', 'skipped')}"
            print(msg)
            log(f"[{i+1}/{len(records)}] {stills_id} {msg}", to_console=False)
            
        else:
            stats['failed'] += 1
            consecutive_api_errors = 0
            msg = f"❌ {result.get('error', 'failed')}"
            print(msg)
            log(f"[{i+1}/{len(records)}] {stills_id} {msg}", to_console=False)
        
        # Progress checkpoints
        if (i + 1) % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = (i + 1 - start_index) / elapsed if elapsed > 0 else 0
            remaining = len(records) - (i + 1)
            eta_min = (remaining / rate / 60) if rate > 0 else 0
            
            checkpoint = f"📊 Checkpoint: {i+1}/{len(records)} | ✅ {stats['successful']} ❌ {stats['failed']} ⏭️ {stats['skipped']} ⚠️ {stats['api_errors']} | {rate:.1f}/sec | ETA: {eta_min:.0f}min"
            log(checkpoint)
            
            # Save progress
            save_progress(i, stats)
        
        # Rate limiting delay
        time.sleep(DELAY_BETWEEN_RECORDS)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    log(f"{'='*80}")
    log(f"COMPLETED SUCCESSFULLY")
    log(f"{'='*80}")
    log(f"✅ Successful: {stats['successful']}")
    log(f"❌ Failed: {stats['failed']}")
    log(f"⏭️  Skipped: {stats['skipped']}")
    log(f"⚠️  API Errors: {stats['api_errors']}")
    log(f"⏱️  Duration: {duration/60:.1f} minutes ({(i+1-start_index)/duration:.1f} records/sec)")
    
    return stats, True  # True = completed successfully

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Limit number of records')
    parser.add_argument('--resume', action='store_true', help='Resume from saved progress')
    args = parser.parse_args()
    
    # Initialize log file
    with open(LOG_FILE, 'w') as f:
        f.write(f"{'='*80}\n")
        f.write(f"THUMBNAIL STANDARDIZATION - {datetime.now().isoformat()}\n")
        f.write(f"{'='*80}\n")
    
    log("="*80)
    log("PRODUCTION THUMBNAIL STANDARDIZATION")
    log("="*80)
    log(f"Settings: {THUMBNAIL_MAX_SIZE[0]}px max, {THUMBNAIL_QUALITY}% quality")
    log(f"Log file: {LOG_FILE}")
    
    # Check for resume
    start_index = 0
    if args.resume:
        progress = load_progress()
        if progress:
            log(f"📂 Resuming from index {progress['last_index'] + 1}")
            start_index = progress['last_index'] + 1
    
    # Get token
    token = config.get_token()
    
    # Fetch records
    records, token = fetch_records(token, limit=args.limit)
    
    if not records:
        log("❌ No records to process")
        sys.exit(1)
    
    if start_index >= len(records):
        log("✅ Already completed all records")
        sys.exit(0)
    
    # Process
    stats, completed = process_batch(records, token, start_index=start_index)
    
    if completed:
        log(f"\n✅ ALL THUMBNAILS STANDARDIZED!")
        log(f"   Next step: Regenerate embeddings in FileMaker")
        
        # Clean up progress file
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
        
        sys.exit(0)
    else:
        log(f"\n⚠️  STOPPED DUE TO API ERRORS")
        log(f"   Check log: {LOG_FILE}")
        log(f"   Resume with: python3 {sys.argv[0]} --resume")
        sys.exit(1)

