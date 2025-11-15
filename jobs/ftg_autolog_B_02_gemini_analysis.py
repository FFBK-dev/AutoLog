#!/usr/bin/env python3
"""
Footage AutoLog B Step 2: Gemini Multi-Image Analysis
- Loads sampled frames with timecodes
- Includes FileMaker metadata (AI_Prompt, INFO_Metadata, etc.)
- Sends all frames to Gemini in single request
- Returns structured JSON with per-frame captions and global metadata
- Supports both LF (Library Footage) and AF (Archival Footage)
"""

import sys
import os
import json
import warnings
from pathlib import Path
from datetime import datetime

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.gemini_client import global_gemini_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "ai_prompt": "AI_Prompt",
    "metadata": "INFO_Metadata",
    "filename": "INFO_Filename",
    "duration": "SPECS_File_Duration_Timecode",
    "dev_console": "AI_DevConsole"
}


def load_tags():
    """Load approved footage tags list."""
    tags_path = Path(__file__).resolve().parent.parent / "tags" / "footage-tags.tab"
    try:
        with open(tags_path, 'r') as f:
            tags = []
            for line in f.readlines():
                line = line.strip()
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        tags.append({'name': parts[0].strip(), 'description': parts[1].strip()})
                    elif len(parts) == 1:
                        tags.append({'name': parts[0].strip(), 'description': ''})
        print(f"  -> Loaded {len(tags)} approved footage tags")
        return tags
    except Exception as e:
        print(f"  -> WARNING: Failed to load footage tags: {e}")
        return []

def load_bins(footage_id):
    """Load approved bins list based on footage ID prefix."""
    # Determine which bins file to use based on footage ID
    if footage_id.startswith("AF"):
        bins_filename = "archival-footage-bins.txt"
        media_type = "archival footage"
    elif footage_id.startswith("LF"):
        bins_filename = "live-footage-bins.txt"
        media_type = "live footage"
    else:
        print(f"  -> WARNING: Unknown footage ID prefix for {footage_id}, defaulting to live footage bins")
        bins_filename = "live-footage-bins.txt"
        media_type = "live footage (default)"
    
    bins_path = Path(__file__).resolve().parent.parent / "tags" / bins_filename
    try:
        with open(bins_path, 'r') as f:
            bins = []
            for line in f.readlines():
                line = line.strip()
                # Skip comments and empty lines
                if line and not line.startswith('#'):
                    parts = line.split('\t')
                    bin_name = parts[0].strip()
                    bins.append(bin_name)
        print(f"  -> Loaded {len(bins)} approved bins for {media_type}")
        return bins
    except Exception as e:
        print(f"  -> WARNING: Failed to load bins file ({bins_filename}): {e}")
        return []


