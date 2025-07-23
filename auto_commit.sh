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