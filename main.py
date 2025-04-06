from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, constr, validator
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from rapidfuzz import fuzz, process as fuzz_process
import time
import sqlite3
from contextlib import contextmanager
from collections import defaultdict
import logging
from logging.handlers import RotatingFileHandler
from typing import List, Optional, Dict, Tuple
import requests
import re

# --------------------------
# Configuration
# --------------------------
class Config:
    GEOCODER_TIMEOUT = 5
    MAX_DISTANCE_KM = 50
    REQUEST_LIMIT = 10  # Requests per minute per IP
    SPELL_CHECK_URL = "https://www.google.com/complete/search?q={}&client=chrome&hl=en"

# --------------------------
# Models (must be defined before endpoints)
# --------------------------
class PropertyRequest(BaseModel):
    query: constr(min_length=2, max_length=50, strip_whitespace=True)
    
    @validator('query')
    def validate_query(cls, v):
        if any(char.isdigit() for char in v):
            raise ValueError("Query should not contain numbers")
        return v.lower()

class PropertyResponse(BaseModel):
    property: str
    distance_km: float
    is_direct_match: bool = False

class ApiResponse(BaseModel):
    query: str
    properties: List[PropertyResponse]
    message: Optional[str] = None
    class Config:
        exclude_unset = True

# --------------------------
# Database Setup
# --------------------------
DB_PATH = "properties.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()

# Initialize database with sample data
init_db()
with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM properties")
    if cursor.fetchone()[0] == 0:
        sample_properties = [
            ("Moustache Udaipur Luxuria", "udaipur", 24.57799888, 73.68263271),
            ("Moustache Udaipur", "udaipur", 24.58145726, 73.68223671),
            ("Moustache Udaipur Verandah", "udaipur", 24.58350565, 73.68120777),
            ("Moustache Jaipur", "jaipur", 27.29124839, 75.89630143),
            ("Moustache Jaisalmer", "jaisalmer", 27.20578572, 70.85906998),
            ("Moustache Jodhpur", "jodhpur", 26.30365556, 73.03570908),
            ("Moustache Agra", "agra", 27.26156953, 78.07524716),
            ("Moustache Delhi", "delhi", 28.61257139, 77.28423582),
            ("Moustache Rishikesh Luxuria", "rishikesh", 30.13769036, 78.32465767),
            ("Moustache Rishikesh Riverside Resort", "rishikesh", 30.10216117, 78.38458848),
            ("Moustache Hostel Varanasi", "varanasi", 25.2992622, 82.99691388),
            ("Moustache Goa Luxuria", "goa", 15.6135195, 73.75705228),
            ("Moustache Koksar Luxuria", "koksar", 32.4357785, 77.18518717),
            ("Moustache Daman", "daman", 20.41486263, 72.83282455),
            ("Panarpani Retreat", "panarpani", 22.52805539, 78.43116291),
            ("Moustache Pushkar", "pushkar", 26.48080513, 74.5613783),
            ("Moustache Khajuraho", "khajuraho", 24.84602104, 79.93139381),
            ("Moustache Manali", "manali", 32.28818695, 77.17702523),
            ("Moustache Bhimtal Luxuria", "bhimtal", 29.36552248, 79.53481747),
            ("Moustache Srinagar", "srinagar", 34.11547314, 74.88701741),
            ("Moustache Ranthambore Luxuria", "ranthambore", 26.05471373, 76.42953726),
            ("Moustache Coimbatore", "coimbatore", 11.02064612, 76.96293531),
            ("Moustache Shoja", "shoja", 31.56341267, 77.36733331)
        ]
        cursor.executemany(
            "INSERT INTO properties (name, city, latitude, longitude) VALUES (?, ?, ?, ?)",
            sample_properties
        )
        conn.commit()

# --------------------------
# Application Setup
# --------------------------
app = FastAPI(title="Moustache Escapes Property Locator API")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting storage
request_log = defaultdict(list)

# --------------------------
# Logging Setup
# --------------------------
log_handler = RotatingFileHandler(
    'app.log',
    maxBytes=1024*1024,
    backupCount=3
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[log_handler]
)
logger = logging.getLogger(__name__)

