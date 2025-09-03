# 🔐 Security Configuration Guide

This repository has been sanitized for public distribution. Before using this system, you must configure sensitive information that has been removed.

## ⚠️ Required Configuration

### 1. **Copy and Configure Files**

```bash
# Copy example files and configure with your values
cp config.example.py config.py
cp env.example .env
```

### 2. **Update config.py**

Replace placeholder values in `config.py`:

```python
# FileMaker Server Configuration
SERVER = "YOUR_FILEMAKER_SERVER_IP"
DB_NAME = "Your Database Name"
USERNAME = "your_filemaker_username"
PASSWORD = "your_filemaker_password"

# SMB Configuration  
SMB_SERVER = "YOUR_SMB_SERVER_IP"
SMB_USERNAME = "your_smb_username"
SMB_PASSWORD = "your_smb_password"
```

### 3. **Update .env File**

Configure environment variables in `.env`:

```bash
FILEMAKER_SERVER=your.server.ip
FILEMAKER_USERNAME=your_username
FILEMAKER_PASSWORD=your_password
FM_AUTOMATION_KEY=your_secure_api_key
```

### 4. **Secure API Key**

Change the default API key in `API.py` or set via environment:

```python
# In API.py, line 99
expected_key = os.getenv('FM_AUTOMATION_KEY', 'your_secure_key_here')
```

### 5. **Update Documentation**

Search and replace in documentation files:
- Replace `YOUR_SERVER_IP` with your actual server IP
- Replace `your_api_key` with your actual API key
- Update path references as needed

## 🚫 **Files Removed from Public Version**

The following information has been sanitized:
- Database credentials and connection strings
- SMB/network mount credentials  
- Server IP addresses
- Default API keys
- Personal file paths
- Database names

## 🔒 **Security Best Practices**

1. **Never commit real credentials** to version control
2. **Use environment variables** for sensitive configuration
3. **Rotate API keys** regularly
4. **Limit network access** to FileMaker servers
5. **Use strong passwords** for all accounts

## 📋 **Files Requiring Updates**

After cloning this repository, update these files with your values:

- `config.py` - Database and SMB credentials
- `.env` - Environment variables
- `auto_commit.sh` - Update paths (if using)
- Documentation files - Replace example IPs and keys

## ⚡ **Quick Start Checklist**

- [ ] Copy `config.example.py` to `config.py`
- [ ] Copy `env.example` to `.env`
- [ ] Update database credentials in `config.py`
- [ ] Set secure API key in `.env`
- [ ] Update SMB credentials if using network volumes
- [ ] Test connection with `python3 -c "import config; print(config.get_token()[:10] + '...')"`
- [ ] Update auto_commit.sh path if using auto-commit
- [ ] Review field mappings in job files for your database structure

## 🔗 **Related Documentation**

- See `documentation/DEPLOYMENT_GUIDE.md` for complete deployment instructions
- See `documentation/README.md` for full setup instructions
- See `documentation/USER_GUIDE.md` for usage examples
- See individual job scripts for specific requirements 