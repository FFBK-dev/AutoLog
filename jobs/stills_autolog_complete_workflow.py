#!/usr/bin/env python3
import subprocess
import sys
import time
from pathlib import Path
import requests
import traceback
from datetime import datetime
import warnings
import json
import openai

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

__ARGS__ = ["stills_id"]  # Single stills_id argument

JOBS_DIR = Path(__file__).resolve().parent  # Same directory as this script

FIELD_MAPPING = {
    "stills_id": "INFO_STILLS_ID",
    "status": "AutoLog_Status",
    "metadata": "INFO_Metadata",
    "url": "SPECS_URL",
    "dev_console": "AI_DevConsole",
    "description_orig": "INFO_Description_Original",
    "copyright": "INFO_Copyright",
    "source": "INFO_Source",
    "archival_id": "INFO_Archival_ID",
    "globals_api_key": "SystemGlobals_AutoLog_OpenAI_API_Key"
}

# Define the complete workflow with status updates
WORKFLOW_STEPS = [
    {
        "step_num": 1,
        "status_before": "0 - Pending File Info",
        "status_after": "1 - File Info Complete",
        "script": "stills_autolog_01_get_file_info.py",
        "description": "Get File Info"
    },
    {
        "step_num": 2,
        "status_before": "1 - File Info Complete",
        "status_after": "2 - Server Copy Complete",
        "script": "stills_autolog_02_copy_to_server.py",
        "description": "Copy to Server"
    },
    {
        "step_num": 3,
        "status_before": "2 - Server Copy Complete",
        "status_after": "3 - Metadata Parsed",
        "script": "stills_autolog_03_parse_metadata.py",
        "description": "Parse Metadata"
    },
    {
        "step_num": 4,
        "status_before": "3 - Metadata Parsed",
        "status_after": "4 - Scraping URL",
        "script": "stills_autolog_04_scrape_url.py",
        "description": "Scrape URL",
        "conditional": True  # Only run if URL exists
    },
    {
        "step_num": 5,
        "status_before": None,  # Variable - could be step 3 or 4 status
        "status_after": "5 - Generating Description",
        "script": "stills_autolog_05_generate_description.py",
        "description": "Generate Description",
        "requires_good_metadata": True
    },
    {
        "step_num": 6,
        "status_before": "5 - Generating Description",
        "status_after": "6 - Generating Embeddings",
        "script": "stills_autolog_06_generate_embeddings.py",
        "description": "Generate Embeddings"
    },
    {
        "step_num": 7,
        "status_before": "6 - Generating Embeddings",
        "status_after": "7 - Applying Tags",
        "script": "stills_autolog_07_apply_tags.py",
        "description": "Apply Tags"
    },
    {
        "step_num": 8,
        "status_before": "7 - Applying Tags",
        "status_after": "8 - Ready for Fusion",
        "script": "stills_autolog_08_fuse_embeddings.py",
        "description": "Fuse Embeddings"
    }
]

def load_prompts():
    """Load prompts from prompts.json file."""
    prompts_path = Path(__file__).resolve().parent.parent / "prompts.json"
    with open(prompts_path, 'r') as f:
        return json.load(f)

def combine_metadata(record_data):
    """Combine all available metadata into a single text for evaluation."""
    metadata_parts = []
    
    # Add EXIF metadata
    raw_metadata = record_data.get(FIELD_MAPPING["metadata"], '')
    if raw_metadata:
        metadata_parts.append(f"EXIF/Technical Metadata:\n{raw_metadata}")
    
    # Add original description
    description = record_data.get(FIELD_MAPPING["description_orig"], '')
    if description:
        metadata_parts.append(f"Original Description:\n{description}")
    
    # Add copyright/attribution
    copyright = record_data.get(FIELD_MAPPING["copyright"], '')
    if copyright:
        metadata_parts.append(f"Copyright/Attribution:\n{copyright}")
    
    # Add source information
    source = record_data.get(FIELD_MAPPING["source"], '')
    if source:
        metadata_parts.append(f"Source Archive:\n{source}")
    
    # Add archival ID
    archival_id = record_data.get(FIELD_MAPPING["archival_id"], '')
    if archival_id:
        metadata_parts.append(f"Archival ID:\n{archival_id}")
    
    # Add URL (for reference)
    url = record_data.get(FIELD_MAPPING["url"], '')
    if url:
        metadata_parts.append(f"Source URL:\n{url}")
    
    return "\n\n".join(metadata_parts)

