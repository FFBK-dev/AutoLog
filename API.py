#!/usr/bin/env python3
"""
FileMaker Automation API Server

This API server provides:
1. Manual job submission via endpoints  
2. Job tracking and monitoring
3. Automatic pending item discovery
4. Resilient error handling
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Body
import logging
import warnings
import subprocess
import os
import sys
import time
import threading
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import requests

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

# Add the parent directory to Python path for imports
sys.path.append(str(Path(__file__).resolve().parent))

import config

# Initialize the FastAPI app
app = FastAPI(title="FileMaker Automation API", version="2.0.0")

# Job tracking
class JobTracker:
    def __init__(self):
        self.jobs_submitted = 0
        self.jobs_completed = 0
        self.current_jobs = {}
        self.lock = threading.Lock()
    
    def submit_job(self, job_name: str, args: list) -> str:
        with self.lock:
            job_id = f"{job_name}_{self.jobs_submitted}_{int(time.time())}"
            self.jobs_submitted += 1
            self.current_jobs[job_id] = {
                "job_name": job_name,
                "args": args,
                "submitted_at": datetime.now(),
                "status": "running"
            }
            return job_id
    
    def complete_job(self, job_id: str, success: bool = True):
        with self.lock:
            if job_id in self.current_jobs:
                self.current_jobs[job_id]["status"] = "completed" if success else "failed"
                self.current_jobs[job_id]["completed_at"] = datetime.now()
                self.jobs_completed += 1
    
    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            running_jobs = [job for job in self.current_jobs.values() if job["status"] == "running"]
            return {
                "total_submitted": self.jobs_submitted,
                "total_completed": self.jobs_completed,
                "currently_running": len(running_jobs),
                "running_jobs": running_jobs,
                "recent_jobs": list(self.current_jobs.values())[-10:]  # Last 10 jobs
            }

job_tracker = JobTracker()

# API Key validation (disabled for internal use)
def check_key(x_api_key: str = Header(None)):
    expected_key = os.getenv('FM_AUTOMATION_KEY', 'supersecret')
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

@app.on_event("startup")
async def startup_event():
    logging.info("🚀 Starting FileMaker Automation API")
    
    # Set up any startup tasks here
    logging.info("⚠️ Using direct OpenAI API calls")

@app.on_event("shutdown")
async def shutdown_event():
    logging.info("🔄 Shutting down FileMaker Automation API")

# Background task runner with enhanced logging
def run_job_with_tracking(job_id: str, cmd: List[str]):
    """Run a job with comprehensive tracking and logging."""
    try:
        logging.info(f"🚀 Starting {job_id}: {' '.join(cmd)}")
        
        # Run the job with timeout
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        # Process output for enhanced logging
        if result.stdout:
            for line in result.stdout.split('\n'):
                if line.strip():
                    # Log key workflow events
                    if "=== Starting AutoLog workflow for" in line:
                        item_id = line.split("for ")[-1].split(" ")[0]
                        logging.info(f"📋 {job_id} - Starting item: {item_id}")
                    elif "=== Workflow COMPLETED successfully for" in line:
                        item_id = line.split("for ")[-1].split(" ")[0]
                        logging.info(f"✅ {job_id} - Completed item: {item_id}")
                    elif "DEBUG:" in line and ("OpenAI" in line or "FileMaker" in line or "ERROR" in line):
                        logging.info(f"🔍 {job_id} - {line.strip()}")
        
        # Final summary
        if result.returncode == 0:
            logging.info(f"✅ {job_id} completed successfully")
        else:
            logging.error(f"❌ {job_id} failed with exit code {result.returncode}")
            # Log both stderr and stdout for complete error information
            if result.stderr:
                logging.error(f"❌ {job_id} stderr: {result.stderr}")
            if result.stdout:
                logging.error(f"❌ {job_id} stdout: {result.stdout}")
            
    except subprocess.TimeoutExpired:
        logging.error(f"⏱️ {job_id} timed out after 10 minutes")
    except Exception as e:
        logging.error(f"❌ {job_id} error: {str(e)}")
    finally:
        job_tracker.complete_job(job_id)

@app.get("/openai/usage")
def get_openai_usage():
    """Get OpenAI API usage statistics across all configured keys."""
    try:
        from utils.openai_client import global_openai_client
        
        if not global_openai_client.api_keys:
            return {
                "status": "no_keys_configured",
                "message": "No OpenAI API keys configured",
                "keys": []
            }
        
        stats = global_openai_client.get_usage_stats()
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "openai_keys": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting OpenAI usage: {str(e)}")

# Load OpenAI client for get_status endpoint
def load_openai_client():
    """Load the OpenAI client with API keys from FileMaker."""
    try:
        from utils.openai_client import global_openai_client
        
        token = config.get_token()
        
        # Get the OpenAI API keys from FileMaker globals
        api_keys = []
        for i in range(1, 6):  # Keys 1-5
            key = config.get_global(token, f"SystemGlobals_AutoLog_OpenAI_API_Key_{i}")
            if key and key.strip():
                api_keys.append(key.strip())
        
        if api_keys:
            global_openai_client.set_api_keys(api_keys)
            logging.info(f"🔑 Loaded {len(api_keys)} OpenAI API keys")
            return global_openai_client
        else:
            logging.warning("⚠️ No OpenAI API keys found in FileMaker globals")
            return None
            
    except Exception as e:
        logging.error(f"❌ Failed to load OpenAI client: {e}")
        return None

@app.get("/status")
def get_status():
    """Get the current status of the API server."""
    try:
        stats = job_tracker.get_stats()
        status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "jobs": stats,
            "server_info": {
                "python_version": sys.version,
                "server_start_time": datetime.now().isoformat()
            }
        }
        
        # Add OpenAI usage information
        try:
            from utils.openai_client import global_openai_client
            if global_openai_client.api_keys:
                openai_stats = global_openai_client.get_usage_stats()
                status["openai_keys"] = {
                    "available": True,
                    "total_keys": openai_stats["total_keys"],
                    "total_capacity": f"{openai_stats['total_capacity']:,} tokens/minute",
                    "current_utilization": f"{openai_stats['total_utilization_percent']:.1f}%"
                }
            else:
                status["openai_keys"] = {"available": False, "reason": "No keys configured"}
        except Exception as e:
            status["openai_keys"] = {"available": False, "reason": f"Error: {str(e)}"}
        
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting status: {str(e)}")

def load_openai_for_status():
    """Load OpenAI client specifically for status endpoint."""
    try:
        from utils.openai_client import global_openai_client
        
        token = config.get_token()
        
        api_keys = []
        for i in range(1, 6):
            key = config.get_global(token, f"SystemGlobals_AutoLog_OpenAI_API_Key_{i}")
            if key and key.strip():
                api_keys.append(key.strip())
        
        if api_keys:
            global_openai_client.set_api_keys(api_keys)
            return global_openai_client.get_usage_stats()
        else:
            return {"error": "No API keys configured"}
            
    except Exception as e:
        return {"error": f"Failed to load OpenAI status: {str(e)}"}

# Existing job execution endpoints (unchanged)
@app.post("/run/{job}")
def run_job(job: str, background_tasks: BackgroundTasks, payload: dict = Body({})):
    """Execute a job with tracking and background processing."""
    
    # Validate the job exists
    jobs_dir = Path(__file__).resolve().parent / "jobs"
    job_file = jobs_dir / f"{job}.py"
    
    if not job_file.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job}' not found")
    
    # Parse arguments from payload - support both formats
    args = []
    if 'args' in payload:
        # New format: {"args": ["arg1", "arg2"]}
        args = payload['args']
    else:
        # Legacy format: {"stills_id": "value"} or {"param1": "value1", "param2": "value2"}
        # For legacy compatibility, extract common parameter names
        legacy_params = ['stills_id', 'item_id', 'record_id']
        for param in legacy_params:
            if param in payload:
                args.append(payload[param])
                break  # Take the first matching parameter
    
    # Build command
    cmd = ["python3", str(job_file)] + args
    
    # Submit job for tracking
    job_id = job_tracker.submit_job(job, args)
    
    # Run job in background
    background_tasks.add_task(run_job_with_tracking, job_id, cmd)
    
    return {
        "job_id": job_id,
        "job_name": job,
        "args": args,
        "submitted": True,
        "status": "running"
    }

@app.get("/jobs")
def list_jobs():
    """List all available jobs."""
    jobs_dir = Path(__file__).resolve().parent / "jobs"
    if not jobs_dir.exists():
        return {"jobs": [], "error": "Jobs directory not found"}
    
    jobs = []
    for job_file in jobs_dir.glob("*.py"):
        if job_file.stem != "__init__":
            jobs.append(job_file.stem)
    
    return {"jobs": sorted(jobs)}

# Health check endpoint
@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    try:
        from utils.openai_client import global_openai_client
        openai_available = len(global_openai_client.api_keys) > 0
        openai_key_count = len(global_openai_client.api_keys)
    except:
        openai_available = False
        openai_key_count = 0
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "openai_keys_available": openai_available,
        "openai_key_count": openai_key_count
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)