#!/usr/bin/env python3
"""Test config loading"""

import sys
sys.path.insert(0, './lib')

from dotenv import load_dotenv
import os

# Load the .env file
load_dotenv()

# Check what we get
print("Environment variables from .env:")
for key in ['OPENAI_API_KEY', 'MUSIC_DIRECTORIES', 'DATABASE_URL', 'LOCATION']:
    value = os.getenv(key, 'NOT_SET')
    print(f"{key} = {repr(value)}")

# Test music directories parsing
music_dirs = os.getenv('MUSIC_DIRECTORIES', '')
print(f"\nRaw music_directories: {repr(music_dirs)}")

# Test the parsing logic from config.py
parsed = [path.strip() for path in music_dirs.split(",") if path.strip()]
print(f"Parsed music_directories: {parsed}")