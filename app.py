from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import tempfile
import csv
import io
import json
import requests
import threading
from datetime import datetime
from invoice_extractor_server import extract_fields_from_image

app = Flask(__name__)
CORS(app, origins=["*"])

# Configure upload settings
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Webhook configuration storage
WEBHOOK_CONFIG_FILE = 'webhook_config.json'
WEBHOOK_LOGS = []
RECEIVED_WEBHOOK_DATA = []  # Store actual received JSON data

def load_webhook_config():
    """Load webhook configuration from file."""
    try:
        if os.path.exists(WEBHOOK_CONFIG_FILE):
            with open(WEBHOOK_CONFIG_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading webhook config: {e}")
    return {'webhooks': []}

def save_webhook_config(config):
    """Save webhook configuration to file."""
    try:
        with open(WEBHOOK_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving webhook config: {e}")
        return False

def send_webhook(url, data, headers=None):
    """Send data to webhook URL asynchronously."""
    def _send():
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'url': url,
            'status': 'pending',
            'response_code': None,
            'error': None
        }
        
        try:
            webhook_headers = {'Content-Type': 'application/json'}
            if headers:
                webhook_headers.update(headers)
            
            response = requests.post(
                url, 
                json=data, 
                headers=webhook_headers,
                timeout=30
            )
            
            log_entry['status'] = 'success' if response.status_code < 400 else 'failed'
            log_entry['response_code'] = response.status_code
            log_entry['response_text'] = response.text[:500]  # Limit response text
            
        except Exception as e:
            log_entry['status'] = 'error'
            log_entry['error'] = str(e)
        
        # Store log (keep only last 100 entries)
        WEBHOOK_LOGS.append(log_entry)
        if len(WEBHOOK_LOGS) > 100:
            WEBHOOK_LOGS.pop(0)
    
    # Send webhook in background thread
    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()

def flatten_invoice_data(data):
    """Flatten nested invoice data for CSV export."""
    flattened = {}
    
    def flatten_dict(d, prefix=''):
        for key, value in d.items():
            if isinstance(value, dict):
                flatten_dict(value, f"{prefix}{key}_")
            elif isinstance(value, list):
                if key == 'items':
                    # Handle items array specially
                    for i, item in enumerate(value):
                        for item_key, item_value in item.items():
                            flattened[f"item_{i+1}_{item_key}"] = item_value
                else:
                    flattened[f"{prefix}{key}"] = str(value)
            else:
                flattened[f"{prefix}{key}"] = value
    
    flatten_dict(data)
    return flattened

@app.route('/api/extract', methods=['POST'])
def extract_invoice_data():
    """Extract data from uploaded invoice image."""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
        file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_extension not in allowed_extensions:
            return jsonify({'error': 'Invalid file type. Please upload an image file.'}), 400
        
        # Save uploaded file temporarily
        temp_filename = f"temp_invoice_{os.urandom(8).hex()}.{file_extension}"
        temp_path = os.path.join(UPLOAD_FOLDER, temp_filename)
        file.save(temp_path)
        
        try:
            # Extract data using your existing function
            extracted_data, error_message = extract_fields_from_image(temp_path)
            
            if error_message:
                return jsonify({'error': error_message}), 500
            
            if not extracted_data:
                return jsonify({'error': 'No data could be extracted from the invoice'}), 400
            
            # Clean up temporary file
            os.remove(temp_path)
            
            # Store current invoice data (replace any previous data)
            current_entry = {
                'timestamp': datetime.now().isoformat(),
                'data': extracted_data
            }
            RECEIVED_WEBHOOK_DATA[:] = [current_entry]
            
            # Send data to configured webhooks
            config = load_webhook_config()
            for webhook in config.get('webhooks', []):
                if webhook.get('enabled', True):
                    send_webhook(
                        webhook['url'], 
                        extracted_data, 
                        webhook.get('headers', {})
                    )
            
            return jsonify(extracted_data)
            
        except Exception as e:
            # Clean up temporary file in case of error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e
            
    except Exception as e:
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/api/download-csv', methods=['POST'])
def download_csv():
    """Generate and download CSV file from extracted data."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Create CSV content in memory
        output = io.StringIO()
        
        # Flatten the structured data for CSV
        flattened_data = flatten_invoice_data(data)
        
        # Write CSV headers and data
        fieldnames = list(flattened_data.keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(flattened_data)
        
        # Convert to bytes
        csv_content = output.getvalue()
        output.close()
        
        # Create a temporary file for download
        temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv')
        temp_file.write(csv_content)
        temp_file.close()
        
        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name='extracted_invoice_data.csv',
            mimetype='text/csv'
        )
        
    except Exception as e:
        return jsonify({'error': f'CSV generation failed: {str(e)}'}), 500

@app.route('/api/download-json', methods=['POST'])
def download_json():
    """Generate and download JSON file from extracted data."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Create a temporary file for download
        temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json')
        json.dump(data, temp_file, indent=2, ensure_ascii=False)
        temp_file.close()
        
        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name='extracted_invoice_data.json',
            mimetype='application/json'
        )
        
    except Exception as e:
        return jsonify({'error': f'JSON generation failed: {str(e)}'}), 500

