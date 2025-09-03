#!/bin/bash

# Manual Sanitization Script (Current Files Only)
# This script sanitizes current files without modifying git history

echo "🔐 Starting manual sanitization of current files..."

# Create backup
echo "📋 Creating backup of sensitive files..."
cp config.py config.py.backup
cp auto_commit.sh auto_commit.sh.backup

# Function to sanitize a file
sanitize_file() {
    local file="$1"
    echo "🧹 Sanitizing $file..."
    
    # Replace sensitive IP addresses
    sed -i.bak 's/10\.0\.222\.144/YOUR_FILEMAKER_SERVER_IP/g' "$file"
    sed -i.bak 's/10\.0\.222\.138/YOUR_SMB_SERVER_IP/g' "$file"
    
    # Replace passwords
    sed -i.bak 's/july1776/your_password/g' "$file"
    
    # Replace API keys
    sed -i.bak 's/supersecret/your_api_key/g' "$file"
    
    # Replace database name
    sed -i.bak 's/Emancipation to Exodus/Your Database Name/g' "$file"
    
    # Replace usernames
    sed -i.bak 's/"Background"/"your_username"/g' "$file"
    sed -i.bak 's/"admin"/"your_smb_username"/g' "$file"
    
    # Replace personal paths
    sed -i.bak 's|/Users/admin/Documents/Github/Filemaker-Backend|/path/to/your/project|g' "$file"
    
    # Remove .bak files
    rm -f "$file.bak"
}

# Sanitize configuration files
if [ -f "config.py" ]; then
    sanitize_file "config.py"
    mv config.py config.example.py
    echo "  -> config.py renamed to config.example.py"
fi

# Sanitize auto commit script
if [ -f "auto_commit.sh" ]; then
    sanitize_file "auto_commit.sh"
fi

# Sanitize documentation files
echo "🧹 Sanitizing documentation files..."
find documentation/ -name "*.md" -type f | while read file; do
    sanitize_file "$file"
done

# Find and sanitize other files with sensitive data
echo "🔍 Finding other files with sensitive data..."
grep -l "10\.0\.222\.144\|july1776\|supersecret" jobs/*.py 2>/dev/null | while read file; do
    sanitize_file "$file"
done

# Update .gitignore
echo "📝 Updating .gitignore..."
cat >> .gitignore << 'EOF'

# Sensitive configuration files
config.py
.env
*.env
.env.*

# Backup files
*.backup

EOF

echo ""
echo "✅ Manual sanitization complete!"
echo ""
echo "📋 Files modified:"
echo "- config.py -> config.example.py (sanitized)"
echo "- auto_commit.sh (sanitized)"
echo "- documentation/*.md (sanitized)"
echo "- jobs/*.py files with sensitive data (sanitized)"
echo "- .gitignore (updated)"
echo ""
echo "📋 Next steps:"
echo "1. Review changes: git diff"
echo "2. Create your config.py: cp config.example.py config.py"
echo "3. Configure with your actual values"
echo "4. Commit changes: git add . && git commit -m 'Sanitize for public release'"
echo ""
echo "⚠️  Note: This only sanitizes current files, not git history"
echo "For complete history cleanup, use the filter-branch script instead" 