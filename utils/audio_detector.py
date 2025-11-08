#!/usr/bin/env python3
"""
Audio detection and transcription utilities for video processing.
Handles background audio transcription and transcript-to-frame mapping.
"""

import os
import subprocess
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def has_audio(video_path: str) -> Optional[bool]:
    """
    Check if video has actual audio content using ffmpeg (matches old flow method).
    
    Uses the same approach as frames_transcribe_audio.py: checks for "Audio:" in
    ffmpeg stderr output, which confirms actual audio content, not just empty streams.
    
    Args:
        video_path: Path to video file
        
    Returns:
        True if audio content exists, False if no audio, None if detection failed
    """
    try:
        # Find ffmpeg (same method as old flow - checks for actual audio content)
        ffmpeg_paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
        ffmpeg_cmd = None
        
        for path in ffmpeg_paths:
            if os.path.exists(path) or path == 'ffmpeg':
                ffmpeg_cmd = path
                break
        
        if not ffmpeg_cmd:
            print(f"  -> Warning: ffmpeg not found, cannot detect audio")
            return None
        
        # Use ffmpeg to check for actual audio content (not just streams)
        # This matches the old flow's methodology from frames_transcribe_audio.py
        probe_cmd = [ffmpeg_cmd, "-i", video_path]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
        
        # Check stderr for "Audio:" which indicates actual audio content
        has_audio_content = "Audio:" in probe_result.stderr
        
        if has_audio_content:
            print(f"  -> ✅ Video has audio content")
        else:
            print(f"  -> 📵 No audio content detected")
        
        return has_audio_content
        
    except subprocess.TimeoutExpired:
        print(f"  -> Warning: Audio detection timed out")
        return None
    except Exception as e:
        print(f"  -> Warning: Audio detection error: {e}")
        return None


