#!/usr/bin/env python3
"""
Footage AI Processing Job Queue Definitions (Redis + Python RQ)

This module defines all 4 AI processing workflow steps as RQ jobs.
Each job:
- Executes its script
- Updates FileMaker status on success
- Queues the next step automatically
- Handles false starts (blocks accidental AI processing)

Part B Workflow: 3 - Ready for AI → 7 - Avid Description
"""

import sys
import os
import subprocess
import warnings
from pathlib import Path
from datetime import datetime
from redis import Redis
from rq import Queue

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

# Setup paths
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Field mapping for FileMaker
FIELD_MAPPING = {
    "status": "AutoLog_Status",
    "footage_id": "INFO_FTG_ID",
    "description": "INFO_Description"
}

# Redis connection (localhost, default port)
redis_conn = Redis(host='localhost', port=6379, db=0, decode_responses=False)

# Create separate queues for each AI processing step
q_step1 = Queue('ftg_ai_step1', connection=redis_conn, default_timeout=1800) # 30 min (sampling)
q_step2 = Queue('ftg_ai_step2', connection=redis_conn, default_timeout=1800) # 30 min (Gemini)
q_step3 = Queue('ftg_ai_step3', connection=redis_conn, default_timeout=1200) # 20 min (frame creation)
q_step4 = Queue('ftg_ai_step4', connection=redis_conn, default_timeout=600)  # 10 min (transcription)

