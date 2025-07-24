# Automated Git Commit System

This document describes the automated git commit system set up for the Filemaker-Backend repository.

## Overview

The system automatically commits all changes to the repository twice daily:
- **12:00 AM (midnight)** - Captures evening/late work
- **12:00 PM (noon)** - Captures morning work

This ensures no work is lost and provides regular version control checkpoints.

## Components

### 1. Auto-Commit Script (`auto_commit.sh`)

Located at: `/Users/admin/Documents/Github/Filemaker-Backend/auto_commit.sh`

**Features:**
- Automatically adds all changes (`git add .`)
- Only commits if there are actual changes (no empty commits)
- Creates timestamped commit messages
- Logs all activity for monitoring
- Optionally pushes to remote (currently disabled)

**Script Contents:**
```bash
#!/bin/bash

# Navigate to your repository
cd /Users/admin/Documents/Github/Filemaker-Backend

# Add all changes
git add .

# Check if there are any changes to commit
if ! git diff --staged --quiet; then
    # Create commit with timestamp
    git commit -m "Daily auto-commit: $(date '+%Y-%m-%d %H:%M:%S')"
    
    # Optionally push to remote (uncomment if desired)
    # git push origin main
    
    echo "$(date): Auto-commit completed successfully" >> ~/auto_commit.log
else
    echo "$(date): No changes to commit" >> ~/auto_commit.log
fi
```

### 2. Cron Job Configuration

**Schedule:**
```cron
# Daily auto-commit at 12:00 AM (midnight)
0 0 * * * /Users/admin/Documents/Github/Filemaker-Backend/auto_commit.sh

# Daily auto-commit at 12:00 PM (noon)
0 12 * * * /Users/admin/Documents/Github/Filemaker-Backend/auto_commit.sh
```

**Cron Format Explanation:**
- `0 0 * * *` = At 00:00 (midnight) every day
- `0 12 * * *` = At 12:00 (noon) every day
- Format: `minute hour day-of-month month day-of-week`

## Monitoring and Management

### View Current Schedule
```bash
crontab -l
```

### Check Activity Log
```bash
# View recent activity
tail -10 ~/auto_commit.log

# Monitor in real-time
tail -f ~/auto_commit.log
```

### View Recent Auto-Commits
```bash
# Show last 10 auto-commits
git log --oneline --grep="Daily auto-commit" -10

# Show all auto-commits with dates
git log --grep="Daily auto-commit" --pretty=format:"%h %ad %s" --date=short
```

### Test the Script Manually
```bash
cd /Users/admin/Documents/Github/Filemaker-Backend
./auto_commit.sh
```

## Configuration Options

### Enable Auto-Push to Remote
To automatically push commits to GitHub, edit `auto_commit.sh` and uncomment:
```bash
git push origin main
```

**⚠️ Warning:** Only enable this if you want all local changes automatically pushed to the remote repository.

### Modify Schedule
Edit the cron schedule:
```bash
crontab -e
```

**Common Schedule Examples:**
```cron
# Every hour
0 * * * * /path/to/auto_commit.sh

# Every 6 hours (4 times daily)
0 */6 * * * /path/to/auto_commit.sh

# Weekdays only at 9 AM and 5 PM
0 9,17 * * 1-5 /path/to/auto_commit.sh

# Once daily at 2 AM
0 2 * * * /path/to/auto_commit.sh
```

### Selective File Commits
To commit only specific files/directories, modify the `git add` line in `auto_commit.sh`:
```bash
# Only commit specific directories
git add jobs/ API.py config.py README.md

# Exclude certain file types
git add . && git reset -- "*.log" "*.tmp"
```

## Troubleshooting

### Cron Job Not Running
1. **Check cron service status:**
   ```bash
   sudo launchctl list | grep cron
   ```

2. **Check system logs:**
   ```bash
   tail -f /var/log/system.log | grep cron
   ```

3. **Verify script permissions:**
   ```bash
   ls -la auto_commit.sh
   # Should show: -rwxr-xr-x (executable)
   ```

### Script Errors
1. **Check the log file:**
   ```bash
   cat ~/auto_commit.log
   ```

2. **Run script manually to see errors:**
   ```bash
   cd /Users/admin/Documents/Github/Filemaker-Backend
   bash -x ./auto_commit.sh
   ```

3. **Common issues:**
   - **Permission denied**: Run `chmod +x auto_commit.sh`
   - **Path not found**: Verify repository path in script
   - **Git not found**: Ensure git is in PATH or use full path `/usr/bin/git`

### Cron Environment Issues
Cron runs with minimal environment. If git commands fail, use full paths:
```bash
#!/bin/bash
export PATH="/usr/local/bin:/usr/bin:/bin"
cd /Users/admin/Documents/Github/Filemaker-Backend
/usr/bin/git add .
# ... rest of script
```

## Management Commands

### Disable Auto-Commits
```bash
# Remove all cron jobs (⚠️ removes ALL user cron jobs)
crontab -r

# Or edit to comment out specific lines
crontab -e
```

### Backup Current Cron Configuration
```bash
crontab -l > ~/crontab_backup.txt
```

### Restore Cron Configuration
```bash
crontab ~/crontab_backup.txt
```

## Alternative Implementation: macOS launchd

For a more modern macOS approach, use launchd instead of cron:

### 1. Create Launch Agent
File: `~/Library/LaunchAgents/com.autocommit.daily.plist`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.autocommit.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/admin/Documents/Github/Filemaker-Backend/auto_commit.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key>
            <integer>0</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>12</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/admin/Documents/Github/Filemaker-Backend</string>
</dict>
</plist>
```

### 2. Load Launch Agent
```bash
launchctl load ~/Library/LaunchAgents/com.autocommit.daily.plist
```

### 3. Manage Launch Agent
```bash
# Check status
launchctl list | grep autocommit

# Unload
launchctl unload ~/Library/LaunchAgents/com.autocommit.daily.plist
```

## File Locations Summary

- **Auto-commit script**: `/Users/admin/Documents/Github/Filemaker-Backend/auto_commit.sh`
- **Activity log**: `~/auto_commit.log`
- **Cron configuration**: View with `crontab -l`
- **Alternative launchd plist**: `com.autocommit.daily.plist` (in repository)

## Security Considerations

1. **File permissions**: Ensure script is not writable by others
2. **Auto-push**: Be cautious about enabling automatic pushes
3. **Sensitive data**: Review what files are being auto-committed
4. **Log rotation**: Monitor log file size (`~/auto_commit.log`)

## Related Commands

```bash
# Check git status
git status

# View recent commits
git log --oneline -10

# Undo last auto-commit (if needed)
git reset --soft HEAD~1

# View what would be committed
git diff --cached

# Check repository size
du -sh .git/
```

## Support

For issues or modifications:
1. Check the troubleshooting section above
2. Review system logs for cron/launchd errors
3. Test the script manually first
4. Verify file permissions and paths

---

**Last Updated**: July 23, 2025  
**System**: macOS 14.1.0 (darwin 24.1.0)  
**Shell**: /bin/zsh 