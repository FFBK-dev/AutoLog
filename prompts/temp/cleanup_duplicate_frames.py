#!/usr/bin/env python3
"""
Cleanup Duplicate Frame Records

This utility finds and removes duplicate frame records while preserving the best copy
of each frame (preferably the one with thumbnail data).

Usage: python3 cleanup_duplicate_frames.py [footage_id]
       If footage_id is provided, only cleans that footage's frames
       If no footage_id, scans all footage records
"""

import sys
import warnings
from pathlib import Path
import requests
import time

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "frame_parent_id": "FRAMES_ParentID", 
    "frame_status": "FRAMES_Status",
    "frame_id": "FRAMES_ID",
    "frame_thumbnail": "FRAMES_Thumbnail",
    "frame_caption": "FRAMES_Caption",
    "frame_transcript": "FRAMES_Transcript"
}

def get_all_footage_ids(token):
    """Get all footage IDs from the database."""
    try:
        # Query all footage records (with pagination if needed)
        footage_ids = []
        offset = 0
        batch_size = 500
        
        while True:
            query_params = {
                "query": [{"INFO_FTG_ID": "*"}],
                "limit": batch_size
            }
            if offset > 0:
                query_params["offset"] = offset
            
            response = requests.post(
                config.url("layouts/FOOTAGE/_find"),
                headers=config.api_headers(token),
                json=query_params,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                records = response.json()['response']['data']
                for record in records:
                    footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
                    if footage_id:
                        footage_ids.append(footage_id)
                
                if len(records) < batch_size:
                    break  # No more records
                offset += len(records)
            else:
                break
        
        return footage_ids
        
    except Exception as e:
        print(f"❌ Error getting footage IDs: {e}")
        return []

def analyze_frame_duplicates(token, footage_id):
    """Analyze frame records for a specific footage ID to find duplicates."""
    try:
        print(f"🔍 Analyzing frames for {footage_id}...")
        
        # Get all frame records for this footage
        query = {"query": [{FIELD_MAPPING["frame_parent_id"]: footage_id}], "limit": 1000}
        
        response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 404:
            print(f"  -> No frames found for {footage_id}")
            return {}
        
        if response.status_code != 200:
            print(f"  -> Error querying frames for {footage_id}: {response.status_code}")
            return {}
        
        frames = response.json()['response']['data']
        print(f"  -> Found {len(frames)} total frame records")
        
        # Group by frame ID to detect duplicates
        frame_groups = {}
        for frame in frames:
            field_data = frame['fieldData']
            frame_id = field_data.get(FIELD_MAPPING["frame_id"], f"Unknown_{frame['recordId']}")
            
            if frame_id not in frame_groups:
                frame_groups[frame_id] = []
            
            # Score this frame instance (higher is better)
            score = 0
            
            # Has thumbnail? +10 points
            if field_data.get(FIELD_MAPPING["frame_thumbnail"], "").strip():
                score += 10
            
            # Has caption? +5 points
            if field_data.get(FIELD_MAPPING["frame_caption"], "").strip():
                score += 5
            
            # Has transcript? +3 points  
            if field_data.get(FIELD_MAPPING["frame_transcript"], "").strip():
                score += 3
            
            # Advanced status? +1 point per step
            status = field_data.get(FIELD_MAPPING["frame_status"], "")
            status_scores = {
                "1 - Pending Thumbnail": 1,
                "2 - Thumbnail Complete": 2,
                "3 - Caption Generated": 3,
                "4 - Audio Transcribed": 4,
                "5 - Generating Embeddings": 5,
                "6 - Embeddings Complete": 6
            }
            score += status_scores.get(status, 0)
            
            frame_groups[frame_id].append({
                'record_id': frame['recordId'],
                'field_data': field_data,
                'score': score
            })
        
        # Find duplicates and select best instances
        duplicates = {}
        for frame_id, instances in frame_groups.items():
            if len(instances) > 1:
                # Sort by score (highest first)
                instances.sort(key=lambda x: x['score'], reverse=True)
                
                best_instance = instances[0]
                duplicates_to_remove = instances[1:]
                
                duplicates[frame_id] = {
                    'keep': best_instance,
                    'remove': duplicates_to_remove,
                    'total_instances': len(instances)
                }
                
                print(f"  -> 🔴 DUPLICATE: {frame_id} ({len(instances)} copies)")
                print(f"     KEEP: Record {best_instance['record_id']} (score: {best_instance['score']})")
                for dup in duplicates_to_remove:
                    print(f"     REMOVE: Record {dup['record_id']} (score: {dup['score']})")
        
        if duplicates:
            print(f"  -> Found {len(duplicates)} duplicate frame sets")
        else:
            print(f"  -> ✅ No duplicates found")
        
        return duplicates
        
    except Exception as e:
        print(f"❌ Error analyzing frames for {footage_id}: {e}")
        return {}

def cleanup_duplicates(token, footage_id, duplicates, dry_run=True):
    """Remove duplicate frame records, keeping the best instance of each."""
    if not duplicates:
        print(f"  -> No duplicates to clean up for {footage_id}")
        return 0, 0
    
    removed_count = 0
    failed_count = 0
    
    print(f"{'🧪 DRY RUN:' if dry_run else '🗑️ REMOVING:'} Cleaning up {len(duplicates)} duplicate frame sets...")
    
    for frame_id, dup_info in duplicates.items():
        print(f"  -> Processing {frame_id} ({dup_info['total_instances']} copies)")
        
        for dup_instance in dup_info['remove']:
            record_id = dup_instance['record_id']
            
            if dry_run:
                print(f"     [DRY RUN] Would delete record {record_id}")
                removed_count += 1
            else:
                try:
                    delete_response = requests.delete(
                        config.url(f"layouts/FRAMES/records/{record_id}"),
                        headers=config.api_headers(token),
                        verify=False,
                        timeout=30
                    )
                    
                    if delete_response.status_code == 200:
                        print(f"     ✅ Deleted record {record_id}")
                        removed_count += 1
                    else:
                        print(f"     ❌ Failed to delete record {record_id}: {delete_response.status_code}")
                        failed_count += 1
                        
                    # Rate limiting - be gentle with the API
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"     ❌ Error deleting record {record_id}: {e}")
                    failed_count += 1
    
    return removed_count, failed_count

