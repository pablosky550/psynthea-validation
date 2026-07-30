"""Deterministic aggregation of isolated per-module scientific experiments.

The aggregator consumes only persisted scientific reports produced by the
orchestration pipeline.  It does not recompute clinical or statistical tests,
and it never converts a technical execution success into an equivalence claim.
A campaign state file defines the exact expected module experiments, preventing
unrelated runs below the same ``runs`` directory from contaminating the result.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import csv
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
from typing import Any

__all__ = [
    "ModuleCampaignAggregationError",
    "ModuleCampaignResult",
    "ModuleResult",
    "aggregate_module_campaign",
    "discover_campaign_reports",
    "main",
    "persist_module_campaign",
]

_SCHEMA_VERSION = "1.0"
_ENCODING = "utf-8"


class ModuleCampaignAggregationError(RuntimeError):
    """Raised when campaign evidence is incomplete, ambiguous or inconsistent."""


@dataclass(frozen=True, slots=True)
class ModuleResult:
    module_name: str
    experiment_id: str
    run_id: str
    report_path: str
    generated_at: str
    population_size: int
    seed: int
    reference_date: str
    min_age: int
    max_age: int
    decision: str
    decision_bucket: str
    validation_status: str
    functional_status: str
    statistical_status: str
    knowledge_status: str
    research_use_ready: bool | None
    root_cause_status: str
    root_cause_confidence: str
    blocking_issue_count: int
    warning_count: int
    significant_after_fdr_count: int
    knowledge_blocking_finding_count: int
    discrepancy_count: int
    blocking_discrepancy_count: int
    top_discrepancy_domain: str | None
    top_discrepancy_severity: str | None
    synthea_counts: Mapping[str, int]
    psynthea_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class ModuleCampaignResult:
    schema_version: str
    generated_at: str
    campaign_id: str
    campaign_state_path: str
    runs_root: str
    expected_module_count: int
    aggregated_module_count: int
    population_sizes: tuple[int, ...]
    seeds: tuple[int, ...]
    reference_dates: tuple[str, ...]
    decision_counts: Mapping[str, int]
    decision_bucket_counts: Mapping[str, int]
    validation_status_counts: Mapping[str, int]
    root_cause_status_counts: Mapping[str, int]
    research_use_ready_counts: Mapping[str, int]
    total_blocking_issues: int
    total_warnings: int
    total_significant_after_fdr: int
    total_blocking_discrepancies: int
    modules: tuple[ModuleResult, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding=_ENCODING))
    except OSError as exc:
        raise ModuleCampaignAggregationError(f"Cannot read JSON artefact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ModuleCampaignAggregationError(f"Invalid JSON artefact {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ModuleCampaignAggregationError(f"JSON root must be an object: {path}")
    return payload


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any, default: str = "unknown") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _decision_bucket(decision: str) -> str:
    normalized = decision.strip().upper()
    if normalized in {"EQUIVALENT", "APPROVED", "PASS"}:
        return "equivalent"
    if normalized in {"REVIEW", "PARTIALLY_COMPARABLE", "PARTIAL"}:
        return "review"
    if normalized in {"NOT_EQUIVALENT", "FAIL", "FAILED"}:
        return "not_equivalent"
    if normalized in {"NOT_COMPARABLE", "INCONCLUSIVE", "NOT_ASSESSABLE"}:
        return "not_comparable"
    return "unknown"


def _latest_succeeded_attempts(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for raw in _sequence(state.get("attempts")):
        if not isinstance(raw, Mapping):
            continue
        module = raw.get("module")
        if isinstance(module, str) and module.strip():
            latest[module.strip()] = raw
    failed = sorted(module for module, item in latest.items() if item.get("status") != "succeeded")
    if failed:
        raise ModuleCampaignAggregationError(
            "Campaign contains modules whose latest attempt did not succeed: " + ", ".join(failed)
        )
    if not latest:
        raise ModuleCampaignAggregationError("Campaign state contains no completed module attempts.")
    return latest


def discover_campaign_reports(
    campaign_state_path: Path | str,
    runs_root: Path | str,
) -> dict[str, Path]:
    """Resolve exactly one canonical report for every succeeded campaign module."""

    state_path = Path(campaign_state_path).expanduser().resolve()
    root = Path(runs_root).expanduser().resolve()
    if not root.is_dir():
        raise ModuleCampaignAggregationError(f"Runs root is not a directory: {root}")
    attempts = _latest_succeeded_attempts(_load_json(state_path))
    expected = {
        module: _text(attempt.get("experiment_id"), "")
        for module, attempt in attempts.items()
    }
    if any(not experiment_id for experiment_id in expected.values()):
        raise ModuleCampaignAggregationError("A succeeded attempt is missing experiment_id.")

    candidates: dict[str, list[tuple[str, Path]]] = {value: [] for value in expected.values()}
    for report_path in sorted(root.glob("**/report/scientific_report.json")):
        payload = _load_json(report_path)
        experiment_id = payload.get("experiment_id")
        if experiment_id in candidates:
            candidates[str(experiment_id)].append((_text(payload.get("generated_at"), ""), report_path))

    resolved: dict[str, Path] = {}
    missing: list[str] = []
    for module, experiment_id in expected.items():
        matches = candidates[experiment_id]
        if not matches:
            missing.append(f"{module} ({experiment_id})")
            continue
        matches.sort(key=lambda item: (item[0], str(item[1])))
        resolved[module] = matches[-1][1]
    if missing:
        raise ModuleCampaignAggregationError(
            "Scientific report not found for completed campaign module(s): " + ", ".join(missing)
        )
    return resolved


def _select_named_module(items: Any, module_name: str) -> Mapping[str, Any]:
    selected = [item for item in _sequence(items) if isinstance(item, Mapping) and item.get("module_name") == module_name]
    if len(selected) != 1:
        raise ModuleCampaignAggregationError(
            f"Expected exactly one result for module {module_name!r}; found {len(selected)}."
        )
    return selected[0]


def _extract_counts(validation: Mapping[str, Any], simulator: str) -> dict[str, int]:
    cohort = _mapping(_mapping(validation.get("cohorts")).get(simulator))
    domains = ("patients", "encounters", "conditions", "medications", "procedures", "observations")
    return {domain: _integer(cohort.get(domain)) for domain in domains}


def _extract_module_result(module_name: str, report_path: Path) -> ModuleResult:
    report = _load_json(report_path)
    cohort = _mapping(report.get("cohort"))
    results = _mapping(report.get("scientific_results"))
    validation = _mapping(results.get("validation"))
    validation_module = _select_named_module(validation.get("modules"), module_name)

    knowledge = _mapping(results.get("knowledge"))
    knowledge_modules = _sequence(knowledge.get("modules"))
    knowledge_module = next(
        (item for item in knowledge_modules if isinstance(item, Mapping) and item.get("module_name") == module_name),
        {},
    )
    root_cause = _mapping(results.get("root_cause"))
    executive = _mapping(report.get("executive_summary"))
    validation_exec = _mapping(executive.get("validation"))
    knowledge_exec = _mapping(executive.get("knowledge"))
    root_exec = _mapping(executive.get("root_cause"))

    functional = _mapping(validation_module.get("functional_summary"))
    statistical = _mapping(validation_module.get("statistical_summary"))
    discrepancies = [item for item in _sequence(_mapping(report.get("scientific_analysis")).get("discrepancies")) if isinstance(item, Mapping)]
    discrepancies.sort(
        key=lambda item: (
            not bool(item.get("blocking")),
            -float(item.get("score", 0.0) or 0.0),
            _text(item.get("domain")),
        )
    )
    top = discrepancies[0] if discrepancies else {}
    decision = _text(report.get("decision"))
    research_ready_raw = knowledge_module.get("research_use_ready")
    research_ready = research_ready_raw if isinstance(research_ready_raw, bool) else None

    return ModuleResult(
        module_name=module_name,
        experiment_id=_text(report.get("experiment_id")),
        run_id=_text(report.get("run_id")),
        report_path=str(report_path),
        generated_at=_text(report.get("generated_at")),
        population_size=_integer(cohort.get("population_size")),
        seed=_integer(cohort.get("seed")),
        reference_date=_text(cohort.get("reference_date")),
        min_age=_integer(cohort.get("min_age")),
        max_age=_integer(cohort.get("max_age")),
        decision=decision,
        decision_bucket=_decision_bucket(decision),
        validation_status=_text(validation_module.get("status"), _text(functional.get("status"))),
        functional_status=_text(functional.get("status")),
        statistical_status=_text(statistical.get("status")),
        knowledge_status=_text(knowledge_module.get("overall_status")),
        research_use_ready=research_ready,
        root_cause_status=_text(root_cause.get("status"), _text(root_exec.get("status"))),
        root_cause_confidence=_text(root_cause.get("confidence"), _text(root_exec.get("confidence"))),
        blocking_issue_count=_integer(validation_module.get("blocking_issue_count"), _integer(validation_exec.get("blocking_issue_count"))),
        warning_count=_integer(validation_module.get("warning_count"), _integer(validation_exec.get("warning_count"))),
        significant_after_fdr_count=_integer(statistical.get("significant_after_fdr_count")),
        knowledge_blocking_finding_count=_integer(knowledge_module.get("blocking_finding_count"), _integer(knowledge_exec.get("blocking_finding_count"))),
        discrepancy_count=len(discrepancies),
        blocking_discrepancy_count=sum(bool(item.get("blocking")) for item in discrepancies),
        top_discrepancy_domain=_text(top.get("domain"), "") or None,
        top_discrepancy_severity=_text(top.get("severity"), "") or None,
        synthea_counts=_extract_counts(validation, "synthea"),
        psynthea_counts=_extract_counts(validation, "psynthea"),
    )


def aggregate_module_campaign(
    campaign_state_path: Path | str,
    runs_root: Path | str,
    *,
    campaign_id: str | None = None,
    generated_at: datetime | None = None,
) -> ModuleCampaignResult:
    state_path = Path(campaign_state_path).expanduser().resolve()
    root = Path(runs_root).expanduser().resolve()
    reports = discover_campaign_reports(state_path, root)
    modules = tuple(
        _extract_module_result(module_name, report_path)
        for module_name, report_path in sorted(reports.items(), key=lambda item: item[0].casefold())
    )
    decisions = Counter(item.decision for item in modules)
    buckets = Counter(item.decision_bucket for item in modules)
    validations = Counter(item.validation_status for item in modules)
    root_statuses = Counter(item.root_cause_status for item in modules)
    readiness = Counter(
        "ready" if item.research_use_ready is True else "not_ready" if item.research_use_ready is False else "unknown"
        for item in modules
    )
    created = (generated_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    inferred_id = state_path.parent.name
    return ModuleCampaignResult(
        schema_version=_SCHEMA_VERSION,
        generated_at=created,
        campaign_id=(campaign_id or inferred_id).strip(),
        campaign_state_path=str(state_path),
        runs_root=str(root),
        expected_module_count=len(reports),
        aggregated_module_count=len(modules),
        population_sizes=tuple(sorted({item.population_size for item in modules})),
        seeds=tuple(sorted({item.seed for item in modules})),
        reference_dates=tuple(sorted({item.reference_date for item in modules})),
        decision_counts=dict(sorted(decisions.items())),
        decision_bucket_counts=dict(sorted(buckets.items())),
        validation_status_counts=dict(sorted(validations.items())),
        root_cause_status_counts=dict(sorted(root_statuses.items())),
        research_use_ready_counts=dict(sorted(readiness.items())),
        total_blocking_issues=sum(item.blocking_issue_count for item in modules),
        total_warnings=sum(item.warning_count for item in modules),
        total_significant_after_fdr=sum(item.significant_after_fdr_count for item in modules),
        total_blocking_discrepancies=sum(item.blocking_discrepancy_count for item in modules),
        modules=modules,
        limitations=(
            "This artefact aggregates persisted module-level evidence and does not recompute statistical tests.",
            "A successful pipeline execution is not interpreted as scientific equivalence.",
            "Population 10 is an integration-screening cohort; confirmatory claims require larger cohorts and independent seeds.",
            "Percentages of modules are descriptive coverage summaries, not probabilities of replacement validity.",
        ),
    )


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding=_ENCODING, dir=path.parent, delete=False) as stream:
        stream.write(content)
        temporary = Path(stream.name)
    temporary.replace(path)


def _write_modules_csv(path: Path, modules: Sequence[ModuleResult]) -> None:
    domains = ("patients", "encounters", "conditions", "medications", "procedures", "observations")
    fields = [
        "module_name", "experiment_id", "run_id", "decision", "decision_bucket",
        "validation_status", "functional_status", "statistical_status", "knowledge_status",
        "research_use_ready", "root_cause_status", "root_cause_confidence",
        "population_size", "seed", "reference_date", "min_age", "max_age",
        "blocking_issue_count", "warning_count", "significant_after_fdr_count",
        "knowledge_blocking_finding_count", "discrepancy_count", "blocking_discrepancy_count",
        "top_discrepancy_domain", "top_discrepancy_severity",
    ] + [f"synthea_{domain}" for domain in domains] + [f"psynthea_{domain}" for domain in domains] + ["report_path"]
    with path.open("w", encoding=_ENCODING, newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in modules:
            row = {field: getattr(item, field) for field in fields if hasattr(item, field)}
            row.update({f"synthea_{domain}": item.synthea_counts.get(domain, 0) for domain in domains})
            row.update({f"psynthea_{domain}": item.psynthea_counts.get(domain, 0) for domain in domains})
            writer.writerow(row)


def _render_markdown(result: ModuleCampaignResult) -> str:
    lines = [
        f"# Module scientific campaign — {result.campaign_id}", "",
        f"Generated: `{result.generated_at}`", "",
        "## Executive summary", "",
        f"- Modules aggregated: **{result.aggregated_module_count}/{result.expected_module_count}**",
        f"- Decision buckets: `{dict(result.decision_bucket_counts)}`",
        f"- Scientific decisions: `{dict(result.decision_counts)}`",
        f"- Research-use readiness: `{dict(result.research_use_ready_counts)}`",
        f"- Blocking discrepancies: **{result.total_blocking_discrepancies}**",
        "",
        "> This aggregation does not convert technical success into equivalence and does not recompute tests.",
        "", "## Module matrix", "",
        "| Module | Decision | Functional | Statistical | Knowledge | RCA | Blocking discrepancies |",
        "|---|---|---|---|---|---|---:|",
    ]
    for item in result.modules:
        lines.append(
            f"| `{item.module_name}` | {item.decision} | {item.functional_status} | "
            f"{item.statistical_status} | {item.knowledge_status} | {item.root_cause_status} | "
            f"{item.blocking_discrepancy_count} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines) + "\n"


def persist_module_campaign(result: ModuleCampaignResult, output_dir: Path | str) -> tuple[Path, ...]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "module_campaign_summary.json"
    csv_path = output / "module_campaign_modules.csv"
    markdown_path = output / "module_campaign_report.md"
    _write_json_atomic(json_path, result.to_dict())
    _write_modules_csv(csv_path, result.modules)
    markdown_path.write_text(_render_markdown(result), encoding=_ENCODING)
    return json_path, csv_path, markdown_path


def _parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate isolated per-module scientific reports.")
    parser.add_argument("--campaign-dir", type=Path, required=True, help="Directory containing campaign_state.json.")
    parser.add_argument("--runs-root", type=Path, default=Path("runs"), help="Root containing orchestration run directories.")
    parser.add_argument("--output-dir", type=Path, help="Output directory; defaults to <campaign-dir>/aggregate.")
    parser.add_argument("--campaign-id", help="Stable campaign identifier; defaults to campaign directory name.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    state_path = arguments.campaign_dir / "campaign_state.json"
    output_dir = arguments.output_dir or arguments.campaign_dir / "aggregate"
    try:
        result = aggregate_module_campaign(
            state_path,
            arguments.runs_root,
            campaign_id=arguments.campaign_id,
        )
        paths = persist_module_campaign(result, output_dir)
    except ModuleCampaignAggregationError as exc:
        print(f"Campaign aggregation error: {exc}")
        return 2
    print(f"Modules aggregated: {result.aggregated_module_count}/{result.expected_module_count}")
    print(f"Decision buckets: {dict(result.decision_bucket_counts)}")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
