#!/usr/bin/env python3
"""
Test startup with minimal configuration
"""
import sys
import os

# Add local lib directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

# Set minimal environment variables
os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY', 'test_key')
os.environ['MUSIC_DIRECTORIES'] = '/tmp/test_music'
os.environ['DATABASE_URL'] = 'sqlite:///test_radio.db'

# Try to import and start
try:
    print("🎵 Testing Radio Free Luna startup...")
    print("=" * 50)
    
    print("1. Testing imports...")
    from src.core.database import init_database
    print("   ✅ Database module loaded")
    
    from src.context.manager import ContextManager
    print("   ✅ Context manager loaded")
    
    from src.web.api import create_app
    print("   ✅ Web API loaded")
    
    print("\n2. Initializing database...")
    init_database()
    print("   ✅ Database initialized")
    
    print("\n3. Creating FastAPI app...")
    app = create_app()
    print("   ✅ API created successfully")
    
    print("\n✅ All components loaded successfully!")
    print("\nTo run the full system:")
    print("  PYTHONPATH=./lib python3 main.py")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()