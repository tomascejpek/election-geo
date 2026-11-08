"""The boundaries of the regions, districts, senate constituencies and municipalities for the maps of the elections, as
GeoJSON files in election_geo/static/election/geo/. Run once when the boundaries change.

The sources are the open data of volby.cz (ČSÚ), in S-JTSK:
- the wards of 2024 (vol_okrsky_2024g100.zip): dissolved by their municipality (a city of parts as a whole), its
  district and region
- the senate constituencies of 2022 (VO_Senat_2022g300.zip)
- the municipalities of PS 2025 (pscoco.csv of PS2025ciselniky*_csv.zip): municipality -> district, region (NUMNUTS,
  the codes of the units of the elections)

Requirements (only of the scripts, not of the package): pyshp, shapely, pyproj, e.g. in a venv of its own:
    python3 -m venv /tmp/geo && /tmp/geo/bin/pip install pyshp shapely pyproj
    /tmp/geo/bin/python scripts/election_geojson.py WARDS.zip SENATE.zip PS2025ciselniky_csv.zip
"""
import csv
import io
import json
import os
import sys
import tempfile
import zipfile

import shapefile
from pyproj import Transformer
from shapely import make_valid, union_all
from shapely.geometry import mapping, shape
from shapely.ops import transform

OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'election_geo', 'static', 'election', 'geo')
# simplified to hundreds of metres in S-JTSK, enough for a map of the country; coordinates rounded to ~10 m, of the
# 6 thousand municipalities to ~100 m (1.8 MB)
TOLERANCE = {'regions': 400, 'districts': 250, 'constituencies': 250, 'municipalities': 400}
DIGITS = {'municipalities': 3}
DEFAULT_DIGITS = 4
TO_WGS84 = Transformer.from_crs('EPSG:5514', 'EPSG:4326', always_xy=True).transform


def read_shapes(path: str) -> list:
    """[(record dict, shapely geometry)] of the first shapefile in a zip."""
    with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(path) as package:
        package.extractall(directory)
        name = next(name for name in os.listdir(directory) if name.endswith('.shp'))
        reader = shapefile.Reader(os.path.join(directory, name[:-4]), encoding='cp1250')
        return [(record.as_dict(), make_valid(shape(geometry.__geo_interface__)))
                for record, geometry in zip(reader.records(), reader.shapes())]


def read_csv(package, name: str) -> list:
    member = next(member for member in package.namelist() if member.endswith('csv_od/' + name + '.csv'))
    return list(csv.DictReader(io.StringIO(package.read(member).decode('utf-8-sig'))))


def municipalities(path: str) -> tuple:
    """municipality (and a city of parts) -> (district, region) of pscoco; municipality, district, region -> name
    (cisob, pscoco, cnumnuts)."""
    with zipfile.ZipFile(path) as package:
        rows = read_csv(package, 'pscoco')
        names = {row['OBEC_PREZ']: row['NAZEVOBCE'] for row in read_csv(package, 'cisob')}
        areas = {row['NUMNUTS']: row['NAZEVNUTS'] for row in read_csv(package, 'cnumnuts')}
    units = {}
    for row in rows:
        names.setdefault(row['OBEC'], row['NAZEVOBCE'])
        for code in (row['OBEC'], row.get('OBEC_PREZ')):
            if code:
                units.setdefault(code, (row['OKRES'], row['KRAJ']))
    return units, names, areas


def rounded(geometry, digits: int):
    return transform(lambda x, y, z=None: (round(x, digits), round(y, digits)), geometry)


def feature(code: str, name: str, geometry, tolerance: float, digits: int = DEFAULT_DIGITS) -> dict:
    geometry = transform(TO_WGS84, geometry.simplify(tolerance, preserve_topology=True))
    return {'type': 'Feature', 'properties': {'code': code, 'name': name},
            'geometry': mapping(rounded(geometry, digits))}


def write(name: str, features: list):
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, name + '.geojson')
    with open(path, 'w', encoding='utf-8') as file:
        json.dump({'type': 'FeatureCollection', 'features': features}, file, ensure_ascii=False,
                  separators=(',', ':'))
    print(name, len(features), os.path.getsize(path), 'B')


def main(wards_zip: str, senate_zip: str, codelists_zip: str):
    units, names, areas = municipalities(codelists_zip)
    districts, regions, cities, missing = {}, {}, {}, set()
    for record, geometry in read_shapes(wards_zip):
        # a ward of Prague, Brno…: OBEC is the city, MOMC its part
        cities.setdefault(record['OBEC'], []).append(geometry)
        municipality = record.get('MOMC') or record['OBEC']
        found = units.get(municipality) or units.get(record['OBEC'])
        if not found:
            missing.add(municipality)
            continue
        district, region = found
        districts.setdefault(district, []).append(geometry)
        regions.setdefault(region, []).append(geometry)
    if missing:
        print('wards of municipalities not in pscoco:', sorted(missing)[:20], len(missing))
    write('regions', [feature(code, areas.get(code, ''), union_all(parts), TOLERANCE['regions'])
                      for code, parts in sorted(regions.items())])
    write('districts', [feature(code, areas.get(code, ''), union_all(parts), TOLERANCE['districts'])
                        for code, parts in sorted(districts.items())])
    write('constituencies', [feature(str(int(record['OBVOD'])), record['SIDLO'], geometry,
                                     TOLERANCE['constituencies'])
                             for record, geometry in read_shapes(senate_zip)])
    write('municipalities', [feature(code, names.get(code, ''), union_all(parts), TOLERANCE['municipalities'],
                                     DIGITS['municipalities'])
                             for code, parts in sorted(cities.items())])


if __name__ == '__main__':
    main(*sys.argv[1:4])
