# Radio Free Luna - Quick Start Guide
**Ready to Test!** - Updated July 23, 2025

## 🎉 System Status: READY FOR TESTING

Radio Free Luna is now **configured and running** with a working web interface, API endpoints, and sample audio files ready for testing.

## 🚀 **Instant Launch** (30 seconds)

```bash
# Start Radio Free Luna (from project directory)
python3 launch_radio_free_luna.py
```

Then open your web browser to: **http://localhost:8080**

That's it! The system is now running and accessible from any computer on your network.

## 📍 **Current System State**

### ✅ **What Works Right Now**:
- **Web Interface**: Full HTML/CSS/JS interface at http://localhost:8080  
- **REST API**: All endpoints functional with mock data
- **Database**: SQLite database initialized with schema
- **Sample Audio**: 22 audio files (103MB) ready for testing
- **Configuration**: Environment configured for basic testing
- **Network Access**: Server binds to 0.0.0.0:8080 (accessible from other computers)

### ⚠️ **Current Mode**: Testing with Mock Components
- **File monitoring**: Mock (no real audio file scanning yet)
- **AI integration**: Mock (no real OpenAI calls)
- **Audio streaming**: Mock (no real audio playback yet)
- **Voice synthesis**: Mock (no TTS integration yet)

This is intentional - we're at the **waypoint** where you can test the interface and API structure before adding real dependencies.

## 🌐 **Testing from Another Computer**

### **From your local network**:
1. Find your server's IP address: `ip addr show`
2. Open browser to: `http://[YOUR-IP]:8080`
3. The web interface should load normally

### **Testing URLs**:
- **Main Interface**: http://localhost:8080/
- **Health Check**: http://localhost:8080/health  
- **System Status**: http://localhost:8080/status
- **API Documentation**: http://localhost:8080/docs
- **Context API**: http://localhost:8080/api/context

## 🧪 **Testing the System**

### **Web Interface Testing**:
1. Open http://localhost:8080
2. Check status indicators (should show "testing mode")  
3. Try "Create AI DJ Session" with theme "upbeat"
4. Test "Generate Commentary" buttons
5. Check "System Status" section

### **API Testing** (from command line):
```bash
# Health check
curl http://localhost:8080/health

# Create a test session  
curl -X POST "http://localhost:8080/api/sessions?theme=relaxing&duration_minutes=30"

# Get context information
curl http://localhost:8080/api/context

# Generate test commentary
curl -X POST "http://localhost:8080/api/commentary?text_type=contextual"
```

## 📁 **Files Created for You**

### **Launcher Script**:
- `launch_radio_free_luna.py` - **Production launcher with mock components**

### **Database**:
- `data/radio_free_luna.db` - **SQLite database initialized and ready**

### **Configuration**:
- `.env` - **Environment variables configured for testing**

### **Testing Tools**:
- `init_db_simple.py` - Database initialization
- `test_server.py` - Basic server testing
- `comprehensive_test_runner.py` - Full system validation

### **Backup Files**:
- `src/core/config.py.backup` - Original complex Pydantic config (restored later)

## 🔧 **Configuration Details**

### **Current .env Settings**:
```bash
OPENAI_API_KEY=sk-test-key-for-basic-validation  # Mock key for testing
MUSIC_DIRECTORIES=/mnt/h/Development/radio_free_luna/sample_audio
DATABASE_URL=sqlite:///data/radio_free_luna.db
LOCATION="Denver, CO"
DJ_PERSONALITY=conversational
KNOWLEDGE_DEPTH=moderate
DEBUG=true
LOG_LEVEL=INFO
```

### **Network Configuration**:
- **Host**: 0.0.0.0 (accessible from any network interface)
- **Port**: 8080  
- **Protocol**: HTTP

## 📊 **System Architecture (Current)**

```
Radio Free Luna (Testing Mode)
├── Web Interface (✅ Working)
│   ├── HTML/CSS/JS (33KB)
│   ├── Real-time API calls
│   └── Status monitoring
├── REST API (✅ Working)  
│   ├── Health endpoints
│   ├── Session management
│   ├── Context awareness
│   └── Commentary generation
├── Database (✅ Working)
│   ├── SQLite initialized
│   ├── Schema ready
│   └── 6,087 lines of ORM code
├── Mock Components (✅ Working)
│   ├── File monitoring simulation
│   ├── AI response simulation  
│   ├── Audio processing simulation
│   └── Voice synthesis simulation
└── Sample Audio (✅ Ready)
    └── 22 audio files available
```

## 🎯 **Next Steps After Testing**

Once you've confirmed the web interface and API work properly:

### **Phase 1: Add Real Dependencies** (Optional)
```bash
# Install missing audio processing
pip install watchdog mutagen librosa

# Add real OpenAI API key to .env
OPENAI_API_KEY=sk-your-real-openai-key-here
```

### **Phase 2: Enable Audio Streaming** (Optional)  
```bash
# Install Icecast2 for real audio streaming
sudo apt install icecast2
# OR use Docker: docker-compose up -d
```

### **Phase 3: Add Voice Synthesis** (Optional)
```bash
# Install TTS-WebUI for voice features
# Instructions in HANDOFF.md
```

## 🚨 **Important Notes**

### **Firewall/Network**:
- Server binds to `0.0.0.0:8080` for network access
- Make sure port 8080 is open if testing from remote computers
- Use `ip addr show` to find your server's IP address

### **Mock Mode Benefits**:
- **Fast startup** - no external dependencies
- **Reliable testing** - no API failures or timeouts  
- **Full functionality** - all endpoints work with test data
- **Development safe** - no real API costs or quota usage

### **File Structure** (Important for troubleshooting):
```
radio_free_luna/
├── launch_radio_free_luna.py  ← **Main launcher**
├── .env                       ← **Configuration**  
├── data/radio_free_luna.db    ← **Database**
├── lib/                       ← **Dependencies (pre-installed)**
├── src/                       ← **Source code**
├── sample_audio/              ← **Test audio files**
└── logs/ai_dj.log            ← **Runtime logs**
```

## 🎉 **Success Criteria**

You should be able to:
- ✅ Access web interface from browser
- ✅ See system status and components  
- ✅ Create test DJ sessions
- ✅ Generate mock commentary
- ✅ Access from another computer on your network
- ✅ See all API endpoints responding correctly

## 🆘 **Troubleshooting**

### **Server won't start**:
```bash
# Check if port is in use
lsof -i :8080

# Check logs
tail -f ai_dj.log
```

### **Can't access from other computer**:
```bash
# Check server IP
ip addr show

# Test local access first  
curl http://localhost:8080/health

# Check firewall
sudo ufw status
```

### **Web interface doesn't load**:
- Check if `src/web/static/` directory exists
- Verify static files are being served: `curl http://localhost:8080/static/css/main.css`

---

**🎵 Radio Free Luna is ready for testing!**  
**Web Interface**: http://localhost:8080  
**Status**: Fully operational in testing mode  
**Network**: Accessible from other computers on your network