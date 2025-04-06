from fastapi import FastAPI
from pydantic import BaseModel
from data import property_data
from utils import fuzzy_match_location, get_coordinates, calculate_distance_km

app = FastAPI()

class LocationQuery(BaseModel):
    query: str

@app.post("/nearest-property")
def get_nearest_property(query: LocationQuery):
    user_input = query.query.strip().lower()
    corrected_city = fuzzy_match_location(user_input)

    if not corrected_city:
        return {
            "matched_type": "unrecognized",
            "message": "Could not recognize or correct the input location."
        }

    # STEP 1: Direct match check
    direct_matches = [
        prop for prop in property_data
        if corrected_city.lower() in prop["property"].lower()
    ]
    if direct_matches:
        return {
            "matched_type": "direct_match",
            "matched_city": corrected_city,
            "nearest_properties": direct_matches
        }

    # STEP 2: Get coordinates
    coords = get_coordinates(corrected_city)
    if not coords:
        return {
            "matched_type": "location_not_found",
            "matched_city": corrected_city,
            "message": f"Could not geolocate '{corrected_city}'."
        }

    # STEP 3: Radius check
    nearby_matches = []
    for prop in property_data:
        prop_coords = (prop["lat"], prop["lon"])
        distance = calculate_distance_km(coords, prop_coords)
        if distance <= 50:
            nearby_matches.append({
                "property": prop["property"],
                "distance_km": round(distance, 2)
            })

    if nearby_matches:
        return {
            "matched_type": "proximity_match",
            "matched_city": corrected_city,
            "nearest_properties": nearby_matches
        }

    # ✅ Final fallback – clean user-friendly message
    return {
        "matched_type": "no_match",
        "matched_city": corrected_city,
        "nearest_properties": [],
        "message": "No properties found within 50 km radius."
    }