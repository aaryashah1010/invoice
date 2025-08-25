import os
import csv
import google.generativeai as genai
from typing import Dict, Optional, Tuple
from PIL import Image
import io
from dotenv import load_dotenv
import base64
import json
import re

# Load environment variables
load_dotenv()

# Initialize Gemini API
try:
    GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')
    if not GEMINI_API_KEY:
        raise ValueError("Please set the GOOGLE_API_KEY in the .env file")
    genai.configure(api_key=GEMINI_API_KEY)
    MODEL = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Error initializing Gemini API: {e}")
    MODEL = None

def extract_fields_from_image(image_path: str) -> Tuple[Dict[str, str], str]:
    """Extract invoice fields from an image using Gemini API."""
    if not MODEL:
        return {}, "Error: Gemini API not properly initialized. Check your API key."
    
    try:
        # Load and prepare the image
        with open(image_path, "rb") as img_file:
            img_data = img_file.read()
        
        # Prepare the prompt
        prompt = """Extract all data from this GST invoice and return it in a structured JSON format. 
        
        For invoices with multiple items, create an array of items with all their details.
        
        Return the response in this exact JSON structure:
        {
          "company_info": {
            "company_name": "string",
            "company_address": "string", 
            "city": "string",
            "pincode": "string",
            "gstin": "string",
            "email": "string",
            "phone": "string",
            "website_url": "string",
            "pan_number": "string",
            "state_and_state_code": "string",
            "contact_person_name": "string"
          },
          "invoice_info": {
            "gst_invoice_number": "string",
            "invoice_date": "string",
            "invoice_type": "string",
            "challan_number": "string",
            "challan_date": "string",
            "purchase_order_number": "string",
            "purchase_order_date": "string",
            "place_of_supply": "string",
            "place_of_delivery": "string",
            "reverse_charge_applicable": "string",
            "e_invoice_irn": "string",
            "e_way_bill_number": "string",
            "qr_code": "string"
          },
          "billing_info": {
            "billing_company_name": "string",
            "billing_address": "string",
            "billing_city": "string", 
            "billing_pincode": "string",
            "billing_party_gstin": "string",
            "email_and_phone_of_buyer": "string"
          },
          "shipping_info": {
            "shipping_company_name": "string",
            "shipping_address": "string",
            "shipping_city": "string",
            "shipping_pincode": "string", 
            "shipping_party_gstin": "string"
          },
          "items": [
            {
              "description_of_goods": "string",
              "hsn_code": "string",
              "quantity": "number",
              "uqc": "string",
              "weight": "string",
              "rate": "number",
              "amount": "number",
              "discount_per_item": "number",
              "taxable_value": "number",
              "batch_no": "string",
              "expiry_date": "string",
              "manufacturing_date": "string"
            }
          ],
          "tax_info": {
            "cgst": "number",
            "sgst": "number", 
            "igst": "number",
            "cess_amount": "number"
          },
          "totals": {
            "invoice_amount": "number",
            "total_invoice": "number"
          },
          "transport_info": {
            "transporter_details": "string",
            "vehicle_number": "string",
            "lr_number": "string",
            "transporter_id": "string"
          },
          "bank_info": {
            "bank_details": "string"
          }
        }
        
        IMPORTANT INSTRUCTIONS:
        1. If any field is not present or not applicable, set it to null
        2. For items array, include ALL items found on the invoice with their complete details
        3. Make sure all numerical values are properly formatted as numbers, not strings
        4. Only extract data that is actually present on the invoice
        5. Do not make up or assume any values"""
        
        # Generate content
        response = MODEL.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_data}])
        
        # Process the response
        try:
            # Try to parse the response as JSON
            result = json.loads(response.text)
            return {k: v for k, v in result.items() if v is not None}, ""
        except json.JSONDecodeError:
            # If direct JSON parsing fails, try to extract JSON from the response
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                return {k: v for k, v in result.items() if v is not None}, ""
            else:
                return {}, "Could not parse the response as JSON"
    except Exception as e:
        return {}, f"Error processing image: {str(e)}"

def save_to_csv(data: Dict[str, str], csv_file: str) -> bool:
    """Save extracted data to CSV file."""
    try:
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data.keys())
            writer.writeheader()
            writer.writerow(data)
        return True
    except Exception as e:
        print(f"Error saving to CSV: {e}")
        return False
