from __future__ import annotations

import csv
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from validation.campaigns.multiseed import (
    CampaignAggregationError,
    aggregate_campaign,
    discover_reports,
    persist_campaign_result,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _make_run(root: Path, seed: int, synthea_prev: float, psynthea_prev: float) -> Path:
    run = root / f"run-{seed}"
    report_path = run / "report" / "scientific_report.json"
    report_path.parent.mkdir(parents=True)
    tables = run / "validation" / "modules" / "hypertension"

    _write_csv(tables / "functional_table_status.csv", [
        {"table": name, "relative_row_difference": difference}
        for name, difference in (
            ("patients", 0.0), ("encounters", -0.3), ("conditions", 0.7),
            ("medications", -1.0), ("procedures", -1.0), ("observations", 0.1),
        )
    ])
    _write_csv(tables / "prevalence_tests.csv", [{
        "domain": "conditions", "code": "59621000",
        "synthea_prevalence": synthea_prev, "psynthea_prevalence": psynthea_prev,
        "absolute_difference": psynthea_prev - synthea_prev,
        "relative_difference": (psynthea_prev - synthea_prev) / synthea_prev,
        "risk_ratio": psynthea_prev / synthea_prev,
        "risk_ratio_ci_lower": 1.2, "risk_ratio_ci_upper": 2.0,
        "odds_ratio": 2.0, "adjusted_p_value": 0.001,
    }])
    _write_csv(tables / "continuous_tests.csv", [
        {"metric": metric, "test_name": test, "p_value": 0.5, "effect_size": 0.02}
        for metric in ("age", "encounters_per_patient", "conditions_per_patient")
        for test in ("kolmogorov_smirnov", "mann_whitney_u", "welch_t_test")
    ])
    _write_csv(tables / "categorical_tests.csv", [
        {"domain": "gender", "p_value": 0.4, "effect_size": 0.02},
        {"domain": "encounter_class", "p_value": 0.001, "effect_size": 0.3},
    ])
    _write_csv(tables / "distribution_tests.csv", [
        {"domain": domain, "jensen_shannon_divergence": 0.2}
        for domain in ("conditions", "medications", "procedures", "observations")
    ])

    table_refs = {
        name: {"path": f"validation/modules/hypertension/{name}.csv"}
        for name in (
            "functional_table_status", "prevalence_tests", "continuous_tests",
            "categorical_tests", "distribution_tests",
        )
    }
    report = {
        "run_id": f"run-{seed}", "experiment_id": f"exp-{seed}", "decision": "REVIEW",
        "cohort": {"seed": seed, "population_size": 1000, "reference_date": "2024-12-31", "min_age": 18, "max_age": 90},
        "scientific_results": {"validation": {
            "cohorts": {
                "synthea": {"patients": 1000, "encounters": 9500, "conditions": int(1000*synthea_prev), "medications": 500, "procedures": 5, "observations": 32000},
                "psynthea": {"patients": 1000, "encounters": 6800, "conditions": int(1000*psynthea_prev), "medications": 0, "procedures": 0, "observations": 34000},
            },
            "modules": [{
                "module_name": "hypertension",
                "functional_summary": {"status": "partially_comparable", "mean_distributional_similarity": 0.625, "mean_jensen_shannon_divergence": 0.49},
                "statistical_summary": {"mean_jensen_shannon_divergence": 0.10, "significant_after_fdr_count": 12},
                "tables": table_refs,
            }],
        }},
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path


def test_aggregate_campaign_orders_seeds_and_calculates_ci(tmp_path: Path) -> None:
    reports = [
        _make_run(tmp_path, 44, 0.30, 0.48),
        _make_run(tmp_path, 42, 0.27, 0.47),
        _make_run(tmp_path, 43, 0.28, 0.46),
    ]
    result = aggregate_campaign(
        reports,
        campaign_id="campaign", module_name="hypertension",
        generated_at=datetime(2026, 7, 23, tzinfo=UTC),
    )
    assert result.seeds == (42, 43, 44)
    summary = next(item for item in result.summaries if item.metric == "primary_condition_absolute_difference")
    assert summary.n == 3
    assert summary.mean == pytest.approx((0.20 + 0.18 + 0.18) / 3)
    assert summary.ci_lower is not None
    assert summary.ci_upper is not None
    assert summary.directional_consistency == 1.0


def test_duplicate_seed_is_rejected(tmp_path: Path) -> None:
    first = _make_run(tmp_path / "a", 42, 0.27, 0.47)
    second = _make_run(tmp_path / "b", 42, 0.28, 0.48)
    third = _make_run(tmp_path / "c", 43, 0.29, 0.49)
    with pytest.raises(CampaignAggregationError, match="Duplicate random seeds"):
        aggregate_campaign([first, second, third], campaign_id="x", module_name="hypertension")


def test_inconsistent_population_is_rejected(tmp_path: Path) -> None:
    reports = [_make_run(tmp_path, seed, 0.27, 0.47) for seed in (42, 43, 44)]
    payload = json.loads(reports[-1].read_text())
    payload["cohort"]["population_size"] = 2000
    reports[-1].write_text(json.dumps(payload))
    with pytest.raises(CampaignAggregationError, match="population_size"):
        aggregate_campaign(reports, campaign_id="x", module_name="hypertension")


def test_persistence_writes_all_canonical_outputs(tmp_path: Path) -> None:
    reports = [_make_run(tmp_path / "runs", seed, 0.27, 0.47) for seed in (42, 43, 44)]
    result = aggregate_campaign(reports, campaign_id="x", module_name="hypertension")
    paths = persist_campaign_result(result, tmp_path / "output")
    assert {path.name for path in paths} == {
        "multiseed_campaign.json", "multiseed_run_metrics.csv",
        "multiseed_metric_summary.csv", "multiseed_report.html",
    }
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)

    html = (tmp_path / "output" / "multiseed_report.html").read_text(encoding="utf-8")
    assert "Executive scientific summary" in html
    assert "Structural output differences" in html
    assert "Limitations and required next analysis" in html
    assert "P-values are not averaged" in html
    assert "MATERIAL_DIFFERENCES" in html
    assert "<svg" in html


def test_discovery_requires_reports(tmp_path: Path) -> None:
    with pytest.raises(CampaignAggregationError, match="No report"):
        discover_reports(tmp_path)
