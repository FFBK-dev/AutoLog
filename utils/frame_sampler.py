#!/usr/bin/env python3
"""
Intelligent frame sampling for video analysis.
Uses ffmpeg scene detection and adaptive sampling to extract representative frames.
"""

import os
import subprocess
import json
import math
from pathlib import Path
from typing import List, Dict, Tuple


class FrameSampler:
    """Extract frames from video using intelligent sampling strategies."""
    
    def __init__(self, video_path: str, duration: float, framerate: float = 30.0):
        """
        Initialize frame sampler.
        
        Args:
            video_path: Path to video file
            duration: Video duration in seconds
            framerate: Video framerate (default: 30.0)
        """
        self.video_path = video_path
        self.duration = duration
        self.framerate = framerate
        
        # Find ffmpeg
        self.ffmpeg_cmd = self._find_ffmpeg()
        self.ffprobe_cmd = self._find_ffprobe()
        
    def _find_ffmpeg(self) -> str:
        """Find ffmpeg executable."""
        ffmpeg_paths = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']
        for path in ffmpeg_paths:
            if os.path.exists(path) or path == 'ffmpeg':
                return path
        raise RuntimeError("FFmpeg not found")
    
    def _find_ffprobe(self) -> str:
        """Find ffprobe executable."""
        ffprobe_paths = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', 'ffprobe']
        for path in ffprobe_paths:
            if os.path.exists(path) or path == 'ffprobe':
                return path
        raise RuntimeError("FFprobe not found")
    
    def detect_scenes(self, threshold: float = 0.3) -> List[float]:
        """
        Detect scene changes using ffmpeg scene detection.
        
        Args:
            threshold: Scene change threshold (0.0-1.0, default 0.3)
            
        Returns:
            List of timestamps (in seconds) where scene changes occur
        """
        try:
            print(f"  -> Detecting scene changes (threshold={threshold})...")
            
            # Use ffmpeg scene detection filter with downsampling for speed
            # Downsampling to 320px width makes this 10x faster on 4K footage
            cmd = [
                self.ffmpeg_cmd,
                '-i', self.video_path,
                '-vf', f"scale=320:-1,select='gt(scene,{threshold})',showinfo",
                '-f', 'null',
                '-'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Parse scene change timestamps from stderr
            scene_times = []
            for line in result.stderr.split('\n'):
                if 'pts_time:' in line:
                    try:
                        # Extract pts_time value
                        pts_start = line.find('pts_time:') + 9
                        pts_end = line.find(' ', pts_start)
                        if pts_end == -1:
                            pts_end = len(line)
                        time_str = line[pts_start:pts_end].strip()
                        timestamp = float(time_str)
                        scene_times.append(timestamp)
                    except (ValueError, IndexError):
                        continue
            
            print(f"  -> Found {len(scene_times)} scene changes")
            return scene_times
            
        except subprocess.TimeoutExpired:
            print(f"  -> Scene detection timed out, using uniform sampling only")
            return []
        except Exception as e:
            print(f"  -> Scene detection error: {e}, using uniform sampling only")
            return []
    
    def calculate_uniform_samples(self, max_frames: int) -> List[float]:
        """
        Calculate evenly spaced sample timestamps.
        
        Args:
            max_frames: Maximum number of frames to sample
            
        Returns:
            List of timestamps (in seconds) for uniform samples
        """
        if self.duration <= 0:
            return []
        
        # Calculate interval
        interval = self.duration / max_frames
        
        # Generate timestamps
        timestamps = []
        for i in range(max_frames):
            timestamp = i * interval
            if timestamp < self.duration:
                timestamps.append(timestamp)
        
        return timestamps
    
    def adaptive_sampling(
        self,
        base_samples: List[float],
        scene_changes: List[float],
        max_total: int,
        min_distance: float = 2.0
    ) -> List[float]:
        """
        Combine uniform and scene-based sampling.
        
        Args:
            base_samples: Uniform sample timestamps
            scene_changes: Scene change timestamps
            max_total: Maximum total frames
            min_distance: Minimum distance between frames in seconds
            
        Returns:
            List of final sample timestamps
        """
        # Start with base samples
        all_samples = set(base_samples)
        
        # Add scene changes that are far enough from existing samples
        for scene_time in scene_changes:
            # Check if this scene change is far enough from existing samples
            too_close = False
            for existing in all_samples:
                if abs(scene_time - existing) < min_distance:
                    too_close = True
                    break
            
            if not too_close:
                all_samples.add(scene_time)
                
                # Stop if we've reached max
                if len(all_samples) >= max_total:
                    break
        
        # Sort and return
        return sorted(list(all_samples))[:max_total]
    
    def format_timecode(self, seconds: float) -> str:
        """
        Convert seconds to HH:MM:SS:FF timecode format.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted timecode string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        frames = int((seconds % 1) * self.framerate)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
    
    def extract_frames(
        self,
        timestamps: List[float],
        output_dir: str,
        max_width: int = 512,
        prefix: str = "frame"
    ) -> Dict[str, Dict]:
        """
        Extract frames at specified timestamps.
        
        Args:
            timestamps: List of timestamps (in seconds) to extract
            output_dir: Directory to save extracted frames
            max_width: Maximum frame width in pixels (maintains aspect ratio)
            prefix: Filename prefix for extracted frames
            
        Returns:
            Dictionary mapping frame filenames to metadata
        """
        os.makedirs(output_dir, exist_ok=True)
        
        extracted_frames = {}
        
        print(f"  -> Extracting {len(timestamps)} frames to {output_dir}...")
        
        for i, timestamp in enumerate(timestamps, 1):
            frame_num = f"{i:03d}"
            output_file = os.path.join(output_dir, f"{prefix}_{frame_num}.jpg")
            timecode = self.format_timecode(timestamp)
            
            try:
                # Extract frame with scaling
                cmd = [
                    self.ffmpeg_cmd,
                    '-ss', str(timestamp),
                    '-i', self.video_path,
                    '-vf', f'scale={max_width}:-1',  # Scale to max_width, maintain aspect ratio
                    '-frames:v', '1',
                    '-q:v', '2',  # High quality JPEG
                    '-y',  # Overwrite
                    output_file,
                    '-loglevel', 'error'
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0 and os.path.exists(output_file):
                    file_size = os.path.getsize(output_file)
                    
                    extracted_frames[os.path.basename(output_file)] = {
                        "timestamp_seconds": timestamp,
                        "timecode_formatted": timecode,
                        "file_path": output_file,
                        "frame_number": i,
                        "file_size_bytes": file_size
                    }
                    
                    print(f"    -> Frame {frame_num}: {timecode} ({timestamp:.2f}s) - {file_size/1024:.1f}KB")
                else:
                    print(f"    -> ❌ Failed to extract frame at {timecode}")
                    
            except subprocess.TimeoutExpired:
                print(f"    -> ❌ Timeout extracting frame at {timecode}")
            except Exception as e:
                print(f"    -> ❌ Error extracting frame at {timecode}: {e}")
        
        print(f"  -> Successfully extracted {len(extracted_frames)}/{len(timestamps)} frames")
        return extracted_frames
    
    def smart_sample(
        self,
        output_dir: str,
        max_width: int = 512,
        scene_threshold: float = 0.3
    ) -> Dict[str, Dict]:
        """
        Perform smart sampling with adaptive frame selection.
        
        Args:
            output_dir: Directory to save extracted frames
            max_width: Maximum frame width in pixels
            scene_threshold: Scene detection threshold
            
        Returns:
            Dictionary mapping frame filenames to metadata
        """
        # Determine sampling config based on duration
        if self.duration < 30:
            config = {
                "max_frames": 12,
                "uniform_cadence": 2.5,
                "adaptive_ratio": 0.3
            }
            print(f"  -> Using 'short_video' config: {config['max_frames']} max frames")
        elif self.duration < 120:
            config = {
                "max_frames": 24,
                "uniform_cadence": 4.0,
                "adaptive_ratio": 0.4
            }
            print(f"  -> Using 'medium_video' config: {config['max_frames']} max frames")
        else:
            config = {
                "max_frames": 36,
                "uniform_cadence": 5.0,
                "adaptive_ratio": 0.5
            }
            print(f"  -> Using 'long_video' config: {config['max_frames']} max frames")
        
        # Calculate base uniform samples
        num_uniform = int(config["max_frames"] * (1 - config["adaptive_ratio"]))
        uniform_samples = self.calculate_uniform_samples(num_uniform)
        
        # Detect scene changes for adaptive sampling (only for videos ≥60s)
        # Short videos skip scene detection for speed (0-2s vs 5-10s)
        if self.duration >= 60:
            scene_changes = self.detect_scenes(scene_threshold)
            print(f"  -> Scene detection enabled (video ≥60s)")
        else:
            scene_changes = []
            print(f"  -> Scene detection skipped (video <60s) - using uniform sampling")
        
        # Combine uniform and adaptive sampling
        final_timestamps = self.adaptive_sampling(
            uniform_samples,
            scene_changes,
            config["max_frames"]
        )
        
        print(f"  -> Final sampling: {len(final_timestamps)} frames "
              f"({len(uniform_samples)} uniform + {len(final_timestamps) - len(uniform_samples)} adaptive)")
        
        # Extract frames
        return self.extract_frames(final_timestamps, output_dir, max_width)


def get_video_info(video_path: str) -> Tuple[float, float]:
    """
    Get video duration and framerate using ffprobe.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Tuple of (duration, framerate)
    """
    try:
        # Find ffprobe
        ffprobe_paths = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', 'ffprobe']
        ffprobe_cmd = None
        
        for path in ffprobe_paths:
            if os.path.exists(path) or path == 'ffprobe':
                ffprobe_cmd = path
                break
        
        if not ffprobe_cmd:
            raise RuntimeError("FFprobe not found")
        
        # Get duration and streams info
        cmd = [
            ffprobe_cmd,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            return None, None
        
        # Parse JSON output
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])
        
        # Find video stream and get framerate
        framerate = 30.0  # Default fallback
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                if 'r_frame_rate' in stream:
                    rate_str = stream['r_frame_rate']
                    if '/' in rate_str:
                        num, den = rate_str.split('/')
                        framerate = float(num) / float(den)
                    else:
                        framerate = float(rate_str)
                break
        
        return duration, framerate
        
    except Exception as e:
        print(f"  -> Error getting video info: {e}")
        return None, None

