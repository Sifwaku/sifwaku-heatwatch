"""
FastAPI routes — API Laboratory, status, current conditions, risk, ENSO.
All external calls are server-side; keys never exposed to frontend.
"""
import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
import httpx
from sqlalchemy.orm import Session

from backend.analytics.heat_risk import compute_risk_score, result_to_dict
from backend.config import get_settings
from backend.database.models import ENSOObservation, RiskAssessment
from backend.database.session import get_db
from backend.providers.registry import (
    get_climate_provider,
    get_climate_providers,
    get_weather_provider,
    get_weather_providers,
)
from backend.services.ingestion import (
    get_or_create_location,
    ingest_current,
    log_api_request,
    store_enso,
    store_forecasts,
    store_observation,
)
from backend.services.validation import validate_weather

router = APIRouter()
settings = get_settings()

NASA_RAINFALL_DOMAINS_URL = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/"
    "IMERG_Precipitation_Rate_30min/default/GoogleMapsCompatible_Level6/all/"
)
_rainfall_frames_cache = None
_rainfall_frames_cache_until = 0.0
_rainfall_frames_lock = asyncio.Lock()


def _expand_rainfall_domains(xml_content: bytes) -> list[datetime]:
    root = ET.fromstring(xml_content)
    instants = set()
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "Domain" or not node.text:
            continue
        for value in node.text.split(","):
            parts = value.strip().split("/")
            try:
                start = datetime.fromisoformat(parts[0].replace("Z", "+00:00")).astimezone(timezone.utc)
                if len(parts) == 1:
                    instants.add(start)
                    continue
                end = datetime.fromisoformat(parts[1].replace("Z", "+00:00")).astimezone(timezone.utc)
                step_match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", parts[2]) if len(parts) > 2 else None
                if not step_match:
                    continue
                days, hours, minutes, seconds = (int(group or 0) for group in step_match.groups())
                step = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
                if step.total_seconds() <= 0:
                    continue
                frame = start
                while frame <= end and len(instants) < 400:
                    instants.add(frame)
                    frame += step
            except (ValueError, OverflowError):
                continue
    return sorted(instants)


@router.get("/rainfall-map-frames")
async def rainfall_map_frames():
    """Return recent, available NASA GPM IMERG timestamps for the map overlay."""
    global _rainfall_frames_cache, _rainfall_frames_cache_until
    if _rainfall_frames_cache and time.monotonic() < _rainfall_frames_cache_until:
        return _rainfall_frames_cache

    async with _rainfall_frames_lock:
        if _rainfall_frames_cache and time.monotonic() < _rainfall_frames_cache_until:
            return _rainfall_frames_cache
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = f"{NASA_RAINFALL_DOMAINS_URL}{start}--{end}.xml"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url)
                response.raise_for_status()
            frames = _expand_rainfall_domains(response.content)
            if not frames:
                raise ValueError("No recent satellite rainfall frames are available.")
            latest = frames[-1]
            recent = [frame for frame in frames if frame >= latest - timedelta(hours=8)]
            _rainfall_frames_cache = {
                "ok": True,
                "source": "NASA GPM IMERG",
                "frames": [frame.isoformat(timespec="seconds").replace("+00:00", "Z") for frame in recent],
                "latest_frame": latest.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "stale": False,
            }
            _rainfall_frames_cache_until = time.monotonic() + 600
            return _rainfall_frames_cache
        except (httpx.HTTPError, ET.ParseError, ValueError) as error:
            if _rainfall_frames_cache:
                return {**_rainfall_frames_cache, "stale": True, "error": str(error)}
            return {"ok": False, "source": "NASA GPM IMERG", "frames": [], "error": str(error)}


def _observation_quality(weather: dict) -> dict:
    """Describe freshness and evidence type without overstating accuracy."""
    if not weather.get("ok") or not weather.get("data"):
        return {
            "status": "UNAVAILABLE",
            "score": 0,
            "age_minutes": None,
            "basis": "No usable provider estimate",
        }
    timestamp = weather["data"].get("timestamp")
    try:
        observed_at = datetime.fromisoformat(str(timestamp).replace("Z", ""))
        age_minutes = max(0, round((datetime.utcnow() - observed_at).total_seconds() / 60, 1))
    except (TypeError, ValueError):
        age_minutes = None

    if age_minutes is None:
        status, score = "TIME UNKNOWN", 25
    elif age_minutes <= 60:
        status, score = "FRESH MODEL ESTIMATE", 90
    elif age_minutes <= 180:
        status, score = "RECENT MODEL ESTIMATE", 75
    elif age_minutes <= 360:
        status, score = "AGING MODEL ESTIMATE", 50
    else:
        status, score = "STALE - VERIFY", 20
    return {
        "status": status,
        "score": score,
        "age_minutes": age_minutes,
        "basis": f"Provider-supplied {weather.get('provider', 'provider')} estimate; no local station observation attached",
    }


