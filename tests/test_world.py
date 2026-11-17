"""The files of the countries of the world (stdlib only) and the functions of scripts/world_geojson.py (skipped
without the requirements of the scripts: pyshp, shapely, pyproj)."""
import importlib.util
import json
import os
import re
import unittest

from election_geo import GEO_DIR

WORLD = os.path.join(GEO_DIR, 'world')
SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'world_geojson.py')
QID = re.compile(r'^Q[1-9][0-9]*$')
CZECHIA, SLOVAKIA, GERMANY, FRANCE, NORWAY, KOSOVO = 'Q213', 'Q214', 'Q183', 'Q142', 'Q20', 'Q1246'


def load(name: str):
    with open(os.path.join(WORLD, name), encoding='utf-8') as file:
        return json.load(file)


def features(name: str) -> dict:
    data = load(name)
    assert data['type'] == 'FeatureCollection'
    return {feature['properties']['code']: feature for feature in data['features']}


class CountriesTest(unittest.TestCase):

    def setUp(self):
        self.countries = load('countries.geojson')['features']
        self.by_code = features('countries.geojson')

    def test_every_country_has_a_qid_of_its_own(self):
        codes = [feature['properties']['code'] for feature in self.countries]
        self.assertGreater(len(codes), 200)
        self.assertTrue(all(QID.match(code) for code in codes), codes)
        self.assertEqual(len(codes), len(set(codes)))

    def test_properties(self):
        for feature in self.countries:
            self.assertEqual(set(feature['properties']), {'code', 'name', 'iso'})
            self.assertTrue(feature['properties']['name'])
            self.assertIn(feature['geometry']['type'], ('Polygon', 'MultiPolygon'))

    def test_iso_of_the_countries_of_minus_99(self):
        self.assertEqual(self.by_code[CZECHIA]['properties']['iso'], 'CZE')
        self.assertEqual(self.by_code[FRANCE]['properties']['iso'], 'FRA')
        self.assertEqual(self.by_code[NORWAY]['properties']['iso'], 'NOR')
        self.assertIsNone(self.by_code[KOSOVO]['properties']['iso'])
        for feature in self.countries:
            code = feature['properties']['iso']
            self.assertTrue(code is None or re.match(r'^[A-Z]{3}$', code), code)

    def test_coordinates_are_wgs84(self):
        def points(coordinates):
            if isinstance(coordinates[0], (int, float)):
                yield coordinates
            else:
                for item in coordinates:
                    yield from points(item)
        for feature in self.countries:
            for x, y in points(feature['geometry']['coordinates']):
                self.assertTrue(-180 <= x <= 180 and -90 <= y <= 90, (feature['properties']['code'], x, y))


class PointsTest(unittest.TestCase):

    def test_small_countries_are_points_of_the_map(self):
        points, countries = features('points.geojson'), features('countries.geojson')
        self.assertTrue({'Q233', 'Q32', 'Q237', 'Q334'} <= set(points))  # Malta, Luxembourg, Vatican, Singapore
        self.assertNotIn(CZECHIA, points)
        self.assertLessEqual(set(points), set(countries))
        for code, point in points.items():
            self.assertEqual(point['geometry']['type'], 'Point')
            self.assertEqual(point['properties'], countries[code]['properties'])


class TerritoriesTest(unittest.TestCase):

    def test_territories_are_countries_of_the_map(self):
        territories, countries = load('territories.json'), features('countries.geojson')
        self.assertEqual(territories['Q33946']['territory'], [CZECHIA, SLOVAKIA])  # Czechoslovakia
        self.assertEqual(territories['Q853348']['territory'], [CZECHIA, SLOVAKIA])  # its regime, ČSSR
        self.assertEqual(len(territories['Q15180']['territory']), 15)  # the Soviet Union
        self.assertTrue(territories['Q16957']['partial'])  # East Germany is a part of Germany
        # a realm of more countries, the member of the UN
        self.assertEqual(territories['Q756617']['territory'], ['Q35', 'Q223', 'Q4628'])
        self.assertFalse(territories['Q756617']['partial'])
        for code, item in territories.items():
            self.assertTrue(QID.match(code), code)
            self.assertNotIn(code, countries, 'a state on the map is its own territory')
            self.assertEqual(set(item), {'name', 'territory', 'partial', 'source'})
            self.assertTrue(item['territory'])
            self.assertLessEqual(set(item['territory']), set(countries), code)
            self.assertIsInstance(item['partial'], bool)
            self.assertTrue(item['source'].startswith('https://'))


def script():
    spec = importlib.util.spec_from_file_location('world_geojson', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REQUIREMENTS = all(importlib.util.find_spec(name) for name in ('shapefile', 'shapely', 'pyproj'))


@unittest.skipUnless(REQUIREMENTS, 'the requirements of the scripts: pyshp, shapely, pyproj')
class ScriptTest(unittest.TestCase):

    def setUp(self):
        self.script = script()

    def test_iso(self):
        iso = self.script.iso
        self.assertEqual(iso({'ISO_A3': 'CZE', 'ISO_A3_EH': 'CZE'}), 'CZE')
        self.assertEqual(iso({'ISO_A3': '-99', 'ISO_A3_EH': 'FRA'}), 'FRA')
        self.assertIsNone(iso({'ISO_A3': '-99', 'ISO_A3_EH': '-99'}))
        self.assertIsNone(iso({'ISO_A3': '', 'ISO_A3_EH': None}))
        self.assertIsNone(iso({'ISO_A3': 'cz<'}))

    def test_area_in_km2(self):
        from shapely.geometry import box
        # a degree by a degree on the equator ~ 111 × 111 km
        self.assertAlmostEqual(self.script.area(box(0, 0, 1, 1)) / 12300, 1, places=1)
        self.assertLess(self.script.area(box(14.4, 35.8, 14.6, 36.0)), self.script.SMALL_AREA)  # ~ Malta

    def test_wrong_or_twice_qids_stop_the_script(self):
        from shapely.geometry import box
        for codes in (['Q1', ''], ['Q1', 'Q1'], ['Q1', 'Q1; drop'], ['Q1', None]):
            with self.subTest(codes=codes), self.assertRaises(SystemExit):
                self.script.check([({'WIKIDATAID': code}, box(0, 0, 1, 1)) for code in codes])
        self.script.check([({'WIKIDATAID': code}, box(0, 0, 1, 1)) for code in ('Q1', 'Q2')])

    def test_country_and_point(self):
        from shapely.geometry import box
        record = {'WIKIDATAID': 'Q233', 'NAME_EN': 'Malta', 'NAME': 'Malta', 'ISO_A3': 'MLT',
                  'LABEL_X': 14.4412345, 'LABEL_Y': 35.8912345}
        country = self.script.country(record, box(14.1234567, 35.7, 14.6, 36.1))
        self.assertEqual(country['properties'], {'code': 'Q233', 'name': 'Malta', 'iso': 'MLT'})
        self.assertIn([14.123, 35.7], [list(xy) for xy in country['geometry']['coordinates'][0]])
        self.assertEqual(self.script.point(record)['geometry'], {'type': 'Point', 'coordinates': [14.441, 35.891]})


if __name__ == '__main__':
    unittest.main()
