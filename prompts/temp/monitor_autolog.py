#!/usr/bin/env python3
"""
Real-time AutoLog Monitor

This script monitors the footage autolog process in real-time, providing:
- Live status updates
- Frame creation tracking
- Thumbnail generation monitoring
- Error detection and reporting
- Session logging
"""

import sys
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime
import warnings
import requests
import json

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from utils.logger import get_logger, create_session_log

class AutoLogMonitor:
    def __init__(self):
        self.logger = get_logger("autolog_monitor")
        self.session_logger, self.session_file = create_session_log("monitor_session")
        self.token = config.get_token()
        self.monitoring = False
        self.stats = {
            'footage_processed': 0,
            'frames_created': 0,
            'thumbnails_generated': 0,
            'errors_detected': 0,
            'start_time': None
        }
        
    def get_footage_status_counts(self):
        """Get current counts by status."""
        try:
            # Query all footage records
            response = requests.post(
                config.url("layouts/FOOTAGE/_find"),
                headers=config.api_headers(self.token),
                json={"query": [{"INFO_FTG_ID": "*"}], "limit": 1000},
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                records = response.json()['response']['data']
                status_counts = {}
                
                for record in records:
                    status = record['fieldData'].get('AutoLog_Status', 'Unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                return status_counts
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get status counts: {e}")
            
        return {}
    
    def get_frame_counts(self):
        """Get frame record statistics."""
        try:
            # Query all frame records
            response = requests.post(
                config.url("layouts/FRAMES/_find"),
                headers=config.api_headers(self.token),
                json={"query": [{"FRAMES_ID": "*"}], "limit": 5000},
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                records = response.json()['response']['data']
                
                total_frames = len(records)
                frames_with_thumbnails = 0
                frames_by_status = {}
                
                for record in records:
                    # Check thumbnail
                    if record['fieldData'].get('FRAMES_Thumbnail', '').strip():
                        frames_with_thumbnails += 1
                    
                    # Count by status
                    status = record['fieldData'].get('FRAMES_Status', 'Unknown')
                    frames_by_status[status] = frames_by_status.get(status, 0) + 1
                
                return {
                    'total': total_frames,
                    'with_thumbnails': frames_with_thumbnails,
                    'by_status': frames_by_status
                }
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get frame counts: {e}")
            
        return {'total': 0, 'with_thumbnails': 0, 'by_status': {}}
    
    def print_status_report(self):
        """Print current system status."""
        print("\n" + "="*80)
        print(f"📊 AUTOLOG MONITOR - {datetime.now().strftime('%H:%M:%S')}")
        print("="*80)
        
        # Footage status counts
        footage_counts = self.get_footage_status_counts()
        if footage_counts:
            print("\n📋 FOOTAGE STATUS:")
            for status, count in sorted(footage_counts.items()):
                emoji = "🚀" if "0 -" in status else "🔄" if "Processing" in status else "✅" if "Complete" in status else "⚠️"
                print(f"   {emoji} {status}: {count}")
        
        # Frame statistics
        frame_stats = self.get_frame_counts()
        if frame_stats['total'] > 0:
            thumbnail_pct = (frame_stats['with_thumbnails'] / frame_stats['total']) * 100
            print(f"\n🖼️ FRAME STATISTICS:")
            print(f"   Total frames: {frame_stats['total']}")
            print(f"   With thumbnails: {frame_stats['with_thumbnails']} ({thumbnail_pct:.1f}%)")
            
            if frame_stats['by_status']:
                print(f"   By status:")
                for status, count in sorted(frame_stats['by_status'].items()):
                    print(f"     • {status}: {count}")
        
        # Processing statistics
        if self.stats['start_time']:
            runtime = (datetime.now() - self.stats['start_time']).total_seconds()
            print(f"\n⏱️ SESSION STATISTICS:")
            print(f"   Runtime: {runtime:.0f}s")
            print(f"   Footage processed: {self.stats['footage_processed']}")
            print(f"   Frames created: {self.stats['frames_created']}")
            print(f"   Thumbnails generated: {self.stats['thumbnails_generated']}")
            print(f"   Errors detected: {self.stats['errors_detected']}")
        
        print(f"\n📝 Session log: {self.session_file}")
        print("="*80)
    
    def monitor_log_file(self, log_file):
        """Monitor a log file for changes."""
        if not log_file.exists():
            return
            
        # Follow the log file
        with open(log_file, 'r') as f:
            # Go to end of file
            f.seek(0, 2)
            
            while self.monitoring:
                line = f.readline()
                if line:
                    line = line.strip()
                    if line:
                        # Parse and categorize log lines
                        self.process_log_line(line)
                        print(f"📝 {datetime.now().strftime('%H:%M:%S')} | {line}")
                else:
                    time.sleep(0.1)
    
    def process_log_line(self, line):
        """Process and categorize log lines."""
        line_lower = line.lower()
        
        # Track statistics
        if "created missing frame" in line_lower:
            self.stats['frames_created'] += 1
        elif "generated thumbnail" in line_lower:
            self.stats['thumbnails_generated'] += 1
        elif "error" in line_lower or "failed" in line_lower:
            self.stats['errors_detected'] += 1
        elif "workflow completed successfully" in line_lower:
            self.stats['footage_processed'] += 1
        
        # Log significant events
        if "error" in line_lower or "failed" in line_lower:
            self.logger.error(f"Detected error: {line}")
            self.session_logger.error(line)
        elif "created missing frame" in line_lower or "generated thumbnail" in line_lower:
            self.logger.info(f"Progress: {line}")
            self.session_logger.info(line)
    
    def start_autolog_process(self):
        """Start the autolog process."""
        self.logger.info("🚀 Starting footage autolog process")
        self.session_logger.info("Starting autolog monitoring session")
        
        try:
            # Start autolog in background
            autolog_cmd = ["python3", "jobs/footage_autolog.py"]
            self.autolog_process = subprocess.Popen(
                autolog_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.logger.info(f"✅ AutoLog process started (PID: {self.autolog_process.pid})")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start autolog: {e}")
            return False
    
    def monitor_autolog_output(self):
        """Monitor autolog process output."""
        if not hasattr(self, 'autolog_process'):
            return
            
        while self.monitoring and self.autolog_process.poll() is None:
            try:
                line = self.autolog_process.stdout.readline()
                if line:
                    line = line.strip()
                    if line:
                        self.process_log_line(line)
                        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                        print(f"🔄 {timestamp} | {line}")
                else:
                    time.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error reading autolog output: {e}")
                break
    
    def run_monitor(self, start_autolog=True):
        """Run the monitoring session."""
        print("🚀 AutoLog Monitor Starting...")
        print(f"📝 Session log: {self.session_file}")
        print("Press Ctrl+C to stop monitoring\n")
        
        self.monitoring = True
        self.stats['start_time'] = datetime.now()
        
        try:
            if start_autolog:
                if not self.start_autolog_process():
                    return
                
                # Start monitoring thread
                monitor_thread = threading.Thread(target=self.monitor_autolog_output)
                monitor_thread.daemon = True
                monitor_thread.start()
            
            # Status reporting loop
            last_report = 0
            while self.monitoring:
                current_time = time.time()
                
                # Print status report every 30 seconds
                if current_time - last_report >= 30:
                    self.print_status_report()
                    last_report = current_time
                
                time.sleep(5)
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
        except Exception as e:
            self.logger.error(f"❌ Monitor error: {e}")
        finally:
            self.monitoring = False
            if hasattr(self, 'autolog_process'):
                self.autolog_process.terminate()
            
            # Final report
            self.print_status_report()
            self.logger.info("📊 Monitoring session completed")

def main():
    monitor = AutoLogMonitor()
    
    # Check if autolog is already running
    print("🔍 Checking for existing autolog process...")
    
    # Start monitoring
    monitor.run_monitor(start_autolog=True)

if __name__ == "__main__":
    main() 