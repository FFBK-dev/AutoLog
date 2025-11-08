#!/usr/bin/env python3
"""
Audit ALL thumbnails in the database to find inconsistencies
This will identify which records have non-standard thumbnails
"""

import sys
import os
import warnings
from pathlib import Path
import requests
import time
from collections import defaultdict
import json

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "thumbnail": "SPECS_Thumbnail",
    "server_path": "SPECS_Filepath_Server"
}

# Standard thumbnail dimensions (allowing for aspect ratio variation)
STANDARD_MAX_DIM = 588
TOLERANCE = 10  # Allow up to 598px (588 + 10) to account for aspect ratio

def get_thumbnail_info_from_url(thumbnail_url, token):
    """Get thumbnail dimensions and size from URL without downloading full file."""
    try:
        # Download just the header to get file size
        resp = requests.head(thumbnail_url, headers=config.api_headers(token), verify=False, timeout=10)
        file_size = int(resp.headers.get('Content-Length', 0))
        
        # Download the file to check dimensions
        # For efficiency, we need to download it
        resp = requests.get(thumbnail_url, headers=config.api_headers(token), verify=False, timeout=30)
        
        if resp.status_code != 200:
            return None
        
        # Save temporarily
        temp_file = f"/tmp/thumb_check_{os.getpid()}.jpg"
        with open(temp_file, 'wb') as f:
            f.write(resp.content)
        
        # Get dimensions
        from PIL import Image
        with Image.open(temp_file) as img:
            dimensions = img.size
        
        # Clean up
        os.remove(temp_file)
        
        return {
            'width': dimensions[0],
            'height': dimensions[1],
            'max_dim': max(dimensions),
            'file_size': len(resp.content)
        }
        
    except Exception as e:
        return None

def check_record_batch(offset, limit, token):
    """Check a batch of records."""
    try:
        # Get records with thumbnail field
        response = requests.get(
            config.url(f"layouts/Stills/records"),
            headers=config.api_headers(token),
            params={
                '_offset': offset,
                '_limit': limit
            },
            verify=False,
            timeout=60
        )
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        records = data['response']['data']
        
        results = []
        
        for record in records:
            field_data = record['fieldData']
            stills_id = field_data.get(FIELD_MAPPING['stills_id'])
            thumbnail_url = field_data.get(FIELD_MAPPING['thumbnail'])
            
            if not stills_id:
                continue
            
            result = {
                'stills_id': stills_id,
                'has_thumbnail': bool(thumbnail_url),
                'thumbnail_url': thumbnail_url[:100] if thumbnail_url else None
            }
            
            # Check if thumbnail exists and get info
            if thumbnail_url:
                # Quick check: is it a streaming URL (embedded) or external reference?
                if 'Streaming' in thumbnail_url:
                    result['type'] = 'embedded'
                    
                    # For sampling, only check dimensions for some records
                    # to avoid overwhelming the system
                    # We'll do a full check later if needed
                    result['checked_dimensions'] = False
                else:
                    result['type'] = 'reference'
                    result['checked_dimensions'] = False
            
            results.append(result)
        
        return results
        
    except Exception as e:
        print(f"Error in batch {offset}-{offset+limit}: {e}")
        return None

def audit_phase_1_quick_scan(token, total_records=8000, batch_size=100):
    """Phase 1: Quick scan to count records and identify obvious issues."""
    print(f"\n{'='*80}")
    print("PHASE 1: QUICK SCAN")
    print(f"{'='*80}")
    print(f"Scanning up to {total_records} records in batches of {batch_size}...")
    print("(This will NOT download thumbnails - just checking metadata)")
    
    stats = {
        'total_checked': 0,
        'has_thumbnail': 0,
        'no_thumbnail': 0,
        'embedded': 0,
        'reference': 0
    }
    
    records_with_thumbnails = []
    
    offset = 1  # FileMaker uses 1-based indexing
    batch_num = 0
    
    while offset <= total_records:
        batch_num += 1
        print(f"\n📦 Processing batch {batch_num} (records {offset}-{offset+batch_size-1})...")
        
        results = check_record_batch(offset, batch_size, token)
        
        if results is None:
            print(f"   ⚠️  Failed to fetch batch")
            break
        
        if not results:
            print(f"   ℹ️  No more records")
            break
        
        # Update stats
        for result in results:
            stats['total_checked'] += 1
            
            if result['has_thumbnail']:
                stats['has_thumbnail'] += 1
                records_with_thumbnails.append(result)
                
                if result.get('type') == 'embedded':
                    stats['embedded'] += 1
                elif result.get('type') == 'reference':
                    stats['reference'] += 1
            else:
                stats['no_thumbnail'] += 1
        
        print(f"   ✅ Processed {len(results)} records")
        print(f"   📊 Running totals: {stats['has_thumbnail']} with thumbnails, {stats['no_thumbnail']} without")
        
        offset += batch_size
        
        # Small delay to not overwhelm the API
        time.sleep(0.1)
    
    return stats, records_with_thumbnails