@router.get("/health")
async def health():
    return {"status": "ok", "service": "SIFWAKU HeatWatch", "phase": "weather dashboard and indicative screening"}


@router.get("/api-sources")
async def api_sources(
    lat: float = Query(None),
    lon: float = Query(None),
):
    """
    Run live connectivity tests for every registered provider.
    Do NOT mark available merely because a website exists.
    """
    lat = lat if lat is not None else settings.default_latitude
    lon = lon if lon is not None else settings.default_longitude
    results = []

    for wp in get_weather_providers():
        tr = await wp.test_connectivity(lat, lon)
        results.append(
            {
                "source": tr.api_name,
                "type": "weather",
                "endpoint": tr.endpoint,
                "http_status": tr.http_status,
                "response_time_ms": tr.response_time_ms,
                "authentication_required": tr.authentication_required,
                "rate_limit_info": tr.rate_limit_info,
                "data_availability": tr.data_availability,
                "variables_returned": tr.variables_returned,
                "units": tr.units,
                "geographic_coverage": tr.geographic_coverage,
                "historical_coverage": tr.historical_coverage,
                "last_successful_request": tr.last_successful_request,
                "error_message": tr.error_message,
                "status": tr.status.value,
                "raw_response_preview": tr.raw_response_preview,
                # Summary columns for API Sources table
                "historical": "Yes" if "1940" in (tr.historical_coverage or "") or "History" in (tr.historical_coverage or "") else "See notes",
                "forecast": "Yes" if tr.status.value in ("AVAILABLE", "PARTIALLY_AVAILABLE") else "No",
                "real_time": "Yes" if tr.status.value == "AVAILABLE" else "Limited",
                "zambia": "Yes" if "Global" in (tr.geographic_coverage or "") or "Zambia" in (tr.geographic_coverage or "") else "Unknown",
                "api_key": "Required" if tr.authentication_required else "Not required",
            }
        )

    for cp in get_climate_providers():
        tr = await cp.test_connectivity()
        results.append(
            {
                "source": tr.api_name,
                "type": "climate/ENSO",
                "endpoint": tr.endpoint,
                "http_status": tr.http_status,
                "response_time_ms": tr.response_time_ms,
                "authentication_required": tr.authentication_required,
                "rate_limit_info": tr.rate_limit_info,
                "data_availability": tr.data_availability,
                "variables_returned": tr.variables_returned,
                "units": tr.units,
                "geographic_coverage": tr.geographic_coverage,
                "historical_coverage": tr.historical_coverage,
                "last_successful_request": tr.last_successful_request,
                "error_message": tr.error_message,
                "status": tr.status.value,
                "raw_response_preview": tr.raw_response_preview,
                "historical": "Yes (1950–present)",
                "forecast": "No (index, not weather forecast)",
                "real_time": "Monthly update",
                "zambia": "Global index (relevant to Zambia climate)",
                "api_key": "Not required",
            }
        )

    return {
        "tested_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "location": {"latitude": lat, "longitude": lon},
        "sources": results,
    }