def build_gemini_prompt(footage_data, frames_metadata, tags, bins):
    """Build structured prompt for Gemini with all context."""
    
    footage_id = footage_data.get(FIELD_MAPPING["footage_id"], "")
    ai_prompt = footage_data.get(FIELD_MAPPING["ai_prompt"], "")
    metadata = footage_data.get(FIELD_MAPPING["metadata"], "")
    filename = footage_data.get(FIELD_MAPPING["filename"], "")
    duration = footage_data.get(FIELD_MAPPING["duration"], "")
    
    # Format tags list
    tags_list_items = []
    for tag in tags:
        if tag['description']:
            tags_list_items.append(f"- {tag['name']}: {tag['description']}")
        else:
            tags_list_items.append(f"- {tag['name']}")
    tags_list_text = "\n".join(tags_list_items)
    
    # Format bins list
    bins_list_items = [f"- {bin_name}" for bin_name in bins]
    bins_list_text = "\n".join(bins_list_items)
    
    # Build frame list with timecodes
    frame_list = []
    for i, (frame_filename, frame_data) in enumerate(sorted(frames_metadata.items()), 1):
        timecode = frame_data['timecode_formatted']
        timestamp = frame_data['timestamp_seconds']
        frame_list.append(f"Frame {i} at {timecode} ({timestamp:.2f}s)")
    
    frame_list_text = "\n".join(frame_list)
    
    prompt = f"""You are an assistant editor creating catalog metadata for live footage.

CONTEXT HIERARCHY - Use information in this priority order:
1. PRIMARY: What you see in each frame (the definitive source)
2. SECONDARY: User-provided context below

General context for this footage:
{ai_prompt if ai_prompt else "(No context provided)"}

Additional metadata:
- Metadata: {metadata if metadata else "(None)"}
- Filename: {filename}
- Duration: {duration}

CRITICAL INSTRUCTIONS:
- Analyze ALL frames as a continuous video sequence
- Detect camera movements by comparing frames (pan, tilt, zoom, static, etc.)
- Use the general context when it directly applies to what you observe
- Don't add details from context that aren't visible in the frames
- Prefer "Drone" for UAV footage, not "aerial" unless very high altitude
- For each frame, provide a vivid caption describing people, setting, action, objects, and shot type

You will analyze {len(frames_metadata)} frames from this video at the following timecodes:
{frame_list_text}

(Images will follow in order after this text)

SHOT TYPE GUIDANCE:
- WIDE SHOT (WS/MWS): Full subjects with significant surrounding environment
- MEDIUM SHOT (MS/MCU): Partial subjects or balanced subject-to-environment ratio
- CLOSE SHOT (CU/ECU): Tight focus on details, minimal background
- DRONE SHOT: UAV footage at typical altitudes (<400ft)

CAMERA MOTION DETECTION:
Analyze how the view changes between frames to detect:
- static: No camera movement
- pan_left/pan_right: Horizontal camera rotation
- tilt_up/tilt_down: Vertical camera rotation
- push_in/pull_out: Camera moves toward/away from subject
- handheld: Shaky, unstable movement
- gimbal: Smooth stabilized movement
- unknown: Cannot determine from available frames

APPROVED TAGS - Select tags for visually significant elements:
{tags_list_text}

CRITICAL TAG SELECTION RULES:
- ONLY tag elements that are PROMINENT, CENTRAL, or VISUALLY SIGNIFICANT in the footage
- An element must play a meaningful role in the composition or narrative
- DO NOT tag background elements, incidental details, or barely visible items
- Select as many tags as appropriate based on visual prominence (no arbitrary limits)

APPROVED BINS - Select ONE primary bin for Avid organization:
{bins_list_text}

CRITICAL BIN SELECTION RULE:
- Select 1-4 bins from the APPROVED BINS LIST above
- The first bin should be MOST representative of this footage for Avid organization
- Return bins as a comma-separated string in priority order
- Do not invent bin names - ONLY use bins from the provided list

Return your analysis as strict JSON with this exact structure:
{{
  "asset_id": "{footage_id}",
  "global": {{
    "title": "3-8 word descriptive title (NO date info in title)",
    "synopsis": "2-4 sentence factual description of the visual content. Start directly with subject/action. NO phrases like 'This video shows' or 'The footage depicts'. End with proper nouns from context (location names, plantation names, building names, etc.) and date in this EXACT format: '[description text]. [Proper Noun Location]. [Month Year].' Do NOT use connecting phrases like 'filmed at' or 'shot at' - just append the proper noun location and date as separate elements.",
    "date": "YYYY/MM/DD or YYYY/MM or YYYY format, empty string if unknown",
    "location": "Proper noun location name from context (e.g. 'Myrtle Grove Plantation', 'Independence Hall', 'Golden Gate Bridge'). Use the FULL proper noun name if provided in context. Empty string if no specific location name in context.",
    "audio_type": "Sound or MOS (will be determined from audio detection)",
    "camera_summary": ["List of camera movements detected across the sequence"],
    "tags": ["Select all visually prominent tags from approved tags list"],
    "avid_bins": "REQUIRED - Comma-separated string of 1-4 bin names from the approved bins list, with the first being MOST representative of this footage"
  }},
  "frames": [
    {{
      "frame_number": 1,
      "timestamp_sec": 0.0,
      "timecode": "00:00:00:00",
      "caption": "Vivid description of this specific frame",
      "camera_motion": ["Detected motion for this frame"],
      "confidence": 0.9
    }}
  ]
}}

CRITICAL: Ensure every frame in the response includes its exact timestamp_sec and timecode that matches the input frame list above.

SYNOPSIS FORMAT EXAMPLE:
Good: "A camera rises through ornate iron gates revealing a tree-lined driveway leading to a colonial mansion. Spanish moss hangs from oak trees framing the approach. Myrtle Grove Plantation. November 2025."

Bad: "This video shows a camera rising through gates at Myrtle Grove Plantation filmed in November 2025."

Key difference: Clean separation with periods, no connecting phrases, proper noun location as distinct element."""
    
    return prompt


