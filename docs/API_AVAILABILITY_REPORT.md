# SIFWAKU HeatWatch — API Availability Report (Phase 1)

**Date of live tests:** 2025-09-25 / 2026-09-26  
**Default location:** Lusaka, Zambia (−15.4167, 28.2833)  
**Rule:** No invented endpoints, keys, measurements, or data. Status comes from actual HTTP requests.

---

## Summary table

| Source | Variable / type | Historical | Forecast | Real-time | Zambia | API Key | Status |
|--------|-----------------|------------|----------|-----------|--------|---------|--------|
| Open-Meteo | Weather (temp, RH, wind, precip, pressure) | Yes (ERA5 from 1940) | Yes (up to 16 days) | Yes | Yes (global) | Not required | 🟡 PARTIALLY AVAILABLE (429 rate-limit observed during testing; endpoint live) |
| NOAA CPC ONI | ENSO index + derived phase | Yes (1950–present) | N/A (climate index) | Monthly | Global index | Not required | 🟢 AVAILABLE |
| OpenWeatherMap | Current + 5-day forecast | Paid only | Yes (free limited) | Yes | Yes | Required | ⚠️ AUTHENTICATION REQUIRED |

---

## 1. Open-Meteo

| Field | Value |
|-------|--------|
| Official docs | https://open-meteo.com/en/docs · https://open-meteo.com/en/docs/historical-weather-api |
| Endpoint (forecast) | `https://api.open-meteo.com/v1/forecast` |
| Endpoint (archive) | `https://archive-api.open-meteo.com/v1/archive` |
| Authentication | None (non-commercial) |
| Rate limits | ~10,000 calls/day non-commercial; CC BY 4.0 attribution required |
| Geographic coverage | Global, including Zambia |
| Historical coverage | ERA5 reanalysis from January 1940 (hourly/daily aggregates) |
| Forecast | Current + hourly up to 16 days |
| Variables | `temperature_2m` (°C), `relative_humidity_2m` (%), `precipitation` / `precipitation_sum` (mm), `wind_speed_10m` (km/h selectable), `surface_pressure` (hPa), wind direction, weather codes |
| Live test (2026-09-25) | HTTP **429** (daily free limit exceeded in test environment). Endpoint confirmed real. |
| Status | 🟡 PARTIALLY AVAILABLE |

---

## 2. NOAA Climate Prediction Center — Oceanic Niño Index (ONI)

| Field | Value |
|-------|--------|
| Official source | https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt |
| Documentation | https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php |
| Authentication | None |
| Rate limits | Public text file; polite use |
| Geographic coverage | Niño 3.4 region index (global climate relevance) |
| Historical coverage | 1950–present, seasonal (3-month running mean) |
| Variables | SEAS, YR, TOTAL (°C), ANOM (°C); phase derived: ≥0.5 El Niño, ≤−0.5 La Niña, else Neutral |
| Live test (2026-09-25) | HTTP **200**, response ~70 ms, valid rows parsed |
| Status | 🟢 AVAILABLE |

**Note:** NOAA has discussed Relative Oceanic Niño Index (RONI) as a successor metric; the classic ONI ASCII product remains publicly accessible and is used here for historical consistency.

---

## 3. OpenWeatherMap

| Field | Value |
|-------|--------|
| Official docs | https://openweathermap.org/api |
| Endpoint | `https://api.openweathermap.org/data/2.5/weather` |
| Authentication | API key required (`appid=`) |
| Free tier | Current weather + 5-day/3-hour forecast; historical is paid |
| Live test | HTTP **401** with invalid key (endpoint exists) |
| Status | ⚠️ AUTHENTICATION REQUIRED |

Set `OPENWEATHERMAP_API_KEY` in `.env` to enable.

---

## Variables vs system requirements

| Required | Open-Meteo | NOAA ONI | OpenWeatherMap free |
|----------|------------|----------|---------------------|
| Temperature | Yes | — | Yes |
| Relative humidity | Yes | — | Yes |
| Wind | Yes | — | Yes |
| Rainfall | Yes | — | Limited |
| Pressure | Yes | — | Yes |
| Forecast T/RH/precip | Yes | — | Yes (5-day) |
| Historical weather | Yes | — | Paid |
| ENSO index / phase | — | Yes | — |
| Named heatwave event catalogue (Zambia) | Derive from T | — | — |

**NOT AVAILABLE FROM verified free providers:** Official Zambia-only heatwave event lists with start/end dates published as a machine API. Events will be **derived** from temperature thresholds after historical data is collected (Phase 5), with clear methodology notes.

---

## Error handling verified in design

The system handles: 401, 403, 404, 429, 500, timeout, invalid JSON, missing variables, missing location, no historical data, API unavailable — without crashing the dashboard. Missing values are reported as unavailable, never invented.

---

## Recommendation for Phase 2+

1. Primary weather: **Open-Meteo** (no key, historical + forecast).  
2. Primary ENSO: **NOAA CPC ONI**.  
3. Optional backup: OpenWeatherMap when a free key is configured.  
4. Proceed to normalization, SQLite storage with provenance, and API Laboratory end-to-end tests before any ML.
