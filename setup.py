#!/usr/bin/env python3
"""
Setup script for Radio Free Luna - AI DJ System
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.database import init_database
from src.core.config import settings
from src.core.file_monitor import FileMonitor

async def init_db():
    """Initialize the database"""
    print("🔧 Initializing database...")
    await init_database(settings.database_url)
    print("✅ Database initialized successfully!")

def scan_music(music_path: str = None):
    """Scan music directories"""
    directories = [music_path] if music_path else settings.music_directories
    
    if not directories:
        print("❌ No music directories specified")
        return
    
    print(f"🔍 Scanning music directories: {directories}")
    
    monitor = FileMonitor(directories, settings.database_url)
    monitor.initial_scan()
    
    print("✅ Music scan completed!")

def main():
    parser = argparse.ArgumentParser(description="Radio Free Luna Setup")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Database initialization
    subparsers.add_parser('init-db', help='Initialize database')
    
    # Music scanning
    scan_parser = subparsers.add_parser('scan-music', help='Scan music directories')
    scan_parser.add_argument('--path', help='Specific path to scan')
    
    args = parser.parse_args()
    
    if args.command == 'init-db':
        asyncio.run(init_db())
    elif args.command == 'scan-music':
        scan_music(args.path)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()