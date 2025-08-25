# Invoice Data Extractor

A professional web application for extracting data from invoices using AI-powered OCR with Google's Gemini API.

## Features

- **Modern React UI**: Clean, professional interface with drag-and-drop file upload
- **AI-Powered OCR**: Uses Google Gemini API for accurate data extraction
- **Real-time Preview**: See your invoice before processing
- **CSV Export**: Download extracted data as CSV files
- **Responsive Design**: Works on desktop and mobile devices

## Setup Instructions

### Prerequisites

- Python 3.8+
- Node.js 16+
- Google API Key for Gemini

### Backend Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the root directory:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

3. Start the Flask backend:
```bash
python app.py
```

The backend will run on `http://localhost:5000`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

The frontend will run on `http://localhost:5173`

## Usage

1. Open your browser and go to `http://localhost:5173`
2. Upload an invoice image by dragging and dropping or clicking "Choose File"
3. Click "Extract Data" to process the invoice
4. Review the extracted data in the results panel
5. Download the data as CSV if needed

## Supported File Formats

- JPG/JPEG
- PNG
- GIF
- BMP
- TIFF

## API Endpoints

- `POST /api/extract` - Extract data from uploaded invoice
- `POST /api/download-csv` - Generate CSV from extracted data
- `GET /api/health` - Health check

## Project Structure

```
invoice/
├── app.py                 # Flask backend API
├── invoice_extractor.py   # Original OCR script
├── requirements.txt       # Python dependencies
├── .env                  # Environment variables
├── frontend/             # React frontend
│   ├── src/
│   │   ├── App.jsx      # Main React component
│   │   └── ...
│   ├── package.json     # Node dependencies
│   └── vite.config.js   # Vite configuration
└── README.md
```

## Notes

- The original `invoice_extractor.py` script remains unchanged and functional
- The Flask API serves as a bridge between the React frontend and the Python OCR functionality
- All extracted data is temporarily stored and can be downloaded as CSV
- File uploads are limited to 16MB for performance
