#!/usr/bin/env python3
"""
Simple web interface test for Radio Free Luna
"""

import requests
import json
from datetime import datetime

def test_web_interface():
    print("🚀 Testing Radio Free Luna Web Interface")
    print(f"🕐 Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    base_url = "http://localhost:8080"
    results = {}
    
    # Test 1: Main web page
    print("🌐 Testing main web interface...")
    try:
        response = requests.get(base_url, timeout=10)
        results['main_page'] = {
            'status_code': response.status_code,
            'success': response.status_code == 200,
            'content_type': response.headers.get('content-type', ''),
            'content_length': len(response.content),
            'has_radio_free_luna': 'Radio Free Luna' in response.text,
            'has_html': '<html' in response.text.lower(),
            'has_css': 'css' in response.text.lower(),
            'has_javascript': 'script' in response.text.lower(),
        }
        
        if response.status_code == 200:
            print(f"   ✅ Main page loaded successfully ({len(response.content)} bytes)")
            if 'Radio Free Luna' in response.text:
                print("   ✅ Radio Free Luna branding found")
            else:
                print("   ⚠️ Radio Free Luna branding not found in content")
        else:
            print(f"   ❌ Main page failed: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Main page error: {e}")
        results['main_page'] = {'error': str(e), 'success': False}
    
    # Test 2: API Endpoints
    print("\n🔌 Testing API endpoints...")
    endpoints = [
        '/health',
        '/status', 
        '/api/context',
        '/api/sessions',
        '/api/commentary'
    ]
    
    api_results = {}
    for endpoint in endpoints:
        try:
            url = f"{base_url}{endpoint}"
            response = requests.get(url, timeout=5)
            
            api_results[endpoint] = {
                'status_code': response.status_code,
                'success': response.status_code < 400,
                'content_type': response.headers.get('content-type', ''),
                'response_size': len(response.content)
            }
            
            if response.headers.get('content-type', '').startswith('application/json'):
                try:
                    json_data = response.json()
                    api_results[endpoint]['json'] = json_data
                    api_results[endpoint]['has_json'] = True
                    print(f"   ✅ {endpoint}: HTTP {response.status_code} (JSON)")
                except:
                    api_results[endpoint]['has_json'] = False
                    print(f"   ⚠️ {endpoint}: HTTP {response.status_code} (Invalid JSON)")
            else:
                print(f"   ✅ {endpoint}: HTTP {response.status_code} ({response.headers.get('content-type', 'unknown')})")
                
        except Exception as e:
            print(f"   ❌ {endpoint}: Error - {e}")
            api_results[endpoint] = {'error': str(e), 'success': False}
    
    results['api_endpoints'] = api_results
    
    # Test 3: Static resources (check if they're referenced)
    print("\n📁 Testing static resources...")
    try:
        main_response = requests.get(base_url, timeout=10)
        content = main_response.text.lower()
        
        static_results = {
            'has_css_links': 'stylesheet' in content or '.css' in content,
            'has_js_scripts': '<script' in content or '.js' in content,
            'has_images': '<img' in content or '.png' in content or '.jpg' in content,
            'has_favicon': 'favicon' in content,
        }
        
        # Try to fetch common static files
        static_files = ['/static/style.css', '/static/app.js', '/favicon.ico', '/static/logo.png']
        for file_path in static_files:
            try:
                response = requests.get(f"{base_url}{file_path}", timeout=3)
                static_results[f'file_{file_path}'] = {
                    'status_code': response.status_code,
                    'exists': response.status_code == 200
                }
                if response.status_code == 200:
                    print(f"   ✅ {file_path}: Found")
                else:
                    print(f"   ⚠️ {file_path}: Not found (HTTP {response.status_code})")
            except:
                static_results[f'file_{file_path}'] = {'exists': False}
                print(f"   ❌ {file_path}: Error accessing")
        
        results['static_resources'] = static_results
        
        # Report on HTML structure
        if static_results['has_css_links']:
            print("   ✅ CSS references found in HTML")
        if static_results['has_js_scripts']:
            print("   ✅ JavaScript references found in HTML")
        if static_results['has_images']:
            print("   ✅ Image references found in HTML")
            
    except Exception as e:
        print(f"   ❌ Static resources test error: {e}")
        results['static_resources'] = {'error': str(e)}
    
    # Test 4: POST endpoints (if any exist)
    print("\n📝 Testing POST functionality...")
    post_endpoints = [
        ('/api/sessions', {'session_name': 'test_session'}),
        ('/api/commentary', {'text': 'test commentary'})
    ]
    
    post_results = {}
    for endpoint, data in post_endpoints:
        try:
            url = f"{base_url}{endpoint}"
            response = requests.post(url, json=data, timeout=5)
            
            post_results[endpoint] = {
                'status_code': response.status_code,
                'success': response.status_code < 400,
                'content_type': response.headers.get('content-type', ''),
                'response_size': len(response.content)
            }
            
            if response.status_code < 400:
                print(f"   ✅ POST {endpoint}: HTTP {response.status_code}")
            else:
                print(f"   ⚠️ POST {endpoint}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ POST {endpoint}: Error - {e}")
            post_results[endpoint] = {'error': str(e), 'success': False}
    
    results['post_endpoints'] = post_results
    
    return results

def generate_report(results):
    """Generate a comprehensive test report"""
    print("\n" + "=" * 60)
    print("🎯 RADIO FREE LUNA WEB INTERFACE TEST REPORT")
    print("=" * 60)
    
    total_tests = 0
    passed_tests = 0
    
    # Summary statistics
    for category, category_results in results.items():
        print(f"\n📋 {category.upper().replace('_', ' ')}")
        print("-" * 40)
        
        if isinstance(category_results, dict):
            if category == 'api_endpoints':
                for endpoint, endpoint_result in category_results.items():
                    total_tests += 1
                    if endpoint_result.get('success', False):
                        passed_tests += 1
                        print(f"   ✅ {endpoint}")
                    else:
                        print(f"   ❌ {endpoint}")
                        
            elif category == 'main_page':
                total_tests += 1
                if category_results.get('success', False):
                    passed_tests += 1
                    print("   ✅ Main page loads successfully")
                    if category_results.get('has_radio_free_luna', False):
                        print("   ✅ Radio Free Luna branding present")
                    if category_results.get('has_html', False):
                        print("   ✅ Valid HTML structure")
                else:
                    print("   ❌ Main page failed to load")
                    
            elif category == 'static_resources':
                if category_results.get('has_css_links', False):
                    print("   ✅ CSS resources referenced")
                if category_results.get('has_js_scripts', False):
                    print("   ✅ JavaScript resources referenced")
                if category_results.get('has_images', False):
                    print("   ✅ Image resources referenced")
                    
            elif category == 'post_endpoints':
                for endpoint, endpoint_result in category_results.items():
                    total_tests += 1
                    if endpoint_result.get('success', False):
                        passed_tests += 1
                        print(f"   ✅ POST {endpoint}")
                    else:
                        print(f"   ⚠️ POST {endpoint}")
    
    print(f"\n🎯 SUMMARY")
    print("-" * 20)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    if total_tests > 0:
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    print(f"\n🕐 Test completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return {
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'success_rate': (passed_tests/total_tests)*100 if total_tests > 0 else 0,
        'results': results
    }

if __name__ == "__main__":
    results = test_web_interface()
    report = generate_report(results)
    
    # Save results to JSON
    with open('web_test_results.json', 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to: web_test_results.json")