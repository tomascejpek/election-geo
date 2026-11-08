from django.apps import AppConfig


class ElectionGeoConfig(AppConfig):
    """Only registers the static files in election_geo/static/election/geo/."""

    name = "election_geo"
    verbose_name = "Election geo"
