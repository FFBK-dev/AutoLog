#!/usr/bin/env python3
"""
Multi-ID Job Script Template

This template provides standardized multi-ID processing for job scripts.
Supports both single ID and multiple IDs in various formats:
- Single ID: "S04871"
- JSON array: '["S04871", "S04872", "S04873"]'
- Comma-separated: "S04871,S04872,S04873"
- Line-separated: "S04871\nS04872\nS04873"
- Space-separated: "S04871 S04872 S04873"
"""

import sys
import warnings
import concurrent.futures
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.input_parser import parse_input_ids, format_input_summary, validate_ids

# Define expected arguments
__ARGS__ = ["item_id"]  # Change this to match your script's expected argument

# Define field mappings for your layout
FIELD_MAPPING = {
    "item_id": "INFO_ITEM_ID",  # Change to match your layout
    "status": "AutoLog_Status",
    "dev_console": "AI_DevConsole",
    # Add other field mappings as needed
}

# Define expected ID prefixes for validation
EXPECTED_ID_PREFIXES = ['S', 'F', 'AF', 'FTG']  # Adjust based on your ID format

# Maximum concurrent workers for batch processing
MAX_WORKERS = 8


def process_single_item(item_id: str, token: str) -> bool:
    """
    Process a single item. Override this function with your specific logic.
    
    Args:
        item_id: The ID of the item to process
        token: FileMaker authentication token
        
    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"  -> Processing {item_id}")
        
        # TODO: Implement your specific processing logic here
        # Example:
        # record_id = config.find_record_id(token, "Layout", {FIELD_MAPPING["item_id"]: f"=={item_id}"})
        # record_data = config.get_record(token, "Layout", record_id)
        # ... your processing logic ...
        
        print(f"  -> ✅ Successfully processed {item_id}")
        return True
        
    except Exception as e:
        print(f"  -> ❌ Error processing {item_id}: {e}")
        return False


def process_batch_items(item_ids: list, token: str, max_workers: int = MAX_WORKERS) -> dict:
    """
    Process multiple items in parallel.
    
    Args:
        item_ids: List of item IDs to process
        token: FileMaker authentication token
        max_workers: Maximum number of concurrent workers
        
    Returns:
        Dictionary with processing results
    """
    if not item_ids:
        return {"total": 0, "successful": 0, "failed": 0, "results": []}
    
    print(f"🔄 Starting batch processing of {len(item_ids)} items")
    
    # Adjust max workers based on number of items
    actual_max_workers = min(max_workers, len(item_ids))
    print(f"📋 Using {actual_max_workers} concurrent workers")
    
    results = {
        "total": len(item_ids),
        "successful": 0,
        "failed": 0,
        "results": []
    }
    
    def process_item_wrapper(item_id):
        """Wrapper function for parallel processing."""
        try:
            success = process_single_item(item_id, token)
            return {
                "item_id": item_id,
                "success": success,
                "error": None
            }
        except Exception as e:
            return {
                "item_id": item_id,
                "success": False,
                "error": str(e)
            }
    
    # Process items in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
        future_to_item = {
            executor.submit(process_item_wrapper, item_id): item_id 
            for item_id in item_ids
        }
        
        for future in concurrent.futures.as_completed(future_to_item):
            try:
                result = future.result()
                results["results"].append(result)
                
                if result["success"]:
                    results["successful"] += 1
                else:
                    results["failed"] += 1
                
                # Progress update
                completed = len(results["results"])
                print(f"📊 Progress: {completed}/{len(item_ids)} completed ({results['successful']} successful, {results['failed']} failed)")
                
            except Exception as e:
                item_id = future_to_item[future]
                print(f"❌ Unexpected error processing {item_id}: {e}")
                results["results"].append({
                    "item_id": item_id,
                    "success": False,
                    "error": str(e)
                })
                results["failed"] += 1
    
    print(f"✅ Batch processing completed: {results['successful']} successful, {results['failed']} failed")
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("ERROR: No input provided. Expected: script.py <input> [token]\n")
        sys.exit(1)
    
    input_string = sys.argv[1]
    
    # Parse input IDs
    item_ids = parse_input_ids(input_string)
    
    if not item_ids:
        print("❌ No valid IDs provided")
        sys.exit(1)
    
    # Validate IDs
    valid_ids, invalid_ids = validate_ids(item_ids, EXPECTED_ID_PREFIXES)
    
    if invalid_ids:
        print(f"⚠️ Invalid IDs found: {invalid_ids}")
        print(f"📋 Proceeding with valid IDs: {valid_ids}")
    
    if not valid_ids:
        print("❌ No valid IDs to process")
        sys.exit(1)
    
    # Print input summary
    print(format_input_summary(valid_ids, Path(__file__).stem))
    
    # Handle token
    if len(sys.argv) == 2:
        # Direct API call mode - create own token/session
        token = config.get_token()
        print(f"🔄 Direct mode: Created new FileMaker session")
    elif len(sys.argv) == 3:
        # Subprocess mode - use provided token from parent process
        token = sys.argv[2]
        print(f"📋 Subprocess mode: Using provided token")
    else:
        sys.stderr.write("ERROR: Invalid arguments. Expected: script.py <input> [token]\n")
        sys.exit(1)
    
    try:
        # Process items
        if len(valid_ids) == 1:
            # Single item processing
            success = process_single_item(valid_ids[0], token)
            sys.exit(0 if success else 1)
        else:
            # Batch processing
            results = process_batch_items(valid_ids, token)
            
            # Output results as JSON for easy parsing
            import json
            print(f"BATCH_RESULTS: {json.dumps(results, indent=2)}")
            
            # Exit with success if all items succeeded
            sys.exit(0 if results["failed"] == 0 else 1)
            
    except Exception as e:
        print(f"❌ Critical error: {e}")
        sys.exit(1) 