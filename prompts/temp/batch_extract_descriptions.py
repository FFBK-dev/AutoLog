#!/usr/bin/env python3
"""
Batch script to extract IPTC descriptions for all stills records.
Processes records safely with rate limiting and batch updates.
"""

import sys
import time
import json
import subprocess
import warnings
from pathlib import Path
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "import_path": "SPECS_Filepath_Import",
    "description_orig": "INFO_Description_Original"
}

def safe_get(metadata_dict, key, default=''):
    """Helper function to safely get metadata values."""
    return metadata_dict.get(key, default)

def extract_comprehensive_description(metadata):
    """Extract description from multiple IPTC/EXIF fields and combine intelligently."""
    # Description fields in nested structure (group, field) with priority order
    description_fields = [
        ('IPTC', 'Caption-Abstract'),        # Primary IPTC description field
        ('IPTC', 'Headline'),                # IPTC headline  
        ('XMP-dc', 'Description'),           # Dublin Core description
        ('XMP-iptcCore', 'Caption'),         # XMP IPTC caption
        ('EXIF', 'ImageDescription'),        # EXIF image description
        ('IPTC', 'ObjectName'),              # IPTC object name
        ('XMP-dc', 'Title'),                 # Dublin Core title
        ('IPTC', 'SpecialInstructions'),     # IPTC special instructions
        ('XMP-iptcCore', 'Headline'),        # XMP IPTC headline
        ('XMP-photoshop', 'Headline'),       # Photoshop headline
        ('XMP-photoshop', 'Instructions')   # Photoshop instructions
    ]
    
    descriptions = []
    found_fields = []
    
    # Extract all available description fields from nested structure
    for group, field in description_fields:
        group_data = metadata.get(group, {})
        if isinstance(group_data, dict):
            value = group_data.get(field, '')
            if value and str(value).strip():
                # Clean up the value and convert to string if needed
                cleaned_value = str(value).strip()
                # Only add if it's not a duplicate and has meaningful content
                if cleaned_value and cleaned_value not in descriptions and len(cleaned_value) > 3:
                    descriptions.append(cleaned_value)
                    found_fields.append(f"{group}:{field}")
    
    if not descriptions:
        return ""
    
    # If we have multiple descriptions, combine them intelligently
    if len(descriptions) == 1:
        final_description = descriptions[0]
    else:
        # Combine multiple descriptions, with the primary one first
        final_description = descriptions[0]
        
        # Add additional descriptions that aren't just duplicates or substrings
        additional_info = []
        for desc in descriptions[1:]:
            # Only add if it's not a substring of the main description and adds value
            if desc.lower() not in final_description.lower() and final_description.lower() not in desc.lower():
                additional_info.append(desc)
        
        if additional_info:
            final_description += " | " + " | ".join(additional_info)
    
    return final_description

def get_all_stills_records(token):
    """Get all stills records from FileMaker."""
    print(f"🔍 Fetching all stills records from FileMaker...")
    
    try:
        # Get all records - FileMaker can handle this efficiently
        import requests
        response = requests.get(
            config.url("layouts/Stills/records"),
            headers=config.api_headers(token),
            params={'_limit': 10000},  # High limit to get all records
            verify=False
        )
        
        records = response.json()['response']['data']
        print(f"📋 Found {len(records)} total stills records")
        return records
        
    except Exception as e:
        print(f"❌ Error fetching records: {e}")
        return []

def process_single_record(record, token, exiftool_cmd):
    """Process a single record to extract IPTC description."""
    record_id = record['recordId']
    field_data = record['fieldData']
    stills_id = field_data.get(FIELD_MAPPING["stills_id"], '')
    import_path = field_data.get(FIELD_MAPPING["import_path"], '')
    current_description = field_data.get(FIELD_MAPPING["description_orig"], '')
    
    # Skip if already has description or no import path
    if current_description and current_description.strip():
        return None, "already_has_description"
    
    if not import_path:
        return None, "no_import_path"
    
    if not Path(import_path).exists():
        return None, "file_not_found"
    
    try:
        # Extract EXIF metadata using exiftool
        result = subprocess.run(
            [exiftool_cmd, '-j', '-g1', '-S', import_path], 
            capture_output=True, 
            text=True,
            timeout=30  # 30 second timeout per file
        )
        
        if result.returncode != 0:
            return None, f"exiftool_error: {result.stderr[:100]}"
        
        metadata = json.loads(result.stdout)[0]
        description = extract_comprehensive_description(metadata)
        
        if description:
            return {
                "record_id": record_id,
                "stills_id": stills_id,
                "description": description
            }, "extracted"
        else:
            return None, "no_description_found"
            
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, f"error: {str(e)[:100]}"

