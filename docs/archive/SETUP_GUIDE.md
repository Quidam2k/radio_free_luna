# Radio Free Luna - Setup Guide

## 🚀 Quick Start Options

You have **3 ways** to run Radio Free Luna:

### Option 1: Docker (Recommended) - 5 minutes
```bash
# Make the script executable
chmod +x run_with_docker.sh

# Run it!
./run_with_docker.sh
```

This handles all dependencies automatically!

### Option 2: Native Linux/macOS - 10 minutes
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY

# Initialize and run
python setup.py init-db
python main.py
```

### Option 3: WSL Workaround - 15 minutes
Since WSL has symlink issues with Windows drives, you can:

1. **Copy project to Linux filesystem**:
   ```bash
   cp -r /mnt/h/Development/radio_free_luna ~/radio_free_luna
   cd ~/radio_free_luna
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Or use Docker Desktop with WSL integration**:
   - Enable WSL integration in Docker Desktop settings
   - Then use Option 1 above

## 📋 Required Configuration

Edit `.env` file with at minimum:
- `OPENAI_API_KEY=sk-your_key_here` (REQUIRED)
- `MUSIC_DIRECTORIES=/path/to/your/music` (can be empty for testing)

## 🎯 What You'll Get

Once running, visit `http://localhost:8080` for:
- AI DJ sessions with contextual music selection
- Smart commentary generation
- Weather and time-aware programming
- Professional audio streaming (when configured)

## ⚠️ Current WSL Limitation

The `/mnt/h` drive doesn't support Python virtual environments due to symlink restrictions. This is why we recommend Docker or copying to the Linux filesystem.

## 🐳 Why Docker is Best

Docker solves all these issues:
- No Python version conflicts
- No dependency issues
- No filesystem problems
- Includes TTS-WebUI automatically
- One command to run everything

Just make sure Docker Desktop is installed and WSL integration is enabled!