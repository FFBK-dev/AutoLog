#!/usr/bin/env python3
"""
Polling-Based Footage AutoLog Workflow Controller

This script implements a continuous polling approach where:
1. Records are polled by status and advanced independently
2. Parent-child dependencies are handled explicitly
3. Retries are seamless (just pick up on next poll)
4. Multiple records can progress in parallel without conflicts
5. No complex sequential workflows - each record moves at its own pace

Advantages over sequential workflow:
- More resilient to individual failures
- Better parallel processing
- Seamless retries
- Cleaner dependency handling
- No workflow state management
"""

import subprocess
import sys
import time
from pathlib import Path
import requests
import traceback
from datetime import datetime
import warnings
import json
import concurrent.futures
import threading
import os
import logging

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.local_metadata_evaluator import evaluate_metadata_local
from utils.status_cache import StatusCache
from utils.batch_status_checker import BatchStatusChecker

def tprint(message):
    """Print with timestamp for performance debugging."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}", flush=True)  # Force flush for real-time streaming

# No arguments - continuously polls for records
__ARGS__ = []

JOBS_DIR = Path(__file__).resolve().parent

# Field mappings for FOOTAGE and FRAMES layouts
FIELD_MAPPING = {
    # FOOTAGE Layout Fields
    "footage_id": "INFO_FTG_ID",
    "status": "AutoLog_Status", 
    "filepath": "SPECS_Filepath_Server",
    "metadata": "INFO_Metadata",
    "url": "SPECS_URL",
    "dev_console": "AI_DevConsole",
    "archival_id": "INFO_Archival_ID",
    "thumbnail": "SPECS_Thumbnail",
    "description": "INFO_Description",
    "filename": "INFO_Filename",
    "source": "INFO_Source",
    
    # Video Specs (from FFprobe)
    "codec": "SPECS_File_Codec",
    "framerate": "SPECS_File_Framerate",
    "start_tc": "SPECS_File_startTC",
    "dimensions": "SPECS_File_Dimensions",
    "duration": "SPECS_File_Duration_Timecode",
    "frames": "SPECS_File_Frames",
    
    # FRAMES Layout Fields  
    "frame_parent_id": "FRAMES_ParentID",
    "frame_status": "FRAMES_Status",
    "frame_id": "FRAMES_ID",
    "frame_thumbnail": "FRAMES_Thumbnail",
    "frame_caption": "FRAMES_Caption",
    "frame_transcript": "FRAMES_Transcript",
    "frame_timecode": "FRAMES_TC_IN",
    "frame_framerate": "FOOTAGE::SPECS_File_Framerate",
    "frame_embed_text": "FRAMES_Embed_Text",
    "frame_embed_fused": "FRAMES_Embed_Fused"
}

# Define polling targets - each status that needs processing
# NOTE: Frames should NOT auto-advance beyond "4 - Audio Transcribed" 
# to preserve parent dependency checks
# Optimized for M4 Mac Mini performance 🚀
POLLING_TARGETS = [
    {
        "name": "Step 1: Get File Info",
        "status": "0 - Pending File Info",
        "next_status": "1 - File Info Complete",
        "script": "footage_autolog_01_get_file_info.py",
        "timeout": 300,
        "max_workers": 12  # I/O bound - can handle more
    },
    {
        "name": "Step 2: Generate Thumbnails", 
        "status": "1 - File Info Complete",
        "next_status": "2 - Thumbnails Complete",
        "script": "footage_autolog_02_generate_thumbnails.py", 
        "timeout": 300,
        "max_workers": 16  # Video processing - M4 excels here
    },
    {
        "name": "Step 3: Create Frame Records",
        "status": "2 - Thumbnails Complete", 
        "next_status": "3 - Creating Frames",
        "script": "footage_autolog_03_create_frames.py",
        "timeout": 300,
        "max_workers": 10  # Database intensive - moderate increase
    },
    {
        "name": "Step 4: Process URL (Conditional)",
        "status": "3 - Creating Frames",
        "next_status": "4 - Scraping URL", 
        "script": "footage_autolog_04_scrape_url.py",
        "timeout": 300,
        "max_workers": 8,  # Network I/O - can handle more concurrent requests
        "conditional": True,
        "check_url_only": True  # Simple URL existence check
    },
    {
        "name": "Step 5: Process Frame Info",
        "status": ["4 - Scraping URL", "3 - Creating Frames", "5 - Processing Frame Info"],  # Multiple valid start states
        "next_status": "5 - Processing Frame Info",
        "script": "footage_autolog_05_process_frames.py",
        "timeout": 1800,  # Longer timeout for frame processing
        "max_workers": 20,  # Most intensive step - max out the M4 power
        "check_frame_dependencies": True  # Special handling for frame completion
    },
    {
        "name": "Step 6: Generate Description",
        "status": "5 - Processing Frame Info",
        "next_status": "6 - Generating Description",
        "final_status": "7 - Generating Embeddings",  # Set after completion
        "script": "footage_autolog_06_generate_description.py",
        "timeout": 600,
        "max_workers": 12,  # AI/OpenAI calls - can parallelize well
        "requires_frame_completion": True,  # Must wait for all frames to be ready
        # NOTE: Frames should NEVER be moved beyond "4 - Audio Transcribed" - PSOS handles the rest
    },
    # NOTE: "Awaiting User Input" is now a true terminal state
    # Users must manually change status (e.g., to "Force Resume") to resume processing
    # The special resume polling target has been removed
]

def find_records_by_status(token, status_list):
    """Find all records with specified status(es)."""
    if isinstance(status_list, str):
        status_list = [status_list]
    
    all_records = []
    
    for status in status_list:
        try:
            query = {
                "query": [{FIELD_MAPPING["status"]: status}],
                "limit": 100
            }
            
            response = requests.post(
                config.url("layouts/FOOTAGE/_find"),
                headers=config.api_headers(token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 404:
                continue  # No records with this status
            
            response.raise_for_status()
            records = response.json()['response']['data']
            
            for record in records:
                footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
                if footage_id:
                    all_records.append({
                        "footage_id": footage_id,
                        "record_id": record['recordId'],
                        "current_status": status,
                        "record_data": record['fieldData']
                    })
        
        except Exception as e:
            tprint(f"❌ Error finding records with status '{status}': {e}")
            continue
    
    return all_records

def check_frame_completion(token, footage_id):
    """Check if ALL child frames are ready for Step 6 (description generation)."""
    try:
        # Get all child frames for this footage
        frames_response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json={"query": [{"FRAMES_ParentID": footage_id}]},
            verify=False,
            timeout=10
        )
        
        if frames_response.status_code == 404:
            return False, "No frames found"
        
        if frames_response.status_code != 200:
            return False, f"Error fetching frames: {frames_response.status_code}"
        
        frames = frames_response.json()['response']['data']
        
        if not frames:
            return False, "No frames found"
        
        total_frames = len(frames)
        completed_frames = 0
        
        for frame in frames:
            frame_data = frame['fieldData']
            frame_status = frame_data.get(FIELD_MAPPING["frame_status"], "")
            caption = frame_data.get("FRAMES_Caption", "").strip()
            
            # Frame is ready for Step 6 if:
            # 1. Status is "4 - Audio Transcribed" AND has caption content (fully complete), OR
            # 2. Status is higher than "4 - Audio Transcribed" (handled by PSOS)
            # Note: We require BOTH status progression AND content to prevent premature Step 6 trigger
            if (frame_status == "4 - Audio Transcribed" and caption) or frame_status in ["5 - Generating Embeddings", "6 - Embeddings Complete", "6 - Complete"]:
                completed_frames += 1
        
        if completed_frames == total_frames:
            return True, f"All {total_frames} frames ready for Step 6"
        else:
            return False, f"{completed_frames}/{total_frames} frames ready"
            
    except Exception as e:
        tprint(f"⚠️ Error checking frame completion: {e}")
        return False, f"Error: {e}"

def evaluate_metadata_quality(record_data, token, record_id=None):
    """Evaluate metadata quality using local analysis with simplified 40-point scale."""
    try:
        # Check if this is an LF item (original camera file)
        footage_id = record_data.get(FIELD_MAPPING["footage_id"], "")
        is_lf_item = footage_id and footage_id.startswith("LF")
        
        # Combine all metadata fields
        metadata_parts = []
        
        # Add technical metadata from dev_FFMPEG field
        ffmpeg_data = record_data.get('dev_FFMPEG', '')
        if ffmpeg_data:
            metadata_parts.append(f"Technical Metadata:\n{ffmpeg_data}")
        
        # Add INFO_Metadata field
        info_metadata = record_data.get(FIELD_MAPPING["metadata"], '')
        if info_metadata:
            metadata_parts.append(f"EXIF/Technical Info:\n{info_metadata}")
        
        # Add other fields
        for field in ["description", "source", "archival_id", "url"]:
            value = record_data.get(FIELD_MAPPING.get(field, field), '')
            if value:
                metadata_parts.append(f"{field.title()}:\n{value}")
        
        combined_metadata = "\n\n".join(metadata_parts)
        
        if not combined_metadata.strip():
            console_msg = "Metadata Evaluation: NO METADATA AVAILABLE - Cannot evaluate quality"
            if record_id:
                write_to_dev_console(record_id, token, console_msg)
            return False
        
        # Special handling for LF items (original camera files)
        if is_lf_item:
            # LF items always go to "Awaiting User Input" - they can never be processed automatically
            evaluate_lf_metadata_quality(combined_metadata, record_id, token, footage_id)
            return False
        
        # Use simplified local evaluator (no URL-aware logic needed)
        evaluation = evaluate_metadata_local(combined_metadata)
        is_sufficient = evaluation.get("sufficient", False)
        reason = evaluation.get("reason", "No reason provided")
        confidence = evaluation.get("confidence", "medium")
        score = evaluation.get("score", 0.0)
        
        # Write evaluation results to AI_DevConsole
        if record_id:
            console_msg = f"Metadata Evaluation: {'✅ PASSED' if is_sufficient else '❌ FAILED'}\n"
            console_msg += f"Score: {score:.0f}/50 (Threshold: 10+)\n"
            console_msg += f"Confidence: {confidence}\n"
            console_msg += f"Details: {reason}"
            write_to_dev_console(record_id, token, console_msg)
        
        return is_sufficient
        
    except Exception as e:
        tprint(f"❌ Error in metadata evaluation: {e}")
        
        # Write error to console
        if record_id:
            console_msg = f"Metadata Evaluation: ❌ ERROR\nException: {str(e)}\nUsing fallback evaluation..."
            write_to_dev_console(record_id, token, console_msg)
        
        # Simple fallback: 30+ characters is reasonable (more generous)
        combined_length = sum(len(str(record_data.get(FIELD_MAPPING.get(field, field), ''))) 
                            for field in ["metadata", "description", "source", "archival_id"])
        fallback_result = combined_length > 30
        
        if record_id:
            fallback_msg = f"Fallback Result: {'✅ PASSED' if fallback_result else '❌ FAILED'} (length check)\nCombined metadata: {combined_length} chars ({'>' if fallback_result else '≤'}30 threshold)"
            write_to_dev_console(record_id, token, fallback_msg)
        
        return fallback_result

def evaluate_lf_metadata_quality(combined_metadata, record_id, token, footage_id):
    """Special metadata evaluation for LF items (original camera files)."""
    try:
        # LF items ALWAYS require user input - we can never automatically determine enough
        # about original camera files to process them without human intervention
        
        console_msg = f"LF Metadata Evaluation: ⏳ AWAITING USER INPUT\n"
        console_msg += f"Original Camera File: {footage_id}\n"
        console_msg += f"Reason: LF items (original camera files) always require manual metadata input\n"
        console_msg += f"Action: Setting to 'Awaiting User Input' for manual processing\n"
        console_msg += f"Available metadata: {len(combined_metadata.strip())} characters"
        
        write_to_dev_console(record_id, token, console_msg)
        
        # LF items NEVER pass automatic evaluation - they always need user input
        return False
        
    except Exception as e:
        console_msg = f"LF Metadata Evaluation: ❌ ERROR\nException: {str(e)}\nSetting to Awaiting User Input..."
        write_to_dev_console(record_id, token, console_msg)
        
        # Even on error, LF items should go to user input
        return False

def write_to_dev_console(record_id, token, message):
    """Write a message to the AI_DevConsole field."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console_entry = f"[{timestamp}] {message}"
        
        # Update the AI_DevConsole field
        field_data = {FIELD_MAPPING["dev_console"]: console_entry}
        config.update_record(token, "FOOTAGE", record_id, field_data)
        
    except Exception as e:
        tprint(f"⚠️ WARNING: Failed to write to AI_DevConsole: {e}")

