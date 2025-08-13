#!/usr/bin/env python3
"""
Modernized Footage AutoLog Run-All Workflow Controller

This script provides queued processing of footage IDs with modern API protection:
1. Accepts payload IDs through arguments or auto-discovers pending items
2. Uses StatusCache and BatchStatusChecker for API efficiency
3. Implements step 6 as final step (stops at "7 - Generating Embeddings")
4. Handles LF items and Force Resume properly
5. Conservative concurrency to prevent FileMaker API overload

Usage:
  python3 footage_autolog_00_run_all.py                    # Auto-discovery mode
  python3 footage_autolog_00_run_all.py '["FTG123", ...]'  # Payload mode
  python3 footage_autolog_00_run_all.py FTG123             # Single item mode
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

def get_timestamp():
    """Get current timestamp string."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

# Accept payload IDs through arguments or auto-discover pending items
__ARGS__ = ["footage_ids_json"]  # Optional JSON array of footage IDs

JOBS_DIR = Path(__file__).resolve().parent  # Same directory as this script

# Debug flag
DEBUG_MODE = os.getenv('AUTOLOG_DEBUG', 'false').lower() == 'true'

# Field mappings for FOOTAGE and FRAMES layouts
FIELD_MAPPING = {
    # FOOTAGE Layout Fields
    "footage_id": "INFO_FTG_ID",
    "status": "AutoLog_Status", 
    "filepath": "SPECS_Filepath_Server",
    "metadata": "INFO_Metadata",
    "url": "SPECS_URL",
    "dev_console": "AI_DevConsole",  # Assuming this exists or will be added
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

# Modern workflow steps (step 6 is final - workflow stops at "7 - Generating Embeddings")
WORKFLOW_STEPS = [
    {
        "step": 1,
        "status_before": "0 - Pending File Info",
        "status_after": "1 - File Info Complete",
        "script": "footage_autolog_01_get_file_info.py",
        "description": "Get File Info",
        "timeout": 300
    },
    {
        "step": 2,
        "status_before": "1 - File Info Complete",
        "status_after": "2 - Thumbnails Complete",
        "script": "footage_autolog_02_generate_thumbnails.py",
        "description": "Generate Footage Thumbnail",
        "timeout": 300
    },
    {
        "step": 3,
        "status_before": "2 - Thumbnails Complete",
        "status_after": "3 - Creating Frames",
        "script": "footage_autolog_03_create_frames.py",
        "description": "Create Frame Records",
        "timeout": 300
    },
    {
        "step": 4,
        "status_before": "3 - Creating Frames",
        "status_after": "4 - Scraping URL",
        "script": "footage_autolog_04_scrape_url.py",
        "description": "Scrape URL",
        "conditional": True,  # Only run if URL exists
        "timeout": 300
    },
    {
        "step": 5,
        "status_before": ["4 - Scraping URL", "3 - Creating Frames"],  # Multiple valid states
        "status_after": "5 - Processing Frame Info",
        "script": "footage_autolog_05_process_frames.py",
        "description": "Process Frame Info",
        "metadata_evaluation": True,  # Evaluate metadata quality
        "timeout": 1800  # Longer timeout for frame processing
    },
    {
        "step": 6,
        "status_before": "5 - Processing Frame Info",
        "status_after": "6 - Generating Description",  # Status while working
        "script": "footage_autolog_06_generate_description.py",
        "description": "Generate Description",
        "final_status": "7 - Generating Embeddings",  # Status after completion (FINAL)
        "requires_frame_completion": True,
        "timeout": 600
    }
]

# Terminal states (workflow complete)
TERMINAL_STATES = [
    "7 - Generating Embeddings",  # Step 6 completion (FINAL)
    "8 - Applying Tags",          # PSOS handled
    "9 - Complete",               # PSOS handled  
    "Awaiting User Input"         # User intervention required
]

# Processable pickup statuses
PICKUP_STATUSES = [
    "0 - Pending File Info",     # Standard start
    "1 - File Info Complete",    # Resume from step 2
    "2 - Thumbnails Complete",   # Resume from step 3
    "3 - Creating Frames",       # Resume from step 4
    "4 - Scraping URL",          # Resume from step 5
    "5 - Processing Frame Info", # Resume from step 6
    "Force Resume"               # User-triggered bypass
]

class ModernProcessingQueue:
    """Modern queued processing with API protection."""
    
    def __init__(self, token, max_concurrent=5, batch_size=10):
        self.token = token
        self.max_concurrent = max_concurrent  # Conservative limit
        self.batch_size = batch_size
        self.status_cache = StatusCache(cache_duration_seconds=60)  # Longer cache for run-all
        self.batch_checker = BatchStatusChecker(token)
        
        # Statistics
        self.stats = {
            "total_items": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "results": [],
            "start_time": datetime.now().isoformat(),
            "end_time": None
        }

def validate_footage_ids(footage_ids, token, max_retries=3):
    """Validate that footage IDs exist in FileMaker."""
    if not footage_ids:
        return []
    
    current_token = token
    
    for attempt in range(max_retries):
        try:
            # Use batch checker for efficient validation
            batch_checker = BatchStatusChecker(current_token)
            status_map = batch_checker.batch_check_footage_statuses(set(footage_ids))
            
            valid_ids = list(status_map.keys())
            missing_ids = [fid for fid in footage_ids if fid not in valid_ids]
            
            tprint(f"📋 Validation: {len(valid_ids)}/{len(footage_ids)} IDs found in FileMaker")
            if missing_ids:
                tprint(f"⚠️ Missing IDs: {missing_ids[:5]}{'...' if len(missing_ids) > 5 else ''}")
            
            return valid_ids
            
        except Exception as e:
            tprint(f"⚠️ Validation attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                current_token = config.get_token()
                time.sleep(2 ** attempt)
                continue
    
    tprint(f"❌ Failed to validate footage IDs after {max_retries} attempts")
    return []

def handle_lf_items(footage_ids, token):
    """Automatically set LF items to Awaiting User Input and filter them out."""
    lf_items = [fid for fid in footage_ids if fid.startswith("LF")]
    
    if lf_items:
        tprint(f"🔄 Found {len(lf_items)} LF items - setting to 'Awaiting User Input'")
        
        # Batch update LF items to awaiting user input
        for lf_id in lf_items:
            try:
                record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={lf_id}"})
                if record_id:
                    update_status(record_id, token, "Awaiting User Input")
                    update_frame_statuses_for_footage(lf_id, token, "Awaiting User Input")
                    tprint(f"  -> ✅ {lf_id}: Set to Awaiting User Input")
                else:
                    tprint(f"  -> ❌ {lf_id}: Record not found")
            except Exception as e:
                tprint(f"  -> ❌ {lf_id}: Error - {e}")
    
    # Return non-LF items for processing
    non_lf_items = [fid for fid in footage_ids if not fid.startswith("LF")]
    tprint(f"📋 Filtering: {len(non_lf_items)} non-LF items ready for processing")
    
    return non_lf_items

def combine_metadata(record_data):
    """Combine all available metadata into a single text for evaluation."""
    metadata_parts = []
    
    # Add technical metadata from dev_FFMPEG field
    ffmpeg_data = record_data.get('dev_FFMPEG', '')
    if ffmpeg_data:
        metadata_parts.append(f"Technical Metadata:\n{ffmpeg_data}")
    
    # Add INFO_Metadata field
    info_metadata = record_data.get(FIELD_MAPPING["metadata"], '')
    if info_metadata:
        metadata_parts.append(f"EXIF/Technical Info:\n{info_metadata}")
    
    # Add description if available
    description = record_data.get(FIELD_MAPPING["description"], '')
    if description:
        metadata_parts.append(f"Description:\n{description}")
    
    # Add source information
    source = record_data.get(FIELD_MAPPING["source"], '')
    if source:
        metadata_parts.append(f"Source:\n{source}")
    
    # Add archival ID
    archival_id = record_data.get(FIELD_MAPPING["archival_id"], '')
    if archival_id:
        metadata_parts.append(f"Archival ID:\n{archival_id}")
    
    # Add URL (for reference)
    url = record_data.get(FIELD_MAPPING["url"], '')
    if url:
        metadata_parts.append(f"Source URL:\n{url}")
    
    return "\n\n".join(metadata_parts)

def evaluate_metadata_quality(record_data, token, record_id=None):
    """Evaluate metadata quality using local analysis with simplified 40-point scale."""
    try:
        # Combine all metadata
        combined_metadata = combine_metadata(record_data)
        
        if not combined_metadata.strip():
            print(f"  -> No metadata available for evaluation")
            console_msg = "Metadata Evaluation: NO METADATA AVAILABLE - Cannot evaluate quality"
            if record_id:
                write_to_dev_console(record_id, token, console_msg)
            return False
        
        print(f"  -> Evaluating combined metadata ({len(combined_metadata)} chars)")
        
        # Use simplified local evaluator (no URL-aware logic needed)
        evaluation = evaluate_metadata_local(combined_metadata)
        
        is_sufficient = evaluation.get("sufficient", False)
        reason = evaluation.get("reason", "No reason provided")
        confidence = evaluation.get("confidence", "medium")
        score = evaluation.get("score", 0.0)
        
        print(f"  -> Metadata Evaluation: {'GOOD' if is_sufficient else 'BAD'}")
        print(f"     Score: {score:.0f}/40")
        print(f"     Reason: {reason}")
        print(f"     Confidence: {confidence}")
        
        # Write evaluation results to AI_DevConsole
        if record_id:
            console_msg = f"Metadata Evaluation: {'✅ PASSED' if is_sufficient else '❌ FAILED'}\n"
            console_msg += f"Score: {score:.0f}/50 (Threshold: 10+)\n"
            console_msg += f"Confidence: {confidence}\n"
            console_msg += f"Details: {reason}"
            write_to_dev_console(record_id, token, console_msg)
        
        return is_sufficient
        
    except Exception as e:
        print(f"  -> ERROR in metadata evaluation: {e}")
        
        # Write error to console
        if record_id:
            console_msg = f"Metadata Evaluation: ❌ ERROR\nException: {str(e)}\nUsing fallback evaluation..."
            write_to_dev_console(record_id, token, console_msg)
        
        # Fall back to basic heuristics
        combined_metadata = combine_metadata(record_data)
        
        # Simple fallback: 30+ characters is reasonable (more generous)
        if len(combined_metadata) > 30:
            print(f"  -> Fallback: Using basic length check - GOOD")
            if record_id:
                fallback_msg = f"Fallback Result: ✅ PASSED (length check)\nCombined metadata: {len(combined_metadata)} chars (>30 threshold)"
                write_to_dev_console(record_id, token, fallback_msg)
            return True
        else:
            print(f"  -> Fallback: Using basic length check - BAD")
            if record_id:
                fallback_msg = f"Fallback Result: ❌ FAILED (length check)\nCombined metadata: {len(combined_metadata)} chars (≤30 threshold)"
                write_to_dev_console(record_id, token, fallback_msg)
            return False

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
            # 1. Status is "4 - Audio Transcribed" or higher, OR
            # 2. Has caption content (caption step complete)
            if (frame_status in ["4 - Audio Transcribed", "5 - Generating Embeddings", "6 - Embeddings Complete"] or
                caption):  # Has caption (caption step done)
                completed_frames += 1
        
        if completed_frames == total_frames:
            return True, f"All {total_frames} frames ready for Step 6"
        else:
            return False, f"{completed_frames}/{total_frames} frames ready"
            
    except Exception as e:
        tprint(f"⚠️ Error checking frame completion: {e}")
        return False, f"Error: {e}"

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

def format_error_message(footage_id, step_name, error_details, error_type="Processing Error"):
    """Format error messages for the AI_DevConsole field in a user-friendly way."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Clean up error details
    clean_error = error_details.strip()
    if clean_error.startswith("Error:"):
        clean_error = clean_error[6:].strip()
    if clean_error.startswith("FATAL ERROR:"):
        clean_error = clean_error[12:].strip()
    
    # Generous truncation limit for FileMaker
    if len(clean_error) > 1000:
        clean_error = clean_error[:997] + "..."
    
    return f"[{timestamp}] {error_type} - {step_name}\nFootage ID: {footage_id}\nIssue: {clean_error}"

def write_footage_error_to_console(footage_id, token, error_message, max_retries=3):
    """Write error message to the AI_DevConsole field for a footage record."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            # First, find the footage record
            record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
            if not record_id:
                print(f"  -> Could not find footage record for {footage_id}")
                return False
            
            # Get current console content
            response = requests.get(
                config.url(f"layouts/FOOTAGE/records/{record_id}"),
                headers=config.api_headers(current_token),
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            current_data = response.json()['response']['data'][0]['fieldData']
            current_console = current_data.get(FIELD_MAPPING["dev_console"], "")
            
            # Append new error message
            if current_console:
                new_console = current_console + "\n\n" + error_message
            else:
                new_console = error_message
            
            # Truncate if too long (FileMaker field limit)
            if len(new_console) > 1000:
                new_console = new_console[-1000:]
            
            # Update the console field
            payload = {"fieldData": {FIELD_MAPPING["dev_console"]: new_console}}
            update_response = requests.patch(
                config.url(f"layouts/FOOTAGE/records/{record_id}"),
                headers=config.api_headers(current_token),
                json=payload,
                verify=False,
                timeout=30
            )
            
            if update_response.status_code == 401:
                current_token = config.get_token()
                continue
            
            update_response.raise_for_status()
            print(f"  -> ✅ Error written to AI_DevConsole for {footage_id}")
            return True
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout writing to AI_DevConsole (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error writing to AI_DevConsole (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except Exception as e:
            print(f"  -> Error writing to AI_DevConsole (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to write error to AI_DevConsole after {max_retries} attempts")
    return False

def write_error_to_console(record_id, token, error_message, max_retries=3):
    """Safely write error message to the AI_DevConsole field with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            payload = {"fieldData": {FIELD_MAPPING["dev_console"]: error_message}}
            response = requests.patch(
                config.url(f"layouts/FOOTAGE/records/{record_id}"), 
                headers=config.api_headers(current_token), 
                json=payload, 
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                print(f"  -> Token expired during error console write, refreshing token (attempt {attempt + 1}/{max_retries})")
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return True
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout writing to error console (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error writing to error console (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except Exception as e:
            print(f"  -> Error writing to error console (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to write error to console after {max_retries} attempts")
    return False

def update_status(record_id, token, new_status, max_retries=3):
    """Update the AutoLog_Status field with retry logic."""
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
                print(f"  -> Token expired during status update, refreshing token (attempt {attempt + 1}/{max_retries})")
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return True
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout updating status (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error updating status (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except Exception as e:
            print(f"  -> Error updating status (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to update status to '{new_status}' after {max_retries} attempts")
    return False

def batch_update_statuses(token, updates):
    """Update multiple record statuses in batch to reduce API overhead.
    
    Args:
        token: FileMaker auth token
        updates: List of dicts with keys: record_id, layout, status
    """
    if not updates:
        return True
    
    print(f"📊 Batch updating {len(updates)} record statuses...")
    successful_updates = 0
    
    # Group updates by layout for efficiency
    layout_groups = {}
    for update in updates:
        layout = update['layout']
        if layout not in layout_groups:
            layout_groups[layout] = []
        layout_groups[layout].append(update)
    
    for layout, layout_updates in layout_groups.items():
        print(f"  -> Updating {len(layout_updates)} records in {layout} layout")
        
        for update in layout_updates:
            try:
                record_id = update['record_id']
                new_status = update['status']
                
                if layout == "FOOTAGE":
                    status_field = FIELD_MAPPING["status"]
                elif layout == "FRAMES":
                    status_field = FIELD_MAPPING["frame_status"]
                else:
                    print(f"    -> WARNING: Unknown layout {layout}")
                    continue
                
                payload = {"fieldData": {status_field: new_status}}
                response = requests.patch(
                    config.url(f"layouts/{layout}/records/{record_id}"),
                    headers=config.api_headers(token),
                    json=payload,
                    verify=False,
                    timeout=15  # Shorter timeout for batch operations
                )
                
                if response.status_code == 200:
                    successful_updates += 1
                else:
                    print(f"    -> WARNING: Failed to update {record_id}: {response.status_code}")
                    
            except Exception as e:
                print(f"    -> WARNING: Exception updating {update.get('record_id', 'unknown')}: {e}")
                continue
    
    print(f"📊 Batch update complete: {successful_updates}/{len(updates)} successful")
    return successful_updates > 0

def get_current_record_data(record_id, token, max_retries=3):
    """Get current record data from FileMaker with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                config.url(f"layouts/FOOTAGE/records/{record_id}"), 
                headers=config.api_headers(current_token), 
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                print(f"  -> Token expired, refreshing token (attempt {attempt + 1}/{max_retries})")
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return response.json()['response']['data'][0], current_token
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout getting record data (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error getting record data (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except Exception as e:
            print(f"  -> Error getting record data (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to get record data after {max_retries} attempts")
    return None, current_token

def wait_for_frame_completion(footage_id, token, max_wait_time=600, check_interval=8):
    """Wait for all frames to complete processing with robust content verification."""
    print(f"  -> Waiting for frame completion for {footage_id} (max {max_wait_time}s)")
    start_time = time.time()
    check_count = 0
    
    while time.time() - start_time < max_wait_time:
        check_count += 1
        try:
            # Check frame statuses
            response = requests.post(
                config.url("layouts/FRAMES/_find"),
                headers=config.api_headers(token),
                json={
                    "query": [{"FRAMES_ParentID": footage_id}],
                    "limit": 100
                },
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                frame_records = response.json()['response']['data']
                if not frame_records:
                    print(f"  -> No frames found for {footage_id}")
                    return False
                
                # Robust verification: check both status AND content
                total_frames = len(frame_records)
                incomplete_frames = []
                
                # Show incomplete frames if any (every 4th check to avoid spam)
                if incomplete_frames and check_count % 4 == 0:
                    print(f"  -> ⚠️ Incomplete frames: {', '.join(incomplete_frames[:3])}{'...' if len(incomplete_frames) > 3 else ''}")
                
                # Success condition: ALL frames are ready (either have content OR correct status)
                # A frame is ready if it has status "4 - Audio Transcribed" or higher, OR has caption content
                # Note: Not all frames will have audio, so we don't require transcripts
                ready_frames = 0
                for frame_record in frame_records:
                    frame_id = frame_record['fieldData'].get('FRAMES_ID', 'Unknown')
                    status = frame_record['fieldData'].get('FRAMES_Status', 'Unknown')
                    caption = frame_record['fieldData'].get('FRAMES_Caption', '').strip()
                    transcript = frame_record['fieldData'].get('FRAMES_Transcript', '').strip()
                    
                    # Frame is ready if:
                    # 1. Status is "4 - Audio Transcribed" or higher (audio step complete, regardless of transcript content)
                    # 2. OR has caption content (caption step complete)
                    # Note: Status "4 - Audio Transcribed" means we've checked for audio, even if none was found
                    if (status in ['4 - Audio Transcribed', '5 - Generating Embeddings', '6 - Embeddings Complete'] or 
                        caption):  # Has caption (caption step done)
                        ready_frames += 1
                    else:
                        incomplete_frames.append(f"{frame_id}:{status} (caption:{len(caption)},transcript:{len(transcript)})")
                
                print(f"  -> Frame check #{check_count}: {ready_frames}/{total_frames} ready frames")
                
                # Show incomplete frames if any (every 4th check to avoid spam)
                if incomplete_frames and check_count % 4 == 0:
                    print(f"  -> ⚠️ Incomplete frames: {', '.join(incomplete_frames[:3])}{'...' if len(incomplete_frames) > 3 else ''}")
                
                # Success condition: ALL frames are ready
                if ready_frames == total_frames:
                    print(f"  -> ✅ All {total_frames} frames are ready for step 6")
                    return True
                elif ready_frames > 0:
                    print(f"  -> ⏳ {ready_frames}/{total_frames} frames ready, waiting...")
                else:
                    print(f"  -> ⏳ No frames ready yet, waiting...")
                
                # Wait before next check
                time.sleep(check_interval)
            else:
                print(f"  -> Error checking frame status: {response.status_code}")
                time.sleep(check_interval)
                
        except Exception as e:
            print(f"  -> Error checking frame completion: {e}")
            time.sleep(check_interval)
    
    print(f"  -> ⏰ Timeout waiting for frame completion after {max_wait_time}s")
    return False



def get_detailed_frame_status(footage_id, token):
    """Get detailed status information for all frames of a footage record."""
    try:
        response = requests.post(
            config.url("layouts/FRAMES/_find"),
            headers=config.api_headers(token),
            json={
                "query": [{"FRAMES_ParentID": footage_id}],
                "limit": 100
            },
            verify=False,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  -> Error getting frames: {response.status_code}")
            return None
        
        frame_records = response.json()['response']['data']
        if not frame_records:
            print(f"  -> No frames found for {footage_id}")
            return None
        
        print(f"  -> 📊 Detailed frame status for {footage_id}:")
        print(f"     Total frames: {len(frame_records)}")
        
        status_summary = {}
        content_summary = {"complete": 0, "incomplete": 0, "missing_caption": 0, "missing_transcript": 0}
        
        for frame_record in frame_records:
            frame_id = frame_record['fieldData'].get('FRAME_ID', 'Unknown')
            status = frame_record['fieldData'].get('FRAMES_Status', 'Unknown')
            caption = frame_record['fieldData'].get('FRAMES_Caption', '').strip()
            transcript = frame_record['fieldData'].get('FRAMES_Transcript', '').strip()
            
            # Count by status
            status_summary[status] = status_summary.get(status, 0) + 1
            
            # Count by content completeness
            if caption and transcript:
                content_summary["complete"] += 1
            else:
                content_summary["incomplete"] += 1
                if not caption:
                    content_summary["missing_caption"] += 1
                if not transcript:
                    content_summary["missing_transcript"] += 1
        
        # Print status summary
        print(f"     Status breakdown:")
        for status, count in sorted(status_summary.items()):
            print(f"       {status}: {count}")
        
        # Print content summary
        print(f"     Content breakdown:")
        print(f"       Complete (caption + transcript): {content_summary['complete']}")
        print(f"       Incomplete: {content_summary['incomplete']}")
        if content_summary['missing_caption'] > 0:
            print(f"       Missing captions: {content_summary['missing_caption']}")
        if content_summary['missing_transcript'] > 0:
            print(f"       Missing transcripts: {content_summary['missing_transcript']}")
        
        return {
            "total_frames": len(frame_records),
            "status_summary": status_summary,
            "content_summary": content_summary
        }
        
    except Exception as e:
        print(f"  -> ❌ Error getting detailed frame status: {e}")
        return None

def update_frame_statuses_for_footage(footage_id, token, new_status, max_retries=3):
    """Update status for all frame records belonging to a specific footage parent."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            print(f"  -> Updating frame statuses to '{new_status}' for footage {footage_id}")
            
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
                print(f"  -> No frame records found for footage {footage_id}")
                return True
            
            response.raise_for_status()
            records = response.json()['response']['data']
            
            if not records:
                print(f"  -> No frame records found for footage {footage_id}")
                return True
            
            print(f"  -> Found {len(records)} frame records to update")
            
            # Update each frame record
            updated_count = 0
            for record in records:
                frame_record_id = record['recordId']
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
                        # Retry this frame
                        frame_response = requests.patch(
                            config.url(f"layouts/FRAMES/records/{frame_record_id}"),
                            headers=config.api_headers(current_token),
                            json=payload,
                            verify=False,
                            timeout=30
                        )
                    
                    frame_response.raise_for_status()
                    updated_count += 1
                    
                except Exception as e:
                    print(f"  -> Warning: Failed to update frame {frame_record_id}: {e}")
                    continue
            
            print(f"  -> Successfully updated {updated_count}/{len(records)} frame records")
            return True
            
        except requests.exceptions.Timeout:
            print(f"  -> Timeout updating frame statuses (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except requests.exceptions.ConnectionError:
            print(f"  -> Connection error updating frame statuses (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
                
        except Exception as e:
            print(f"  -> Error updating frame statuses (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    print(f"  -> Failed to update frame statuses after {max_retries} attempts")
    return False

def run_workflow_step(step, footage_id, record_id, token):
    """Run a single workflow step with retry logic."""
    step_num = step["step_num"]
    script_name = step["script"]
    description = step["description"]
    is_final_step = step.get("final_status") is not None  # Check if this has a final_status
    
    tprint(f"--- Step {step_num}: {description} ---")
    tprint(f"  -> Processing footage_id: {footage_id}")
    
    # Handle dynamic status checking for step 5 (could come from step 3, 4, or user-triggered)
    if step_num == 5 and step.get("status_before") is None:
        # Get current record data to check actual status
        record_data, token = get_current_record_data(record_id, token)
        if record_data:
            current_status = record_data['fieldData'].get(FIELD_MAPPING["status"], '')
            print(f"  -> Current status: {current_status}")
            # Step 5 can proceed from "3 - Creating Frames", "4 - Scraping URL", or user-triggered "5 - Processing Frame Info"
            valid_statuses = ["3 - Creating Frames", "4 - Scraping URL", "5 - Processing Frame Info"]
            if current_status not in valid_statuses:
                print(f"  -> WARNING: Unexpected status '{current_status}' for step 5")
        else:
            print(f"  -> WARNING: Could not get record data for status check")
        
        # For step 5, only update status if we're NOT already at "5 - Processing Frame Info"
        if not is_final_step and step.get("status_after"):
            if current_status != "5 - Processing Frame Info":
                print(f"  -> Updating status to: {step['status_after']} (before running step)")
                if not update_status(record_id, token, step["status_after"]):
                    print(f"  -> WARNING: Failed to update status to '{step['status_after']}', but continuing workflow")
                else:
                    print(f"  -> Status updated successfully")
            else:
                print(f"  -> Status already at '{current_status}' - continuing with step execution")
    else:
        # For non-final steps, update to the "after" status BEFORE running the script
        if not is_final_step and step.get("status_after"):
            print(f"  -> Updating status to: {step['status_after']} (before running step)")
            if not update_status(record_id, token, step["status_after"]):
                print(f"  -> WARNING: Failed to update status to '{step['status_after']}', but continuing workflow")
            else:
                print(f"  -> Status updated successfully")
        elif is_final_step:
            print(f"  -> Final step - will update to '{step['status_after']}' after completion")
    
    # Handle conditional steps with simple URL check (always scrape if URL exists)
    if step.get("conditional") and step.get("check_url_only"):
        print(f"  -> Checking URL availability for conditional URL scraping")
        # Get current record data to check URL availability
        record_data, token = get_current_record_data(record_id, token)
        if not record_data:
            print(f"  -> WARNING: Could not get record data for {footage_id}")
            print(f"  -> Assuming no URL and continuing workflow")
            return True
        
        # Check URL availability - always scrape if URL exists
        url = record_data['fieldData'].get(FIELD_MAPPING["url"], '')
        has_url = bool(url and url.strip())
        
        if has_url:
            print(f"  -> URL found for {footage_id}: {url}")
            print(f"  -> Proceeding with URL scraping (always scrape when URL is available)")
            # Continue with URL scraping
        else:
            print(f"  -> No URL found for {footage_id}")
            print(f"  -> Skipping URL scraping (no URL available)")
            # Skip URL scraping when no URL is available
            current_status = record_data['fieldData'].get(FIELD_MAPPING['status'], 'Unknown')
            print(f"  -> Status remains: {current_status} (URL scraping skipped, continuing workflow)")
            return True
    
    # Handle metadata evaluation checkpoint (after URL scraping)
    elif step.get("evaluate_metadata"):
        print(f"  -> Metadata evaluation checkpoint - evaluating quality after URL scraping")
        # Get current record data to evaluate final metadata quality
        record_data, token = get_current_record_data(record_id, token)
        if not record_data:
            print(f"  -> WARNING: Could not get record data for {footage_id}")
            print(f"  -> Assuming metadata is insufficient and halting workflow")
            if not update_status(record_id, token, "Awaiting User Input"):
                print(f"  -> ERROR: Failed to update status to 'Awaiting User Input'")
            return False
        
        # Evaluate final metadata quality (after any URL scraping)
        metadata_quality_good = evaluate_metadata_quality(record_data['fieldData'], token, record_id)
        
        if metadata_quality_good:
            print(f"  -> GOOD: Metadata quality is sufficient, proceeding with frame processing for {footage_id}")
            # Continue with frame processing
        else:
            print(f"  -> BAD: Metadata quality is insufficient, halting workflow for {footage_id}")
            print(f"  -> Setting status to 'Awaiting User Input' for manual intervention")
            if not update_status(record_id, token, "Awaiting User Input"):
                print(f"  -> ERROR: Failed to update status to 'Awaiting User Input'")
            return False  # Stop workflow - needs user intervention
    
    # Run the script with retry logic
    script_path = JOBS_DIR / script_name
    
    if not script_path.exists():
        print(f"  -> FATAL ERROR: Script not found: {script_path}")
        error_msg = format_error_message(
            footage_id,
            description,
            f"Script not found: {script_name}",
            "Configuration Error"
        )
        write_error_to_console(record_id, token, error_msg)
        return False
    
    # Determine timeout based on step type
    if step_num == 5:  # Frame processing
        # Get video duration for timeout estimation
        try:
            record_data, token = get_current_record_data(record_id, token)
            if record_data:
                duration_str = record_data['fieldData'].get('SPECS_File_Duration_Timecode', '')
                if duration_str:
                    # Parse duration and estimate timeout
                    duration_parts = duration_str.split(':')
                    if len(duration_parts) == 3:
                        hours, minutes, seconds = map(int, duration_parts)
                        total_seconds = hours * 3600 + minutes * 60 + seconds
                    elif len(duration_parts) == 2:
                        minutes, seconds = map(int, duration_parts)
                        total_seconds = minutes * 60 + seconds
                    else:
                        total_seconds = 0
                    
                    # Calculate timeout: base + 2x video duration + overhead
                    timeout = 300 + (total_seconds * 2) + 300  # 5min base + 2x duration + 5min overhead
                    timeout = max(900, min(timeout, 3600))  # 15min to 1hour
                    print(f"  -> 📹 Video duration: {duration_str} -> timeout: {timeout}s")
                else:
                    timeout = 1800  # Default 30 minutes
            else:
                timeout = 1800
        except:
            timeout = 1800
    else:
        timeout = 300  # Reduced to 5 minutes for other steps (was 10)
    
    # Retry logic for step execution
    max_retries = 3
    for attempt in range(max_retries):
        try:
            tprint(f"  -> Running script: {script_name} for {footage_id} (attempt {attempt + 1}/{max_retries})")
            tprint(f"🔄 Initiating subprocess: {description} (Step {step_num}) on ID {footage_id}")
            
            # Debug mode for real-time output
            if DEBUG_MODE:
                tprint(f"  -> DEBUG MODE: Running subprocess with real-time output")
                subprocess_start = time.time()
                result = subprocess.run(
                    ["python3", str(script_path), footage_id, token], 
                    timeout=timeout
                )
                subprocess_duration = time.time() - subprocess_start
                success = result.returncode == 0
            else:
                # Normal mode - capture output
                tprint(f"  -> Executing: python3 {script_path} {footage_id} {token[:10]}...")
                subprocess_start = time.time()
                result = subprocess.run(
                    ["python3", str(script_path), footage_id, token], 
                    capture_output=True, 
                    text=True,
                    timeout=timeout
                )
                subprocess_duration = time.time() - subprocess_start
                success = result.returncode == 0
            
            if success:
                tprint(f"✅ Subprocess completed: {description} (Step {step_num}) on ID {footage_id} ({subprocess_duration:.2f}s)")
                tprint(f"  -> SUCCESS: {script_name} completed for {footage_id}")
                
                # Handle final step completion (step 6 - description generation)
                if is_final_step and step.get("final_status"):
                    print(f"  -> Final step completed - updating footage and frame statuses")
                    
                    # Update footage status to "7 - Generating Embeddings"
                    print(f"  -> Updating footage status to: {step['final_status']}")
                    if not update_status(record_id, token, step["final_status"]):
                        print(f"  -> WARNING: Failed to update footage status to '{step['final_status']}', but step completed successfully")
                    else:
                        print(f"  -> Footage status updated successfully")
                    
                    # Update all child frame statuses to "5 - Generating Embeddings"
                    if not update_frame_statuses_for_footage(footage_id, token, "5 - Generating Embeddings"):
                        print(f"  -> WARNING: Failed to update frame statuses, but footage step completed successfully")
                    else:
                        print(f"  -> Frame statuses updated successfully")
                        
                elif not is_final_step:
                    print(f"  -> Status already updated before step execution")
                
                return True
            else:
                print(f"❌ Subprocess failed: {description} (Step {step_num}) on ID {footage_id}")
                print(f"  -> FAILURE: {script_name} failed with exit code {result.returncode} for {footage_id}")
                
                if not DEBUG_MODE:
                    print(f"  -> RAW STDERR OUTPUT:")
                    if result.stderr:
                        print(result.stderr)
                    print(f"  -> RAW STDOUT OUTPUT:")
                    if result.stdout:
                        print(result.stdout)
                
                # Extract meaningful error for FileMaker storage
                if not DEBUG_MODE:
                    stderr_output = result.stderr.strip() if result.stderr else ""
                    stdout_output = result.stdout.strip() if result.stdout else ""
                    
                    # Filter out warnings for storage
                    def filter_warnings_for_storage(text):
                        if not text:
                            return ""
                        
                        lines = text.split('\n')
                        filtered = []
                        
                        for line in lines:
                            # Filter very specific urllib3 warnings
                            is_urllib3_warning = (
                                line.strip().startswith('warnings.warn(') and any(pattern in line for pattern in [
                                    '/urllib3/__init__.py',
                                    'NotOpenSSLWarning',
                                    'urllib3 v2 only supports OpenSSL'
                                ])
                            )
                            
                            if not is_urllib3_warning:
                                filtered.append(line)
                        
                        return '\n'.join(filtered).strip()
                    
                    stderr_filtered = filter_warnings_for_storage(stderr_output)
                    stdout_filtered = filter_warnings_for_storage(stdout_output)
                    
                    if stderr_filtered:
                        error_details = stderr_filtered
                    elif stdout_filtered:
                        error_details = stdout_filtered
                    else:
                        error_details = f"Script failed with exit code {result.returncode}"
                    
                    print(f"  -> Writing error to FileMaker: {error_details[:200]}...")
                    
                    error_msg = format_error_message(
                        footage_id,
                        description,
                        error_details,
                        "Processing Error"
                    )
                    write_footage_error_to_console(footage_id, token, error_msg)
                
                # Check if we should retry
                if attempt < max_retries - 1:
                    retry_delay = 2 ** attempt  # Exponential backoff
                    print(f"  -> Retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"  -> Max retries exceeded for {script_name}")
                    return False
                    
        except subprocess.TimeoutExpired:
            print(f"  -> TIMEOUT: {script_name} timed out after {timeout}s for {footage_id}")
            
            # Check if we should retry
            if attempt < max_retries - 1:
                retry_delay = 2 ** attempt  # Exponential backoff
                print(f"  -> Retrying after timeout in {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                continue
            else:
                error_msg = format_error_message(
                    footage_id,
                    description,
                    f"Script timed out after {timeout}s: {script_name}",
                    "Timeout Error"
                )
                write_footage_error_to_console(footage_id, token, error_msg)
                return False
                
        except Exception as e:
            print(f"  -> SYSTEM ERROR: {e}")
            traceback.print_exc()
            
            # Check if we should retry
            if attempt < max_retries - 1:
                retry_delay = 2 ** attempt  # Exponential backoff
                print(f"  -> Retrying after system error in {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                continue
            else:
                error_msg = format_error_message(
                    footage_id,
                    description,
                    f"System error running {script_name}: {str(e)}",
                    "System Error"
                )
                write_footage_error_to_console(footage_id, token, error_msg)
                return False
    
    return False

def run_complete_workflow(footage_id, record_id, token):
    """Run the complete AutoLog workflow for a single footage_id with pre-fetched record_id."""
    workflow_start_time = time.time()
    print(f"=== Starting AutoLog workflow for {footage_id} (record_id: {record_id}) ===")
    
    # Minimal random delay to stagger connection attempts
    import random
    time.sleep(random.uniform(0.001, 0.005))  # Reduced delay
    
    try:
        # Get current record state to determine where to start
        record_data, token = get_current_record_data(record_id, token)
        if not record_data:
            print(f"❌ Failed to get record data for {footage_id}")
            return False
        
        current_status = record_data['fieldData'].get(FIELD_MAPPING["status"], "0 - Pending File Info")
        start_step = determine_workflow_start_step(current_status, record_data['fieldData'])
        
        if start_step is None:
            print(f"=== No processing needed for {footage_id} (status: {current_status}) ===")
            return True
        
        print(f"=== Starting workflow from step {start_step} for status '{current_status}' ===")
        
        # Run workflow steps starting from determined step
        for step in WORKFLOW_STEPS:
            if step["step_num"] < start_step:
                print(f"  -> Skipping step {step['step_num']}: {step['description']} (already completed)")
                continue  # Skip already completed steps
            step_start_time = time.time()
            success = run_workflow_step(step, footage_id, record_id, token)
            step_duration = time.time() - step_start_time
            
            if not success:
                print(f"=== Workflow STOPPED at step {step['step_num']}: {step['description']} ===")
                print(f"  -> Step duration: {step_duration:.2f} seconds")
                print(f"  -> Total workflow duration: {time.time() - workflow_start_time:.2f} seconds")
                return False
            
            print(f"  -> Step {step['step_num']} completed in {step_duration:.2f} seconds")
            
            # Special handling for step 5: Wait for frame processing to complete
            if step["step_num"] == 5:
                print(f"  -> Step 5 completed - checking if all frames are ready for step 6...")
                frames_ready = wait_for_frame_completion(footage_id, token)
                if not frames_ready:
                    # Get detailed frame status for debugging
                    print(f"  -> 🔍 Getting detailed frame status for debugging...")
                    get_detailed_frame_status(footage_id, token)
                    
                    error_msg = format_error_message(
                        footage_id,
                        "Frame Processing",
                        f"Frames not ready for step 6 after waiting. Some frames may be stuck in processing.",
                        "Frame Processing Warning"
                    )
                    write_footage_error_to_console(footage_id, token, error_msg)
                    print(f"  -> WARNING: Frames not ready for step 6 - workflow will continue on next run")
                    print(f"  -> Error written to AI_DevConsole for {footage_id}")
                    return True  # Don't fail, just let it continue later
                else:
                    print(f"  -> ✅ All frames ready for step 6 - proceeding to description generation")
            
            # Brief delays for complex operations
            if step.get("step_num") == 4:
                print(f"  -> Brief delay after frame processing to allow completion")
                time.sleep(0.2)
            elif step.get("step_num") in [1, 2]:
                time.sleep(0.05)
        
        total_duration = time.time() - workflow_start_time
        print(f"=== Workflow COMPLETED successfully for {footage_id} in {total_duration:.2f} seconds ===")
        return True
        
    except Exception as e:
        total_duration = time.time() - workflow_start_time
        print(f"=== FATAL ERROR in workflow for {footage_id} after {total_duration:.2f} seconds: {e} ===")
        traceback.print_exc()
        
        # Try to write error to console
        try:
            error_msg = format_error_message(
                footage_id,
                "Workflow Controller",
                f"Critical system error: {str(e)}",
                "Critical Error"
            )
            write_footage_error_to_console(footage_id, token, error_msg)
        except:
            pass
        
        return False

def run_batch_workflow(footage_ids, token, max_workers=15):
    """Run the complete AutoLog workflow for multiple footage_ids in parallel."""
    sorted_footage_ids = sorted(footage_ids)
    
    print(f"=== Starting BATCH AutoLog workflow for {len(sorted_footage_ids)} items ===")
    print(f"=== Processing in order: {sorted_footage_ids[:5]}{'...' if len(sorted_footage_ids) > 5 else ''} ===")
    
    # Pre-fetch all record IDs
    print(f"=== Pre-fetching record IDs for {len(sorted_footage_ids)} items ===")
    footage_to_record_id = {}
    failed_lookups = []
    
    for footage_id in sorted_footage_ids:
        try:
            record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
            footage_to_record_id[footage_id] = record_id
            print(f"  -> {footage_id}: {record_id}")
        except Exception as e:
            print(f"  -> {footage_id}: FAILED - {e}")
            failed_lookups.append(footage_id)
    
    if failed_lookups:
        print(f"⚠️ {len(failed_lookups)} items failed record lookup: {failed_lookups}")
        sorted_footage_ids = [fid for fid in sorted_footage_ids if fid not in failed_lookups]
    
    if not sorted_footage_ids:
        print(f"❌ No items can be processed - all record lookups failed")
        return {"total_items": 0, "successful": 0, "failed": len(failed_lookups), "results": []}
    
    # Adjust concurrency for footage processing
    actual_max_workers = min(max_workers, len(sorted_footage_ids))
    print(f"=== Using {actual_max_workers} concurrent workers ===")
    
    results = {
        "total_items": len(sorted_footage_ids) + len(failed_lookups),
        "successful": 0,
        "failed": len(failed_lookups),
        "results": [{"footage_id": fid, "success": False, "error": "Record lookup failed"} for fid in failed_lookups],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    def process_single_item(footage_id):
        """Process a single footage_id and return result."""
        try:
            print(f"[BATCH] Starting workflow for {footage_id}")
            record_id = footage_to_record_id[footage_id]
            success = run_complete_workflow(footage_id, record_id, token)
            result = {
                "footage_id": footage_id,
                "success": success,
                "completed_at": datetime.now().isoformat(),
                "error": None
            }
            print(f"[BATCH] {'✅ SUCCESS' if success else '❌ FAILED'}: {footage_id}")
            return result
        except Exception as e:
            result = {
                "footage_id": footage_id,
                "success": False,
                "completed_at": datetime.now().isoformat(),
                "error": str(e)
            }
            print(f"[BATCH] ❌ ERROR: {footage_id} - {e}")
            return result
    
    # Process items in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        future_to_footage_id = {}
        for footage_id in sorted_footage_ids:
            future = executor.submit(process_single_item, footage_id)
            future_to_footage_id[future] = footage_id
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_footage_id):
            result = future.result()
            results["results"].append(result)
            
            if result["success"]:
                results["successful"] += 1
            else:
                results["failed"] += 1
            
            completed = len(results["results"])
            print(f"[BATCH] Progress: {completed}/{len(sorted_footage_ids)} completed ({results['successful']} successful, {results['failed']} failed)")
    
    results["end_time"] = datetime.now().isoformat()
    
    # Calculate total duration
    start_time = datetime.fromisoformat(results["start_time"])
    end_time = datetime.fromisoformat(results["end_time"])
    duration = (end_time - start_time).total_seconds()
    
    # Print final summary
    print(f"=== BATCH AutoLog workflow COMPLETED ===")
    print(f"Total items: {results['total_items']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")
    print(f"Success rate: {(results['successful'] / results['total_items'] * 100):.1f}%")
    print(f"Total duration: {duration:.2f} seconds")
    print(f"Average per item: {duration / results['total_items']:.2f} seconds")
    print(f"⚡ Throughput: {results['total_items'] / duration * 60:.1f} items/minute")
    
    return results

def run_pipeline_workflow(footage_ids, token, max_workers=20):
    """Run workflow using pipeline processing - records flow through steps independently."""
    sorted_footage_ids = sorted(footage_ids)
    
    tprint(f"=== Starting PIPELINE AutoLog workflow for {len(sorted_footage_ids)} items ===")
    tprint(f"=== Processing: {sorted_footage_ids[:5]}{'...' if len(sorted_footage_ids) > 5 else ''} ===")
    
    # Pre-fetch all record IDs
    tprint(f"=== Pre-fetching record IDs for {len(sorted_footage_ids)} items ===")
    footage_to_record_id = {}
    failed_lookups = []
    
    for footage_id in sorted_footage_ids:
        try:
            lookup_start = time.time()
            record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
            lookup_duration = time.time() - lookup_start
            footage_to_record_id[footage_id] = record_id
            tprint(f"  -> {footage_id}: {record_id} ({lookup_duration:.3f}s)")
        except Exception as e:
            tprint(f"  -> {footage_id}: FAILED - {e}")
            failed_lookups.append(footage_id)
    
    if failed_lookups:
        tprint(f"⚠️ {len(failed_lookups)} items failed record lookup: {failed_lookups}")
        sorted_footage_ids = [fid for fid in sorted_footage_ids if fid not in failed_lookups]
    
    if not sorted_footage_ids:
        tprint(f"❌ No items can be processed - all record lookups failed")
        return {"total_items": 0, "successful": 0, "failed": len(failed_lookups), "results": []}
    
    # Use higher concurrency for pipeline processing
    actual_max_workers = min(max_workers, len(sorted_footage_ids) * 2)  # More workers for pipeline
    tprint(f"=== Using {actual_max_workers} concurrent workers for pipeline processing ===")
    
    results = {
        "total_items": len(sorted_footage_ids) + len(failed_lookups),
        "successful": 0,
        "failed": len(failed_lookups),
        "results": [{"footage_id": fid, "success": False, "error": "Record lookup failed"} for fid in failed_lookups],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    def run_single_workflow_item(footage_id):
        """Run complete workflow for a single item - each item flows through steps independently."""
        try:
            tprint(f"[PIPELINE] Starting independent workflow for {footage_id}")
            workflow_start = time.time()
            record_id = footage_to_record_id[footage_id]
            success = run_complete_workflow(footage_id, record_id, token)
            workflow_duration = time.time() - workflow_start
            result = {
                "footage_id": footage_id,
                "success": success,
                "completed_at": datetime.now().isoformat(),
                "error": None,
                "duration": workflow_duration
            }
            tprint(f"[PIPELINE] {'✅ COMPLETE' if success else '❌ FAILED'}: {footage_id} ({workflow_duration:.2f}s)")
            return result
        except Exception as e:
            workflow_duration = time.time() - workflow_start if 'workflow_start' in locals() else 0
            result = {
                "footage_id": footage_id,
                "success": False,
                "completed_at": datetime.now().isoformat(),
                "error": str(e),
                "duration": workflow_duration
            }
            tprint(f"[PIPELINE] ❌ ERROR: {footage_id} - {e} ({workflow_duration:.2f}s)")
            return result
    
    # Process all items in parallel - each flows through its own complete workflow
    tprint(f"=== Starting pipeline processing with {actual_max_workers} workers ===")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        # Submit all workflows to run in parallel
        submission_start = time.time()
        future_to_footage_id = {
            executor.submit(run_single_workflow_item, footage_id): footage_id 
            for footage_id in sorted_footage_ids
        }
        submission_duration = time.time() - submission_start
        tprint(f"=== All {len(sorted_footage_ids)} jobs submitted in {submission_duration:.3f}s ===")
        
        # Collect results as they complete
        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_footage_id):
            result = future.result()
            results["results"].append(result)
            completed_count += 1
            
            if result["success"]:
                results["successful"] += 1
            else:
                results["failed"] += 1
            
            # More frequent progress updates with timestamps
            success_rate = (results['successful'] / completed_count * 100) if completed_count > 0 else 0
            tprint(f"[PIPELINE] Progress: {completed_count}/{len(sorted_footage_ids)} ({results['successful']} ✅, {results['failed']} ❌) - {success_rate:.1f}% success")
    
    results["end_time"] = datetime.now().isoformat()
    
    # Calculate total duration
    start_time = datetime.fromisoformat(results["start_time"])
    end_time = datetime.fromisoformat(results["end_time"])
    duration = (end_time - start_time).total_seconds()
    
    # Print final summary
    print(f"=== PIPELINE AutoLog workflow COMPLETED ===")
    print(f"Total duration: {duration:.2f} seconds")
    print(f"Total items: {results['total_items']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")
    
    if results['successful'] > 0:
        avg_time_per_item = duration / results['successful']
        print(f"Average time per successful item: {avg_time_per_item:.2f} seconds")
    
    success_rate = (results['successful'] / results['total_items'] * 100) if results['total_items'] > 0 else 0
    print(f"Success rate: {success_rate:.1f}%")
    
    return results

def run_optimized_pipeline_workflow(footage_ids, token, max_workers=20):
    """Run workflow with optimized step-wise processing - batch Step 6 for maximum speed."""
    sorted_footage_ids = sorted(footage_ids)
    
    tprint(f"=== Starting OPTIMIZED PIPELINE AutoLog workflow for {len(sorted_footage_ids)} items ===")
    tprint(f"=== Processing: {sorted_footage_ids[:5]}{'...' if len(sorted_footage_ids) > 5 else ''} ===")
    
    # Pre-fetch all record IDs
    tprint(f"=== Pre-fetching record IDs for {len(sorted_footage_ids)} items ===")
    footage_to_record_id = {}
    failed_lookups = []
    
    for footage_id in sorted_footage_ids:
        try:
            lookup_start = time.time()
            record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
            lookup_duration = time.time() - lookup_start
            footage_to_record_id[footage_id] = record_id
            tprint(f"  -> {footage_id}: {record_id} ({lookup_duration:.3f}s)")
        except Exception as e:
            tprint(f"  -> {footage_id}: FAILED - {e}")
            failed_lookups.append(footage_id)
    
    if failed_lookups:
        tprint(f"⚠️ {len(failed_lookups)} items failed record lookup: {failed_lookups}")
        sorted_footage_ids = [fid for fid in sorted_footage_ids if fid not in failed_lookups]
    
    if not sorted_footage_ids:
        tprint(f"❌ No items can be processed - all record lookups failed")
        return {"total_items": 0, "successful": 0, "failed": len(failed_lookups), "results": []}
    
    # Use higher concurrency for pipeline processing
    actual_max_workers = min(max_workers, len(sorted_footage_ids))
    tprint(f"=== Using {actual_max_workers} concurrent workers for optimized pipeline ===")
    
    results = {
        "total_items": len(sorted_footage_ids) + len(failed_lookups),
        "successful": 0,
        "failed": len(failed_lookups),
        "results": [{"footage_id": fid, "success": False, "error": "Record lookup failed"} for fid in failed_lookups],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    def run_steps_1_through_5(footage_id):
        """Run steps 1-5 for a single footage item."""
        try:
            workflow_start = time.time()
            record_id = footage_to_record_id[footage_id]
            
            tprint(f"[PIPELINE] Starting steps 1-5 for {footage_id}")
            
            # Get current record state to determine where to start
            record_data, current_token = get_current_record_data(record_id, token)
            if not record_data:
                return {"footage_id": footage_id, "success": False, "error": "Failed to get record data", "ready_for_step6": False}
            
            current_status = record_data['fieldData'].get(FIELD_MAPPING["status"], "0 - Pending File Info")
            start_step = determine_workflow_start_step(current_status, record_data['fieldData'])
            
            if start_step is None:
                return {"footage_id": footage_id, "success": True, "error": None, "ready_for_step6": True, "duration": 0}
            
            # Run workflow steps 1-5 only
            for step in WORKFLOW_STEPS:
                if step["step_num"] > 5:  # Skip step 6 - we'll batch it
                    break
                    
                if step["step_num"] < start_step:
                    continue  # Skip already completed steps
                    
                step_start_time = time.time()
                success = run_workflow_step(step, footage_id, record_id, current_token)
                step_duration = time.time() - step_start_time
                
                if not success:
                    workflow_duration = time.time() - workflow_start
                    tprint(f"[PIPELINE] ❌ Steps 1-5 FAILED: {footage_id} at step {step['step_num']} ({workflow_duration:.2f}s)")
                    return {"footage_id": footage_id, "success": False, "error": f"Failed at step {step['step_num']}", "ready_for_step6": False, "duration": workflow_duration}
                
                # Special handling for step 5: Wait for frame processing
                if step["step_num"] == 5:
                    tprint(f"[PIPELINE] Checking frame completion for {footage_id}...")
                    frames_ready = wait_for_frame_completion(footage_id, current_token, max_wait_time=300, check_interval=5)
                    if not frames_ready:
                        workflow_duration = time.time() - workflow_start
                        tprint(f"[PIPELINE] ⚠️ Frames not ready for {footage_id} - will retry later ({workflow_duration:.2f}s)")
                        return {"footage_id": footage_id, "success": True, "error": "Frames not ready", "ready_for_step6": False, "duration": workflow_duration}
            
            workflow_duration = time.time() - workflow_start
            tprint(f"[PIPELINE] ✅ Steps 1-5 COMPLETE: {footage_id} - ready for step 6 ({workflow_duration:.2f}s)")
            return {"footage_id": footage_id, "success": True, "error": None, "ready_for_step6": True, "duration": workflow_duration}
            
        except Exception as e:
            workflow_duration = time.time() - workflow_start if 'workflow_start' in locals() else 0
            tprint(f"[PIPELINE] ❌ Exception in steps 1-5: {footage_id} - {e} ({workflow_duration:.2f}s)")
            return {"footage_id": footage_id, "success": False, "error": str(e), "ready_for_step6": False, "duration": workflow_duration}
    
    # PHASE 1: Run steps 1-5 for all items in parallel
    tprint(f"=== PHASE 1: Running steps 1-5 for all items in parallel ===")
    
    phase1_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        future_to_footage_id = {
            executor.submit(run_steps_1_through_5, footage_id): footage_id 
            for footage_id in sorted_footage_ids
        }
        
        for future in concurrent.futures.as_completed(future_to_footage_id):
            result = future.result()
            phase1_results.append(result)
            tprint(f"[PHASE1] Progress: {len(phase1_results)}/{len(sorted_footage_ids)} - {result['footage_id']}: {'✅' if result['success'] else '❌'}")
    
    # Separate items ready for step 6 vs those that failed
    ready_for_step6 = [r for r in phase1_results if r.get('ready_for_step6', False)]
    failed_items = [r for r in phase1_results if not r['success'] or not r.get('ready_for_step6', False)]
    
    tprint(f"=== PHASE 1 COMPLETE: {len(ready_for_step6)} ready for step 6, {len(failed_items)} not ready ===")
    
    # PHASE 2: Batch process step 6 for all ready items
    if ready_for_step6:
        tprint(f"=== PHASE 2: Batch processing step 6 for {len(ready_for_step6)} items ===")
        
        # Extract footage IDs ready for step 6
        step6_footage_ids = [r['footage_id'] for r in ready_for_step6]
        
        def run_step6_for_item(footage_id):
            """Run step 6 for a single footage item."""
            try:
                step6_start = time.time()
                record_id = footage_to_record_id[footage_id]
                step = WORKFLOW_STEPS[5]  # Step 6 (index 5)
                
                tprint(f"[STEP6] Processing description for {footage_id}")
                success = run_workflow_step(step, footage_id, record_id, token)
                step6_duration = time.time() - step6_start
                
                if success:
                    tprint(f"[STEP6] ✅ Description complete: {footage_id} ({step6_duration:.2f}s)")
                    return {"footage_id": footage_id, "success": True, "error": None, "duration": step6_duration}
                else:
                    tprint(f"[STEP6] ❌ Description failed: {footage_id} ({step6_duration:.2f}s)")
                    return {"footage_id": footage_id, "success": False, "error": "Step 6 failed", "duration": step6_duration}
                    
            except Exception as e:
                step6_duration = time.time() - step6_start if 'step6_start' in locals() else 0
                tprint(f"[STEP6] ❌ Exception: {footage_id} - {e} ({step6_duration:.2f}s)")
                return {"footage_id": footage_id, "success": False, "error": str(e), "duration": step6_duration}
        
        # Process step 6 in parallel with fewer workers (AI intensive)
        step6_max_workers = min(8, len(step6_footage_ids))  # Fewer workers for AI operations
        step6_results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=step6_max_workers) as executor:
            future_to_footage_id = {
                executor.submit(run_step6_for_item, footage_id): footage_id 
                for footage_id in step6_footage_ids
            }
            
            for future in concurrent.futures.as_completed(future_to_footage_id):
                result = future.result()
                step6_results.append(result)
                tprint(f"[PHASE2] Progress: {len(step6_results)}/{len(step6_footage_ids)} - {result['footage_id']}: {'✅' if result['success'] else '❌'}")
        
        # Combine results
        all_results = []
        
        # Add phase 1 results that weren't ready for step 6
        for result in failed_items:
            all_results.append({
                "footage_id": result['footage_id'],
                "success": result['success'],
                "completed_at": datetime.now().isoformat(),
                "error": result.get('error'),
                "duration": result.get('duration', 0)
            })
        
        # Add step 6 results
        for phase1_result in ready_for_step6:
            step6_result = next((r for r in step6_results if r['footage_id'] == phase1_result['footage_id']), None)
            if step6_result:
                total_duration = phase1_result.get('duration', 0) + step6_result.get('duration', 0)
                all_results.append({
                    "footage_id": phase1_result['footage_id'],
                    "success": step6_result['success'],
                    "completed_at": datetime.now().isoformat(),
                    "error": step6_result.get('error'),
                    "duration": total_duration
                })
    else:
        # No items ready for step 6
        all_results = []
        for result in failed_items:
            all_results.append({
                "footage_id": result['footage_id'],
                "success": result['success'],
                "completed_at": datetime.now().isoformat(),
                "error": result.get('error'),
                "duration": result.get('duration', 0)
            })
    
    # Update results
    results["results"].extend(all_results)
    for result in all_results:
        if result["success"]:
            results["successful"] += 1
        else:
            results["failed"] += 1
    
    results["end_time"] = datetime.now().isoformat()
    
    # Calculate total duration
    start_time = datetime.fromisoformat(results["start_time"])
    end_time = datetime.fromisoformat(results["end_time"])
    duration = (end_time - start_time).total_seconds()
    
    # Print final summary
    tprint(f"=== OPTIMIZED PIPELINE AutoLog workflow COMPLETED ===")
    tprint(f"Total duration: {duration:.2f} seconds")
    tprint(f"Total items: {results['total_items']}")
    tprint(f"Successful: {results['successful']}")
    tprint(f"Failed: {results['failed']}")
    
    if results['successful'] > 0:
        avg_time_per_item = duration / results['successful']
        tprint(f"Average time per successful item: {avg_time_per_item:.2f} seconds")
    
    success_rate = (results['successful'] / results['total_items'] * 100) if results['total_items'] > 0 else 0
    tprint(f"Success rate: {success_rate:.1f}%")
    
    return results

def find_pending_items(token):
    """Find all items with '0 - Pending File Info' status."""
    try:
        print(f"🔍 Searching for items with '0 - Pending File Info' status...")
        
        query = {
            "query": [{FIELD_MAPPING["status"]: "0 - Pending File Info"}],
            "limit": 100
        }
        
        response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False
        )
        
        if response.status_code == 404:
            print(f"📋 No pending items found")
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        # Extract footage_ids from the records
        footage_ids = []
        for record in records:
            footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
            if footage_id:
                footage_ids.append(footage_id)
            else:
                print(f"⚠️ Warning: Record {record['recordId']} has no footage_id")
        
        print(f"📋 Found {len(footage_ids)} pending items: {footage_ids[:10]}{'...' if len(footage_ids) > 10 else ''}")
        return footage_ids
        
    except Exception as e:
        print(f"❌ Error finding pending items: {e}")
        return []

# Legacy function - replaced by find_all_processable_items
def find_resume_processing_items(token):
    """DEPRECATED: Find all items with 'Force Resume' status (modern name)."""
    try:
        tprint(f"🔍 Searching for items with 'Force Resume' status...")
        
        query = {
            "query": [{FIELD_MAPPING["status"]: "Force Resume"}],
            "limit": 100
        }
        
        response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False
        )
        
        if response.status_code == 404:
            tprint(f"📋 No Force Resume items found")
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        # Extract footage_ids from the records
        footage_ids = []
        for record in records:
            footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
            if footage_id:
                footage_ids.append(footage_id)
        
        tprint(f"📋 Found {len(footage_ids)} Force Resume items: {footage_ids[:10]}{'...' if len(footage_ids) > 10 else ''}")
        return footage_ids
        
    except Exception as e:
        tprint(f"❌ Error finding Force Resume items: {e}")
        return []

def find_awaiting_user_input_items(token):
    """Find all items with 'Awaiting User Input' status (user has added metadata, ready to resume)."""
    try:
        print(f"🔍 Searching for items with 'Awaiting User Input' status...")
        
        query = {
            "query": [{FIELD_MAPPING["status"]: "Awaiting User Input"}],
            "limit": 100
        }
        
        response = requests.post(
            config.url("layouts/FOOTAGE/_find"),
            headers=config.api_headers(token),
            json=query,
            verify=False
        )
        
        if response.status_code == 404:
            print(f"📋 No awaiting user input items found")
            return []
        
        response.raise_for_status()
        records = response.json()['response']['data']
        
        # Extract footage_ids from the records
        footage_ids = []
        for record in records:
            footage_id = record['fieldData'].get(FIELD_MAPPING["footage_id"])
            if footage_id:
                footage_ids.append(footage_id)
        
        print(f"📋 Found {len(footage_ids)} awaiting user input items: {footage_ids[:10]}{'...' if len(footage_ids) > 10 else ''}")
        return footage_ids
        
    except Exception as e:
        print(f"❌ Error finding awaiting user input items: {e}")
        return []

def run_streaming_pipeline_workflow(footage_ids, token, max_workers=20):
    """
    STREAMING PIPELINE: Each item flows through all steps independently.
    Fast items don't wait for slow items - true parallel processing.
    """
    tprint(f"🚀 Using STREAMING PIPELINE processing for maximum throughput")
    tprint(f"🎯 Each item flows independently through all 6 steps")
    
    # Pre-fetch all record IDs to avoid lookup delays
    footage_to_record_id = {}
    failed_lookups = []
    
    for footage_id in footage_ids:
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        if record_id:
            footage_to_record_id[footage_id] = record_id
        else:
            failed_lookups.append(footage_id)
            tprint(f"❌ Failed to find record for {footage_id}")
    
    if failed_lookups:
        tprint(f"⚠️ Skipping {len(failed_lookups)} items with lookup failures")
    
    sorted_footage_ids = sorted(footage_to_record_id.keys())
    tprint(f"=== Starting STREAMING PIPELINE AutoLog workflow for {len(sorted_footage_ids)} items ===")
    
    results = {
        "total_items": len(sorted_footage_ids) + len(failed_lookups),
        "successful": 0,
        "failed": len(failed_lookups),
        "results": [{"footage_id": fid, "success": False, "error": "Record lookup failed"} for fid in failed_lookups],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    def run_complete_item_workflow(footage_id):
        """Run the complete workflow (steps 1-6) for a single footage item."""
        try:
            item_start = time.time()
            record_id = footage_to_record_id[footage_id]
            
            tprint(f"[STREAM] Starting complete workflow for {footage_id}")
            
            # Run the existing complete workflow function
            success = run_complete_workflow(footage_id, record_id, token)
            
            duration = time.time() - item_start
            tprint(f"[STREAM] {'✅ COMPLETED' if success else '❌ FAILED'}: {footage_id} ({duration:.1f}s)")
            
            return {
                "footage_id": footage_id, 
                "success": success, 
                "error": None if success else "Workflow failed", 
                "duration": duration
            }
            
        except Exception as e:
            duration = time.time() - item_start
            error_msg = str(e)
            tprint(f"[STREAM] ❌ ERROR: {footage_id} - {error_msg} ({duration:.1f}s)")
            return {"footage_id": footage_id, "success": False, "error": error_msg, "duration": duration}
    
    # Process all items in parallel - each flows through all steps independently
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        tprint(f"[STREAM] Launching {len(sorted_footage_ids)} items with {max_workers} max workers")
        
        # Submit all jobs
        future_to_footage = {
            executor.submit(run_complete_item_workflow, footage_id): footage_id 
            for footage_id in sorted_footage_ids
        }
        
        # Process results as they complete
        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_footage):
            footage_id = future_to_footage[future]
            try:
                result = future.result()
                results["results"].append(result)
                
                if result["success"]:
                    results["successful"] += 1
                    status_emoji = "✅"
                else:
                    results["failed"] += 1
                    status_emoji = "❌"
                
                completed_count += 1
                progress_pct = (completed_count / len(sorted_footage_ids)) * 100
                
                tprint(f"[STREAM] Progress: {completed_count}/{len(sorted_footage_ids)} ({progress_pct:.1f}%) - {footage_id}: {status_emoji}")
                
            except Exception as e:
                results["failed"] += 1
                results["results"].append({
                    "footage_id": footage_id, 
                    "success": False, 
                    "error": f"Future exception: {str(e)}", 
                    "duration": 0
                })
                completed_count += 1
                tprint(f"[STREAM] Progress: {completed_count}/{len(sorted_footage_ids)} - {footage_id}: ❌ (Exception)")
    
    # Final summary
    total_time = time.time() - time.time()  # Will be calculated properly
    results["end_time"] = datetime.now().isoformat()
    
    tprint(f"")
    tprint(f"=== STREAMING PIPELINE COMPLETE ===")
    tprint(f"📊 Results: {results['successful']}/{results['total_items']} successful")
    tprint(f"⏱️ Average time per item: {sum(r.get('duration', 0) for r in results['results'] if r.get('duration', 0) > 0) / max(1, len([r for r in results['results'] if r.get('duration', 0) > 0])):.1f}s")
    
    # Show any failures
    failures = [r for r in results["results"] if not r["success"]]
    if failures:
        tprint(f"❌ Failed items:")
        for failure in failures[:5]:  # Show first 5 failures
            tprint(f"  -> {failure['footage_id']}: {failure['error']}")
        if len(failures) > 5:
            tprint(f"  -> ... and {len(failures) - 5} more")
    
    return results

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

def get_current_record_data(record_id, token, max_retries=3):
    """Get current record data from FileMaker with retry logic."""
    current_token = token
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                config.url(f"layouts/FOOTAGE/records/{record_id}"), 
                headers=config.api_headers(current_token), 
                verify=False,
                timeout=30
            )
            
            if response.status_code == 401:
                current_token = config.get_token()
                continue
            
            response.raise_for_status()
            return response.json()['response']['data'][0], current_token
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
    
    return None, current_token

def process_single_footage(footage_id, token, queue_stats):
    """Process a single footage item through the complete workflow."""
    try:
        tprint(f"🚀 Starting workflow for {footage_id}")
        start_time = time.time()
        
        # Get record ID
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        if not record_id:
            tprint(f"❌ {footage_id}: Record not found")
            return {"footage_id": footage_id, "success": False, "error": "Record not found"}
        
        # Get current record data and status
        record_data, token = get_current_record_data(record_id, token)
        if not record_data:
            tprint(f"❌ {footage_id}: Failed to get record data")
            return {"footage_id": footage_id, "success": False, "error": "Failed to get record data"}
        
        current_status = record_data['fieldData'].get(FIELD_MAPPING["status"], "Unknown")
        
        # Check if already complete
        if current_status in TERMINAL_STATES:
            tprint(f"✅ {footage_id}: Already complete (status: {current_status})")
            return {"footage_id": footage_id, "success": True, "error": None, "skipped": True}
        
        # Handle Force Resume
        if current_status == "Force Resume":
            tprint(f"🚀 {footage_id}: Force Resume - bypassing metadata evaluation")
            write_to_dev_console(record_id, token, "FORCE RESUME triggered by user - bypassing metadata evaluation")
            current_status = "5 - Processing Frame Info"  # Jump to step 5
            update_status(record_id, token, current_status)
        
        # Process workflow steps
        for step in WORKFLOW_STEPS:
            step_num = step["step"]
            status_before = step["status_before"]
            status_after = step["status_after"]
            script = step["script"]
            description = step["description"]
            timeout = step.get("timeout", 300)
            
            # Check if we should run this step
            if isinstance(status_before, list):
                should_run = current_status in status_before
            else:
                should_run = current_status == status_before
            
            if not should_run:
                continue
            
            tprint(f"  -> Step {step_num}: {description}")
            
            # Handle conditional URL scraping
            if step.get("conditional"):
                url = record_data['fieldData'].get(FIELD_MAPPING["url"], '')
                if not url or not url.strip():
                    tprint(f"  -> {footage_id}: Skipping URL scraping - no URL available")
                    current_status = status_after  # Skip to next status
                    update_status(record_id, token, current_status)
                    continue
            
            # Update status to processing state
            update_status(record_id, token, status_after)
            
            # Run the script
            success, error_msg = run_single_script(script, footage_id, token, timeout)
            
            if not success:
                tprint(f"❌ {footage_id}: Step {step_num} failed - {error_msg}")
                return {"footage_id": footage_id, "success": False, "error": f"Step {step_num}: {error_msg}"}
            
            tprint(f"✅ {footage_id}: Step {step_num} completed")
            current_status = status_after
            
            # Handle metadata evaluation after step 4/5
            if step.get("metadata_evaluation"):
                # Get fresh record data for evaluation
                record_data, token = get_current_record_data(record_id, token)
                if record_data:
                    metadata_good = evaluate_metadata_quality(record_data['fieldData'], token, record_id)
                    if not metadata_good:
                        tprint(f"⚠️ {footage_id}: Metadata quality insufficient - setting to Awaiting User Input")
                        update_status(record_id, token, "Awaiting User Input")
                        update_frame_statuses_for_footage(footage_id, token, "Awaiting User Input")
                        return {"footage_id": footage_id, "success": True, "error": None, "awaiting_user": True}
            
            # Handle frame completion check for step 6
            if step.get("requires_frame_completion"):
                frames_ready, frame_status = check_frame_completion(token, footage_id)
                if not frames_ready:
                    tprint(f"⏳ {footage_id}: Waiting for frames - {frame_status}")
                    return {"footage_id": footage_id, "success": False, "error": f"Frames not ready: {frame_status}"}
            
            # Handle final status for step 6
            if step.get("final_status"):
                final_status = step["final_status"]
                tprint(f"🎯 {footage_id}: Setting final status to '{final_status}'")
                update_status(record_id, token, final_status)
                
                # Move all frames to final status
                update_frame_statuses_for_footage(footage_id, token, "5 - Generating Embeddings")
                
                current_status = final_status
                break  # Workflow complete
        
        duration = time.time() - start_time
        tprint(f"✅ {footage_id}: Workflow completed successfully ({duration:.1f}s)")
        
        return {"footage_id": footage_id, "success": True, "error": None, "duration": duration}
        
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        tprint(f"❌ {footage_id}: Exception - {error_msg} ({duration:.1f}s)")
        return {"footage_id": footage_id, "success": False, "error": error_msg, "duration": duration}

def process_queued_batch(footage_ids, token, max_workers=5):
    """Process footage IDs in protected batches with modern API protection."""
    tprint(f"🚀 Starting modernized queued batch processing")
    
    # Initialize processing queue
    queue = ModernProcessingQueue(token, max_workers=max_workers, batch_size=10)
    queue.stats["total_items"] = len(footage_ids)
    
    # 1. Validate and filter IDs
    tprint(f"📋 Phase 1: Validating {len(footage_ids)} footage IDs...")
    valid_ids = validate_footage_ids(footage_ids, token)
    
    if not valid_ids:
        tprint(f"❌ No valid footage IDs found")
        queue.stats["failed"] = queue.stats["total_items"]
        queue.stats["end_time"] = datetime.now().isoformat()
        return queue.stats
    
    # 2. Handle LF items
    tprint(f"📋 Phase 2: Handling LF items...")
    processable_ids = handle_lf_items(valid_ids, token)
    
    if not processable_ids:
        tprint(f"✅ All items were LF items - set to Awaiting User Input")
        queue.stats["skipped"] = len(valid_ids)
        queue.stats["end_time"] = datetime.now().isoformat()
        return queue.stats
    
    # 3. Batch processing with controlled concurrency
    tprint(f"📋 Phase 3: Processing {len(processable_ids)} items in batches...")
    
    batch_size = queue.batch_size
    batches = [processable_ids[i:i+batch_size] for i in range(0, len(processable_ids), batch_size)]
    
    for batch_num, batch in enumerate(batches):
        tprint(f"🔄 Processing batch {batch_num+1}/{len(batches)} ({len(batch)} items)")
        
        # Process batch with controlled concurrency
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_single_footage, footage_id, token, queue.stats) for footage_id in batch]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    queue.stats["results"].append(result)
                    
                    if result["success"]:
                        if result.get("skipped") or result.get("awaiting_user"):
                            queue.stats["skipped"] += 1
                        else:
                            queue.stats["successful"] += 1
                    else:
                        queue.stats["failed"] += 1
                        
                except Exception as e:
                    tprint(f"❌ Future exception: {e}")
                    queue.stats["failed"] += 1
        
        # API protection delay between batches
        if batch_num < len(batches) - 1:
            tprint(f"⏸️ API protection delay...")
            time.sleep(2)  # 2-second pause between batches
    
    # Final summary
    queue.stats["end_time"] = datetime.now().isoformat()
    
    tprint(f"\n=== QUEUED BATCH PROCESSING COMPLETE ===")
    tprint(f"📊 Results: {queue.stats['successful']} successful, {queue.stats['failed']} failed, {queue.stats['skipped']} skipped")
    
    # Show failures
    failures = [r for r in queue.stats["results"] if not r["success"]]
    if failures:
        tprint(f"❌ Failed items:")
        for failure in failures[:5]:
            tprint(f"  -> {failure['footage_id']}: {failure['error']}")
        if len(failures) > 5:
            tprint(f"  -> ... and {len(failures) - 5} more")
    
    return queue.stats

def find_all_processable_items(token):
    """Find all items that can be processed (auto-discovery mode)."""
    all_items = []
    
    tprint(f"🔍 Auto-discovery: Finding all processable items...")
    
    for status in PICKUP_STATUSES:
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
                    all_items.append(footage_id)
            
            if records:
                tprint(f"  -> Found {len(records)} items with status '{status}'")
        
        except Exception as e:
            tprint(f"⚠️ Error finding items with status '{status}': {e}")
            continue
    
    # Remove duplicates and sort
    unique_items = sorted(list(set(all_items)))
    tprint(f"📋 Auto-discovery: Found {len(unique_items)} unique processable items")
    
    return unique_items

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
        
        # Parse input IDs from arguments or discover automatically
        if len(sys.argv) > 1:
            # Payload mode: Process specific IDs
            footage_ids_json = sys.argv[1]
            try:
                footage_ids = json.loads(footage_ids_json)
                if not isinstance(footage_ids, list):
                    footage_ids = [str(footage_ids)]  # Convert single ID to list
                tprint(f"📋 Payload mode: Processing {len(footage_ids)} specified items")
            except json.JSONDecodeError:
                # Treat as single ID if not valid JSON
                footage_ids = [footage_ids_json]
                tprint(f"📋 Payload mode: Processing single item '{footage_ids_json}'")
        else:
            # Discovery mode: Find pending items automatically
            footage_ids = find_all_processable_items(token)
            tprint(f"📋 Discovery mode: Found {len(footage_ids)} items to process")
        
        if not footage_ids:
            tprint("✅ No items to process")
            sys.exit(0)
        
        # Process with modern queued approach
        results = process_queued_batch(footage_ids, token, max_workers=5)
        
        # Output results
        print(f"RESULTS: {json.dumps(results, indent=2)}")
        sys.exit(0 if results['failed'] == 0 else 1)
        
    except KeyboardInterrupt:
        tprint(f"🛑 Processing interrupted by user")
        sys.exit(0)
    except Exception as e:
        tprint(f"❌ Critical error: {e}")
        traceback.print_exc()
        sys.exit(1) 