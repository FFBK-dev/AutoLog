#!/usr/bin/env python3
"""
Prepare Test Footage for Force Resume Testing

This script sets specific footage records to "Force Resume" status
to test the improved API gatekeeper integration.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.fm_api_helpers import find_footage_records, update_footage_record

def prepare_force_resume_records(start_num, end_num):
    """Prepare footage records LF{start_num} to LF{end_num} for Force Resume testing."""
    print(f"🎬 Preparing Force Resume test for footage LF{start_num:04d} to LF{end_num:04d}")
    
    try:
        token = config.get_token()
        updated_count = 0
        
        for num in range(start_num, end_num + 1):
            footage_id = f"LF{num:04d}"
            
            # Find the footage record
            records = find_footage_records(token, {"INFO_FTG_ID": f"=={footage_id}"}, priority='high')
            
            if not records:
                print(f"  ⚠️ {footage_id}: Record not found")
                continue
            
            record = records[0]
            record_id = record['recordId']
            current_status = record['fieldData'].get('AutoLog_Status', '')
            
            print(f"  📋 {footage_id}: Current status = '{current_status}'")
            
            # Update to Force Resume
            update_data = {"AutoLog_Status": "Force Resume"}
            
            if update_footage_record(token, record_id, update_data, priority='high'):
                print(f"  ✅ {footage_id}: Set to 'Force Resume'")
                updated_count += 1
            else:
                print(f"  ❌ {footage_id}: Failed to update")
        
        print(f"\n🎉 Preparation complete: {updated_count} records set to Force Resume")
        return updated_count
        
    except Exception as e:
        print(f"❌ Error preparing records: {e}")
        return 0

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 prepare_test_footage_force_resume.py <start_num> <end_num>")
        print("Example: python3 prepare_test_footage_force_resume.py 370 375")
        sys.exit(1)
    
    try:
        start_num = int(sys.argv[1])
        end_num = int(sys.argv[2])
        
        if start_num > end_num:
            print("❌ Start number must be <= end number")
            sys.exit(1)
        
        count = prepare_force_resume_records(start_num, end_num)
        
        if count > 0:
            print(f"\n✅ Ready to test Force Resume with {count} records!")
            print(f"🚀 You can now monitor the autolog process to see gatekeeper protection in action")
        else:
            print(f"❌ No records were prepared")
            
    except ValueError:
        print("❌ Start and end numbers must be integers")
        sys.exit(1) 