import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
print("DEBUG: Loaded API key =", api_key)

if not api_key:
    print("Error: API key not found in .env file")
    exit(1)

try:
    # Configure the API
    genai.configure(api_key=api_key)

    # Use the correct model (multimodal supported)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # Test the API
    response = model.generate_content("Say 'API is working' if you can read this.")
    print("API Response:")
    print(response.text)

except Exception as e:
    print("❌ Error testing API:", e)
