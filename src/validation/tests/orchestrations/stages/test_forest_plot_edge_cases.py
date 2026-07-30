from __future__ import annotations

import math

from validation.orchestration.stages.report import _forest_plot


def _discrepancy(*, rr: float, lower: float, upper: float) -> dict[str, object]:
    return {
        "title": "Condition prevalence differs",
        "domain": "conditions",
        "related_findings": [
            {
                "risk_ratio": rr,
                "ci_lower": lower,
                "ci_upper": upper,
            }
        ],
    }


def test_forest_plot_skips_zero_risk_ratio_without_math_domain_error() -> None:
    html = _forest_plot([_discrepancy(rr=0.0, lower=0.1, upper=1.2)])
    assert "No valid risk-ratio confidence intervals" in html


def test_forest_plot_skips_non_finite_statistics() -> None:
    html = _forest_plot(
        [
            _discrepancy(rr=math.nan, lower=0.1, upper=1.2),
            _discrepancy(rr=1.2, lower=0.1, upper=math.inf),
        ]
    )
    assert "No valid risk-ratio confidence intervals" in html


def test_forest_plot_renders_valid_positive_interval() -> None:
    html = _forest_plot([_discrepancy(rr=1.2, lower=0.8, upper=1.7)])
    assert "Risk-ratio forest plot" in html
    assert "<svg" in html
    assert "1.20 [0.80–1.70]" in html
