#!/usr/bin/env python3
"""
Efficient batch script to extract IPTC descriptions from existing INFO_Metadata fields.
Much faster than processing 7,392 image files with ExifTool.
"""

import sys
import time
import json
import sqlite3
import warnings
from pathlib import Path
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "metadata": "INFO_Metadata",
    "description_orig": "INFO_Description_Original"
}

def extract_comprehensive_description(metadata):
    """Extract description from multiple IPTC/EXIF fields and combine intelligently."""
    if not metadata:
        return ""
    
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

def fetch_all_metadata(token):
    """Fetch all records with metadata from FileMaker and store in SQLite."""
    print(f"🔍 Fetching all stills records with metadata from FileMaker...")
    
    try:
        import requests
        
        # Fetch records in batches to avoid FileMaker limits
        all_records = []
        batch_size = 1000
        offset = 1
        
        while True:
            print(f"  📦 Fetching batch starting at record {offset}...")
            
            response = requests.get(
                config.url("layouts/Stills/records"),
                headers=config.api_headers(token),
                params={'_limit': batch_size, '_offset': offset},
                verify=False
            )
            
            if response.status_code == 404:
                # No more records
                break
                
            response.raise_for_status()
            batch_records = response.json()['response']['data']
            
            if not batch_records:
                # No more records
                break
            
            all_records.extend(batch_records)
            print(f"    Got {len(batch_records)} records (total so far: {len(all_records)})")
            
            # If we got fewer records than the batch size, we're done
            if len(batch_records) < batch_size:
                break
            
            offset += batch_size
            
            # Small delay between batches
            time.sleep(0.5)
        
        records = all_records
        print(f"📋 Found {len(records)} total stills records")
        
        # Create temporary SQLite database
        db_path = Path("temp/metadata_extraction.db")
        db_path.parent.mkdir(exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stills_metadata (
                record_id TEXT PRIMARY KEY,
                stills_id TEXT,
                metadata_json TEXT,
                current_description TEXT,
                extracted_description TEXT
            )
        ''')
        
        # Insert records
        records_with_metadata = 0
        records_with_existing_desc = 0
        
        for record in records:
            record_id = record['recordId']
            field_data = record['fieldData']
            stills_id = field_data.get(FIELD_MAPPING["stills_id"], '')
            metadata_json = field_data.get(FIELD_MAPPING["metadata"], '')
            current_description = field_data.get(FIELD_MAPPING["description_orig"], '')
            
            if metadata_json:
                records_with_metadata += 1
            
            if current_description and current_description.strip():
                records_with_existing_desc += 1
            
            cursor.execute('''
                INSERT OR REPLACE INTO stills_metadata 
                (record_id, stills_id, metadata_json, current_description, extracted_description)
                VALUES (?, ?, ?, ?, ?)
            ''', (record_id, stills_id, metadata_json, current_description, None))
        
        conn.commit()
        
        print(f"💾 Stored {len(records)} records in temporary database")
        print(f"📊 {records_with_metadata} records have metadata")
        print(f"📊 {records_with_existing_desc} records already have descriptions")
        
        return conn, db_path
        
    except Exception as e:
        print(f"❌ Error fetching records: {e}")
        return None, None

def process_metadata_batch(conn):
    """Process all metadata to extract descriptions."""
    print(f"🔄 Processing metadata to extract descriptions...")
    
    cursor = conn.cursor()
    
    # Get records that need processing (have metadata but no current description)
    cursor.execute('''
        SELECT record_id, stills_id, metadata_json 
        FROM stills_metadata 
        WHERE metadata_json != '' 
        AND (current_description IS NULL OR current_description = '')
    ''')
    
    records_to_process = cursor.fetchall()
    print(f"📋 Found {len(records_to_process)} records to process")
    
    stats = {
        "total": len(records_to_process),
        "extracted": 0,
        "no_description": 0,
        "errors": 0
    }
    
    for i, (record_id, stills_id, metadata_json) in enumerate(records_to_process):
        try:
            # Parse the JSON metadata
            metadata = json.loads(metadata_json)
            
            # Extract description
            description = extract_comprehensive_description(metadata)
            
            if description:
                # Update the database
                cursor.execute('''
                    UPDATE stills_metadata 
                    SET extracted_description = ? 
                    WHERE record_id = ?
                ''', (description, record_id))
                
                stats["extracted"] += 1
                print(f"  ✅ {stills_id}: {description[:80]}...")
            else:
                stats["no_description"] += 1
                
        except json.JSONDecodeError:
            stats["errors"] += 1
            print(f"  ❌ {stills_id}: Invalid JSON metadata")
        except Exception as e:
            stats["errors"] += 1
            print(f"  ❌ {stills_id}: Error - {e}")
        
        # Progress update every 100 records
        if (i + 1) % 100 == 0:
            progress = ((i + 1) / len(records_to_process)) * 100
            print(f"  📊 Progress: {progress:.1f}% ({i + 1}/{len(records_to_process)})")
    
    conn.commit()
    
    print(f"\n🎯 Metadata processing complete!")
    print(f"📊 Statistics:")
    print(f"  Total processed: {stats['total']}")
    print(f"  Successfully extracted: {stats['extracted']}")
    print(f"  No description found: {stats['no_description']}")
    print(f"  Errors: {stats['errors']}")
    
    return stats["extracted"]

def batch_update_filemaker(conn, token):
    """Update FileMaker with extracted descriptions."""
    print(f"💾 Updating FileMaker with extracted descriptions...")
    
    cursor = conn.cursor()
    
    # Get records with extracted descriptions
    cursor.execute('''
        SELECT record_id, stills_id, extracted_description 
        FROM stills_metadata 
        WHERE extracted_description IS NOT NULL 
        AND extracted_description != ''
    ''')
    
    updates = cursor.fetchall()
    print(f"📋 Found {len(updates)} records to update in FileMaker")
    
    if not updates:
        print(f"  Nothing to update")
        return 0
    
    success_count = 0
    
    # Process in batches of 50
    batch_size = 50
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i+batch_size]
        
        print(f"  📦 Updating batch {i//batch_size + 1}/{(len(updates)-1)//batch_size + 1} ({len(batch)} records)")
        
        for record_id, stills_id, description in batch:
            try:
                # Update FileMaker record
                field_data = {FIELD_MAPPING["description_orig"]: description}
                config.update_record(token, "Stills", record_id, field_data)
                success_count += 1
                
                # Small delay between updates
                time.sleep(0.1)
                
            except Exception as e:
                print(f"    ❌ Failed to update {stills_id}: {e}")
        
        # Progress update
        progress = ((i + batch_size) / len(updates)) * 100
        print(f"    📊 Progress: {min(progress, 100):.1f}% ({min(i + batch_size, len(updates))}/{len(updates)})")
        
        # Rate limiting between batches
        if i + batch_size < len(updates):
            time.sleep(2)
    
    print(f"  ✅ Successfully updated {success_count}/{len(updates)} records")
    return success_count

def main():
    """Main processing function."""
    print(f"🚀 Starting efficient batch IPTC description extraction from database")
    print(f"📅 Started at: {datetime.now()}")
    
    try:
        # Get FileMaker token
        token = config.get_token()
        print(f"✅ Got FileMaker token")
        
        # Step 1: Fetch all metadata and store in SQLite
        conn, db_path = fetch_all_metadata(token)
        if not conn:
            return 1
        
        # Step 2: Process metadata to extract descriptions
        extracted_count = process_metadata_batch(conn)
        
        if extracted_count == 0:
            print(f"  No descriptions to update")
            conn.close()
            return 0
        
        # Step 3: Update FileMaker with results
        updated_count = batch_update_filemaker(conn, token)
        
        # Cleanup
        conn.close()
        if db_path.exists():
            db_path.unlink()  # Delete temporary database
            print(f"🗑️ Cleaned up temporary database")
        
        # Final summary
        print(f"\n🎯 Batch processing complete!")
        print(f"📅 Finished at: {datetime.now()}")
        print(f"📈 Final Results:")
        print(f"  Descriptions extracted: {extracted_count}")
        print(f"  Records updated in FileMaker: {updated_count}")
        
        return 0
        
    except Exception as e:
        print(f"💥 Critical error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 