@router.post("/api-lab/test")
async def api_lab_test(
    provider: str = Query(..., description="Open-Meteo | OpenWeatherMap | NOAA CPC ONI"),
    data_type: str = Query("current", description="current | forecast | historical | enso"),
    latitude: float = Query(None),
    longitude: float = Query(None),
    location_name: str = Query("Lusaka"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    days: int = Query(3),
    store: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    API Laboratory — full pipeline:
    REQUEST → HTTP STATUS → RESPONSE TIME → RAW → PARSED → VALIDATION → STORAGE
    """
    lat = latitude if latitude is not None else settings.default_latitude
    lon = longitude if longitude is not None else settings.default_longitude
    pipeline: dict = {
        "provider": provider,
        "data_type": data_type,
        "request": {
            "latitude": lat,
            "longitude": lon,
            "location_name": location_name,
            "start_date": start_date,
            "end_date": end_date,
            "days": days,
        },
        "http_status": None,
        "response_time_ms": None,
        "raw_response": None,
        "parsed_data": None,
        "validation": None,
        "database_storage": None,
        "error": None,
    }

    try:
        if data_type == "enso" or provider == "NOAA CPC ONI":
            cp = get_climate_provider("NOAA CPC ONI")
            tr = await cp.test_connectivity()
            pipeline["http_status"] = tr.http_status
            pipeline["response_time_ms"] = tr.response_time_ms
            pipeline["raw_response"] = tr.raw_response_preview
            series, err = await cp.get_enso_series()
            if err:
                pipeline["error"] = err
                pipeline["database_storage"] = "SKIPPED"
            else:
                latest = series[-1] if series else None
                pipeline["parsed_data"] = {
                    "records": len(series),
                    "latest": {
                        "date": latest.date if latest else None,
                        "enso_index": latest.enso_index if latest else None,
                        "enso_phase": latest.enso_phase if latest else None,
                        "source": latest.source if latest else None,
                    },
                }
                pipeline["validation"] = {"status": "OK", "note": "Index values within expected ±3 °C range checked implicitly"}
                if store and series:
                    n = store_enso(db, series)
                    pipeline["database_storage"] = f"STORED {n} new ENSO records (duplicates skipped)"
                else:
                    pipeline["database_storage"] = "NOT REQUESTED"
            log_api_request(db, cp.name, tr.endpoint, tr.http_status, tr.response_time_ms, tr.http_status == 200, tr.error_message)
            return pipeline

        # Weather paths
        wp = get_weather_provider(provider if provider != "NOAA CPC ONI" else "Open-Meteo")
        tr = await wp.test_connectivity(lat, lon)
        pipeline["http_status"] = tr.http_status
        pipeline["response_time_ms"] = tr.response_time_ms
        pipeline["raw_response"] = tr.raw_response_preview

        if data_type == "current":
            obs, err = await wp.get_current(lat, lon, location_name)
            if err or not obs:
                pipeline["error"] = err or "No observation returned"
                pipeline["database_storage"] = "SKIPPED"
            else:
                vr = validate_weather(obs)
                pipeline["parsed_data"] = {
                    "timestamp": obs.timestamp.isoformat(),
                    "location": obs.location,
                    "latitude": obs.latitude,
                    "longitude": obs.longitude,
                    "temperature_c": obs.temperature_c,
                    "humidity_percent": obs.humidity_percent,
                    "rainfall_mm": obs.rainfall_mm,
                    "wind_speed_ms": obs.wind_speed_ms,
                    "pressure_hpa": obs.pressure_hpa,
                    "source": obs.source,
                }
                pipeline["validation"] = {
                    "is_valid": vr.is_valid,
                    "flags": vr.flags,
                    "reason": vr.reason or "All checks passed",
                }
                if store:
                    loc = get_or_create_location(db, location_name, lat, lon)
                    row, status = store_observation(db, loc, obs)
                    pipeline["database_storage"] = status
                    pipeline["observation_id"] = row.id if row else None
                else:
                    pipeline["database_storage"] = "NOT REQUESTED"

        elif data_type == "forecast":
            items, err = await wp.get_forecast(lat, lon, location_name, days=days)
            if err:
                pipeline["error"] = err
                pipeline["database_storage"] = "SKIPPED"
            else:
                pipeline["parsed_data"] = {
                    "count": len(items),
                    "sample": [
                        {
                            "timestamp": i.timestamp.isoformat(),
                            "temperature_c": i.temperature_c,
                            "humidity_percent": i.humidity_percent,
                            "rainfall_mm": i.rainfall_mm,
                            "source": i.source,
                        }
                        for i in items[:6]
                    ],
                }
                pipeline["validation"] = {"status": "Batch validated on store"}
                if store and items:
                    loc = get_or_create_location(db, location_name, lat, lon)
                    n = store_forecasts(db, loc, items)
                    pipeline["database_storage"] = f"STORED {n} forecast rows"
                else:
                    pipeline["database_storage"] = "NOT REQUESTED"

        elif data_type == "historical":
            if not start_date or not end_date:
                pipeline["error"] = "start_date and end_date required (YYYY-MM-DD)"
                return pipeline
            items, err = await wp.get_historical(lat, lon, start_date, end_date, location_name)
            if err:
                pipeline["error"] = err
                pipeline["database_storage"] = "SKIPPED"
            else:
                pipeline["parsed_data"] = {
                    "count": len(items),
                    "sample": [
                        {
                            "timestamp": i.timestamp.isoformat(),
                            "temperature_c": i.temperature_c,
                            "humidity_percent": i.humidity_percent,
                            "rainfall_mm": i.rainfall_mm,
                            "source": i.source,
                        }
                        for i in items[:10]
                    ],
                }
                pipeline["validation"] = {"status": "Batch validated on store"}
                if store and items:
                    loc = get_or_create_location(db, location_name, lat, lon)
                    stored = 0
                    for obs in items:
                        _, st = store_observation(db, loc, obs)
                        if st.startswith("STORED"):
                            stored += 1
                    pipeline["database_storage"] = f"STORED {stored} historical observations"
                else:
                    pipeline["database_storage"] = "NOT REQUESTED"
        else:
            pipeline["error"] = f"Unknown data_type: {data_type}"

        log_api_request(
            db,
            wp.name,
            tr.endpoint,
            tr.http_status,
            tr.response_time_ms,
            tr.http_status == 200 if tr.http_status else False,
            tr.error_message,
        )
    except Exception as e:
        pipeline["error"] = f"Unhandled: {e}"

    return pipeline


@router.get("/current")
async def current_conditions(
    latitude: float = Query(None),
    longitude: float = Query(None),
    location_name: str = Query("Lusaka"),
    provider: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    lat = latitude if latitude is not None else settings.default_latitude
    lon = longitude if longitude is not None else settings.default_longitude
    result = await ingest_current(db, lat, lon, location_name, provider)
    return result


@router.get("/enso/latest")
async def enso_latest(db: Session = Depends(get_db)):
    cp = get_climate_provider()
    latest, err = await cp.get_latest_enso()
    if err or not latest:
        # Try DB cache
        row = db.query(ENSOObservation).order_by(ENSOObservation.id.desc()).first()
        if row:
            return {
                "ok": True,
                "from_cache": True,
                "date": row.date_label,
                "enso_index": row.enso_index,
                "enso_phase": row.enso_phase,
                "source": row.source,
            }
        return {"ok": False, "error": err or "No ENSO data"}
    # Optionally persist
    store_enso(db, [latest])
    return {
        "ok": True,
        "from_cache": False,
        "date": latest.date,
        "enso_index": latest.enso_index,
        "enso_phase": latest.enso_phase,
        "source": latest.source,
    }


@router.get("/risk")
async def heat_risk(
    latitude: float = Query(None),
    longitude: float = Query(None),
    location_name: str = Query("Lusaka"),
    provider: Optional[str] = Query(None),
    store_assessment: bool = Query(False, description="Persist this assessment for later analysis"),
    db: Session = Depends(get_db),
):
    """Compute baseline heat risk from live (or latest) observation + ENSO context."""
    lat = latitude if latitude is not None else settings.default_latitude
    lon = longitude if longitude is not None else settings.default_longitude

    weather = await ingest_current(db, lat, lon, location_name, provider)
    if not weather.get("ok"):
        return {
            "ok": False,
            "weather_ok": False,
            "weather_error": weather.get("error") or "No valid weather observation available",
            "observation": weather.get("data"),
            "observation_provider": weather.get("provider"),
            "data_quality": _observation_quality(weather),
            "enso_ok": False,
            "risk": None,
            "disclaimer": "Warning withheld because the latest weather observation did not pass validation.",
        }
    enso = await enso_latest(db)

    temp = weather.get("data", {}).get("temperature_c") if weather.get("ok") else None
    hum = weather.get("data", {}).get("humidity_percent") if weather.get("ok") else None
    wind = weather.get("data", {}).get("wind_speed_ms") if weather.get("ok") else None
    rain = weather.get("data", {}).get("rainfall_mm") if weather.get("ok") else None

    enso_phase = enso.get("enso_phase") if enso.get("ok") else None
    enso_index = enso.get("enso_index") if enso.get("ok") else None

    result = compute_risk_score(
        temperature_c=temp,
        humidity_percent=hum,
        wind_speed_ms=wind,
        rainfall_mm=rain,
        consecutive_hot_days=None,  # needs historical series — Phase 5+
        enso_phase=enso_phase,
        enso_index=enso_index,
    )
    d = result_to_dict(result)

    if store_assessment:
        loc = get_or_create_location(db, location_name, lat, lon)
        ra = RiskAssessment(
            location_id=loc.id,
            risk_score=result.risk_score,
            risk_level=result.risk_level,
            heat_index_c=result.heat_index_c,
            temperature_c=result.temperature_c,
            humidity_percent=result.humidity_percent,
            consecutive_hot_days=result.consecutive_hot_days,
            enso_phase=result.enso_phase,
            enso_index=result.enso_index,
            methodology_note=result.methodology_note,
            components_json=json.dumps(result.components),
        )
        db.add(ra)
        db.commit()

    return {
        "ok": True,
        "weather_ok": weather.get("ok"),
        "weather_error": weather.get("error"),
        "observation": weather.get("data"),
        "observation_provider": weather.get("provider"),
        "data_quality": _observation_quality(weather),
        "enso_ok": enso.get("ok"),
        "risk": d,
        "disclaimer": result.methodology_note,
    }


@router.get("/forecast")
async def forecast(
    latitude: float = Query(None),
    longitude: float = Query(None),
    location_name: str = Query("Lusaka"),
    days: int = Query(3, ge=1, le=16),
    provider: Optional[str] = Query(None),
    store: bool = Query(False, description="Persist this forecast snapshot for later verification"),
    db: Session = Depends(get_db),
):
    lat = latitude if latitude is not None else settings.default_latitude
    lon = longitude if longitude is not None else settings.default_longitude
    wp = get_weather_provider(provider)
    items, err = await wp.get_forecast(lat, lon, location_name, days=days)
    if err:
        return {"ok": False, "error": err, "provider": wp.name}
    valid_items = [item for item in items if validate_weather(item).is_valid]
    invalid_count = len(items) - len(valid_items)
    stored_count = 0
    if store and valid_items:
        loc = get_or_create_location(db, location_name, lat, lon)
        stored_count = store_forecasts(db, loc, valid_items)
    return {
        "ok": True,
        "provider": wp.name,
        "requested_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": len(valid_items),
        "invalid_count": invalid_count,
        "stored_count": stored_count,
        "forecast": [
            {
                "timestamp": i.timestamp.isoformat(),
                "temperature_c": i.temperature_c,
                "humidity_percent": i.humidity_percent,
                "rainfall_mm": i.rainfall_mm,
                "wind_speed_ms": i.wind_speed_ms,
                "source": i.source,
            }
            for i in valid_items
        ],
    }


@router.get("/history")
async def history(
    latitude: float = Query(None),
    longitude: float = Query(None),
    location_name: str = Query("Lusaka"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    provider: Optional[str] = Query(None),
    store: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Return a validated daily historical series for pattern analysis."""
    lat = latitude if latitude is not None else settings.default_latitude
    lon = longitude if longitude is not None else settings.default_longitude
    end = end_date or datetime.utcnow().date().isoformat()
    start = start_date or (datetime.utcnow().date() - timedelta(days=30)).isoformat()
    wp = get_weather_provider(provider)
    items, err = await wp.get_historical(lat, lon, start, end, location_name)
    if err:
        return {"ok": False, "error": err, "provider": wp.name}

    valid_items = [item for item in items if validate_weather(item).is_valid]
    invalid_count = len(items) - len(valid_items)
    stored_count = 0
    if store and valid_items:
        loc = get_or_create_location(db, location_name, lat, lon)
        for item in valid_items:
            _, status = store_observation(db, loc, item)
            if status.startswith("STORED"):
                stored_count += 1

    return {
        "ok": True,
        "provider": wp.name,
        "location": location_name,
        "start_date": start,
        "end_date": end,
        "count": len(valid_items),
        "invalid_count": invalid_count,
        "stored_count": stored_count,
        "observations": [
            {
                "timestamp": item.timestamp.isoformat(),
                "temperature_c": item.temperature_c,
                "temperature_min_c": item.temperature_min_c,
                "humidity_percent": item.humidity_percent,
                "rainfall_mm": item.rainfall_mm,
                "wind_speed_ms": item.wind_speed_ms,
                "source": item.source,
            }
            for item in valid_items
        ],
    }
