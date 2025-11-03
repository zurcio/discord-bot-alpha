from core.shared import load_json

PLANETS_FILE = "data/planets.json"

def get_planet_name(planet_id):
    planets = load_json(PLANETS_FILE)
    return planets.get(str(planet_id), {}).get("name", f"Planet {planet_id}")