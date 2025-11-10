#!/usr/bin/env python3
"""
Footage AutoLog Part B Dashboard

A clean, modern web interface for monitoring Footage AutoLog Part B AI processing.
Shows FileMaker footage IDs and workflow steps in plain language.

Usage:
    python3 dashboard/ftg_dashboard.py
    Then open: http://localhost:9181
"""

from flask import Flask, render_template_string
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from jobs.ftg_autolog_B_queue_jobs import q_step1, q_step2, q_step3, q_step4

app = Flask(__name__)

STEP_NAMES = {
    'ftg_step1': 'Step 1: Assess & Sample Frames',
    'ftg_step2': 'Step 2: Gemini AI Analysis',
    'ftg_step3': 'Step 3: Create Frame Records',
    'ftg_step4': 'Step 4: Audio Transcription'
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Footage AutoLog Part B Dashboard</title>
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
            background: #ffffff;
            color: #37352f;
            min-height: 100vh;
            padding: 32px 48px;
        }
        
        .header {
            margin-bottom: 32px;
            padding-bottom: 16px;
            border-bottom: 1px solid #e9e9e7;
        }
        
        h1 {
            font-size: 32px;
            font-weight: 700;
            color: #37352f;
            margin-bottom: 4px;
        }
        
        .subtitle {
            font-size: 14px;
            color: #787774;
        }
        
        .controls {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            align-items: center;
        }
        
        .search-box {
            flex: 1;
            max-width: 300px;
            padding: 8px 12px;
            border: 1px solid #e9e9e7;
            border-radius: 3px;
            font-size: 14px;
            font-family: inherit;
            background: #ffffff;
            transition: border 0.2s;
        }
        
        .search-box:focus {
            outline: none;
            border-color: #37352f;
        }
        
        .filter-btn {
            padding: 8px 12px;
            border: 1px solid #e9e9e7;
            border-radius: 3px;
            font-size: 14px;
            font-family: inherit;
            background: #ffffff;
            color: #37352f;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .filter-btn:hover {
            background: #f7f7f5;
        }
        
        .filter-btn.active {
            background: #37352f;
            color: #ffffff;
            border-color: #37352f;
        }
        
        .stats-bar {
            display: flex;
            gap: 24px;
            margin-bottom: 16px;
            font-size: 13px;
            color: #787774;
        }
        
        .stat-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .stat-value {
            font-weight: 600;
            color: #37352f;
        }
        
        .table-container {
            border: 1px solid #e9e9e7;
            border-radius: 3px;
            overflow: hidden;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            background: #ffffff;
        }
        
        thead {
            background: #f7f7f5;
            border-bottom: 1px solid #e9e9e7;
        }
        
        th {
            text-align: left;
            padding: 10px 16px;
            font-size: 12px;
            font-weight: 600;
            color: #787774;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        td {
            padding: 12px 16px;
            font-size: 14px;
            color: #37352f;
            border-top: 1px solid #e9e9e7;
        }
        
        tr:hover {
            background: #f7f7f5;
        }
        
        .footage-id {
            font-weight: 600;
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            font-size: 13px;
        }
        
        .status-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 500;
            white-space: nowrap;
        }
        
        .status-processing {
            background: #37352f;
            color: #ffffff;
        }
        
        .status-queued {
            background: #e9e9e7;
            color: #37352f;
        }
        
        .step-name {
            font-size: 13px;
            color: #787774;
        }
        
        .empty-state {
            padding: 48px;
            text-align: center;
            color: #787774;
            font-size: 14px;
        }
        
        .footer {
            margin-top: 24px;
            padding-top: 16px;
            border-top: 1px solid #e9e9e7;
            text-align: center;
            font-size: 12px;
            color: #787774;
        }
        
        @keyframes blink {
            0%, 50%, 100% { opacity: 1; }
            25%, 75% { opacity: 0.3; }
        }
        
        .status-processing {
            animation: blink 2s ease-in-out infinite;
        }
    </style>
    <script>
        let currentFilter = 'all';
        
        function filterTable(filter) {
            currentFilter = filter;
            applyFilters();
            
            // Update button states
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
        }
        
        function searchTable() {
            applyFilters();
        }
        
        function applyFilters() {
            const searchValue = document.getElementById('search').value.toLowerCase();
            const rows = document.querySelectorAll('tbody tr');
            let visibleCount = 0;
            
            rows.forEach(row => {
                const footageId = row.querySelector('.footage-id').textContent.toLowerCase();
                const status = row.dataset.status;
                const step = row.dataset.step;
                
                const matchesSearch = footageId.includes(searchValue);
                const matchesFilter = currentFilter === 'all' || 
                                     (currentFilter === 'processing' && status === 'processing') ||
                                     (currentFilter === 'step1' && step === '1') ||
                                     (currentFilter === 'step2' && step === '2') ||
                                     (currentFilter === 'step3' && step === '3') ||
                                     (currentFilter === 'step4' && step === '4');
                
                if (matchesSearch && matchesFilter) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });
            
            // Show/hide empty state
            const emptyState = document.querySelector('.empty-state');
            if (emptyState) {
                emptyState.style.display = visibleCount === 0 ? 'table-row' : 'none';
            }
        }
    </script>
