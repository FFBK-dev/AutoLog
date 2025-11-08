#!/usr/bin/env python3
"""
LF AutoLog Job Queue Definitions (Redis + Python RQ)

This module defines all 6 LF AutoLog workflow steps as RQ jobs.
Each job:
- Executes its script
- Updates FileMaker status on success
- Queues the next step automatically
- No race conditions (status only updates after work completes)
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
    "footage_id": "INFO_FTG_ID"
}

# Redis connection (localhost, default port)
redis_conn = Redis(host='localhost', port=6379, db=0, decode_responses=False)

# Create separate queues for each step
q_step1 = Queue('lf_step1', connection=redis_conn, default_timeout=600)  # 10 min
q_step2 = Queue('lf_step2', connection=redis_conn, default_timeout=600)  # 10 min
q_step3 = Queue('lf_step3', connection=redis_conn, default_timeout=1800) # 30 min (sampling)
q_step4 = Queue('lf_step4', connection=redis_conn, default_timeout=1800) # 30 min (Gemini)
q_step5 = Queue('lf_step5', connection=redis_conn, default_timeout=1200) # 20 min (frame creation)
q_step6 = Queue('lf_step6', connection=redis_conn, default_timeout=600)  # 10 min (transcription)

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
            payload = {
                "fieldData": {
                    FIELD_MAPPING["status"]: new_status
                }
            }
            
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
            return False
        except Exception as e:
            tprint(f"  -> ❌ Status update error: {e}")
            return False
    
    return False

# ============================================================================
# JOB DEFINITIONS (Steps 1-6)
# ============================================================================

def job_step1_file_info(footage_id, token):
    """
    Step 1: Get File Info
    Status: 0 - Pending File Info → 1 - File Info Complete
    Note: False starts are detected but still continue to Step 2 for thumbnails
    """
    tprint(f"🔵 Step 1 Starting: {footage_id} (Get File Info)")
    
    success = run_script("lf_autolog_01_get_file_info.py", footage_id, token)
    
    if success:
        # Always continue to Step 2 (even for false starts - they need thumbnails)
        if update_status(footage_id, token, "1 - File Info Complete"):
            # Check if false start for logging purposes
            is_false_start = check_false_start(footage_id, token)
            if is_false_start:
                tprint(f"✅ Step 1 Complete: {footage_id} (FALSE START detected - will get thumbnail then complete)")
            else:
                tprint(f"✅ Step 1 Complete: {footage_id}")
            
            # Queue Step 2
            q_step2.enqueue(job_step2_thumbnail, footage_id, token)
            return {"status": "success", "next": "step2"}
        else:
            tprint(f"⚠️ Step 1 work done but status update failed: {footage_id}")
            return {"status": "partial", "next": None}
    else:
        tprint(f"❌ Step 1 Failed: {footage_id}")
        return {"status": "failed", "next": None}

def job_step2_thumbnail(footage_id, token):
    """
    Step 2: Generate Thumbnails
    Status: 1 - File Info Complete → 3 - Creating Frames OR 10 - Complete (false start)
    Note: Sets status to "3 - Creating Frames" when queuing Step 3 (not "2 - Thumbnails Complete")
    """
    tprint(f"🔵 Step 2 Starting: {footage_id} (Generate Thumbnails)")
    
    success = run_script("lf_autolog_02_generate_thumbnails.py", footage_id, token)
    
    if success:
        # Check if this is a false start
        is_false_start = check_false_start(footage_id, token)
        
        if is_false_start:
            # False start: Has thumbnail now, mark complete and skip rest of workflow
            if update_status(footage_id, token, "10 - Complete"):
                tprint(f"✅ Step 2 Complete: {footage_id} (FALSE START - marked complete)")
                return {"status": "success", "next": "complete", "false_start": True}
            else:
                tprint(f"⚠️ Step 2 work done but status update failed: {footage_id}")
                return {"status": "partial", "next": None}
        else:
            # Normal flow: Set to "3 - Creating Frames" (indicates Step 3 is queued)
            if update_status(footage_id, token, "3 - Creating Frames"):
                tprint(f"✅ Step 2 Complete: {footage_id} (Queuing Step 3)")
                # Queue Step 3
                q_step3.enqueue(job_step3_assess, footage_id, token)
                return {"status": "success", "next": "step3"}
            else:
                tprint(f"⚠️ Step 2 work done but status update failed: {footage_id}")
                return {"status": "partial", "next": None}
    else:
        tprint(f"❌ Step 2 Failed: {footage_id}")
        return {"status": "failed", "next": None}

def job_step3_assess(footage_id, token):
    """
    Step 3: Assess and Sample Frames
    Status: 3 - Creating Frames → Awaiting User Input OR 5 - Processing Frame Info
    
    Special handling:
    - False starts: Skip immediately to "10 - Complete"
    - Normal flow: Ends at "Awaiting User Input" (waits for user prompt)
    - Force Resume: Continues to Step 4 (5 - Processing Frame Info)
    """
    tprint(f"🔵 Step 3 Starting: {footage_id} (Assess & Sample)")
    
    # Check for false start first (catches Force Resume false starts)
    is_false_start = check_false_start(footage_id, token)
    if is_false_start:
        # False start came through Force Resume - skip to complete
        if update_status(footage_id, token, "10 - Complete"):
            tprint(f"⚠️ Step 3 Skipped: {footage_id} (FALSE START - marked complete)")
            return {"status": "success", "next": "complete", "false_start": True}
        else:
            tprint(f"⚠️ False start detected but status update failed: {footage_id}")
            return {"status": "partial", "next": None}
    
    success = run_script("lf_autolog_03_assess_and_sample.py", footage_id, token)
    
    if success:
        # Check if this is Force Resume
        is_force_resume = check_force_resume(footage_id, token)
        
        if is_force_resume:
            # Force Resume: Set to "5 - Processing Frame Info" (indicates Step 4 is queued)
            if update_status(footage_id, token, "5 - Processing Frame Info"):
                tprint(f"✅ Step 3 Complete (Force Resume): {footage_id} (Queuing Step 4)")
                # Queue Step 4 immediately
                q_step4.enqueue(job_step4_gemini, footage_id, token)
                return {"status": "success", "next": "step4", "force_resume": True}
            else:
                tprint(f"⚠️ Step 3 work done but status update failed: {footage_id}")
                return {"status": "partial", "next": None}
        else:
            # Normal flow: Halt at Awaiting User Input
            if update_status(footage_id, token, "Awaiting User Input"):
                tprint(f"⏸️ Step 3 Halted: {footage_id} (Awaiting User Input)")
                return {"status": "success", "next": "awaiting_input"}
            else:
                tprint(f"⚠️ Step 3 work done but status update failed: {footage_id}")
                return {"status": "partial", "next": None}
    else:
        tprint(f"❌ Step 3 Failed: {footage_id}")
        return {"status": "failed", "next": None}

def job_step4_gemini(footage_id, token):
    """
    Step 4: Gemini Multi-Image Analysis
    Status: 5 - Processing Frame Info → 6 - Generating Description
    Note: Sets status to "6" (indicates Step 5 is queued to create frame records)
    """
    tprint(f"🔵 Step 4 Starting: {footage_id} (Gemini Analysis)")
    
    success = run_script("lf_autolog_04_gemini_analysis.py", footage_id, token)
    
    if success:
        if update_status(footage_id, token, "6 - Generating Description"):
            tprint(f"✅ Step 4 Complete: {footage_id} (Queuing Step 5)")
            # Queue Step 5
            q_step5.enqueue(job_step5_create_frames, footage_id, token)
            return {"status": "success", "next": "step5"}
        else:
            tprint(f"⚠️ Step 4 work done but status update failed: {footage_id}")
            return {"status": "partial", "next": None}
    else:
        tprint(f"❌ Step 4 Failed: {footage_id}")
        return {"status": "failed", "next": None}

def job_step5_create_frames(footage_id, token):
    """
    Step 5: Create Frame Records from Gemini Data
    Status: 6 - Generating Description → 7 - Avid Description
    
    Note: Always sets to "7 - Avid Description" (final status).
    If audio transcription is pending, Step 6 runs in background without changing status.
    """
    tprint(f"🔵 Step 5 Starting: {footage_id} (Create Frame Records)")
    
    success = run_script("lf_autolog_05_create_frames.py", footage_id, token)
    
    if success:
        # Check if audio transcription is pending
        has_pending_audio = check_audio_transcription_pending(footage_id, token)
        
        # Always set to final status "7 - Avid Description"
        if update_status(footage_id, token, "7 - Avid Description"):
            if has_pending_audio:
                # Queue Step 6 (audio transcription mapping) - runs in background
                tprint(f"✅ Step 5 Complete: {footage_id} (Queueing audio transcription)")
                q_step6.enqueue(job_step6_transcribe_audio, footage_id, token)
                return {"status": "success", "next": "step6"}
            else:
                tprint(f"✅ Step 5 Complete: {footage_id} (No audio)")
                return {"status": "success", "next": "complete"}
        else:
            tprint(f"⚠️ Step 5 work done but status update failed: {footage_id}")
            return {"status": "partial", "next": None}
    else:
        tprint(f"❌ Step 5 Failed: {footage_id}")
        return {"status": "failed", "next": None}

def job_step6_transcribe_audio(footage_id, token):
    """
    Step 6: Map Audio Transcription to Frame Records
    Status: 7 - Avid Description (no change - already set by Step 5)
    
    Note: This step runs in background to populate audio transcription data.
    Status remains at "7 - Avid Description" throughout.
    """
    tprint(f"🔵 Step 6 Starting: {footage_id} (Map Audio Transcription)")
    
    success = run_script("lf_autolog_06_transcribe_audio.py", footage_id, token)
    
    if success:
        tprint(f"✅ Step 6 Complete: {footage_id} (Audio transcription mapped)")
        return {"status": "success", "next": "complete"}
    else:
        tprint(f"❌ Step 6 Failed: {footage_id} (Audio transcription incomplete)")
        return {"status": "failed", "next": None}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def check_force_resume(footage_id, token):
    """Check if a record was marked as Force Resume."""
    import requests
    
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
            status = data.get(FIELD_MAPPING["status"], "")
            return status == "Force Resume"
        
        return False
        
    except Exception as e:
        tprint(f"  -> Warning: Could not check Force Resume status: {e}")
        return False

def check_false_start(footage_id, token):
    """Check if a record is a false start (< 5 seconds) by checking actual duration."""
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
            
            # Check description first (if Step 1 already marked it)
            description = data.get("INFO_Description", "")
            if description == "False start":
                return True
            
            # Check actual duration (for Force Resume items)
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
    """Check if audio transcription is still pending (exists but not complete)."""
    try:
        assessment_dir = f"/tmp/lf_autolog_assessment"
        assessment_file = Path(assessment_dir) / f"{footage_id}_assessment.json"
        
        if not assessment_file.exists():
            return False
        
        import json
        with open(assessment_file, 'r') as f:
            assessment = json.load(f)
        
        # If has_audio is True and transcription process was started
        if assessment.get('has_audio', False):
            transcript_file = Path(assessment_dir) / f"{footage_id}_transcript.json"
            # If transcript file doesn't exist yet, transcription is still pending
            return not transcript_file.exists()
        
        return False
        
    except Exception as e:
        tprint(f"  -> Warning: Could not check audio transcription status: {e}")
        return False

# ============================================================================
# BATCH OPERATIONS
# ============================================================================

def queue_lf_batch(footage_ids, token=None):
    """Queue multiple LF items for processing (Step 1)."""
    if token is None:
        token = config.get_token()
    
    job_ids = []
    for footage_id in footage_ids:
        if footage_id.startswith("LF"):
            job = q_step1.enqueue(job_step1_file_info, footage_id, token)
            job_ids.append(job.id)
            tprint(f"📥 Queued: {footage_id} → {job.id}")
    
    return job_ids

def queue_force_resume_batch(footage_ids, token=None):
    """Queue Force Resume items directly at Step 3."""
    if token is None:
        token = config.get_token()
    
    job_ids = []
    for footage_id in footage_ids:
        if footage_id.startswith("LF"):
            job = q_step3.enqueue(job_step3_assess, footage_id, token)
            job_ids.append(job.id)
            tprint(f"🔄 Queued (Force Resume): {footage_id} → {job.id}")
    
    return job_ids

if __name__ == "__main__":
    tprint("✅ LF AutoLog Job Queue System Loaded")
    tprint(f"📊 Queue Status:")
    tprint(f"  - Step 1 (File Info): {len(q_step1)} queued")
    tprint(f"  - Step 2 (Thumbnails): {len(q_step2)} queued")
    tprint(f"  - Step 3 (Assess): {len(q_step3)} queued")
    tprint(f"  - Step 4 (Gemini): {len(q_step4)} queued")
    tprint(f"  - Step 5 (Create Frames): {len(q_step5)} queued")
    tprint(f"  - Step 6 (Transcription): {len(q_step6)} queued")

