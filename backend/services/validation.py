"""
Data validation before storage.
Flag suspicious records; do not silently delete.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from backend.providers.base import NormalizedWeather


def _coerce_float(value: Optional[float], *, default: Optional[float] = None) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


@dataclass
class ValidationResult:
    is_valid: bool
    flags: list[str] = field(default_factory=list)
    reason: Optional[str] = None


# Physically plausible ranges for surface weather (not medical thresholds)
TEMP_MIN, TEMP_MAX = -40.0, 55.0
HUMIDITY_MIN, HUMIDITY_MAX = 0.0, 100.0
RAIN_MIN, RAIN_MAX = 0.0, 500.0  # mm per period
WIND_MIN, WIND_MAX = 0.0, 100.0  # m/s
PRESSURE_MIN, PRESSURE_MAX = 870.0, 1085.0  # hPa


def validate_weather(obs: NormalizedWeather) -> ValidationResult:
    flags: list[str] = []

    if obs.timestamp is None:
        flags.append("MISSING_TIMESTAMP")
    elif obs.timestamp > datetime.utcnow().replace(tzinfo=None) + __import__("datetime").timedelta(days=16):
        flags.append("TIMESTAMP_FAR_FUTURE")

    temperature_c = _coerce_float(obs.temperature_c)
    if obs.temperature_c is not None and temperature_c is None:
        flags.append(f"TEMPERATURE_INVALID ({obs.temperature_c})")
    elif temperature_c is not None:
        if not (TEMP_MIN <= temperature_c <= TEMP_MAX):
            flags.append(f"TEMPERATURE_OUT_OF_RANGE ({temperature_c})")
    else:
        flags.append("MISSING_TEMPERATURE")

    temperature_min_c = _coerce_float(obs.temperature_min_c)
    if obs.temperature_min_c is not None and temperature_min_c is None:
        flags.append(f"TEMPERATURE_MIN_INVALID ({obs.temperature_min_c})")
    elif temperature_min_c is not None:
        if not (TEMP_MIN <= temperature_min_c <= TEMP_MAX):
            flags.append(f"TEMPERATURE_MIN_OUT_OF_RANGE ({temperature_min_c})")
        if temperature_c is not None and temperature_min_c > temperature_c:
            flags.append("DAILY_MIN_GREATER_THAN_MAX")

    humidity = _coerce_float(obs.humidity_percent)
    if obs.humidity_percent is not None and humidity is None:
        flags.append(f"HUMIDITY_INVALID ({obs.humidity_percent})")
    elif humidity is not None and not (HUMIDITY_MIN <= humidity <= HUMIDITY_MAX):
        flags.append(f"HUMIDITY_OUT_OF_RANGE ({humidity})")

    rainfall = _coerce_float(obs.rainfall_mm)
    if obs.rainfall_mm is not None and rainfall is None:
        flags.append(f"RAINFALL_INVALID ({obs.rainfall_mm})")
    elif rainfall is not None and not (RAIN_MIN <= rainfall <= RAIN_MAX):
        flags.append(f"RAINFALL_OUT_OF_RANGE ({rainfall})")

    wind = _coerce_float(obs.wind_speed_ms)
    if obs.wind_speed_ms is not None and wind is None:
        flags.append(f"WIND_INVALID ({obs.wind_speed_ms})")
    elif wind is not None and not (WIND_MIN <= wind <= WIND_MAX):
        flags.append(f"WIND_OUT_OF_RANGE ({wind})")

    pressure = _coerce_float(obs.pressure_hpa)
    if obs.pressure_hpa is not None and pressure is None:
        flags.append(f"PRESSURE_INVALID ({obs.pressure_hpa})")
    elif pressure is not None and not (PRESSURE_MIN <= pressure <= PRESSURE_MAX):
        flags.append(f"PRESSURE_OUT_OF_RANGE ({pressure})")

    if obs.latitude is None or obs.longitude is None:
        flags.append("MISSING_COORDINATES")
    elif not (-90 <= _coerce_float(obs.latitude, default=-999.0) <= 90 and -180 <= _coerce_float(obs.longitude, default=-999.0) <= 180):
        flags.append("INVALID_COORDINATES")

    hard = any(
        f.startswith(p)
        for f in flags
        for p in (
            "TEMPERATURE_OUT_OF_RANGE",
            "TEMPERATURE_INVALID",
            "HUMIDITY_OUT_OF_RANGE",
            "HUMIDITY_INVALID",
            "TEMPERATURE_MIN_OUT_OF_RANGE",
            "TEMPERATURE_MIN_INVALID",
            "DAILY_MIN_GREATER_THAN_MAX",
            "INVALID_COORDINATES",
            "MISSING_TEMPERATURE",
        )
    )
    is_valid = not hard

    reason = "; ".join(flags) if flags else None
    return ValidationResult(is_valid=is_valid, flags=flags, reason=reason)