def evaluate_metadata_quality(record_data, token):
    """Evaluate metadata quality using AI."""
    try:
        # Get OpenAI API key
        system_globals = config.get_system_globals(token)
        api_key = system_globals.get(FIELD_MAPPING["globals_api_key"])
        if not api_key:
            print(f"  -> ERROR: OpenAI API Key not found in SystemGlobals")
            return False
        
        # Create OpenAI client
        client = openai.OpenAI(api_key=api_key)
        
        # Combine all metadata
        combined_metadata = combine_metadata(record_data)
        
        if not combined_metadata.strip():
            print(f"  -> No metadata available for evaluation")
            return False
        
        print(f"  -> Evaluating combined metadata ({len(combined_metadata)} chars)")
        
        # Load and format the prompt
        prompts = load_prompts()
        prompt_template = prompts["stills_metadata_evaluation"]
        prompt_text = prompt_template.format(combined_metadata=combined_metadata)
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt_text}
            ],
            response_format={"type": "json_object"},
            max_tokens=300,
            temperature=0.1  # Low temperature for consistent evaluation
        )
        
        evaluation = json.loads(response.choices[0].message.content)
        is_sufficient = evaluation.get("sufficient", False)
        reason = evaluation.get("reason", "No reason provided")
        confidence = evaluation.get("confidence", "medium")
        
        print(f"  -> AI Evaluation: {'GOOD' if is_sufficient else 'BAD'}")
        print(f"     Reason: {reason}")
        print(f"     Confidence: {confidence}")
        
        return is_sufficient
        
    except Exception as e:
        print(f"  -> ERROR in metadata evaluation: {e}")
        return False

