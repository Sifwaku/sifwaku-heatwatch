"""
Open-Meteo weather provider.
Official docs: https://open-meteo.com/en/docs
No API key required for non-commercial use.
Rate limit: ~10,000 calls/day non-commercial.
Attribution required (CC BY 4.0).
"""
import time
from datetime import datetime
from typing import Any, Optional

import httpx

from backend.providers.base import (
    APITestResult,
    NormalizedWeather,
    ProviderStatus,
    WeatherProvider,
)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class OpenMeteoProvider(WeatherProvider):
    name = "Open-Meteo"

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    async def test_connectivity(
        self,
        latitude: float,
        longitude: float,
    ) -> APITestResult:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,surface_pressure",
            "hourly": "temperature_2m",
            "forecast_days": 1,
        }
        start = time.perf_counter()
        result = APITestResult(
            api_name=self.name,
            endpoint=FORECAST_URL,
            authentication_required=False,
            rate_limit_info="~10,000 calls/day non-commercial; attribution required",
            geographic_coverage="Global (including Zambia)",
            historical_coverage="ERA5 from 1940 via archive-api.open-meteo.com",
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(FORECAST_URL, params=params)
            elapsed = (time.perf_counter() - start) * 1000
            result.http_status = resp.status_code
            result.response_time_ms = round(elapsed, 1)
            result.raw_response_preview = resp.text[:800]

            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current", {})
                result.variables_returned = list(current.keys())
                result.units = data.get("current_units", {})
                result.data_availability = "Current + forecast available"
                result.last_successful_request = datetime.utcnow().isoformat() + "Z"
                result.status = ProviderStatus.AVAILABLE
            elif resp.status_code == 429:
                result.error_message = "Rate limit exceeded (429). Free tier daily limit reached."
                result.status = ProviderStatus.PARTIALLY_AVAILABLE
                result.data_availability = "Endpoint live but rate-limited"
            else:
                result.error_message = f"HTTP {resp.status_code}: {resp.text[:300]}"
                result.status = ProviderStatus.UNAVAILABLE
        except httpx.TimeoutException:
            result.error_message = "Request timed out"
            result.status = ProviderStatus.UNAVAILABLE
        except Exception as e:
            result.error_message = str(e)
            result.status = ProviderStatus.UNAVAILABLE
        return result

    def _parse_current(
        self,
        data: dict[str, Any],
        latitude: float,
        longitude: float,
        location_name: str,
    ) -> NormalizedWeather:
        current = data.get("current", {})
        ts_str = current.get("time")
        try:
            ts = datetime.fromisoformat(ts_str) if ts_str else datetime.utcnow()
        except ValueError:
            ts = datetime.utcnow()

        # Open-Meteo wind_speed_10m is often km/h; convert to m/s when units say km/h
        wind = current.get("wind_speed_10m")
        units = data.get("current_units", {})
        wind_unit = units.get("wind_speed_10m", "km/h")
        wind_ms = None
        if wind is not None:
            if "km" in str(wind_unit).lower():
                wind_ms = round(float(wind) / 3.6, 3)
            else:
                wind_ms = float(wind)

        return NormalizedWeather(
            timestamp=ts,
            location=location_name or f"{latitude},{longitude}",
            latitude=latitude,
            longitude=longitude,
            temperature_c=current.get("temperature_2m"),
            humidity_percent=current.get("relative_humidity_2m"),
            rainfall_mm=current.get("precipitation"),
            wind_speed_ms=wind_ms,
            pressure_hpa=current.get("surface_pressure"),
            source=self.name,
            raw_payload=data,
        )

    async def get_current(
        self,
        latitude: float,
        longitude: float,
        location_name: str = "",
    ) -> tuple[Optional[NormalizedWeather], Optional[str]]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,surface_pressure,wind_direction_10m",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(FORECAST_URL, params=params)
            if resp.status_code == 429:
                return None, "Open-Meteo rate limit exceeded (429). Try again later."
            if resp.status_code != 200:
                return None, f"Open-Meteo HTTP {resp.status_code}: {resp.text[:200]}"
            data = resp.json()
            obs = self._parse_current(data, latitude, longitude, location_name)
            if obs.temperature_c is None:
                return None, "Open-Meteo returned no temperature_2m"
            return obs, None
        except httpx.TimeoutException:
            return None, "Open-Meteo request timed out"
        except Exception as e:
            return None, f"Open-Meteo error: {e}"

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        location_name: str = "",
        days: int = 3,
    ) -> tuple[list[NormalizedWeather], Optional[str]]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,surface_pressure",
            "forecast_days": min(max(days, 1), 16),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(FORECAST_URL, params=params)
            if resp.status_code == 429:
                return [], "Open-Meteo rate limit exceeded (429)"
            if resp.status_code != 200:
                return [], f"Open-Meteo HTTP {resp.status_code}"
            data = resp.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            results: list[NormalizedWeather] = []
            for i, t in enumerate(times):
                try:
                    ts = datetime.fromisoformat(t)
                except ValueError:
                    continue
                wind = hourly.get("wind_speed_10m", [None])[i] if i < len(hourly.get("wind_speed_10m", [])) else None
                wind_ms = round(float(wind) / 3.6, 3) if wind is not None else None
                results.append(
                    NormalizedWeather(
                        timestamp=ts,
                        location=location_name or f"{latitude},{longitude}",
                        latitude=latitude,
                        longitude=longitude,
                        temperature_c=_safe_get(hourly, "temperature_2m", i),
                        humidity_percent=_safe_get(hourly, "relative_humidity_2m", i),
                        rainfall_mm=_safe_get(hourly, "precipitation", i),
                        wind_speed_ms=wind_ms,
                        pressure_hpa=_safe_get(hourly, "surface_pressure", i),
                        source=self.name,
                        raw_payload=None,
                    )
                )
            return results, None
        except Exception as e:
            return [], f"Open-Meteo forecast error: {e}"

    async def get_historical(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        location_name: str = "",
    ) -> tuple[list[NormalizedWeather], Optional[str]]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean,wind_speed_10m_max",
            "timezone": "auto",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(ARCHIVE_URL, params=params)
            if resp.status_code == 429:
                return [], "Open-Meteo archive rate limit exceeded (429)"
            if resp.status_code != 200:
                return [], f"Open-Meteo archive HTTP {resp.status_code}: {resp.text[:200]}"
            data = resp.json()
            daily = data.get("daily", {})
            times = daily.get("time", [])
            results: list[NormalizedWeather] = []
            for i, t in enumerate(times):
                try:
                    ts = datetime.fromisoformat(t)
                except ValueError:
                    continue
                # Use max temp as representative daily temperature for risk calc
                tmax = _safe_get(daily, "temperature_2m_max", i)
                tmin = _safe_get(daily, "temperature_2m_min", i)
                results.append(
                    NormalizedWeather(
                        timestamp=ts,
                        location=location_name or f"{latitude},{longitude}",
                        latitude=latitude,
                        longitude=longitude,
                        temperature_c=tmax,
                        temperature_min_c=tmin,
                        humidity_percent=_safe_get(daily, "relative_humidity_2m_mean", i),
                        rainfall_mm=_safe_get(daily, "precipitation_sum", i),
                        wind_speed_ms=(
                            round(float(w) / 3.6, 3)
                            if (w := _safe_get(daily, "wind_speed_10m_max", i)) is not None
                            else None
                        ),
                        source=self.name,
                        raw_payload=None,
                    )
                )
            return results, None
        except Exception as e:
            return [], f"Open-Meteo historical error: {e}"


def _safe_get(d: dict, key: str, idx: int) -> Optional[float]:
    arr = d.get(key, [])
    if idx < len(arr) and arr[idx] is not None:
        try:
            return float(arr[idx])
        except (TypeError, ValueError):
            return None
    return None
