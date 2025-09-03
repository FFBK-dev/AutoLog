#!/bin/bash

# Repository Sanitization Script
# This script removes sensitive information from git history and prepares repo for public release

echo "🔐 Starting repository sanitization for public release..."

# Create backup branch
echo "📋 Creating backup branch..."
git checkout -b pre-sanitization-backup

# Return to main branch
git checkout main

# 1. Add sensitive files to .gitignore if not already there
echo "📝 Updating .gitignore..."
cat >> .gitignore << 'EOF'

# Sensitive configuration files
config.py
.env
*.env
.env.*

# Temporary and test files
/temp/*
!/temp/.gitkeep

# Logs and sensitive data
/logs/*
!/logs/.gitkeep

# macOS and system files
.DS_Store
*.log

EOF

# 2. Remove config.py from tracking and replace with example
echo "🔄 Replacing config.py with sanitized version..."
git rm --cached config.py 2>/dev/null || true
mv config.py config.py.backup 2>/dev/null || true
mv config.example.py config.py 2>/dev/null || true

# 3. Create .gitkeep files for empty directories
touch temp/.gitkeep
touch logs/.gitkeep

# 4. Use git filter-branch to remove sensitive data from history
echo "🧹 Cleaning git history (this may take a while)..."

# Remove config.py from all commits
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch config.py' \
  --prune-empty --tag-name-filter cat -- --all

# Remove any .env files from history
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env' \
  --prune-empty --tag-name-filter cat -- --all

# 5. Clean up filter-branch refs
echo "🗑️  Cleaning up references..."
rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 6. Stage sanitized files
echo "📦 Staging sanitized files..."
git add .
git add .gitignore
git add config.example.py
git add env.example
git add SECURITY_README.md

# 7. Commit changes
echo "💾 Committing sanitized repository..."
git commit -m "🔐 Sanitize repository for public release

- Replace config.py with sanitized config.example.py
- Add env.example for environment configuration
- Add SECURITY_README.md with setup instructions
- Update .gitignore to exclude sensitive files
- Remove sensitive data from git history

Users must copy example files and configure with their values:
- cp config.example.py config.py
- cp env.example .env"

echo ""
echo "✅ Repository sanitization complete!"
echo ""
echo "📋 Next steps:"
echo "1. Review the changes with: git log --oneline -10"
echo "2. Test that sensitive data is gone: git log --all --grep='july1776'"
echo "3. Force push to remote: git push --force-with-lease origin main"
echo "4. Consider creating a new repository for public release"
echo ""
echo "⚠️  IMPORTANT:"
echo "- The backup branch 'pre-sanitization-backup' contains original data"
echo "- Delete this branch after confirming sanitization: git branch -D pre-sanitization-backup"
echo "- Force push will rewrite history - coordinate with team if shared repository"
echo ""
echo "🔍 Verify no sensitive data remains:"
echo "git log --all --full-history -- config.py"
echo "git log --all -S 'july1776' --source --all"
echo "git log --all -S '10.0.222.144' --source --all" 