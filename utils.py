from rapidfuzz import process
from geopy.geocoders import Nominatim
import geopy.distance
import time

# Known cities/areas around which properties are placed
all_known_cities = [
    "Udaipur", "Jaipur", "Jaisalmer", "Jodhpur", "Agra", "Delhi", "Rishikesh",
    "Varanasi", "Goa", "Koksar", "Daman", "Pushkar", "Khajuraho", 
    "Manali", "Bhimtal", "Srinagar", "Ranthambore", "Coimbatore", "Shoja", "Sissu"
]

def fuzzy_match_location(query: str):
    result = process.extractOne(query, all_known_cities, score_cutoff=60)
    if result is None:
        return None
    best_match, score, _ = result
    return best_match

def get_coordinates(location: str):
    geolocator = Nominatim(user_agent="formi_api_v1")
    for _ in range(3):  # Retry logic
        try:
            loc = geolocator.geocode(location, timeout=5)
            if loc:
                return (loc.latitude, loc.longitude)
        except Exception:
            time.sleep(0.5)
    return None

def calculate_distance_km(coord1, coord2):
    return geopy.distance.distance(coord1, coord2).km