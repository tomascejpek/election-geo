"""The countries of the world for the maps of the memberships of the states in the international organisations, as
GeoJSON files in election_geo/static/election/geo/world/. Run once when Natural Earth comes out with new boundaries.

The source is Natural Earth, Admin 0 – Countries, 1:50m (ne_50m_admin_0_countries.zip, public domain,
https://www.naturalearthdata.com/downloads/50m-cultural-vectors/50m-admin-0-countries-2/), in WGS 84. 1:110m lacks
many of the small states.

- countries.geojson: every country (states, dependencies, disputed areas) of today, `code` is its Wikidata Q-id
  (WIKIDATAID), `name` the English name, `iso` the ISO 3166-1 alpha-3 code or null (ISO_A3 is -99 for France or
  Norway: ISO_A3_EH has theirs; Kosovo, Somaliland… have none)
- points.geojson: the countries too small to be seen on a map of the world (Malta, Luxembourg, Vatican…) once more as
  a point (the place of the label of Natural Earth), to be drawn as a circle
- former.json is not made here but by hand: a former state -> the countries of today on its territory; the script
  checks that its countries are in countries.geojson

Requirements (only of the scripts, not of the package): pyshp, shapely, pyproj, e.g. in a venv of its own:
    python3 -m venv /tmp/geo && /tmp/geo/bin/pip install pyshp shapely pyproj
    /tmp/geo/bin/python scripts/world_geojson.py ne_50m_admin_0_countries.zip
"""
import json
import os
import re
import sys
import tempfile
import zipfile

import numpy
import shapefile
import shapely
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import mapping, shape

OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'election_geo', 'static', 'election', 'geo', 'world')
# in degrees: ~2 km, enough for a map of the world; coordinates rounded to ~100 m
TOLERANCE = 0.02
DIGITS = 3
# km², a country smaller than this is a point too (Luxembourg 2 586 km², Cape Verde 4 033 km²; Cyprus 9 251 km² is
# seen)
SMALL_AREA = 5000
QID = re.compile(r'^Q[1-9][0-9]*$')
ISO_A3 = re.compile(r'^[A-Z]{3}$')
TO_EQUAL_AREA = Transformer.from_crs('EPSG:4326', '+proj=moll +datum=WGS84 +units=km', always_xy=True).transform


def read_shapes(path: str) -> list:
    """[(record dict, shapely geometry)] of the first shapefile in a zip."""
    with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(path) as package:
        package.extractall(directory)
        name = next(name for name in os.listdir(directory) if name.endswith('.shp'))
        reader = shapefile.Reader(os.path.join(directory, name[:-4]), encoding='utf-8')
        return [(record.as_dict(), make_valid(shape(geometry.__geo_interface__)))
                for record, geometry in zip(reader.records(), reader.shapes())]


def iso(record: dict):
    """The ISO 3166-1 alpha-3 code, of ISO_A3_EH when ISO_A3 is -99 (France, Norway), or None."""
    for field in ('ISO_A3', 'ISO_A3_EH'):
        code = record.get(field) or ''
        if ISO_A3.match(code):
            return code
    return None


def area(geometry) -> float:
    """km²"""
    return shapely.transform(geometry, lambda xy: numpy.column_stack(TO_EQUAL_AREA(xy[:, 0], xy[:, 1]))).area


def rounded(geometry, digits: int = DIGITS):
    return shapely.transform(geometry, lambda xy: numpy.round(xy, digits))


def properties(record: dict) -> dict:
    return {'code': record['WIKIDATAID'], 'name': record['NAME_EN'] or record['NAME'], 'iso': iso(record)}


def country(record: dict, geometry) -> dict:
    return {'type': 'Feature', 'properties': properties(record),
            'geometry': mapping(rounded(geometry.simplify(TOLERANCE, preserve_topology=True)))}


def point(record: dict) -> dict:
    return {'type': 'Feature', 'properties': properties(record),
            'geometry': {'type': 'Point', 'coordinates': [round(record['LABEL_X'], DIGITS),
                                                          round(record['LABEL_Y'], DIGITS)]}}


def check(shapes: list):
    """Every country has a Q-id of its own (the key of the maps)."""
    codes = [record['WIKIDATAID'] for record, _ in shapes]
    wrong = [code for code in codes if not QID.match(code or '')]
    twice = sorted({code for code in codes if codes.count(code) > 1})
    if wrong or twice:
        sys.exit(f'wrong Q-ids: {wrong}, Q-ids twice: {twice}')


def check_former(codes: set):
    """The countries of the territories of the former states are on the map."""
    with open(os.path.join(OUTPUT, 'former.json'), encoding='utf-8') as file:
        former = json.load(file)
    missing = {state: sorted(set(item['territory']) - codes) for state, item in former.items()
               if set(item['territory']) - codes}
    if missing:
        sys.exit(f'the countries of former.json not on the map: {missing}')


def write(name: str, features: list):
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, name + '.geojson')
    with open(path, 'w', encoding='utf-8') as file:
        json.dump({'type': 'FeatureCollection', 'features': features}, file, ensure_ascii=False,
                  separators=(',', ':'))
    print(name, len(features), os.path.getsize(path), 'B')


def main(countries_zip: str):
    shapes = read_shapes(countries_zip)
    check(shapes)
    shapes.sort(key=lambda item: int(item[0]['WIKIDATAID'][1:]))
    write('countries', [country(record, geometry) for record, geometry in shapes])
    write('points', [point(record) for record, geometry in shapes if area(geometry) < SMALL_AREA])
    check_former({record['WIKIDATAID'] for record, _ in shapes})


if __name__ == '__main__':
    main(sys.argv[1])
