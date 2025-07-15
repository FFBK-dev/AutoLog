#!/usr/bin/env python3
"""
Update Prompts - Simple script to rebuild prompts.json from text files

Just run this script whenever you've finished editing the .txt files
and want to update the prompts.json file.

Usage:
    python update_prompts.py
"""

import json
import os
from pathlib import Path

def main():
    print("🔄 Updating prompts.json from text files...")
    
    # Get the current directory (should be the prompts directory)
    current_dir = Path(__file__).parent
    
    # prompts.json should be in the same directory
    prompts_json = current_dir / "prompts.json"
    
    prompts = {}
    
    # Read all .txt files in the current directory
    txt_files = list(current_dir.glob("*.txt"))
    
    if not txt_files:
        print("❌ No .txt files found in this directory!")
        return
    
    for txt_file in sorted(txt_files):
        prompt_name = txt_file.stem
        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            prompts[prompt_name] = content
            print(f"📖 Read: {txt_file.name}")
        except Exception as e:
            print(f"❌ Error reading {txt_file.name}: {e}")
    
    # Write to prompts.json
    try:
        with open(prompts_json, 'w', encoding='utf-8') as f:
            json.dump(prompts, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Successfully updated {prompts_json}")
        print(f"📊 Updated {len(prompts)} prompts:")
        for name in sorted(prompts.keys()):
            print(f"   - {name}")
        
    except Exception as e:
        print(f"❌ Error writing to prompts.json: {e}")

if __name__ == "__main__":
    main() 