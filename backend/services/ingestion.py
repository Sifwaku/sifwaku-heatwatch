"""
Ingestion service: fetch → validate → store with provenance.
"""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.database.models import (
    APIRequest,
    ENSOObservation,
    Location,
    WeatherForecast,
    WeatherObservation,
)
from backend.providers.base import NormalizedENSO, NormalizedWeather
from backend.providers.registry import get_climate_provider, get_weather_provider
from backend.services.validation import validate_weather


def get_or_create_location(
    db: Session,
    name: str,
    latitude: float,
    longitude: float,
    country: str = "Zambia",
    province: Optional[str] = None,
) -> Location:
    loc = (
        db.query(Location)
        .filter(
            Location.latitude == latitude,
            Location.longitude == longitude,
        )
        .first()
    )
    if loc:
        return loc
    loc = Location(
        name=name,
        country=country,
        province=province,
        latitude=latitude,
        longitude=longitude,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


def log_api_request(
    db: Session,
    api_name: str,
    endpoint: str,
    http_status: Optional[int],
    response_time_ms: Optional[float],
    success: bool,
    error_message: Optional[str] = None,
) -> None:
    rec = APIRequest(
        api_name=api_name,
        endpoint=endpoint,
        http_status=http_status,
        response_time_ms=response_time_ms,
        success=success,
        error_message=error_message,
    )
    db.add(rec)
    db.commit()


def store_observation(db: Session, loc: Location, obs: NormalizedWeather) -> tuple[Optional[WeatherObservation], str]:
    vr = validate_weather(obs)
    existing = (
        db.query(WeatherObservation)
        .filter(
            WeatherObservation.location_id == loc.id,
            WeatherObservation.timestamp == obs.timestamp,
            WeatherObservation.source == obs.source,
        )
        .first()
    )
    if existing:
        if obs.temperature_min_c is not None and existing.temperature_min_c is None:
            existing.temperature_min_c = obs.temperature_min_c
            db.commit()
        return existing, "DUPLICATE — already stored"

    row = WeatherObservation(
        location_id=loc.id,
        timestamp=obs.timestamp,
        temperature_c=obs.temperature_c,
        temperature_min_c=obs.temperature_min_c,
        humidity_percent=obs.humidity_percent,
        rainfall_mm=obs.rainfall_mm,
        wind_speed_ms=obs.wind_speed_ms,
        wind_direction_deg=obs.wind_direction_deg,
        pressure_hpa=obs.pressure_hpa,
        source=obs.source,
        is_valid=vr.is_valid,
        validation_flags="; ".join(vr.flags) if vr.flags else None,
        raw_json=json.dumps(obs.raw_payload) if obs.raw_payload else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    status = "STORED" if vr.is_valid else f"STORED_WITH_FLAGS: {vr.reason}"
    return row, status


def store_forecasts(db: Session, loc: Location, items: list[NormalizedWeather]) -> int:
    count = 0
    for obs in items:
        vr = validate_weather(obs)
        row = WeatherForecast(
            location_id=loc.id,
            forecast_time=obs.timestamp,
            temperature_c=obs.temperature_c,
            humidity_percent=obs.humidity_percent,
            rainfall_mm=obs.rainfall_mm,
            wind_speed_ms=obs.wind_speed_ms,
            pressure_hpa=obs.pressure_hpa,
            source=obs.source,
            is_valid=vr.is_valid,
            validation_flags="; ".join(vr.flags) if vr.flags else None,
        )
        db.add(row)
        count += 1
    db.commit()
    return count


def store_enso(db: Session, items: list[NormalizedENSO]) -> int:
    count = 0
    for e in items:
        existing = (
            db.query(ENSOObservation)
            .filter(
                ENSOObservation.date_label == e.date,
                ENSOObservation.source == e.source,
            )
            .first()
        )
        if existing:
            continue
        row = ENSOObservation(
            date_label=e.date,
            enso_index=e.enso_index,
            enso_phase=e.enso_phase,
            source=e.source,
            raw_json=json.dumps(e.raw_payload) if e.raw_payload else None,
        )
        db.add(row)
        count += 1
    db.commit()
    return count


async def ingest_current(
    db: Session,
    latitude: float,
    longitude: float,
    location_name: str = "Lusaka",
    provider_name: Optional[str] = None,
) -> dict:
    provider = get_weather_provider(provider_name)
    obs, err = await provider.get_current(latitude, longitude, location_name)
    if err or obs is None:
        return {"ok": False, "error": err or "No data", "provider": provider.name}

    loc = get_or_create_location(db, location_name, latitude, longitude)
    row, status = store_observation(db, loc, obs)
    is_valid = bool(row and row.is_valid)
    return {
        "ok": is_valid,
        "error": None if is_valid else f"Observation failed validation: {row.validation_flags or 'unknown validation error'}",
        "provider": provider.name,
        "storage_status": status,
        "observation_id": row.id if row else None,
        "is_valid": row.is_valid if row else None,
        "validation_flags": row.validation_flags if row else None,
        "data": {
            "timestamp": obs.timestamp.isoformat(),
            "temperature_c": obs.temperature_c,
            "humidity_percent": obs.humidity_percent,
            "rainfall_mm": obs.rainfall_mm,
            "wind_speed_ms": obs.wind_speed_ms,
            "pressure_hpa": obs.pressure_hpa,
            "source": obs.source,
        },
    }
