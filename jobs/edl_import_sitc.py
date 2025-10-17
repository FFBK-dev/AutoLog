#!/usr/bin/env python3
"""
EDL Import to SITC Table Job

This job parses EDL files from Avid Media Composer and creates records in the SITC table
with timing information for still images. Each still image (S####) gets a record with:
- SITC_STILLS_ID: The still image ID (S0001, S0425, etc.)
- SPECS_AVID_TC_IN: Timeline start timecode (Dst In)
- SPECS_AVID_TC_OUT: Timeline end timecode (Dst Out)

Arguments:
- edl_file_path: Path to the EDL file to process
"""

import sys
import warnings
import re
import json
import os
import requests
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["edl_file_path"]

FIELD_MAPPING = {
    "stills_id": "SITC_STILLS_ID",
    "tc_in": "SPECS_AVID_TC_IN",
    "tc_out": "SPECS_AVID_TC_OUT"
}

def parse_edl_line(line):
    """Parse a single EDL line to extract relevant information."""
    # Skip comment lines and empty lines
    if line.startswith('*') or line.strip() == '' or line.startswith('TITLE:') or line.startswith('FCM:'):
        return None
    
    # Split the line by whitespace
    parts = line.split()
    
    if len(parts) < 8:
        return None
    
    # EDL format: 
    # [0]Edit# [1]Source [2]Track [3]Edit_Type [4]Src_In [5]Src_Out [6]Dst_In [7]Dst_Out
    try:
        edit_number = parts[0]
        source_name = parts[1]
        track = parts[2]
        edit_type = parts[3]
        src_in = parts[4]
        src_out = parts[5]
        dst_in = parts[6]
        dst_out = parts[7]
        
        return {
            'edit_number': edit_number,
            'source_name': source_name,
            'track': track,
            'edit_type': edit_type,
            'src_in': src_in,
            'src_out': src_out,
            'dst_in': dst_in,
            'dst_out': dst_out
        }
    except (IndexError, ValueError):
        return None

def extract_still_id(source_name):
    """Extract S#### ID from source name."""
    # Look for S followed by digits, with optional file extensions
    patterns = [
        r'S(\d{4})',  # S0001, S1234, etc.
        r'S(\d{3})',  # S001, S123, etc.
        r'S(\d{2})',  # S01, S12, etc.
        r'S(\d{1})',  # S1, S2, etc.
    ]
    
    for pattern in patterns:
        match = re.search(pattern, source_name, re.IGNORECASE)
        if match:
            # Pad with zeros to make it 4 digits
            number = match.group(1).zfill(4)
            return f"S{number}"
    
    return None

def parse_edl_file(file_path):
    """Parse an EDL file and extract still image entries."""
    still_entries = []
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"EDL file not found: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
    except UnicodeDecodeError:
        # Try with different encoding if UTF-8 fails
        with open(file_path, 'r', encoding='latin-1') as file:
            lines = file.readlines()
    
    print(f"📄 Processing {len(lines)} lines from EDL file...")
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
            
        parsed = parse_edl_line(line)
        if not parsed:
            continue
        
        # Extract still ID
        still_id = extract_still_id(parsed['source_name'])
        if still_id:
            entry = {
                'line_number': line_num,
                'still_id': still_id,
                'source_name': parsed['source_name'],
                'track': parsed['track'],
                'dst_in': parsed['dst_in'],
                'dst_out': parsed['dst_out'],
                'edit_number': parsed['edit_number']
            }
            still_entries.append(entry)
            print(f"  📋 Found: {still_id} | {parsed['dst_in']} → {parsed['dst_out']}")
    
    return still_entries

def validate_timecode(timecode):
    """Validate timecode format (HH:MM:SS:FF)."""
    pattern = r'^\d{2}:\d{2}:\d{2}:\d{2}$'
    return bool(re.match(pattern, timecode))

