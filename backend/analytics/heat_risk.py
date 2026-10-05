"""
Transparent baseline heat-risk model.
NO machine learning. NO claim of medical authority.
Clearly distinguishes observed vs calculated vs model output.
"""
import json
import math
from dataclasses import asdict, dataclass
from typing import Optional


def _coerce_float(value: Optional[float], *, default: Optional[float] = None) -> Optional[float]:
    """Accept numeric strings and safely reject invalid values."""
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
class HeatRiskResult:
    risk_score: float  # 0–100
    risk_level: str  # LOW / MODERATE / HIGH / EXTREME
    heat_index_c: Optional[float]
    temperature_c: Optional[float]
    humidity_percent: Optional[float]
    consecutive_hot_days: Optional[int]
    enso_phase: Optional[str]
    enso_index: Optional[float]
    components: dict
    methodology_note: str = (
        "Baseline transparent model using measurable variables only. "
        "NOT a medical diagnosis or official meteorological warning. "
        "Thresholds are illustrative for a student project and are not "
        "authoritative WMO or Ministry of Health criteria."
    )


def heat_index_celsius(temp_c: float, rh: float) -> Optional[float]:
    """
    Rothfusz regression (NWS) converted to Celsius input/output.
    Valid mainly for T >= ~27°C and RH >= 40%; outside that range,
    we keep a simple approximation that avoids crashes on malformed inputs.
    """
    temp = _coerce_float(temp_c)
    if temp is None:
        return None
    humidity = _coerce_float(rh, default=0.0)
    if humidity is None:
        return round(temp, 2)

    humidity = min(max(humidity, 0.0), 100.0)
    # Convert to Fahrenheit for the standard formula.
    t_f = temp * 9 / 5 + 32

    # Use the simple approximation when the standard regression is outside its comfort range.
    if t_f < 80:
        exponent = 17.27 * temp / (237.7 + temp)
        approx = temp + 0.33 * (humidity / 100) * (6.105 * math.exp(exponent)) - 0.70 * 0 - 4
        return round(max(temp, approx), 2)

    hi_f = (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * humidity
        - 0.22475541 * t_f * humidity
        - 6.83783e-3 * t_f ** 2
        - 5.481717e-2 * humidity ** 2
        + 1.22874e-3 * t_f ** 2 * humidity
        + 8.5282e-4 * t_f * humidity ** 2
        - 1.99e-6 * t_f ** 2 * humidity ** 2
    )
    return round((hi_f - 32) * 5 / 9, 2)


def compute_risk_score(
    temperature_c: Optional[float],
    humidity_percent: Optional[float] = None,
    wind_speed_ms: Optional[float] = None,
    rainfall_mm: Optional[float] = None,
    consecutive_hot_days: Optional[int] = None,
    night_min_temp_c: Optional[float] = None,
    enso_phase: Optional[str] = None,
    enso_index: Optional[float] = None,
    hot_day_threshold_c: float = 32.0,
) -> HeatRiskResult:
    """
    Configurable baseline score (0–100).

    Components (weights sum conceptually to 100):
    - Temperature / Heat Index contribution (up to 50)
    - Consecutive hot days (up to 20)
    - Night-time recovery (up to 15)
    - Humidity / wind / rain context (up to 10)
    - ENSO context only (up to 5) — never treated as proof of heatwave

    Levels (illustrative, not official):
    - LOW: 0–24
    - MODERATE: 25–49
    - HIGH: 50–74
    - EXTREME: 75–100
    """
    components: dict = {}
    score = 0.0
    hi = None

    temp = _coerce_float(temperature_c)
    humidity = _coerce_float(humidity_percent)
    wind = _coerce_float(wind_speed_ms)
    rainfall = _coerce_float(rainfall_mm)
    night_min = _coerce_float(night_min_temp_c)
    enso_value = _coerce_float(enso_index)
    hot_day_threshold = _coerce_float(hot_day_threshold_c, default=32.0)

    # --- Temperature / Heat Index ---
    if temp is not None:
        if humidity is not None and humidity >= 0:
            hi = heat_index_celsius(temp, humidity)
        else:
            hi = temp
        hi = hi if hi is not None else temp

        # Map HI to 0–50 points
        if hi < 27:
            t_pts = 0
        elif hi < 32:
            t_pts = 10 + (hi - 27) * 2
        elif hi < 39:
            t_pts = 20 + (hi - 32) * (20 / 7)
        elif hi < 46:
            t_pts = 40 + (hi - 39) * (10 / 7)
        else:
            t_pts = 50
        t_pts = max(0, min(50, t_pts))
        score += t_pts
        components["temperature_heat_index_points"] = round(t_pts, 1)
        components["heat_index_c"] = hi
        components["observed_temperature_c"] = temp
    else:
        components["temperature_heat_index_points"] = 0
        components["note"] = "Temperature not available — score incomplete"

    # --- Consecutive hot days ---
    chd = consecutive_hot_days or 0
    try:
        chd = int(chd)
    except (TypeError, ValueError):
        chd = 0
    chd_pts = min(20, chd * 4)  # 5 days → 20 pts
    score += chd_pts
    components["consecutive_hot_days"] = chd
    components["consecutive_hot_days_points"] = chd_pts
    components["hot_day_threshold_c"] = hot_day_threshold

    # --- Night recovery (higher min = less recovery) ---
    if night_min is not None:
        if night_min >= 26:
            night_pts = 15
        elif night_min >= 22:
            night_pts = 8
        elif night_min >= 18:
            night_pts = 3
        else:
            night_pts = 0
        score += night_pts
        components["night_min_temp_c"] = night_min
        components["night_recovery_points"] = night_pts
    else:
        components["night_recovery_points"] = 0

    # --- Humidity / wind / rain context (small) ---
    context_pts = 0.0
    if humidity is not None and humidity > 70 and temp is not None and temp > 28:
        context_pts += 4
    if wind is not None and wind < 2 and temp is not None and temp > 30:
        context_pts += 3  # low wind worsens heat stress slightly
    if rainfall is not None and rainfall > 5:
        context_pts -= 3  # recent rain may moderate
    context_pts = max(0, min(10, context_pts))
    score += context_pts
    components["context_points"] = round(context_pts, 1)
    components["humidity_percent"] = humidity
    components["wind_speed_ms"] = wind
    components["rainfall_mm"] = rainfall

    # --- ENSO context only (max 5) — analysis, not proof ---
    enso_pts = 0.0
    if enso_phase == "El Niño" and (enso_value or 0) >= 0.5:
        enso_pts = min(5, 2 + (enso_value or 0))
    elif enso_phase == "La Niña":
        enso_pts = 0
    components["enso_context_points"] = round(enso_pts, 1)
    components["enso_phase"] = enso_phase
    components["enso_index"] = enso_value
    components["enso_note"] = (
        "ENSO is used only as a weak context variable. "
        "El Niño does not automatically mean a heatwave will occur."
    )
    score += enso_pts

    score = max(0.0, min(100.0, round(score, 1)))

    if score < 25:
        level = "LOW"
    elif score < 50:
        level = "MODERATE"
    elif score < 75:
        level = "HIGH"
    else:
        level = "EXTREME"

    return HeatRiskResult(
        risk_score=score,
        risk_level=level,
        heat_index_c=hi,
        temperature_c=temperature_c,
        humidity_percent=humidity_percent,
        consecutive_hot_days=chd,
        enso_phase=enso_phase,
        enso_index=enso_index,
        components=components,
    )


def result_to_dict(result: HeatRiskResult) -> dict:
    d = asdict(result)
    d["components_json"] = json.dumps(result.components)
    return d
