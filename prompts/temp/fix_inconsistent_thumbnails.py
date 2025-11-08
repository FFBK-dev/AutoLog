#!/usr/bin/env python3
"""
Fix Inconsistent Thumbnails - Frames marked as "Complete" but with empty thumbnail containers
Resets their status to "1 - Pending Thumbnail" to trigger regeneration.
"""

import sys
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.fm_api_helpers import find_frame_records, update_frame_record
import argparse

def fix_inconsistent_thumbnails(token, missing_frames):
    """
    Fix frames that have "Complete" status but empty thumbnail containers.
    Resets their status to "1 - Pending Thumbnail" to trigger regeneration.
    """
    if not missing_frames:
        print("✅ No inconsistent thumbnails to fix")
        return True
    
    print(f"🔧 Fixing {len(missing_frames)} frames with inconsistent thumbnail status...")
    
    fixed = 0
    failed = 0
    
    for missing in missing_frames:
        frame_id = missing['frame_id']
        record_id = missing['record_id']
        
        print(f"  -> Resetting status for {frame_id} (Record ID: {record_id})...")
        
        try:
            # Update the frame status to trigger thumbnail regeneration
            update_data = {
                "FRAMES_Status": "1 - Pending Thumbnail"
            }
            
            success = update_frame_record(token, record_id, update_data, priority='low')
            
            if success:
                print(f"    -> ✅ Reset {frame_id} to 'Pending Thumbnail'")
                fixed += 1
            else:
                print(f"    -> ❌ Failed to reset {frame_id}")
                failed += 1
                
        except Exception as e:
            print(f"    -> ❌ Error resetting {frame_id}: {e}")
            failed += 1
    
    print(f"🔧 Status reset results: {fixed} reset, {failed} failed")
    
    if fixed > 0:
        print(f"\n💡 Now run the regular thumbnail generation workflow:")
        print(f"   python3 jobs/frames_generate_thumbnails.py")
        print(f"   This will pick up the frames with 'Pending Thumbnail' status")
    
    return fixed > 0

def audit_and_fix_by_pattern(token, footage_pattern="LF*", max_footage=100, fix=False):
    """
    Audit and optionally fix thumbnails by footage pattern.
    """
    print(f"🔍 Auditing thumbnails for footage pattern: {footage_pattern}")
    
    try:
        # Import the audit function from smart_thumbnail_audit
        from temp.smart_thumbnail_audit import audit_thumbnails_by_pattern
        
        # Run the audit
        missing_frames, total_frames, total_missing = audit_thumbnails_by_pattern(
            token, footage_pattern, max_footage
        )
        
        # Print results
        print(f"\n📊 Audit Results:")
        print(f"  -> Total frames checked: {total_frames}")
        print(f"  -> Missing thumbnails: {total_missing}")
        if total_frames > 0:
            print(f"  -> Missing percentage: {(total_missing/total_frames*100):.1f}%")
        
        if missing_frames:
            print(f"\n⚠️ Frames with empty thumbnail containers:")
            for missing in missing_frames[:10]:  # Show first 10
                print(f"  - {missing['frame_id']} (footage: {missing['footage_id']})")
            if len(missing_frames) > 10:
                print(f"  ... and {len(missing_frames) - 10} more")
        
        # Fix if requested
        if fix and missing_frames:
            print(f"\n🔧 Fixing inconsistent thumbnail status...")
            fix_inconsistent_thumbnails(token, missing_frames)
        elif missing_frames:
            print(f"\n💡 To fix inconsistent thumbnails, run:")
            print(f"   python3 temp/fix_inconsistent_thumbnails.py --pattern {footage_pattern} --fix")
        
        return missing_frames, total_frames, total_missing
        
    except Exception as e:
        print(f"❌ Error during audit: {e}")
        import traceback
        traceback.print_exc()
        return [], 0, 0

def main():
    parser = argparse.ArgumentParser(description='Fix frames with inconsistent thumbnail status')
    parser.add_argument('--pattern', default='LF040*', help='Footage ID pattern to audit (default: LF040*)')
    parser.add_argument('--max-footage', type=int, default=100, help='Maximum footage records to check (default: 100)')
    parser.add_argument('--fix', action='store_true', help='Fix inconsistent thumbnail status after audit')
    
    args = parser.parse_args()
    
    try:
        # Get token
        print("🔑 Getting FileMaker token...")
        token = config.get_token()
        print("✅ Token obtained")
        
        # Run audit and fix
        missing_frames, total_frames, total_missing = audit_and_fix_by_pattern(
            token, 
            args.pattern, 
            args.max_footage,
            args.fix
        )
        
        if args.fix and missing_frames:
            print(f"\n🎯 Next Steps:")
            print(f"1. Run: python3 jobs/frames_generate_thumbnails.py")
            print(f"2. This will process the {len(missing_frames)} frames now marked as 'Pending Thumbnail'")
            print(f"3. Check results with: python3 temp/smart_thumbnail_audit.py --pattern {args.pattern}")
        
    except Exception as e:
        print(f"❌ Script failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 