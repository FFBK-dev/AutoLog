#!/usr/bin/env python3
"""
Bin Scanner Utility

Scans Avid project directories for .avb bin files and generates 
dynamic bin lists for use in tagging workflows.
"""

import os
import warnings
from pathlib import Path
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Bin directory configuration
BIN_DIRECTORIES = {
    "stills": [
        "/Volumes/PROJECT_E2E/E2E/5. STILLS/5b. BY CATEGORY"
    ],
    "archival": [
        "/Volumes/PROJECT_E2E/E2E/6. ARC FOOTAGE/6b. BY CATEGORY"
    ],
    "live": [
        "/Volumes/PROJECT_E2E/E2E/7. LIVE FOOTAGE/7b. BY CATEGORY",
        "/Volumes/PROJECT_E2E/E2E/7. LIVE FOOTAGE/7c. BY LOCATION"
    ]
}

# Output file configuration
OUTPUT_FILES = {
    "stills": "stills-bins.txt",
    "archival": "archival-footage-bins.txt",
    "live": "live-footage-bins.txt"
}


def scan_for_bins(directory_path):
    """
    Recursively scan a directory for .avb files and extract bin names.
    
    Args:
        directory_path: Path to directory to scan
        
    Returns:
        List of bin names (without .avb extension)
    """
    bins = []
    
    if not os.path.exists(directory_path):
        print(f"  ⚠️  Directory not found: {directory_path}")
        return bins
    
    try:
        # Walk through directory recursively
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                if file.endswith('.avb'):
                    # Extract bin name (remove .avb extension)
                    bin_name = file[:-4]
                    bins.append(bin_name)
        
        print(f"  ✅ Found {len(bins)} bins in {directory_path}")
        
    except Exception as e:
        print(f"  ❌ Error scanning {directory_path}: {e}")
    
    return bins


def scan_media_type(media_type):
    """
    Scan all directories for a specific media type.
    
    Args:
        media_type: One of "stills", "archival", "live"
        
    Returns:
        Sorted list of unique bin names
    """
    print(f"\n📁 Scanning {media_type} bins...")
    
    directories = BIN_DIRECTORIES.get(media_type, [])
    all_bins = []
    
    for directory in directories:
        bins = scan_for_bins(directory)
        all_bins.extend(bins)
    
    # Remove duplicates and sort
    unique_bins = sorted(set(all_bins))
    
    print(f"  📊 Total unique bins: {len(unique_bins)}")
    
    return unique_bins


def write_bins_file(bins, media_type):
    """
    Write bins to output file in tags directory.
    
    Args:
        bins: List of bin names
        media_type: One of "stills", "archival", "live"
        
    Returns:
        Path to output file
    """
    # Get output filename
    output_filename = OUTPUT_FILES.get(media_type)
    if not output_filename:
        raise ValueError(f"Unknown media type: {media_type}")
    
    # Construct full path to tags directory
    script_dir = Path(__file__).resolve().parent.parent
    tags_dir = script_dir / "tags"
    output_path = tags_dir / output_filename
    
    # Create tags directory if it doesn't exist
    tags_dir.mkdir(parents=True, exist_ok=True)
    
    # Write bins to file
    try:
        with open(output_path, 'w') as f:
            # Write header comment
            f.write(f"# {media_type.upper()} BINS\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total bins: {len(bins)}\n")
            f.write("#\n")
            
            # Write each bin name
            for bin_name in bins:
                f.write(f"{bin_name}\n")
        
        print(f"  ✅ Written to: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"  ❌ Error writing file {output_path}: {e}")
        raise


def scan_all_bins():
    """
    Scan all media types and generate bin files.
    
    Returns:
        Dictionary with results for each media type
    """
    print("🔍 Starting bin scan...")
    print("=" * 60)
    
    results = {}
    
    for media_type in ["stills", "archival", "live"]:
        try:
            # Scan for bins
            bins = scan_media_type(media_type)
            
            # Write to file
            output_path = write_bins_file(bins, media_type)
            
            results[media_type] = {
                "success": True,
                "bin_count": len(bins),
                "output_file": str(output_path),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"  ❌ Failed to scan {media_type}: {e}")
            results[media_type] = {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    print("\n" + "=" * 60)
    print("✅ Bin scan complete!")
    print(f"  Stills: {results.get('stills', {}).get('bin_count', 0)} bins")
    print(f"  Archival: {results.get('archival', {}).get('bin_count', 0)} bins")
    print(f"  Live: {results.get('live', {}).get('bin_count', 0)} bins")
    
    return results


def get_scan_status():
    """
    Get status of existing bin files.
    
    Returns:
        Dictionary with status information
    """
    script_dir = Path(__file__).resolve().parent.parent
    tags_dir = script_dir / "tags"
    
    status = {}
    
    for media_type, filename in OUTPUT_FILES.items():
        file_path = tags_dir / filename
        
        if file_path.exists():
            # Read file to count bins
            try:
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                    # Count non-comment, non-empty lines
                    bin_count = sum(1 for line in lines if line.strip() and not line.startswith('#'))
                
                # Get file modification time
                mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                
                status[media_type] = {
                    "exists": True,
                    "bin_count": bin_count,
                    "last_updated": mod_time.isoformat(),
                    "file_path": str(file_path)
                }
            except Exception as e:
                status[media_type] = {
                    "exists": True,
                    "error": f"Failed to read file: {e}",
                    "file_path": str(file_path)
                }
        else:
            status[media_type] = {
                "exists": False,
                "message": "Bin file not found - run scan to generate"
            }
    
    return status


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        # Show status
        print("📊 Bin File Status")
        print("=" * 60)
        status = get_scan_status()
        
        for media_type, info in status.items():
            print(f"\n{media_type.upper()}:")
            if info.get("exists"):
                if "error" in info:
                    print(f"  ❌ {info['error']}")
                else:
                    print(f"  ✅ {info['bin_count']} bins")
                    print(f"  📅 Last updated: {info['last_updated']}")
                    print(f"  📁 File: {info['file_path']}")
            else:
                print(f"  ⚠️  {info['message']}")
    else:
        # Run full scan
        results = scan_all_bins()
        
        # Exit with error if any scan failed
        if any(not r.get("success", False) for r in results.values()):
            sys.exit(1)
        else:
            sys.exit(0)

