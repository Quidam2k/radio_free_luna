#!/usr/bin/env python3
"""
Comprehensive test runner for Radio Free Luna
Supports different test types and can be integrated with MCP tools
"""

import argparse
import sys
import subprocess
import json
import time
import requests
from pathlib import Path
from typing import List, Dict, Any


class RadioFreeLunaTestRunner:
    """Main test runner for Radio Free Luna system."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.test_results = []
        self.server_process = None
    
    def check_dependencies(self) -> bool:
        """Check if required testing dependencies are available."""
        missing_deps = []
        
        # Check Python dependencies
        try:
            import pytest
        except ImportError:
            missing_deps.append("pytest")
        
        try:
            import requests
        except ImportError:
            missing_deps.append("requests")
        
        # Check Node.js for Puppeteer tests
        try:
            subprocess.run(["node", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Warning: Node.js not available - Puppeteer tests will be skipped")
        
        if missing_deps:
            print(f"Missing dependencies: {', '.join(missing_deps)}")
            print("Install with: pip install " + " ".join(missing_deps))
            return False
        
        return True
    
    def start_test_server(self, timeout: int = 30) -> bool:
        """Start the Radio Free Luna server for testing."""
        print("Starting test server...")
        
        try:
            # Start server in background
            self.server_process = subprocess.Popen(
                [sys.executable, "main.py"],
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait for server to be ready
            for i in range(timeout):
                try:
                    response = requests.get("http://localhost:8080/health", timeout=2)
                    if response.status_code == 200:
                        print("✓ Test server is ready")
                        return True
                except requests.exceptions.ConnectionError:
                    time.sleep(1)
            
            print("✗ Test server failed to start within timeout")
            return False
            
        except Exception as e:
            print(f"✗ Failed to start test server: {e}")
            return False
    
    def stop_test_server(self):
        """Stop the test server."""
        if self.server_process:
            print("Stopping test server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            self.server_process = None
    
    def run_unit_tests(self) -> bool:
        """Run unit tests."""
        print("\n" + "="*50)
        print("RUNNING UNIT TESTS")
        print("="*50)
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_core.py",
            "-v",
            "-m", "not e2e",
            "--tb=short"
        ]
        
        result = subprocess.run(cmd, cwd=self.project_root)
        success = result.returncode == 0
        
        self.test_results.append({
            "type": "unit_tests",
            "success": success,
            "returncode": result.returncode
        })
        
        return success
    
    def run_api_tests(self) -> bool:
        """Run API tests."""
        print("\n" + "="*50)
        print("RUNNING API TESTS")
        print("="*50)
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_api.py",
            "-v",
            "--tb=short"
        ]
        
        result = subprocess.run(cmd, cwd=self.project_root)
        success = result.returncode == 0
        
        self.test_results.append({
            "type": "api_tests",
            "success": success,
            "returncode": result.returncode
        })
        
        return success
    
    def run_integration_tests(self) -> bool:
        """Run integration tests."""
        print("\n" + "="*50)
        print("RUNNING INTEGRATION TESTS")
        print("="*50)
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_integration.py",
            "-v",
            "-m", "not slow",
            "--tb=short"
        ]
        
        result = subprocess.run(cmd, cwd=self.project_root)
        success = result.returncode == 0
        
        self.test_results.append({
            "type": "integration_tests",
            "success": success,
            "returncode": result.returncode
        })
        
        return success
    
    def run_e2e_tests(self) -> bool:
        """Run end-to-end tests with Puppeteer."""
        print("\n" + "="*50)
        print("RUNNING END-TO-END TESTS")
        print("="*50)
        
        # Check if Node.js is available
        try:
            subprocess.run(["node", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Skipping E2E tests - Node.js not available")
            return True
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_e2e_puppeteer.py",
            "-v",
            "-m", "e2e",
            "--tb=short"
        ]
        
        result = subprocess.run(cmd, cwd=self.project_root)
        success = result.returncode == 0
        
        self.test_results.append({
            "type": "e2e_tests",
            "success": success,
            "returncode": result.returncode
        })
        
        return success
    
    def run_manual_api_checks(self) -> bool:
        """Run manual API endpoint checks."""
        print("\n" + "="*50)
        print("RUNNING MANUAL API CHECKS")
        print("="*50)
        
        base_url = "http://localhost:8080"
        checks_passed = 0
        total_checks = 0
        
        # Health check
        total_checks += 1
        try:
            response = requests.get(f"{base_url}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    print("✓ Health check passed")
                    checks_passed += 1
                else:
                    print("✗ Health check returned unhealthy status")
            else:
                print(f"✗ Health check failed with status {response.status_code}")
        except Exception as e:
            print(f"✗ Health check failed: {e}")
        
        # System status
        total_checks += 1
        try:
            response = requests.get(f"{base_url}/status", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("system") == "Radio Free Luna":
                    print("✓ System status check passed")
                    checks_passed += 1
                else:
                    print("✗ System status check failed - incorrect system name")
            else:
                print(f"✗ System status check failed with status {response.status_code}")
        except Exception as e:
            print(f"✗ System status check failed: {e}")
        
        # Context API (allowed to fail if not configured)
        total_checks += 1
        try:
            response = requests.get(f"{base_url}/api/context", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "error" not in data:
                    print("✓ Context API working")
                    checks_passed += 1
                else:
                    print("! Context API returned error (expected if not configured)")
                    checks_passed += 1  # Count as pass since it's expected
            else:
                print(f"! Context API returned status {response.status_code}")
                checks_passed += 1  # Count as pass since it's optional
        except Exception as e:
            print(f"! Context API failed: {e} (expected if not configured)")
            checks_passed += 1  # Count as pass since it's optional
        
        success = checks_passed == total_checks
        
        self.test_results.append({
            "type": "manual_api_checks",
            "success": success,
            "checks_passed": checks_passed,
            "total_checks": total_checks
        })
        
        return success
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report."""
        total_test_types = len(self.test_results)
        passed_test_types = sum(1 for r in self.test_results if r["success"])
        
        report = {
            "summary": {
                "total_test_types": total_test_types,
                "passed_test_types": passed_test_types, 
                "failed_test_types": total_test_types - passed_test_types,
                "overall_success": passed_test_types == total_test_types,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "results": self.test_results,
            "recommendations": []
        }
        
        # Add recommendations based on failures
        for result in self.test_results:
            if not result["success"]:
                if result["type"] == "unit_tests":
                    report["recommendations"].append(
                        "Unit tests failed - check core component implementations"
                    )
                elif result["type"] == "api_tests":
                    report["recommendations"].append(
                        "API tests failed - check endpoint implementations and server configuration"
                    )
                elif result["type"] == "integration_tests":
                    report["recommendations"].append(
                        "Integration tests failed - check component interactions and dependencies"
                    )
                elif result["type"] == "e2e_tests":
                    report["recommendations"].append(
                        "E2E tests failed - check web interface and full system integration"
                    )
        
        if not report["recommendations"]:
            report["recommendations"].append(
                "All tests passed! System is ready for deployment and use."
            )
        
        return report
    
    def run_all_tests(self, include_e2e: bool = True, start_server: bool = True) -> bool:
        """Run complete test suite."""
        print("🎵 Radio Free Luna - Comprehensive Test Suite")
        print("="*60)
        
        if not self.check_dependencies():
            return False
        
        overall_success = True
        
        try:
            # Start server if requested
            if start_server:
                if not self.start_test_server():
                    print("Failed to start test server - some tests may fail")
                    overall_success = False
            
            # Run unit tests (don't require server)
            if not self.run_unit_tests():
                overall_success = False
            
            # Run API tests (require server)
            if start_server:
                if not self.run_api_tests():
                    overall_success = False
                
                # Run manual API checks
                if not self.run_manual_api_checks():
                    overall_success = False
            
            # Run integration tests
            if not self.run_integration_tests():
                overall_success = False
            
            # Run E2E tests if requested
            if include_e2e and start_server:
                if not self.run_e2e_tests():
                    overall_success = False
        
        finally:
            # Stop server
            if start_server:
                self.stop_test_server()
        
        # Generate and display report
        report = self.generate_report()
        
        print("\n" + "="*60)
        print("TEST REPORT")
        print("="*60)
        print(json.dumps(report, indent=2))
        
        if overall_success:
            print("\n🎉 ALL TESTS PASSED! Radio Free Luna is ready for testing!")
        else:
            print("\n❌ Some tests failed. Check the report above for details.")
        
        return overall_success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Radio Free Luna Test Runner")
    parser.add_argument(
        "--no-e2e", 
        action="store_true", 
        help="Skip end-to-end tests"
    )
    parser.add_argument(
        "--no-server", 
        action="store_true",
        help="Don't start test server (for external server testing)"
    )
    parser.add_argument(
        "--unit-only",
        action="store_true",
        help="Run only unit tests"
    )
    parser.add_argument(
        "--api-only",
        action="store_true", 
        help="Run only API tests"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick test suite (unit + API tests)"
    )
    
    args = parser.parse_args()
    
    runner = RadioFreeLunaTestRunner()
    
    if args.unit_only:
        success = runner.run_unit_tests()
    elif args.api_only:
        if not args.no_server and not runner.start_test_server():
            return 1
        try:
            success = runner.run_api_tests() and runner.run_manual_api_checks()
        finally:
            if not args.no_server:
                runner.stop_test_server()
    elif args.quick:
        success = runner.run_all_tests(include_e2e=False, start_server=not args.no_server)
    else:
        success = runner.run_all_tests(include_e2e=not args.no_e2e, start_server=not args.no_server)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())