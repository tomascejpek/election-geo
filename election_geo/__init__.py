"""The boundaries of the Czech units of the elections (regions, districts, senate constituencies, municipalities,
wards, parts of the cities) and of the countries of the world (world/) as GeoJSON static files for Django:
static/election/geo/."""
import os

__version__ = "0.2.0"

# the directory of the files, for reading them on the server (cities.json, the index of the wards and the parts)
GEO_DIR = os.path.join(os.path.dirname(__file__), "static", "election", "geo")
