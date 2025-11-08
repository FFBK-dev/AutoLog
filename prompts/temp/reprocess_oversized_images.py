#!/usr/bin/env python3
"""
Reprocess Oversized Images Script

Finds all Stills records where either dimension exceeds 15000 pixels
and reprocesses them through copy_to_server to resize them properly.
"""

import sys
import warnings
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
import requests

MAX_DIMENSION = 15000

def find_oversized_records(token):
    """Find all records where either dimension exceeds the max."""
    print(f"🔍 Searching for records with dimensions > {MAX_DIMENSION}px...")
    
    oversized_records = []
    
    try:
        # We need to get all records and check dimensions
        # FileMaker Data API doesn't support > comparisons in find easily
        # So we'll get batches and filter
        
        offset = 1
        batch_size = 100
        total_checked = 0
        
        while True:
            print(f"  -> Checking batch at offset {offset}...")
            
            response = requests.get(
                config.url(f"layouts/Stills/records?_offset={offset}&_limit={batch_size}"),
                headers=config.api_headers(token),
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                # Token expired
                token = config.get_token()
                continue
            
            if response.status_code >= 400:
                # End of records or error - we're done
                break
            
            data = response.json()
            records = data.get('response', {}).get('data', [])
            
            if not records:
                break
            
            # Check each record
            for record in records:
                field_data = record['fieldData']
                stills_id = field_data.get('INFO_STILLS_ID')
                dim_x = field_data.get('SPECS_File_Dimensions_X')
                dim_y = field_data.get('SPECS_File_Dimensions_Y')
                server_path = field_data.get('SPECS_Filepath_Server')
                
                # Skip if no dimensions or no server path (hasn't been copied yet)
                if not dim_x or not dim_y or not server_path:
                    continue
                
                # Check if either dimension exceeds the limit
                if dim_x > MAX_DIMENSION or dim_y > MAX_DIMENSION:
                    oversized_records.append({
                        'stills_id': stills_id,
                        'width': dim_x,
                        'height': dim_y,
                        'server_path': server_path
                    })
                    print(f"  ⚠️ Found: {stills_id} - {dim_x}x{dim_y}")
            
            total_checked += len(records)
            print(f"  -> Checked {total_checked} records so far, found {len(oversized_records)} oversized")
            
            offset += batch_size
            
            # Small delay to avoid overwhelming the API
            time.sleep(0.5)
        
        print(f"\n✅ Search complete!")
        print(f"📊 Total records checked: {total_checked}")
        print(f"📋 Oversized records found: {len(oversized_records)}")
        
        return oversized_records, token
        
    except Exception as e:
        print(f"❌ Error finding oversized records: {e}")
        return [], token

def reprocess_record(stills_id, token):
    """Reprocess a single record through copy_to_server."""
    try:
        print(f"  🔄 Reprocessing {stills_id}...")
        
        # Run the copy_to_server script
        cmd = [
            'python3',
            '/Users/admin/Documents/Github/Filemaker-Backend/jobs/stills_autolog_02_copy_to_server.py',
            stills_id,
            token
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per image
        )
        
        if result.returncode == 0:
            print(f"  ✅ {stills_id} - Successfully reprocessed")
            return True
        else:
            print(f"  ❌ {stills_id} - Failed with exit code {result.returncode}")
            if result.stderr:
                print(f"     Error: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ⏱️ {stills_id} - Timeout after 5 minutes")
        return False
    except Exception as e:
        print(f"  ❌ {stills_id} - Error: {e}")
        return False

def main():
    """Main execution function."""
    print("=" * 70)
    print("🔄 Reprocess Oversized Images")
    print("=" * 70)
    print(f"Target: Images with dimensions > {MAX_DIMENSION}px")
    print(f"Action: Reprocess through copy_to_server (will resize to {MAX_DIMENSION}px max)")
    print("=" * 70)
    
    # Get token
    try:
        token = config.get_token()
        print("✅ Successfully connected to FileMaker\n")
    except Exception as e:
        print(f"❌ Failed to connect to FileMaker: {e}")
        return False
    
    # Find oversized records
    oversized_records, token = find_oversized_records(token)
    
    if not oversized_records:
        print("\n✅ No oversized records found - all images are within limits!")
        return True
    
    # Show summary
    print(f"\n📋 Records to reprocess:")
    for i, record in enumerate(oversized_records, 1):
        print(f"  {i:2d}. {record['stills_id']:8s} - {record['width']:5d}x{record['height']:5d}")
    
    # Confirm
    print(f"\n⚠️  This will reprocess {len(oversized_records)} images")
    print(f"   Each image will be resized to max {MAX_DIMENSION}px on longest side")
    print(f"   Estimated time: ~{len(oversized_records) * 10} seconds ({len(oversized_records) * 10 / 60:.1f} minutes)")
    
    # Process records
    print(f"\n🚀 Starting reprocessing...\n")
    
    stats = {
        'total': len(oversized_records),
        'successful': 0,
        'failed': 0
    }
    
    start_time = datetime.now()
    
    for i, record in enumerate(oversized_records, 1):
        print(f"\n[{i}/{len(oversized_records)}] Processing {record['stills_id']} ({record['width']}x{record['height']})")
        
        success = reprocess_record(record['stills_id'], token)
        
        if success:
            stats['successful'] += 1
        else:
            stats['failed'] += 1
        
        # Progress update
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = i / elapsed if elapsed > 0 else 0
        remaining = len(oversized_records) - i
        eta_seconds = remaining / rate if rate > 0 else 0
        
        print(f"  📊 Progress: {i}/{len(oversized_records)} ({i/len(oversized_records)*100:.1f}%)")
        print(f"     Success: {stats['successful']}, Failed: {stats['failed']}")
        print(f"     Rate: {rate:.1f} records/sec, ETA: {eta_seconds/60:.1f} minutes")
    
    # Final summary
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print("\n" + "=" * 70)
    print("✅ Reprocessing Complete!")
    print("=" * 70)
    print(f"Final Statistics:")
    print(f"  Total Records: {stats['total']}")
    print(f"  Successfully Reprocessed: {stats['successful']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Total Time: {elapsed/60:.1f} minutes")
    print(f"  Average Rate: {stats['total']/elapsed:.1f} records/sec")
    print("=" * 70)
    
    return stats['failed'] == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

