#!/usr/bin/env python3
"""
Unified API Monitoring Dashboard

A comprehensive web interface for monitoring all FileMaker automation API activity.
Shows all jobs (API and queued) with clean filtering by asset type and status.

Usage:
    python3 dashboard/ftg_dashboard.py
    Then open: http://localhost:9181
"""

from flask import Flask, render_template_string
import requests
import sys
from pathlib import Path

app = Flask(__name__)

# Dashboard will fetch data from API server
API_BASE_URL = "http://localhost:8081"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AutoLog Dashboard</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🪵</text></svg>">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="300">
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
            margin-bottom: 24px;
            padding-bottom: 12px;
            border-bottom: 1px solid #e9e9e7;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .header-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        h1 {
            font-size: 28px;
            font-weight: 700;
            color: #37352f;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .log-icon {
            font-size: 24px;
            line-height: 1;
        }
        
        .api-status {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 500;
        }
        
        .api-status.healthy {
            background: #d3f9d8;
            color: #2b8a3e;
        }
        
        .api-status.error {
            background: #ffe3e3;
            color: #c92a2a;
        }
        
        .refresh-btn {
            padding: 3px 8px;
            border: 1px solid #e9e9e7;
            border-radius: 3px;
            font-size: 11px;
            font-family: inherit;
            background: #ffffff;
            color: #787774;
            cursor: pointer;
            transition: all 0.2s;
            margin-left: 8px;
        }
        
        .refresh-btn:hover {
            background: #37352f;
            color: #ffffff;
            border-color: #37352f;
        }
        
        .refresh-btn:active {
            transform: scale(0.95);
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
            padding: 7px 12px;
            border: 1px solid #e9e9e7;
            border-radius: 3px;
            font-size: 13px;
            font-family: inherit;
            background: #ffffff;
            transition: border 0.2s;
        }
        
        .search-box:focus {
            outline: none;
            border-color: #37352f;
        }
        
        .filter-dropdown {
            position: relative;
        }
        
        .filter-trigger {
            padding: 7px 12px;
            border: 1px solid #e9e9e7;
            border-radius: 3px;
            font-size: 13px;
            font-family: inherit;
            background: #ffffff;
            color: #37352f;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .filter-trigger:hover {
            background: #f7f7f5;
        }
        
        .filter-trigger.active {
            background: #37352f;
            color: #ffffff;
            border-color: #37352f;
        }
        
        .filter-menu {
            position: absolute;
            top: calc(100% + 4px);
            left: 0;
            background: #ffffff;
            border: 1px solid #e9e9e7;
            border-radius: 3px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            padding: 8px;
            min-width: 200px;
            z-index: 1000;
            display: none;
        }
        
        .filter-menu.show {
            display: block;
        }
        
        .filter-option {
            padding: 6px 10px;
            border-radius: 3px;
            cursor: pointer;
            transition: background 0.15s;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .filter-option:hover {
            background: #f7f7f5;
        }
        
        .filter-checkbox {
            width: 16px;
            height: 16px;
            border: 1.5px solid #e9e9e7;
            border-radius: 3px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        
        .filter-option.selected .filter-checkbox {
            background: #37352f;
            border-color: #37352f;
            color: #ffffff;
        }
        
        .filter-option.selected .filter-checkbox:before {
            content: '✓';
            font-size: 11px;
        }
        
        .selected-badges {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }
        
        .selected-badge {
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            background: #e9e9e7;
            color: #37352f;
        }
        
        .stats-bar {
            display: flex;
            gap: 20px;
            margin-top: 24px;
            padding-top: 16px;
            border-top: 1px solid #e9e9e7;
            font-size: 12px;
            color: #9b9a97;
            flex-wrap: wrap;
        }
        
        .stat-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        .stat-value {
            font-weight: 500;
            color: #787774;
        }
        
        .table-container {
            border: 1px solid #e9e9e7;
            border-radius: 3px;
            overflow: hidden;
            background: #ffffff;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
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
            cursor: pointer;
            user-select: none;
            transition: background 0.15s;
            position: relative;
        }
        
        th:hover {
            background: #ececea;
        }
        
        th.sortable:after {
            content: ' ↕';
            opacity: 0.3;
            font-size: 10px;
        }
        
        th.sort-asc:after {
            content: ' ↑';
            opacity: 1;
        }
        
        th.sort-desc:after {
            content: ' ↓';
            opacity: 1;
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
        
        .filemaker-id {
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            font-size: 13px;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 500;
            white-space: nowrap;
        }
        
        /* Status badges */
        .status-running {
            background: #37352f;
            color: #ffffff;
            animation: pulse 2s ease-in-out infinite;
        }
        
        .status-completed {
            background: #d3f9d8;
            color: #2b8a3e;
        }
        
        .status-failed {
            background: #ffe3e3;
            color: #c92a2a;
        }
        
        .status-queued {
            background: #e9e9e7;
            color: #37352f;
        }
        
        /* Media type badges */
        .media-stills {
            background: #e7f5ff;
            color: #1971c2;
        }
        
        .media-footage {
            background: #ffe3e3;
            color: #c92a2a;
        }
        
        .media-music {
            background: #d3f9d8;
            color: #2b8a3e;
        }
        
        .media-metadata {
            background: #f3e5ff;
            color: #862e9c;
        }
        
        .media-avid {
            background: #fff3bf;
            color: #e67700;
        }
        
        .media-system {
            background: #e3fafc;
            color: #0c8599;
        }
        
        .media-other {
            background: #e9e9e7;
            color: #37352f;
        }
        
        .job-name {
            font-size: 13px;
            color: #787774;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .duration {
            font-size: 13px;
            color: #787774;
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
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
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .error-message {
            padding: 16px;
            margin-bottom: 16px;
            background: #ffe3e3;
            border: 1px solid #ffc9c9;
            border-radius: 3px;
            color: #c92a2a;
            font-size: 14px;
        }
    </style>
    <script>
        let selectedTypes = [];
        let selectedStatuses = [];
        
        function toggleDropdown(dropdownId) {
            const menu = document.getElementById(dropdownId);
            const allMenus = document.querySelectorAll('.filter-menu');
            
            // Close other menus
            allMenus.forEach(m => {
                if (m.id !== dropdownId) m.classList.remove('show');
            });
            
            menu.classList.toggle('show');
        }
        
        function toggleFilter(filterType, value) {
            if (filterType === 'type') {
                const index = selectedTypes.indexOf(value);
                if (index > -1) {
                    selectedTypes.splice(index, 1);
                } else {
                    selectedTypes.push(value);
                }
            } else if (filterType === 'status') {
                const index = selectedStatuses.indexOf(value);
                if (index > -1) {
                    selectedStatuses.splice(index, 1);
                } else {
                    selectedStatuses.push(value);
                }
            }
            
            updateFilterUI();
            applyFilters();
        }
        
        function updateFilterUI() {
            // Update checkboxes
            document.querySelectorAll('.filter-option').forEach(opt => {
                const type = opt.dataset.filterType;
                const value = opt.dataset.value;
                
                if (type === 'type' && selectedTypes.includes(value)) {
                    opt.classList.add('selected');
                } else if (type === 'status' && selectedStatuses.includes(value)) {
                    opt.classList.add('selected');
                } else {
                    opt.classList.remove('selected');
                }
            });
            
            // Update trigger button state
            const typeBtn = document.getElementById('type-trigger');
            const statusBtn = document.getElementById('status-trigger');
            
            if (selectedTypes.length > 0) {
                typeBtn.classList.add('active');
            } else {
                typeBtn.classList.remove('active');
            }
            
            if (selectedStatuses.length > 0) {
                statusBtn.classList.add('active');
            } else {
                statusBtn.classList.remove('active');
            }
        }
        
        function applyFilters() {
            const searchValue = document.getElementById('search').value.toLowerCase().trim();
            const rows = document.querySelectorAll('tbody tr:not(.empty-state)');
            let visibleCount = 0;
            
            rows.forEach(row => {
                // Get all searchable text from the row
                const filmakerId = (row.dataset.filmakerId || '').toLowerCase();
                const jobName = (row.dataset.jobName || '').toLowerCase();
                const mediaType = row.dataset.mediaType;
                const status = row.dataset.status;
                
                // Also search in visible text content
                const rowText = row.textContent.toLowerCase();
                
                // Match search across all text in the row
                const matchesSearch = searchValue === '' || 
                                     filmakerId.includes(searchValue) || 
                                     jobName.includes(searchValue) ||
                                     rowText.includes(searchValue);
                                     
                const matchesType = selectedTypes.length === 0 || selectedTypes.includes(mediaType);
                const matchesStatus = selectedStatuses.length === 0 || selectedStatuses.includes(status);
                
                if (matchesSearch && matchesType && matchesStatus) {
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
        
        // Close dropdowns when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.filter-dropdown')) {
                document.querySelectorAll('.filter-menu').forEach(m => m.classList.remove('show'));
            }
        });
        
        // Table sorting
        let currentSort = { column: null, direction: 'asc' };
        
        function sortTable(columnIndex) {
            const table = document.querySelector('table tbody');
            const rows = Array.from(table.querySelectorAll('tr:not(.empty-state)'));
            const header = document.querySelectorAll('th')[columnIndex];
            
            // Determine sort direction
            if (currentSort.column === columnIndex) {
                currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                currentSort.direction = 'asc';
            }
            currentSort.column = columnIndex;
            
            // Remove sort classes from all headers
            document.querySelectorAll('th').forEach(th => {
                th.classList.remove('sort-asc', 'sort-desc');
            });
            
            // Add sort class to current header
            header.classList.add(currentSort.direction === 'asc' ? 'sort-asc' : 'sort-desc');
            
            // Sort rows
            rows.sort((a, b) => {
                const aCell = a.children[columnIndex];
                const bCell = b.children[columnIndex];
                
                let aValue, bValue;
                
                // Get values based on column
                if (columnIndex === 0) { // FileMaker ID
                    aValue = aCell.textContent.trim();
                    bValue = bCell.textContent.trim();
                } else if (columnIndex === 1) { // Type
                    aValue = aCell.textContent.trim();
                    bValue = bCell.textContent.trim();
                } else if (columnIndex === 2) { // Job
                    aValue = aCell.textContent.trim();
                    bValue = bCell.textContent.trim();
                } else if (columnIndex === 3) { // Status
                    aValue = aCell.textContent.trim();
                    bValue = bCell.textContent.trim();
                } else if (columnIndex === 4) { // Duration
                    // Parse duration to seconds for proper sorting
                    aValue = parseDuration(aCell.textContent.trim());
                    bValue = parseDuration(bCell.textContent.trim());
                }
                
                // Compare values
                if (aValue === '-' || aValue === '') return 1;
                if (bValue === '-' || bValue === '') return -1;
                
                if (typeof aValue === 'number' && typeof bValue === 'number') {
                    return currentSort.direction === 'asc' ? aValue - bValue : bValue - aValue;
                } else {
                    return currentSort.direction === 'asc' 
                        ? aValue.localeCompare(bValue)
                        : bValue.localeCompare(aValue);
                }
            });
            
            // Reorder rows in DOM
            rows.forEach(row => table.appendChild(row));
        }
        
        function parseDuration(durationStr) {
            if (durationStr === '-' || !durationStr) return 0;
            
            let seconds = 0;
            const parts = durationStr.match(/(\d+)m\s*(\d+)s|(\d+)s/);
            
            if (parts) {
                if (parts[1]) { // Has minutes
                    seconds = parseInt(parts[1]) * 60 + parseInt(parts[2]);
                } else if (parts[3]) { // Just seconds
                    seconds = parseInt(parts[3]);
                }
            }
            
            return seconds;
        }
    </script>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <h1>
                <span class="log-icon">🪵</span>
                AutoLog
            </h1>
        </div>
        <span class="api-status {{ 'healthy' if api_connected else 'error' }}">
            {{ '● Connected' if api_connected else '● Disconnected' }}
        </span>
    </div>
    
    {% if not api_connected %}
    <div class="error-message">
        ⚠️ Cannot connect to API server at {{ api_url }}. Make sure the API is running on port 8081.
    </div>
    {% endif %}
    
    <div class="controls">
        <input type="text" id="search" class="search-box" placeholder="Search..." onkeyup="applyFilters()">
        
        <div class="filter-dropdown">
            <button class="filter-trigger" id="type-trigger" onclick="toggleDropdown('type-menu')">
                Type ▾
            </button>
            <div class="filter-menu" id="type-menu">
                <div class="filter-option" data-filter-type="type" data-value="stills" onclick="toggleFilter('type', 'stills')">
                    <div class="filter-checkbox"></div>
                    <span>Stills</span>
                </div>
                <div class="filter-option" data-filter-type="type" data-value="footage" onclick="toggleFilter('type', 'footage')">
                    <div class="filter-checkbox"></div>
                    <span>Footage</span>
                </div>
                <div class="filter-option" data-filter-type="type" data-value="music" onclick="toggleFilter('type', 'music')">
                    <div class="filter-checkbox"></div>
                    <span>Music</span>
                </div>
                <div class="filter-option" data-filter-type="type" data-value="avid" onclick="toggleFilter('type', 'avid')">
                    <div class="filter-checkbox"></div>
                    <span>Avid</span>
                </div>
                <div class="filter-option" data-filter-type="type" data-value="system" onclick="toggleFilter('type', 'system')">
                    <div class="filter-checkbox"></div>
                    <span>System</span>
                </div>
                <div class="filter-option" data-filter-type="type" data-value="other" onclick="toggleFilter('type', 'other')">
                    <div class="filter-checkbox"></div>
                    <span>Other</span>
                </div>
            </div>
        </div>
        
        <div class="filter-dropdown">
            <button class="filter-trigger" id="status-trigger" onclick="toggleDropdown('status-menu')">
                Status ▾
            </button>
            <div class="filter-menu" id="status-menu">
                <div class="filter-option" data-filter-type="status" data-value="running" onclick="toggleFilter('status', 'running')">
                    <div class="filter-checkbox"></div>
                    <span>Running</span>
                </div>
                <div class="filter-option" data-filter-type="status" data-value="queued" onclick="toggleFilter('status', 'queued')">
                    <div class="filter-checkbox"></div>
                    <span>Queued</span>
                </div>
                <div class="filter-option" data-filter-type="status" data-value="completed" onclick="toggleFilter('status', 'completed')">
                    <div class="filter-checkbox"></div>
                    <span>Completed</span>
                </div>
                <div class="filter-option" data-filter-type="status" data-value="failed" onclick="toggleFilter('status', 'failed')">
                    <div class="filter-checkbox"></div>
                    <span>Failed</span>
                </div>
            </div>
        </div>
    </div>
    
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th class="sortable" onclick="sortTable(0)" title="Click to sort">FileMaker ID</th>
                    <th class="sortable" onclick="sortTable(1)" title="Click to sort">Type</th>
                    <th class="sortable" onclick="sortTable(2)" title="Click to sort">Job</th>
                    <th class="sortable" onclick="sortTable(3)" title="Click to sort">Status</th>
                    <th class="sortable" onclick="sortTable(4)" title="Click to sort">Duration</th>
                </tr>
            </thead>
            <tbody>
                {% for job in jobs %}
                <tr data-filemaker-id="{{ job.filemaker_id or '' }}" 
                    data-job-name="{{ job.job_name }}"
                    data-media-type="{{ job.media_type }}" 
                    data-status="{{ job.status }}">
                    <td>
                        <span class="filemaker-id">
                            {{ job.filemaker_id or '-' }}
                        </span>
                    </td>
                    <td>
                        <span class="badge media-{{ job.media_type }}">
                            {{ job.media_type|capitalize }}
                        </span>
                    </td>
                    <td>
                        <span class="job-name" title="{{ job.job_name }}">
                            {{ job.job_name }}
                        </span>
                    </td>
                    <td>
                        <span class="badge status-{{ job.status }}">
                            {{ job.status|capitalize }}
                        </span>
                    </td>
                    <td>
                        <span class="duration">
                            {% if job.duration_seconds %}
                                {% if job.duration_seconds < 60 %}
                                    {{ job.duration_seconds|round|int }}s
                                {% else %}
                                    {{ (job.duration_seconds / 60)|round|int }}m {{ (job.duration_seconds % 60)|round|int }}s
                                {% endif %}
                            {% else %}
                                -
                            {% endif %}
                        </span>
                    </td>
                </tr>
                {% endfor %}
                
                {% if not jobs %}
                <tr class="empty-state">
                    <td colspan="5">
                        No jobs in history - API is idle<br>
                        <small style="color: #787774; font-size: 12px; margin-top: 8px; display: block;">
                            This dashboard shows the last 100 jobs submitted since API startup. 
                            Trigger a workflow to see it appear here in real-time!
                        </small>
                    </td>
                </tr>
                {% endif %}
            </tbody>
        </table>
    </div>
    
    <div class="stats-bar">
        <div class="stat-item">
            <span>Jobs:</span>
            <span class="stat-value">{{ stats.total_api_jobs }}</span>
        </div>
        <div class="stat-item">
            <span>Running:</span>
            <span class="stat-value">{{ stats.api_running }}</span>
        </div>
        <div class="stat-item">
            <span>Queued:</span>
            <span class="stat-value">{{ stats.redis_queued }}</span>
        </div>
        <div class="stat-item">
            <span>Completed:</span>
            <span class="stat-value">{{ stats.api_completed }}</span>
        </div>
        <div class="stat-item">
            <span>Failed:</span>
            <span class="stat-value">{{ stats.api_failed }}</span>
        </div>
        <div class="stat-item" style="margin-left: auto; color: #9b9a97; display: flex; align-items: center;">
            <span>⟳ Auto-refresh: 5min • {{ timestamp }}</span>
            <button class="refresh-btn" onclick="window.location.reload()">Refresh</button>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Main unified dashboard view."""
    
    # Try to fetch data from API
    api_connected = False
    jobs = []
    stats = {
        'total_api_jobs': 0,
        'api_running': 0,
        'api_completed': 0,
        'api_failed': 0,
        'redis_queued': 0,
        'redis_processing': 0
    }
    
    try:
        response = requests.get(f"{API_BASE_URL}/dashboard/data", timeout=2)
        if response.status_code == 200:
            api_connected = True
            data = response.json()
            
            # Process API jobs
            api_jobs = data.get('api_jobs', [])
            
            # Process Redis queues into job format
            redis_queues = data.get('redis_queues', {})
            redis_jobs = []
            
            for queue_name, queue_data in redis_queues.items():
                # Add processing items
                for item_id in queue_data.get('processing_items', []):
                    redis_jobs.append({
                        'job_id': f'redis_{queue_name}_{item_id}',
                        'job_name': f'Footage Part B - {queue_name.replace("_", " ").title()}',
                        'media_type': 'footage',
                        'filemaker_id': item_id,
                        'status': 'running',
                        'duration_seconds': None
                    })
                
                # Add queued items (show up to 20 per queue)
                for item_id in queue_data.get('queued_items', [])[:20]:
                    redis_jobs.append({
                        'job_id': f'redis_{queue_name}_queued_{item_id}',
                        'job_name': f'Footage Part B - {queue_name.replace("_", " ").title()}',
                        'media_type': 'footage',
                        'filemaker_id': item_id,
                        'status': 'queued',
                        'duration_seconds': None
                    })
            
            # Combine jobs: running API first, then running Redis, then queued Redis, then completed/failed
            jobs = []
            
            # Running API jobs
            jobs.extend([j for j in api_jobs if j['status'] == 'running'])
            
            # Running Redis jobs
            jobs.extend([j for j in redis_jobs if j['status'] == 'running'])
            
            # Queued Redis jobs
            jobs.extend([j for j in redis_jobs if j['status'] == 'queued'])
            
            # Completed and failed API jobs (most recent first)
            completed_failed = [j for j in api_jobs if j['status'] in ['completed', 'failed']]
            jobs.extend(completed_failed[:50])  # Limit to last 50 completed/failed
            
            stats = data.get('stats', stats)
            
    except requests.exceptions.RequestException as e:
        # API not available
        pass
    
    from datetime import datetime
    
    return render_template_string(
        HTML_TEMPLATE,
        api_connected=api_connected,
        api_url=API_BASE_URL,
        jobs=jobs,
        stats=stats,
        timestamp=datetime.now().strftime('%I:%M:%S %p')
    )

if __name__ == '__main__':
    print("📊 Starting AutoLog Dashboard...")
    print("🌐 Open: http://localhost:9181")
    print("⟳ Auto-refresh: 5 minutes")
    print("🔗 API: " + API_BASE_URL)
    print("")
    app.run(host='0.0.0.0', port=9181, debug=False)
