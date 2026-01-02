#!/usr/bin/env python3
"""
Radio Free Luna - Quick Start Script
Automated setup and testing for minimal friction
"""

import os
import sys
import subprocess
import time
import requests
from pathlib import Path
import json


def print_banner():
    """Print the Radio Free Luna banner"""
    print("🎵" * 20)
    print("🎵  RADIO FREE LUNA - AI DJ SYSTEM  🎵")
    print("🎵  Quick Start & Testing Script     🎵")
    print("🎵" * 20)
    print()


def check_python_version():
    """Check Python version compatibility"""
    if sys.version_info < (3, 9):
        print("❌ Python 3.9+ required. Current version:", sys.version)
        return False
    print("✅ Python version:", sys.version.split()[0])
    return True


def check_dependencies():
    """Check if key dependencies are available"""
    print("\n📦 Checking dependencies...")
    
    missing = []
    try:
        import fastapi
        print("✅ FastAPI available")
    except ImportError:
        missing.append("fastapi")
    
    try:
        import openai
        print("✅ OpenAI available")
    except ImportError:
        missing.append("openai")
    
    try:
        import aiohttp
        print("✅ aiohttp available")
    except ImportError:
        missing.append("aiohttp")
    
    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        return False
    
    return True


def setup_environment():
    """Setup .env file if it doesn't exist"""
    print("\n⚙️  Setting up environment...")
    
    env_path = Path(".env")
    env_example_path = Path(".env.example")
    
    if not env_path.exists():
        if env_example_path.exists():
            # Copy .env.example to .env
            with open(env_example_path, 'r') as src:
                content = src.read()
            
            with open(env_path, 'w') as dst:
                dst.write(content)
            
            print("✅ Created .env from .env.example")
            print("⚠️  Please edit .env with your API keys before continuing")
            print("   Minimum required: OPENAI_API_KEY and MUSIC_DIRECTORIES")
            return False
        else:
            print("❌ No .env.example found")
            return False
    else:
        print("✅ .env file exists")
        return True


def check_configuration():
    """Check if basic configuration is present"""
    print("\n🔍 Checking configuration...")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        openai_key = os.getenv('OPENAI_API_KEY')
        music_dirs = os.getenv('MUSIC_DIRECTORIES')
        
        if not openai_key or openai_key.startswith('your_') or openai_key.startswith('sk-your'):
            print("⚠️  OPENAI_API_KEY not configured")
            return False
        
        if not music_dirs or music_dirs.startswith('/path/to'):
            print("⚠️  MUSIC_DIRECTORIES not configured (optional for testing)")
        
        print("✅ Basic configuration looks good")
        return True
        
    except Exception as e:
        print(f"❌ Configuration check failed: {e}")
        return False