def update_status(record_id, token, new_status, max_retries=3):
    """Update record status with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            payload = {"fieldData": {FIELD_MAPPING["status"]: new_status}}
            response = requests.patch(
                config.url(f"layouts/FOOTAGE/records/{record_id}"),
                headers=config.api_headers(current_token),
                json=payload,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return True
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
    
    return False

def run_single_script(script_name, footage_id, token, timeout=300):
    """Run a single script for a footage ID."""
    script_path = JOBS_DIR / script_name
    
    if not script_path.exists():
        return False, f"Script not found: {script_name}"
    
    try:
        result = subprocess.run(
            ["python3", str(script_path), footage_id, token],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        success = result.returncode == 0
        error_msg = result.stderr.strip() if result.stderr else None
        
        return success, error_msg
        
    except subprocess.TimeoutExpired:
        return False, f"Script timed out after {timeout}s"
    except Exception as e:
        return False, f"System error: {str(e)}"

def update_frame_statuses_for_footage(footage_id, token, new_status, max_retries=3):
    """Update status for all frame records belonging to a specific footage parent."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            # Find all frame records for this footage
            query = {
                "query": [{FIELD_MAPPING["frame_parent_id"]: footage_id}],
                "limit": 1000
            }
            
            response = requests.post(
                config.url("layouts/FRAMES/_find"),
                headers=config.api_headers(current_token),
                json=query,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 404:
                tprint(f"  -> No frames found for {footage_id}")
                return True  # No frames found
            
            response.raise_for_status()
            records = response.json()['response']['data']
            
            if not records:
                tprint(f"  -> No frame records found for {footage_id}")
                return True
            
            tprint(f"  -> Found {len(records)} frames to update for {footage_id}")
            
            # Update each frame record
            updated_count = 0
            failed_count = 0
            for record in records:
                frame_record_id = record['recordId']
                frame_id = record['fieldData'].get(FIELD_MAPPING["frame_id"], f"Frame_{frame_record_id}")
                current_frame_status = record['fieldData'].get(FIELD_MAPPING["frame_status"], "Unknown")
                
                try:
                    payload = {"fieldData": {FIELD_MAPPING["frame_status"]: new_status}}
                    frame_response = requests.patch(
                        config.url(f"layouts/FRAMES/records/{frame_record_id}"),
                        headers=config.api_headers(current_token),
                        json=payload,
                        verify=False,
                        timeout=30
                    )
                    
                    if frame_response.status_code == 401:
                        current_token = config.get_token()
                        # Retry this frame with new token
                        frame_response = requests.patch(
                            config.url(f"layouts/FRAMES/records/{frame_record_id}"),
                            headers=config.api_headers(current_token),
                            json=payload,
                            verify=False,
                            timeout=30
                        )
                    
                    frame_response.raise_for_status()
                    updated_count += 1
                    tprint(f"  -> ✅ {frame_id}: {current_frame_status} → {new_status}")
                    
                except Exception as e:
                    failed_count += 1
                    tprint(f"  -> ❌ {frame_id}: Failed to update from '{current_frame_status}' to '{new_status}': {e}")
                    continue  # Skip failed updates
            
            tprint(f"  -> Frame status update summary for {footage_id}: {updated_count} updated, {failed_count} failed")
            
            if failed_count > 0:
                tprint(f"  -> ⚠️ {footage_id}: Some frame updates failed - may need manual intervention")
            
            return updated_count > 0  # Return True if at least one frame was updated
            
        except Exception as e:
            tprint(f"  -> ❌ Error in update_frame_statuses_for_footage for {footage_id}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
    
    tprint(f"  -> ❌ Failed to update frame statuses for {footage_id} after {max_retries} attempts")
    return False

def process_polling_target(target, token, poll_stats):
    """Process all records for a specific polling target."""
    target_name = target["name"]
    source_status = target["status"]
    next_status = target["next_status"]
    script_name = target["script"]
    timeout = target.get("timeout", 300)
    max_workers = target.get("max_workers", 5)
    
    tprint(f"🔍 Polling: {target_name}")
    
    # Find records ready for this step
    records = find_records_by_status(token, source_status)
    
    if not records:
        tprint(f"  -> No records found")
        return
    
    tprint(f"  -> Found {len(records)} records to process")
    
    # DEBUGGING: Show specific records found for step 6
    if target_name == "Step 6: Generate Description":
        tprint(f"  -> 🎯 STEP 6 CANDIDATES:")
        for record in records:
            footage_id = record["footage_id"]
            tprint(f"     -> {footage_id}: Status '{record['current_status']}'")
    
    # Filter records based on special conditions
    eligible_records = []
    
    for record in records:
        footage_id = record["footage_id"]
        record_data = record["record_data"]
        
        # Check conditional URL scraping (always scrape if URL exists, except for LF items)
        if target.get("conditional") and target.get("check_url_only"):
            # LF items should go to Awaiting User Input instead of URL scraping
            if footage_id.startswith("LF"):
                tprint(f"  -> {footage_id}: LF item - setting to Awaiting User Input (requires manual processing)")
                update_status(record["record_id"], token, "Awaiting User Input")
                update_frame_statuses_for_footage(footage_id, token, "Awaiting User Input")
                continue
            
            url = record_data.get(FIELD_MAPPING["url"], '')
            has_url = bool(url and url.strip())
            
            if not has_url:
                tprint(f"  -> {footage_id}: SKIP - no URL available for scraping")
                # Update status to skip this step
                update_status(record["record_id"], token, next_status)
                continue
            else:
                tprint(f"  -> {footage_id}: URL found - proceeding with scraping")
        
        # Check frame completion requirements for step 6 (description generation)
        if target.get("requires_frame_completion"):
            frames_ready, frame_status = check_frame_completion(token, footage_id)
            if not frames_ready:
                tprint(f"  -> {footage_id}: Waiting for frames - {frame_status}")
                
                # Add detailed debugging for stuck records
                # Check if this record has been stuck for a while
                try:
                    # Get the record's fieldData to check timestamp or other indicators
                    current_time = time.time()
                    tprint(f"  -> {footage_id}: DETAILED FRAME STATUS:")
                    
                    # Re-query frames for detailed status
                    debug_response = requests.post(
                        config.url("layouts/FRAMES/_find"),
                        headers=config.api_headers(token),
                        json={"query": [{"FRAMES_ParentID": footage_id}], "limit": 20},
                        verify=False,
                        timeout=10
                    )
                    
                    if debug_response.status_code == 200:
                        debug_frames = debug_response.json()['response']['data']
                        for i, frame in enumerate(debug_frames[:5]):  # Show first 5 frames
                            frame_data = frame['fieldData']
                            frame_status = frame_data.get(FIELD_MAPPING["frame_status"], 'Unknown')
                            frame_caption = frame_data.get(FIELD_MAPPING["frame_caption"], '').strip()
                            frame_id = frame_data.get(FIELD_MAPPING["frame_id"], f'Frame_{i+1}')
                            
                            caption_length = len(frame_caption) if frame_caption else 0
                            tprint(f"     -> {frame_id}: '{frame_status}' (caption: {caption_length} chars)")
                    
                except Exception as debug_e:
                    tprint(f"  -> {footage_id}: Debug error: {debug_e}")
                
                continue
            else:
                # DEBUGGING: Show when frames ARE ready for step 6
                tprint(f"  -> {footage_id}: ✅ FRAMES ARE READY - {frame_status}")
                tprint(f"  -> {footage_id}: 🎯 PROCEEDING TO STEP 6 (Generate Description)")
        
        # Handle user resume logic
        if target.get("user_resume"):
            # This logic has been removed - "Awaiting User Input" is now a true terminal state
            # Users must manually change status to resume processing
            pass
        
        # Check frame dependencies for step 5
        if target.get("check_frame_dependencies"):
            # For step 5, we just need frames to exist (they'll be processed by the script)
            try:
                response = requests.post(
                    config.url("layouts/FRAMES/_find"),
                    headers=config.api_headers(token),
                    json={"query": [{"FRAMES_ParentID": footage_id}], "limit": 1},
                    verify=False,
                    timeout=10
                )
                if response.status_code == 404:
                    tprint(f"  -> {footage_id}: No frames found - skipping")
                    continue
            except:
                continue
        
        eligible_records.append(record)
    
    if not eligible_records:
        tprint(f"  -> No eligible records after filtering")
        
        # DEBUGGING: Show why step 6 records were filtered out
        if target_name == "Step 6: Generate Description":
            tprint(f"  -> 🎯 STEP 6 FILTERING RESULTS: All {len(records)} records were filtered out!")
            for record in records:
                footage_id = record["footage_id"]
                frames_ready, frame_status = check_frame_completion(token, footage_id)
                tprint(f"     -> {footage_id}: Frame check = {frames_ready} ({frame_status})")
        
        return
    
    tprint(f"  -> Processing {len(eligible_records)} eligible records")
    
    # DEBUGGING: Show which step 6 records made it through filtering
    if target_name == "Step 6: Generate Description":
        tprint(f"  -> 🎯 STEP 6 ELIGIBLE RECORDS:")
        for record in eligible_records:
            footage_id = record["footage_id"]
            tprint(f"     -> {footage_id}: ELIGIBLE for step 6!")
    
    # Process records in parallel
    def process_single_record(record):
        footage_id = record["footage_id"]
        record_id = record["record_id"]
        
        try:
            tprint(f"  -> Starting {footage_id}")
            
            # Update status to processing state (unless it's already there)
            current_status = record["current_status"]
            if current_status != next_status:
                if not update_status(record_id, token, next_status):
                    tprint(f"  -> {footage_id}: Failed to update status")
                    return False
            
            # Run the script
            success, error_msg = run_single_script(script_name, footage_id, token, timeout)
            
            if success:
                tprint(f"  -> ✅ {footage_id}: Completed")
                
                # DEBUGGING: Check what actually happened with frames after "completion"
                if script_name == "footage_autolog_05_process_frames.py":
                    try:
                        debug_response = requests.post(
                            config.url("layouts/FRAMES/_find"),
                            headers=config.api_headers(token),
                            json={"query": [{"FRAMES_ParentID": footage_id}], "limit": 10},
                            verify=False,
                            timeout=10
                        )
                        
                        if debug_response.status_code == 200:
                            debug_frames = debug_response.json()['response']['data']
                            status_counts = {}
                            content_counts = {"with_caption": 0, "with_transcript": 0, "empty": 0}
                            
                            for frame in debug_frames:
                                frame_data = frame['fieldData']
                                frame_status = frame_data.get(FIELD_MAPPING["frame_status"], 'Unknown')
                                caption = frame_data.get(FIELD_MAPPING["frame_caption"], '').strip()
                                transcript = frame_data.get(FIELD_MAPPING["frame_transcript"], '').strip()
                                
                                status_counts[frame_status] = status_counts.get(frame_status, 0) + 1
                                
                                if caption:
                                    content_counts["with_caption"] += 1
                                if transcript:
                                    content_counts["with_transcript"] += 1
                                if not caption and not transcript:
                                    content_counts["empty"] += 1
                            
                            # Show detailed post-completion frame status
                            status_summary = ", ".join([f"{status}: {count}" for status, count in status_counts.items()])
                            content_summary = f"Caption: {content_counts['with_caption']}, Transcript: {content_counts['with_transcript']}, Empty: {content_counts['empty']}"
                            
                            tprint(f"  -> 📊 POST-COMPLETION FRAME STATUS for {footage_id}:")
                            tprint(f"     Status breakdown: {status_summary}")
                            tprint(f"     Content breakdown: {content_summary}")
                            
                            # Check if frames are actually ready for step 6
                            frames_at_4 = status_counts.get('4 - Audio Transcribed', 0)
                            total_frames = len(debug_frames)
                            if frames_at_4 == total_frames and frames_at_4 > 0:
                                tprint(f"  -> ✅ {footage_id}: ALL {total_frames} frames ready for step 6!")
                            elif frames_at_4 > 0:
                                tprint(f"  -> ⚠️ {footage_id}: Only {frames_at_4}/{total_frames} frames at '4 - Audio Transcribed'")
                            else:
                                tprint(f"  -> ❌ {footage_id}: NO frames at '4 - Audio Transcribed' - step 6 won't trigger!")
                                
                    except Exception as debug_e:
                        tprint(f"  -> ❌ {footage_id}: Debug frame check failed: {debug_e}")
                
                # Handle final status update for step 6
                if target.get("final_status"):
                    final_status = target["final_status"]
                    tprint(f"  -> Setting {footage_id} final status to '{final_status}'")
                    if update_status(record_id, token, final_status):
                        tprint(f"  -> ✅ {footage_id}: Parent status updated to '{final_status}'")
                    else:
                        tprint(f"  -> ❌ {footage_id}: Failed to update parent final status")
                
                # Handle frame status updates after parent completion
                if target.get("update_frame_statuses_after"):
                    frame_status = target["update_frame_statuses_after"]
                    tprint(f"  -> 🔄 Moving ALL frames for {footage_id} to '{frame_status}'")
                    
                    if update_frame_statuses_for_footage(footage_id, token, frame_status):
                        tprint(f"  -> ✅ {footage_id}: Frame statuses updated to '{frame_status}'")
                    else:
                        tprint(f"  -> ❌ {footage_id}: Failed to update frame statuses")
                        
                    # Verify frame updates with a quick check
                    try:
                        verify_response = requests.post(
                            config.url("layouts/FRAMES/_find"),
                            headers=config.api_headers(token),
                            json={"query": [{"FRAMES_ParentID": footage_id}], "limit": 5},
                            verify=False,
                            timeout=10
                        )
                        
                        if verify_response.status_code == 200:
                            verify_frames = verify_response.json()['response']['data']
                            updated_count = 0
                            for frame in verify_frames:
                                current_frame_status = frame['fieldData'].get(FIELD_MAPPING["frame_status"], 'Unknown')
                                if current_frame_status == frame_status:
                                    updated_count += 1
                            
                            tprint(f"  -> 📊 VERIFICATION: {updated_count}/{len(verify_frames)} frames now at '{frame_status}'")
                    except:
                        tprint(f"  -> ⚠️ Could not verify frame status updates")
                
                poll_stats["successful"] += 1
                return True
            else:
                tprint(f"  -> ❌ {footage_id}: {error_msg}")
                poll_stats["failed"] += 1
                return False
                
        except Exception as e:
            tprint(f"  -> ❌ {footage_id}: Exception - {e}")
            poll_stats["failed"] += 1
            return False
    
    # Use ThreadPoolExecutor for parallel processing
    actual_max_workers = min(max_workers, len(eligible_records))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        futures = [executor.submit(process_single_record, record) for record in eligible_records]
        
        # Wait for completion
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                tprint(f"  -> Future exception: {e}")
                poll_stats["failed"] += 1

def check_all_records_terminal(token, footage_terminal_states, frame_terminal_states):
    """Check if all footage and frame records have reached terminal states."""
    try:
        # Check all footage records
        footage_response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"INFO_FTG_ID": "*"}],
                "limit": 1000
            },
            verify=False,
            timeout=30
        )
        
        if footage_response.status_code == 200:
            footage_records = footage_response.json()['response']['data']
            non_terminal_footage = 0
            status_counts = {}
            
            for record in footage_records:
                current_status = record['fieldData'].get(FIELD_MAPPING["status"], "Unknown")
                
                # Track status counts for debugging
                status_counts[current_status] = status_counts.get(current_status, 0) + 1
                
                if current_status not in footage_terminal_states and current_status != "Unknown":
                    non_terminal_footage += 1
            
            if non_terminal_footage > 0:
                tprint(f"📊 Completion check: {non_terminal_footage} footage records still processing")
                # Show status breakdown for debugging
                non_terminal_statuses = {status: count for status, count in status_counts.items() 
                                       if status not in footage_terminal_states and status != "Unknown"}
                if non_terminal_statuses:
                    tprint(f"📋 Non-terminal status breakdown: {non_terminal_statuses}")
                return False
        
        # Check all frame records
        frames_response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"FRAMES_ID": "*"}],
                "limit": 1000
            },
            verify=False,
            timeout=30
        )
        
        if frames_response.status_code == 200:
            frame_records = frames_response.json()['response']['data']
            
            # Build footage status map for frame parent checks
            footage_status_map = {}
            if footage_response.status_code == 200:
                for record in footage_records:
                    footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
                    footage_status = record['fieldData'].get(FIELD_MAPPING["status"], "Unknown")
                    if footage_id:
                        footage_status_map[footage_id] = footage_status
            
            non_terminal_frames = 0
            frame_status_counts = {}
            
            for record in frame_records:
                current_status = record['fieldData'].get(FIELD_MAPPING["frame_status"], "Unknown")
                parent_id = record['fieldData'].get(FIELD_MAPPING["frame_parent_id"])
                
                # Track status counts for debugging
                frame_status_counts[current_status] = frame_status_counts.get(current_status, 0) + 1
                
                # Consider frames with completed parents as effectively terminal
                if parent_id and parent_id in footage_status_map:
                    parent_status = footage_status_map[parent_id]
                    if parent_status in ["8 - Applying Tags", "9 - Complete"]:
                        continue  # Skip - parent completed, so frame is effectively done
                
                if current_status not in frame_terminal_states and current_status != "Unknown":
                    non_terminal_frames += 1
            
            if non_terminal_frames > 0:
                tprint(f"📊 Completion check: {non_terminal_frames} frame records still processing")
                # Show status breakdown for debugging
                non_terminal_frame_statuses = {status: count for status, count in frame_status_counts.items() 
                                             if status not in frame_terminal_states and status != "Unknown"}
                if non_terminal_frame_statuses:
                    tprint(f"📋 Non-terminal frame status breakdown: {non_terminal_frame_statuses}")
                return False
        
        tprint(f"✅ Completion check: All records have reached terminal states!")
        return True
        
    except Exception as e:
        tprint(f"❌ Error in completion check: {e}")
        return False