# --------------------------
# Services
# --------------------------
def google_spell_suggest(query: str) -> str:
    """Get spelling suggestions from Google's autocomplete (no API key needed)"""
    try:
        response = requests.get(
            Config.SPELL_CHECK_URL.format(requests.utils.quote(query)),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
            timeout=5
        )
        if response.status_code == 200:
            suggestions = response.json()[1]
            if suggestions:
                # Return the most confident suggestion
                return suggestions[0]
    except Exception as e:
        logger.warning(f"Google spell check failed: {str(e)}")
    return query

def suggest_correction(query: str) -> str:
    """
    Hybrid spelling correction:
    1. First check our property cities with fuzzy matching
    2. Fallback to Google's spell check
    """
    # Check against our property cities
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT city FROM properties")
        property_cities = [row[0] for row in cursor.fetchall()]
    
    result = fuzz_process.extractOne(
        query,
        property_cities,
        scorer=fuzz.WRatio,
        score_cutoff=70
    )
    if result and result[1] > 70:
        return result[0]
    
    # Fallback to Google's spell check
    corrected = google_spell_suggest(query)
    if corrected.lower() != query.lower():
        # Verify the correction is a place name
        if any(char.isalpha() for char in corrected):
            return corrected.lower()
    
    return query

def geocode_with_nominatim(location: str) -> Optional[Tuple[float, float]]:
    """Geocode using Nominatim (free, no API key needed)"""
    try:
        geolocator = Nominatim(
            user_agent="moustache-property-locator",
            timeout=Config.GEOCODER_TIMEOUT
        )
        location_data = geolocator.geocode(f"{location}, India")
        if location_data:
            return (location_data.latitude, location_data.longitude)
    except Exception as e:
        logger.warning(f"Geocoding failed for {location}: {str(e)}")
    return None

def get_properties_by_city(city: str) -> List[Dict]:
    """Get properties by city name"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, latitude, longitude FROM properties WHERE city = ?",
            (city,)
        )
        return [
            {"property": row[0], "latitude": row[1], "longitude": row[2]}
            for row in cursor.fetchall()
        ]

def find_nearby_properties(lat: float, lon: float) -> List[Dict]:
    """Find properties within configured radius"""
    nearby = []
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, latitude, longitude FROM properties")
        for row in cursor.fetchall():
            distance = geodesic((lat, lon), (row[1], row[2])).kilometers
            if distance <= Config.MAX_DISTANCE_KM:
                nearby.append({
                    "property": row[0],
                    "distance_km": round(distance, 2)
                })
    return sorted(nearby, key=lambda x: x["distance_km"])

# --------------------------
# Middleware
# --------------------------
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    ip = request.client.host
    current_time = time.time()
    
    request_log[ip] = [t for t in request_log[ip] if current_time - t < 60]
    
    if len(request_log[ip]) >= Config.REQUEST_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests"}
        )
        
    request_log[ip].append(current_time)
    return await call_next(request)

# --------------------------
# API Endpoints
# --------------------------
@app.post("/find-properties", response_model=ApiResponse)
async def find_properties(request: PropertyRequest):
    query = request.query
    
    # Step 1: Correct spelling (kept for internal use but won't appear in response)
    corrected = suggest_correction(query)
    logger.info(f"Original: '{query}', Corrected: '{corrected}'")
    
    # Step 2: Check for direct matches
    direct_properties = get_properties_by_city(corrected)
    if direct_properties:
        return ApiResponse(
            query=query,
            properties=[{
                "property": p["property"],
                "distance_km": 0.0,
                # is_direct_match won't appear in response due to PropertyResponse model
            } for p in direct_properties]
        )
    
    # Step 3: Geocode and proximity search
    coords = geocode_with_nominatim(corrected)
    if not coords and corrected != query:
        coords = geocode_with_nominatim(query)
    
    if not coords:
        return ApiResponse(
            query=query,
            properties=[],
            message="Could not determine location"
        )
    
    properties = find_nearby_properties(*coords)
    
    return ApiResponse(
        query=query,
        properties=[{
            "property": p["property"],
            "distance_km": p["distance_km"]
        } for p in properties],
        message="No properties found" if not properties else None
    )

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)