#!/usr/bin/env python3
"""
Direct filesystem audit of server files for colorspace consistency
Scans the Stills FM DB folder directly without querying FileMaker
"""

import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from PIL import Image

# Target directory
STILLS_DIR = Path("/Volumes/6 E2E/7A Stills_FM DB")

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
            
            if info.get('has_icc'):
                info['icc_size'] = len(img.info['icc_profile'])
            
            return info
            
    except Exception as e:
        return {'error': str(e)}

def scan_directory(directory):
    """Scan directory for all image files."""
    print(f"\n{'='*80}")
    print(f"SCANNING: {directory}")
    print(f"{'='*80}")
    
    if not directory.exists():
        print(f"❌ Directory not found: {directory}")
        return None
    
    print(f"Looking for .jpg and .jpeg files...")
    
    # Find all JPEG files
    jpg_files = []
    for pattern in ['**/*.jpg', '**/*.jpeg', '**/*.JPG', '**/*.JPEG']:
        jpg_files.extend(directory.glob(pattern))
    
    print(f"✅ Found {len(jpg_files)} JPEG files")
    
    return jpg_files

def audit_files(files):
    """Audit all image files."""
    print(f"\n{'='*80}")
    print(f"AUDITING {len(files)} FILES")
    print(f"{'='*80}")
    
    stats = {
        'total': len(files),
        'checked': 0,
        'errors': 0,
        'by_mode': defaultdict(int),
        'by_format': defaultdict(int),
        'with_icc': 0,
        'without_icc': 0,
        'by_size_range': defaultdict(int)
    }
    
    problematic_files = []
    sample_files = {}
    
    start_time = datetime.now()
    
    for i, file_path in enumerate(files):
        # Progress
        if (i + 1) % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(files) - (i + 1)) / rate if rate > 0 else 0
            print(f"Progress: {i+1}/{len(files)} ({(i+1)/len(files)*100:.1f}%) - {rate:.1f} files/sec - ETA: {eta:.0f}s")
        
        # Analyze
        info = analyze_image_file(file_path)
        
        if 'error' in info:
            stats['errors'] += 1
            problematic_files.append({
                'file': str(file_path),
                'issue': 'analysis_error',
                'error': info['error']
            })
            continue
        
        stats['checked'] += 1
        
        # Track mode
        mode = info['mode']
        stats['by_mode'][mode] += 1
        
        # Track format
        file_format = info.get('format', 'unknown')
        stats['by_format'][file_format] += 1
        
        # Track ICC
        if info.get('has_icc'):
            stats['with_icc'] += 1
        else:
            stats['without_icc'] += 1
        
        # Track size ranges
        width, height = info['size']
        max_dim = max(width, height)
        if max_dim < 1000:
            size_range = '<1000px'
        elif max_dim < 2000:
            size_range = '1000-2000px'
        elif max_dim < 5000:
            size_range = '2000-5000px'
        else:
            size_range = '>5000px'
        stats['by_size_range'][size_range] += 1
        
        # Store samples
        if mode not in sample_files:
            sample_files[mode] = {
                'file': str(file_path),
                'info': info
            }
        
        # Flag non-RGB
        if mode not in ['RGB', 'L']:
            problematic_files.append({
                'file': str(file_path),
                'issue': 'non_rgb_mode',
                'mode': mode,
                'info': info
            })
    
    return stats, problematic_files, sample_files

