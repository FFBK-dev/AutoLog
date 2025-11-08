#!/usr/bin/env python3
"""
Migration Script: Parse SPECS_File_Dimensions into X and Y fields

This script processes all existing Stills records and splits the dimensions
field (format: "1920x1080") into separate X and Y fields.

Features:
- Batch processing with configurable batch size
- API rate limiting with delays between batches
- Progress tracking and resumable operation
- Dry-run mode for testing
- Comprehensive error handling
"""

import sys
import warnings
import time
import json
from pathlib import Path
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
import requests

# Configuration
BATCH_SIZE = 50  # Process records in batches of 50
DELAY_BETWEEN_BATCHES = 2  # Seconds to wait between batches (API rate limiting)
DELAY_BETWEEN_UPDATES = 0.1  # Seconds to wait between individual updates
DRY_RUN = False  # Set to True to simulate without making changes

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "dimensions": "SPECS_File_Dimensions",
    "dimensions_x": "SPECS_File_Dimensions_X",
    "dimensions_y": "SPECS_File_Dimensions_Y"
}

def parse_dimensions(dimensions_str):
    """Parse dimensions string into width and height integers."""
    if not dimensions_str or dimensions_str == "Unknown":
        return None, None
    
    try:
        if 'x' in dimensions_str:
            width_str, height_str = dimensions_str.split('x', 1)
            width = int(width_str.strip())
            height = int(height_str.strip())
            return width, height
    except (ValueError, AttributeError) as e:
        print(f"  -> Warning: Could not parse dimensions '{dimensions_str}': {e}")
    
    return None, None

