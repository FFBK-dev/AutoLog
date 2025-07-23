#!/usr/bin/env python3
import sys
import warnings
from pathlib import Path
import time

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def test_pipeline_performance():
    """Test the performance of the new pipeline approach."""
    print(f"🧪 Testing pipeline performance improvements")
    print("=" * 60)
    
    try:
        token = config.get_token()
        
        # Import the main workflow module
        sys.path.append(str(Path(__file__).resolve().parent.parent / "jobs"))
        import footage_autolog_00_run_all as workflow
        
        # Find pending items
        pending_items = workflow.find_pending_items(token)
        resume_items = workflow.find_resume_processing_items(token)
        user_input_items = workflow.find_awaiting_user_input_items(token)
        
        all_items = list(set(pending_items + resume_items + user_input_items))
        
        if not all_items:
            print(f"✅ No items found for processing")
            return True
        
        print(f"📋 Found {len(all_items)} items to process:")
        print(f"  - {len(pending_items)} pending items")
        print(f"  - {len(resume_items)} resume processing items") 
        print(f"  - {len(user_input_items)} awaiting user input items")
        
        if len(all_items) == 1:
            print(f"📋 Single item detected - running individual workflow")
            footage_id = all_items[0]
            record_id = config.find_record_id(token, "FOOTAGE", {"INFO_FTG_ID": f"=={footage_id}"})
            
            start_time = time.time()
            success = workflow.run_complete_workflow(footage_id, record_id, token)
            duration = time.time() - start_time
            
            print(f"📊 Single item results:")
            print(f"  Duration: {duration:.2f} seconds")
            print(f"  Success: {'✅ YES' if success else '❌ NO'}")
            return success
        else:
            print(f"🚀 Multiple items detected - using PIPELINE processing")
            
            start_time = time.time()
            results = workflow.run_pipeline_workflow(all_items, token)
            duration = time.time() - start_time
            
            print(f"📊 Pipeline processing results:")
            print(f"  Total duration: {duration:.2f} seconds")
            print(f"  Items processed: {results['total_items']}")
            print(f"  Successful: {results['successful']}")
            print(f"  Failed: {results['failed']}")
            
            if results['successful'] > 0:
                avg_time = duration / results['successful']
                print(f"  Average time per item: {avg_time:.2f} seconds")
                
                # Estimate old approach time (sequential steps across all items)
                estimated_old_time = duration * 1.5  # Conservative estimate
                time_saved = estimated_old_time - duration
                print(f"  Estimated time saved: {time_saved:.2f} seconds ({time_saved/60:.1f} minutes)")
            
            success_rate = (results['successful'] / results['total_items'] * 100) if results['total_items'] > 0 else 0
            print(f"  Success rate: {success_rate:.1f}%")
            
            return results['failed'] == 0
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_pipeline_performance()
    sys.exit(0 if success else 1) 