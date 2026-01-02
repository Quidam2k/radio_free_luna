#!/usr/bin/env python3
"""
Mock API server for testing Radio Free Luna without dependencies
"""
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

class MockAPIHandler(BaseHTTPRequestHandler):
    """Mock API handler that simulates Radio Free Luna endpoints"""
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        # Route handlers
        if path == '/health':
            response = {
                "status": "healthy",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "components": {
                    "database": "active",
                    "context_manager": "active",
                    "streaming": "mock_mode",
                    "voice": "unavailable"
                }
            }
        
        elif path == '/status':
            response = {
                "system": "Radio Free Luna",
                "version": "1.0.0",
                "uptime": "0:05:32",
                "status": "operational",
                "mode": "testing",
                "components": {
                    "database": {"status": "active", "tracks": 0},
                    "context_manager": {"status": "active", "last_update": "2 minutes ago"},
                    "streaming": {"status": "mock_mode", "active_sessions": 0},
                    "voice_synthesis": {"status": "unavailable", "reason": "TTS-WebUI not configured"}
                },
                "music_library": {
                    "directories": ["/tmp/test_music"],
                    "total_tracks": 0,
                    "last_scan": "Never"
                }
            }
        
        elif path == '/api/context':
            response = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "location": "Denver, CO",
                "time_of_day": "afternoon",
                "weather": {
                    "description": "partly cloudy",
                    "temperature": 72,
                    "mood": "pleasant"
                },
                "season": "summer",
                "themes": ["upbeat", "relaxing", "contemplative"],
                "music_guidance": "Perfect for some mellow afternoon vibes with a touch of energy",
                "dj_personality": "conversational"
            }
        
        elif path.startswith('/api/sessions'):
            query = parse_qs(parsed_path.query)
            theme = query.get('theme', ['contextual'])[0]
            duration = int(query.get('duration_minutes', ['30'])[0])
            
            response = {
                "session_id": "test_session_123",
                "theme": theme,
                "duration_minutes": duration,
                "status": "created",
                "tracks": [
                    {"title": "Mock Track 1", "artist": "Test Artist", "duration": 180},
                    {"title": "Mock Track 2", "artist": "Test Artist", "duration": 210},
                    {"title": "Mock Track 3", "artist": "Test Artist", "duration": 195}
                ],
                "commentary": {
                    "opening": "Welcome to Radio Free Luna. Today we're exploring the theme of " + theme,
                    "transitions": ["Next up, a beautiful piece...", "This reminds me of..."],
                    "closing": "Thanks for listening to this journey through " + theme
                },
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        
        else:
            response = {"error": "Endpoint not found", "path": path}
        
        # Send response
        self.wfile.write(json.dumps(response, indent=2).encode())
    
    def do_POST(self):
        """Handle POST requests"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else ""
        
        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        # Route handlers
        if path.startswith('/api/test-voice'):
            query = parse_qs(parsed_path.query)
            text = query.get('text', ['Hello from Radio Free Luna'])[0]
            
            response = {
                "status": "simulated",
                "message": "Voice synthesis unavailable in test mode",
                "text": text,
                "would_generate": {
                    "voice_model": "alloy",
                    "duration_estimate": len(text) * 0.1
                }
            }
        
        elif path.startswith('/api/commentary'):
            query = parse_qs(parsed_path.query)
            text_type = query.get('text_type', ['contextual'])[0]
            
            commentaries = {
                "contextual": "It's a beautiful afternoon here in Denver. The partly cloudy skies remind me of those days when life presents us with just the right mix of sun and shade...",
                "opening": "Good afternoon, this is Radio Free Luna, where every song tells a story and every moment has its soundtrack. I'm your AI DJ, and today we're going to explore some fascinating musical territories...",
                "closing": "As we wrap up this session, remember that music is the invisible thread that connects us all. Until next time, keep listening, keep wondering, and keep the music alive.",
                "transition": "That was a beautiful piece that really captures the essence of a summer afternoon. Coming up next, we have something that might surprise you..."
            }
            
            response = {
                "type": text_type,
                "text": commentaries.get(text_type, "Welcome to Radio Free Luna..."),
                "context_aware": True,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        
        else:
            response = {"error": "Endpoint not found", "path": path}
        
        # Send response
        self.wfile.write(json.dumps(response, indent=2).encode())
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        """Custom log format"""
        print(f"[{time.strftime('%H:%M:%S')}] {format % args}")

def start_mock_server(port=8080):
    """Start the mock API server"""
    server = HTTPServer(('', port), MockAPIHandler)
    print(f"🎵 Mock Radio Free Luna API Server")
    print(f"📡 Listening on http://localhost:{port}")
    print(f"🌐 Web interface: http://localhost:{port}/src/web/static/index.html")
    print("\nEndpoints available:")
    print("  GET  /health")
    print("  GET  /status")
    print("  GET  /api/context")
    print("  GET  /api/sessions?theme=X&duration_minutes=Y")
    print("  POST /api/test-voice?text=X")
    print("  POST /api/commentary?text_type=X")
    print("\nPress Ctrl+C to stop the server\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down mock server...")
        server.shutdown()

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    start_mock_server(port)