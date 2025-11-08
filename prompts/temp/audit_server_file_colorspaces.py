#!/usr/bin/env python3
"""
Audit server files in Stills FM DB folder for colorspace consistency
Checks if all JPEGs are RGB and identifies any problematic files
"""

import sys
import os
import warnings
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from PIL import Image
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "server_path": "SPECS_Filepath_Server"
}

# Audit settings
BATCH_SIZE = 100
SAMPLE_SIZE = None  # None = audit all, or set to number for sampling

def analyze_image_file(file_path):
    """Analyze a single image file for colorspace and properties."""
    try:
        with Image.open(file_path) as img:
            info = {
                'mode': img.mode,
                'format': img.format,
                'size': img.size,
                'has_icc': 'icc_profile' in img.info if hasattr(img, 'info') else False,
            }
            
            # Get additional info
            if hasattr(img, 'info'):
                if 'icc_profile' in img.info:
                    info['icc_size'] = len(img.info['icc_profile'])
                
                # Check for color space info in EXIF or metadata
                for key in ['dpi', 'jfif', 'jfif_version', 'exif']:
                    if key in img.info:
                        info[key] = str(img.info[key])[:100]  # Truncate long values
            
            # Quick pixel check to verify it's actually RGB data
            if img.mode == 'RGB':
                # Sample a few pixels
                import numpy as np
                arr = np.array(img)
                info['pixel_sample'] = arr[0, 0].tolist()  # Top-left pixel
                info['array_shape'] = arr.shape
                info['dtype'] = str(arr.dtype)
            
            return info
            
    except Exception as e:
        return {'error': str(e)}

def get_all_records_with_server_paths(token, limit=None):
    """Fetch all records that have server paths."""
    print(f"\n{'='*80}")
    print("FETCHING RECORDS FROM FILEMAKER")
    print(f"{'='*80}")
    
    all_records = []
    offset = 1
    
    while True:
        print(f"\nFetching batch at offset {offset}...")
        
        try:
            response = requests.get(
                config.url(f"layouts/Stills/records"),
                headers=config.api_headers(token),
                params={
                    '_offset': offset,
                    '_limit': BATCH_SIZE
                },
                verify=False,
                timeout=60
            )
            
            if response.status_code != 200:
                print(f"   ⚠️  Error: {response.status_code}")
                break
            
            data = response.json()
            records = data['response']['data']
            
            if not records:
                print(f"   ℹ️  No more records")
                break
            
            for record in records:
                field_data = record['fieldData']
                stills_id = field_data.get(FIELD_MAPPING['stills_id'])
                server_path = field_data.get(FIELD_MAPPING['server_path'])
                
                if stills_id and server_path:
                    all_records.append({
                        'stills_id': stills_id,
                        'server_path': server_path
                    })
            
            print(f"   ✅ Found {len(records)} records ({len(all_records)} with server paths)")
            
            offset += BATCH_SIZE
            
            # Optional limit
            if limit and len(all_records) >= limit:
                all_records = all_records[:limit]
                break
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            break
    
    return all_records

def audit_server_files(records):
    """Audit all server files for colorspace consistency."""
    print(f"\n{'='*80}")
    print(f"AUDITING {len(records)} SERVER FILES")
    print(f"{'='*80}")
    
    stats = {
        'total': len(records),
        'checked': 0,
        'file_not_found': 0,
        'errors': 0,
        'by_mode': defaultdict(int),
        'by_format': defaultdict(int),
        'with_icc': 0,
        'without_icc': 0
    }
    
    problematic_files = []
    sample_files = {}  # Store samples of each mode
    
    for i, record in enumerate(records):
        stills_id = record['stills_id']
        server_path = record['server_path']
        
        # Progress indicator
        if (i + 1) % 100 == 0:
            print(f"Progress: {i+1}/{len(records)} ({(i+1)/len(records)*100:.1f}%)")
        
        # Check if file exists
        if not os.path.exists(server_path):
            stats['file_not_found'] += 1
            problematic_files.append({
                'stills_id': stills_id,
                'issue': 'file_not_found',
                'path': server_path
            })
            continue
        
        # Analyze the file
        info = analyze_image_file(server_path)
        
        if 'error' in info:
            stats['errors'] += 1
            problematic_files.append({
                'stills_id': stills_id,
                'issue': 'analysis_error',
                'error': info['error'],
                'path': server_path
            })
            continue
        
        stats['checked'] += 1
        
        # Track mode
        mode = info['mode']
        stats['by_mode'][mode] += 1
        
        # Track format
        file_format = info.get('format', 'unknown')
        stats['by_format'][file_format] += 1
        
        # Track ICC profiles
        if info.get('has_icc'):
            stats['with_icc'] += 1
        else:
            stats['without_icc'] += 1
        
        # Store sample of each mode
        if mode not in sample_files and len(sample_files) < 10:
            sample_files[mode] = {
                'stills_id': stills_id,
                'path': server_path,
                'info': info
            }
        
        # Flag non-RGB files
        if mode not in ['RGB', 'L']:
            problematic_files.append({
                'stills_id': stills_id,
                'issue': 'non_rgb_mode',
                'mode': mode,
                'path': server_path,
                'info': info
            })
    
    return stats, problematic_files, sample_files

