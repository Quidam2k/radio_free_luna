#!/usr/bin/env python3
"""
Run Radio Free Luna with locally installed packages
"""
import sys
import os

# Add local lib directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

# Now import and run main
if __name__ == "__main__":
    from main import main
    main()