# LaunchAgent Setup Guide

This guide covers the automated LaunchAgent tasks for the FileMaker Backend system.

## Overview

Two LaunchAgents are configured to run automated tasks:

1. **Bin Scanner** - Scans Avid project bins daily at 6:00 AM
2. **Auto-Commit** - Commits and pushes changes daily at 2:00 AM

## Installation

Both LaunchAgents are installed in:
```
~/Library/LaunchAgents/
```

**Files:**
- `com.filemaker.binscanner.plist` - Bin scanning agent
- `com.filemaker.autocommit.plist` - Auto-commit agent

## Bin Scanner (com.filemaker.binscanner)

### What It Does
- Scans `/Volumes/PROJECT_E2E/E2E` for Avid bins (.avb files)
- Generates three bin lists: stills, archival footage, live footage
- Saves lists to `tags/` folder for AI workflows

### Schedule
**Daily at 6:00 AM**

### Configuration
```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>6</integer>
    <key>Minute</key>
    <integer>0</integer>
</dict>
```

### Logs
- **Output**: `/tmp/bin-scan.log`
- **Errors**: `/tmp/bin-scan-error.log`

### Management Commands

**Load (Enable):**
```bash
launchctl load ~/Library/LaunchAgents/com.filemaker.binscanner.plist
```

**Unload (Disable):**
```bash
launchctl unload ~/Library/LaunchAgents/com.filemaker.binscanner.plist
```

**Run Manually:**
```bash
launchctl start com.filemaker.binscanner
```

**Check Status:**
```bash
launchctl list | grep filemaker
```

**View Logs:**
```bash
cat /tmp/bin-scan.log
cat /tmp/bin-scan-error.log
```

### API Details
- **Endpoint**: `http://localhost:8081/scan/bins`
- **Method**: POST
- **Authentication**: X-API-Key header (from .env)

## Auto-Commit (com.filemaker.autocommit)

### What It Does
- Adds all changes in the repository
- Creates timestamped commit
- Pushes to `origin/main`
- Logs results

### Schedule
**Daily at 2:00 AM**

### Configuration
```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>2</integer>
    <key>Minute</key>
    <integer>0</integer>
</dict>
```

### Logs
- **LaunchAgent Output**: `/tmp/auto-commit.log`
- **Script Output**: `~/auto_commit.log`

### Management Commands

**Load (Enable):**
```bash
launchctl load ~/Library/LaunchAgents/com.filemaker.autocommit.plist
```

**Unload (Disable):**
```bash
launchctl unload ~/Library/LaunchAgents/com.filemaker.autocommit.plist
```

**Run Manually:**
```bash
launchctl start com.filemaker.autocommit
```

**Check Status:**
```bash
launchctl list | grep filemaker
```

**View Logs:**
```bash
cat ~/auto_commit.log
cat /tmp/auto-commit.log
```

### Script Location
`/Users/admin/Documents/Github/Filemaker-Backend/auto_commit.sh`

## Troubleshooting

### Check if LaunchAgents are Loaded
```bash
launchctl list | grep filemaker
```

**Expected Output:**
```
-	0	com.filemaker.autocommit
-	0	com.filemaker.binscanner
```

The `-` at the beginning means they're loaded but not currently running (normal for scheduled tasks).

### Bin Scanner Not Working

**Problem**: Bin scanner fails or produces empty bin lists

**Checks:**
1. Is the API running?
   ```bash
   ps aux | grep uvicorn | grep -v grep
   ```

2. Is PROJECT_E2E volume mounted?
   ```bash
   ls -la /Volumes/PROJECT_E2E/
   ```

3. Check error log:
   ```bash
   cat /tmp/bin-scan-error.log
   ```

4. Test the endpoint manually:
   ```bash
   curl -X POST -H "X-API-Key: your_api_key_here" http://localhost:8081/scan/bins
   ```

5. Check API logs:
   ```bash
   tail -f /Users/admin/Documents/Github/Filemaker-Backend/api.log
   ```

### Auto-Commit Not Working

**Problem**: Changes aren't being committed

**Checks:**
1. Is the script executable?
   ```bash
   ls -la /Users/admin/Documents/Github/Filemaker-Backend/auto_commit.sh
   ```

2. Check script logs:
   ```bash
   cat ~/auto_commit.log
   ```

3. Test the script manually:
   ```bash
   /Users/admin/Documents/Github/Filemaker-Backend/auto_commit.sh
   ```

4. Check git status:
   ```bash
   cd /Users/admin/Documents/Github/Filemaker-Backend
   git status
   ```

### Permission Errors

If you see permission errors, the LaunchAgent might not have permission to access certain files or volumes.

**Fix:**
1. Grant Full Disk Access to `/bin/bash` and `/usr/bin/curl` in System Preferences > Security & Privacy > Privacy > Full Disk Access

### Restart After System Reboot

LaunchAgents automatically restart after system reboot. No action needed.

To verify after reboot:
```bash
launchctl list | grep filemaker
```

## Changing Schedules

### Modify Schedule Times

Edit the plist files and change the hour/minute values:

```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>6</integer>  <!-- Change this -->
    <key>Minute</key>
    <integer>0</integer>  <!-- Change this -->
</dict>
```

**After editing, reload:**
```bash
launchctl unload ~/Library/LaunchAgents/com.filemaker.binscanner.plist
launchctl load ~/Library/LaunchAgents/com.filemaker.binscanner.plist
```

### Run Multiple Times Per Day

To run at multiple times (e.g., 6 AM and 6 PM), duplicate the `StartCalendarInterval` dict:

```xml
<key>StartCalendarInterval</key>
<array>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <dict>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</array>
```

## Monitoring

### Check Recent Activity

**Bin Scanner:**
```bash
tail -20 /tmp/bin-scan.log
```

**Auto-Commit:**
```bash
tail -20 ~/auto_commit.log
```

### Set Up Notifications (Optional)

Add notification on failure by creating a wrapper script that sends notifications:

```bash
#!/bin/bash
/path/to/original/script.sh
if [ $? -ne 0 ]; then
    osascript -e 'display notification "Task failed" with title "LaunchAgent Error"'
fi
```

## Uninstall

To completely remove the LaunchAgents:

```bash
# Unload them
launchctl unload ~/Library/LaunchAgents/com.filemaker.binscanner.plist
launchctl unload ~/Library/LaunchAgents/com.filemaker.autocommit.plist

# Delete the plist files
rm ~/Library/LaunchAgents/com.filemaker.binscanner.plist
rm ~/Library/LaunchAgents/com.filemaker.autocommit.plist
```

## Summary

✅ **Bin Scanner** - Keeps Avid bin lists fresh for AI tagging workflows
✅ **Auto-Commit** - Automatically backs up daily changes to git

Both agents run automatically in the background and require no manual intervention.

