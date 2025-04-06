# Moustache Escapes Property Locator API

A FastAPI backend service that helps find nearby hotel properties with automatic spelling correction.

## Features
- Finds properties within 50km radius
- Corrects spelling mistakes (e.g., "nioda" → "noida")
- Fast response time (<2 seconds)
- No API keys required
- Built-in rate limiting

## Installation
1. Clone the repository:
```bash
git clone https://github.com/yourusername/moustache-escapes-api.git
cd moustache-escapes-api
```

2. Install dependencies:
```bash
pip install fastapi uvicorn geopy rapidfuzz requests
```

3. Initialize database:
```bash
python property_locator.py
```

## Running the API
```bash
uvicorn property_locator:app --reload
```

API will be available at: `http://127.0.0.1:8000`

## API Endpoints

### POST /find-properties
**Request:**
```json
{
  "query": "nioda"
}
```

**Response:**
```json
{
  "query": "nioda",
  "properties": [
    {
      "property": "Moustache Delhi", 
      "distance_km": 6.27
    }
  ],
  "message": null
}
```

### GET /health
**Response:**
```json
{
  "status": "healthy",
  "version": "1.0"
}
```

## Example Usage

### cURL
```bash
curl -X POST http://localhost:8000/find-properties \
-H "Content-Type: application/json" \
-d '{"query": "bangalre"}'
```

### Python
```python
import requests
response = requests.post(
    "http://localhost:8000/find-properties",
    json={"query": "sissu"}
)
print(response.json())
```

## Technical Details
- **Framework**: FastAPI
- **Database**: SQLite
- **Geocoding**: Nominatim (OpenStreetMap)
- **Spelling Correction**: Google Autocomplete
- **Rate Limiting**: 10 requests/minute per IP

