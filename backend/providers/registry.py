"""
Provider registry — application code uses this, not concrete providers.
"""
from typing import Optional

from backend.providers.base import ClimateProvider, WeatherProvider
from backend.providers.noaa_enso import NOAAENSOProvider
from backend.providers.open_meteo import OpenMeteoProvider
from backend.providers.openweathermap import OpenWeatherMapProvider


def get_weather_providers() -> list[WeatherProvider]:
    """Return all configured weather providers (order = preference)."""
    return [
        OpenMeteoProvider(),
        OpenWeatherMapProvider(),
    ]


def get_climate_providers() -> list[ClimateProvider]:
    return [
        NOAAENSOProvider(),
    ]


def get_weather_provider(name: Optional[str] = None) -> WeatherProvider:
    providers = {p.name: p for p in get_weather_providers()}
    if name and name in providers:
        return providers[name]
    return providers["Open-Meteo"]


def get_climate_provider(name: Optional[str] = None) -> ClimateProvider:
    providers = {p.name: p for p in get_climate_providers()}
    if name and name in providers:
        return providers[name]
    return providers["NOAA CPC ONI"]
