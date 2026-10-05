# SIFWAKU HeatWatch

**Zambia weather dashboard and heat-risk screening tool**

Visitors can select a Zambian province, district or town, view provider-supplied current conditions and a seven-day outlook, and explore historical weather. The field and district brief shows daily rainfall and temperature estimates with coverage notes, and can be printed or downloaded as CSV. The heat-risk screen is illustrative; it is not a probability, a medical assessment, or an official warning. Weather estimates are not local station observations.

---

## 1. Problem

Heat extremes affect health, agriculture, and energy demand in Zambia and the wider southern African region. Climate context (including ENSO / El Niño) can modulate risk, but **El Niño is not proof that a local heatwave will occur**. A usable early-warning system must first prove that required data can be obtained reliably, with clear provenance and honest handling of missing or failed sources.

## 2. Research question

Which public APIs can supply, for Zambia (starting with Lusaka):

- near-real-time and historical temperature, humidity, wind, rainfall, and pressure;
- ENSO indices and phase;
- enough history to support transparent heat-risk indicators and (later) time-aware models—

and under what limits (auth, rate limits, geographic/historical coverage)?

## 3. System architecture

```
API sources
    ↓
API connectivity tests
    ↓
Raw API responses
    ↓
Data validation
    ↓
Data normalization
    ↓
Database (provenance preserved)
    ↓
Feature engineering
    ↓
Heat-risk calculation (baseline, non-ML)
    ↓
Dashboard
    ↓
Early-warning output (later phases)
```

Separation of concerns:

| Layer | Role |
|-------|------|
| `providers/` | Adapters per API (WeatherProvider / ClimateProvider) |
| `services/` | Validation, ingestion |
| `database/` | Relational storage with source + timestamp |
| `analytics/` | Transparent heat-risk score |
| `api/` | FastAPI routes (server-side only for keys) |
| `frontend/` | Weather dashboard, historical analysis, and provider diagnostics |

The province map uses geoBoundaries' Zambia ADM1 boundaries for 2020, sourced from the Zambia Data Hub and released under CC BY 4.0. The dashboard includes attribution beside the map.

The map overlays NASA GPM IMERG satellite precipitation tiles on those boundaries, with the latest available frame, a recent-frame slider, playback, and an official colour legend. The frames are 30-minute satellite estimates and may be several hours behind; they are not ground radar or station readings. The map requests only the Zambia tiles it needs and keeps the provider timestamp visible.

### Farmer and district planning brief

The dashboard groups the seven-day point forecast into calendar days, showing estimated rainfall, temperature range, and how many hourly values were available. A partial day is labeled; rainfall is a full-day total only when all 24 hourly forecast values exist. Use **Print / save brief** for a compact handout or **Download daily CSV** for spreadsheet workflows. The CSV retains location coordinates, provider, generation time, and a plain-language data limitation on every row.

This is a situational-awareness aid. A selected district forecast is sampled at its reference coordinates; it is not a district-wide average or field-specific soil/weather measurement. It does not contain rainfall probabilities, crop-stage advice, official Zambian warnings, or verified accuracy scores. Farmers should compare it with field conditions and local reports. Government use should remain exploratory until official agency data, station observations, data-sharing arrangements, and forecast verification are in place.

## 4. APIs investigated

See **[docs/API_AVAILABILITY_REPORT.md](docs/API_AVAILABILITY_REPORT.md)** for full live-test results.

| Provider | Role | Key? | Status (live test) |
|----------|------|------|---------------------|
| Open-Meteo | Weather current / forecast / historical | No | Endpoint live; 429 possible on free tier |
| NOAA CPC ONI | ENSO index 1950–present | No | AVAILABLE |
| OpenWeatherMap | Weather (optional) | Yes | AUTH REQUIRED |

## 5. Variables obtained

Standard weather schema after normalization:

- `timestamp`, `location`, `latitude`, `longitude`
- `temperature_c`, `humidity_percent`, `rainfall_mm`
- `wind_speed_ms`, `pressure_hpa`, `source`
- Original payload retained for audit where available

ENSO schema:

- `date`, `enso_index`, `enso_phase`, `source`

## 6. API limitations

- Open-Meteo free tier rate limits (~10k/day non-commercial); attribution required.
- OpenWeatherMap historical is paid; free key needed for current/forecast.
- No free verified “official Zambia heatwave event list” API; events derived later from temperature series.
- ENSO is a **context** variable only.

## 7. Data dictionary (core)

| Field | Unit | Notes |
|-------|------|--------|
| temperature_c | °C | Observed or daily max for historical aggregates |
| humidity_percent | % | 0–100 expected |
| rainfall_mm | mm | Period total as provided by API |
| wind_speed_ms | m/s | Converted from km/h when needed |
| pressure_hpa | hPa | Surface / MSL as provided |
| enso_index | °C anomaly | ONI ANOM |
| enso_phase | text | El Niño / La Niña / Neutral (±0.5 °C) |
| risk_score | 0–100 | Baseline model — not medical |
| risk_level | text | LOW / MODERATE / HIGH / EXTREME (illustrative) |

