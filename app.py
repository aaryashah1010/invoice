from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import tempfile
import csv
import io
import json
from invoice_extractor import extract_fields_from_image

app = Flask(__name__)
CORS(app)

# Configure upload settings
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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
    app.run(debug=True, host='0.0.0.0', port=5001)