def run_polling_workflow(token, poll_duration=3600, poll_interval=30):
    """Run controlled concurrent polling - process ALL records individually every 30 seconds."""
    tprint(f"🚀 Starting controlled concurrent polling workflow")
    tprint(f"📊 Poll duration: {poll_duration}s, interval: {poll_interval}s")
    tprint(f"📋 Will stop early if all records reach completion or 'Awaiting User Input'")
    
    start_time = time.time()
    poll_count = 0
    
    # Initialize status cache and batch checker for efficient API usage
    status_cache = StatusCache(cache_duration_seconds=poll_interval)
    batch_checker = BatchStatusChecker(token)
    
    # Statistics tracking
    poll_stats = {
        "successful": 0,
        "failed": 0,
        "poll_cycles": 0,
        "api_calls_saved": 0,
        "last_activity": start_time
    }
    
    # Define terminal states that allow early completion
    footage_terminal_states = [
        "7 - Generating Embeddings", 
        "8 - Applying Tags", 
        "9 - Complete", 
        "Awaiting User Input"
    ]
    frame_terminal_states = [
        "4 - Audio Transcribed",    # Terminal for this workflow - PSOS handles beyond here
        "5 - Generating Embeddings", 
        "6 - Embeddings Complete",
        "6 - Complete",             # Terminal completion states (handled by PSOS)
        "Awaiting User Input"
    ]
    
    # Check if all records are already complete before starting
    try:
        all_complete = check_all_records_terminal(token, footage_terminal_states, frame_terminal_states)
        if all_complete:
            tprint(f"🎉 All records already completed or awaiting user input - no polling needed!")
            poll_stats["poll_cycles"] = 0
            return poll_stats
    except Exception as e:
        tprint(f"⚠️ Error in initial completion check: {e}")
    
    while time.time() - start_time < poll_duration:
        poll_count += 1
        cycle_start = time.time()
        
        tprint(f"\n=== POLL CYCLE {poll_count} ===")
        
        # Clear expired cache entries and reset per-cycle logging  
        status_cache.clear_expired_cache()
        if hasattr(process_frame_task, '_logged_waiting'):
            process_frame_task._logged_waiting.clear()
        
        cycle_successful = 0
        cycle_failed = 0
        
        try:
            # SCALABLE APPROACH: Query by specific statuses that need processing
            # This will work efficiently even with 100K+ records
            
            # Define all footage statuses that need processing (NOT terminal states)
            footage_processing_statuses = [
                "0 - Pending File Info",
                "1 - File Info Complete", 
                "2 - Thumbnails Complete",
                "3 - Creating Frames",
                "4 - Scraping URL",
                "5 - Processing Frame Info",
                "6 - Generating Description",
                "Force Resume"
                # NOTE: "Awaiting User Input" is a terminal state - user must manually change status to resume
            ]
            
            # Define all frame statuses that need processing
            frame_processing_statuses = [
                "1 - Pending Thumbnail",
                "2 - Thumbnail Complete",
                "3 - Caption Generated", 
                "4 - Audio Transcribed",
                "Force Resume"
            ]
            
            # Get footage records by processing statuses (much more efficient)
            footage_records = []
            for status in footage_processing_statuses:
                try:
                    # Use pagination for statuses that might have many records
                    offset = 0
                    batch_size = 500
                    status_total = 0
                    
                    while True:
                        # FileMaker API requires offset > 0, so omit it for first query
                        query_params = {
                            "query": [{"AutoLog_Status": status}],
                            "limit": batch_size
                        }
                        if offset > 0:
                            query_params["offset"] = offset
                        
                        footage_response = requests.post(
                            config.url("layouts/FOOTAGE/_find"),
                            headers=config.api_headers(token),
                            json=query_params,
                            verify=False,
                            timeout=30
                        )
                        
                        if footage_response.status_code == 200:
                            response_data = footage_response.json()['response']
                            status_records = response_data['data']
                            footage_records.extend(status_records)
                            status_total += len(status_records)
                            
                            # Check if we've retrieved all records for this status
                            if len(status_records) < batch_size:
                                break  # No more records
                            
                            offset += len(status_records)  # Move offset by actual records returned
                            
                            # Safety limit to prevent infinite loops (max 10K records per status)
                            if offset >= 10000:
                                tprint(f"⚠️ Reached safety limit for status '{status}' - stopping pagination")
                                break
                                
                        elif footage_response.status_code == 404:
                            break  # No records for this status
                        else:
                            tprint(f"⚠️ Error querying footage status '{status}': {footage_response.status_code}")
                            break
                    
                    if status_total > 0:
                        tprint(f"📊 Found {status_total} footage records with status '{status}'")
                        
                except Exception as e:
                    tprint(f"⚠️ Error querying footage status '{status}': {e}")
                    continue
            
            # Get frame records by processing statuses (much more efficient)
            frame_records = []
            for status in frame_processing_statuses:
                try:
                    # Use pagination for statuses that might have many records
                    offset = 0
                    batch_size = 1000  # Larger batches for frames
                    status_total = 0
                    
                    while True:
                        # FileMaker API requires offset > 0, so omit it for first query
                        query_params = {
                            "query": [{"FRAMES_Status": status}],
                            "limit": batch_size
                        }
                        if offset > 0:
                            query_params["offset"] = offset
                        
                        frames_response = requests.post(
                            config.url("layouts/FRAMES/_find"),
                            headers=config.api_headers(token),
                            json=query_params,
                            verify=False,
                            timeout=30
                        )
                        
                        if frames_response.status_code == 200:
                            response_data = frames_response.json()['response']
                            status_records = response_data['data']
                            frame_records.extend(status_records)
                            status_total += len(status_records)
                            
                            # Check if we've retrieved all records for this status
                            if len(status_records) < batch_size:
                                break  # No more records
                            
                            offset += len(status_records)  # Move offset by actual records returned
                            
                            # Safety limit to prevent infinite loops (max 50K frame records per status)
                            if offset >= 50000:
                                tprint(f"⚠️ Reached safety limit for frame status '{status}' - stopping pagination")
                                break
                                
                        elif frames_response.status_code == 404:
                            break  # No records for this status
                        else:
                            tprint(f"⚠️ Error querying frame status '{status}': {frames_response.status_code}")
                            break
                    
                    if status_total > 0:
                        tprint(f"📊 Found {status_total} frame records with status '{status}'")
                        
                except Exception as e:
                    tprint(f"⚠️ Error querying frame status '{status}': {e}")
                    continue
            
            all_tasks = []
            
            # Populate status cache with footage and frame records
            # This enables efficient parent-child dependency checks
            status_cache.add_footage_records(footage_records)
            status_cache.add_frame_records(frame_records)
            
            # Build a map of footage statuses for frame dependency checking
            footage_status_map = {}
            for footage_record in footage_records:
                footage_id = footage_record['fieldData'].get(FIELD_MAPPING["footage_id"])
                footage_status = footage_record['fieldData'].get(FIELD_MAPPING["status"], "Unknown")
                if footage_id:
                    footage_status_map[footage_id] = footage_status
            
            # Process footage records into tasks
            for record in footage_records:
                footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
                current_status = record['fieldData'].get(FIELD_MAPPING["status"], "Unknown")
                
                # Only include records that are NOT in terminal states
                if footage_id and current_status not in footage_terminal_states and current_status != "Unknown":
                    all_tasks.append({
                        "type": "footage",
                        "id": footage_id,
                        "record_id": record['recordId'],
                        "current_status": current_status,
                        "record_data": record['fieldData']
                    })
            
            # Process frame records into tasks
            for record in frame_records:
                frame_id = record['fieldData'].get(FIELD_MAPPING["frame_id"])
                current_status = record['fieldData'].get(FIELD_MAPPING["frame_status"], "Unknown")
                parent_id = record['fieldData'].get(FIELD_MAPPING["frame_parent_id"])
                
                # Skip frames if their parent has reached terminal success states
                if parent_id and parent_id in footage_status_map:
                    parent_status = footage_status_map[parent_id]
                    if parent_status in ["8 - Applying Tags", "9 - Complete"]:
                        # Skip this frame - parent has fully completed workflow
                        continue
                
                if frame_id and current_status not in frame_terminal_states and current_status != "Unknown":
                    all_tasks.append({
                        "type": "frame", 
                        "id": frame_id,
                        "record_id": record['recordId'],
                        "current_status": current_status,
                        "record_data": record['fieldData']
                    })
            
            tprint(f"📊 Found {len(all_tasks)} total records to process")
            
            # If no tasks found, check if everything is complete
            if not all_tasks:
                tprint(f"📊 No tasks to process - checking if all records are complete")
                try:
                    all_complete = check_all_records_terminal(token, footage_terminal_states, frame_terminal_states)
                    if all_complete:
                        tprint(f"🎉 No tasks found and all records complete - stopping polling!")
                        break
                    else:
                        tprint(f"⏳ No tasks found but some records still processing - continuing to poll")
                except Exception as e:
                    tprint(f"⚠️ Error checking completion when no tasks found: {e}")
            
            # Debug: Show Force Resume records specifically
            force_resume_footage = [task for task in all_tasks if task["type"] == "footage" and task["current_status"] == "Force Resume"]
            force_resume_frames = [task for task in all_tasks if task["type"] == "frame" and task["current_status"] == "Force Resume"]
            
            if force_resume_footage:
                tprint(f"🚀 FORCE RESUME: {len(force_resume_footage)} footage records")
                    
            if force_resume_frames:
                tprint(f"🚀 FORCE RESUME: {len(force_resume_frames)} frame records")
            
            # Debug: Show task breakdown
            footage_tasks = [task for task in all_tasks if task["type"] == "footage"]
            frame_tasks = [task for task in all_tasks if task["type"] == "frame"]
            tprint(f"📊 Processing: {len(footage_tasks)} footage, {len(frame_tasks)} frames")
            
            # Process ALL records concurrently (footage + frames)
            def process_single_task(task):
                """Process a single task (footage or frame) to its next step."""
                try:
                    task_id = task["id"]
                    task_type = task["type"]
                    current_status = task["current_status"]
                    record_data = task["record_data"]
                    
                    # Determine next action based on current status
                    if task_type == "footage":
                        return process_footage_task(task, token)
                    else:  # frame
                        return process_frame_task(task, token, status_cache)
                        
                except Exception as e:
                    tprint(f"❌ Error processing {task.get('type', 'unknown')} {task.get('id', 'unknown')}: {e}")
                    return False
            
            # CONTROLLED CONCURRENCY: Run tasks with proper resource management
            if all_tasks:
                max_workers = min(5, len(all_tasks))  # Very conservative limit to prevent overwhelming
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all tasks  
                    futures = [executor.submit(process_single_task, task) for task in all_tasks]
                    
                    # Wait with timeout to allow faster individual progression
                    completed_count = 0
                    failed_count = 0
                    
                    try:
                        # Use as_completed with timeout to avoid waiting too long
                        for future in concurrent.futures.as_completed(futures, timeout=30):
                            try:
                                result = future.result()
                                if result:
                                    completed_count += 1
                                else:
                                    failed_count += 1
                            except Exception as e:
                                failed_count += 1
                    except concurrent.futures.TimeoutError:
                        # Some tasks are still running - that's OK, they'll continue
                        tprint(f"⏱️ Cycle timeout - some tasks still running in background")
                    
                    cycle_successful = completed_count
                    cycle_failed = failed_count
                    
                    # Handle any cache misses with batch status check
                    unique_parents_needed = status_cache.get_unique_parents_needing_check()
                    if unique_parents_needed:
                        tprint(f"🔍 Batch checking {len(unique_parents_needed)} parent statuses for cache misses...")
                        batch_checker.token = token  # Update token in case it changed
                        batch_status_results = batch_checker.batch_check_footage_statuses(unique_parents_needed)
                        
                        if batch_status_results:
                            status_cache.batch_update_footage_statuses(batch_status_results)
                            poll_stats["api_calls_saved"] += len(unique_parents_needed) - 1  # Saved N-1 individual calls
                            tprint(f"✅ Updated cache with {len(batch_status_results)} parent statuses")
            
        except Exception as e:
            tprint(f"❌ Error in poll cycle: {e}")
            cycle_failed += 1
        
        cycle_duration = time.time() - cycle_start
        
        tprint(f"📊 Cycle {poll_count}: {cycle_successful} completed, {cycle_failed} failed ({cycle_duration:.1f}s)")
        
        # Update stats
        poll_stats["successful"] += cycle_successful
        poll_stats["failed"] += cycle_failed
        poll_stats["poll_cycles"] += 1
        
        if cycle_successful > 0 or cycle_failed > 0:
            poll_stats["last_activity"] = time.time()
        
        # Check if all records have reached terminal states (completion or awaiting user input)
        try:
            all_complete = check_all_records_terminal(token, footage_terminal_states, frame_terminal_states)
            if all_complete:
                tprint(f"🎉 All records have reached completion or 'Awaiting User Input' - stopping polling early!")
                break
        except Exception as e:
            tprint(f"⚠️ Error checking completion status: {e}")
        
        # Sleep until next poll cycle
        time.sleep(poll_interval)
    
    total_duration = time.time() - start_time
    tprint(f"\n=== POLLING SESSION COMPLETE ===")
    
    # Determine if we stopped early or reached timeout
    if total_duration < poll_duration - poll_interval:
        tprint(f"🎉 Stopped early - all records completed or awaiting user input")
    else:
        tprint(f"⏰ Reached maximum poll duration ({poll_duration}s)")
    
    tprint(f"Total duration: {total_duration:.1f}s")
    tprint(f"Poll cycles: {poll_stats['poll_cycles']}")
    tprint(f"Successful operations: {poll_stats['successful']}")
    tprint(f"Failed operations: {poll_stats['failed']}")
    
    # Cache performance stats
    cache_stats = status_cache.get_stats()
    tprint(f"🗄️ Cache performance:")
    tprint(f"   API calls saved: {poll_stats['api_calls_saved']}")
    tprint(f"   Cache hit rate: {cache_stats['hit_rate']:.1%}")
    tprint(f"   Cache hits: {cache_stats['cache_hits']}")
    tprint(f"   Cache misses: {cache_stats['cache_misses']}")
    
    return poll_stats

