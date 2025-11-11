#!/usr/bin/env python3
"""
Footage AutoLog B Step 1: Assess and Sample Frames
- Detects audio and kicks off background transcription (non-blocking)
- Performs intelligent frame sampling with scene detection
- Tracks timecodes for all sampled frames
- Saves metadata for Gemini analysis
- Supports both LF (Library Footage) and AF (Archival Footage)
"""

import sys
import os
import json
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.frame_sampler import FrameSampler, get_video_info
from utils.audio_detector import has_audio, transcribe_full_audio_background

__ARGS__ = ["footage_id"]

FIELD_MAPPING = {
    "footage_id": "INFO_FTG_ID",
    "filepath": "SPECS_Filepath_Server"
}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    footage_id = sys.argv[1]
    
    # Flexible token handling
    if len(sys.argv) == 2:
        token = config.get_token()
        print(f"Direct mode: Created new FileMaker session for {footage_id}")
    elif len(sys.argv) == 3:
        token = sys.argv[2]
        print(f"Subprocess mode: Using provided token for {footage_id}")
    else:
        sys.stderr.write(f"ERROR: Invalid arguments. Expected: script.py footage_id [token]\n")
        sys.exit(1)
    
    try:
        print(f"=== Starting Assessment and Sampling for {footage_id} ===")
        
        # Get the current record to find the file path
        record_id = config.find_record_id(token, "FOOTAGE", {FIELD_MAPPING["footage_id"]: f"=={footage_id}"})
        record_data = config.get_record(token, "FOOTAGE", record_id)
        file_path = record_data[FIELD_MAPPING["filepath"]]
        
        print(f"Processing file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            # Try mounting volume
            if not config.ensure_volume_mounted(file_path):
                raise FileNotFoundError(f"Footage file not accessible: {file_path}")
        
        # Get video info
        print(f"\n📹 Getting video information...")
        duration, framerate = get_video_info(file_path)
        
        if duration is None or framerate is None:
            raise RuntimeError("Could not determine video duration and framerate")
        
        print(f"  -> Duration: {duration:.2f}s")
        print(f"  -> Framerate: {framerate:.2f} fps")
        
        # Setup output directory for this footage (supports both LF and AF prefixes)
        output_dir = f"/private/tmp/ftg_autolog_{footage_id}"
        os.makedirs(output_dir, exist_ok=True)
        print(f"  -> Output directory: {output_dir}")
        
        # STEP 1: Audio Detection and Background Transcription
        print(f"\n🎙️ Audio Detection...")
        audio_exists = has_audio(file_path)
        
        if audio_exists:
            print(f"  -> ✅ Audio detected - starting background transcription...")
            
            transcript_path = os.path.join(output_dir, "transcript.json")
            status_path = os.path.join(output_dir, "transcription_status.json")
            
            # Kick off transcription in background (NON-BLOCKING!)
            transcribe_full_audio_background(
                video_path=file_path,
                output_path=transcript_path,
                status_file=status_path,
                model="base"  # Balance between speed and accuracy
            )
            
            print(f"  -> 🔄 Transcription running in background (non-blocking)")
            audio_status = "transcribing"
        elif audio_exists is False:
            print(f"  -> 📵 No audio detected - skipping transcription")
            audio_status = "silent"
        else:
            print(f"  -> ⚠️ Audio detection inconclusive - assuming has audio")
            audio_status = "unknown"
        
        # STEP 2: Intelligent Frame Sampling
        print(f"\n🎬 Intelligent Frame Sampling...")
        sampler = FrameSampler(file_path, duration, framerate)
        
        # Perform smart sampling with scene detection
        extracted_frames = sampler.smart_sample(
            output_dir=output_dir,
            max_width=512,  # Downsample for efficiency
            scene_threshold=0.3
        )
        
        if not extracted_frames:
            raise RuntimeError("Failed to extract any frames")
        
        print(f"  -> ✅ Extracted {len(extracted_frames)} frames")
        
        # STEP 3: Save Assessment Metadata
        print(f"\n💾 Saving assessment metadata...")
        
        assessment_data = {
            "footage_id": footage_id,
            "file_path": file_path,
            "duration_seconds": duration,
            "framerate": framerate,
            "audio_status": audio_status,
            "audio_transcript_path": os.path.join(output_dir, "transcript.json") if audio_exists else None,
            "transcription_status_path": os.path.join(output_dir, "transcription_status.json") if audio_exists else None,
            "frame_count": len(extracted_frames),
            "frames": extracted_frames,
            "output_directory": output_dir
        }
        
        assessment_path = os.path.join(output_dir, "assessment.json")
        with open(assessment_path, 'w') as f:
            json.dump(assessment_data, f, indent=2)
        
        print(f"  -> Saved to: {assessment_path}")
        
        # Print summary
        print(f"\n=== Assessment Complete ===")
        print(f"  Footage: {footage_id}")
        print(f"  Duration: {duration:.2f}s @ {framerate:.2f}fps")
        print(f"  Audio: {audio_status}")
        print(f"  Frames: {len(extracted_frames)} sampled")
        print(f"  Output: {output_dir}")
        
        if audio_exists:
            print(f"  ⚡ Audio transcription continuing in background...")
        
        print(f"\n✅ Assessment and sampling completed for {footage_id}")
        print(f"🔄 Ready for Step 4: Gemini Analysis")
        
    except Exception as e:
        print(f"❌ Error in assessment and sampling for {footage_id}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