def print_audit_report(stats, problematic_files, sample_files):
    """Print comprehensive audit report."""
    print(f"\n{'='*80}")
    print("AUDIT REPORT")
    print(f"{'='*80}")
    
    print(f"\n📊 Overall Statistics:")
    print(f"   Total records: {stats['total']}")
    print(f"   Successfully checked: {stats['checked']}")
    print(f"   File not found: {stats['file_not_found']}")
    print(f"   Analysis errors: {stats['errors']}")
    
    print(f"\n🎨 Color Mode Distribution:")
    for mode, count in sorted(stats['by_mode'].items(), key=lambda x: -x[1]):
        percentage = count / stats['checked'] * 100 if stats['checked'] > 0 else 0
        status = "✅" if mode in ['RGB', 'L'] else "⚠️"
        print(f"   {status} {mode}: {count} ({percentage:.1f}%)")
    
    print(f"\n📁 File Format Distribution:")
    for fmt, count in sorted(stats['by_format'].items(), key=lambda x: -x[1]):
        percentage = count / stats['checked'] * 100 if stats['checked'] > 0 else 0
        print(f"   {fmt}: {count} ({percentage:.1f}%)")
    
    print(f"\n🌈 ICC Color Profiles:")
    print(f"   With ICC profile: {stats['with_icc']} ({stats['with_icc']/stats['checked']*100 if stats['checked'] > 0 else 0:.1f}%)")
    print(f"   Without ICC profile: {stats['without_icc']} ({stats['without_icc']/stats['checked']*100 if stats['checked'] > 0 else 0:.1f}%)")
    
    # Show samples
    if sample_files:
        print(f"\n🔍 Sample Files by Mode:")
        for mode, sample in sample_files.items():
            print(f"\n   {mode} mode example: {sample['stills_id']}")
            print(f"      Path: {sample['path'][:80]}...")
            print(f"      Size: {sample['info']['size'][0]}x{sample['info']['size'][1]}")
            print(f"      Format: {sample['info'].get('format', 'unknown')}")
            print(f"      Has ICC: {sample['info'].get('has_icc', False)}")
            if 'pixel_sample' in sample['info']:
                print(f"      Sample pixel RGB: {sample['info']['pixel_sample']}")
    
    # Show problematic files
    if problematic_files:
        print(f"\n⚠️  PROBLEMATIC FILES:")
        
        # Group by issue type
        by_issue = defaultdict(list)
        for pf in problematic_files:
            by_issue[pf['issue']].append(pf)
        
        for issue, files in by_issue.items():
            print(f"\n   {issue.replace('_', ' ').title()}: {len(files)} files")
            
            # Show first 10 examples
            for pf in files[:10]:
                print(f"      - {pf['stills_id']}: {pf.get('mode', pf.get('error', 'unknown'))}")
            
            if len(files) > 10:
                print(f"      ... and {len(files) - 10} more")
    
    # Recommendations
    print(f"\n{'='*80}")
    print("RECOMMENDATIONS")
    print(f"{'='*80}")
    
    rgb_percentage = stats['by_mode']['RGB'] / stats['checked'] * 100 if stats['checked'] > 0 else 0
    
    if rgb_percentage > 99:
        print(f"\n✅ EXCELLENT: {rgb_percentage:.1f}% of files are RGB")
        print("   → Server files are already in correct colorspace")
        print("   → Safe to proceed with thumbnail regeneration")
    elif rgb_percentage > 95:
        print(f"\n✅ GOOD: {rgb_percentage:.1f}% of files are RGB")
        print("   → Most files are correct")
        print("   → Consider converting the non-RGB files before thumbnail regeneration")
    else:
        print(f"\n⚠️  WARNING: Only {rgb_percentage:.1f}% of files are RGB")
        print("   → Significant number of files need colorspace conversion")
        print("   → Should convert server files to RGB before thumbnail regeneration")
    
    # Check ICC profiles
    if stats['with_icc'] > 0:
        icc_percentage = stats['with_icc'] / stats['checked'] * 100
        print(f"\n🌈 ICC Profile Notes:")
        print(f"   {icc_percentage:.1f}% of files have ICC color profiles")
        if icc_percentage > 50:
            print("   → Consider stripping ICC profiles during thumbnail generation")
            print("   → Or ensure consistent ICC handling in CLIP processing")
        else:
            print("   → Most files don't have ICC profiles (simpler processing)")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Audit server files for colorspace consistency')
    parser.add_argument('--limit', type=int, help='Limit number of records to check (for testing)')
    
    args = parser.parse_args()
    
    print("="*80)
    print("SERVER FILE COLORSPACE AUDIT")
    print("="*80)
    print("\nThis will check all server files in the Stills FM DB folder")
    print("to ensure RGB colorspace consistency for reliable CLIP embeddings.")
    
    if args.limit:
        print(f"\n⚠️  Testing mode: Will check only {args.limit} records")
    
    # Get FileMaker token
    token = config.get_token()
    
    # Fetch records
    records = get_all_records_with_server_paths(token, limit=args.limit)
    
    print(f"\n✅ Found {len(records)} records with server paths")
    
    if len(records) == 0:
        print("\n❌ No records to audit")
        sys.exit(0)
    
    # Run audit
    start_time = datetime.now()
    stats, problematic_files, sample_files = audit_server_files(records)
    duration = (datetime.now() - start_time).total_seconds()
    
    # Print report
    print_audit_report(stats, problematic_files, sample_files)
    
    print(f"\n⏱️  Audit completed in {duration:.1f} seconds ({stats['checked']/duration:.1f} files/second)")

