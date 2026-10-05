"""
NOAA CPC Oceanic Niño Index (ONI) provider.
Official data: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
No authentication required. Public domain climate index.
Phase derived from anomaly thresholds (±0.5 °C) per NOAA convention.
"""
import time
from typing import Optional

import httpx

from backend.providers.base import (
    APITestResult,
    ClimateProvider,
    NormalizedENSO,
    ProviderStatus,
)

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"


def _phase_from_anom(anom: float) -> str:
    if anom >= 0.5:
        return "El Niño"
    if anom <= -0.5:
        return "La Niña"
    return "Neutral"


class NOAAENSOProvider(ClimateProvider):
    name = "NOAA CPC ONI"

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self._cache: list[NormalizedENSO] = []
        self._cache_time: Optional[float] = None
        self._cache_ttl = 3600  # 1 hour

    async def _fetch_raw(self) -> tuple[Optional[str], Optional[str]]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(ONI_URL)
            if resp.status_code != 200:
                return None, f"NOAA ONI HTTP {resp.status_code}"
            return resp.text, None
        except httpx.TimeoutException:
            return None, "NOAA ONI request timed out"
        except Exception as e:
            return None, f"NOAA ONI error: {e}"

    def _parse_oni_text(self, text: str) -> list[NormalizedENSO]:
        """
        Parse CPC oni.ascii.txt format:
        SEAS  YR   TOTAL   ANOM
         DJF 1950  25.01  -1.32
        ...
        """
        rows: list[NormalizedENSO] = []
        lines = text.strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.upper().startswith("SEAS"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            seas, yr, total, anom = parts[0], parts[1], parts[2], parts[3]
            try:
                anom_f = float(anom)
                # Skip missing-value markers sometimes present as -99.9
                if anom_f < -90:
                    continue
                date_label = f"{yr}-{seas}"
                rows.append(
                    NormalizedENSO(
                        date=date_label,
                        enso_index=round(anom_f, 2),
                        enso_phase=_phase_from_anom(anom_f),
                        source=self.name,
                        raw_payload={
                            "seas": seas,
                            "year": int(yr),
                            "total": float(total),
                            "anom": anom_f,
                        },
                    )
                )
            except (ValueError, TypeError):
                continue
        return rows

    async def _ensure_cache(self) -> Optional[str]:
        now = time.time()
        if self._cache and self._cache_time and (now - self._cache_time) < self._cache_ttl:
            return None
        text, err = await self._fetch_raw()
        if err:
            return err
        self._cache = self._parse_oni_text(text or "")
        self._cache_time = now
        if not self._cache:
            return "NOAA ONI file parsed but no valid rows found"
        return None

    async def test_connectivity(self) -> APITestResult:
        start = time.perf_counter()
        result = APITestResult(
            api_name=self.name,
            endpoint=ONI_URL,
            authentication_required=False,
            rate_limit_info="Public text file; polite use expected",
            geographic_coverage="Global climate index (Niño 3.4 region)",
            historical_coverage="1950–present (monthly 3-month running mean)",
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(ONI_URL)
            elapsed = (time.perf_counter() - start) * 1000
            result.http_status = resp.status_code
            result.response_time_ms = round(elapsed, 1)
            result.raw_response_preview = resp.text[:600]

            if resp.status_code == 200:
                parsed = self._parse_oni_text(resp.text)
                result.variables_returned = ["SEAS", "YR", "TOTAL", "ANOM", "derived_phase"]
                result.units = {"ANOM": "°C", "TOTAL": "°C"}
                result.data_availability = f"{len(parsed)} seasonal records retrieved"
                result.last_successful_request = __import__("datetime").datetime.utcnow().isoformat() + "Z"
                result.status = ProviderStatus.AVAILABLE if parsed else ProviderStatus.PARTIALLY_AVAILABLE
                if not parsed:
                    result.error_message = "File retrieved but no parsable ONI rows"
            else:
                result.error_message = f"HTTP {resp.status_code}"
                result.status = ProviderStatus.UNAVAILABLE
        except Exception as e:
            result.error_message = str(e)
            result.status = ProviderStatus.UNAVAILABLE
        return result

    async def get_enso_series(
        self,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> tuple[list[NormalizedENSO], Optional[str]]:
        err = await self._ensure_cache()
        if err:
            return [], err
        series = self._cache
        if start_year is not None:
            series = [r for r in series if r.raw_payload and r.raw_payload.get("year", 0) >= start_year]
        if end_year is not None:
            series = [r for r in series if r.raw_payload and r.raw_payload.get("year", 9999) <= end_year]
        return series, None

    async def get_latest_enso(self) -> tuple[Optional[NormalizedENSO], Optional[str]]:
        err = await self._ensure_cache()
        if err:
            return None, err
        if not self._cache:
            return None, "No ENSO records available"
        return self._cache[-1], None
