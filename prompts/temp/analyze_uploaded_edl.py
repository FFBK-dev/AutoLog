#!/usr/bin/env python3
"""
Analyze uploaded EDL files to understand their format and content
"""

import sys
import re
from pathlib import Path

def analyze_edl_file(file_path):
    """Analyze an EDL file and provide detailed information."""
    print(f"🎬 Analyzing: {file_path}")
    print("-" * 60)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return
    
    lines = content.split('\n')
    print(f"📄 Total lines: {len(lines)}")
    print(f"📊 File size: {len(content)} bytes")
    print()
    
    # Analyze each line
    edl_entries = []
    still_entries = []
    other_entries = []
    
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
            
        print(f"Line {i:2d}: {line}")
        
        # Check if it's a title or header
        if line.startswith('TITLE:') or line.startswith('FCM:'):
            print(f"         → Header line")
            continue
        
        # Check if it's a comment
        if line.startswith('*'):
            print(f"         → Comment line")
            continue
        
        # Try to parse as EDL entry
        parts = line.split()
        if len(parts) >= 8:
            try:
                edit_num = parts[0]
                source = parts[1]
                track = parts[2]
                edit_type = parts[3]
                src_in = parts[4]
                src_out = parts[5]
                dst_in = parts[6]
                dst_out = parts[7]
                
                entry = {
                    'line_num': i,
                    'edit_num': edit_num,
                    'source': source,
                    'track': track,
                    'edit_type': edit_type,
                    'src_in': src_in,
                    'src_out': src_out,
                    'dst_in': dst_in,
                    'dst_out': dst_out
                }
                edl_entries.append(entry)
                
                # Check if it's a still image
                if re.search(r'S\d+', source, re.IGNORECASE):
                    still_entries.append(entry)
                    print(f"         → STILL IMAGE: {source}")
                else:
                    other_entries.append(entry)
                    print(f"         → Video/Audio: {source}")
                    
            except Exception as e:
                print(f"         → Parse error: {e}")
        else:
            print(f"         → Invalid EDL format (need 8+ parts)")
    
    print()
    print("📊 Summary:")
    print(f"  • Total EDL entries: {len(edl_entries)}")
    print(f"  • Still images: {len(still_entries)}")
    print(f"  • Other entries: {len(other_entries)}")
    
    if still_entries:
        print()
        print("🖼️  Still Images Found:")
        for entry in still_entries:
            print(f"  • {entry['source']} | {entry['dst_in']} → {entry['dst_out']}")
    else:
        print()
        print("ℹ️  No still images found in this EDL")
        if other_entries:
            print("📹 Other entries:")
            for entry in other_entries:
                print(f"  • {entry['source']} ({entry['track']}) | {entry['dst_in']} → {entry['dst_out']}")
    
    print()

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_uploaded_edl.py <edl_file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    analyze_edl_file(file_path)

if __name__ == "__main__":
    main()
