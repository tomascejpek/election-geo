# election-geo

The boundaries of the Czech units of the elections and of the countries of the world as GeoJSON (WGS 84), simplified
for the maps on the web (of the results of the elections, of the memberships of the states in the international
organisations). Packaged as Django static files, so a Django project serves them at `static/election/geo/`.

## Files

`election_geo/static/election/geo/`:

| File | Units | Properties |
|---|---|---|
| `regions.geojson` | 14 regions (kraje) | `code` (NUMNUTS of the elections, 1100), `name` |
| `districts.geojson` | 77 districts (okresy) | `code` (NUMNUTS), `name` |
| `constituencies.geojson` | 81 senate constituencies (of 2022) | `code` (its number), `name` |
| `municipalities.geojson` | 6254 municipalities | `code` (the code of the municipality, 500011), `name` |
| `wards/<municipality>.geojson` | the wards (volební okrsky) of a municipality of more of them | `code` (500011/1), `ward` (the code of the ward), `years` (of its sets) |
| `parts/<city>.geojson` | the parts of a city of parts (Praha, Brno, Ostrava…) | `code`, `name` of a part |
| `cities.json` | the index: `{municipality: {"wards": [years], "parts": [codes]}}` | |
| `world/countries.geojson` | 242 countries of the world of today (states, dependencies, disputed areas) | `code` (Wikidata Q-id, Q213), `name` (English), `iso` (ISO 3166-1 alpha-3 or null) |
| `world/points.geojson` | the countries smaller than 5 000 km² (Malta, Luxembourg, Vatican…) once more as a point, to be drawn as a circle | as `countries.geojson` |
| `world/former.json` | by hand: a former state -> the countries of today on its territory, `{Q-id: {"name", "territory": [Q-ids], "partial", "source"}}` | |

The wards change between the elections (renumbered, split), so a ward has the years of the sets of boundaries it is
in: a map of an election uses the set of its year.

The map of the world has the boundaries of today. A former state (Czechoslovakia, the Soviet Union, Yugoslavia…) is
drawn as the countries of today on its territory (`former.json`); `partial` is true when it was only a part of them
(East Germany of Germany), so a map can tell it apart.

## Use in Django

```
pip install "election-geo @ git+https://github.com/tomascejpek/election-geo.git@0.2.0"
```

Add `"election_geo"` to `INSTALLED_APPS`: the files are found by the static files finder of the apps, e.g.
`{% static 'election/geo/regions.geojson' %}`. `election_geo.GEO_DIR` is their directory, for reading them on the
server.

## Sources

The open data of the Czech Statistical Office (ČSÚ): the boundaries of the wards and of the senate constituencies of
[volby.cz](https://www.volby.cz/) and of [geodata.csu.gov.cz](https://geodata.csu.gov.cz/), the code lists of the
elections. The data are © ČSÚ, used under its terms of the open data; name the source when you use them.

The countries of the world: [Natural Earth](https://www.naturalearthdata.com/), Admin 0 – Countries 1:50m (public
domain); the Q-ids of [Wikidata](https://www.wikidata.org/) (CC0).

## Making the files again

When a new set of boundaries comes out (new wards before an election), the scripts make the files again from the
sources (see their docstrings for the packages to download). They need `pyshp`, `shapely` and `pyproj`, not needed
by the package:

```
python3 -m venv /tmp/geo && /tmp/geo/bin/pip install pyshp shapely pyproj
/tmp/geo/bin/python scripts/election_geojson.py WARDS.zip SENATE.zip PS2025ciselniky_csv.zip
/tmp/geo/bin/python scripts/election_city_geojson.py 2022=vol_okrsky_2022g100.zip 2024=vol_okrsky_2024g100.zip ...
/tmp/geo/bin/python scripts/world_geojson.py ne_50m_admin_0_countries.zip
```

## Tests

```
python3 -m unittest discover tests
```

The tests of the files need only the standard library; the tests of the scripts run with their requirements
(`/tmp/geo/bin/python -m unittest discover tests`), without them they are skipped.

## License

The code is MIT (see `LICENSE`); the data are of ČSÚ and Natural Earth, see Sources.