def format_error_message(stills_id, step_name, error_details, error_type="Processing Error"):
    """Format error messages for the AI_DevConsole field in a user-friendly way."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Clean up error details
    clean_error = error_details.strip()
    if clean_error.startswith("Error:"):
        clean_error = clean_error[6:].strip()
    if clean_error.startswith("FATAL ERROR:"):
        clean_error = clean_error[12:].strip()
    
    # Truncate very long error messages
    if len(clean_error) > 200:
        clean_error = clean_error[:197] + "..."
    
    return f"[{timestamp}] {error_type} - {step_name}\nStills ID: {stills_id}\nIssue: {clean_error}"

def write_error_to_console(record_id, token, error_message):
    """Safely write error message to the AI_DevConsole field."""
    try:
        payload = {"fieldData": {FIELD_MAPPING["dev_console"]: error_message}}
        response = requests.patch(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            json=payload, 
            verify=False
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to write error to console: {e}")
        return False

def update_status(record_id, token, new_status):
    """Update the AutoLog_Status field."""
    try:
        payload = {"fieldData": {FIELD_MAPPING["status"]: new_status}}
        response = requests.patch(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            json=payload, 
            verify=False
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to update status to '{new_status}': {e}")
        return False

def get_current_record_data(record_id, token):
    """Get current record data from FileMaker."""
    try:
        response = requests.get(
            config.url(f"layouts/Stills/records/{record_id}"), 
            headers=config.api_headers(token), 
            verify=False
        )
        response.raise_for_status()
        return response.json()['response']['data'][0]
    except Exception as e:
        print(f"Failed to get current record data: {e}")
        return None

def run_workflow_step(step, stills_id, record_id, token):
    """Run a single workflow step."""
    step_num = step["step_num"]
    script_name = step["script"]
    description = step["description"]
    
    print(f"--- Step {step_num}: {description} ---")
    
    # Update status before running step (if specified)
    if step.get("status_before"):
        if not update_status(record_id, token, step["status_before"]):
            return False
        print(f"  -> Status updated to: {step['status_before']}")
    
    # Handle conditional steps
    if step.get("conditional"):
        if step_num == 4:  # URL scraping step
            # Get current record data to check for URL
            record_data = get_current_record_data(record_id, token)
            if not record_data:
                print(f"  -> SKIP: Could not get record data")
                return True
            
            url = record_data['fieldData'].get(FIELD_MAPPING["url"], '')
            if not url:
                print(f"  -> SKIP: No URL found for scraping")
                return True
            else:
                print(f"  -> URL found: {url}")
    
    # Handle steps that require good metadata
    if step.get("requires_good_metadata"):
        # Get current record data to check metadata quality
        record_data = get_current_record_data(record_id, token)
        if not record_data:
            print(f"  -> FATAL: Could not get record data")
            return False
        
        # Evaluate metadata quality inline
        if not evaluate_metadata_quality(record_data['fieldData'], token):
            print(f"  -> HALT: Metadata quality is BAD, not 'GOOD'")
            # Set status to awaiting user input
            if not update_status(record_id, token, "Awaiting User Input"):
                print(f"  -> Failed to update status to 'Awaiting User Input'")
            return False
        else:
            print(f"  -> Metadata quality is GOOD, proceeding")
    
    # Run the script
    script_path = JOBS_DIR / script_name
    
    if not script_path.exists():
        error_msg = format_error_message(
            stills_id,
            description,
            f"Script not found: {script_name}",
            "Configuration Error"
        )
        write_error_to_console(record_id, token, error_msg)
        print(f"  -> ERROR: Script not found: {script_path}")
        return False
    
    try:
        print(f"  -> Running: {script_name}")
        result = subprocess.run(
            ["python3", str(script_path), stills_id], 
            capture_output=True, 
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print(f"  -> SUCCESS: {script_name}")
            
            # Update status after successful completion (only if status_after is not None)
            if step["status_after"] is not None:
                if not update_status(record_id, token, step["status_after"]):
                    print(f"  -> Warning: Failed to update status to '{step['status_after']}'")
                else:
                    print(f"  -> Status updated to: {step['status_after']}")
            
            return True
        else:
            # Extract meaningful error from stderr/stdout
            stderr_output = result.stderr.strip() if result.stderr else ""
            stdout_output = result.stdout.strip() if result.stdout else ""
            
            # Filter out urllib3 warnings
            def filter_warnings(text):
                if not text:
                    return ""
                lines = text.split('\n')
                filtered = []
                for line in lines:
                    if 'urllib3' in line and 'LibreSSL' in line:
                        continue
                    if 'NotOpenSSLWarning' in line:
                        continue
                    filtered.append(line)
                return '\n'.join(filtered).strip()
            
            stderr_output = filter_warnings(stderr_output)
            stdout_output = filter_warnings(stdout_output)
            
            # Get the most relevant error information
            if stderr_output:
                error_details = stderr_output
            elif stdout_output:
                error_details = stdout_output
            else:
                error_details = f"Script failed with exit code {result.returncode}"
            
            error_msg = format_error_message(
                stills_id,
                description,
                error_details,
                "Processing Error"
            )
            write_error_to_console(record_id, token, error_msg)
            print(f"  -> FAILURE: {error_details}")
            return False
            
    except subprocess.TimeoutExpired:
        error_msg = format_error_message(
            stills_id,
            description,
            f"Script timed out after 5 minutes: {script_name}",
            "Timeout Error"
        )
        write_error_to_console(record_id, token, error_msg)
        print(f"  -> TIMEOUT: {script_name}")
        return False
        
    except Exception as e:
        error_msg = format_error_message(
            stills_id,
            description,
            f"System error running {script_name}: {str(e)}",
            "System Error"
        )
        write_error_to_console(record_id, token, error_msg)
        print(f"  -> SYSTEM ERROR: {e}")
        return False

def run_complete_workflow(stills_id, token):
    """Run the complete AutoLog workflow for a single stills_id."""
    print(f"=== Starting AutoLog workflow for {stills_id} ===")
    
    try:
        # Get record ID
        record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
        print(f"Found record ID: {record_id}")
        
        # Run each workflow step
        for step in WORKFLOW_STEPS:
            success = run_workflow_step(step, stills_id, record_id, token)
            if not success:
                print(f"=== Workflow STOPPED at step {step['step_num']}: {step['description']} ===")
                return False
            
            # Add extra delay after description generation to allow calculated fields to update
            if step.get("step_num") == 5:
                print(f"  -> Extra delay after description generation to allow calculated fields to update")
                time.sleep(3)  # Extra delay after description generation
            else:
                time.sleep(0.1)
        
        # Mark as complete
        if not update_status(record_id, token, "9 - Complete"):
            print(f"  -> Warning: Failed to update final status to 'Complete'")
        else:
            print(f"  -> Final status updated to: 9 - Complete")
        
        print(f"=== Workflow COMPLETED successfully for {stills_id} ===")
        return True
        
    except Exception as e:
        print(f"=== FATAL ERROR in workflow for {stills_id}: {e} ===")
        traceback.print_exc()
        
        # Try to write error to console if we have a record ID
        try:
            record_id = config.find_record_id(token, "Stills", {FIELD_MAPPING["stills_id"]: f"=={stills_id}"})
            error_msg = format_error_message(
                stills_id,
                "Workflow Controller",
                f"Critical system error: {str(e)}",
                "Critical Error"
            )
            write_error_to_console(record_id, token, error_msg)
        except:
            pass
        
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 stills_autolog_complete_workflow.py <stills_id>")
        sys.exit(1)
    
    stills_id = sys.argv[1]
    
    try:
        token = config.get_token()
        success = run_complete_workflow(stills_id, token)
        print(f"SUCCESS [complete_workflow]: {stills_id}" if success else f"FAILURE [complete_workflow]: {stills_id}")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Critical startup error: {e}")
        sys.exit(1) 