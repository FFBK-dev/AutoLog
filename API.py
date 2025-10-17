#!/usr/bin/env python3
"""
FileMaker Automation API Server

This API server provides:
1. Manual job submission via endpoints  
2. Job tracking and monitoring
3. Automatic pending item discovery
4. Resilient error handling
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Body, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
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

# Initialize the FastAPI app with increased payload limits
app = FastAPI(
    title="FileMaker Automation API", 
    version="2.0.0",
    # Set generous limits for metadata export operations
    # This handles large batch exports from Avid panel
    docs_url="/docs",
    redoc_url="/redoc"
)

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
    
    def complete_job(self, job_id: str, success: bool = True, results: Dict[str, Any] = None):
        with self.lock:
            if job_id in self.current_jobs:
                self.current_jobs[job_id]["status"] = "completed" if success else "failed"
                self.current_jobs[job_id]["completed_at"] = datetime.now()
                if results:
                    self.current_jobs[job_id]["results"] = results
                self.jobs_completed += 1
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        with self.lock:
            if job_id in self.current_jobs:
                job_info = self.current_jobs[job_id].copy()
                # Convert datetime objects to ISO strings for JSON serialization
                job_info["submitted_at"] = job_info["submitted_at"].isoformat()
                if "completed_at" in job_info:
                    job_info["completed_at"] = job_info["completed_at"].isoformat()
                return job_info
            else:
                return None
    
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

# Configure CORS and payload handling for Avid panel integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middleware to handle large payloads gracefully
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response
import asyncio

class LargePayloadMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        # Log large payload requests for debugging
        if hasattr(request, 'headers'):
            content_length = request.headers.get('content-length')
            if content_length and int(content_length) > 1024 * 1024:  # > 1MB
                logging.info(f"📦 Large payload received: {int(content_length) / 1024 / 1024:.1f}MB from {request.client.host if request.client else 'unknown'}")
        
        response = await call_next(request)
        return response

app.add_middleware(LargePayloadMiddleware)

# API Key validation (optional for backward compatibility)
def check_key(x_api_key: str = Header(None)):
    # Allow requests without API key (backward compatibility)
    if x_api_key is None:
        return None
    
    # If API key is provided, it must match
    expected_key = os.getenv('FM_AUTOMATION_KEY', 'your_api_key_here')
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

@app.on_event("startup")
async def startup_event():
    logging.info("🚀 Starting FileMaker Automation API")
    
    # Mount required network volumes at startup
    logging.info("🔧 Mounting network volumes...")
    
    try:
        # Mount footage volume
        if config.mount_volume("footage"):
            logging.info("✅ Footage volume mounted successfully")
        else:
            logging.warning("⚠️ Failed to mount footage volume")
        
        # Mount stills volume  
        if config.mount_volume("stills"):
            logging.info("✅ Stills volume mounted successfully")
        else:
            logging.warning("⚠️ Failed to mount stills volume")
            
    except Exception as e:
        logging.error(f"❌ Error during volume mounting: {e}")
    
    # Set up any startup tasks here
    logging.info("⚠️ Using direct OpenAI API calls")

@app.on_event("shutdown")
async def shutdown_event():
    logging.info("🔄 Shutting down FileMaker Automation API")

# Helper function for synchronous metadata processing
def execute_metadata_query_sync(payload: dict):
    """Execute metadata query synchronously for small requests."""
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(payload, f)
        payload_file = f.name
    
    try:
        cmd = ["python3", str(Path(__file__).resolve().parent / "jobs" / "metadata-to-avid.py"), payload_file]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout for metadata queries
        )
        
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            error_output = result.stderr if result.stderr else result.stdout
            try:
                error_data = json.loads(error_output)
                raise HTTPException(status_code=500, detail=error_data.get("error", "Unknown error"))
            except json.JSONDecodeError:
                raise HTTPException(status_code=500, detail=f"Script error: {error_output}")
                
    finally:
        if os.path.exists(payload_file):
            os.unlink(payload_file)

# Helper function for synchronous metadata export
def execute_metadata_export_sync(payload: dict):
    """Execute metadata export synchronously for small requests."""
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(payload, f)
        payload_file = f.name
    
    try:
        cmd = ["python3", str(Path(__file__).resolve().parent / "jobs" / "metadata-from-avid.py"), payload_file]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout for metadata exports
        )
        
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            error_output = result.stderr if result.stderr else result.stdout
            try:
                error_data = json.loads(error_output)
                raise HTTPException(status_code=500, detail=error_data.get("error", "Unknown error"))
            except json.JSONDecodeError:
                raise HTTPException(status_code=500, detail=f"Script error: {error_output}")
                
    finally:
        if os.path.exists(payload_file):
            os.unlink(payload_file)

# Helper function for async metadata processing
def run_metadata_job_with_tracking(job_id: str, script_name: str, payload: dict):
    """Run metadata job with comprehensive tracking."""
    import tempfile
    
    try:
        logging.info(f"🚀 Starting metadata job {job_id}")
        
        # Create temporary payload file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(payload, f)
            payload_file = f.name
        
        try:
            cmd = ["python3", str(Path(__file__).resolve().parent / "jobs" / script_name), payload_file]
            
            # Dynamic timeout based on payload size
            total_items = 0
            if 'identifiers' in payload:
                total_items = len(payload['identifiers'])
            elif 'assets' in payload:
                total_items = len(payload['assets'])
            
            # Scale timeout: 2s per item, minimum 5min, maximum 20min
            base_timeout = 300  # 5 minutes
            per_item_time = 2   # 2 seconds per item
            max_timeout = 1200  # 20 minutes
            
            timeout = min(max_timeout, max(base_timeout, total_items * per_item_time))
            logging.info(f"📊 {job_id} - Processing {total_items} items with {timeout}s timeout")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout  # Dynamic timeout based on load size
            )
            
            success = result.returncode == 0
            job_results = None
            
            if success:
                try:
                    job_results = json.loads(result.stdout)
                    result_count = len(job_results.get('results', []))
                    logging.info(f"✅ {job_id} completed successfully - processed {result_count} items")
                except json.JSONDecodeError:
                    logging.warning(f"⚠️ {job_id} completed but could not parse results")
                    success = False
            else:
                logging.error(f"❌ {job_id} failed with exit code {result.returncode}")
                if result.stderr:
                    logging.error(f"❌ {job_id} stderr: {result.stderr}")
            
            job_tracker.complete_job(job_id, success, job_results)
            
        finally:
            # Clean up temporary file
            if os.path.exists(payload_file):
                os.unlink(payload_file)
                
    except subprocess.TimeoutExpired:
        logging.error(f"⏱️ {job_id} timed out after 5 minutes")
        job_tracker.complete_job(job_id, False, {"error": "Operation timed out"})
    except Exception as e:
        logging.error(f"❌ {job_id} error: {str(e)}")
        job_tracker.complete_job(job_id, False, {"error": str(e)})

# Background task runner with enhanced logging
def run_job_with_tracking(job_id: str, cmd: List[str]):
    """Run a job with comprehensive tracking and logging."""
    # Check if this is the polling script - show more detailed output
    is_polling_script = any("footage_autolog" in str(c) for c in cmd)
    
    process = None
    try:
        logging.info(f"🚀 Starting {job_id}: {' '.join(cmd)}")
        
        # Run the job with timeout (longer for polling script)
        timeout = 3600 if is_polling_script else 600  # 1 hour for polling, 10 min for others
        
        if is_polling_script:
            # Use real-time streaming for polling scripts
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'  # Force Python to use unbuffered output
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
                env=env
            )
            
            # Stream output in real-time
            try:
                for line in iter(process.stdout.readline, ''):
                    if line.strip():
                        skip_line = any(pattern in line for pattern in [
                            "warnings.warn(",
                            "urllib3",
                            "site-packages",
                            "/Library/",
                            "DeprecationWarning"
                        ])
                        
                        if not skip_line:
                            logging.info(f"🔄 {job_id} - {line.strip()}")
            except Exception as stream_e:
                logging.error(f"❌ {job_id} streaming error: {stream_e}")
            
            return_code = process.wait(timeout=timeout)
            
        else:
            # Use traditional capture for other scripts
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return_code = result.returncode
            
            # Process output for enhanced logging
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        # Log key workflow events for other scripts
                        if "=== Starting AutoLog workflow for" in line:
                            item_id = line.split("for ")[-1].split(" ")[0]
                            logging.info(f"📋 {job_id} - Starting item: {item_id}")
                        elif "=== Workflow COMPLETED successfully for" in line:
                            item_id = line.split("for ")[-1].split(" ")[0]
                            logging.info(f"✅ {job_id} - Completed item: {item_id}")
                        elif "DEBUG:" in line and ("OpenAI" in line or "FileMaker" in line or "ERROR" in line):
                            logging.info(f"🔍 {job_id} - {line.strip()}")
            
            if result.stderr:
                # Filter out urllib3 LibreSSL warnings from stderr
                filtered_stderr = '\n'.join([
                    line for line in result.stderr.split('\n')
                    if not any(pattern in line for pattern in [
                        "urllib3/__init__.py",
                        "NotOpenSSLWarning",
                        "urllib3 v2 only supports OpenSSL",
                        "warnings.warn("
                    ])
                ]).strip()
                
                if filtered_stderr:
                    logging.error(f"❌ {job_id} stderr: {filtered_stderr}")
        
        # Final summary and results capture
        job_results = None
        success = return_code == 0
        
        # For avid-search and avid-find-similar jobs, capture JSON results from stdout
        if success and (job_id.startswith("avid-search") or job_id.startswith("avid-find-similar")) and not is_polling_script:
            try:
                if result.stdout:
                    # Look for JSON results in the output
                    lines = result.stdout.split('\n')
                    json_capture = False
                    json_lines = []
                    
                    for line in lines:
                        if line.strip() == "📊 JSON Results:":
                            json_capture = True
                            continue
                        elif json_capture:
                            if line.strip() and line.strip().startswith('{'):
                                json_lines.append(line)
                            elif line.strip() and not line.strip().startswith('{') and json_lines:
                                json_lines.append(line)
                            elif not line.strip() and json_lines:
                                break
                    
                    if json_lines:
                        json_str = '\n'.join(json_lines)
                        job_results = json.loads(json_str)
                        # Handle different result formats for different job types
                        if 'ranked_results' in job_results:
                            result_count = len(job_results.get('ranked_results', []))
                        elif 'similar_items' in job_results:
                            result_count = len(job_results.get('similar_items', []))
                        else:
                            result_count = 0
                        logging.info(f"📊 {job_id} - Captured {result_count} results")
                        
            except Exception as json_e:
                logging.warning(f"⚠️ {job_id} - Could not parse JSON results: {json_e}")
        
        if success:
            logging.info(f"✅ {job_id} completed successfully")
        else:
            logging.error(f"❌ {job_id} failed with exit code {return_code}")
            
    except subprocess.TimeoutExpired:
        timeout_msg = "1 hour" if is_polling_script else "10 minutes"
        logging.error(f"⏱️ {job_id} timed out after {timeout_msg}")
        if process:
            process.kill()
            process.wait()
        success = False
    except Exception as e:
        logging.error(f"❌ {job_id} error: {str(e)}")
        if process:
            process.kill()
            process.wait()
        success = False
    finally:
        if process and process.stdout:
            process.stdout.close()
        job_tracker.complete_job(job_id, success, job_results)

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

@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    """Get status of a specific job for polling."""
    job_info = job_tracker.get_job_status(job_id)
    
    if not job_info:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Format response for Avid panel polling
    if job_info["status"] == "running":
        return {
            "job_id": job_id,
            "state": "processing",
            "progress": {"processed": 0, "total": 0},  # Could be enhanced with real progress
            "results": None,
            "error": None,
            "submitted_at": job_info["submitted_at"],
            "estimated_completion": None  # Could calculate based on job type
        }
    elif job_info["status"] == "completed":
        results = job_info.get("results", {})
        return {
            "job_id": job_id,
            "state": "completed",
            "progress": {"processed": len(results.get("results", [])), "total": len(results.get("results", []))},
            "results": results,
            "error": None,
            "submitted_at": job_info["submitted_at"],
            "completed_at": job_info.get("completed_at")
        }
    else:  # failed
        return {
            "job_id": job_id,
            "state": "failed",
            "progress": {"processed": 0, "total": 0},
            "results": None,
            "error": job_info.get("results", {}).get("error", "Unknown error"),
            "submitted_at": job_info["submitted_at"],
            "completed_at": job_info.get("completed_at")
        }

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
    
    # Special handling for footage_autolog to support polling parameters
    if job == "footage_autolog":
        duration = payload.get('duration', 3600)  # Default: 1 hour
        interval = payload.get('interval', 10)    # Default: 10 seconds (fast polling)
        
        def run_footage_autolog():
            """Run footage_autolog with environment variables and real-time streaming."""
            env = os.environ.copy()
            env['POLL_DURATION'] = str(duration)
            env['POLL_INTERVAL'] = str(interval)
            env['PYTHONUNBUFFERED'] = '1'  # Force Python to use unbuffered output
            
            process = None
            try:
                logging.info(f"🚀 Starting {job_id}: {' '.join(cmd)} (duration={duration}s, interval={interval}s)")
                
                # Use Popen for real-time streaming
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Merge stderr into stdout
                    text=True,
                    bufsize=1,  # Line buffered
                    universal_newlines=True,
                    env=env
                )
                
                # Stream output in real-time
                try:
                    logging.info(f"🔄 {job_id} - Starting real-time output streaming...")
                    line_count = 0
                    for line in iter(process.stdout.readline, ''):
                        line_count += 1
                        if line.strip():
                            # Filter out verbose traces
                            skip_line = any(pattern in line for pattern in [
                                "warnings.warn(",
                                "urllib3",
                                "site-packages", 
                                "/Library/",
                                "DeprecationWarning"
                            ])
                            
                            if not skip_line:
                                logging.info(f"🔄 {job_id} - {line.strip()}")
                        elif line_count % 100 == 0:  # Debug: Show we're getting empty lines too
                            logging.info(f"🔄 {job_id} - [DEBUG] Read {line_count} lines from process...")
                    
                    logging.info(f"🔄 {job_id} - Finished streaming output (total lines: {line_count})")
                except Exception as stream_e:
                    logging.error(f"❌ {job_id} streaming error: {stream_e}")
                
                # Wait for process completion
                return_code = process.wait(timeout=duration + 300)
                
                if return_code == 0:
                    logging.info(f"✅ {job_id} completed successfully")
                else:
                    logging.error(f"❌ {job_id} failed with exit code {return_code}")
                        
            except subprocess.TimeoutExpired:
                logging.error(f"⏱️ {job_id} timed out")
                if process:
                    process.kill()
                    process.wait()
            except Exception as e:
                logging.error(f"❌ {job_id} error: {str(e)}")
                if process:
                    process.kill()
                    process.wait()
            finally:
                if process and process.stdout:
                    process.stdout.close()
                job_tracker.complete_job(job_id)
        
        background_tasks.add_task(run_footage_autolog)
    else:
        # Run job in background (normal jobs)
        background_tasks.add_task(run_job_with_tracking, job_id, cmd)
    
    # Build response
    response = {
        "job_id": job_id,
        "job_name": job,
        "args": args,
        "submitted": True,
        "status": "running"
    }
    
    # Add polling parameters for footage_autolog
    if job == "footage_autolog":
        duration = payload.get('duration', 3600)
        interval = payload.get('interval', 30)
        response.update({
            "poll_duration": duration,
            "poll_interval": interval,
            "message": f"Polling workflow started for {duration}s with {interval}s intervals (faster response mode)"
        })
    
    return response

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

@app.get("/job/{job_id}")
def get_job_status(job_id: str):
    """Get the status and details of a specific job."""
    job_info = job_tracker.get_job_status(job_id)
    
    if job_info is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    return job_info

# Health check endpoint
# Polling workflow endpoint
@app.post("/poll/footage")
def start_polling_workflow(background_tasks: BackgroundTasks, payload: dict = Body({})):
    """Start the polling-based footage workflow that continuously processes records by status."""
    
    # Parse polling parameters
    poll_duration = payload.get('duration', 3600)  # Default: 1 hour
    poll_interval = payload.get('interval', 10)    # Default: 10 seconds (fast polling)
    
    # Validate parameters
    if poll_duration < 60 or poll_duration > 28800:  # 1 minute to 8 hours
        raise HTTPException(status_code=400, detail="Duration must be between 60 and 28800 seconds (1 minute to 8 hours)")
    
    if poll_interval < 5 or poll_interval > 300:  # 5 seconds to 5 minutes
        raise HTTPException(status_code=400, detail="Interval must be between 5 and 300 seconds")
    
    # Build command for polling workflow
    cmd = [
        "python3", 
        str(Path(__file__).resolve().parent / "jobs" / "footage_autolog_00_run_all.py")
    ]
    
    # Set environment variables for polling parameters
    env = os.environ.copy()
    env['POLL_DURATION'] = str(poll_duration)
    env['POLL_INTERVAL'] = str(poll_interval)
    
    # Submit job for tracking
    job_id = job_tracker.submit_job("footage_polling", [f"duration={poll_duration}", f"interval={poll_interval}"])
    
    # Run polling workflow in background with custom environment
    def run_polling_job():
        process = None
        try:
            logging.info(f"🔄 Starting polling workflow {job_id} (duration={poll_duration}s, interval={poll_interval}s)")
            
            # Use real-time streaming for polling
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
                env=env
            )
            
            # Stream output in real-time
            try:
                for line in iter(process.stdout.readline, ''):
                    if line.strip():
                        # Show most polling script output (filter out only very verbose lines)
                        skip_line = any(pattern in line for pattern in [
                            "warnings.warn(",  # Skip warning traces
                            "urllib3",         # Skip urllib3 warnings
                            "site-packages"    # Skip package traces
                        ])
                        
                        if not skip_line:
                            logging.info(f"🔄 {job_id} - {line.strip()}")
            except Exception as stream_e:
                logging.error(f"❌ {job_id} streaming error: {stream_e}")
            
            return_code = process.wait(timeout=poll_duration + 300)
            
            if return_code == 0:
                logging.info(f"✅ {job_id} completed successfully")
            else:
                logging.error(f"❌ {job_id} failed with exit code {return_code}")
                    
        except subprocess.TimeoutExpired:
            logging.error(f"⏱️ {job_id} timed out")
            if process:
                process.kill()
                process.wait()
        except Exception as e:
            logging.error(f"❌ {job_id} error: {str(e)}")
            if process:
                process.kill()
                process.wait()
        finally:
            if process and process.stdout:
                process.stdout.close()
            job_tracker.complete_job(job_id)
    
    background_tasks.add_task(run_polling_job)
    
    return {
        "job_id": job_id,
        "job_name": "footage_polling",
        "poll_duration": poll_duration,
        "poll_interval": poll_interval,
        "submitted": True,
        "status": "running",
        "message": f"Polling workflow started for {poll_duration}s with {poll_interval}s intervals"
    }

# Music AutoLog Endpoint
@app.post("/run/music_autolog", dependencies=[Depends(check_key)])
def run_music_autolog(background_tasks: BackgroundTasks):
    """Execute Music AutoLog workflow for pending items."""
    
    # Build command for music autolog workflow
    cmd = [
        "python3", 
        str(Path(__file__).resolve().parent / "jobs" / "music_autolog_00_run_all.py")
    ]
    
    # Submit job for tracking
    job_id = job_tracker.submit_job("music_autolog", [])
    
    # Run in background
    background_tasks.add_task(run_job_with_tracking, job_id, cmd)
    
    return {
        "job_id": job_id,
        "job_name": "music_autolog",
        "submitted": True,
        "status": "running",
        "message": "Music AutoLog workflow started - processing pending items"
    }

# Metadata Bridge Endpoints for Avid Media Composer Integration

@app.post("/metadata-bridge/query")
def metadata_bridge_query(request: Request, background_tasks: BackgroundTasks, payload: dict = Body(...)):
    """
    Metadata bridge endpoint for FileMaker Pro → Avid Media Composer (metadata-to-avid)
    
    Accepts: { "media_type": "stills|archival|live_footage", "identifiers": ["id1", "id2"] }
    Returns: Metadata for the specified identifiers (async for large requests)
    """
    try:
        # Log the incoming request for debugging
        logging.info(f"🔍 Metadata bridge query received from {request.client.host}")
        logging.info(f"🔍 Payload received: {payload}")
        
        # Validate payload
        media_type = payload.get('media_type')
        identifiers = payload.get('identifiers', [])
        
        if not media_type:
            logging.error(f"❌ Missing media_type in payload: {payload}")
            raise HTTPException(status_code=400, detail="Missing media_type in payload")
        
        if not identifiers:
            logging.error(f"❌ Missing identifiers in payload: {payload}")
            raise HTTPException(status_code=400, detail="Missing identifiers in payload")
        
        # Decide between sync and async based on payload size
        if len(identifiers) > 10:  # Use async for large requests
            job_id = job_tracker.submit_job("metadata-query", [payload])
            
            # Run in background
            background_tasks.add_task(run_metadata_job_with_tracking, job_id, "metadata-to-avid.py", payload)
            
            return {
                "job_id": job_id,
                "processing": True,
                "total_identifiers": len(identifiers),
                "estimated_completion_seconds": len(identifiers) * 2,  # 2s per item estimate
                "poll_endpoint": f"/status/{job_id}",
                "message": f"Processing {len(identifiers)} {media_type} records asynchronously"
            }
        else:
            # Synchronous processing for small requests
            return execute_metadata_query_sync(payload)
                
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logging.error(f"❌ Metadata bridge query JSON decode error: {str(e)}")
        logging.error(f"❌ Raw payload that failed to parse: {payload}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    except Exception as e:
        logging.error(f"❌ Metadata bridge query error: {str(e)}")
        logging.error(f"❌ Error type: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/metadata-bridge/export")
def metadata_bridge_export(request: Request, background_tasks: BackgroundTasks, payload: dict = Body(...)):
    """
    Metadata bridge endpoint for Avid Media Composer → FileMaker Pro (metadata-from-avid)
    
    Accepts: { "media_type": "stills|archival|live_footage", "assets": [...] }
    Returns: Success confirmation with processing results
    
    Enhanced for large payload handling (up to 50MB)
    """
    try:
        # Enhanced logging for large payload debugging
        client_ip = request.client.host if request.client else "unknown"
        logging.info(f"🔍 Metadata bridge export received from {client_ip}")
        
        # Log payload size for debugging
        payload_size = len(str(payload))
        if payload_size > 1024:
            logging.info(f"📦 Payload size: {payload_size / 1024:.1f}KB")
        
        # Log essential info without dumping large payloads
        media_type = payload.get('media_type')
        assets = payload.get('assets', [])
        logging.info(f"📋 Media type: {media_type}, assets count: {len(assets)}")
        
        # Validate payload
        if not media_type:
            logging.error(f"❌ Missing media_type in payload")
            raise HTTPException(status_code=400, detail="Missing media_type in payload")
        
        if not assets:
            logging.error(f"❌ Missing assets in payload")
            raise HTTPException(status_code=400, detail="Missing assets in payload")
        
        # Validate reasonable limits (safety check)
        if len(assets) > 1000:  # Generous limit
            logging.error(f"❌ Too many assets: {len(assets)} (max 1000)")
            raise HTTPException(status_code=400, detail=f"Too many assets: {len(assets)}. Maximum 1000 per request.")
        
        # Decide between sync and async based on payload size
        if len(assets) > 10:  # Use async for large requests
            job_id = job_tracker.submit_job("metadata-export", [payload])
            
            # Run in background
            background_tasks.add_task(run_metadata_job_with_tracking, job_id, "metadata-from-avid.py", payload)
            
            return {
                "job_id": job_id,
                "processing": True,
                "total_assets": len(assets),
                "estimated_completion_seconds": len(assets) * 3,  # 3s per item estimate (updates are slower)
                "poll_endpoint": f"/status/{job_id}",
                "message": f"Processing {len(assets)} {media_type} updates asynchronously"
            }
        else:
            # Synchronous processing for small requests
            return execute_metadata_export_sync(payload)
                
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logging.error(f"❌ Metadata bridge export JSON decode error: {str(e)}")
        logging.error(f"❌ Raw payload that failed to parse: {payload}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    except Exception as e:
        logging.error(f"❌ Metadata bridge export error: {str(e)}")
        logging.error(f"❌ Error type: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/edl-export")
def edl_export(request: Request, payload: dict = Body(...)):
    """
    EDL Export endpoint for receiving EDL files from Avid Media Composer
    
    Accepts: { "edl_content": "TITLE: ...", "filename": "project.edl", "source": "avid_panel" }
    Returns: Success confirmation with storage location
    
    This endpoint receives EDL files and stores them for analysis and processing.
    """
    try:
        # Log the incoming request
        client_ip = request.client.host if request.client else "unknown"
        logging.info(f"🎬 EDL export received from {client_ip}")
        
        # Validate payload
        edl_content = payload.get('edl_content')
        filename = payload.get('filename', 'unknown.edl')
        source = payload.get('source', 'unknown')
        
        if not edl_content:
            logging.error(f"❌ Missing edl_content in payload")
            raise HTTPException(status_code=400, detail="Missing edl_content in payload")
        
        # Create EDL storage directory if it doesn't exist
        edl_storage_dir = Path(__file__).resolve().parent / "temp" / "edl_imports"
        edl_storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = filename.replace('/', '_').replace('\\', '_')
        unique_filename = f"{timestamp}_{source}_{safe_filename}"
        edl_file_path = edl_storage_dir / unique_filename
        
        # Store the EDL content
        with open(edl_file_path, 'w', encoding='utf-8') as f:
            f.write(edl_content)
        
        # Log storage details
        file_size = len(edl_content)
        logging.info(f"📁 EDL stored: {unique_filename} ({file_size} bytes)")
        
        # Analyze the EDL content for still images (quick preview)
        still_count = 0
        lines = edl_content.split('\n')
        for line in lines:
            if line.strip() and not line.startswith('*') and not line.startswith('TITLE:') and not line.startswith('FCM:'):
                parts = line.split()
                if len(parts) >= 8:
                    source_name = parts[1] if len(parts) > 1 else ""
                    if 'S' in source_name and any(char.isdigit() for char in source_name):
                        still_count += 1
        
        # Return success response
        return {
            "status": "success",
            "message": f"EDL file received and stored successfully",
            "filename": unique_filename,
            "file_path": str(edl_file_path),
            "file_size_bytes": file_size,
            "source": source,
            "preview": {
                "total_lines": len(lines),
                "estimated_still_images": still_count,
                "ready_for_analysis": True
            },
            "next_steps": {
                "analysis": f"EDL file ready for analysis at {edl_file_path}",
                "import": f"Use /run/edl_import_sitc endpoint to import to SITC table",
                "format_check": "EDL format appears compatible with existing parser"
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ EDL export error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"EDL export error: {str(e)}")

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

@app.get("/sessions")
def get_session_status():
    """Get current FileMaker session information."""
    try:
        session_info = config.get_session_info()
        api_status = config.test_api_connection()
        
        return {
            "api_available": api_status,
            "session_info": session_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logging.error(f"❌ Error getting session status: {e}")
        raise HTTPException(status_code=500, detail=f"Session status error: {str(e)}")

@app.post("/sessions/cleanup")
def cleanup_sessions():
    """Force cleanup of all FileMaker sessions."""
    try:
        config.force_session_cleanup()
        return {"message": "All sessions cleaned up successfully"}
    except Exception as e:
        logging.error(f"❌ Error cleaning up sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Session cleanup error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    # Configure uvicorn for large payload handling (Avid metadata exports)
    uvicorn_config = {
        "host": "0.0.0.0",
        "port": 8000,
        "limit_max_requests": 1000,
        "limit_concurrency": 1000,
        # Critical: Set large payload limits for metadata export
        "h11_max_incomplete_event_size": 50 * 1024 * 1024,  # 50MB
        "timeout_keep_alive": 30,
        "timeout_graceful_shutdown": 30,
        # Enhanced logging
        "log_level": "info",
        "access_log": True
    }
    
    logging.info("🚀 Starting FileMaker Automation API with enhanced payload support")
    logging.info("📦 Maximum payload size: 50MB (for Avid metadata exports)")
    
    uvicorn.run(app, **uvicorn_config)