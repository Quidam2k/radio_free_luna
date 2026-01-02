#!/usr/bin/env python3
"""
Radio Free Luna - Startup Script
Handles Python path setup and launches the AI DJ system
"""

import os
import sys
from pathlib import Path

# Add lib directory to Python path for pre-installed dependencies
project_root = Path(__file__).parent
lib_path = project_root / "lib"

if lib_path.exists():
    print(f"🎵 Radio Free Luna - Adding lib path: {lib_path}")
    sys.path.insert(0, str(lib_path))
else:
    print("⚠️  Warning: lib directory not found - dependencies may need installation")

# Add project root to Python path
sys.path.insert(0, str(project_root))

# Set environment variable for other processes
os.environ['PYTHONPATH'] = f"{lib_path}:{project_root}:{os.environ.get('PYTHONPATH', '')}"

print("🎵 Radio Free Luna - AI DJ System")
print("=" * 50)
print(f"📁 Project root: {project_root}")
print(f"📚 Using dependencies from: {lib_path}")
print(f"🐍 Python path configured")
print()

# Now import and run the main application
try:
    print("🚀 Starting Radio Free Luna...")
    import main
    # The main.py file handles its own async execution
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("📋 Checking dependencies...")
    
    # Check what's available in lib
    if lib_path.exists():
        available_packages = [d.name for d in lib_path.iterdir() if d.is_dir() and not d.name.endswith('.dist-info')]
        print(f"📦 Available packages: {', '.join(available_packages[:10])}...")
    
    print("\n🔧 Troubleshooting steps:")
    print("1. Ensure you're in the project root directory")
    print("2. Check that lib/ directory contains required packages")
    print("3. Verify .env file is configured")
    sys.exit(1)

except Exception as e:
    print(f"❌ Startup error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)