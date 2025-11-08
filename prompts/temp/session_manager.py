#!/usr/bin/env python3
"""
FileMaker Session Management Utility

This script helps diagnose and manage FileMaker Data API sessions.
Use this when experiencing session-related issues.
"""

import sys
import warnings
from pathlib import Path

# Suppress urllib3 LibreSSL warning
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL 1.1.1+.*', category=Warning)

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

def main():
    print("🔧 FileMaker Session Management Utility")
    print("=" * 50)
    
    while True:
        print("\nOptions:")
        print("1. Test API Connection")
        print("2. Show Session Info")
        print("3. Force Cleanup All Sessions")
        print("4. Create New Session")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == "1":
            print("\n🧪 Testing API Connection...")
            config.test_api_connection()
            
        elif choice == "2":
            print("\n📊 Session Information:")
            info = config.get_session_info()
            print(f"  Total active sessions: {info['total_sessions']}")
            
            if info['sessions']:
                for session in info['sessions']:
                    status = "✅ Valid" if session['is_valid'] else "❌ Expired"
                    print(f"  - {session['key']}: {session['token_preview']} "
                          f"(Age: {session['age_minutes']}min) {status}")
            else:
                print("  No active sessions")
                
        elif choice == "3":
            print("\n🧹 Force Cleanup...")
            config.force_session_cleanup()
            
        elif choice == "4":
            print("\n🔄 Creating New Session...")
            try:
                token = config.get_cached_token()
                print(f"✅ New session created: {token[:8]}...")
            except Exception as e:
                print(f"❌ Failed to create session: {e}")
                
        elif choice == "5":
            print("\n👋 Goodbye!")
            break
            
        else:
            print("\n❌ Invalid choice. Please try again.")

if __name__ == "__main__":
    main() 