## 8. Database design

SQLite by default (`data/sifwaku_heatwatch.db`). Tables:

- `locations`, `weather_observations`, `weather_forecasts`
- `enso_observations`, `heatwave_events`
- `api_sources`, `api_requests`, `risk_assessments`

Every observation stores **source** and **timestamp** (provenance).

## 9. Heat-risk methodology

Transparent baseline (no ML):

- Heat index (Rothfusz / NWS-style) when T and RH available
- Consecutive hot days, night recovery, humidity/wind/rain context
- ENSO contributes at most a small context term

**Not** claimed as medically authoritative or as an official warning.  
See `backend/analytics/heat_risk.py`.

## 10. ML methodology (Phase 9 only)

Deferred until enough timestamped forecasts can be compared with local observations.  
Planned: time-aware split, logistic / RF / XGBoost, metrics Precision/Recall/F1/ROC-AUC/Brier, no random split leakage.

## 11. Validation

Range checks on T, RH, rain, wind, pressure, coordinates; flags stored, not silent deletes.  
Duplicates keyed by location + timestamp + source.

## 12. Limitations

- Student project; not operational WMO/health service.
- Free API rate limits and occasional outages.
- The dashboard uses provider weather estimates; no local station observations are attached yet.
- Heat-risk and rain/wind/cold thresholds are illustrative screens, not calibrated probabilities or official warnings.
- Historical weather is provider-estimated and cannot independently validate past forecasts.
- The page refresh interval does not guarantee equally fresh provider data; check the observation timestamp.
- ENSO–local weather association needs more local history before strong claims.

To build a trustworthy prediction service, collect timestamped forecasts and local observations, compare them by location and forecast lead time, and publish accuracy and uncertainty before adding multiple sources, fallbacks, or performance-backed alerts.

## 13. Installation

```powershell
cd sifwaku-heatwatch
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

On macOS or Linux, activate with `source .venv/bin/activate` and copy the settings file with `cp .env.example .env`.

## 14. API-key configuration

| Variable | Required? |
|----------|-----------|
| `OPENWEATHERMAP_API_KEY` | Only for OpenWeatherMap provider |
| `VISUALCROSSING_API_KEY` | Optional future |
| Open-Meteo / NOAA ONI | No key |

Never put keys in frontend JavaScript. Never commit `.env`.

## 15. Running the project

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

Open:

- http://localhost:8000/ — Weather dashboard  
- http://localhost:8000/history — Historical analysis  
- http://localhost:8000/api-sources-page — Live provider status  
- http://localhost:8000/api-lab — Provider diagnostics  
- http://localhost:8000/docs — OpenAPI  

The dashboard refreshes about every 15 minutes while its page is open. Provider update timing and availability can vary; the brief's generation time is when this service requested the estimates, not when the provider issued its forecast.

### Development order (followed)

1. API discovery → 2. Connectivity testing → 3. Normalization → 4. Database →  
5. Historical collection → 6. Baseline risk → 7. Dashboard → 8. ENSO analysis →  
9. ML (blocked until data proven) → 10. Alerts → 11. Sensors  

## 16. Free hosting

GitHub stores the source code; it does not run this Python API. The included `render.yaml` is configured for a **free Render web service**:

1. In Render, choose **New → Blueprint**, connect the `Sifwaku/sifwaku-heatwatch` GitHub repository, and deploy the `render.yaml` file.
2. Confirm the service plan is **Free** before creating it. The app uses no paid add-ons or persistent disk.
3. Once deployment finishes, open the service's `onrender.com` URL. `/` redirects to the dashboard; `/api/health` reports whether the API is responding.

This free setup is for a public preview. Render may spin the service down after 15 minutes without traffic; the next visit can take about a minute to load. Its filesystem is temporary, so the SQLite database (including locally saved history) can be erased when the service restarts, sleeps, or is redeployed. Weather is fetched from the provider when requested, so a sleeping service does not refresh data in the background. These limits make it unsuitable for dependable alerts or official operational decisions.

The included `.python-version` pins the service to Python 3.12, which matches the project's pinned scientific Python dependencies. Open-Meteo works without a key. Optional provider keys should be added through the host's secret settings, never committed to the repository. For persistent records and continuous availability, move to a paid host or managed database when funding is available, then add backups, monitoring, and forecast verification.

---

**Licence note:** Open-Meteo data requires attribution under CC BY 4.0. NOAA CPC ONI is public US government climate data. Use other commercial APIs under their respective terms.
