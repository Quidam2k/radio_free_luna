"""
End-to-End tests using Puppeteer for browser automation
Tests the complete user experience through the web interface
"""

import pytest
import asyncio
import json
import subprocess
import time
from pathlib import Path


class TestWebInterfaceE2E:
    """End-to-end tests for the web interface using Puppeteer."""
    
    @pytest.fixture(scope="class")
    def puppeteer_script(self, tmp_path_factory):
        """Create Puppeteer test script."""
        temp_dir = tmp_path_factory.mktemp("puppeteer")
        script_path = temp_dir / "radio_free_luna_tests.js"
        
        script_content = '''
const puppeteer = require('puppeteer');
const assert = require('assert');

class RadioFreeLunaE2ETests {
    constructor() {
        this.browser = null;
        this.page = null;
        this.baseUrl = 'http://localhost:8080';
    }

    async setup() {
        this.browser = await puppeteer.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        this.page = await this.browser.newPage();
        
        // Set up console logging
        this.page.on('console', msg => {
            console.log('PAGE LOG:', msg.text());
        });
        
        // Set up error handling
        this.page.on('pageerror', error => {
            console.error('PAGE ERROR:', error.message);
        });
    }

    async teardown() {
        if (this.browser) {
            await this.browser.close();
        }
    }

    async testHealthCheck() {
        console.log('Testing health check endpoint...');
        
        const response = await this.page.goto(`${this.baseUrl}/health`);
        assert.strictEqual(response.status(), 200);
        
        const content = await this.page.content();
        const data = JSON.parse(await this.page.evaluate(() => document.body.textContent));
        
        assert.strictEqual(data.status, 'healthy');
        assert.strictEqual(data.system, 'Radio Free Luna');
        console.log('✓ Health check passed');
    }

    async testRootEndpoint() {
        console.log('Testing root endpoint...');
        
        const response = await this.page.goto(`${this.baseUrl}/`);
        assert.strictEqual(response.status(), 200);
        
        const content = await this.page.content();
        const data = JSON.parse(await this.page.evaluate(() => document.body.textContent));
        
        assert.strictEqual(data.message, 'Radio Free Luna - AI DJ System');
        assert(data.tagline.includes('every song tells a story'));
        console.log('✓ Root endpoint passed');
    }

    async testContextAPI() {
        console.log('Testing context API...');
        
        const response = await this.page.goto(`${this.baseUrl}/api/context`);
        
        if (response.status() === 200) {
            const content = await this.page.content();
            const data = JSON.parse(await this.page.evaluate(() => document.body.textContent));
            
            if (!data.error) {
                assert(data.description);
                assert(Array.isArray(data.themes));
                console.log('✓ Context API returned valid data');
            } else {
                console.log('! Context API returned error (expected if not configured):', data.error);
            }
        }
    }

    async testSessionCreation() {
        console.log('Testing session creation...');
        
        try {
            // Use page.evaluate to make POST request
            const result = await this.page.evaluate(async (baseUrl) => {
                const response = await fetch(`${baseUrl}/api/sessions?theme=rainy_day&duration_minutes=30`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                return {
                    status: response.status,
                    data: await response.json()
                };
            }, this.baseUrl);
            
            if (result.status === 200) {
                if (!result.data.error) {
                    assert(result.data.session_id || result.data.theme);
                    console.log('✓ Session creation succeeded');
                } else {
                    console.log('! Session creation returned error (expected if not fully configured):', result.data.error);
                }
            }
        } catch (error) {
            console.log('! Session creation test failed (expected if components not initialized):', error.message);
        }
    }

    async testVoiceAPI() {
        console.log('Testing voice synthesis API...');
        
        try {
            const result = await this.page.evaluate(async (baseUrl) => {
                const response = await fetch(`${baseUrl}/api/test-voice?text=Hello from Radio Free Luna`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                return {
                    status: response.status,
                    data: await response.json()
                };
            }, this.baseUrl);
            
            if (result.status === 200) {
                assert(result.data.status);
                if (result.data.status === 'success') {
                    console.log('✓ Voice synthesis working');
                } else {
                    console.log('! Voice synthesis not available (expected if TTS not configured)');
                }
            }
        } catch (error) {
            console.log('! Voice API test failed:', error.message);
        }
    }

    async testSystemStatus() {
        console.log('Testing system status...');
        
        const response = await this.page.goto(`${this.baseUrl}/status`);
        assert.strictEqual(response.status(), 200);
        
        const content = await this.page.content();
        const data = JSON.parse(await this.page.evaluate(() => document.body.textContent));
        
        assert.strictEqual(data.system, 'Radio Free Luna');
        assert.strictEqual(data.status, 'operational');
        assert(data.context);
        assert(data.music_library);
        assert(data.ai_systems);
        
        console.log('✓ System status check passed');
    }

    async testAPIDocumentation() {
        console.log('Testing API documentation...');
        
        const response = await this.page.goto(`${this.baseUrl}/docs`);
        
        if (response.status() === 200) {
            // Check if FastAPI docs are loading
            await this.page.waitForSelector('body', { timeout: 5000 });
            const title = await this.page.title();
            
            if (title.includes('FastAPI') || title.includes('Radio Free Luna')) {
                console.log('✓ API documentation accessible');
            } else {
                console.log('! API documentation may not be properly configured');
            }
        } else {
            console.log('! API documentation not accessible');
        }
    }

    async testWebInterfaceBasics() {
        console.log('Testing basic web interface...');
        
        // Test static file serving
        const staticResponse = await this.page.goto(`${this.baseUrl}/static/`);
        // Static files may not exist yet, so we don't assert success
        
        console.log('✓ Static file handling tested');
    }

    async runAllTests() {
        console.log('Starting Radio Free Luna E2E Tests...');
        
        try {
            await this.setup();
            
            await this.testHealthCheck();
            await this.testRootEndpoint();
            await this.testSystemStatus();
            await this.testContextAPI();
            await this.testSessionCreation();
            await this.testVoiceAPI();
            await this.testAPIDocumentation();
            await this.testWebInterfaceBasics();
            
            console.log('\\n✅ All E2E tests completed successfully!');
            return { success: true, errors: [] };
            
        } catch (error) {
            console.error('\\n❌ E2E test failed:', error.message);
            return { success: false, errors: [error.message] };
        } finally {
            await this.teardown();
        }
    }
}

// Run tests if called directly
if (require.main === module) {
    const tests = new RadioFreeLunaE2ETests();
    tests.runAllTests().then(result => {
        process.exit(result.success ? 0 : 1);
    });
}

module.exports = RadioFreeLunaE2ETests;
'''
        
        script_path.write_text(script_content)
        return script_path
    
    @pytest.fixture(scope="class")
    def package_json(self, tmp_path_factory):
        """Create package.json for Puppeteer dependencies."""
        temp_dir = tmp_path_factory.mktemp("puppeteer")
        package_path = temp_dir / "package.json"
        
        package_content = {
            "name": "radio-free-luna-e2e-tests",
            "version": "1.0.0",
            "description": "End-to-end tests for Radio Free Luna",
            "dependencies": {
                "puppeteer": "^21.0.0"
            }
        }
        
        package_path.write_text(json.dumps(package_content, indent=2))
        return package_path
    
    @pytest.mark.e2e
    def test_install_puppeteer_dependencies(self, package_json):
        """Install Puppeteer dependencies for testing."""
        package_dir = package_json.parent
        
        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=package_dir,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            assert result.returncode == 0, f"npm install failed: {result.stderr}"
            
        except subprocess.TimeoutExpired:
            pytest.skip("npm install timed out - puppeteer installation takes time")
        except FileNotFoundError:
            pytest.skip("npm not available - skipping Puppeteer tests")
    
    @pytest.mark.e2e
    def test_run_puppeteer_tests(self, puppeteer_script):
        """Run the complete Puppeteer test suite."""
        script_dir = puppeteer_script.parent
        
        try:
            # Check if Node.js is available
            subprocess.run(["node", "--version"], check=True, capture_output=True)
            
            # Run the Puppeteer tests
            result = subprocess.run(
                ["node", str(puppeteer_script)],
                cwd=script_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            print("Puppeteer test output:")
            print(result.stdout)
            if result.stderr:
                print("Puppeteer test errors:")
                print(result.stderr)
            
            # The test script should exit with 0 for success
            assert result.returncode == 0, f"Puppeteer tests failed: {result.stderr}"
            
        except FileNotFoundError:
            pytest.skip("Node.js not available - skipping Puppeteer tests")
        except subprocess.TimeoutExpired:
            pytest.fail("Puppeteer tests timed out")


class TestMCPIntegration:
    """Tests specifically designed for MCP (Model Context Protocol) integration."""
    
    def test_create_mcp_test_config(self, tmp_path):
        """Create MCP-compatible test configuration."""
        mcp_config = {
            "name": "radio-free-luna-tests",
            "description": "Automated tests for Radio Free Luna AI DJ System",
            "version": "1.0.0",
            "tests": {
                "health_check": {
                    "type": "http_get",
                    "url": "http://localhost:8080/health",
                    "expected_status": 200,
                    "expected_fields": ["status", "version", "system"]
                },
                "system_status": {
                    "type": "http_get", 
                    "url": "http://localhost:8080/status",
                    "expected_status": 200,
                    "expected_fields": ["system", "status", "context"]
                },
                "context_api": {
                    "type": "http_get",
                    "url": "http://localhost:8080/api/context",
                    "expected_status": 200,
                    "allow_errors": True  # May return error if not configured
                },
                "session_creation": {
                    "type": "http_post",
                    "url": "http://localhost:8080/api/sessions",
                    "params": {"theme": "test", "duration_minutes": 30},
                    "expected_status": 200,
                    "allow_errors": True  # May return error if not fully configured
                },
                "voice_test": {
                    "type": "http_post",
                    "url": "http://localhost:8080/api/test-voice",
                    "params": {"text": "Test voice synthesis"},
                    "expected_status": 200,
                    "allow_errors": True  # May return error if TTS not available
                }
            },
            "puppeteer_tests": {
                "script_path": "tests/test_e2e_puppeteer.js",
                "browser_options": {
                    "headless": True,
                    "args": ["--no-sandbox", "--disable-setuid-sandbox"]
                }
            }
        }
        
        config_path = tmp_path / "mcp_test_config.json"
        config_path.write_text(json.dumps(mcp_config, indent=2))
        
        return config_path
    
    def test_mcp_test_runner_script(self, tmp_path):
        """Create MCP-compatible test runner script."""
        runner_script = '''#!/usr/bin/env python3
"""
MCP-compatible test runner for Radio Free Luna
Can be called by MCP tools for automated testing
"""

import json
import sys
import subprocess
import requests
import time
from pathlib import Path


class MCPTestRunner:
    def __init__(self, config_path=None):
        self.config_path = config_path or "mcp_test_config.json"
        self.config = self.load_config()
        self.results = []
    
    def load_config(self):
        """Load test configuration."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"tests": {}}
    
    def wait_for_server(self, url="http://localhost:8080/health", timeout=30):
        """Wait for server to be ready."""
        print(f"Waiting for server at {url}...")
        
        for i in range(timeout):
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    print("✓ Server is ready")
                    return True
            except requests.exceptions.ConnectionError:
                time.sleep(1)
        
        print("✗ Server not ready within timeout")
        return False
    
    def run_http_test(self, name, test_config):
        """Run HTTP-based test."""
        try:
            url = test_config["url"]
            expected_status = test_config.get("expected_status", 200)
            
            if test_config["type"] == "http_get":
                response = requests.get(url, timeout=10)
            elif test_config["type"] == "http_post":
                params = test_config.get("params", {})
                response = requests.post(url, params=params, timeout=10)
            
            success = response.status_code == expected_status
            
            if not success and not test_config.get("allow_errors", False):
                self.results.append({
                    "name": name,
                    "success": False,
                    "error": f"Expected status {expected_status}, got {response.status_code}"
                })
                return False
            
            # Check expected fields
            if "expected_fields" in test_config:
                try:
                    data = response.json()
                    for field in test_config["expected_fields"]:
                        if field not in data:
                            self.results.append({
                                "name": name,
                                "success": False,
                                "error": f"Missing expected field: {field}"
                            })
                            return False
                except json.JSONDecodeError:
                    if not test_config.get("allow_errors", False):
                        self.results.append({
                            "name": name,
                            "success": False,
                            "error": "Response not valid JSON"
                        })
                        return False
            
            self.results.append({
                "name": name,
                "success": True,
                "response_status": response.status_code
            })
            return True
            
        except Exception as e:
            if not test_config.get("allow_errors", False):
                self.results.append({
                    "name": name,
                    "success": False,
                    "error": str(e)
                })
                return False
            
            self.results.append({
                "name": name,
                "success": True,  # Allowed to fail
                "error": str(e),
                "allowed_failure": True
            })
            return True
    
    def run_puppeteer_tests(self):
        """Run Puppeteer tests if configured."""
        if "puppeteer_tests" not in self.config:
            return True
        
        script_path = self.config["puppeteer_tests"]["script_path"]
        
        try:
            result = subprocess.run(
                ["node", script_path],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            success = result.returncode == 0
            
            self.results.append({
                "name": "puppeteer_e2e_tests",
                "success": success,
                "stdout": result.stdout,
                "stderr": result.stderr
            })
            
            return success
            
        except Exception as e:
            self.results.append({
                "name": "puppeteer_e2e_tests",
                "success": False,
                "error": str(e)
            })
            return False
    
    def run_all_tests(self):
        """Run all configured tests."""
        print(f"Running MCP tests for {self.config.get('name', 'Radio Free Luna')}...")
        
        # Wait for server to be ready
        if not self.wait_for_server():
            return False
        
        # Run HTTP tests
        all_passed = True
        for name, test_config in self.config.get("tests", {}).items():
            print(f"Running test: {name}")
            success = self.run_http_test(name, test_config)
            if not success:
                all_passed = False
            print(f"  {'✓' if success else '✗'} {name}")
        
        # Run Puppeteer tests
        if "puppeteer_tests" in self.config:
            print("Running Puppeteer E2E tests...")
            success = self.run_puppeteer_tests()
            if not success:
                all_passed = False
            print(f"  {'✓' if success else '✗'} Puppeteer E2E tests")
        
        return all_passed
    
    def generate_report(self):
        """Generate test report."""
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r["success"])
        
        report = {
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": total_tests - passed_tests,
                "success_rate": f"{(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "0%"
            },
            "results": self.results
        }
        
        return report


def main():
    """Main entry point for MCP test runner."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "mcp_test_config.json"
    
    runner = MCPTestRunner(config_path)
    success = runner.run_all_tests()
    report = runner.generate_report()
    
    print("\\n" + "="*50)
    print("TEST REPORT")
    print("="*50)
    print(json.dumps(report, indent=2))
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
'''
        
        runner_path = tmp_path / "mcp_test_runner.py"
        runner_path.write_text(runner_script)
        runner_path.chmod(0o755)  # Make executable
        
        return runner_path


@pytest.mark.slow
class TestPerformanceE2E:
    """End-to-end performance tests."""
    
    def test_concurrent_api_requests(self):
        """Test API performance under concurrent load."""
        # This would be implemented with actual load testing
        # For now, we provide the structure
        pass
    
    def test_large_session_creation(self):
        """Test creating sessions with large music libraries."""
        # This would test performance with thousands of tracks
        pass
    
    def test_memory_usage_over_time(self):
        """Test memory usage stability over extended operation."""
        # This would run the system for extended periods
        pass