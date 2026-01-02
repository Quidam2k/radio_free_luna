#!/usr/bin/env python3
"""
Test server startup with minimal dependencies
"""

import sys
import asyncio
from pathlib import Path

# Add lib and src to path
sys.path.insert(0, './lib')
sys.path.insert(0, './src')

async def test_server():
    print("🌐 Testing Radio Free Luna web server startup...")
    
    try:
        # Test basic imports first
        print("📦 Testing imports...")
        from fastapi import FastAPI
        from src.core.config import settings
        print("✅ Core imports successful")
        
        # Create minimal FastAPI app
        app = FastAPI(title="Radio Free Luna - Test")
        
        @app.get("/")
        async def root():
            return {"message": "Radio Free Luna is running!", "status": "ok"}
        
        @app.get("/health")
        async def health():
            return {"status": "healthy", "system": "Radio Free Luna Test"}
        
        print("✅ FastAPI app created successfully")
        
        # Test if we can start uvicorn
        try:
            import uvicorn
            print("✅ Uvicorn available")
            
            print("🚀 Starting test server on http://localhost:8080")
            print("   - Health check: http://localhost:8080/health")
            print("   - Press Ctrl+C to stop")
            
            # Start server
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=8080,
                log_level="info"
            )
            server = uvicorn.Server(config)
            await server.serve()
            
        except ImportError:
            print("❌ Uvicorn not available")
            
    except Exception as e:
        print(f"❌ Server test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_server())