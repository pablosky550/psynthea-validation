from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from validation.campaigns.module_aggregation import (
    ModuleCampaignAggregationError,
    aggregate_module_campaign,
    discover_campaign_reports,
    persist_module_campaign,
)


def _make_campaign(tmp_path: Path, modules: tuple[str, ...] = ("asthma", "hypertension")) -> tuple[Path, Path]:
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    attempts = []
    runs = tmp_path / "runs"
    for index, module in enumerate(modules):
        experiment_id = f"experiment-module-{module}-p10"
        attempts.append({"module": module, "status": "succeeded", "experiment_id": experiment_id})
        report = runs / experiment_id / f"run-{index}" / "report" / "scientific_report.json"
        report.parent.mkdir(parents=True)
        payload = {
            "run_id": f"run-{index}", "experiment_id": experiment_id,
            "generated_at": f"2026-07-29T08:00:0{index}+00:00",
            "decision": "REVIEW" if module == "asthma" else "NOT_COMPARABLE",
            "cohort": {"population_size": 10, "seed": 42, "reference_date": "2024-12-31", "min_age": 18, "max_age": 90},
            "executive_summary": {
                "validation": {"blocking_issue_count": 1, "warning_count": 2},
                "knowledge": {"blocking_finding_count": 3},
                "root_cause": {"status": "inconclusive", "confidence": "none"},
            },
            "scientific_results": {
                "validation": {
                    "cohorts": {
                        "synthea": {"patients": 10, "encounters": 20, "conditions": 1, "medications": 0, "procedures": 0, "observations": 30},
                        "psynthea": {"patients": 10, "encounters": 22, "conditions": 2, "medications": 0, "procedures": 0, "observations": 25},
                    },
                    "modules": [{
                        "module_name": module,
                        "functional_summary": {"status": "partially_comparable"},
                        "statistical_summary": {"status": "reference_empty", "significant_after_fdr_count": 0},
                    }],
                },
                "knowledge": {"modules": [{"module_name": module, "overall_status": "fail", "research_use_ready": False, "blocking_finding_count": 3}]},
                "root_cause": {"status": "inconclusive", "confidence": "none"},
            },
            "scientific_analysis": {"discrepancies": [{"domain": "observations", "severity": "high", "blocking": True, "score": 80}]},
        }
        report.write_text(json.dumps(payload), encoding="utf-8")
    state = campaign / "campaign_state.json"
    state.write_text(json.dumps({"attempts": attempts}), encoding="utf-8")
    return state, runs


def test_aggregate_is_deterministic_and_preserves_scientific_decisions(tmp_path: Path) -> None:
    state, runs = _make_campaign(tmp_path)
    result = aggregate_module_campaign(
        state, runs, campaign_id="p10",
        generated_at=datetime(2026, 7, 29, tzinfo=UTC),
    )
    assert [item.module_name for item in result.modules] == ["asthma", "hypertension"]
    assert result.decision_counts == {"NOT_COMPARABLE": 1, "REVIEW": 1}
    assert result.decision_bucket_counts == {"not_comparable": 1, "review": 1}
    assert result.total_blocking_discrepancies == 2
    assert result.population_sizes == (10,)


def test_latest_report_for_same_experiment_is_selected(tmp_path: Path) -> None:
    state, runs = _make_campaign(tmp_path, ("asthma",))
    original = next(runs.glob("**/scientific_report.json"))
    payload = json.loads(original.read_text())
    payload["run_id"] = "run-new"
    payload["generated_at"] = "2026-07-29T09:00:00+00:00"
    newer = runs / "duplicate" / "report" / "scientific_report.json"
    newer.parent.mkdir(parents=True)
    newer.write_text(json.dumps(payload), encoding="utf-8")
    reports = discover_campaign_reports(state, runs)
    assert reports["asthma"] == newer


def test_failed_latest_attempt_is_rejected(tmp_path: Path) -> None:
    state, runs = _make_campaign(tmp_path, ("asthma",))
    payload = json.loads(state.read_text())
    payload["attempts"].append({"module": "asthma", "status": "failed", "experiment_id": "experiment-module-asthma-p10"})
    state.write_text(json.dumps(payload))
    with pytest.raises(ModuleCampaignAggregationError, match="did not succeed"):
        aggregate_module_campaign(state, runs)


def test_missing_report_is_rejected(tmp_path: Path) -> None:
    state, runs = _make_campaign(tmp_path, ("asthma",))
    next(runs.glob("**/scientific_report.json")).unlink()
    with pytest.raises(ModuleCampaignAggregationError, match="not found"):
        aggregate_module_campaign(state, runs)


def test_persistence_writes_json_csv_and_markdown(tmp_path: Path) -> None:
    state, runs = _make_campaign(tmp_path)
    result = aggregate_module_campaign(state, runs)
    paths = persist_module_campaign(result, tmp_path / "aggregate")
    assert {path.name for path in paths} == {
        "module_campaign_summary.json", "module_campaign_modules.csv", "module_campaign_report.md"
    }
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
    markdown = (tmp_path / "aggregate" / "module_campaign_report.md").read_text()
    assert "does not convert technical success into equivalence" in markdown
