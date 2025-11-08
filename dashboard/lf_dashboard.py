#!/usr/bin/env python3
"""
Custom LF AutoLog Dashboard

A clean, modern web interface for monitoring LF AutoLog job processing.
Shows FileMaker IDs and workflow steps in plain language.

Usage:
    python3 dashboard/lf_dashboard.py
    Then open: http://localhost:9181
"""

from flask import Flask, render_template_string
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from jobs.lf_queue_jobs import q_step1, q_step2, q_step3, q_step4, q_step5, q_step6

app = Flask(__name__)

STEP_NAMES = {
    'lf_step1': 'Step 1: Getting File Info',
    'lf_step2': 'Step 2: Creating Thumbnails',
    'lf_step3': 'Step 3: Analyzing & Sampling',
    'lf_step4': 'Step 4: Gemini AI Analysis',
    'lf_step5': 'Step 5: Creating Frame Records',
    'lf_step6': 'Step 6: Audio Transcription'
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>LF AutoLog Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="5">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            color: white;
            margin-bottom: 40px;
        }
        
        h1 {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 10px;
        }
        
        .subtitle {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        
        .stat-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .stat-label {
            font-size: 0.875rem;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: #1f2937;
        }
        
        .stat-value.active {
            color: #10b981;
        }
        
        .stat-value.failed {
            color: #ef4444;
        }
        
        .steps {
            display: grid;
            gap: 20px;
        }
        
        .step-card {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .step-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        
        .step-title {
            font-size: 1.25rem;
            font-weight: 600;
            color: #1f2937;
        }
        
        .step-count {
            display: inline-flex;
            align-items: center;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 0.875rem;
            font-weight: 600;
        }
        
        .step-count.queued {
            background: #dbeafe;
            color: #1e40af;
        }
        
        .step-count.empty {
            background: #f3f4f6;
            color: #6b7280;
        }
        
        .step-count.failed {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .jobs-list {
            display: grid;
            gap: 8px;
        }
        
        .job-item {
            display: flex;
            align-items: center;
            padding: 12px 16px;
            background: #f9fafb;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        
        .job-id {
            font-weight: 600;
            color: #1f2937;
            font-size: 1rem;
        }
        
        .empty-state {
            text-align: center;
            padding: 32px;
            color: #6b7280;
        }
        
        .refresh-note {
            text-align: center;
            color: white;
            opacity: 0.8;
            margin-top: 32px;
            font-size: 0.875rem;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .pulse {
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎬 LF AutoLog Dashboard</h1>
            <p class="subtitle">Real-time workflow monitoring</p>
        </header>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">Total Queued</div>
                <div class="stat-value active">{{ total_queued }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Failed</div>
                <div class="stat-value failed">{{ total_failed }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Active Workers</div>
                <div class="stat-value">31</div>
            </div>
        </div>
        
        <div class="steps">
            {% for step_key, step_name in steps.items() %}
            <div class="step-card">
                <div class="step-header">
                    <div class="step-title">{{ step_name }}</div>
                    {% if queues[step_key]['count'] > 0 %}
                        <span class="step-count queued pulse">{{ queues[step_key]['count'] }} queued</span>
                    {% elif queues[step_key]['failed'] > 0 %}
                        <span class="step-count failed">{{ queues[step_key]['failed'] }} failed</span>
                    {% else %}
                        <span class="step-count empty">Idle</span>
                    {% endif %}
                </div>
                
                {% if queues[step_key]['jobs'] %}
                <div class="jobs-list">
                    {% for job in queues[step_key]['jobs'] %}
                    <div class="job-item">
                        <div class="job-id">{{ job }}</div>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <div class="empty-state">
                    No items in queue
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        
        <p class="refresh-note">⟳ Auto-refreshing every 5 seconds</p>
    </div>
</body>
</html>
"""

def extract_footage_id(job):
    """Extract footage ID from job arguments."""
    try:
        # Job args format: ('LF1554', 'token...')
        if hasattr(job, 'args') and len(job.args) > 0:
            return job.args[0]
        return "Unknown"
    except:
        return "Unknown"

@app.route('/')
def dashboard():
    """Main dashboard view."""
    
    # Get all queues
    queues_data = {
        'lf_step1': {'queue': q_step1, 'count': 0, 'failed': 0, 'jobs': []},
        'lf_step2': {'queue': q_step2, 'count': 0, 'failed': 0, 'jobs': []},
        'lf_step3': {'queue': q_step3, 'count': 0, 'failed': 0, 'jobs': []},
        'lf_step4': {'queue': q_step4, 'count': 0, 'failed': 0, 'jobs': []},
        'lf_step5': {'queue': q_step5, 'count': 0, 'failed': 0, 'jobs': []},
        'lf_step6': {'queue': q_step6, 'count': 0, 'failed': 0, 'jobs': []}
    }
    
    total_queued = 0
    total_failed = 0
    
    # Populate queue data
    for key, data in queues_data.items():
        queue = data['queue']
        
        # Get queued jobs
        jobs = queue.jobs
        data['count'] = len(jobs)
        total_queued += len(jobs)
        
        # Extract footage IDs
        for job in jobs[:10]:  # Show max 10 per queue
            footage_id = extract_footage_id(job)
            data['jobs'].append(footage_id)
        
        # Get failed count
        try:
            data['failed'] = queue.failed_job_registry.count
            total_failed += data['failed']
        except:
            data['failed'] = 0
    
    return render_template_string(
        HTML_TEMPLATE,
        steps=STEP_NAMES,
        queues=queues_data,
        total_queued=total_queued,
        total_failed=total_failed
    )

if __name__ == '__main__':
    print("🎬 Starting LF AutoLog Dashboard...")
    print("📊 Open: http://localhost:9181")
    print("⟳ Auto-refreshes every 5 seconds")
    print("")
    app.run(host='0.0.0.0', port=9181, debug=False)