def write_to_dev_console(record_id, token, message):
    """Write to AI_DevConsole field."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console_entry = f"[{timestamp}] {message}"
        field_data = {FIELD_MAPPING["dev_console"]: console_entry}
        config.update_record(token, "FOOTAGE", record_id, field_data)
    except Exception as e:
        print(f"  -> WARNING: Failed to write to AI_DevConsole: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    footage_id = sys.argv[1]
    
    # Flexible token handling
    if len(sys.argv) == 2:
        token = config.get_token()
        print(f"Direct mode: Created new FileMaker session for {footage_id}")
    elif len(sys.argv) == 3:
        token = sys.argv[2]
        print(f"Subprocess mode: Using provided token for {footage_id}")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py footage_id [token]\n")
        sys.exit(1)
    
    try:
        print(f"=== Starting Gemini Multi-Image Analysis for {footage_id} ===")
        
        # Get the current record
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        footage_data = config.get_record(token, "FOOTAGE", record_id)
        
        # Load assessment data from step 1 (supports both LF and AF prefixes)
        assessment_path = f"/private/tmp/ftg_autolog_{footage_id}/assessment.json"
        
        if not os.path.exists(assessment_path):
            raise FileNotFoundError(f"Assessment file not found: {assessment_path}. Run step 1 first.")
        
        with open(assessment_path, 'r') as f:
            assessment_data = json.load(f)
        
        print(f"  -> Loaded assessment data: {len(assessment_data['frames'])} frames")
        
        # Setup Gemini client
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        gemini_model = os.getenv('GEMINI_MODEL', 'gemini-2.0-pro-exp')
        
        if not gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not found in environment")
        
        global_gemini_client.set_api_key(gemini_api_key, gemini_model)
        
        # Load tags
        tags = load_tags()
        
        # Load bins (based on footage ID prefix)
        bins = load_bins(footage_id)
        
        # Build prompt
        print(f"\n📝 Building Gemini prompt...")
        prompt = build_gemini_prompt(footage_data, assessment_data['frames'], tags, bins)
        
        # Log prompt to DevConsole for visibility
        print(f"  -> Logging prompt to AI_DevConsole...")
        write_to_dev_console(record_id, token, f"Gemini Analysis Prompt:\n{prompt[:500]}...")
        
        # Prepare image list
        output_dir = assessment_data['output_directory']
        image_paths = []
        
        for frame_filename in sorted(assessment_data['frames'].keys()):
            frame_path = os.path.join(output_dir, frame_filename)
            if os.path.exists(frame_path):
                image_paths.append(frame_path)
        
        print(f"  -> Prepared {len(image_paths)} images for Gemini")
        
        # Define response schema for structured output
        response_schema = {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "global": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "synopsis": {"type": "string"},
                        "date": {"type": "string"},
                        "location": {"type": "string"},
                        "audio_type": {"type": "string"},
                        "camera_summary": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "avid_bins": {"type": "string"}
                    },
                    "required": ["title", "synopsis", "date", "location", "audio_type", "camera_summary", "tags", "avid_bins"]
                },
                "frames": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "frame_number": {"type": "integer"},
                            "timestamp_sec": {"type": "number"},
                            "timecode": {"type": "string"},
                            "caption": {"type": "string"},
                            "camera_motion": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "confidence": {"type": "number"}
                        },
                        "required": ["frame_number", "timestamp_sec", "timecode", "caption", "camera_motion", "confidence"]
                    }
                }
            },
            "required": ["asset_id", "global", "frames"]
        }
        
        # Call Gemini
        print(f"\n🚀 Calling Gemini API with {len(image_paths)} images...")
        print(f"  -> Model: {gemini_model}")
        print(f"  -> Timeout: 180s")
        
        response = global_gemini_client.generate_content(
            prompt=prompt,
            images=image_paths,
            response_schema=response_schema,
            max_retries=3,
            timeout=180
        )
        
        # Parse response
        response_text = response.text
        print(f"\n📊 Received Gemini response ({len(response_text)} chars)")
        
        try:
            gemini_result = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse Gemini response as JSON: {e}")
            print(f"Response text: {response_text[:500]}...")
            raise
        
        # Update audio_type from assessment
        if assessment_data['audio_status'] == 'silent':
            gemini_result['global']['audio_type'] = 'MOS'
        elif assessment_data['audio_status'] == 'transcribing':
            gemini_result['global']['audio_type'] = 'Sound'
        
        # Save result
        result_path = os.path.join(output_dir, "gemini_result.json")
        with open(result_path, 'w') as f:
            json.dump(gemini_result, f, indent=2)
        
        print(f"  -> Saved result to: {result_path}")
        
        # Print summary
        print(f"\n=== Gemini Analysis Complete ===")
        print(f"  Title: {gemini_result['global']['title']}")
        print(f"  Synopsis: {gemini_result['global']['synopsis'][:100]}...")
        print(f"  Date: {gemini_result['global']['date']}")
        print(f"  Location: {gemini_result['global']['location']}")
        print(f"  Audio Type: {gemini_result['global']['audio_type']}")
        print(f"  Tags: {', '.join(gemini_result['global']['tags'])}")
        print(f"  Avid Bins: {gemini_result['global'].get('avid_bins', 'None')}")
        print(f"  Frames analyzed: {len(gemini_result['frames'])}")
        
        print(f"\n✅ Gemini analysis completed for {footage_id}")
        print(f"🔄 Ready for Step 5: Create Frame Records")
        
    except Exception as e:
        print(f"❌ Error in Gemini analysis for {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