def get_records_batch(token, offset=1, limit=BATCH_SIZE):
    """Get a batch of records from FileMaker."""
    try:
        # Get records with dimensions field populated
        # Using a simple get all approach with offset/limit
        response = requests.get(
            config.url(f"layouts/Stills/records?_offset={offset}&_limit={limit}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 401:
            # Token expired, get new one
            print("  -> Token expired, refreshing...")
            token = config.get_token()
            response = requests.get(
                config.url(f"layouts/Stills/records?_offset={offset}&_limit={limit}"),
                headers=config.api_headers(token),
                verify=False,
                timeout=30
            )
        
        response.raise_for_status()
        data = response.json()
        records = data.get('response', {}).get('data', [])
        
        # Get total record count from metadata
        total_count = data.get('response', {}).get('dataInfo', {}).get('foundCount', 0)
        
        return records, total_count, token
        
    except Exception as e:
        print(f"  -> Error fetching records: {e}")
        return [], 0, token

def update_record_dimensions(token, record_id, width, height):
    """Update a record with X and Y dimensions."""
    try:
        payload = {
            "fieldData": {
                FIELD_MAPPING["dimensions_x"]: width,
                FIELD_MAPPING["dimensions_y"]: height
            }
        }
        
        if DRY_RUN:
            print(f"    [DRY RUN] Would update record {record_id}: X={width}, Y={height}")
            return True, token
        
        response = requests.patch(
            config.url(f"layouts/Stills/records/{record_id}"),
            headers=config.api_headers(token),
            json=payload,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 401:
            # Token expired, get new one
            token = config.get_token()
            response = requests.patch(
                config.url(f"layouts/Stills/records/{record_id}"),
                headers=config.api_headers(token),
                json=payload,
                verify=False,
                timeout=30
            )
        
        response.raise_for_status()
        return True, token
        
    except Exception as e:
        print(f"    Error updating record {record_id}: {e}")
        return False, token

def migrate_dimensions():
    """Main migration function."""
    print("=" * 70)
    print("🔄 Dimension Migration Script")
    print("=" * 70)
    print(f"Configuration:")
    print(f"  Batch Size: {BATCH_SIZE}")
    print(f"  Delay Between Batches: {DELAY_BETWEEN_BATCHES}s")
    print(f"  Delay Between Updates: {DELAY_BETWEEN_UPDATES}s")
    print(f"  Dry Run: {'YES - No changes will be made' if DRY_RUN else 'NO - Records will be updated'}")
    print("=" * 70)
    
    # Get initial token
    try:
        token = config.get_token()
        print("✅ Successfully connected to FileMaker")
    except Exception as e:
        print(f"❌ Failed to connect to FileMaker: {e}")
        return False
    
    # Statistics
    stats = {
        "total_processed": 0,
        "successful_updates": 0,
        "skipped": 0,
        "failed": 0,
        "already_split": 0,
        "no_dimensions": 0
    }
    
    offset = 1
    batch_num = 1
    start_time = datetime.now()
    
    print("\n🚀 Starting migration...\n")
    
    # First, get total count
    print("📊 Counting total records...")
    _, total_count, token = get_records_batch(token, offset=1, limit=1)
    print(f"📋 Found {total_count} total records in database\n")
    
    while True:
        print(f"📦 Processing batch {batch_num} (offset {offset})...")
        
        # Get batch of records
        records, _, token = get_records_batch(token, offset=offset, limit=BATCH_SIZE)
        
        if not records:
            print("  -> No more records to process")
            break
        
        print(f"  -> Retrieved {len(records)} records")
        
        # Process each record in the batch
        for record in records:
            stats["total_processed"] += 1
            
            record_id = record['recordId']
            field_data = record['fieldData']
            
            stills_id = field_data.get(FIELD_MAPPING["stills_id"], "Unknown")
            dimensions = field_data.get(FIELD_MAPPING["dimensions"], "")
            current_x = field_data.get(FIELD_MAPPING["dimensions_x"])
            current_y = field_data.get(FIELD_MAPPING["dimensions_y"])
            
            # Skip if no dimensions
            if not dimensions or dimensions == "Unknown":
                stats["no_dimensions"] += 1
                continue
            
            # Skip if already split
            if current_x and current_y:
                stats["already_split"] += 1
                continue
            
            # Parse dimensions
            width, height = parse_dimensions(dimensions)
            
            if width is None or height is None:
                print(f"  ⚠️ {stills_id}: Could not parse dimensions '{dimensions}'")
                stats["skipped"] += 1
                continue
            
            # Update record
            success, token = update_record_dimensions(token, record_id, width, height)
            
            if success:
                print(f"  ✅ {stills_id}: {dimensions} → X={width}, Y={height}")
                stats["successful_updates"] += 1
            else:
                print(f"  ❌ {stills_id}: Failed to update")
                stats["failed"] += 1
            
            # Small delay between updates to avoid overwhelming the API
            if not DRY_RUN:
                time.sleep(DELAY_BETWEEN_UPDATES)
        
        # Progress update
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = stats["total_processed"] / elapsed if elapsed > 0 else 0
        remaining = total_count - stats["total_processed"]
        eta_seconds = remaining / rate if rate > 0 else 0
        
        print(f"\n📊 Progress Summary:")
        print(f"  Processed: {stats['total_processed']}/{total_count} ({stats['total_processed']/total_count*100:.1f}%)")
        print(f"  Updated: {stats['successful_updates']}")
        print(f"  Already Split: {stats['already_split']}")
        print(f"  No Dimensions: {stats['no_dimensions']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Processing Rate: {rate:.1f} records/sec")
        print(f"  ETA: {eta_seconds/60:.1f} minutes")
        print()
        
        # Move to next batch
        offset += BATCH_SIZE
        batch_num += 1
        
        # Delay between batches to respect API rate limits
        if not DRY_RUN and records:  # Only delay if there were records and not in dry run
            print(f"⏸️  Waiting {DELAY_BETWEEN_BATCHES}s before next batch...")
            time.sleep(DELAY_BETWEEN_BATCHES)
            print()
    
    # Final summary
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print("=" * 70)
    print("✅ Migration Complete!")
    print("=" * 70)
    print(f"Final Statistics:")
    print(f"  Total Processed: {stats['total_processed']}")
    print(f"  Successfully Updated: {stats['successful_updates']}")
    print(f"  Already Split: {stats['already_split']}")
    print(f"  No Dimensions: {stats['no_dimensions']}")
    print(f"  Skipped (parse error): {stats['skipped']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Total Time: {elapsed/60:.1f} minutes")
    print(f"  Average Rate: {stats['total_processed']/elapsed:.1f} records/sec")
    print("=" * 70)
    
    return stats["failed"] == 0

if __name__ == "__main__":
    # Check for dry-run flag
    if "--dry-run" in sys.argv:
        DRY_RUN = True
        print("🔍 DRY RUN MODE ENABLED - No changes will be made\n")
    
    # Check for custom batch size
    if "--batch-size" in sys.argv:
        try:
            idx = sys.argv.index("--batch-size")
            BATCH_SIZE = int(sys.argv[idx + 1])
            print(f"📦 Custom batch size: {BATCH_SIZE}\n")
        except (IndexError, ValueError):
            print("⚠️ Invalid batch size argument, using default\n")
    
    success = migrate_dimensions()
    sys.exit(0 if success else 1)

