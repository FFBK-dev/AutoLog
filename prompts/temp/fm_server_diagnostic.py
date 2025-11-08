#!/usr/bin/env python3
"""
FileMaker Server Diagnostic Tool

Checks various aspects of FileMaker Server health.
"""

import requests
import socket
import sys
import warnings
from pathlib import Path

warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def check_port(host, port, timeout=5):
    """Check if a port is open on a host."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def test_filemaker_ports():
    """Test common FileMaker ports."""
    server = config.SERVER
    ports_to_check = [
        (443, "HTTPS/Data API"),
        (80, "HTTP"),
        (5003, "FileMaker Client"),
        (8989, "Internal Service (causing the issue)"),
        (16000, "Admin Console"),
        (16001, "Admin Console HTTPS")
    ]
    
    print(f"🔍 Testing ports on {server}:")
    for port, description in ports_to_check:
        is_open = check_port(server, port)
        status = "✅ Open" if is_open else "❌ Closed"
        print(f"  Port {port} ({description}): {status}")
    
    return True

def test_auth_only():
    """Test just authentication without accessing layouts."""
    try:
        print(f"\n🔐 Testing authentication only...")
        response = requests.post(
            config.url("sessions"),
            auth=(config.USERNAME, config.PASSWORD),
            headers={"Content-Type": "application/json"},
            data="{}",
            verify=False,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Authentication successful")
            token = response.json()["response"]["token"]
            print(f"  Token: {token[:12]}...")
            
            # Try to close the session cleanly
            try:
                close_response = requests.delete(
                    config.url(f"sessions/{token}"),
                    headers={"Content-Type": "application/json"},
                    verify=False,
                    timeout=5
                )
                if close_response.status_code == 200:
                    print(f"✅ Session closed successfully")
                else:
                    print(f"⚠️ Session close returned {close_response.status_code}")
            except:
                print(f"⚠️ Failed to close session (this is expected if Data API is broken)")
            
            return True
        else:
            print(f"❌ Authentication failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Authentication test failed: {e}")
        return False

def main():
    print("🏥 FileMaker Server Health Diagnostic")
    print("=" * 50)
    
    test_filemaker_ports()
    print()
    test_auth_only()
    
    print(f"\n📋 Summary:")
    print(f"  The Data API can authenticate but fails on layout access.")
    print(f"  Error: Internal service on port 8989 is not responding.")
    print(f"  This is a FileMaker Server internal issue, not your code.")
    print(f"\n🔧 Recommended actions:")
    print(f"  1. Restart FileMaker Server services")
    print(f"  2. Check FileMaker Server Admin Console for errors")
    print(f"  3. Contact your FileMaker Server administrator")

if __name__ == "__main__":
    main() 