def main():
    """Main cleanup function."""
    print("🧹 Frame Duplication Cleanup Utility")
    print("=====================================")
    print()
    
    # Parse command line arguments
    if len(sys.argv) > 2:
        print("Usage: python3 cleanup_duplicate_frames.py [footage_id]")
        sys.exit(1)
    
    specific_footage_id = sys.argv[1] if len(sys.argv) == 2 else None
    
    try:
        token = config.get_token()
        
        # Determine which footage IDs to process
        if specific_footage_id:
            footage_ids = [specific_footage_id]
            print(f"🎯 Processing specific footage: {specific_footage_id}")
        else:
            print("🔍 Getting all footage IDs...")
            footage_ids = get_all_footage_ids(token)
            print(f"📊 Found {len(footage_ids)} footage records to check")
        
        if not footage_ids:
            print("❌ No footage IDs found to process")
            sys.exit(1)
        
        print()
        
        # Phase 1: Analysis (dry run)
        print("🔍 PHASE 1: ANALYSIS")
        print("===================")
        
        total_duplicates = 0
        total_instances_to_remove = 0
        footage_with_duplicates = []
        
        for footage_id in footage_ids:
            duplicates = analyze_frame_duplicates(token, footage_id)
            if duplicates:
                footage_with_duplicates.append((footage_id, duplicates))
                total_duplicates += len(duplicates)
                total_instances_to_remove += sum(len(d['remove']) for d in duplicates.values())
        
        print()
        print("📊 ANALYSIS SUMMARY:")
        print(f"   Footage with duplicates: {len(footage_with_duplicates)}")
        print(f"   Total duplicate frame sets: {total_duplicates}")
        print(f"   Total records to remove: {total_instances_to_remove}")
        print()
        
        if not footage_with_duplicates:
            print("✅ No duplicates found - cleanup not needed!")
            sys.exit(0)
        
        # Phase 2: Dry run cleanup
        print("🧪 PHASE 2: DRY RUN CLEANUP")
        print("==========================")
        
        total_dry_run_removed = 0
        for footage_id, duplicates in footage_with_duplicates:
            dry_removed, _ = cleanup_duplicates(token, footage_id, duplicates, dry_run=True)
            total_dry_run_removed += dry_removed
        
        print()
        print(f"🧪 DRY RUN SUMMARY: Would remove {total_dry_run_removed} duplicate records")
        print()
        
        # Phase 3: Confirmation and actual cleanup
        print("⚠️  READY FOR ACTUAL CLEANUP")
        print("============================")
        print(f"This will permanently delete {total_instances_to_remove} duplicate frame records.")
        print("The best copy of each frame (with thumbnails/content) will be preserved.")
        print()
        
        # Safety confirmation
        confirm = input("Type 'DELETE' to proceed with cleanup (or anything else to cancel): ").strip()
        
        if confirm != "DELETE":
            print("🛑 Cleanup cancelled by user")
            sys.exit(0)
        
        print()
        print("🗑️ PHASE 3: ACTUAL CLEANUP")
        print("=========================")
        
        total_removed = 0
        total_failed = 0
        
        for footage_id, duplicates in footage_with_duplicates:
            removed, failed = cleanup_duplicates(token, footage_id, duplicates, dry_run=False)
            total_removed += removed
            total_failed += failed
        
        print()
        print("✅ CLEANUP COMPLETE!")
        print("===================")
        print(f"   Successfully removed: {total_removed} duplicate records")
        print(f"   Failed to remove: {total_failed} records")
        print(f"   Footage cleaned: {len(footage_with_duplicates)} records")
        print()
        
        if total_failed > 0:
            print("⚠️  Some deletions failed - you may need to clean these manually")
        else:
            print("🎉 All duplicates successfully removed!")
        
    except KeyboardInterrupt:
        print("\n🛑 Cleanup interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 