def process_footage_task(task, token):
    """Process a single footage record to its next step(s) - chain when possible."""
    footage_id = task["id"]
    current_status = task["current_status"]
    record_data = task["record_data"]
    
    # Only log significant events, not routine processing
    
    # Track how many steps we complete in this cycle
    steps_completed = 0
    max_steps_per_cycle = 5  # Prevent infinite loops
    
    while steps_completed < max_steps_per_cycle:

        
        # Special case: Check if ready for step 6 (description generation)
        if current_status == "5 - Processing Frame Info":
            frames_ready, frame_status = check_frame_completion(token, footage_id)
            if frames_ready:
                tprint(f"🎯 {footage_id}: ALL FRAMES READY → Step 6: Generate Description")
                success = run_footage_script(footage_id, "footage_autolog_06_generate_description.py", "6 - Generating Description", "7 - Generating Embeddings", token, task["record_id"])
                if success:
                    steps_completed += 1
                    current_status = "7 - Generating Embeddings"
                    # Frame status update is handled in run_footage_script function
                    break  # Final step completed
                else:
                    break
            else:
                tprint(f"⏳ {footage_id}: Waiting for frames - {frame_status}")
                break  # Dependency not met
        
        # Special case: Metadata evaluation AFTER step 4 (URL scraping)
        elif current_status == "4 - Scraping URL":
            # Handle LF items that somehow reached this step
            if footage_id.startswith("LF"):
                tprint(f"  -> {footage_id}: LF item reached URL scraping step - setting to Awaiting User Input")
                update_status(task["record_id"], token, "Awaiting User Input")
                update_frame_statuses_for_footage(footage_id, token, "Awaiting User Input")
                steps_completed += 1
                break
            
            # Get fresh record data to include any scraped content
            try:
                response = requests.get(
                    config.url(f"layouts/FOOTAGE/records/{task['record_id']}"),
                    headers=config.api_headers(token),
                    verify=False,
                    timeout=10
                )
                
                if response.status_code == 200:
                    fresh_record_data = response.json()['response']['data'][0]['fieldData']
                else:
                    fresh_record_data = record_data
            except:
                fresh_record_data = record_data
            
            # Evaluate metadata quality (including any scraped content)
            metadata_quality_good = evaluate_metadata_quality(fresh_record_data, token, task["record_id"])
            
            if metadata_quality_good:
                tprint(f"✅ {footage_id}: Metadata quality GOOD after URL step - proceeding to frame processing")
                success = run_footage_script(footage_id, "footage_autolog_05_process_frames.py", "5 - Processing Frame Info", None, token, task["record_id"])
                if success:
                    steps_completed += 1
                    current_status = "5 - Processing Frame Info"
                    # Brief delay to ensure frame status updates are committed before checking step 6 readiness
                    time.sleep(2)
                    # Continue to next iteration to check if step 6 is ready
                    continue
                else:
                    break
            else:
                tprint(f"⚠️ {footage_id}: Metadata quality BAD after URL step - setting parent AND children to Awaiting User Input")
                update_status(task["record_id"], token, "Awaiting User Input")
                update_frame_statuses_for_footage(footage_id, token, "Awaiting User Input")
                steps_completed += 1
                break  # Handled (waiting for user)
        
        # Special case: Handle user-resumed items
        elif current_status == "Awaiting User Input":
            # "Awaiting User Input" is a terminal state - no automatic processing
            # User must manually change the status (e.g., to "Force Resume") to resume processing
            tprint(f"⏸️ {footage_id}: In 'Awaiting User Input' state - requires manual intervention to resume")
            break
        
        # Special case: Force Resume - bypasses all metadata checks
        elif current_status == "Force Resume":
            tprint(f"🚀 FOOTAGE FORCE RESUME: {footage_id}")
            
            # Write force resume message to console
            write_to_dev_console(task["record_id"], token, "FORCE RESUME triggered by user - bypassing metadata evaluation")
            
            # NOTE: We no longer reset frame statuses to avoid re-processing completed frames
            # Instead, the frame processing script now understands "Force Resume" as equivalent to "2 - Thumbnail Complete"
            tprint(f"  -> {footage_id}: Starting frame processing (frames will be processed from their current state)...")
            
            # Immediately start frame processing regardless of metadata quality
            success = run_footage_script(footage_id, "footage_autolog_05_process_frames.py", "5 - Processing Frame Info", None, token, task["record_id"])
            if success:
                steps_completed += 1
                current_status = "5 - Processing Frame Info"
                # Continue to next iteration to check if step 6 is ready
                continue
            else:
                break
        
        # Standard progression - these can chain together
        else:
            status_map = {
                "0 - Pending File Info": ("footage_autolog_01_get_file_info.py", "1 - File Info Complete"),
                "1 - File Info Complete": ("footage_autolog_02_generate_thumbnails.py", "2 - Thumbnails Complete"),
                "2 - Thumbnails Complete": ("footage_autolog_03_create_frames.py", "3 - Creating Frames"),
                "3 - Creating Frames": ("footage_autolog_04_scrape_url.py", "4 - Scraping URL"),
            }
            
            # Special handling for LF items - set to Awaiting User Input
            if current_status == "3 - Creating Frames" and footage_id.startswith("LF"):
                tprint(f"  -> {footage_id}: LF item - setting to Awaiting User Input (requires manual processing)")
                update_status(task["record_id"], token, "Awaiting User Input")
                update_frame_statuses_for_footage(footage_id, token, "Awaiting User Input")
                steps_completed += 1
                break  # LF items always stop here for manual input
            
            if current_status in status_map:
                script, next_status = status_map[current_status]
                success = run_footage_script(footage_id, script, next_status, None, token, task["record_id"])
                if success:
                    steps_completed += 1
                    current_status = next_status
                    tprint(f"⚡ {footage_id}: Chaining to next step → {next_status}")
                    # Continue to next iteration for possible chaining
                    continue
                else:
                    break
            else:
                # No more steps to process
                break
    
    if steps_completed > 1:
        tprint(f"🚀 {footage_id}: Completed {steps_completed} steps in this cycle!")
    
    return steps_completed > 0


