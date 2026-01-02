#!/usr/bin/env python3
"""
Comprehensive web interface test for Radio Free Luna using Playwright
"""

import asyncio
import json
import requests
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

class RadioFreeLunaWebTester:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
        self.screenshots_dir = Path("test_screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)
        
    async def test_main_interface(self, page):
        """Test the main web interface"""
        print("🌐 Testing main web interface...")
        
        try:
            # Navigate to main page
            await page.goto(self.base_url)
            await page.wait_for_load_state('networkidle', timeout=10000)
            
            # Take screenshot of main page
            timestamp = datetime.now().strftime("%H%M%S")
            await page.screenshot(path=f"{self.screenshots_dir}/01_main_page_{timestamp}.png")
            
            # Get page title and content
            title = await page.title()
            content = await page.content()
            
            print(f"   ✓ Page title: {title}")
            print(f"   ✓ Page loaded successfully")
            
            # Check for Radio Free Luna branding
            if "Radio Free Luna" in content:
                print("   ✓ Radio Free Luna branding found")
            else:
                print("   ❌ Radio Free Luna branding not found")
                
            # Look for key elements
            elements_to_check = [
                'h1', 'h2', 'h3',  # Headers
                'button',          # Buttons
                'form',            # Forms
                'input',           # Input fields
                'div.status',      # Status displays
                'div.controls'     # Control panels
            ]
            
            found_elements = {}
            for selector in elements_to_check:
                try:
                    elements = await page.query_selector_all(selector)
                    found_elements[selector] = len(elements)
                    if elements:
                        print(f"   ✓ Found {len(elements)} {selector} elements")
                except:
                    found_elements[selector] = 0
                    
            return {
                'success': True,
                'title': title,
                'elements': found_elements,
                'has_branding': "Radio Free Luna" in content
            }
            
        except Exception as e:
            print(f"   ❌ Error testing main interface: {e}")
            return {'success': False, 'error': str(e)}

    async def test_interactive_elements(self, page):
        """Test buttons, forms, and interactive elements"""
        print("🎛️ Testing interactive elements...")
        
        try:
            results = {}
            
            # Look for buttons and try to interact
            buttons = await page.query_selector_all('button')
            print(f"   Found {len(buttons)} buttons")
            
            for i, button in enumerate(buttons[:5]):  # Test first 5 buttons
                try:
                    button_text = await button.inner_text()
                    print(f"   Testing button: '{button_text}'")
                    
                    # Take screenshot before clicking
                    await page.screenshot(path=f"{self.screenshots_dir}/02_before_button_{i}.png")
                    
                    # Click button and wait for response
                    await button.click()
                    await page.wait_for_timeout(1000)  # Wait 1 second
                    
                    # Take screenshot after clicking
                    await page.screenshot(path=f"{self.screenshots_dir}/02_after_button_{i}.png")
                    
                    results[f'button_{i}'] = {
                        'text': button_text,
                        'clicked': True
                    }
                    
                except Exception as e:
                    print(f"   ❌ Error with button {i}: {e}")
                    results[f'button_{i}'] = {
                        'error': str(e)
                    }
            
            # Look for forms
            forms = await page.query_selector_all('form')
            print(f"   Found {len(forms)} forms")
            
            # Look for input fields
            inputs = await page.query_selector_all('input, textarea, select')
            print(f"   Found {len(inputs)} input fields")
            
            # Test first form if it exists
            if forms:
                try:
                    form = forms[0]
                    form_inputs = await form.query_selector_all('input, textarea, select')
                    
                    # Fill out form fields
                    for i, input_field in enumerate(form_inputs[:3]):  # Test first 3 inputs
                        input_type = await input_field.get_attribute('type') or 'text'
                        input_name = await input_field.get_attribute('name') or f'field_{i}'
                        
                        if input_type in ['text', 'email', 'search']:
                            await input_field.fill(f'test_value_{i}')
                            print(f"   ✓ Filled {input_name} field")
                        elif input_type == 'textarea':
                            await input_field.fill('Test commentary text')
                            print(f"   ✓ Filled textarea field")
                    
                    # Take screenshot of filled form
                    await page.screenshot(path=f"{self.screenshots_dir}/03_form_filled.png")
                    
                    results['form_test'] = {'success': True, 'inputs_filled': len(form_inputs)}
                    
                except Exception as e:
                    print(f"   ❌ Error testing form: {e}")
                    results['form_test'] = {'error': str(e)}
            
            return results
            
        except Exception as e:
            print(f"   ❌ Error testing interactive elements: {e}")
            return {'error': str(e)}

    async def test_ajax_functionality(self, page):
        """Test AJAX calls and dynamic content updates"""
        print("⚡ Testing AJAX functionality...")
        
        try:
            # Listen for network requests
            requests_made = []
            
            def handle_request(request):
                requests_made.append({
                    'url': request.url,
                    'method': request.method,
                    'headers': dict(request.headers)
                })
            
            page.on('request', handle_request)
            
            # Look for elements that might trigger AJAX calls
            ajax_triggers = await page.query_selector_all(
                'button[data-action], .ajax-button, [onclick*="fetch"], [onclick*="ajax"]'
            )
            
            print(f"   Found {len(ajax_triggers)} potential AJAX triggers")
            
            # Test a few AJAX triggers
            for i, trigger in enumerate(ajax_triggers[:3]):
                try:
                    trigger_text = await trigger.inner_text()
                    print(f"   Testing AJAX trigger: '{trigger_text}'")
                    
                    requests_before = len(requests_made)
                    await trigger.click()
                    await page.wait_for_timeout(2000)  # Wait for AJAX calls
                    requests_after = len(requests_made)
                    
                    if requests_after > requests_before:
                        print(f"   ✓ AJAX call triggered ({requests_after - requests_before} requests)")
                    
                except Exception as e:
                    print(f"   ❌ Error testing AJAX trigger {i}: {e}")
            
            # Take screenshot of final state
            await page.screenshot(path=f"{self.screenshots_dir}/04_ajax_final.png")
            
            return {
                'ajax_triggers_found': len(ajax_triggers),
                'requests_made': len(requests_made),
                'requests': requests_made[-10:]  # Last 10 requests
            }
            
        except Exception as e:
            print(f"   ❌ Error testing AJAX functionality: {e}")
            return {'error': str(e)}

    def test_api_endpoints(self):
        """Test API endpoints directly"""
        print("🔌 Testing API endpoints...")
        
        endpoints = [
            '/health',
            '/status',
            '/api/context',
            '/api/sessions',
            '/api/commentary'
        ]
        
        results = {}
        
        for endpoint in endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                print(f"   Testing {url}")
                
                response = requests.get(url, timeout=5)
                
                results[endpoint] = {
                    'status_code': response.status_code,
                    'success': response.status_code < 400,
                    'content_type': response.headers.get('content-type', ''),
                    'response_size': len(response.content)
                }
                
                if response.headers.get('content-type', '').startswith('application/json'):
                    try:
                        results[endpoint]['json'] = response.json()
                        print(f"   ✓ {endpoint}: {response.status_code} (JSON response)")
                    except:
                        results[endpoint]['json'] = None
                        print(f"   ⚠️ {endpoint}: {response.status_code} (Invalid JSON)")
                else:
                    print(f"   ✓ {endpoint}: {response.status_code} ({response.headers.get('content-type', 'unknown')})")
                    
            except Exception as e:
                print(f"   ❌ {endpoint}: Error - {e}")
                results[endpoint] = {
                    'error': str(e),
                    'success': False
                }
        
        return results

    async def test_static_resources(self, page):
        """Test that CSS, JS, and other static resources load properly"""
        print("📁 Testing static resources...")
        
        try:
            # Go to main page
            await page.goto(self.base_url)
            await page.wait_for_load_state('networkidle')
            
            # Check for CSS files
            css_links = await page.query_selector_all('link[rel="stylesheet"]')
            print(f"   Found {len(css_links)} CSS files")
            
            # Check for JS files
            js_scripts = await page.query_selector_all('script[src]')
            print(f"   Found {len(js_scripts)} JavaScript files")
            
            # Check for images
            images = await page.query_selector_all('img')
            print(f"   Found {len(images)} images")
            
            # Test CSS application by checking computed styles
            body_color = await page.evaluate('getComputedStyle(document.body).color')
            body_bg = await page.evaluate('getComputedStyle(document.body).backgroundColor')
            
            print(f"   ✓ CSS applied - body color: {body_color}, background: {body_bg}")
            
            # Check for JavaScript execution
            js_working = await page.evaluate('typeof window !== "undefined" && typeof document !== "undefined"')
            print(f"   ✓ JavaScript environment: {'Working' if js_working else 'Not working'}")
            
            return {
                'css_files': len(css_links),
                'js_files': len(js_scripts),
                'images': len(images),
                'css_applied': body_color != 'rgb(0, 0, 0)' or body_bg != 'rgba(0, 0, 0, 0)',
                'js_working': js_working
            }
            
        except Exception as e:
            print(f"   ❌ Error testing static resources: {e}")
            return {'error': str(e)}

    async def run_comprehensive_test(self):
        """Run all tests"""
        print("🚀 Starting comprehensive Radio Free Luna web interface test")
        print(f"📍 Base URL: {self.base_url}")
        print(f"🕐 Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)
        
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=False)  # Set to True for headless
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            
            test_results = {}
            
            try:
                # Test 1: Main Interface
                test_results['main_interface'] = await self.test_main_interface(page)
                
                # Test 2: Interactive Elements
                test_results['interactive_elements'] = await self.test_interactive_elements(page)
                
                # Test 3: AJAX Functionality
                test_results['ajax_functionality'] = await self.test_ajax_functionality(page)
                
                # Test 4: Static Resources
                test_results['static_resources'] = await self.test_static_resources(page)
                
            finally:
                await browser.close()
        
        # Test 5: API Endpoints (no browser needed)
        test_results['api_endpoints'] = self.test_api_endpoints()
        
        return test_results

    def generate_report(self, results):
        """Generate a comprehensive test report"""
        print("\n" + "=" * 60)
        print("🎯 RADIO FREE LUNA WEB INTERFACE TEST REPORT")
        print("=" * 60)
        
        total_tests = 0
        passed_tests = 0
        
        for test_name, test_result in results.items():
            print(f"\n📋 {test_name.upper().replace('_', ' ')}")
            print("-" * 40)
            
            if isinstance(test_result, dict):
                if test_result.get('success', True) and 'error' not in test_result:
                    print("   ✅ PASSED")
                    passed_tests += 1
                else:
                    print("   ❌ FAILED")
                    if 'error' in test_result:
                        print(f"   Error: {test_result['error']}")
                
                total_tests += 1
                
                # Print key details
                for key, value in test_result.items():
                    if key not in ['success', 'error'] and not key.startswith('_'):
                        if isinstance(value, (str, int, bool)):
                            print(f"   {key}: {value}")
                        elif isinstance(value, dict) and len(value) < 5:
                            print(f"   {key}: {value}")
                        elif isinstance(value, list) and len(value) < 10:
                            print(f"   {key}: {value}")
        
        print(f"\n🎯 SUMMARY")
        print("-" * 20)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%" if total_tests > 0 else "N/A")
        
        print(f"\n📸 Screenshots saved to: {self.screenshots_dir}")
        print(f"🕐 Test completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'success_rate': (passed_tests/total_tests)*100 if total_tests > 0 else 0,
            'results': results
        }

async def main():
    tester = RadioFreeLunaWebTester()
    results = await tester.run_comprehensive_test()
    report = tester.generate_report(results)
    
    # Save detailed results to JSON
    with open('test_results.json', 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to: test_results.json")

if __name__ == "__main__":
    asyncio.run(main())