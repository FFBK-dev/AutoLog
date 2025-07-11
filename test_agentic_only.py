#!/usr/bin/env python3
import sys
import json
import warnings
import os
import base64
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent))
import config

def load_prompts():
    """Load prompts from prompts.json file."""
    prompts_path = Path(__file__).resolve().parent / "prompts.json"
    with open(prompts_path, 'r') as f:
        return json.load(f)

def test_openai_import():
    """Test OpenAI import explicitly"""
    print(f"\n🔧 TESTING OPENAI IMPORT...")
    try:
        import openai
        print(f"✅ OpenAI imported successfully")
        print(f"  Version: {openai.__version__}")
        print(f"  Location: {openai.__file__}")
        print(f"  Module loaded successfully")
        return openai
    except Exception as e:
        print(f"❌ OpenAI import failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_agentic_lookup_standalone(stills_id):
    """Test the agentic lookup function directly without selenium dependencies."""
    print(f"\n🔍 TESTING AGENTIC LOOKUP FOR {stills_id}...")
    
    token = config.get_token()
    
    # Get record data
    try:
        record_id = config.find_record_id(token, "Stills", {"INFO_STILLS_ID": f"=={stills_id}"})
        record_data = config.get_record(token, "Stills", record_id)
        print(f"✅ Found record")
    except Exception as e:
        print(f"❌ Error fetching record: {e}")
        return
    
    # Check server path
    server_path = record_data.get('SPECS_Filepath_Server', '')
    if not server_path:
        print("❌ No server path found!")
        return
    
    print(f"📁 Server path: {server_path}")
    
    # Check if file exists
    if not os.path.exists(server_path):
        print(f"❌ Image file not found at: {server_path}")
        return
    else:
        print(f"✅ Image file exists")
    
    # Test prompts loading
    try:
        prompts = load_prompts()
        print(f"✅ Prompts loaded successfully")
        if "stills_agentic_lookup" in prompts:
            print(f"✅ Agentic lookup prompt found")
            prompt_template = prompts["stills_agentic_lookup"]
        else:
            print(f"❌ Agentic lookup prompt missing from prompts.json")
            return
    except Exception as e:
        print(f"❌ Error loading prompts: {e}")
        return
    
    # Test OpenAI import
    openai = test_openai_import()
    if not openai:
        return
    
    # Get OpenAI API key
    try:
        system_globals = config.get_system_globals(token)
        api_key = system_globals.get("SystemGlobals_AutoLog_OpenAI_API_Key")
        if not api_key:
            print("❌ OpenAI API Key not found in SystemGlobals")
            return
        # For OpenAI v1.x, create a client with the API key
        client = openai.OpenAI(api_key=api_key)
        print(f"✅ OpenAI client created with API key")
    except Exception as e:
        print(f"❌ Error creating OpenAI client: {e}")
        return
    
    # Run the agentic lookup
    try:
        print(f"\n🤖 Running agentic analysis...")
        
        # Get context data
        filename = record_data.get("INFO_Filename", "")
        source = record_data.get("INFO_Source", "")
        archival_id = record_data.get("INFO_Archival_ID", "")
        existing_metadata = record_data.get("INFO_Metadata", "")
        
        print(f"  Filename: {filename}")
        print(f"  Source: {source}")
        print(f"  Archival ID: {archival_id}")
        print(f"  Existing metadata: {existing_metadata[:100] if existing_metadata else '(empty)'}")
        
        # Format the prompt with context
        prompt_text = prompt_template.format(
            INFO_Filename=filename,
            INFO_Source=source,
            INFO_Archival_ID=archival_id,
            INFO_Metadata=existing_metadata
        )
        
        print(f"\n📝 Prompt preview (first 200 chars):")
        print(f"  {prompt_text[:200]}...")

        # Read and encode the image
        with open(server_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        print(f"✅ Image encoded successfully")

        # Create the message with image
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ]
        
        print(f"🚀 Sending request to OpenAI...")
        
        # Debug the exact call
        print(f"  Using model: gpt-4o")
        print(f"  Message count: {len(messages)}")
        print(f"  Content types: {[type(c) for c in messages[0]['content']]}")
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=500
        )
        
        print(f"✅ Received response from OpenAI")
        
        analysis = json.loads(response.choices[0].message.content)
        
        print(f"\n📊 ANALYSIS RESULTS:")
        print(f"  Historical Context: {analysis.get('historical_context', 'N/A')}")
        print(f"  Date Range: {analysis.get('potential_date_range', 'N/A')}")
        print(f"  Location: {analysis.get('geographic_location', 'N/A')}")
        print(f"  Key Details: {analysis.get('key_details', 'N/A')}")
        print(f"  Confidence: {analysis.get('confidence_level', 'N/A')}")
        
        # Check confidence level
        confidence = analysis.get("confidence_level", "low")
        if confidence == "low":
            print(f"\n⚠️ Low confidence results - would not be used")
            return None
        
        # Format the analysis into a useful description
        parts = []
        if analysis.get("historical_context"):
            parts.append(f"Historical Context: {analysis['historical_context']}")
        if analysis.get("potential_date_range"):
            parts.append(f"Date: {analysis['potential_date_range']}")
        if analysis.get("geographic_location"):
            parts.append(f"Location: {analysis['geographic_location']}")
        if analysis.get("key_details"):
            parts.append(f"Details: {analysis['key_details']}")
            
        if parts:
            combined_analysis = " | ".join(parts)
            print(f"\n✅ SUCCESS! Combined analysis:")
            print(f"  {combined_analysis}")
            return combined_analysis
        else:
            print(f"\n❌ No useful information extracted")
            return None
            
    except Exception as e:
        print(f"❌ Agentic analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_metadata_check(stills_id):
    """Test what happens with current metadata."""
    print(f"\n📏 TESTING METADATA SUFFICIENCY...")
    
    token = config.get_token()
    record_id = config.find_record_id(token, "Stills", {"INFO_STILLS_ID": f"=={stills_id}"})
    record_data = config.get_record(token, "Stills", record_id)
    
    metadata = record_data.get('INFO_Metadata', '')
    metadata_length = len(metadata.strip())
    
    print(f"  Current metadata length: {metadata_length}")
    print(f"  Threshold: 50 characters")
    print(f"  Sufficient: {'✅ YES' if metadata_length > 50 else '❌ NO'}")
    
    if metadata_length <= 50:
        print(f"  → Would proceed to scraping/agentic lookup")
    else:
        print(f"  → Would skip to AI description generation")

if __name__ == "__main__":
    stills_id = "S04619"
    
    print(f"🧪 AGENTIC LOOKUP TEST FOR {stills_id}")
    print("=" * 50)
    
    # Test metadata sufficiency first
    test_metadata_check(stills_id)
    
    # Test agentic lookup
    result = test_agentic_lookup_standalone(stills_id)
    
    print(f"\n📋 SUMMARY:")
    print(f"  Agentic lookup result: {'✅ SUCCESS' if result else '❌ FAILED'}")
    if result:
        print(f"  This would be added to metadata and record would go back to '4 - Metadata Parsed'")
        print(f"  Then it would likely proceed to '6 - Ready for AI Description'")
    else:
        print(f"  This would result in '5H - Halted: Awaiting User Input'") 