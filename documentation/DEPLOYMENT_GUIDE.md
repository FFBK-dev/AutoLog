# 🚀 Production Deployment Guide

This guide helps you deploy the FileMaker Backend system for a new production team.

## 📋 **Prerequisites**

- **FileMaker Server** with Data API enabled
- **SMB/Network volumes** accessible from the deployment server
- **Python 3.8+** with pip
- **Network access** between your server and FileMaker Server

## ⚙️ **Initial Setup**

### 1. **Clone and Configure**

```bash
# Clone the repository
git clone <your-repo-url>
cd Filemaker-Backend

# Copy template files
cp config.example.py config.py
cp env.example .env

# Install dependencies
pip install -r requirements.txt
```

### 2. **Configure Database Connection**

Edit `config.py`:

```python
# FileMaker Server Configuration
SERVER   = "YOUR_FILEMAKER_SERVER_IP"
DB_NAME  = "Your Database Name"
USERNAME = "your_filemaker_username"
PASSWORD = "your_filemaker_password"

# SMB Volume Configuration
SMB_SERVER = "YOUR_SMB_SERVER_IP"
SMB_USERNAME = "your_smb_username"
SMB_PASSWORD = "your_smb_password"
VOLUMES = {
    "stills": "Your Stills Volume Name",
    "footage": "Your Footage Volume Name"
}
```

### 3. **Configure Environment Variables**

Edit `.env`:

```bash
# FileMaker Server Configuration
FILEMAKER_SERVER=your.filemaker.server.ip
FILEMAKER_USERNAME=your_filemaker_username
FILEMAKER_PASSWORD=your_filemaker_password

# API Authentication
FM_AUTOMATION_KEY=your_secure_api_key_here

# Development Settings
AUTOLOG_DEBUG=false
```

### 4. **Update Auto-Commit Script** (Optional)

If using auto-commit, edit `auto_commit.sh`:

```bash
# Update the path to your project
cd /path/to/your/project
```

## 🔧 **System Configuration**

### **FileMaker Database Requirements**

Your FileMaker database should have these layouts and field structures:

#### Required Layouts:
- `Stills` - For still image processing
- `Footage` - For video processing  
- `Settings` - For system globals

#### Required Fields (adapt names in FIELD_MAPPING):
- `AutoLog_Status` - Workflow status tracking
- `AI_DevConsole` - Error/debug messages visible to users
- Container fields for thumbnails and processed content

### **Volume Mounting**

Ensure SMB volumes are accessible:

```bash
# Test manual mount
open "smb://username:password@server/volume_name"
```

## 🚀 **Starting the System**

### **Development Mode**

```bash
# Start the API server
python API.py

# Test with a simple request
curl -X GET "http://localhost:8081/status" -H "x-api-key: your_secure_api_key_here"
```

### **Production Mode**

```bash
# Use a process manager like PM2 or systemd
pm2 start API.py --name "filemaker-backend"

# Or with systemd (create service file)
sudo systemctl start filemaker-backend
sudo systemctl enable filemaker-backend
```

## 📊 **Testing the Installation**

### **1. Connection Test**

```python
# Test FileMaker connection
python3 -c "import config; print('Token:', config.get_token()[:10] + '...')"
```

### **2. Volume Test**

```python
# Test volume mounting
python3 -c "import config; print('Stills mount:', config.mount_volume('stills'))"
```

### **3. API Test**

```bash
# Test API endpoints
curl -X GET "http://localhost:8081/status" -H "x-api-key: your_api_key"

# Test job submission
curl -X POST "http://localhost:8081/run/stills_autolog_01_get_file_info" \
  -H "x-api-key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"item_id": "TEST001"}'
```

## 🔒 **Security Checklist**

- [ ] **Unique API key** set in `.env`
- [ ] **Strong passwords** for all accounts
- [ ] **Network access** limited to required IPs
- [ ] **Regular key rotation** scheduled
- [ ] **Backup procedures** in place
- [ ] **Log monitoring** configured

## 📝 **Customization for Your Environment**

### **Field Mapping**

Update field mappings in individual job files:

```python
FIELD_MAPPING = {
    "item_id": "YOUR_ITEM_ID_FIELD",
    "status": "YOUR_STATUS_FIELD", 
    "dev_console": "YOUR_CONSOLE_FIELD",
    # Add your specific field mappings
}
```

### **Workflow Steps**

Customize workflow steps in main workflow files (`*_00_run_all.py`):

```python
WORKFLOW_STEPS = [
    {
        "step_num": 1,
        "status_before": "0 - Pending File Info",
        "status_after": "1 - File Info Complete", 
        "script": "your_custom_script.py"
    }
    # Add your workflow steps
]
```

## 🆘 **Troubleshooting**

### **Common Issues**

**Connection Errors:**
```bash
# Check FileMaker server connectivity
curl -k "https://YOUR_SERVER/fmi/data/vLatest/productInfo"
```

**Volume Mount Issues:**
```bash
# Check SMB connectivity
smbclient -L YOUR_SMB_SERVER -U YOUR_USERNAME
```

**Permission Errors:**
```bash
# Check file permissions
ls -la config.py
chmod 600 config.py  # Restrict access to config file
```

### **Log Analysis**

Monitor logs for issues:

```bash
# View API logs
tail -f logs/api_operations.log

# View job-specific logs  
tail -f logs/autolog_monitor.log
```

## 📞 **Support**

For deployment assistance:

1. **Check existing documentation** in `/documentation/`
2. **Review error logs** in `/logs/`
3. **Test individual components** before full deployment
4. **Verify network connectivity** between all systems

## 🔄 **Maintenance**

### **Regular Tasks**
- Monitor log file sizes
- Rotate API keys periodically
- Update system dependencies
- Backup configuration files
- Monitor disk space usage

### **Updates**
```bash
# Pull latest changes
git pull origin main

# Restart services
pm2 restart filemaker-backend
```

---

**⚠️ Important:** Never commit real credentials to version control. Always use the template files and environment variables for sensitive configuration. 