</head>
<body>
    <div class="header">
        <h1>Footage AutoLog Part B</h1>
        <div class="subtitle">Real-time AI processing workflow</div>
    </div>
    
    <div class="controls">
        <input type="text" id="search" class="search-box" placeholder="Search footage IDs..." onkeyup="searchTable()">
        <button class="filter-btn active" onclick="filterTable('all')">All</button>
        <button class="filter-btn" onclick="filterTable('processing')">Processing</button>
        <button class="filter-btn" onclick="filterTable('step1')">Step 1</button>
        <button class="filter-btn" onclick="filterTable('step2')">Step 2</button>
        <button class="filter-btn" onclick="filterTable('step3')">Step 3</button>
        <button class="filter-btn" onclick="filterTable('step4')">Step 4</button>
    </div>
    
    <div class="stats-bar">
        <div class="stat-item">
            <span>Total in queue:</span>
            <span class="stat-value">{{ total_items }}</span>
        </div>
        <div class="stat-item">
            <span>Processing now:</span>
            <span class="stat-value">{{ total_processing }}</span>
        </div>
        <div class="stat-item">
            <span>Failed:</span>
            <span class="stat-value">{{ total_failed }}</span>
        </div>
        <div class="stat-item">
            <span>Active workers:</span>
            <span class="stat-value">20</span>
        </div>
    </div>
    
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>Footage ID</th>
                    <th>Status</th>
                    <th>Current Step</th>
                </tr>
            </thead>
            <tbody>
                {% for item in items %}
                <tr data-status="{{ item.status }}" data-step="{{ item.step_num }}">
                    <td><span class="footage-id">{{ item.footage_id }}</span></td>
                    <td>
                        <span class="status-badge status-{{ item.status }}">
                            {{ item.status_text }}
                        </span>
                    </td>
                    <td><span class="step-name">{{ item.step_name }}</span></td>
                </tr>
                {% endfor %}
                {% if not items %}
                <tr class="empty-state">
                    <td colspan="3">No items in queue</td>
                </tr>
                {% endif %}
            </tbody>
        </table>
    </div>
    
    <div class="footer">
        ⟳ Auto-refreshing every 5 seconds
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

def get_started_jobs(queue):
    """Get jobs that are currently being processed."""
    try:
        from rq.registry import StartedJobRegistry
        from rq.job import Job
        
        started_registry = StartedJobRegistry(queue=queue)
        job_ids = started_registry.get_job_ids()
        
        processing = []
        for job_id in job_ids[:10]:  # Max 10
            try:
                job = Job.fetch(job_id, connection=queue.connection)
                footage_id = extract_footage_id(job)
                processing.append(footage_id)
            except:
                pass
        
        return processing
    except:
        return []

@app.route('/')
def dashboard():
    """Main dashboard view - flat table of all items."""
    
    items = []
    total_processing = 0
    total_failed = 0
    
    # Queue configurations
    queues = [
        (q_step1, 1, 'Step 1: Assess & Sample'),
        (q_step2, 2, 'Step 2: Gemini Analysis'),
        (q_step3, 3, 'Step 3: Create Frames'),
        (q_step4, 4, 'Step 4: Transcription')
    ]
    
    # Collect all items from all queues
    for queue, step_num, step_name in queues:
        # Get processing items
        processing_jobs = get_started_jobs(queue)
        for footage_id in processing_jobs:
            items.append({
                'footage_id': footage_id,
                'status': 'processing',
                'status_text': 'Processing',
                'step_num': step_num,
                'step_name': step_name
            })
            total_processing += 1
        
        # Get queued items (show more since it's a table)
        for job in queue.jobs[:50]:  # Show up to 50 per queue
            footage_id = extract_footage_id(job)
            items.append({
                'footage_id': footage_id,
                'status': 'queued',
                'status_text': 'Queued',
                'step_num': step_num,
                'step_name': step_name
            })
        
        # Count failed
        try:
            total_failed += queue.failed_job_registry.count
        except:
            pass
    
    # Sort: processing first, then by step number
    items.sort(key=lambda x: (0 if x['status'] == 'processing' else 1, x['step_num']))
    
    return render_template_string(
        HTML_TEMPLATE,
        items=items,
        total_items=len(items),
        total_processing=total_processing,
        total_failed=total_failed
    )

if __name__ == '__main__':
    print("🎬 Starting Footage AutoLog Part B Dashboard...")
    print("📊 Open: http://localhost:9181")
    print("⟳ Auto-refreshes every 5 seconds")
    print("")
    app.run(host='0.0.0.0', port=9181, debug=False)

