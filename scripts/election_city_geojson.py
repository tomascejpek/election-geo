"""The boundaries of the wards and of the parts of the cities for the maps of the elections in a municipality, as
GeoJSON files in election_geo/static/election/geo/: wards/<municipality>.geojson for every municipality of more wards,
parts/<city>.geojson for the cities of parts (Praha, Brno, Ostrava…), and cities.json, the index of them. Run when
a new set of boundaries comes out.

The wards change between the elections (renumbered, split), so a set of boundaries is used only for the elections of
its year. The sets, generalised to 100 m by ČSÚ:
- 2022, 2024: volby.cz, opendata/kv2022/geo/vol_okrsky_2022g100.zip, opendata/se2024/geo/vol_okrsky_2024g100.zip
  (shapefiles in S-JTSK: KOD, CISLO, MOMC, OBEC, in any case)
- 2025, 2026: geodata.csu.gov.cz, the layers 1 (generalised) of Hosted/Volebni_okrsky_2025_gdb and
  Hosted/Volební_okrsky_ZO2026 (an ArcGIS feature service: kod, cislo, kod_mco, naz_mco, kod_obec)
A ward of the same code, number and shape in more sets is written once with all its years: the shapes differ by less
than 10 % of the area (the sources generalise differently, the same ward differs by 2-8 %, a split one much more).
The parts of a city are the wards of the newest set dissolved by their part.

Requirements (only of the scripts, not of the package): pyshp, shapely, pyproj, e.g. in a venv of its own:
    python3 -m venv /tmp/geo && /tmp/geo/bin/pip install pyshp shapely pyproj
    /tmp/geo/bin/python scripts/election_city_geojson.py 2022=vol_okrsky_2022g100.zip 2024=vol_okrsky_2024g100.zip \\
        2025=https://geodata.csu.gov.cz/server/rest/services/Hosted/Volebni_okrsky_2025_gdb/FeatureServer/1 \\
        2026=https://geodata.csu.gov.cz/server/rest/services/Hosted/Volební_okrsky_ZO2026/FeatureServer/1
"""
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict

import shapefile
from pyproj import Transformer
from shapely import make_valid, union_all
from shapely.geometry import mapping, shape
from shapely.ops import transform

OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'election_geo', 'static', 'election', 'geo')
# ~1 m, the wards of the old towns are small
DIGITS = 5
# the parts of a city dissolved of the wards, simplified a little in S-JTSK (m)
PARTS_TOLERANCE = 20
TO_WGS84 = Transformer.from_crs('EPSG:5514', 'EPSG:4326', always_xy=True).transform
USER_AGENT = 'PivoBot/1.0 (https://pivni.info)'
PAGE = 2000
SAME_SHAPE = 0.1


class Ward:
    def __init__(self, code: str, number: int, municipality: str, part: str, part_name: str, geometry):
        self.code, self.number, self.municipality = code, number, municipality
        self.part, self.part_name = part, part_name
        self.geometry = geometry  # WGS84

    @property
    def unit(self) -> str:
        """The municipality of the ward in the data of the elections: the part of a city, else the municipality."""
        return self.part or self.municipality


def same_shape(one, other) -> bool:
    """The same ward drawn again (another first point, rounding): the shapes differ by less than 10 % of the area."""
    try:
        return one.symmetric_difference(other).area <= SAME_SHAPE * max(one.area, other.area)
    except Exception:
        return False


def rounded(geometry):
    return transform(lambda x, y, z=None: (round(x, DIGITS), round(y, DIGITS)), geometry)


def read_shapefile(path: str) -> list:
    with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(path) as package:
        package.extractall(directory)
        name = next(name for name in os.listdir(directory) if name.endswith('.shp'))
        reader = shapefile.Reader(os.path.join(directory, name[:-4]), encoding='cp1250')
        wards = []
        for record, geometry in zip(reader.records(), reader.shapes()):
            # KOD or Kod by the year, MOMC empty or 0 outside the cities of parts
            fields = {key.upper(): value for key, value in record.as_dict().items()}
            wards.append(Ward(str(fields['KOD']), int(fields['CISLO']), str(fields['OBEC']),
                              str(fields['MOMC'] or '') if fields.get('MOMC') not in (None, '', 0) else '', '',
                              transform(TO_WGS84, make_valid(shape(geometry.__geo_interface__)))))
        return wards