def transcribe_full_audio_background(
    video_path: str,
    output_path: str,
    status_file: str,
    model: str = "base"
):
    """
    Transcribe full audio track in background thread.
    Writes status updates to status_file.
    
    Args:
        video_path: Path to video file
        output_path: Path to write transcript JSON
        status_file: Path to write status updates
        model: Whisper model size (tiny, base, small, medium, large)
    """
    def _transcribe():
        try:
            # Write initial status
            with open(status_file, 'w') as f:
                json.dump({"status": "running", "progress": 0}, f)
            
            print(f"  -> 🎙️ Starting background audio transcription...")
            print(f"  -> Model: {model}, Output: {output_path}")
            
            # Use whisper command-line tool for transcription
            # First check if whisper is available
            try:
                subprocess.run(['whisper', '--help'], capture_output=True, timeout=5)
                whisper_cmd = 'whisper'
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print(f"  -> Warning: whisper CLI not found, trying openai-whisper")
                whisper_cmd = 'whisper'  # Will fail below if not found
            
            # Extract audio to temp WAV file first (faster for Whisper)
            temp_audio = output_path.replace('.json', '_audio.wav')
            
            # Find ffmpeg
            ffmpeg_paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
            ffmpeg_cmd = None
            for path in ffmpeg_paths:
                if os.path.exists(path) or path == 'ffmpeg':
                    ffmpeg_cmd = path
                    break
            
            if not ffmpeg_cmd:
                raise RuntimeError("FFmpeg not found")
            
            # Extract audio
            extract_cmd = [
                ffmpeg_cmd,
                '-i', video_path,
                '-vn',  # No video
                '-acodec', 'pcm_s16le',  # PCM 16-bit
                '-ar', '16000',  # 16kHz sample rate
                '-ac', '1',  # Mono
                '-y',  # Overwrite
                temp_audio,
                '-loglevel', 'error'
            ]
            
            print(f"  -> Extracting audio track...")
            result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                raise RuntimeError(f"Audio extraction failed: {result.stderr}")
            
            # Update status
            with open(status_file, 'w') as f:
                json.dump({"status": "running", "progress": 50}, f)
            
            # Transcribe with Whisper
            print(f"  -> Transcribing audio with Whisper ({model} model)...")
            
            whisper_cmd_list = [
                whisper_cmd,
                temp_audio,
                '--model', model,
                '--output_format', 'json',
                '--output_dir', os.path.dirname(output_path),
                '--language', 'en',  # Assume English
                '--word_timestamps', 'True'  # Get word-level timestamps
            ]
            
            result = subprocess.run(
                whisper_cmd_list,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for transcription
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Whisper transcription failed: {result.stderr}")
            
            # Whisper outputs to filename.json, rename if needed
            whisper_output = temp_audio.replace('.wav', '.json')
            if os.path.exists(whisper_output) and whisper_output != output_path:
                os.rename(whisper_output, output_path)
            
            # Clean up temp audio
            if os.path.exists(temp_audio):
                os.remove(temp_audio)
            
            # Write success status
            with open(status_file, 'w') as f:
                json.dump({
                    "status": "completed",
                    "progress": 100,
                    "output_file": output_path
                }, f)
            
            print(f"  -> ✅ Background transcription completed: {output_path}")
            
        except subprocess.TimeoutExpired:
            with open(status_file, 'w') as f:
                json.dump({
                    "status": "failed",
                    "error": "Transcription timed out"
                }, f)
            print(f"  -> ❌ Background transcription timed out")
            
        except Exception as e:
            with open(status_file, 'w') as f:
                json.dump({
                    "status": "failed",
                    "error": str(e)
                }, f)
            print(f"  -> ❌ Background transcription error: {e}")
    
    # Start transcription in background thread
    thread = threading.Thread(target=_transcribe, daemon=True)
    thread.start()
    print(f"  -> 🔄 Audio transcription running in background...")


def check_transcription_status(status_file: str) -> Dict:
    """
    Check status of background transcription.
    
    Args:
        status_file: Path to status file
        
    Returns:
        Status dictionary with keys: status, progress, error (optional)
    """
    if not os.path.exists(status_file):
        return {"status": "not_started", "progress": 0}
    
    try:
        with open(status_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def load_transcript(transcript_path: str) -> Optional[Dict]:
    """
    Load transcript JSON file.
    
    Args:
        transcript_path: Path to transcript JSON
        
    Returns:
        Transcript dictionary or None if failed
    """
    if not os.path.exists(transcript_path):
        return None
    
    try:
        with open(transcript_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"  -> Error loading transcript: {e}")
        return None


def map_transcript_to_frames(
    transcript: Dict,
    frame_timestamps: List[float],
    window_seconds: float = 2.5
) -> Dict[float, str]:
    """
    Map transcript segments to nearest frame timestamps.
    
    Args:
        transcript: Whisper transcript JSON with segments/words
        frame_timestamps: List of frame timestamps in seconds
        window_seconds: Time window around each frame (default: ±2.5s)
        
    Returns:
        Dictionary mapping frame timestamps to transcript text
    """
    frame_transcripts = {}
    
    # Extract segments from transcript
    segments = transcript.get('segments', [])
    if not segments:
        print(f"  -> No transcript segments found")
        return frame_transcripts
    
    print(f"  -> Mapping {len(segments)} transcript segments to {len(frame_timestamps)} frames...")
    
    # For each frame, find transcript segments within time window
    for frame_time in frame_timestamps:
        window_start = frame_time - window_seconds
        window_end = frame_time + window_seconds
        
        matching_text = []
        
        for segment in segments:
            segment_start = segment.get('start', 0)
            segment_end = segment.get('end', 0)
            
            # Check if segment overlaps with frame window
            if segment_start <= window_end and segment_end >= window_start:
                text = segment.get('text', '').strip()
                if text:
                    matching_text.append(text)
        
        # Combine matching segments
        if matching_text:
            frame_transcripts[frame_time] = ' '.join(matching_text)
    
    print(f"  -> Mapped transcripts to {len(frame_transcripts)} frames")
    return frame_transcripts


def extract_audio_type(transcript: Dict) -> str:
    """
    Determine if video has sound or is MOS based on transcript.
    
    Args:
        transcript: Whisper transcript JSON
        
    Returns:
        "Sound" if audio detected, "MOS" if silent
    """
    if not transcript:
        return "MOS"
    
    segments = transcript.get('segments', [])
    
    # Check if there's any meaningful text
    total_text = ' '.join([seg.get('text', '').strip() for seg in segments])
    
    if len(total_text) > 10:  # At least some words
        return "Sound"
    else:
        return "MOS"