def batch_update_descriptions(updates, token):
    """Update multiple records in batch with rate limiting."""
    if not updates:
        return True
    
    success_count = 0
    
    for update in updates:
        try:
            # Update individual record
            field_data = {FIELD_MAPPING["description_orig"]: update["description"]}
            config.update_record(token, "Stills", update["record_id"], field_data)
            success_count += 1
            
            # Small delay between updates to be gentle on FileMaker
            time.sleep(0.1)
            
        except Exception as e:
            print(f"  ❌ Failed to update {update['stills_id']}: {e}")
    
    return success_count

def main():
    """Main batch processing function."""
    print(f"🚀 Starting batch IPTC description extraction")
    print(f"📅 Started at: {datetime.now()}")
    
    try:
        # Get FileMaker token
        token = config.get_token()
        print(f"✅ Got FileMaker token")
        
        # Find exiftool
        exiftool_paths = ['/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool', 'exiftool']
        exiftool_cmd = None
        
        for path in exiftool_paths:
            if Path(path).exists() or path == 'exiftool':
                exiftool_cmd = path
                break
        
        if not exiftool_cmd:
            raise RuntimeError("ExifTool not found in any expected location")
        
        print(f"🔧 Using exiftool at: {exiftool_cmd}")
        
        # Get all records
        records = get_all_stills_records(token)
        if not records:
            print(f"❌ No records found")
            return
        
        # Processing statistics
        stats = {
            "total": len(records),
            "processed": 0,
            "extracted": 0,
            "already_has_description": 0,
            "no_import_path": 0,
            "file_not_found": 0,
            "no_description_found": 0,
            "errors": 0
        }
        
        # Process in batches of 50 for manageable progress reporting
        batch_size = 50
        updates_pending = []
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            batch_updates = []
            
            print(f"\n📦 Processing batch {i//batch_size + 1}/{(len(records)-1)//batch_size + 1} (records {i+1}-{min(i+batch_size, len(records))})")
            
            for record in batch:
                result, status = process_single_record(record, token, exiftool_cmd)
                stats["processed"] += 1
                stats[status] = stats.get(status, 0) + 1
                
                if result:
                    batch_updates.append(result)
                    stats["extracted"] += 1
                    print(f"  ✅ {result['stills_id']}: {result['description'][:80]}...")
                elif status == "already_has_description":
                    print(f"  ⏭️ {record['fieldData'].get(FIELD_MAPPING['stills_id'], 'Unknown')}: Already has description")
                elif status != "no_description_found":  # Only show interesting errors
                    print(f"  ⚠️ {record['fieldData'].get(FIELD_MAPPING['stills_id'], 'Unknown')}: {status}")
            
            # Update this batch in FileMaker
            if batch_updates:
                success_count = batch_update_descriptions(batch_updates, token)
                print(f"  💾 Updated {success_count}/{len(batch_updates)} records in FileMaker")
            
            # Progress update
            progress = (stats["processed"] / stats["total"]) * 100
            print(f"  📊 Progress: {progress:.1f}% ({stats['processed']}/{stats['total']})")
            
            # Rate limiting - pause between batches
            if i + batch_size < len(records):  # Don't sleep after the last batch
                time.sleep(2)  # 2 second pause between batches
        
        # Final statistics
        print(f"\n🎯 Batch processing complete!")
        print(f"📅 Finished at: {datetime.now()}")
        print(f"📊 Final Statistics:")
        print(f"  Total records: {stats['total']}")
        print(f"  Successfully extracted: {stats['extracted']}")
        print(f"  Already had descriptions: {stats['already_has_description']}")
        print(f"  No import path: {stats['no_import_path']}")
        print(f"  File not found: {stats['file_not_found']}")
        print(f"  No description in metadata: {stats['no_description_found']}")
        print(f"  Errors: {stats.get('errors', 0)}")
        
        extraction_rate = (stats['extracted'] / stats['total']) * 100
        print(f"  📈 Extraction success rate: {extraction_rate:.1f}%")
        
    except Exception as e:
        print(f"💥 Critical error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 