def create_sitc_record(entry, token):
    """Create a SITC record in FileMaker for a still image entry."""
    
    # Validate timecodes
    if not validate_timecode(entry['dst_in']) or not validate_timecode(entry['dst_out']):
        print(f"  ❌ Invalid timecode format for {entry['still_id']}: {entry['dst_in']} → {entry['dst_out']}")
        return False
    
    # Prepare record data - only the essential fields
    record_data = {
        FIELD_MAPPING["stills_id"]: entry['still_id'],
        FIELD_MAPPING["tc_in"]: entry['dst_in'],
        FIELD_MAPPING["tc_out"]: entry['dst_out']
    }
    
    # Create the record
    payload = {"fieldData": record_data}
    
    try:
        response = requests.post(
            config.url("layouts/SITC/records"),
            headers=config.api_headers(token),
            json=payload,
            verify=False,
            timeout=30
        )
        
        if response.status_code in [200, 201]:  # FileMaker can return either 200 or 201 for successful creation
            response_data = response.json()
            if response_data.get('messages', [{}])[0].get('code') == '0':  # Code '0' means success in FileMaker
                record_id = response_data.get('response', {}).get('recordId', 'unknown')
                print(f"  ✅ Created SITC record for {entry['still_id']} (ID: {record_id})")
                return True
            else:
                print(f"  ❌ Failed to create SITC record for {entry['still_id']}: FileMaker error")
                print(f"      Response: {response.text}")
                return False
        else:
            print(f"  ❌ Failed to create SITC record for {entry['still_id']}: HTTP {response.status_code}")
            print(f"      Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error creating SITC record for {entry['still_id']}: {e}")
        return False

def check_existing_records(entries, token):
    """Check for existing SITC records to avoid duplicates."""
    print(f"🔍 Checking for existing SITC records...")
    
    new_entries = []
    existing_count = 0
    
    for entry in entries:
        try:
            # Search for existing record with same stills_id, tc_in, and tc_out
            query = {
                "query": [
                    {
                        FIELD_MAPPING["stills_id"]: entry['still_id'],
                        FIELD_MAPPING["tc_in"]: entry['dst_in'],
                        FIELD_MAPPING["tc_out"]: entry['dst_out']
                    }
                ]
            }
            
            response = requests.post(
                config.url("layouts/SITC/records/_find"),
                headers=config.api_headers(token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                # Record exists
                existing_count += 1
                print(f"  📌 Skipping existing: {entry['still_id']} ({entry['dst_in']} → {entry['dst_out']})")
            elif response.status_code == 404:
                # Record doesn't exist, add to new entries
                new_entries.append(entry)
            else:
                # Error checking, assume it's new to be safe
                print(f"  ⚠️  Could not check {entry['still_id']}, treating as new")
                new_entries.append(entry)
                
        except Exception as e:
            print(f"  ⚠️  Error checking {entry['still_id']}: {e}")
            new_entries.append(entry)
    
    print(f"  📊 Found {existing_count} existing records, {len(new_entries)} new records to create")
    return new_entries

def main():
    if len(sys.argv) != 2:
        print("❌ Usage: python edl_import_sitc.py <edl_file_path>")
        print("   Example: python edl_import_sitc.py /path/to/file.edl")
        sys.exit(1)
    
    edl_file_path = sys.argv[1]
    
    print("🎬 EDL Import to SITC Table")
    print(f"📁 File: {edl_file_path}")
    print("-" * 80)
    
    try:
        # Get FileMaker token
        print("🔐 Authenticating with FileMaker...")
        token = config.get_token()
        
        # Parse EDL file
        print("📄 Parsing EDL file...")
        still_entries = parse_edl_file(edl_file_path)
        
        if not still_entries:
            print("❌ No still images found in EDL file")
            sys.exit(1)
        
        print(f"📊 Found {len(still_entries)} still image entries")
        
        # Check for existing records
        new_entries = check_existing_records(still_entries, token)
        
        if not new_entries:
            print("✅ All records already exist in SITC table")
            sys.exit(0)
        
        # Create new records
        print(f"🔄 Creating {len(new_entries)} new SITC records...")
        
        success_count = 0
        for entry in new_entries:
            if create_sitc_record(entry, token):
                success_count += 1
        
        # Summary
        print("-" * 80)
        print(f"📊 Import Summary:")
        print(f"  🎯 Total entries found: {len(still_entries)}")
        print(f"  📌 Already existed: {len(still_entries) - len(new_entries)}")
        print(f"  ✅ Successfully created: {success_count}")
        print(f"  ❌ Failed to create: {len(new_entries) - success_count}")
        
        if success_count == len(new_entries):
            print("🎉 EDL import completed successfully!")
        else:
            print("⚠️  EDL import completed with some errors")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Critical error during EDL import: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 