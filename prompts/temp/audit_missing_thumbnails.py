#!/usr/bin/env python3
"""
Audit Missing Thumbnails

This script finds all frame records with missing or empty thumbnail containers
and optionally regenerates them with extended timeouts for larger files.

Usage: 
    python3 audit_missing_thumbnails.py [--fix] [--timeout=300]
    
    --fix: Actually regenerate missing thumbnails (default: just audit)
    --timeout: Timeout in seconds for thumbnail generation (default: 300)
"""

import sys
import warnings
import argparse
from pathlib import Path
import time
import concurrent.futures

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.fm_api_helpers import find_frame_records, gatekeeper_find_records, update_frame_record

def audit_missing_thumbnails(token):
    """Find all frames with missing thumbnail containers."""
    print("🔍 Auditing all frame records for missing thumbnails...")
    
    try:
        # Get all frame records (this might take a while for large databases)
        print("  -> Fetching all frame records...")
        all_frames = []
        offset = 0
        batch_size = 1000
        
        while True:
            # Use direct gatekeeper call for large queries
            batch_frames = gatekeeper_find_records(
                token, 
                "FRAMES", 
                [{}],  # Empty query to get all records
                limit=batch_size, 
                offset=offset, 
                priority='low'
            )
            
            if not batch_frames:
                break
            
            all_frames.extend(batch_frames)
            offset += batch_size
            print(f"    -> Fetched {len(all_frames)} frames so far...")
            
            # Break if we got fewer than batch_size (end of records)
            if len(batch_frames) < batch_size:
                break
        
        print(f"  -> Total frames found: {len(all_frames)}")
        
        # Analyze thumbnail status
        missing_thumbnails = []
        valid_thumbnails = 0
        
        for frame in all_frames:
            frame_data = frame['fieldData']
            frame_id = frame_data.get('FRAMES_ID', frame['recordId'])
            parent_id = frame_data.get('FRAMES_ParentID', 'unknown')
            thumbnail_field = frame_data.get('FRAMES_Thumbnail', '')
            
            # Check if thumbnail container is empty
            if not thumbnail_field or thumbnail_field.strip() == '':
                missing_thumbnails.append({
                    'frame_id': frame_id,
                    'parent_id': parent_id,
                    'record_id': frame['recordId'],
                    'frame_data': frame_data
                })
            else:
                valid_thumbnails += 1
        
        print(f"\n📊 Audit Results:")
        print(f"  -> Total frames: {len(all_frames)}")
        print(f"  -> Valid thumbnails: {valid_thumbnails}")
        print(f"  -> Missing thumbnails: {len(missing_thumbnails)}")
        print(f"  -> Missing percentage: {(len(missing_thumbnails)/len(all_frames)*100):.1f}%")
        
        # Group by parent footage
        by_footage = {}
        for frame in missing_thumbnails:
            parent = frame['parent_id']
            if parent not in by_footage:
                by_footage[parent] = []
            by_footage[parent].append(frame['frame_id'])
        
        print(f"\n📋 Footage items with missing thumbnails:")
        for footage_id, frame_ids in sorted(by_footage.items()):
            print(f"  -> {footage_id}: {len(frame_ids)} missing thumbnails")
            if len(frame_ids) <= 5:
                print(f"     Frames: {', '.join(frame_ids)}")
            else:
                print(f"     Frames: {', '.join(frame_ids[:5])}... (+{len(frame_ids)-5} more)")
        
        return missing_thumbnails
        
    except Exception as e:
        print(f"❌ Error during audit: {e}")
        import traceback
        traceback.print_exc()
        return []

def fix_missing_thumbnails(missing_thumbnails, token, timeout=300, max_workers=4):
    """Regenerate missing thumbnails with extended timeout."""
    if not missing_thumbnails:
        print("✅ No missing thumbnails to fix")
        return True
    
    print(f"\n🔧 Regenerating {len(missing_thumbnails)} missing thumbnails...")
    print(f"  -> Using timeout: {timeout}s")
    print(f"  -> Max workers: {max_workers}")
    
    successful = 0
    failed = 0
    
    def regenerate_single_thumbnail(frame_info):
        frame_id = frame_info['frame_id']
        record_id = frame_info['record_id']
        
        try:
            print(f"    -> Regenerating thumbnail for {frame_id}...")
            
            # Import the retry function
            sys.path.append(str(Path(__file__).resolve().parent.parent / "jobs"))
            from footage_autolog_05_process_frames import run_frame_script_with_retry
            
            success = run_frame_script_with_retry(
                "frames_generate_thumbnails.py", 
                frame_id, 
                token, 
                timeout=timeout, 
                max_retries=3  # Extra retries for problematic files
            )
            
            if success:
                print(f"    -> ✅ Successfully regenerated thumbnail for {frame_id}")
                return True
            else:
                print(f"    -> ❌ Failed to regenerate thumbnail for {frame_id}")
                return False
                
        except Exception as e:
            print(f"    -> ❌ Error regenerating thumbnail for {frame_id}: {e}")
            return False
    
    # Process in parallel with conservative worker count to respect gatekeeper
    print(f"  -> Processing thumbnails in batches...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_frame = {
            executor.submit(regenerate_single_thumbnail, frame_info): frame_info 
            for frame_info in missing_thumbnails
        }
        
        for future in concurrent.futures.as_completed(future_to_frame):
            frame_info = future_to_frame[future]
            try:
                success = future.result()
                if success:
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"    -> Exception processing {frame_info['frame_id']}: {e}")
                failed += 1
            
            # Progress update
            total_processed = successful + failed
            if total_processed % 10 == 0:
                progress_pct = (total_processed / len(missing_thumbnails)) * 100
                print(f"    -> Progress: {total_processed}/{len(missing_thumbnails)} ({progress_pct:.1f}%) - ✅ {successful} ❌ {failed}")
    
    print(f"\n🎯 Thumbnail Regeneration Results:")
    print(f"  -> Successful: {successful}")
    print(f"  -> Failed: {failed}")
    print(f"  -> Success rate: {(successful/(successful+failed)*100):.1f}%")
    
    return successful > 0

def main():
    parser = argparse.ArgumentParser(description='Audit and fix missing thumbnails')
    parser.add_argument('--fix', action='store_true', help='Actually regenerate missing thumbnails')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout for thumbnail generation (default: 300s)')
    parser.add_argument('--workers', type=int, default=4, help='Max parallel workers (default: 4)')
    
    args = parser.parse_args()
    
    try:
        print("🔑 Getting FileMaker token...")
        token = config.get_token()
        print("✅ Token obtained")
        
        # Run the audit
        missing_thumbnails = audit_missing_thumbnails(token)
        
        if args.fix and missing_thumbnails:
            print(f"\n{'='*60}")
            print("🔧 THUMBNAIL REGENERATION MODE")
            print(f"{'='*60}")
            
            # Confirm before proceeding
            response = input(f"\nRegenerate {len(missing_thumbnails)} missing thumbnails? (y/N): ")
            if response.lower() == 'y':
                fix_missing_thumbnails(missing_thumbnails, token, args.timeout, args.workers)
            else:
                print("❌ Thumbnail regeneration cancelled")
        elif args.fix:
            print("✅ No missing thumbnails found - nothing to fix")
        else:
            print(f"\n💡 To fix missing thumbnails, run:")
            print(f"   python3 {sys.argv[0]} --fix --timeout={args.timeout}")
        
    except Exception as e:
        print(f"❌ Script error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 