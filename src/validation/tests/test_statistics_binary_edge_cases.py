"""Regression tests for binary epidemiological statistics edge cases."""

from __future__ import annotations

from validation.statistics import (
    binary_association_measures,
    confidence_interval_risk_ratio,
)


def test_risk_ratio_ci_rejects_event_counts_above_population() -> None:
    """Repeated event rows must not be interpreted as binary patient risks."""

    interval = confidence_interval_risk_ratio(
        synthea_events=121,
        synthea_total=100,
        psynthea_events=110,
        psynthea_total=100,
    )

    assert interval.lower is None
    assert interval.upper is None


def test_binary_association_is_safe_for_non_binary_event_counts() -> None:
    """Invalid binary counts return unavailable measures instead of crashing."""

    result = binary_association_measures(
        synthea_events=121,
        synthea_total=100,
        psynthea_events=110,
        psynthea_total=100,
    )

    assert result.risk_ratio is None
    assert result.odds_ratio is None
    assert result.risk_ratio_ci is None
    assert result.odds_ratio_ci is None


def test_risk_ratio_ci_remains_available_for_valid_binary_counts() -> None:
    interval = confidence_interval_risk_ratio(
        synthea_events=20,
        synthea_total=100,
        psynthea_events=25,
        psynthea_total=100,
    )

    assert interval.lower is not None
    assert interval.upper is not None
    assert interval.lower < interval.upper
