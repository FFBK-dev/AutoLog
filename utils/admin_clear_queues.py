#!/usr/bin/env python3
"""
Admin utility to clear RQ queues for Footage AutoLog Part B.

NOTE: Queues are automatically cleared when API.py shuts down.
This script is for manual clearing while the API is still running.

Usage:
    python3 utils/admin_clear_queues.py
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from jobs.ftg_autolog_B_queue_jobs import (
    q_step1, q_step2, q_step3, q_step4
)

def clear_all_queues():
    """Clear all queues and failed registries."""
    
    print("🧹 Clearing all Footage AutoLog Part B queues...\n")
    
    queues = [
        (q_step1, "Step 1: Assess & Sample"),
        (q_step2, "Step 2: Gemini Analysis"),
        (q_step3, "Step 3: Create Frames"),
        (q_step4, "Step 4: Transcription")
    ]
    
    total_cleared = 0
    total_failed_cleared = 0
    
    for queue, name in queues:
        # Clear main queue
        queue_count = len(queue)
        queue.empty()
        print(f"✅ Cleared {name}: {queue_count} items")
        total_cleared += queue_count
        
        # Clear failed registry
        try:
            failed_count = queue.failed_job_registry.count
            queue.failed_job_registry.empty()
            print(f"✅ Cleared {name} failed: {failed_count} items")
            total_failed_cleared += failed_count
        except Exception as e:
            print(f"⚠️  Could not clear {name} failed registry: {e}")
        
        print()
    
    print(f"🎉 Complete!")
    print(f"   Total cleared: {total_cleared}")
    print(f"   Total failed cleared: {total_failed_cleared}")
    print()
    print("💡 To re-queue items, use: python3 jobs/ftg_autolog_B_00_run_all.py")

if __name__ == "__main__":
    # Confirm before clearing
    print("⚠️  WARNING: This will clear ALL queued and failed jobs!")
    print("   Make sure workers are stopped first.\n")
    
    response = input("Type 'yes' to continue: ")
    
    if response.lower() == 'yes':
        clear_all_queues()
    else:
        print("❌ Cancelled")

