#!/usr/bin/env python3
"""
Simple database initialization without watchdog dependency
"""

import asyncio
import sys
from pathlib import Path

# Add lib and src to path
sys.path.insert(0, './lib')
sys.path.insert(0, './src')

async def main():
    print("🔧 Initializing Radio Free Luna database...")
    
    try:
        # Import after path setup
        from src.core.database import init_database
        from src.core.config import settings
        
        print(f"📁 Database URL: {settings.database_url}")
        
        # Initialize database
        await init_database(settings.database_url)
        
        print("✅ Database initialized successfully!")
        print(f"📊 Database file: {settings.database_url}")
        
        # Verify database file exists
        if 'sqlite:///data/' in settings.database_url:
            db_file = settings.database_url.replace('sqlite:///', '')
            if Path(db_file).exists():
                print(f"✅ Database file exists: {db_file}")
            else:
                print(f"⚠️  Database file not found: {db_file}")
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())