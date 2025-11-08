#!/usr/bin/env python3
"""
Comprehensive Database Audit and Fix

This script performs a complete audit of the footage database to ensure:
1. Correct number of frame records per footage (based on duration)
2. No duplicate frame records
3. All frame records have thumbnails

Usage: python3 database_audit_and_fix.py [--fix] [--footage-id LF0001]
       --fix: Actually perform fixes (default is dry-run)
       --footage-id: Audit specific footage only
"""

import sys
import warnings
import argparse
import time
import os
import subprocess
import json
import math
from pathlib import Path
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "filepath": "SPECS_Filepath_Server",
    "duration": "SPECS_File_Duration_Timecode",
    "framerate": "SPECS_File_Framerate",
    "frame_parent_id": "FRAMES_ParentID", 
    "frame_status": "FRAMES_Status",
    "frame_id": "FRAMES_ID",
    "frame_thumbnail": "FRAMES_Thumbnail",
    "frame_timecode": "FRAMES_TC_IN"
}

class DatabaseAuditor:
    def __init__(self, fix_mode=False):
        self.fix_mode = fix_mode
        self.token = config.get_token()
        self.stats = {
            'footage_processed': 0,
            'footage_with_issues': 0,
            'duplicate_frames_removed': 0,
            'missing_frames_created': 0,
            'thumbnails_generated': 0,
            'errors': 0
        }
        
    def get_video_duration_and_framerate(self, file_path):
        """Get video duration and framerate using FFprobe."""
        try:
            # Find ffprobe
            ffprobe_paths = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', 'ffprobe']
            ffprobe_cmd = None
            
            for path in ffprobe_paths:
                if os.path.exists(path) or path == 'ffprobe':
                    ffprobe_cmd = path
                    break
            
            if not ffprobe_cmd:
                return None, None
            
            cmd = [
                ffprobe_cmd,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                return None, None
            
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            
            # Find video stream and get framerate
            framerate = 30.0  # Default fallback
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    if 'r_frame_rate' in stream:
                        rate_str = stream['r_frame_rate']
                        if '/' in rate_str:
                            num, den = rate_str.split('/')
                            framerate = float(num) / float(den)
                        else:
                            framerate = float(rate_str)
                    break
            
            return duration, framerate
            
        except Exception as e:
            print(f"     Error getting video info: {e}")
            return None, None

    def calculate_expected_frame_count(self, duration, interval=5):
        """Calculate expected number of frames based on video duration."""
        if duration is None:
            return None
        return math.ceil(duration / interval)

    def get_all_footage_records(self):
        """Get all footage records from the database."""
        try:
            footage_records = []
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
                    headers=config.api_headers(self.token),
                    json=query_params,
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 200:
                    records = response.json()['response']['data']
                    for record in records:
                        field_data = record['fieldData']
                        footage_id = field_data.get(FIELD_MAPPING["footage_id"])
                        if footage_id:
                            footage_records.append({
                                'footage_id': footage_id,
                                'record_id': record['recordId'],
                                'field_data': field_data
                            })
                    
                    if len(records) < batch_size:
                        break
                    offset += len(records)
                else:
                    print(f"Error getting footage records: {response.status_code}")
                    break
            
            return footage_records
            
        except Exception as e:
            print(f"Error getting footage records: {e}")
            return []

    def get_frame_records_for_footage(self, footage_id):
        """Get all frame records for a specific footage."""
        try:
            frame_query = {"query": [{FIELD_MAPPING["frame_parent_id"]: footage_id}], "limit": 1000}
            
            response = requests.post(
                config.url("layouts/FRAMES/_find"),
                headers=config.api_headers(self.token),
                json=frame_query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['response']['data']
            elif response.status_code == 404:
                return []
            else:
                print(f"     Error querying frames: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"     Error getting frame records: {e}")
            return []

    def analyze_frame_duplicates(self, frames):
        """Analyze frame records for duplicates and return cleanup plan."""
        frame_groups = {}
        
        for frame in frames:
            field_data = frame['fieldData']
            frame_id = field_data.get(FIELD_MAPPING["frame_id"], f"Unknown_{frame['recordId']}")
            
            if frame_id not in frame_groups:
                frame_groups[frame_id] = []
            
            # Score this frame instance
            score = 0
            if field_data.get(FIELD_MAPPING["frame_thumbnail"], "").strip():
                score += 10
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
        duplicates_to_remove = []
        for frame_id, instances in frame_groups.items():
            if len(instances) > 1:
                # Sort by score (highest first)
                instances.sort(key=lambda x: x['score'], reverse=True)
                
                # Keep the best, mark others for removal
                for instance in instances[1:]:
                    duplicates_to_remove.append({
                        'frame_id': frame_id,
                        'record_id': instance['record_id']
                    })
        
        return duplicates_to_remove, len(set(frame_groups.keys()))

    def remove_duplicate_frames(self, duplicates_to_remove, footage_id):
        """Remove duplicate frame records."""
        removed_count = 0
        
        for duplicate in duplicates_to_remove:
            try:
                if self.fix_mode:
                    delete_response = requests.delete(
                        config.url(f"layouts/FRAMES/records/{duplicate['record_id']}"),
                        headers=config.api_headers(self.token),
                        verify=False,
                        timeout=30
                    )
                    
                    if delete_response.status_code == 200:
                        print(f"     ✅ Removed duplicate {duplicate['frame_id']} (Record {duplicate['record_id']})")
                        removed_count += 1
                    else:
                        print(f"     ❌ Failed to remove {duplicate['frame_id']}: {delete_response.status_code}")
                else:
                    print(f"     [DRY RUN] Would remove duplicate {duplicate['frame_id']} (Record {duplicate['record_id']})")
                    removed_count += 1
                    
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                print(f"     ❌ Error removing {duplicate['frame_id']}: {e}")
        
        return removed_count

    def create_missing_frames(self, footage_id, file_path, current_frame_count, expected_frame_count, duration, framerate):
        """Create missing frame records."""
        if not self.fix_mode:
            print(f"     [DRY RUN] Would create {expected_frame_count - current_frame_count} missing frames")
            return expected_frame_count - current_frame_count
        
        try:
            # Import the frame creation function
            sys.path.append(str(Path(__file__).resolve().parent.parent / "jobs"))
            from footage_autolog_03_create_frames import create_frame_record, format_timecode
            
            created_count = 0
            interval = 5  # 5-second intervals
            
            # Get existing frame numbers to avoid conflicts
            existing_frames = self.get_frame_records_for_footage(footage_id)
            existing_frame_numbers = set()
            
            for frame in existing_frames:
                frame_id = frame['fieldData'].get(FIELD_MAPPING["frame_id"], "")
                if frame_id.startswith(f"{footage_id}_"):
                    try:
                        frame_num = int(frame_id.split("_")[-1])
                        existing_frame_numbers.add(frame_num)
                    except:
                        pass
            
            # Create missing frames
            for i in range(1, expected_frame_count + 1):
                if i not in existing_frame_numbers:
                    timecode_seconds = (i - 1) * interval
                    if timecode_seconds <= duration:
                        success, record_id = create_frame_record(
                            self.token, footage_id, file_path, 
                            timecode_seconds, framerate, i
                        )
                        if success:
                            created_count += 1
                            print(f"     ✅ Created missing frame {footage_id}_{i:03d}")
                        else:
                            print(f"     ❌ Failed to create frame {footage_id}_{i:03d}")
            
            return created_count
            
        except Exception as e:
            print(f"     ❌ Error creating missing frames: {e}")
            return 0

    def check_and_fix_thumbnails(self, frames, footage_id):
        """Check for missing thumbnails and generate them if needed."""
        missing_thumbnails = []
        
        for frame in frames:
            field_data = frame['fieldData']
            frame_id = field_data.get(FIELD_MAPPING["frame_id"], "Unknown")
            has_thumbnail = bool(field_data.get(FIELD_MAPPING["frame_thumbnail"], "").strip())
            
            if not has_thumbnail:
                missing_thumbnails.append({
                    'frame_id': frame_id,
                    'record_id': frame['recordId'],
                    'field_data': field_data
                })
        
        if not missing_thumbnails:
            return 0
        
        print(f"     🖼️ {len(missing_thumbnails)} frames missing thumbnails")
        
        if not self.fix_mode:
            print(f"     [DRY RUN] Would generate {len(missing_thumbnails)} thumbnails")
            return len(missing_thumbnails)
        
        # Generate missing thumbnails
        generated_count = 0
        for missing in missing_thumbnails:
            try:
                # Use the frames_generate_thumbnails script
                script_path = Path(__file__).resolve().parent.parent / "jobs" / "frames_generate_thumbnails.py"
                
                result = subprocess.run(
                    ["python3", str(script_path), missing['frame_id'], self.token],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    print(f"     ✅ Generated thumbnail for {missing['frame_id']}")
                    generated_count += 1
                else:
                    print(f"     ❌ Failed to generate thumbnail for {missing['frame_id']}")
                    
            except Exception as e:
                print(f"     ❌ Error generating thumbnail for {missing['frame_id']}: {e}")
        
        return generated_count

    def audit_footage_record(self, footage_record):
        """Perform complete audit of a single footage record."""
        footage_id = footage_record['footage_id']
        field_data = footage_record['field_data']
        
        print(f"🔍 Auditing {footage_id}...")
        
        has_issues = False
        
        # Get file path and check if file exists
        file_path = field_data.get(FIELD_MAPPING["filepath"], "")
        if not file_path or not os.path.exists(file_path):
            print(f"     ❌ File not found: {file_path}")
            self.stats['errors'] += 1
            return
        
        # Get video duration and framerate
        duration, framerate = self.get_video_duration_and_framerate(file_path)
        if duration is None:
            print(f"     ❌ Could not determine video duration")
            self.stats['errors'] += 1
            return
        
        # Calculate expected frame count
        expected_frame_count = self.calculate_expected_frame_count(duration)
        
        print(f"     📊 Video: {duration:.1f}s @ {framerate:.1f}fps → Expected {expected_frame_count} frames")
        
        # Get current frame records
        frames = self.get_frame_records_for_footage(footage_id)
        current_frame_count = len(frames)
        
        print(f"     📊 Current: {current_frame_count} frame records")
        
        # Check for duplicates
        duplicates_to_remove, unique_frame_count = self.analyze_frame_duplicates(frames)
        
        if duplicates_to_remove:
            has_issues = True
            print(f"     🔴 Found {len(duplicates_to_remove)} duplicate frame records")
            removed_count = self.remove_duplicate_frames(duplicates_to_remove, footage_id)
            self.stats['duplicate_frames_removed'] += removed_count
            
            # Refresh frame list after removing duplicates
            if self.fix_mode:
                frames = self.get_frame_records_for_footage(footage_id)
                current_frame_count = len(frames)
        
        # Check frame count accuracy
        if unique_frame_count != expected_frame_count:
            has_issues = True
            if unique_frame_count < expected_frame_count:
                print(f"     🔴 Missing {expected_frame_count - unique_frame_count} frames")
                created_count = self.create_missing_frames(
                    footage_id, file_path, unique_frame_count, 
                    expected_frame_count, duration, framerate
                )
                self.stats['missing_frames_created'] += created_count
                
                # Refresh frame list after creating frames
                if self.fix_mode:
                    frames = self.get_frame_records_for_footage(footage_id)
            elif unique_frame_count > expected_frame_count:
                print(f"     ⚠️ More frames than expected ({unique_frame_count} vs {expected_frame_count})")
        
        # Check thumbnails
        thumbnail_count = self.check_and_fix_thumbnails(frames, footage_id)
        if thumbnail_count > 0:
            has_issues = True
            self.stats['thumbnails_generated'] += thumbnail_count
        
        if has_issues:
            self.stats['footage_with_issues'] += 1
            print(f"     🔧 Issues found and {'fixed' if self.fix_mode else 'identified'}")
        else:
            print(f"     ✅ No issues found")
        
        self.stats['footage_processed'] += 1

    def run_audit(self, specific_footage_id=None):
        """Run the complete database audit."""
        print("🔍 COMPREHENSIVE DATABASE AUDIT")
        print("===============================")
        print(f"Mode: {'FIX' if self.fix_mode else 'DRY RUN'}")
        print()
        
        if specific_footage_id:
            print(f"🎯 Auditing specific footage: {specific_footage_id}")
            
            # Get specific footage record
            footage_query = {"query": [{FIELD_MAPPING["footage_id"]: specific_footage_id}], "limit": 1}
            response = requests.post(
                config.url("layouts/FOOTAGE/_find"),
                headers=config.api_headers(self.token),
                json=footage_query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                records = response.json()['response']['data']
                if records:
                    footage_record = {
                        'footage_id': specific_footage_id,
                        'record_id': records[0]['recordId'],
                        'field_data': records[0]['fieldData']
                    }
                    self.audit_footage_record(footage_record)
                else:
                    print(f"❌ Footage {specific_footage_id} not found")
            else:
                print(f"❌ Error finding footage {specific_footage_id}: {response.status_code}")
        else:
            print("🔍 Getting all footage records...")
            footage_records = self.get_all_footage_records()
            print(f"📊 Found {len(footage_records)} footage records to audit")
            print()
            
            for i, footage_record in enumerate(footage_records, 1):
                try:
                    print(f"[{i}/{len(footage_records)}]", end=" ")
                    self.audit_footage_record(footage_record)
                    print()
                    
                    # Brief pause to avoid overwhelming the API
                    time.sleep(0.5)
                    
                except KeyboardInterrupt:
                    print("\n🛑 Audit interrupted by user")
                    break
                except Exception as e:
                    print(f"     ❌ Error auditing {footage_record['footage_id']}: {e}")
                    self.stats['errors'] += 1
        
        # Print final summary
        print("📊 AUDIT SUMMARY")
        print("================")
        print(f"Footage processed: {self.stats['footage_processed']}")
        print(f"Footage with issues: {self.stats['footage_with_issues']}")
        print(f"Duplicate frames removed: {self.stats['duplicate_frames_removed']}")
        print(f"Missing frames created: {self.stats['missing_frames_created']}")
        print(f"Thumbnails generated: {self.stats['thumbnails_generated']}")
        print(f"Errors encountered: {self.stats['errors']}")
        print()
        
        if not self.fix_mode and (self.stats['footage_with_issues'] > 0):
            print("💡 Run with --fix to apply the fixes")
        elif self.fix_mode:
            print("✅ All fixes have been applied!")

def main():
    parser = argparse.ArgumentParser(description='Comprehensive Database Audit and Fix')
    parser.add_argument('--fix', action='store_true', 
                        help='Actually perform fixes (default is dry-run)')
    parser.add_argument('--footage-id', type=str, 
                        help='Audit specific footage only (e.g., LF0001)')
    
    args = parser.parse_args()
    
    try:
        auditor = DatabaseAuditor(fix_mode=args.fix)
        auditor.run_audit(specific_footage_id=args.footage_id)
        
    except KeyboardInterrupt:
        print("\n🛑 Audit interrupted by user")
    except Exception as e:
        print(f"❌ Critical error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 