def audit_phase_2_sample_check(records_with_thumbnails, token, sample_size=50):
    """Phase 2: Sample check dimensions of embedded thumbnails."""
    print(f"\n{'='*80}")
    print("PHASE 2: SAMPLE DIMENSION CHECK")
    print(f"{'='*80}")
    print(f"Checking dimensions of {sample_size} sample thumbnails...")
    print("(This will download sample thumbnails to check actual dimensions)")
    
    # Sample records
    import random
    embedded_records = [r for r in records_with_thumbnails if r.get('type') == 'embedded']
    
    if len(embedded_records) == 0:
        print("No embedded thumbnails found!")
        return {}
    
    sample = random.sample(embedded_records, min(sample_size, len(embedded_records)))
    
    dimension_groups = defaultdict(list)
    size_stats = []
    
    for i, record in enumerate(sample):
        print(f"\n📸 Checking {record['stills_id']} ({i+1}/{len(sample)})...")
        
        info = get_thumbnail_info_from_url(record['thumbnail_url'], token)
        
        if info:
            dim_key = f"{info['width']}x{info['height']}"
            dimension_groups[dim_key].append(record['stills_id'])
            size_stats.append(info)
            
            # Check if it's standard
            is_standard = info['max_dim'] <= (STANDARD_MAX_DIM + TOLERANCE)
            status = "✅ STANDARD" if is_standard else "⚠️  NON-STANDARD"
            
            print(f"   Dimensions: {info['width']}x{info['height']} ({info['file_size']:,} bytes)")
            print(f"   Status: {status}")
        else:
            print(f"   ❌ Failed to check")
        
        # Delay between downloads
        time.sleep(0.2)
    
    return {
        'dimension_groups': dimension_groups,
        'size_stats': size_stats,
        'sample_size': len(sample)
    }

if __name__ == "__main__":
    print("="*80)
    print("THUMBNAIL CONSISTENCY AUDIT")
    print("="*80)
    print("\nThis will scan the database to identify thumbnail inconsistencies")
    print("for semantic search and duplicate detection.")
    
    # Get FileMaker token
    token = config.get_token()
    
    # Phase 1: Quick scan
    stats, records_with_thumbnails = audit_phase_1_quick_scan(token)
    
    # Print Phase 1 results
    print(f"\n{'='*80}")
    print("PHASE 1 RESULTS")
    print(f"{'='*80}")
    print(f"Total records checked: {stats['total_checked']}")
    print(f"Has thumbnail: {stats['has_thumbnail']} ({stats['has_thumbnail']/stats['total_checked']*100:.1f}%)")
    print(f"No thumbnail: {stats['no_thumbnail']} ({stats['no_thumbnail']/stats['total_checked']*100:.1f}%)")
    print(f"Embedded thumbnails: {stats['embedded']}")
    print(f"Reference thumbnails: {stats['reference']}")
    
    # Phase 2: Sample check
    if stats['has_thumbnail'] > 0:
        sample_results = audit_phase_2_sample_check(records_with_thumbnails, token, sample_size=50)
        
        print(f"\n{'='*80}")
        print("PHASE 2 RESULTS")
        print(f"{'='*80}")
        
        if sample_results.get('dimension_groups'):
            print(f"\nDimension Distribution (from {sample_results['sample_size']} samples):")
            for dim, ids in sorted(sample_results['dimension_groups'].items()):
                print(f"  {dim}: {len(ids)} thumbnails")
                print(f"    Examples: {', '.join(ids[:3])}")
            
            # Analyze sizes
            if sample_results.get('size_stats'):
                sizes = sample_results['size_stats']
                max_dims = [s['max_dim'] for s in sizes]
                file_sizes = [s['file_size'] for s in sizes]
                
                import numpy as np
                print(f"\nSize Statistics:")
                print(f"  Max dimension range: {min(max_dims)}-{max(max_dims)} pixels")
                print(f"  File size range: {min(file_sizes):,}-{max(file_sizes):,} bytes")
                print(f"  Average file size: {int(np.mean(file_sizes)):,} bytes")
                
                # Check for non-standard
                non_standard = [s for s in sizes if s['max_dim'] > (STANDARD_MAX_DIM + TOLERANCE)]
                if non_standard:
                    print(f"\n⚠️  NON-STANDARD THUMBNAILS DETECTED:")
                    print(f"  {len(non_standard)}/{len(sizes)} samples are larger than {STANDARD_MAX_DIM}px")
                    print(f"  Estimated total non-standard: {int(len(non_standard)/len(sizes) * stats['has_thumbnail'])}")
                else:
                    print(f"\n✅ All sampled thumbnails appear to be standard size")
    
    # Recommendations
    print(f"\n{'='*80}")
    print("RECOMMENDATIONS")
    print(f"{'='*80}")
    
    if stats.get('reference', 0) > 0:
        print(f"\n⚠️  {stats['reference']} records use reference thumbnails")
        print("   These may cause issues if paths change")
    
    print(f"\n📋 For consistent embeddings, ALL thumbnails should be:")
    print(f"   - Maximum dimension: {STANDARD_MAX_DIM} pixels")
    print(f"   - JPEG quality: 85%")
    print(f"   - Embedded (not references)")
    
    print(f"\n💡 Next Steps:")
    print(f"   1. Review the dimension distribution above")
    print(f"   2. Decide if full audit (all {stats['has_thumbnail']} thumbnails) is needed")
    print(f"   3. Plan systematic thumbnail regeneration")
    print(f"   4. Regenerate embeddings after thumbnail standardization")

