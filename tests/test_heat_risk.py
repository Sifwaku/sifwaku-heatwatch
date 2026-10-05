"""Unit tests for baseline heat-risk (no external API calls)."""
from backend.analytics.heat_risk import compute_risk_score


def test_low_risk_cool_day():
    r = compute_risk_score(temperature_c=22.0, humidity_percent=50.0)
    assert r.risk_level == "LOW"
    assert 0 <= r.risk_score < 25


def test_higher_score_hot_humid():
    cool = compute_risk_score(temperature_c=25.0, humidity_percent=40.0)
    hot = compute_risk_score(temperature_c=38.0, humidity_percent=70.0)
    assert hot.risk_score > cool.risk_score


def test_enso_does_not_dominate():
    base = compute_risk_score(temperature_c=30.0, humidity_percent=50.0)
    with_enso = compute_risk_score(
        temperature_c=30.0,
        humidity_percent=50.0,
        enso_phase="El Niño",
        enso_index=1.5,
    )
    # ENSO context capped at 5 points
    assert with_enso.risk_score - base.risk_score <= 5.1


def test_missing_temperature_incomplete():
    r = compute_risk_score(temperature_c=None)
    assert "Temperature not available" in str(r.components.get("note", ""))