@app.route('/api/webhooks', methods=['GET'])
def get_webhooks():
    """Get all configured webhooks."""
    config = load_webhook_config()
    return jsonify(config)

@app.route('/api/webhooks', methods=['POST'])
def add_webhook():
    """Add a new webhook configuration."""
    try:
        data = request.get_json()
        
        if not data or not data.get('url'):
            return jsonify({'error': 'Webhook URL is required'}), 400
        
        config = load_webhook_config()
        
        webhook = {
            'id': len(config['webhooks']) + 1,
            'name': data.get('name', f"Webhook {len(config['webhooks']) + 1}"),
            'url': data['url'],
            'enabled': data.get('enabled', True),
            'headers': data.get('headers', {}),
            'created_at': datetime.now().isoformat()
        }
        
        config['webhooks'].append(webhook)
        
        if save_webhook_config(config):
            return jsonify(webhook), 201
        else:
            return jsonify({'error': 'Failed to save webhook configuration'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Failed to add webhook: {str(e)}'}), 500

@app.route('/api/webhooks/<int:webhook_id>', methods=['DELETE'])
def delete_webhook(webhook_id):
    """Delete a webhook configuration."""
    try:
        config = load_webhook_config()
        config['webhooks'] = [w for w in config['webhooks'] if w.get('id') != webhook_id]
        
        if save_webhook_config(config):
            return jsonify({'message': 'Webhook deleted successfully'})
        else:
            return jsonify({'error': 'Failed to save webhook configuration'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Failed to delete webhook: {str(e)}'}), 500

@app.route('/api/webhooks/<int:webhook_id>/toggle', methods=['POST'])
def toggle_webhook(webhook_id):
    """Toggle webhook enabled/disabled status."""
    try:
        config = load_webhook_config()
        
        for webhook in config['webhooks']:
            if webhook.get('id') == webhook_id:
                webhook['enabled'] = not webhook.get('enabled', True)
                break
        
        if save_webhook_config(config):
            return jsonify({'message': 'Webhook status updated'})
        else:
            return jsonify({'error': 'Failed to save webhook configuration'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Failed to toggle webhook: {str(e)}'}), 500

@app.route('/api/webhook-logs', methods=['GET'])
def get_webhook_logs():
    """Get webhook delivery logs."""
    return jsonify({'logs': WEBHOOK_LOGS})

@app.route('/api/demo-webhook', methods=['POST'])
def demo_webhook():
    """Demo webhook endpoint to receive invoice data."""
    try:
        data = request.get_json()
        
        # Log the received data
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'demo_webhook_received',
            'data_keys': list(data.keys()) if data else [],
            'invoice_number': data.get('invoice_info', {}).get('gst_invoice_number', 'N/A') if data else 'N/A',
            'company_name': data.get('company_info', {}).get('company_name', 'N/A') if data else 'N/A',
            'total_amount': data.get('totals', {}).get('total_invoice', 'N/A') if data else 'N/A'
        }
        
        # Store in webhook logs for demonstration
        WEBHOOK_LOGS.append(log_entry)
        if len(WEBHOOK_LOGS) > 100:
            WEBHOOK_LOGS.pop(0)
        
        # Only store data if this is a demo webhook call (not from main extraction)
        # Check if data is already stored from main extraction process
        if not RECEIVED_WEBHOOK_DATA or RECEIVED_WEBHOOK_DATA[0]['data'] != data:
            received_entry = {
                'timestamp': log_entry['timestamp'],
                'data': data
            }
            # Replace entire list with single current entry
            RECEIVED_WEBHOOK_DATA[:] = [received_entry]
        
        print(f"Demo webhook received data: {log_entry}")
        
        return jsonify({
            'status': 'success',
            'message': 'Invoice data received successfully',
            'received_at': log_entry['timestamp'],
            'data_summary': {
                'invoice_number': log_entry['invoice_number'],
                'company_name': log_entry['company_name'],
                'total_amount': log_entry['total_amount'],
                'fields_count': len(log_entry['data_keys'])
            }
        }), 200
        
    except Exception as e:
        error_log = {
            'timestamp': datetime.now().isoformat(),
            'type': 'demo_webhook_error',
            'error': str(e)
        }
        WEBHOOK_LOGS.append(error_log)
        
        return jsonify({
            'status': 'error',
            'message': f'Failed to process webhook data: {str(e)}'
        }), 500

@app.route('/api/get-data', methods=['GET'])
def get_demo_webhook_data():
    """Get all JSON data received by the demo webhook."""
    return jsonify({
        'count': len(RECEIVED_WEBHOOK_DATA),
        'data': RECEIVED_WEBHOOK_DATA
    })

@app.route('/api/clear-webhook-data', methods=['POST'])
def clear_webhook_data():
    """Clear all stored webhook data."""
    RECEIVED_WEBHOOK_DATA.clear()
    WEBHOOK_LOGS.clear()
    return jsonify({
        'status': 'success',
        'message': 'All webhook data cleared',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/test-webhook-system', methods=['GET'])
def test_webhook_system():
    """Test all webhook-related endpoints - combines test_webhook.py functionality."""
    results = {
        'timestamp': datetime.now().isoformat(),
        'tests': []
    }
    
    try:
        # 1. Check server health
        results['tests'].append({
            'name': 'Server Health Check',
            'status': 'success',
            'message': 'Server is running'
        })
        
        # 2. Check/Add demo webhook configuration (prevent duplicates)
        webhook_url = request.url_root.rstrip('/') + '/api/demo-webhook'
        config = load_webhook_config()
        
        # Check if demo webhook already exists
        existing_webhook = None
        for webhook in config['webhooks']:
            if webhook['url'] == webhook_url and 'Auto Test' in webhook['name']:
                existing_webhook = webhook
                break
        
        if existing_webhook:
            results['tests'].append({
                'name': 'Check Webhook Configuration',
                'status': 'success',
                'message': f'Demo webhook already exists: {existing_webhook["name"]} (ID: {existing_webhook["id"]})',
                'webhook_id': existing_webhook['id']
            })
        else:
            # Add new webhook only if it doesn't exist
            webhook_data = {
                "name": "Auto Test Webhook",
                "url": webhook_url,
                "enabled": True,
                "headers": {
                    "Authorization": "Bearer test-token",
                    "X-Source": "auto-test"
                }
            }
            
            webhook = {
                'id': len(config['webhooks']) + 1,
                'name': webhook_data['name'],
                'url': webhook_data['url'],
                'enabled': webhook_data.get('enabled', True),
                'headers': webhook_data.get('headers', {}),
                'created_at': datetime.now().isoformat()
            }
            config['webhooks'].append(webhook)
            
            if save_webhook_config(config):
                results['tests'].append({
                    'name': 'Add Webhook Configuration',
                    'status': 'success',
                    'message': f'New webhook added: {webhook["name"]} (ID: {webhook["id"]})',
                    'webhook_id': webhook['id']
                })
            else:
                results['tests'].append({
                    'name': 'Add Webhook Configuration',
                    'status': 'failed',
                    'message': 'Failed to save webhook configuration'
                })
        
        # 3. Get all webhooks
        config = load_webhook_config()
        results['tests'].append({
            'name': 'Get Webhooks',
            'status': 'success',
            'message': f'Found {len(config["webhooks"])} webhook(s)',
            'webhooks': [{'name': w['name'], 'url': w['url'], 'enabled': w.get('enabled', True)} for w in config['webhooks']]
        })
        
        # 4. Test demo webhook directly
        sample_invoice_data = {
            "company_info": {
                "company_name": "Test Company Ltd",
                "gstin": "27ABCDE1234F1Z5"
            },
            "invoice_info": {
                "gst_invoice_number": "AUTO-TEST-001",
                "invoice_date": "2024-08-28"
            },
            "totals": {
                "total_invoice": 15000.00
            },
            "items": [
                {
                    "description_of_goods": "Test Product",
                    "quantity": 2,
                    "rate": 7500.00,
                    "amount": 15000.00
                }
            ]
        }
        
        # Simulate webhook call by calling the demo webhook function directly
        try:
            # Store current request context
            with app.test_request_context(json=sample_invoice_data, content_type='application/json'):
                demo_response = demo_webhook()
                if demo_response[1] == 200:  # Check status code
                    response_data = demo_response[0].get_json()
                    results['tests'].append({
                        'name': 'Demo Webhook Test',
                        'status': 'success',
                        'message': 'Demo webhook received data successfully',
                        'data_summary': response_data.get('data_summary', {})
                    })
                else:
                    results['tests'].append({
                        'name': 'Demo Webhook Test',
                        'status': 'failed',
                        'message': 'Demo webhook test failed'
                    })
        except Exception as e:
            results['tests'].append({
                'name': 'Demo Webhook Test',
                'status': 'error',
                'message': f'Demo webhook test error: {str(e)}'
            })
        
        # 5. Check webhook logs
        results['tests'].append({
            'name': 'Webhook Logs Check',
            'status': 'success',
            'message': f'Found {len(WEBHOOK_LOGS)} log entries',
            'recent_logs': WEBHOOK_LOGS[-3:] if len(WEBHOOK_LOGS) > 0 else []
        })
        
        # Summary
        success_count = sum(1 for test in results['tests'] if test['status'] == 'success')
        total_count = len(results['tests'])
        
        results['summary'] = {
            'total_tests': total_count,
            'successful': success_count,
            'failed': total_count - success_count,
            'overall_status': 'success' if success_count == total_count else 'partial_success'
        }
        
        results['usage_info'] = {
            'demo_webhook_url': request.url_root.rstrip('/') + '/api/demo-webhook',
            'webhook_management': request.url_root.rstrip('/') + '/api/webhooks',
            'webhook_logs': request.url_root.rstrip('/') + '/api/webhook-logs',
            'received_data': request.url_root.rstrip('/') + '/api/demo-webhook-data'
        }
        
        return jsonify(results)
        
    except Exception as e:
        results['tests'].append({
            'name': 'System Test',
            'status': 'error',
            'message': f'Test system error: {str(e)}'
        })
        results['summary'] = {
            'total_tests': len(results['tests']),
            'successful': 0,
            'failed': len(results['tests']),
            'overall_status': 'failed'
        }
        return jsonify(results), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'message': 'Invoice extractor API is running'})

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 16MB.'}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    print("Starting Invoice Extractor API...")
    print("Make sure your .env file contains the GOOGLE_API_KEY")
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)
