#!/usr/bin/env python3
"""
Smart Thumbnail Audit - Query frames in manageable chunks by footage pattern
Avoids the 500 error from trying to fetch all frames at once.
"""

import sys
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.fm_api_helpers import find_frame_records, find_footage_records
import subprocess
import argparse

def audit_thumbnails_by_pattern(token, footage_pattern="LF*", max_footage=100):
    """
    Audit thumbnails by querying footage first, then their frames.
    This avoids the 500 error from querying all frames at once.
    """
    print(f"🔍 Auditing thumbnails for footage pattern: {footage_pattern}")
    
    try:
        # Step 1: Get footage records matching the pattern
        print(f"  -> Finding footage records matching {footage_pattern}...")
        footage_records = find_footage_records(
            token, 
            {'INFO_FTG_ID': footage_pattern}, 
            limit=max_footage
        )
        print(f"  -> Found {len(footage_records)} footage records")
        
        if not footage_records:
            print("  -> No footage records found for pattern")
            return [], 0, 0
        
        # Step 2: Check frames for each footage
        all_missing = []
        total_frames = 0
        total_missing = 0
        
        for i, footage in enumerate(footage_records):
            footage_id = footage['fieldData'].get('INFO_FTG_ID')
            if not footage_id:
                continue
                
            print(f"  -> [{i+1}/{len(footage_records)}] Checking {footage_id}...")
            
            try:
                # Get frames for this footage
                frames = find_frame_records(
                    token, 
                    {'FRAMES_ParentID': footage_id}, 
                    limit=50  # Most footage shouldn't have more than 50 frames
                )
                
                if not frames:
                    continue
                
                # Check for missing thumbnails
                missing_in_footage = []
                for frame in frames:
                    total_frames += 1
                    thumbnail = frame['fieldData'].get('FRAMES_Thumbnail', '')
                    frame_id = frame['fieldData'].get('FRAMES_ID')
                    
                    # FileMaker container fields contain URLs/paths when they have content
                    # Empty containers are typically empty strings or very short values
                    if not thumbnail or len(thumbnail.strip()) < 10:
                        missing_in_footage.append({
                            'frame_id': frame_id,
                            'footage_id': footage_id,
                            'record_id': frame['recordId']
                        })
                        total_missing += 1
                
                if missing_in_footage:
                    print(f"    -> ⚠️ {len(missing_in_footage)}/{len(frames)} missing thumbnails")
                    for missing in missing_in_footage:
                        print(f"      - {missing['frame_id']}")
                    all_missing.extend(missing_in_footage)
                else:
                    print(f"    -> ✅ {len(frames)} frames, all thumbnails present")
                    
            except Exception as e:
                print(f"    -> ❌ Error checking {footage_id}: {e}")
                continue
        
        return all_missing, total_frames, total_missing
        
    except Exception as e:
        print(f"❌ Error during audit: {e}")
        import traceback
        traceback.print_exc()
        return [], 0, 0

def fix_missing_thumbnails(token, missing_frames, timeout=300):
    """
    Fix missing thumbnails for the provided frames.
    """
    if not missing_frames:
        print("✅ No missing thumbnails to fix")
        return True
    
    print(f"🔧 Fixing {len(missing_frames)} missing thumbnails...")
    
    fixed = 0
    failed = 0
    
    for missing in missing_frames:
        frame_id = missing['frame_id']
        print(f"  -> Fixing {frame_id}...")
        
        try:
            # Run thumbnail generation script
            cmd = [
                sys.executable,
                "jobs/frames_generate_thumbnails.py",
                frame_id,
                token
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=Path(__file__).resolve().parent.parent
            )
            
            if result.returncode == 0:
                print(f"    -> ✅ Fixed {frame_id}")
                fixed += 1
            else:
                print(f"    -> ❌ Failed {frame_id}: {result.stderr[:100]}")
                failed += 1
                
        except subprocess.TimeoutExpired:
            print(f"    -> ⏱️ Timeout fixing {frame_id}")
            failed += 1
        except Exception as e:
            print(f"    -> ❌ Error fixing {frame_id}: {e}")
            failed += 1
    
    print(f"🔧 Thumbnail fix results: {fixed} fixed, {failed} failed")
    return fixed > 0

def main():
    parser = argparse.ArgumentParser(description='Smart thumbnail audit by footage pattern')
    parser.add_argument('--pattern', default='LF*', help='Footage ID pattern to audit (default: LF*)')
    parser.add_argument('--max-footage', type=int, default=100, help='Maximum footage records to check (default: 100)')
    parser.add_argument('--fix', action='store_true', help='Fix missing thumbnails after audit')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout for thumbnail generation (default: 300s)')
    
    args = parser.parse_args()
    
    try:
        # Get token
        print("🔑 Getting FileMaker token...")
        token = config.get_token()
        print("✅ Token obtained")
        
        # Run audit
        missing_frames, total_frames, total_missing = audit_thumbnails_by_pattern(
            token, 
            args.pattern, 
            args.max_footage
        )
        
        # Print results
        print(f"\n📊 Audit Results:")
        print(f"  -> Total frames checked: {total_frames}")
        print(f"  -> Missing thumbnails: {total_missing}")
        if total_frames > 0:
            print(f"  -> Missing percentage: {(total_missing/total_frames*100):.1f}%")
        
        if missing_frames:
            print(f"\n⚠️ Frames with missing thumbnails:")
            for missing in missing_frames[:10]:  # Show first 10
                print(f"  - {missing['frame_id']} (footage: {missing['footage_id']})")
            if len(missing_frames) > 10:
                print(f"  ... and {len(missing_frames) - 10} more")
        
        # Fix if requested
        if args.fix and missing_frames:
            print(f"\n🔧 Fixing missing thumbnails...")
            fix_missing_thumbnails(token, missing_frames, args.timeout)
        elif missing_frames:
            print(f"\n💡 To fix missing thumbnails, run:")
            print(f"   python3 temp/smart_thumbnail_audit.py --pattern {args.pattern} --fix --timeout={args.timeout}")
        
    except Exception as e:
        print(f"❌ Script failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 