def run_quick_tests():
    """Run quick automated tests"""
    print("\n🧪 Running quick tests...")
    
    try:
        result = subprocess.run(
            [sys.executable, "run_tests.py", "--unit-only"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print("✅ Unit tests passed")
            return True
        else:
            print("❌ Some unit tests failed")
            print("Error output:", result.stderr[-500:] if result.stderr else "No error output")
            return False
            
    except subprocess.TimeoutExpired:
        print("⚠️  Tests timed out")
        return False
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        return False


def start_server():
    """Start the Radio Free Luna server"""
    print("\n🚀 Starting Radio Free Luna server...")
    
    try:
        # Start server in background
        process = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        print("⏳ Waiting for server to start...")
        for i in range(30):  # Wait up to 30 seconds
            try:
                response = requests.get("http://localhost:8080/health", timeout=2)
                if response.status_code == 200:
                    print("✅ Server started successfully!")
                    return process
            except requests.exceptions.ConnectionError:
                time.sleep(1)
                print("." if i % 5 != 4 else f" {i+1}s")
                continue
        
        print("❌ Server failed to start within 30 seconds")
        process.terminate()
        return None
        
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return None


def test_api_endpoints():
    """Test key API endpoints"""
    print("\n🔧 Testing API endpoints...")
    
    endpoints = [
        ("Health Check", "http://localhost:8080/health"),
        ("System Status", "http://localhost:8080/status"),
        ("API Info", "http://localhost:8080/api"),
        ("Context", "http://localhost:8080/api/context"),
    ]
    
    results = []
    for name, url in endpoints:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"✅ {name}: OK")
                results.append(True)
            else:
                print(f"⚠️  {name}: HTTP {response.status_code}")
                results.append(False)
        except Exception as e:
            print(f"❌ {name}: {e}")
            results.append(False)
    
    return all(results)


def test_web_interface():
    """Test web interface accessibility"""
    print("\n🌐 Testing web interface...")
    
    try:
        response = requests.get("http://localhost:8080/", timeout=10)
        if response.status_code == 200:
            content = response.text
            if "Radio Free Luna" in content:
                print("✅ Web interface accessible")
                return True
            else:
                print("⚠️  Web interface returned unexpected content")
                return False
        else:
            print(f"❌ Web interface returned HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Web interface test failed: {e}")
        return False


def create_test_session():
    """Test session creation"""
    print("\n🎭 Testing session creation...")
    
    try:
        response = requests.post(
            "http://localhost:8080/api/sessions",
            params={"theme": "upbeat", "duration_minutes": 15},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if "error" not in data:
                print("✅ Session creation successful")
                print(f"   Session ID: {data.get('session_id', 'Unknown')}")
                return True
            else:
                print(f"⚠️  Session creation returned error: {data['error']}")
                return False
        else:
            print(f"❌ Session creation failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Session creation test failed: {e}")
        return False


def main():
    """Main quick start function"""
    print_banner()
    
    # Pre-flight checks
    if not check_python_version():
        return 1
    
    if not check_dependencies():
        print("\n💡 Run: pip install -r requirements.txt")
        return 1
    
    if not setup_environment():
        print("\n💡 Please configure .env file and run again")
        return 1
    
    if not check_configuration():
        print("\n💡 Please check your .env configuration")
        return 1
    
    # Run tests
    if not run_quick_tests():
        print("\n💡 Some tests failed, but continuing...")
    
    # Start server
    server_process = start_server()
    if not server_process:
        return 1
    
    try:
        # Test functionality
        tests_passed = 0
        total_tests = 4
        
        if test_api_endpoints():
            tests_passed += 1
        
        if test_web_interface():
            tests_passed += 1
        
        if create_test_session():
            tests_passed += 1
        
        # Final assessment
        print("\n" + "="*50)
        print("🎯 QUICK START RESULTS")
        print("="*50)
        
        if tests_passed >= 3:
            print("🎉 SUCCESS! Radio Free Luna is ready!")
            print("\n✅ What's working:")
            print("   • Server is running")
            print("   • Web interface accessible")
            print("   • API endpoints responding")
            print("   • Basic functionality operational")
            
            print("\n🌐 Access the system:")
            print("   • Web Interface: http://localhost:8080")
            print("   • API Documentation: http://localhost:8080/docs")
            print("   • Health Check: http://localhost:8080/health")
            
            print("\n📖 Next steps:")
            print("   1. Explore the web interface")
            print("   2. Configure music directories in .env")
            print("   3. Set up TTS-WebUI for voice features")
            print("   4. Review HANDOFF.md for detailed testing")
            
            print("\n⏹️  Press Ctrl+C to stop the server")
            
            # Keep server running
            try:
                server_process.wait()
            except KeyboardInterrupt:
                print("\n🛑 Stopping server...")
                server_process.terminate()
                print("✅ Server stopped")
            
            return 0
            
        else:
            print(f"⚠️  PARTIAL SUCCESS ({tests_passed}/{total_tests} tests passed)")
            print("System is running but some features may not work properly.")
            print("Check the logs and HANDOFF.md for troubleshooting.")
            return 1
            
    finally:
        if server_process:
            server_process.terminate()


if __name__ == "__main__":
    sys.exit(main())