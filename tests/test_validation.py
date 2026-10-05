from datetime import datetime

from backend.providers.base import NormalizedWeather
from backend.services.validation import validate_weather


def test_valid_observation():
    obs = NormalizedWeather(
        timestamp=datetime.utcnow(),
        location="Lusaka",
        latitude=-15.4,
        longitude=28.3,
        temperature_c=28.0,
        humidity_percent=55.0,
        rainfall_mm=0.0,
        wind_speed_ms=3.0,
        pressure_hpa=1012.0,
        source="test",
    )
    vr = validate_weather(obs)
    assert vr.is_valid
    assert not vr.flags


def test_humidity_out_of_range():
    obs = NormalizedWeather(
        timestamp=datetime.utcnow(),
        location="Lusaka",
        latitude=-15.4,
        longitude=28.3,
        temperature_c=28.0,
        humidity_percent=145.0,
        source="test",
    )
    vr = validate_weather(obs)
    assert not vr.is_valid
    assert any("HUMIDITY" in f for f in vr.flags)


def test_valid_daily_minimum_temperature():
    obs = NormalizedWeather(
        timestamp=datetime.utcnow(),
        location="Lusaka",
        latitude=-15.4,
        longitude=28.3,
        temperature_c=30.0,
        temperature_min_c=18.0,
        source="test",
    )
    assert validate_weather(obs).is_valid


def test_daily_minimum_cannot_exceed_maximum():
    obs = NormalizedWeather(
        timestamp=datetime.utcnow(),
        location="Lusaka",
        latitude=-15.4,
        longitude=28.3,
        temperature_c=20.0,
        temperature_min_c=22.0,
        source="test",
    )
    result = validate_weather(obs)
    assert not result.is_valid
    assert "DAILY_MIN_GREATER_THAN_MAX" in result.flags
