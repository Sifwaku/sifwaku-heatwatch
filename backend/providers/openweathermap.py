"""
OpenWeatherMap provider (optional — requires API key).
Docs: https://openweathermap.org/api
Free tier: current + 5-day/3-hour forecast. Historical is paid.
"""
import time
from datetime import datetime
from typing import Optional

import httpx

from backend.config import get_settings
from backend.providers.base import (
    APITestResult,
    NormalizedWeather,
    ProviderStatus,
    WeatherProvider,
)

BASE = "https://api.openweathermap.org/data/2.5"


class OpenWeatherMapProvider(WeatherProvider):
    name = "OpenWeatherMap"

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self.api_key = get_settings().openweathermap_api_key

    async def test_connectivity(
        self,
        latitude: float,
        longitude: float,
    ) -> APITestResult:
        result = APITestResult(
            api_name=self.name,
            endpoint=f"{BASE}/weather",
            authentication_required=True,
            rate_limit_info="Free tier limited; see openweathermap.org/price",
            geographic_coverage="Global",
            historical_coverage="Paid plans only for History API",
        )
        if not self.api_key:
            result.status = ProviderStatus.AUTH_REQUIRED
            result.error_message = "OPENWEATHERMAP_API_KEY not set in environment"
            result.data_availability = "Cannot test without API key"
            return result

        params = {"lat": latitude, "lon": longitude, "appid": self.api_key, "units": "metric"}
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{BASE}/weather", params=params)
            result.http_status = resp.status_code
            result.response_time_ms = round((time.perf_counter() - start) * 1000, 1)
            result.raw_response_preview = resp.text[:600]
            if resp.status_code == 200:
                data = resp.json()
                main = data.get("main", {})
                result.variables_returned = list(main.keys()) + ["wind", "weather"]
                result.units = {"temp": "°C", "humidity": "%", "pressure": "hPa"}
                result.data_availability = "Current weather available (free tier)"
                result.last_successful_request = datetime.utcnow().isoformat() + "Z"
                result.status = ProviderStatus.AVAILABLE
            elif resp.status_code in (401, 403):
                result.status = ProviderStatus.AUTH_REQUIRED
                result.error_message = "Invalid or unauthorized API key"
            else:
                result.status = ProviderStatus.UNAVAILABLE
                result.error_message = f"HTTP {resp.status_code}"
        except Exception as e:
            result.error_message = str(e)
            result.status = ProviderStatus.UNAVAILABLE
        return result

    async def get_current(
        self,
        latitude: float,
        longitude: float,
        location_name: str = "",
    ) -> tuple[Optional[NormalizedWeather], Optional[str]]:
        if not self.api_key:
            return None, "OPENWEATHERMAP_API_KEY not configured"
        params = {"lat": latitude, "lon": longitude, "appid": self.api_key, "units": "metric"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{BASE}/weather", params=params)
            if resp.status_code != 200:
                return None, f"OpenWeatherMap HTTP {resp.status_code}"
            data = resp.json()
            main = data.get("main", {})
            wind = data.get("wind", {})
            rain = data.get("rain", {})
            return NormalizedWeather(
                timestamp=datetime.utcfromtimestamp(data.get("dt", time.time())),
                location=location_name or data.get("name", ""),
                latitude=latitude,
                longitude=longitude,
                temperature_c=main.get("temp"),
                humidity_percent=main.get("humidity"),
                rainfall_mm=rain.get("1h") or rain.get("3h"),
                wind_speed_ms=wind.get("speed"),
                wind_direction_deg=wind.get("deg"),
                pressure_hpa=main.get("pressure"),
                source=self.name,
                raw_payload=data,
            ), None
        except Exception as e:
            return None, str(e)

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        location_name: str = "",
        days: int = 3,
    ) -> tuple[list[NormalizedWeather], Optional[str]]:
        if not self.api_key:
            return [], "OPENWEATHERMAP_API_KEY not configured"
        params = {"lat": latitude, "lon": longitude, "appid": self.api_key, "units": "metric"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{BASE}/forecast", params=params)
            if resp.status_code != 200:
                return [], f"OpenWeatherMap forecast HTTP {resp.status_code}"
            data = resp.json()
            results = []
            for item in data.get("list", [])[: days * 8]:  # 3h steps
                main = item.get("main", {})
                wind = item.get("wind", {})
                rain = item.get("rain", {})
                results.append(
                    NormalizedWeather(
                        timestamp=datetime.utcfromtimestamp(item.get("dt", 0)),
                        location=location_name,
                        latitude=latitude,
                        longitude=longitude,
                        temperature_c=main.get("temp"),
                        humidity_percent=main.get("humidity"),
                        rainfall_mm=rain.get("3h"),
                        wind_speed_ms=wind.get("speed"),
                        pressure_hpa=main.get("pressure"),
                        source=self.name,
                    )
                )
            return results, None
        except Exception as e:
            return [], str(e)

    async def get_historical(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        location_name: str = "",
    ) -> tuple[list[NormalizedWeather], Optional[str]]:
        return [], "NOT AVAILABLE FROM THIS PROVIDER (OpenWeatherMap History API is paid)"