def process_frame_task(task, token, status_cache=None):
    """Process a single frame record to its next step(s) - chain when possible."""
    frame_id = task["id"]
    current_status = task["current_status"]
    record_data = task["record_data"]
    original_status = current_status  # Remember the original status

    # Only log significant events, not routine processing

    # Special case: Force Resume for frames - bypass parent dependency checks
    if current_status == "Force Resume":
        tprint(f"🚀 FRAME FORCE RESUME: {frame_id}")
        
        # Force Resume means regenerate caption and audio  
        tprint(f"✅ {frame_id}: Force Resume - will regenerate caption and audio")
        # Skip parent dependency check and proceed directly to processing
    else:
        # Check parent dependency first (normal flow) - USE STATUS CACHE
        parent_id = record_data.get(FIELD_MAPPING["frame_parent_id"])
        if parent_id:
            # Use status cache if available, fall back to individual API call
            if status_cache:
                is_ready, parent_status = status_cache.is_parent_ready_for_frames(parent_id)
                
                if parent_status == "CACHE_MISS":
                    # Cache miss - we'll handle this in batch later
                    tprint(f"⏳ {frame_id}: Parent {parent_id} status not cached - skipping this cycle")
                    return False
                
                if parent_status.startswith("TERMINAL_SUCCESS:"):
                    actual_status = parent_status.split(":", 1)[1]
                    tprint(f"✅ {frame_id}: Parent {parent_id} reached '{actual_status}' - frame processing complete")
                    return True
                
                if not is_ready:
                    # Don't spam logs - only log first check per cycle
                    if not hasattr(process_frame_task, '_logged_waiting'):
                        process_frame_task._logged_waiting = set()
                    
                    log_key = f"{frame_id}:{parent_id}:{parent_status}"
                    if log_key not in process_frame_task._logged_waiting:
                        tprint(f"⏳ {frame_id}: Parent {parent_id} still at '{parent_status}' - waiting")
                        process_frame_task._logged_waiting.add(log_key)
                    
                    return False
            else:
                # Fallback to original individual API call logic
                try:
                    parent_response = requests.post(
                        config.url("layouts/FOOTAGE/_find"),
                        headers=config.api_headers(token),
                        json={"query": [{"INFO_FTG_ID": parent_id}], "limit": 1},
                        verify=False,
                        timeout=10
                    )

                    if parent_response.status_code == 200:
                        parent_records = parent_response.json()['response']['data']
                        if parent_records:
                            parent_status = parent_records[0]['fieldData'].get(FIELD_MAPPING["status"], "Unknown")

                            # If parent has reached terminal success states, frame processing is complete
                            parent_terminal_success_statuses = [
                                "8 - Applying Tags",  # Parent fully completed - frames definitely done
                                "9 - Complete"
                                # NOTE: "7 - Generating Embeddings" removed - frames may still need to reach "4 - Audio Transcribed"
                            ]
                            
                            if parent_status in parent_terminal_success_statuses:
                                tprint(f"✅ {frame_id}: Parent {parent_id} reached '{parent_status}' - frame processing complete")
                                return True  # Success - parent completed the workflow
                            
                            parent_ready_statuses = [
                                "4 - Scraping URL",
                                "5 - Processing Frame Info",
                                "6 - Generating Description",
                                "7 - Generating Embeddings",
                                "Force Resume"  # Allow frames to process when parent is force resuming
                            ]

                            if parent_status not in parent_ready_statuses:
                                tprint(f"⏳ {frame_id}: Parent {parent_id} still at '{parent_status}' - waiting")
                                return False

                except Exception as e:
                    tprint(f"⚠️ {frame_id}: Could not check parent status: {e}")

    # Track steps completed for chaining
    steps_completed = 0
    max_steps_per_cycle = 4  # Frames have fewer steps
    
    while steps_completed < max_steps_per_cycle:
        # Standard frame progression - can chain together
        status_map = {
            "1 - Pending Thumbnail": ("frames_generate_thumbnails.py", "2 - Thumbnail Complete"),
            "2 - Thumbnail Complete": ("frames_generate_captions.py", "3 - Caption Generated"),
            "3 - Caption Generated": ("frames_transcribe_audio.py", "4 - Audio Transcribed"),
            "Force Resume": ("frames_generate_captions.py", "3 - Caption Generated"),  # Force Resume → Caption → Audio
        }

        if current_status in status_map:
            script, next_status = status_map[current_status]
            success = run_frame_script(frame_id, script, next_status, token, task["record_id"])
            if success:
                steps_completed += 1
                current_status = next_status
                if next_status != "4 - Audio Transcribed":  # Don't chain beyond final step
                    tprint(f"⚡ {frame_id}: Chaining to next step → {next_status}")
                    continue
                else:
                    break  # Reached final frame step
            else:
                break
        else:
            # No more steps to process
            break
    
    # FIX: For Force Resume frames that completed processing, ensure final status is properly set
    if original_status == "Force Resume" and steps_completed > 0 and current_status == "4 - Audio Transcribed":
        try:
            # Explicitly update the frame status to terminal state to prevent re-processing
            payload = {"fieldData": {FIELD_MAPPING["frame_status"]: "4 - Audio Transcribed"}}
            response = requests.patch(
                config.url(f"layouts/FRAMES/records/{task['record_id']}"),
                headers=config.api_headers(token),
                json=payload,
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            tprint(f"🎯 {frame_id}: Force Resume completed - status finalized to '4 - Audio Transcribed'")
        except Exception as e:
            tprint(f"⚠️ {frame_id}: Failed to finalize status: {e}")
    
    if steps_completed > 1:
        tprint(f"🚀 {frame_id}: Completed {steps_completed} steps in this cycle!")
    
    return steps_completed > 0

def run_footage_script(footage_id, script_name, next_status, final_status, token, record_id):
    """Run a footage script and update status."""
    try:
        # Update status immediately
        tprint(f"🔄 {footage_id}: Updating status to '{next_status}'")
        update_status(record_id, token, next_status)
        
        # Run script
        tprint(f"🚀 {footage_id}: Running {script_name}")
        success, error_msg = run_single_script(script_name, footage_id, token, 300)
        
        if success:
            tprint(f"✅ {footage_id}: {script_name} completed successfully")
            
            # Update to final status if specified (for step 6)
            if final_status:
                tprint(f"🔄 {footage_id}: Script completed, updating to final status '{final_status}'")
                update_status(record_id, token, final_status)
                
                # NOTE: We do NOT update frame statuses beyond "4 - Audio Transcribed"
                # PSOS scripts will handle frame progression from here
                tprint(f"✅ {footage_id}: Successfully moved to {final_status} (frames remain at their current status for PSOS)")
            else:
                tprint(f"✅ {footage_id}: Script completed, no final status to set")
            
            return True
        else:
            tprint(f"❌ {footage_id}: {script_name} failed: {error_msg}")
            return False
            
    except Exception as e:
        tprint(f"❌ {footage_id}: Exception in {script_name}: {e}")
        return False

def run_frame_script(frame_id, script_name, next_status, token, record_id):
    """Run a frame script and update status."""
    try:
        # Update status immediately
        payload = {"fieldData": {FIELD_MAPPING["frame_status"]: next_status}}
        response = requests.patch(
            config.url(f"layouts/FRAMES/records/{record_id}"),
            headers=config.api_headers(token),
            json=payload,
            verify=False,
            timeout=30
        )
        response.raise_for_status()
        
        # Run script
        success, error_msg = run_single_script(script_name, frame_id, token, 300)
        
        if success:
            tprint(f"✅ {frame_id}: {script_name} completed")
            return True
        else:
            tprint(f"❌ {frame_id}: {script_name} failed: {error_msg}")
            return False
            
    except Exception as e:
        tprint(f"❌ {frame_id}: Exception in {script_name}: {e}")
        return False

if __name__ == "__main__":
    try:
        # Mount required network volumes at startup
        tprint(f"🔧 Mounting network volumes...")
        
        try:
            # Mount footage volume
            if config.mount_volume("footage"):
                tprint(f"✅ Footage volume (FTG_E2E) mounted successfully")
            else:
                tprint(f"⚠️ Failed to mount footage volume (FTG_E2E)")
            
            # Mount stills volume  
            if config.mount_volume("stills"):
                tprint(f"✅ Stills volume (6 E2E) mounted successfully")
            else:
                tprint(f"⚠️ Failed to mount stills volume (6 E2E)")
                
        except Exception as e:
            tprint(f"❌ Error during volume mounting: {e}")
        
        token = config.get_token()
        
        # Run polling workflow
        # Default: 1 hour duration, 10-second intervals for responsive progression
        poll_duration = int(os.getenv('POLL_DURATION', 3600))  # 1 hour default
        poll_interval = int(os.getenv('POLL_INTERVAL', 30))    # 30 seconds default to prevent resource overload
        
        results = run_polling_workflow(token, poll_duration, poll_interval)
        
        # Exit successfully
        tprint(f"✅ Polling workflow completed successfully")
        sys.exit(0)
        
    except KeyboardInterrupt:
        tprint(f"🛑 Polling workflow interrupted by user")
        sys.exit(0)
    except Exception as e:
        tprint(f"❌ Critical error in polling workflow: {e}")
        traceback.print_exc()
        sys.exit(1) 