# Helper functions
def tprint(message):
    """Thread-safe print with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def run_script(script_name, footage_id, token):
    """Run a job script and return success status."""
    try:
        script_path = Path(__file__).resolve().parent / script_name
        
        if not script_path.exists():
            tprint(f"  -> ❌ Script not found: {script_path}")
            return False
        
        cmd = ["python3", str(script_path), footage_id]
        
        # Set environment for scripts
        env = os.environ.copy()
        env['FM_TOKEN'] = token
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min max per script
            env=env
        )
        
        if result.returncode == 0:
            return True
        else:
            tprint(f"  -> ❌ Script failed: {result.stderr[:200]}")
            return False
            
    except subprocess.TimeoutExpired:
        tprint(f"  -> ⏱️ Script timeout: {script_name}")
        return False
    except Exception as e:
        tprint(f"  -> ❌ Error running script: {e}")
        return False

def update_status(footage_id, token, new_status, max_retries=3):
    """Update FileMaker status with retry logic."""
    import requests
    import time
    
    current_token = token
    
    for attempt in range(max_retries):
        try:
            # Find record ID
            record_id = config.find_record_id(
                current_token,
                "FOOTAGE",
                {FIELD_MAPPING["footage_id"]: footage_id}
            )
            
            if not record_id:
                tprint(f"  -> ❌ Record not found: {footage_id}")
                return False
            
            # Update status
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
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
        except Exception as e:
            tprint(f"  -> ❌ Error updating status: {e}")
            return False
    
    return False

def check_false_start(footage_id, token):
    """
    Check if a record is a false start (< 5 seconds).
    Prevents accidental AI processing of false starts.
    """
    import requests
    import re
    
    try:
        record_id = config.find_record_id(
            token,
            "FOOTAGE",
            {FIELD_MAPPING["footage_id"]: footage_id}
        )
        
        if not record_id:
            return False
        
        response = requests.get(
            config.url(f"layouts/FOOTAGE/records/{record_id}"),
            headers=config.api_headers(token),
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()['response']['data'][0]['fieldData']
            
            # Check description first (if Part A already marked it)
            description = data.get(FIELD_MAPPING["description"], "")
            if description == "False start":
                return True
            
            # Check actual duration (for edge cases)
            duration_tc = data.get("SPECS_File_Duration_Timecode", "")
            if duration_tc:
                # Parse timecode format: HH:MM:SS:FF
                match = re.match(r'(\d+):(\d+):(\d+):(\d+)', duration_tc)
                if match:
                    hours, minutes, seconds, frames = map(int, match.groups())
                    # Assume 24fps as default
                    total_seconds = hours * 3600 + minutes * 60 + seconds + (frames / 24.0)
                    
                    if total_seconds < 5.0:
                        tprint(f"  -> False start detected by duration: {total_seconds:.2f}s")
                        return True
            
            return False
        
        return False
        
    except Exception as e:
        tprint(f"  -> Warning: Could not check false start status: {e}")
        return False

def check_audio_transcription_pending(footage_id, token):
    """Check if audio transcription is pending for this footage."""
    import os
    
    try:
        # Check if background transcription file exists
        temp_dir = "/private/tmp"
        assessment_file = os.path.join(temp_dir, f"{footage_id}_assessment.json")
        
        if os.path.exists(assessment_file):
            import json
            with open(assessment_file, 'r') as f:
                assessment_data = json.load(f)
            
            return assessment_data.get("has_audio", False)
        
        return False
        
    except Exception as e:
        tprint(f"  -> Warning: Could not check audio transcription status: {e}")
        return False

# =============================================================================
# JOB DEFINITIONS
# =============================================================================

def job_step1_assess(footage_id, token):
    """
    Step 1: Assess and Sample Frames
    Status: 3 - Ready for AI → 4 - Frames Sampled
    
    FALSE START PROTECTION: Blocks processing if video < 5 seconds
    """
    tprint(f"🔵 Step 1 Starting: {footage_id} (Assess & Sample)")
    
    # Check for false start FIRST (critical protection)
    is_false_start = check_false_start(footage_id, token)
    if is_false_start:
        # Block AI processing for false starts
        if update_status(footage_id, token, "False Start"):
            tprint(f"🛑 Step 1 Blocked: {footage_id} (FALSE START - cannot process for AI)")
            return {"status": "blocked", "next": None, "false_start": True}
        else:
            tprint(f"⚠️ False start detected but status update failed: {footage_id}")
            return {"status": "partial", "next": None}
    
    success = run_script("ftg_autolog_B_01_assess_and_sample.py", footage_id, token)
    
    if success:
        # Set to "4 - Frames Sampled" (indicates Step 2 is queued)
        if update_status(footage_id, token, "4 - Frames Sampled"):
            tprint(f"✅ Step 1 Complete: {footage_id} (Queuing Step 2)")
            # Queue Step 2
            q_step2.enqueue(job_step2_gemini, footage_id, token)
            return {"status": "success", "next": "step2"}
        else:
            tprint(f"⚠️ Step 1 work done but status update failed: {footage_id}")
            return {"status": "partial", "next": None}
    else:
        tprint(f"❌ Step 1 Failed: {footage_id}")
        return {"status": "failed", "next": None}

def job_step2_gemini(footage_id, token):
    """
    Step 2: Gemini Multi-Image Analysis
    Status: 4 - Frames Sampled → 5 - AI Analysis Complete
    """
    tprint(f"🔵 Step 2 Starting: {footage_id} (Gemini Analysis)")
    
    success = run_script("ftg_autolog_B_02_gemini_analysis.py", footage_id, token)
    
    if success:
        if update_status(footage_id, token, "5 - AI Analysis Complete"):
            tprint(f"✅ Step 2 Complete: {footage_id} (Queuing Step 3)")
            # Queue Step 3
            q_step3.enqueue(job_step3_create_frames, footage_id, token)
            return {"status": "success", "next": "step3"}
        else:
            tprint(f"⚠️ Step 2 work done but status update failed: {footage_id}")
            return {"status": "partial", "next": None}
    else:
        tprint(f"❌ Step 2 Failed: {footage_id}")
        return {"status": "failed", "next": None}

def job_step3_create_frames(footage_id, token):
    """
    Step 3: Create Frame Records from Gemini Data
    Status: 5 - AI Analysis Complete → 6 - Frames Created OR 7 - Avid Description
    
    Note: Goes directly to "7 - Avid Description" if no audio.
    If audio present, queues Step 4 but status already set to "7".
    """
    tprint(f"🔵 Step 3 Starting: {footage_id} (Create Frame Records)")
    
    success = run_script("ftg_autolog_B_03_create_frames.py", footage_id, token)
    
    if success:
        # Check if audio transcription is pending
        has_pending_audio = check_audio_transcription_pending(footage_id, token)
        
        # Always set to "7 - Avid Description" (final status - triggers FM server scripts)
        if update_status(footage_id, token, "7 - Avid Description"):
            if has_pending_audio:
                # Queue Step 4 (audio transcription) - runs in background
                tprint(f"✅ Step 3 Complete: {footage_id} (Queueing audio transcription)")
                q_step4.enqueue(job_step4_transcribe_audio, footage_id, token)
                return {"status": "success", "next": "step4"}
            else:
                tprint(f"✅ Step 3 Complete: {footage_id} (No audio)")
                return {"status": "success", "next": "complete"}
        else:
            tprint(f"⚠️ Step 3 work done but status update failed: {footage_id}")
            return {"status": "partial", "next": None}
    else:
        tprint(f"❌ Step 3 Failed: {footage_id}")
        return {"status": "failed", "next": None}

def job_step4_transcribe_audio(footage_id, token):
    """
    Step 4: Map Audio Transcription to Frame Records
    Status: 7 - Avid Description (no change - already set by Step 3)
    
    Note: This step runs in background to populate audio transcription data.
    Status remains at "7 - Avid Description" throughout.
    """
    tprint(f"🔵 Step 4 Starting: {footage_id} (Map Audio Transcription)")
    
    success = run_script("ftg_autolog_B_04_transcribe_audio.py", footage_id, token)
    
    if success:
        tprint(f"✅ Step 4 Complete: {footage_id} (Audio transcription mapped)")
        return {"status": "success", "next": "complete"}
    else:
        tprint(f"❌ Step 4 Failed: {footage_id} (Audio transcription incomplete)")
        return {"status": "failed", "next": None}

# =============================================================================
# BATCH QUEUEING FUNCTIONS
# =============================================================================

def queue_ftg_ai_batch(footage_ids, token=None):
    """Queue multiple items for AI processing at Step 1."""
    if token is None:
        token = config.get_token()
    
    job_ids = []
    for footage_id in footage_ids:
        job = q_step1.enqueue(job_step1_assess, footage_id, token)
        job_ids.append(job.id)
        tprint(f"📥 Queued: {footage_id} → {job.id}")
    
    return job_ids

def queue_ftg_ai_item(footage_id, token=None):
    """Queue a single item for AI processing at Step 1."""
    if token is None:
        token = config.get_token()
    
    job = q_step1.enqueue(job_step1_assess, footage_id, token)
    tprint(f"📥 Queued: {footage_id} → {job.id}")
    return job.id

if __name__ == "__main__":
    tprint("✅ Footage AI Processing Job Queue System Loaded")
    tprint(f"📊 Queue Status:")
    tprint(f"  - Step 1 (Assess): {len(q_step1)} queued")
    tprint(f"  - Step 2 (Gemini): {len(q_step2)} queued")
    tprint(f"  - Step 3 (Create Frames): {len(q_step3)} queued")
    tprint(f"  - Step 4 (Transcription): {len(q_step4)} queued")

