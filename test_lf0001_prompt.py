#!/usr/bin/env python3
import sys
import warnings
import json
import requests
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent))
import config

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "footage_metadata": "INFO_Metadata",
    "footage_source": "INFO_Source", 
    "footage_filename": "INFO_Filename",
    "footage_ai_prompt": "AI_Prompt",
}

def test_lf0001_prompt():
    """Test what AI_Prompt value is being retrieved for LF0001."""
    try:
        print("🔍 Testing AI_Prompt retrieval for LF0001...")
        
        # Get FileMaker token
        token = config.get_token()
        
        # Find LF0001 record using the same method as the caption script
        print(f"\n1. Finding LF0001 record...")
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: "==LF0001"})
        print(f"   Record ID: {record_id}")
        
        # Get record data using the same method as the caption script
        print(f"\n2. Getting record data...")
        record_data = config.get_record(token, "FOOTAGE", record_id)
        
        # Show all the fields that the caption script would use
        print(f"\n3. Field values for caption generation:")
        print(f"   footage_id: {record_data.get(FIELD_MAPPING['footage_id'], 'NOT FOUND')}")
        print(f"   footage_metadata: {len(record_data.get(FIELD_MAPPING['footage_metadata'], ''))} chars")
        print(f"   footage_source: {record_data.get(FIELD_MAPPING['footage_source'], 'NOT FOUND')}")
        print(f"   footage_filename: {record_data.get(FIELD_MAPPING['footage_filename'], 'NOT FOUND')}")
        
        # The critical field - AI_Prompt
        ai_prompt = record_data.get(FIELD_MAPPING["footage_ai_prompt"], "")
        print(f"   footage_ai_prompt: '{ai_prompt}' (length: {len(ai_prompt)})")
        
        # Load prompts from prompts.json (same as caption script)
        print(f"\n4. Loading prompt templates...")
        prompts_path = Path(__file__).resolve().parent / "prompts" / "prompts.json"
        with open(prompts_path, 'r') as f:
            PROMPTS = json.load(f)
        
        # Generate the actual prompt that would be used (LF footage uses caption_LF)
        print(f"\n5. Generating prompt for LF footage...")
        prompt_template = PROMPTS["caption_LF"]
        print(f"   Template: {prompt_template[:200]}...")
        
        # Substitute the values
        prompt_text = prompt_template.format(
            AI_Prompt=ai_prompt,
            INFO_Metadata=record_data.get(FIELD_MAPPING["footage_metadata"], "")
        )
        
        print(f"\n6. ═══ FINAL PROMPT THAT WOULD BE USED ═══")
        print(f"{prompt_text}")
        print(f"═══ END OF PROMPT ═══")
        
        # Show metadata preview
        metadata = record_data.get(FIELD_MAPPING["footage_metadata"], "")
        if metadata:
            print(f"\n7. Metadata preview:")
            print(f"   {metadata[:500]}{'...' if len(metadata) > 500 else ''}")
        else:
            print(f"\n7. No metadata found")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing AI_Prompt: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_lf0001_prompt() 