def print_report(stats, problematic_files, sample_files):
    """Print audit report."""
    print(f"\n{'='*80}")
    print("COLORSPACE AUDIT REPORT")
    print(f"{'='*80}")
    
    print(f"\n📊 Overall:")
    print(f"   Total files: {stats['total']}")
    print(f"   Successfully checked: {stats['checked']}")
    print(f"   Errors: {stats['errors']}")
    
    print(f"\n🎨 Color Mode Distribution:")
    for mode, count in sorted(stats['by_mode'].items(), key=lambda x: -x[1]):
        percentage = count / stats['checked'] * 100 if stats['checked'] > 0 else 0
        status = "✅" if mode in ['RGB', 'L'] else "⚠️"
        print(f"   {status} {mode}: {count:,} files ({percentage:.2f}%)")
    
    print(f"\n📁 File Format:")
    for fmt, count in sorted(stats['by_format'].items(), key=lambda x: -x[1]):
        percentage = count / stats['checked'] * 100 if stats['checked'] > 0 else 0
        print(f"   {fmt}: {count:,} ({percentage:.1f}%)")
    
    print(f"\n🌈 ICC Profiles:")
    if stats['checked'] > 0:
        print(f"   With ICC: {stats['with_icc']:,} ({stats['with_icc']/stats['checked']*100:.1f}%)")
        print(f"   Without ICC: {stats['without_icc']:,} ({stats['without_icc']/stats['checked']*100:.1f}%)")
    
    print(f"\n📏 Size Distribution:")
    for size_range, count in sorted(stats['by_size_range'].items()):
        percentage = count / stats['checked'] * 100 if stats['checked'] > 0 else 0
        print(f"   {size_range}: {count:,} ({percentage:.1f}%)")
    
    # Samples
    if sample_files:
        print(f"\n🔍 Mode Samples:")
        for mode, sample in sample_files.items():
            print(f"\n   {mode}:")
            print(f"      File: {Path(sample['file']).name}")
            print(f"      Size: {sample['info']['size'][0]}x{sample['info']['size'][1]}")
            print(f"      Has ICC: {sample['info'].get('has_icc', False)}")
    
    # Problems
    if problematic_files:
        print(f"\n⚠️  ISSUES FOUND: {len(problematic_files)}")
        
        by_issue = defaultdict(list)
        for pf in problematic_files:
            by_issue[pf['issue']].append(pf)
        
        for issue, files in by_issue.items():
            print(f"\n   {issue.replace('_', ' ').title()}: {len(files)}")
            for pf in files[:5]:
                if 'mode' in pf:
                    print(f"      - {Path(pf['file']).name} (mode: {pf['mode']})")
                else:
                    print(f"      - {Path(pf['file']).name} (error: {pf.get('error', 'unknown')})")
            if len(files) > 5:
                print(f"      ... and {len(files) - 5} more")
    
    # Recommendations
    print(f"\n{'='*80}")
    print("RECOMMENDATIONS")
    print(f"{'='*80}")
    
    rgb_count = stats['by_mode'].get('RGB', 0)
    rgb_percentage = rgb_count / stats['checked'] * 100 if stats['checked'] > 0 else 0
    
    if rgb_percentage > 99.5:
        print(f"\n✅ EXCELLENT: {rgb_percentage:.2f}% of files are RGB")
        print("   → Server files are in correct colorspace")
        print("   → Safe to proceed with thumbnail regeneration")
    elif rgb_percentage > 95:
        print(f"\n✅ GOOD: {rgb_percentage:.2f}% are RGB")
        print("   → Vast majority are correct")
        non_rgb = stats['checked'] - rgb_count
        print(f"   → {non_rgb} files need attention")
    else:
        print(f"\n⚠️  CONCERN: Only {rgb_percentage:.2f}% are RGB")
        non_rgb = stats['checked'] - rgb_count
        print(f"   → {non_rgb:,} files are not RGB")
        print("   → Should investigate before thumbnail regeneration")
    
    # ICC recommendations
    if stats['with_icc'] > 0:
        icc_pct = stats['with_icc'] / stats['checked'] * 100
        print(f"\n🌈 ICC Profiles: {icc_pct:.1f}% have embedded profiles")
        if icc_pct > 10:
            print("   → ICC profiles may affect colorspace interpretation")
            print("   → Consider stripping during thumbnail generation for consistency")

if __name__ == "__main__":
    print("="*80)
    print("DIRECT FILESYSTEM COLORSPACE AUDIT")
    print("="*80)
    
    # Check if directory is mounted
    if not STILLS_DIR.exists():
        print(f"\n❌ ERROR: Directory not found")
        print(f"   {STILLS_DIR}")
        print("\nIs the volume mounted? Check:")
        print("   /Volumes/6 E2E/")
        exit(1)
    
    print(f"\nScanning: {STILLS_DIR}")
    
    start_time = datetime.now()
    
    # Scan
    files = scan_directory(STILLS_DIR)
    if not files:
        exit(1)
    
    # Audit
    stats, problematic_files, sample_files = audit_files(files)
    
    # Report
    print_report(stats, problematic_files, sample_files)
    
    duration = (datetime.now() - start_time).total_seconds()
    print(f"\n⏱️  Completed in {duration:.1f} seconds ({stats['checked']/duration:.1f} files/second)")

