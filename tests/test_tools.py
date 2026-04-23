"""Unit tests for :mod:`agents.tools`."""

from __future__ import annotations

from agents.tools import (
    check_application_velocity,
    estimate_bank_balance_signal,
    fetch_credit_report,
    screen_ofac_sanctions,
)


def test_credit_report_is_deterministic_for_same_name() -> None:
    a = fetch_credit_report("Jane Doe", 720)
    b = fetch_credit_report("Jane Doe", 720)

    for key in ("tradelines_total", "revolving_utilisation_pct", "delinquencies_24m"):
        assert a[key] == b[key]


def test_credit_report_tier_reflects_fico() -> None:
    assert fetch_credit_report("Anyone", 780)["fico_tier"] == "prime"
    assert fetch_credit_report("Anyone", 680)["fico_tier"] == "near_prime"
    assert fetch_credit_report("Anyone", 600)["fico_tier"] == "subprime"
    assert fetch_credit_report("Anyone", 540)["fico_tier"] == "deep_subprime"


def test_velocity_returns_bounded_counts() -> None:
    v = check_application_velocity("Jane Doe")

    assert 0 <= v["hard_inquiries_30d"] <= 7
    assert v["hard_inquiries_90d"] >= v["hard_inquiries_30d"]
    assert v["stacking_risk"] in {"normal", "elevated", "high"}


def test_ofac_returns_clear_for_synthetic_names() -> None:
    r = screen_ofac_sanctions("Jane Doe")

    assert r["match"] is False
    assert r["list_consulted"] == "OFAC Specially Designated Nationals"


def test_bank_balance_signal_scales_with_income_and_tenure() -> None:
    weak = estimate_bank_balance_signal(20_000, 580, 0.5)
    strong = estimate_bank_balance_signal(200_000, 800, 10)

    assert (
        strong["cash_flow_stability_index"] > weak["cash_flow_stability_index"]
    )
    assert strong["overdrafts_90d"] <= weak["overdrafts_90d"]
