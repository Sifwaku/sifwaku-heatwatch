"""
Abstract base classes for weather and climate providers.
The rest of the application depends only on these interfaces.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ProviderStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIALLY_AVAILABLE = "PARTIALLY_AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    AUTH_REQUIRED = "AUTHENTICATION_REQUIRED"


@dataclass
class APITestResult:
    """Result of a live API connectivity test. Never invent data."""
    api_name: str
    endpoint: str
    http_status: Optional[int] = None
    response_time_ms: Optional[float] = None
    authentication_required: bool = False
    rate_limit_info: str = "Unknown"
    data_availability: str = "Unknown"
    variables_returned: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    geographic_coverage: str = "Unknown"
    historical_coverage: str = "Unknown"
    last_successful_request: Optional[str] = None
    error_message: Optional[str] = None
    status: ProviderStatus = ProviderStatus.UNAVAILABLE
    raw_response_preview: Optional[str] = None


@dataclass
class NormalizedWeather:
    """Standard schema after normalization. Provenance preserved."""
    timestamp: datetime
    location: str
    latitude: float
    longitude: float
    temperature_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    humidity_percent: Optional[float] = None
    rainfall_mm: Optional[float] = None
    wind_speed_ms: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    pressure_hpa: Optional[float] = None
    source: str = ""
    raw_payload: Optional[dict[str, Any]] = None


@dataclass
class NormalizedENSO:
    """Standard ENSO schema."""
    date: str  # e.g. "2024-DJF" or "2024-01"
    enso_index: Optional[float] = None
    enso_phase: Optional[str] = None  # El Niño / La Niña / Neutral
    source: str = ""
    raw_payload: Optional[dict[str, Any]] = None


class WeatherProvider(ABC):
    """Abstract weather data provider."""

    name: str = "base"

    @abstractmethod
    async def test_connectivity(
        self,
        latitude: float,
        longitude: float,
    ) -> APITestResult:
        """Perform a real HTTP request and report status. Do not invent data."""
        ...

    @abstractmethod
    async def get_current(
        self,
        latitude: float,
        longitude: float,
        location_name: str = "",
    ) -> tuple[Optional[NormalizedWeather], Optional[str]]:
        """
        Returns (normalized observation, error_message).
        error_message is set when data cannot be obtained.
        """
        ...

    @abstractmethod
    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        location_name: str = "",
        days: int = 3,
    ) -> tuple[list[NormalizedWeather], Optional[str]]:
        ...

    @abstractmethod
    async def get_historical(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        location_name: str = "",
    ) -> tuple[list[NormalizedWeather], Optional[str]]:
        ...


class ClimateProvider(ABC):
    """Abstract climate / ENSO provider."""

    name: str = "base"

    @abstractmethod
    async def test_connectivity(self) -> APITestResult:
        ...

    @abstractmethod
    async def get_enso_series(
        self,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> tuple[list[NormalizedENSO], Optional[str]]:
        ...

    @abstractmethod
    async def get_latest_enso(self) -> tuple[Optional[NormalizedENSO], Optional[str]]:
        ...
