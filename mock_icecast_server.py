#!/usr/bin/env python3
"""
Mock Icecast2 server for testing streaming functionality
"""

import socket
import threading
import time
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import base64

class MockIcecastHandler(BaseHTTPRequestHandler):
    """Mock Icecast2 HTTP handler"""
    
    def do_PUT(self):
        """Handle PUT requests from source clients"""
        print(f"📡 Received PUT request to {self.path}")
        
        # Check for source authentication
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Basic '):
            try:
                encoded = auth_header[6:]
                decoded = base64.b64decode(encoded).decode('utf-8')
                username, password = decoded.split(':', 1)
                print(f"   🔐 Auth: {username} (password: {'*' * len(password)})")
            except:
                print("   ❌ Invalid authentication")
        
        # Print all headers
        print("   📋 Headers received:")
        for name, value in self.headers.items():
            print(f"      {name}: {value}")
        
        # Send success response for source connection
        self.send_response(200)
        self.send_header('Server', 'MockIcecast/2.4.4')
        self.send_header('Connection', 'close')
        self.end_headers()
        
        print("   ✅ Source connection accepted")
        
        # Read audio data (simulate streaming)
        bytes_received = 0
        start_time = time.time()
        
        try:
            while True:
                chunk = self.rfile.read(4096)
                if not chunk:
                    break
                bytes_received += len(chunk)
                
                # Print progress every 50KB
                if bytes_received % 51200 == 0:
                    elapsed = time.time() - start_time
                    rate = bytes_received / elapsed if elapsed > 0 else 0
                    print(f"   🌊 Streaming: {bytes_received:,} bytes ({rate/1024:.1f} KB/s)")
                
        except Exception as e:
            print(f"   ⚠️  Streaming ended: {e}")
        
        total_time = time.time() - start_time
        avg_rate = bytes_received / total_time if total_time > 0 else 0
        print(f"   🎵 Stream complete: {bytes_received:,} bytes in {total_time:.1f}s ({avg_rate/1024:.1f} KB/s avg)")
    
    def do_GET(self):
        """Handle GET requests from clients"""
        print(f"🎧 Client request: GET {self.path}")
        
        if self.path == '/admin/stats.xml':
            # Mock admin stats for connection testing
            stats_xml = '''<?xml version="1.0"?>
<icestats>
    <server_id>MockIcecast 2.4.4</server_id>
    <server_start>Wed, 23 Jul 2025 20:00:00 +0000</server_start>
    <server_start_iso8601>2025-07-23T20:00:00+0000</server_start_iso8601>
</icestats>'''
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/xml')
            self.send_header('Content-Length', str(len(stats_xml)))
            self.end_headers()
            self.wfile.write(stats_xml.encode())
            print("   📊 Admin stats served")
            
        elif self.path.startswith('/ai_dj_stream') or self.path.startswith('/test'):
            # Mock client stream request
            self.send_response(200)
            self.send_header('Content-Type', 'audio/mpeg')
            self.send_header('Ice-Name', 'Radio Free Luna - AI DJ Stream')
            self.send_header('Ice-Description', 'Mock streaming test')
            self.end_headers()
            
            print("   🎧 Client stream started (mock)")
            
            # Send mock audio data for 10 seconds
            for i in range(10):
                mock_audio = b'\x00' * 1024  # Silent audio data
                try:
                    self.wfile.write(mock_audio)
                    time.sleep(1)
                    print(f"      📡 Sent {len(mock_audio)} bytes to client")
                except:
                    print("      🔌 Client disconnected")
                    break
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default HTTP logging"""
        pass

def start_mock_icecast(host='localhost', port=8000):
    """Start mock Icecast2 server"""
    print(f"🎵 Starting Mock Icecast2 Server")
    print(f"   📡 Host: {host}")
    print(f"   🔌 Port: {port}")
    print(f"   🌐 Admin: http://{host}:{port}/admin/stats.xml")
    print(f"   🎧 Stream: http://{host}:{port}/ai_dj_stream")
    print("-" * 50)
    
    try:
        server = HTTPServer((host, port), MockIcecastHandler)
        
        print(f"✅ Mock Icecast2 server running on {host}:{port}")
        print("   Press Ctrl+C to stop")
        print()
        
        server.serve_forever()
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping mock Icecast2 server...")
        server.shutdown()
        print("✅ Mock server stopped")
    
    except Exception as e:
        print(f"❌ Failed to start mock server: {e}")

if __name__ == "__main__":
    # Parse command line arguments
    host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    
    start_mock_icecast(host, port)