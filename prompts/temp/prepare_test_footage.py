#!/usr/bin/env python3
"""
Prepare Test Footage Records

This script helps prepare footage records for testing by:
- Finding records with specific criteria
- Setting them to desired test statuses
- Providing detailed logging of changes
"""

import sys
import warnings
from pathlib import Path
import requests
import argparse

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.logger import get_logger, create_session_log

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "status": "AutoLog_Status",
    "dev_console": "AI_DevConsole"
}

class TestPreparator:
    def __init__(self):
        self.logger = get_logger("test_preparation")
        self.session_logger, self.session_file = create_session_log("test_prep")
        self.token = config.get_token()
    
    def find_footage_records(self, limit=50, status_filter=None):
        """Find footage records for testing."""
        self.logger.info(f"🔍 Finding footage records (limit: {limit})")
        
        try:
            query = {"query": [{"INFO_FTG_ID": "*"}], "limit": limit}
            
            if status_filter:
                query["query"] = [{"AutoLog_Status": status_filter}]
                self.logger.info(f"Filtering by status: {status_filter}")
            
            response = requests.post(
                config.url("layouts/FOOTAGE/_find"),
                headers=config.api_headers(self.token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                records = response.json()['response']['data']
                self.logger.info(f"✅ Found {len(records)} footage records")
                return records
            elif response.status_code == 404:
                self.logger.warning("⚠️ No records found matching criteria")
                return []
            else:
                self.logger.error(f"❌ API error: {response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error finding records: {e}")
            return []
    
    def update_footage_status(self, record_id, footage_id, new_status, clear_console=True):
        """Update a footage record's status."""
        try:
            update_data = {
                "fieldData": {
                    FIELD_MAPPING["status"]: new_status
                }
            }
            
            # Clear dev console if requested
            if clear_console:
                update_data["fieldData"][FIELD_MAPPING["dev_console"]] = f"[TEST PREP] Status set to '{new_status}' for testing"
            
            response = requests.patch(
                config.url(f"layouts/FOOTAGE/records/{record_id}"),
                headers=config.api_headers(self.token),
                json=update_data,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                self.logger.info(f"✅ Updated {footage_id} to '{new_status}'")
                self.session_logger.info(f"Updated {footage_id}: {new_status}")
                return True
            else:
                self.logger.error(f"❌ Failed to update {footage_id}: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error updating {footage_id}: {e}")
            return False
    
    def clear_frame_records(self, footage_id):
        """Clear all frame records for a footage item."""
        try:
            self.logger.info(f"🗑️ Clearing frame records for {footage_id}")
            
            # Find frame records
            frame_query = {"query": [{"FRAMES_ParentID": footage_id}], "limit": 200}
            response = requests.post(
                config.url("layouts/FRAMES/_find"),
                headers=config.api_headers(self.token),
                json=frame_query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 404:
                self.logger.info(f"✅ No frame records found for {footage_id}")
                return True
            elif response.status_code != 200:
                self.logger.error(f"❌ Failed to find frames for {footage_id}: {response.status_code}")
                return False
            
            frames = response.json()['response']['data']
            self.logger.info(f"Found {len(frames)} frame records to delete")
            
            # Delete each frame record
            deleted_count = 0
            for frame in frames:
                try:
                    delete_response = requests.delete(
                        config.url(f"layouts/FRAMES/records/{frame['recordId']}"),
                        headers=config.api_headers(self.token),
                        verify=False,
                        timeout=30
                    )
                    
                    if delete_response.status_code == 200:
                        deleted_count += 1
                    else:
                        self.logger.warning(f"⚠️ Failed to delete frame record {frame['recordId']}")
                        
                except Exception as e:
                    self.logger.error(f"❌ Error deleting frame record: {e}")
            
            self.logger.info(f"✅ Deleted {deleted_count}/{len(frames)} frame records for {footage_id}")
            return deleted_count == len(frames)
            
        except Exception as e:
            self.logger.error(f"❌ Error clearing frames for {footage_id}: {e}")
            return False
    
    def prepare_test_batch(self, count=30, target_status="0 - Pending File Info", clear_frames=False):
        """Prepare a batch of test footage records."""
        self.logger.info(f"🧪 Preparing {count} test records with status '{target_status}'")
        self.session_logger.info(f"Starting test preparation: {count} records -> '{target_status}'")
        
        # Find records that are NOT in the target status
        all_records = self.find_footage_records(limit=100)
        if not all_records:
            self.logger.error("❌ No records found to prepare")
            return
        
        # Filter for records not already in target status
        candidates = []
        for record in all_records:
            current_status = record['fieldData'].get(FIELD_MAPPING["status"], "")
            if current_status != target_status:
                candidates.append(record)
        
        if len(candidates) < count:
            self.logger.warning(f"⚠️ Only {len(candidates)} candidates available (requested {count})")
            count = len(candidates)
        
        # Select the first N candidates
        selected_records = candidates[:count]
        
        self.logger.info(f"📋 Selected {len(selected_records)} records for preparation")
        
        # Process each record
        success_count = 0
        for record in selected_records:
            footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
            record_id = record['recordId']
            
            if not footage_id:
                continue
            
            # Clear frames if requested
            if clear_frames:
                if not self.clear_frame_records(footage_id):
                    self.logger.warning(f"⚠️ Failed to clear frames for {footage_id}")
            
            # Update status
            if self.update_footage_status(record_id, footage_id, target_status):
                success_count += 1
        
        self.logger.info(f"✅ Successfully prepared {success_count}/{len(selected_records)} test records")
        self.session_logger.info(f"Test preparation complete: {success_count} records ready")
        
        return success_count

def main():
    parser = argparse.ArgumentParser(description='Prepare footage records for testing')
    parser.add_argument('--count', type=int, default=30, 
                        help='Number of records to prepare (default: 30)')
    parser.add_argument('--status', type=str, default="0 - Pending File Info",
                        help='Target status to set (default: "0 - Pending File Info")')
    parser.add_argument('--clear-frames', action='store_true',
                        help='Clear existing frame records')
    parser.add_argument('--list-statuses', action='store_true',
                        help='List current status distribution')
    
    args = parser.parse_args()
    
    preparator = TestPreparator()
    
    if args.list_statuses:
        print("📊 Current Status Distribution:")
        records = preparator.find_footage_records(limit=1000)
        status_counts = {}
        
        for record in records:
            status = record['fieldData'].get(FIELD_MAPPING["status"], "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        for status, count in sorted(status_counts.items()):
            print(f"   {status}: {count}")
        return
    
    print(f"🧪 PREPARING TEST FOOTAGE RECORDS")
    print(f"Count: {args.count}")
    print(f"Target Status: {args.status}")
    print(f"Clear Frames: {args.clear_frames}")
    print(f"Session Log: {preparator.session_file}")
    print()
    
    # Confirm with user
    confirm = input("Proceed with test preparation? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Test preparation cancelled")
        return
    
    # Prepare test batch
    success_count = preparator.prepare_test_batch(
        count=args.count,
        target_status=args.status,
        clear_frames=args.clear_frames
    )
    
    print(f"\n✅ Test preparation complete!")
    print(f"Successfully prepared: {success_count} records")
    print(f"You can now run: python3 temp/monitor_autolog.py")

if __name__ == "__main__":
    main() 