def read_feature_service(url: str) -> list:
    """The features of a layer of an ArcGIS feature service as GeoJSON (WGS84), by pages."""
    wards, offset = [], 0
    while True:
        query = urllib.parse.urlencode({
            'where': '1=1', 'outFields': 'kod,cislo,kod_mco,naz_mco,kod_obec', 'returnGeometry': 'true',
            'outSR': '4326', 'f': 'geojson', 'orderByFields': 'objectid', 'resultOffset': offset,
            'resultRecordCount': PAGE})
        request = urllib.request.Request(urllib.parse.quote(url, safe=':/') + '/query?' + query,
                                         headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(request, timeout=300) as response:
            features = json.load(response).get('features', [])
        for feature in features:
            properties = feature['properties']
            try:
                number = int(str(properties['cislo']).strip())
            except ValueError:
                # a feature without the number of its ward (a part of a ward, an error of the source)
                print('left out, no number:', properties)
                continue
            if not feature.get('geometry'):
                print('left out, no geometry:', properties)
                continue
            wards.append(Ward(str(properties['kod']), number, str(properties['kod_obec']),
                              str(properties.get('kod_mco') or '').strip(), properties.get('naz_mco') or '',
                              make_valid(shape(feature['geometry']))))
        if len(features) < PAGE:
            return wards
        offset += PAGE


def read(source: str) -> list:
    return read_feature_service(source) if source.startswith('http') else read_shapefile(source)


def write(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, separators=(',', ':'))


def main(sources: dict):
    years = sorted(sources)
    # municipality -> (code, number, unit) -> [[geometry, years]], a ward of another shape in another year apart
    by_municipality = defaultdict(lambda: defaultdict(list))
    newest = {}
    names = {}
    for year in years:
        wards = read(sources[year])
        print(year, len(wards), 'wards')
        newest = wards
        for ward in wards:
            geometry = rounded(ward.geometry)
            shapes = by_municipality[ward.municipality][(ward.code, ward.number, ward.unit)]
            same = next((item for item in shapes if same_shape(item[0], geometry)), None)
            if same is None:
                shapes.append([geometry, [year]])
            else:
                # the newest drawing of the ward
                same[0] = geometry
                same[1].append(year)
            if ward.part_name:
                names[ward.part] = ward.part_name
    for directory in ('wards', 'parts'):
        shutil.rmtree(os.path.join(OUTPUT, directory), ignore_errors=True)
    index = {}
    size = 0
    for municipality, by_key in sorted(by_municipality.items()):
        wards = [(key, item) for key, shapes in by_key.items() for item in shapes]
        ward_years = defaultdict(int)
        for _, (_, ward_in) in wards:
            for year in ward_in:
                ward_years[year] += 1
        # a map of wards only where a year has more of them
        map_years = sorted(year for year, count in ward_years.items() if count > 1)
        if not map_years:
            continue
        features = [{'type': 'Feature', 'geometry': mapping(geometry),
                     'properties': {'code': '{}/{}'.format(unit, number), 'ward': code, 'years': ward_in}}
                    for (code, number, unit), (geometry, ward_in) in sorted(wards, key=lambda item: (
                        item[0][2], item[0][1], item[1][1]))]
        path = os.path.join(OUTPUT, 'wards', municipality + '.geojson')
        write(path, {'type': 'FeatureCollection', 'features': features})
        size += os.path.getsize(path)
        index[municipality] = {'wards': map_years}
    # the parts of the cities, of the newest set
    parts = defaultdict(lambda: defaultdict(list))
    for ward in newest:
        if ward.part:
            parts[ward.municipality][ward.part].append(ward.geometry)
    to_sjtsk = Transformer.from_crs('EPSG:4326', 'EPSG:5514', always_xy=True).transform
    for city, city_parts in sorted(parts.items()):
        features = []
        for part, geometries in sorted(city_parts.items()):
            geometry = transform(to_sjtsk, union_all(geometries)).simplify(PARTS_TOLERANCE, preserve_topology=True)
            features.append({'type': 'Feature', 'geometry': mapping(rounded(transform(TO_WGS84, geometry))),
                             'properties': {'code': part, 'name': names.get(part, '')}})
        path = os.path.join(OUTPUT, 'parts', city + '.geojson')
        write(path, {'type': 'FeatureCollection', 'features': features})
        size += os.path.getsize(path)
        index.setdefault(city, {})['parts'] = sorted(city_parts)
    write(os.path.join(OUTPUT, 'cities.json'), index)
    print('municipalities', len(index), 'cities of parts', len(parts), 'size', size, 'B')


if __name__ == '__main__':
    main(dict(argument.split('=', 1) for argument in sys.argv[1:]))
