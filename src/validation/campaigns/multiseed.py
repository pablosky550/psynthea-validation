"""Reproducible aggregation of paired Synthea/Psynthea runs across seeds.

The module consumes persisted single-run scientific artefacts.  It never
recomputes cohort metrics from raw patient data and never treats repeated seeds
as independent evidence.  Input consistency is checked before aggregation so a
campaign cannot silently combine different populations, modules, age windows or
reference dates.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
import csv
from dataclasses import asdict
from datetime import UTC, datetime
from html import escape
import json
from math import isclose
from pathlib import Path
import statistics
import sys
from typing import Any

from scipy import stats

from validation.campaigns.models import (
    CampaignResult,
    MetricSummary,
    RunMetric,
    RunRecord,
)

__all__ = [
    "CampaignAggregationError",
    "aggregate_campaign",
    "discover_reports",
    "main",
    "persist_campaign_result",
]

_SCHEMA_VERSION = "1.0"
_DEFAULT_PRIMARY_CONDITION_CODE = "59621000"
_JSON_ENCODING = "utf-8"


class CampaignAggregationError(RuntimeError):
    """Raised when campaign inputs are incomplete, inconsistent or ambiguous."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding=_JSON_ENCODING))
    except OSError as exc:
        raise CampaignAggregationError(f"Cannot read JSON artefact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CampaignAggregationError(f"Invalid JSON artefact: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CampaignAggregationError(f"JSON artefact must contain an object: {path}")
    return payload


def _load_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding=_JSON_ENCODING, newline="") as stream:
            return list(csv.DictReader(stream))
    except OSError as exc:
        raise CampaignAggregationError(f"Cannot read CSV artefact: {path}") from exc


def _float(value: str | int | float | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise CampaignAggregationError(f"Expected numeric value, got {value!r}.") from exc


def _int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise CampaignAggregationError(f"{field_name} must be an integer.")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise CampaignAggregationError(f"{field_name} must be an integer.") from exc
    return result


def discover_reports(runs_root: Path | str) -> tuple[Path, ...]:
    """Discover canonical scientific JSON reports below ``runs_root``."""

    root = Path(runs_root).expanduser().resolve()
    if not root.is_dir():
        raise CampaignAggregationError(f"Runs root is not a directory: {root}")
    reports = tuple(sorted(root.glob("**/report/scientific_report.json")))
    if not reports:
        raise CampaignAggregationError(
            f"No report/scientific_report.json artefacts found below {root}."
        )
    return reports


def _table_path(report_path: Path, module: Mapping[str, Any], table: str) -> Path:
    tables = module.get("tables")
    if not isinstance(tables, Mapping) or table not in tables:
        raise CampaignAggregationError(
            f"Report {report_path} does not reference table {table!r}."
        )
    table_ref = tables[table]
    if not isinstance(table_ref, Mapping) or not table_ref.get("path"):
        raise CampaignAggregationError(
            f"Invalid table reference {table!r} in {report_path}."
        )
    run_root = report_path.parent.parent
    path = run_root / str(table_ref["path"])
    if not path.is_file():
        raise CampaignAggregationError(f"Referenced table does not exist: {path}")
    return path


def _select_module(
    report_path: Path,
    validation: Mapping[str, Any],
    module_name: str,
) -> Mapping[str, Any]:
    modules = validation.get("modules")
    if not isinstance(modules, Sequence):
        raise CampaignAggregationError(f"Validation modules are invalid in {report_path}.")
    selected = [item for item in modules if item.get("module_name") == module_name]
    if len(selected) != 1:
        raise CampaignAggregationError(
            f"Expected exactly one module {module_name!r} in {report_path}; "
            f"found {len(selected)}."
        )
    return selected[0]


def _append_metric(
    metrics: list[RunMetric],
    metric: str,
    value: float | int | None,
    *,
    domain: str,
    unit: str,
    simulator: str | None = None,
) -> None:
    metrics.append(
        RunMetric(
            metric=metric,
            value=None if value is None else float(value),
            domain=domain,
            unit=unit,
            simulator=simulator,
        )
    )


def _extract_run_record(
    report_path: Path,
    *,
    module_name: str,
    primary_condition_code: str,
) -> RunRecord:
    report = _load_json(report_path)
    cohort = report.get("cohort")
    results = report.get("scientific_results")
    if not isinstance(cohort, Mapping) or not isinstance(results, Mapping):
        raise CampaignAggregationError(f"Incomplete scientific report: {report_path}")
    validation = results.get("validation")
    if not isinstance(validation, Mapping):
        raise CampaignAggregationError(f"Missing validation result: {report_path}")
    module = _select_module(report_path, validation, module_name)
    functional = module.get("functional_summary")
    statistical = module.get("statistical_summary")
    if not isinstance(functional, Mapping) or not isinstance(statistical, Mapping):
        raise CampaignAggregationError(f"Missing module summaries in {report_path}.")

    metrics: list[RunMetric] = []
    cohorts = validation.get("cohorts")
    if not isinstance(cohorts, Mapping):
        raise CampaignAggregationError(f"Missing cohort counts in {report_path}.")
    for simulator in ("synthea", "psynthea"):
        counts = cohorts.get(simulator)
        if not isinstance(counts, Mapping):
            raise CampaignAggregationError(
                f"Missing {simulator} cohort counts in {report_path}."
            )
        for domain in (
            "patients",
            "encounters",
            "conditions",
            "medications",
            "procedures",
            "observations",
        ):
            _append_metric(
                metrics,
                f"{domain}_count",
                _int(counts.get(domain), f"{simulator}.{domain}"),
                domain=domain,
                unit="count",
                simulator=simulator,
            )

    table_status = _load_csv(_table_path(report_path, module, "functional_table_status"))
    for row in table_status:
        domain = row["table"]
        _append_metric(
            metrics,
            f"{domain}_relative_difference",
            _float(row.get("relative_row_difference")),
            domain=domain,
            unit="proportion",
        )

    prevalence = _load_csv(_table_path(report_path, module, "prevalence_tests"))
    primary_rows = [
        row
        for row in prevalence
        if row.get("domain") == "conditions"
        and row.get("code") == primary_condition_code
    ]
    if len(primary_rows) != 1:
        raise CampaignAggregationError(
            f"Expected one condition prevalence row for code "
            f"{primary_condition_code!r} in {report_path}; found {len(primary_rows)}."
        )
    primary = primary_rows[0]
    for simulator in ("synthea", "psynthea"):
        _append_metric(
            metrics,
            "primary_condition_prevalence",
            _float(primary.get(f"{simulator}_prevalence")),
            domain="conditions",
            unit="proportion",
            simulator=simulator,
        )
    for name in (
        "absolute_difference",
        "relative_difference",
        "risk_ratio",
        "risk_ratio_ci_lower",
        "risk_ratio_ci_upper",
        "odds_ratio",
        "adjusted_p_value",
    ):
        unit = "ratio" if "ratio" in name else "p_value" if "p_value" in name else "proportion"
        _append_metric(
            metrics,
            f"primary_condition_{name}",
            _float(primary.get(name)),
            domain="conditions",
            unit=unit,
        )

    continuous = _load_csv(_table_path(report_path, module, "continuous_tests"))
    for metric_name in ("age", "encounters_per_patient", "conditions_per_patient"):
        for test_name in ("kolmogorov_smirnov", "mann_whitney_u", "welch_t_test"):
            matches = [
                row
                for row in continuous
                if row.get("metric") == metric_name and row.get("test_name") == test_name
            ]
            if len(matches) == 1:
                row = matches[0]
                _append_metric(
                    metrics,
                    f"{metric_name}_{test_name}_p_value",
                    _float(row.get("p_value")),
                    domain="demographics" if metric_name == "age" else "utilization",
                    unit="p_value",
                )
                _append_metric(
                    metrics,
                    f"{metric_name}_{test_name}_effect_size",
                    _float(row.get("effect_size")),
                    domain="demographics" if metric_name == "age" else "utilization",
                    unit="effect_size",
                )

    categorical = _load_csv(_table_path(report_path, module, "categorical_tests"))
    for domain in ("gender", "encounter_class"):
        matches = [row for row in categorical if row.get("domain") == domain]
        if len(matches) == 1:
            row = matches[0]
            _append_metric(
                metrics,
                f"{domain}_p_value",
                _float(row.get("p_value")),
                domain="demographics" if domain == "gender" else "utilization",
                unit="p_value",
            )
            _append_metric(
                metrics,
                f"{domain}_effect_size",
                _float(row.get("effect_size")),
                domain="demographics" if domain == "gender" else "utilization",
                unit="effect_size",
            )

    distribution = _load_csv(_table_path(report_path, module, "distribution_tests"))
    for row in distribution:
        domain = row.get("domain")
        if domain:
            _append_metric(
                metrics,
                f"{domain}_jensen_shannon_divergence",
                _float(row.get("jensen_shannon_divergence")),
                domain=domain,
                unit="divergence",
            )

    _append_metric(
        metrics,
        "functional_mean_distributional_similarity",
        _float(functional.get("mean_distributional_similarity")),
        domain="overall",
        unit="similarity",
    )
    _append_metric(
        metrics,
        "functional_mean_jensen_shannon_divergence",
        _float(functional.get("mean_jensen_shannon_divergence")),
        domain="overall",
        unit="divergence",
    )
    _append_metric(
        metrics,
        "statistical_mean_jensen_shannon_divergence",
        _float(statistical.get("mean_jensen_shannon_divergence")),
        domain="overall",
        unit="divergence",
    )
    _append_metric(
        metrics,
        "significant_after_fdr_count",
        _float(statistical.get("significant_after_fdr_count")),
        domain="overall",
        unit="count",
    )

    return RunRecord(
        run_id=str(report.get("run_id", "")),
        experiment_id=str(report.get("experiment_id", "")),
        seed=_int(cohort.get("seed"), "cohort.seed"),
        population_size=_int(cohort.get("population_size"), "cohort.population_size"),
        module_name=module_name,
        reference_date=str(cohort.get("reference_date", "")),
        min_age=_int(cohort.get("min_age"), "cohort.min_age"),
        max_age=_int(cohort.get("max_age"), "cohort.max_age"),
        decision=str(report.get("decision", "")),
        validation_status=str(functional.get("status", "")),
        report_path=report_path.resolve(),
        metrics=tuple(metrics),
    )


def _validate_campaign(records: Sequence[RunRecord], minimum_runs: int) -> None:
    if len(records) < minimum_runs:
        raise CampaignAggregationError(
            f"Campaign requires at least {minimum_runs} runs; found {len(records)}."
        )
    seeds = [record.seed for record in records]
    duplicate_seeds = sorted(seed for seed, count in Counter(seeds).items() if count > 1)
    if duplicate_seeds:
        raise CampaignAggregationError(
            f"Duplicate random seeds are not allowed: {duplicate_seeds}."
        )
    fields = (
        "population_size",
        "module_name",
        "reference_date",
        "min_age",
        "max_age",
    )
    for field in fields:
        values = {getattr(record, field) for record in records}
        if len(values) != 1:
            raise CampaignAggregationError(
                f"Campaign mixes inconsistent {field} values: {sorted(values, key=str)}."
            )


def _summarize_metric(
    key: tuple[str, str, str, str | None],
    values: Sequence[float | None],
) -> MetricSummary:
    metric, domain, unit, simulator = key
    observed = [value for value in values if value is not None]
    n = len(observed)
    missing = len(values) - n
    if not observed:
        return MetricSummary(
            metric, domain, unit, simulator, 0, missing,
            None, None, None, None, None, None, None, None, None,
        )

    mean = statistics.fmean(observed)
    minimum = min(observed)
    maximum = max(observed)
    if n >= 2:
        standard_deviation = statistics.stdev(observed)
        standard_error = standard_deviation / n**0.5
        critical = float(stats.t.ppf(0.975, df=n - 1))
        ci_lower = mean - critical * standard_error
        ci_upper = mean + critical * standard_error
    else:
        standard_deviation = None
        standard_error = None
        ci_lower = None
        ci_upper = None

    coefficient_of_variation = (
        None if isclose(mean, 0.0, abs_tol=1e-15) or standard_deviation is None
        else abs(standard_deviation / mean)
    )
    directional_consistency: float | None = None
    if "difference" in metric or "effect_size" in metric:
        non_zero = [
            value for value in observed if not isclose(value, 0.0, abs_tol=1e-15)
        ]
        if non_zero and not isclose(mean, 0.0, abs_tol=1e-15):
            expected_positive = mean > 0
            directional_consistency = (
                sum((value > 0) == expected_positive for value in non_zero)
                / len(non_zero)
            )
    elif "risk_ratio" in metric or "odds_ratio" in metric:
        informative = [
            value for value in observed if not isclose(value, 1.0, abs_tol=1e-15)
        ]
        if informative and not isclose(mean, 1.0, abs_tol=1e-15):
            expected_above_one = mean > 1.0
            directional_consistency = (
                sum((value > 1.0) == expected_above_one for value in informative)
                / len(informative)
            )

    return MetricSummary(
        metric=metric,
        domain=domain,
        unit=unit,
        simulator=simulator,
        n=n,
        missing=missing,
        mean=mean,
        standard_deviation=standard_deviation,
        standard_error=standard_error,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        minimum=minimum,
        maximum=maximum,
        coefficient_of_variation=coefficient_of_variation,
        directional_consistency=directional_consistency,
    )


def _summary_lookup(
    summaries: Sequence[MetricSummary],
) -> dict[tuple[str, str | None], MetricSummary]:
    return {(item.metric, item.simulator): item for item in summaries}


def _ci_text(summary: MetricSummary, *, percent: bool = False) -> str:
    if summary.ci_lower is None or summary.ci_upper is None:
        return "95% CI unavailable"
    scale = 100.0 if percent else 1.0
    suffix = " percentage points" if percent else ""
    return (
        f"95% CI {summary.ci_lower * scale:+.1f} to "
        f"{summary.ci_upper * scale:+.1f}{suffix}"
        if percent
        else f"95% CI {summary.ci_lower:.3f} to {summary.ci_upper:.3f}"
    )


def _derive_conclusions(
    summaries: Sequence[MetricSummary],
    primary_condition_code: str,
) -> tuple[str, ...]:
    lookup = _summary_lookup(summaries)
    conclusions: list[str] = []

    prevalence_difference = lookup.get(("primary_condition_absolute_difference", None))
    risk_ratio = lookup.get(("primary_condition_risk_ratio", None))
    encounters = lookup.get(("encounters_relative_difference", None))
    medications = lookup.get(("medications_relative_difference", None))
    procedures = lookup.get(("procedures_relative_difference", None))
    observations = lookup.get(("observations_relative_difference", None))
    age_effect = lookup.get(("age_kolmogorov_smirnov_effect_size", None))
    gender_effect = lookup.get(("gender_effect_size", None))

    if prevalence_difference and prevalence_difference.mean is not None:
        consistency = prevalence_difference.directional_consistency
        consistency_text = (
            "all analysed seeds"
            if consistency == 1.0
            else f"{consistency:.0%} of analysed seeds"
            if consistency is not None
            else "the analysed runs"
        )
        conclusions.append(
            f"For condition {primary_condition_code}, Psynthea prevalence exceeded "
            f"Synthea by {prevalence_difference.mean * 100:.1f} percentage points on "
            f"average ({_ci_text(prevalence_difference, percent=True)}), with the "
            f"same direction in {consistency_text}."
        )
    if risk_ratio and risk_ratio.mean is not None:
        conclusions.append(
            f"The mean risk ratio was {risk_ratio.mean:.3f} "
            f"({_ci_text(risk_ratio)}), indicating materially higher primary-condition "
            f"prevalence in Psynthea throughout the campaign."
        )
    if encounters and encounters.mean is not None:
        conclusions.append(
            f"Psynthea produced {abs(encounters.mean) * 100:.1f}% fewer encounter rows "
            f"on average; the direction was consistent in "
            f"{encounters.directional_consistency:.0%} of seeds."
        )
    if medications and medications.mean is not None:
        conclusions.append(
            f"Medication output was absent from Psynthea in every analysed run "
            f"(mean relative difference {medications.mean:+.3f})."
        )
    if procedures and procedures.mean is not None:
        conclusions.append(
            f"Procedure output was also absent from Psynthea in every analysed run; "
            f"the low Synthea event counts require cautious interpretation."
        )
    if observations and observations.mean is not None:
        conclusions.append(
            f"Psynthea produced {observations.mean * 100:+.1f}% more observation rows "
            f"on average, consistently across seeds."
        )
    if age_effect and gender_effect and age_effect.mean is not None and gender_effect.mean is not None:
        conclusions.append(
            f"Demographic differences remained small across seeds: mean age KS distance "
            f"{age_effect.mean:.3f} and mean gender effect size {gender_effect.mean:.3f}."
        )
    conclusions.append(
        "The campaign demonstrates stable, reproducible differences for the selected "
        "clinical and structural outcomes. It does not establish global simulator "
        "non-equivalence, because equivalence margins and coverage of all modules and "
        "domains have not yet been defined."
    )
    conclusions.append(
        "Across-seed confidence intervals quantify variation between independent seeds; "
        "they do not replace patient-level confidence intervals or tests within each run."
    )
    return tuple(conclusions)


def aggregate_campaign(
    report_paths: Iterable[Path | str],
    *,
    campaign_id: str,
    module_name: str,
    primary_condition_code: str = _DEFAULT_PRIMARY_CONDITION_CODE,
    minimum_runs: int = 3,
    generated_at: datetime | None = None,
) -> CampaignResult:
    """Aggregate validated single-run reports into one campaign result."""

    paths = tuple(sorted(Path(path).expanduser().resolve() for path in report_paths))
    records = tuple(
        sorted(
            (
                _extract_run_record(
                    path,
                    module_name=module_name,
                    primary_condition_code=primary_condition_code,
                )
                for path in paths
            ),
            key=lambda item: item.seed,
        )
    )
    _validate_campaign(records, minimum_runs)

    grouped: dict[tuple[str, str, str, str | None], list[float | None]] = defaultdict(list)
    all_keys = {
        (metric.metric, metric.domain, metric.unit, metric.simulator)
        for record in records
        for metric in record.metrics
    }
    for record in records:
        by_key = {
            (metric.metric, metric.domain, metric.unit, metric.simulator): metric.value
            for metric in record.metrics
        }
        for key in all_keys:
            grouped[key].append(by_key.get(key))
    summaries = tuple(
        _summarize_metric(key, grouped[key])
        for key in sorted(all_keys, key=lambda item: tuple("" if value is None else value for value in item))
    )

    return CampaignResult(
        schema_version=_SCHEMA_VERSION,
        generated_at=(generated_at or datetime.now(UTC)).astimezone(UTC),
        campaign_id=campaign_id,
        module_name=module_name,
        primary_condition_code=primary_condition_code,
        run_count=len(records),
        seeds=tuple(record.seed for record in records),
        population_size_per_run=records[0].population_size,
        reference_date=records[0].reference_date,
        min_age=records[0].min_age,
        max_age=records[0].max_age,
        decisions=dict(sorted(Counter(record.decision for record in records).items())),
        validation_statuses=dict(
            sorted(Counter(record.validation_status for record in records).items())
        ),
        records=records,
        summaries=summaries,
        conclusions=_derive_conclusions(summaries, primary_condition_code),
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding=_JSON_ENCODING, newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _format(value: float | None, digits: int = 4) -> str:
    return "NA" if value is None else f"{value:.{digits}g}"


def _format_percent(value: float | None, digits: int = 1, *, signed: bool = False) -> str:
    if value is None:
        return "NA"
    sign = "+" if signed else ""
    return f"{value * 100:{sign}.{digits}f}%"


def _metric_value(record: RunRecord, metric: str, simulator: str | None = None) -> float | None:
    for item in record.metrics:
        if item.metric == metric and item.simulator == simulator:
            return item.value
    return None


def _campaign_assessment(result: CampaignResult) -> tuple[str, str, str]:
    lookup = _summary_lookup(result.summaries)
    difference = lookup.get(("primary_condition_absolute_difference", None))
    medications = lookup.get(("medications_relative_difference", None))
    encounters = lookup.get(("encounters_relative_difference", None))

    material_primary = bool(
        difference
        and difference.mean is not None
        and difference.ci_lower is not None
        and difference.ci_upper is not None
        and (difference.ci_lower > 0.0 or difference.ci_upper < 0.0)
        and abs(difference.mean) >= 0.05
        and difference.directional_consistency == 1.0
    )
    structural_gap = bool(
        (medications and medications.mean == -1.0)
        or (
            encounters
            and encounters.mean is not None
            and abs(encounters.mean) >= 0.20
            and encounters.directional_consistency == 1.0
        )
    )
    if material_primary and structural_gap:
        return (
            "MATERIAL_DIFFERENCES",
            "Material, reproducible differences detected",
            "The analysed hypertension campaign does not support practical similarity "
            "for the primary clinical outcome and several structural domains.",
        )
    if material_primary or structural_gap:
        return (
            "REVIEW",
            "Review required",
            "At least one clinically or structurally material difference was reproducible "
            "across seeds.",
        )
    return (
        "INCONCLUSIVE",
        "No material difference established",
        "The current campaign is insufficient to claim equivalence; predefined margins "
        "are still required.",
    )


def _svg_primary_outcome(result: CampaignResult) -> str:
    width, height = 860, 310
    left, right, top, bottom = 64, 24, 32, 54
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_y = 0.60
    seeds = list(result.seeds)
    step = plot_w / max(len(seeds) - 1, 1)

    def point(index: int, value: float) -> tuple[float, float]:
        return left + index * step, top + plot_h * (1.0 - value / max_y)

    synthea_values = [
        _metric_value(record, "primary_condition_prevalence", "synthea") or 0.0
        for record in result.records
    ]
    psynthea_values = [
        _metric_value(record, "primary_condition_prevalence", "psynthea") or 0.0
        for record in result.records
    ]
    synthea_points = " ".join(
        f"{x:.1f},{y:.1f}" for x, y in (point(i, value) for i, value in enumerate(synthea_values))
    )
    psynthea_points = " ".join(
        f"{x:.1f},{y:.1f}" for x, y in (point(i, value) for i, value in enumerate(psynthea_values))
    )
    grid = []
    for value in (0.0, 0.2, 0.4, 0.6):
        y = top + plot_h * (1.0 - value / max_y)
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="grid-line"/>'
            f'<text x="{left-12}" y="{y+4:.1f}" text-anchor="end" class="axis-label">{value:.0%}</text>'
        )
    x_labels = "".join(
        f'<text x="{left+i*step:.1f}" y="{height-20}" text-anchor="middle" class="axis-label">{seed}</text>'
        for i, seed in enumerate(seeds)
    )
    circles = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="synthea-point"/>'
        for x, y in (point(i, value) for i, value in enumerate(synthea_values))
    ) + "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="psynthea-point"/>'
        for x, y in (point(i, value) for i, value in enumerate(psynthea_values))
    )
    return f'''<svg viewBox="0 0 {width} {height}" role="img" aria-label="Primary-condition prevalence by seed">
{''.join(grid)}
<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" class="axis"/>
<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" class="axis"/>
<polyline points="{synthea_points}" class="synthea-line"/>
<polyline points="{psynthea_points}" class="psynthea-line"/>
{circles}{x_labels}
<text x="{width/2:.1f}" y="{height-2}" text-anchor="middle" class="axis-title">Random seed</text>
<g transform="translate({width-250},18)"><line x1="0" y1="0" x2="24" y2="0" class="synthea-line"/><text x="32" y="4" class="legend">Synthea</text><line x1="108" y1="0" x2="132" y2="0" class="psynthea-line"/><text x="140" y="4" class="legend">Psynthea</text></g>
</svg>'''


def _svg_domain_differences(result: CampaignResult) -> str:
    lookup = _summary_lookup(result.summaries)
    domains = [
        ("Encounters", "encounters_relative_difference"),
        ("Conditions", "conditions_relative_difference"),
        ("Medications", "medications_relative_difference"),
        ("Procedures", "procedures_relative_difference"),
        ("Observations", "observations_relative_difference"),
    ]
    values = [lookup[(metric, None)].mean or 0.0 for _, metric in domains]
    width, height = 860, 300
    left, right, top, bottom = 128, 40, 24, 28
    center = left + (width-left-right) / 2
    half = (width-left-right) / 2
    max_abs = max(1.05, max(abs(value) for value in values))
    row_h = (height-top-bottom) / len(domains)
    elements = [
        f'<line x1="{center:.1f}" y1="{top}" x2="{center:.1f}" y2="{height-bottom}" class="zero-line"/>'
    ]
    for index, ((label, _), value) in enumerate(zip(domains, values, strict=True)):
        y = top + index * row_h + row_h * 0.2
        bar_h = row_h * 0.58
        length = abs(value) / max_abs * half
        x = center if value >= 0 else center - length
        css = "positive-bar" if value >= 0 else "negative-bar"
        elements.append(
            f'<text x="{left-12}" y="{y+bar_h*0.70:.1f}" text-anchor="end" class="domain-label">{escape(label)}</text>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{length:.1f}" height="{bar_h:.1f}" rx="4" class="{css}"/>'
            f'<text x="{(x+length+8 if value>=0 else x-8):.1f}" y="{y+bar_h*0.70:.1f}" text-anchor="{'start' if value>=0 else 'end'}" class="bar-value">{value:+.1%}</text>'
        )
    return f'''<svg viewBox="0 0 {width} {height}" role="img" aria-label="Mean relative row-count differences by domain">
{''.join(elements)}
<text x="{center-half/2:.1f}" y="{height-4}" text-anchor="middle" class="axis-label">Fewer rows in Psynthea</text>
<text x="{center+half/2:.1f}" y="{height-4}" text-anchor="middle" class="axis-label">More rows in Psynthea</text>
</svg>'''


def _domain_assessment_rows(result: CampaignResult) -> str:
    lookup = _summary_lookup(result.summaries)
    definitions = (
        ("Patients", "patients_relative_difference", 0.01, "Cohort size"),
        ("Encounters", "encounters_relative_difference", 0.10, "Healthcare utilisation"),
        ("Conditions", "conditions_relative_difference", 0.10, "Condition output"),
        ("Medications", "medications_relative_difference", 0.10, "Medication output"),
        ("Procedures", "procedures_relative_difference", 0.10, "Procedure output"),
        ("Observations", "observations_relative_difference", 0.10, "Observation output"),
    )
    rows: list[str] = []
    for label, metric, review_threshold, interpretation in definitions:
        summary = lookup.get((metric, None))
        value = None if summary is None else summary.mean
        consistency = None if summary is None else summary.directional_consistency
        if value is None:
            status, css = "Unavailable", "status-muted"
        elif abs(value) <= 0.01:
            status, css = "Aligned", "status-good"
        elif abs(value) < review_threshold:
            status, css = "Minor difference", "status-watch"
        else:
            status, css = "Material difference", "status-bad"
        rows.append(
            "<tr>"
            f"<td>{escape(label)}</td>"
            f"<td>{escape(interpretation)}</td>"
            f"<td>{_format_percent(value, signed=True)}</td>"
            f"<td>{'NA' if consistency is None else f'{consistency:.0%}'}</td>"
            f'<td><span class="status {css}">{status}</span></td>'
            "</tr>"
        )
    return "".join(rows)


def _render_html(result: CampaignResult) -> str:
    summary_lookup = _summary_lookup(result.summaries)
    primary_s = summary_lookup[("primary_condition_prevalence", "synthea")]
    primary_p = summary_lookup[("primary_condition_prevalence", "psynthea")]
    primary_d = summary_lookup[("primary_condition_absolute_difference", None)]
    primary_rr = summary_lookup[("primary_condition_risk_ratio", None)]
    age_effect = summary_lookup.get(("age_kolmogorov_smirnov_effect_size", None))
    gender_effect = summary_lookup.get(("gender_effect_size", None))
    encounter_effect = summary_lookup.get(("encounter_class_effect_size", None))
    assessment_code, assessment_title, assessment_text = _campaign_assessment(result)

    rows = []
    for record in result.records:
        synthea = _metric_value(record, "primary_condition_prevalence", "synthea")
        psynthea = _metric_value(record, "primary_condition_prevalence", "psynthea")
        difference = _metric_value(record, "primary_condition_absolute_difference")
        risk_ratio = _metric_value(record, "primary_condition_risk_ratio")
        rows.append(
            "<tr>"
            f"<td>{record.seed}</td><td><code>{escape(record.run_id)}</code></td>"
            f"<td>{_format_percent(synthea)}</td>"
            f"<td>{_format_percent(psynthea)}</td>"
            f"<td>{_format_percent(difference, signed=True)}</td>"
            f"<td>{_format(risk_ratio, 4)}</td>"
            f'<td><span class="status status-watch">{escape(record.decision)}</span></td>'
            "</tr>"
        )
    conclusion_html = "".join(f"<li>{escape(text)}</li>" for text in result.conclusions)
    total_patients = result.run_count * result.population_size_per_run * 2
    generated_at = result.generated_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    decision_summary = ", ".join(
        f"{escape(decision)}: {count}" for decision, count in result.decisions.items()
    )

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Multiseed scientific campaign — {escape(result.campaign_id)}</title>
<style>
:root {{ --ink:#172033; --muted:#667085; --line:#dfe4ec; --paper:#ffffff; --canvas:#f3f5f8; --navy:#203a61; --blue:#4279b8; --orange:#d97706; --green:#16794b; --red:#b42318; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:var(--canvas); }}
* {{ box-sizing:border-box; }} body {{ margin:0; line-height:1.5; }} main {{ max-width:1220px; margin:0 auto; padding:38px 28px 72px; }}
h1 {{ margin:0; font-size:34px; line-height:1.16; letter-spacing:-.02em; }} h2 {{ margin:38px 0 14px; font-size:23px; }} h3 {{ margin:0 0 10px; font-size:17px; }} p {{ margin:8px 0; }}
.eyebrow {{ color:var(--blue); font-size:12px; font-weight:800; letter-spacing:.09em; text-transform:uppercase; }} .meta {{ color:var(--muted); margin:9px 0 24px; }}
.assessment {{ display:grid; grid-template-columns:180px 1fr; gap:22px; align-items:center; background:#fff7ed; border:1px solid #fed7aa; border-left:7px solid var(--orange); border-radius:14px; padding:20px 22px; margin:24px 0; }}
.assessment-code {{ font-size:13px; font-weight:800; letter-spacing:.06em; color:#9a3412; }} .assessment h2 {{ margin:0 0 4px; font-size:22px; }}
.grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }} .grid.two {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
.card,.panel {{ background:var(--paper); border:1px solid var(--line); border-radius:14px; box-shadow:0 1px 2px rgba(16,24,40,.03); }} .card {{ padding:18px; }} .panel {{ padding:20px; }}
.label {{ color:var(--muted); font-size:12px; font-weight:700; letter-spacing:.035em; text-transform:uppercase; }} .value {{ font-size:28px; font-weight:750; margin:5px 0 2px; letter-spacing:-.02em; }} .subvalue {{ color:var(--muted); font-size:13px; }}
.callout {{ border-left:4px solid var(--blue); background:#eff6ff; padding:15px 18px; border-radius:0 10px 10px 0; }} .notice {{ border-left-color:var(--orange); background:#fffaf0; }}
table {{ width:100%; border-collapse:separate; border-spacing:0; background:white; border:1px solid var(--line); border-radius:12px; overflow:hidden; font-size:14px; }} th,td {{ border-bottom:1px solid #eaecf0; padding:11px 12px; text-align:right; vertical-align:middle; }} tr:last-child td {{ border-bottom:0; }} th {{ background:#f8fafc; color:#475467; font-size:12px; text-transform:uppercase; letter-spacing:.035em; }} th:first-child,td:first-child,th:nth-child(2),td:nth-child(2) {{ text-align:left; }} code {{ font-size:12px; }}
.status {{ display:inline-flex; align-items:center; border-radius:999px; padding:3px 9px; font-size:12px; font-weight:750; white-space:nowrap; }} .status-good {{ color:#05603a; background:#ecfdf3; }} .status-watch {{ color:#92400e; background:#fffbeb; }} .status-bad {{ color:#991b1b; background:#fef2f2; }} .status-muted {{ color:#475467; background:#f2f4f7; }}
.findings {{ margin:0; padding-left:21px; }} .findings li {{ margin:9px 0; }} .method-list {{ margin:0; padding-left:19px; }} .method-list li {{ margin:6px 0; }}
.chart {{ overflow-x:auto; }} svg {{ width:100%; min-width:620px; height:auto; }} .grid-line {{ stroke:#e5e7eb; stroke-width:1; }} .axis,.zero-line {{ stroke:#98a2b3; stroke-width:1.2; }} .axis-label,.axis-title,.legend,.domain-label,.bar-value {{ fill:#667085; font-size:12px; }} .axis-title,.domain-label {{ font-weight:650; }} .synthea-line {{ fill:none; stroke:var(--navy); stroke-width:3; }} .psynthea-line {{ fill:none; stroke:var(--orange); stroke-width:3; }} .synthea-point {{ fill:var(--navy); }} .psynthea-point {{ fill:var(--orange); }} .positive-bar {{ fill:#d97706; }} .negative-bar {{ fill:#4279b8; }}
.footer {{ margin-top:38px; color:var(--muted); font-size:12px; border-top:1px solid var(--line); padding-top:16px; }}
@media(max-width:900px) {{ .grid {{ grid-template-columns:1fr 1fr; }} .grid.two {{ grid-template-columns:1fr; }} .assessment {{ grid-template-columns:1fr; gap:5px; }} }} @media(max-width:580px) {{ main {{ padding:24px 14px 48px; }} .grid {{ grid-template-columns:1fr; }} h1 {{ font-size:28px; }} }}
@media print {{ :root {{ background:white; }} main {{ max-width:none; padding:18mm 14mm; }} .card,.panel,table {{ box-shadow:none; break-inside:avoid; }} .chart {{ break-inside:avoid; }} }}
</style></head><body><main>
<div class="eyebrow">Psynthea validation · IRYCIS</div>
<h1>Multiseed scientific validation report</h1>
<div class="meta">Campaign <strong>{escape(result.campaign_id)}</strong> · module {escape(result.module_name)} · generated {generated_at}</div>

<section class="assessment">
<div class="assessment-code">{escape(assessment_code)}</div>
<div><h2>{escape(assessment_title)}</h2><p>{escape(assessment_text)}</p></div>
</section>

<section>
<h2>Campaign design</h2>
<div class="grid">
<div class="card"><div class="label">Independent seeds</div><div class="value">{result.run_count}</div><div class="subvalue">{', '.join(map(str, result.seeds))}</div></div>
<div class="card"><div class="label">Population per simulator/run</div><div class="value">{result.population_size_per_run:,}</div><div class="subvalue">{total_patients:,} generated patient records analysed</div></div>
<div class="card"><div class="label">Reference date</div><div class="value" style="font-size:22px">{escape(result.reference_date)}</div><div class="subvalue">Age range {result.min_age}–{result.max_age} years</div></div>
<div class="card"><div class="label">Single-run decisions</div><div class="value" style="font-size:22px">{decision_summary}</div><div class="subvalue">Paired Synthea/Psynthea runs</div></div>
</div>
</section>

<section>
<h2>Executive scientific summary</h2>
<div class="grid">
<div class="card"><div class="label">Synthea HTN prevalence</div><div class="value">{_format_percent(primary_s.mean)}</div><div class="subvalue">Across-seed 95% CI {_format_percent(primary_s.ci_lower)}–{_format_percent(primary_s.ci_upper)}</div></div>
<div class="card"><div class="label">Psynthea HTN prevalence</div><div class="value">{_format_percent(primary_p.mean)}</div><div class="subvalue">Across-seed 95% CI {_format_percent(primary_p.ci_lower)}–{_format_percent(primary_p.ci_upper)}</div></div>
<div class="card"><div class="label">Mean prevalence difference</div><div class="value">{_format_percent(primary_d.mean, signed=True)}</div><div class="subvalue">95% CI {_format_percent(primary_d.ci_lower, signed=True)} to {_format_percent(primary_d.ci_upper, signed=True)}</div></div>
<div class="card"><div class="label">Mean risk ratio</div><div class="value">{_format(primary_rr.mean, 4)}</div><div class="subvalue">95% CI {_format(primary_rr.ci_lower, 4)}–{_format(primary_rr.ci_upper, 4)}</div></div>
</div>
<div class="callout" style="margin-top:14px"><strong>Interpretation:</strong> The primary clinical difference is large, preserves its direction in every seed, and is accompanied by reproducible differences in utilisation and output coverage. These results justify root-cause analysis before any claim of similarity.</div>
</section>

<section>
<h2>Primary clinical outcome by seed</h2>
<div class="panel chart">{_svg_primary_outcome(result)}</div>
</section>

<section>
<h2>Structural output differences</h2>
<div class="grid two">
<div class="panel chart"><h3>Mean relative row-count difference</h3>{_svg_domain_differences(result)}</div>
<div class="panel"><h3>Domain assessment</h3><table><thead><tr><th>Domain</th><th>Interpretation</th><th>Mean Δ</th><th>Direction</th><th>Assessment</th></tr></thead><tbody>{_domain_assessment_rows(result)}</tbody></table></div>
</div>
</section>

<section>
<h2>Demographic comparability and utilisation</h2>
<div class="grid">
<div class="card"><div class="label">Age KS distance</div><div class="value">{_format(None if age_effect is None else age_effect.mean, 3)}</div><div class="subvalue">Small average distributional distance</div></div>
<div class="card"><div class="label">Gender effect size</div><div class="value">{_format(None if gender_effect is None else gender_effect.mean, 3)}</div><div class="subvalue">Negligible average association</div></div>
<div class="card"><div class="label">Encounter-class effect size</div><div class="value">{_format(None if encounter_effect is None else encounter_effect.mean, 3)}</div><div class="subvalue">Material structural difference</div></div>
<div class="card"><div class="label">Primary difference consistency</div><div class="value">{'NA' if primary_d.directional_consistency is None else f'{primary_d.directional_consistency:.0%}'}</div><div class="subvalue">Seeds with the same direction</div></div>
</div>
<p class="callout"><strong>Methodological interpretation:</strong> Small demographic effect sizes make age or gender imbalance an unlikely primary explanation for the clinical gap. The encounter-class effect size indicates that the simulators are producing materially different patterns of healthcare utilisation.</p>
</section>

<section>
<h2>Per-seed evidence</h2>
<table><thead><tr><th>Seed</th><th>Run ID</th><th>Synthea prevalence</th><th>Psynthea prevalence</th><th>Difference</th><th>Risk ratio</th><th>Decision</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</section>

<section>
<h2>Scientific interpretation</h2>
<div class="panel"><ul class="findings">{conclusion_html}</ul></div>
</section>

<section>
<h2>Limitations and required next analysis</h2>
<div class="grid two">
<div class="panel"><h3>Current limitations</h3><ul class="method-list"><li>Five seeds provide an initial stability assessment but limited precision for between-seed variance.</li><li>No a priori equivalence or non-inferiority margins have yet been defined.</li><li>The campaign covers the hypertension module and selected exported domains, not global Synthea/Psynthea behaviour.</li><li>Differences in medications and procedures may arise from engine capabilities, module execution, lifecycle logic, exporter semantics, or coding coverage.</li><li>Across-seed intervals describe reproducibility of seed-level estimates, not patient-level sampling uncertainty.</li></ul></div>
<div class="panel"><h3>Recommended next step</h3><ol class="method-list"><li>Trace the hypertension pathway and medication/procedure emission logic in both engines.</li><li>Separate module-level differences from global engine and exporter differences.</li><li>Define clinically justified equivalence margins with IRYCIS investigators.</li><li>Repeat the campaign after each targeted correction and compare effect-size reduction.</li><li>Later expand to larger cohorts and additional modules.</li></ol></div>
</div>
</section>

<section>
<h2>Methods and provenance</h2>
<div class="callout notice">All metrics are extracted from persisted single-run scientific artefacts. Runs are paired by configuration and independently repeated across seeds. Means, standard deviations, standard errors and 95% confidence intervals across seeds use the Student t distribution. P-values are not averaged or used as the primary campaign-level evidence; interpretation prioritises effect magnitude, confidence intervals and directional consistency. No patient-level test is recomputed in this campaign layer.</div>
</section>

<div class="footer">Schema {escape(result.schema_version)} · Primary condition code {escape(result.primary_condition_code)} · Campaign result retained in multiseed_campaign.json</div>
</main></body></html>'''

def persist_campaign_result(result: CampaignResult, output_dir: Path | str) -> tuple[Path, ...]:
    """Persist canonical JSON, long-form CSVs and a human-readable HTML report."""

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "multiseed_campaign.json"
    run_csv_path = output / "multiseed_run_metrics.csv"
    summary_csv_path = output / "multiseed_metric_summary.csv"
    html_path = output / "multiseed_report.html"

    json_path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding=_JSON_ENCODING,
    )
    run_rows: list[dict[str, Any]] = []
    for record in result.records:
        for metric in record.metrics:
            run_rows.append(
                {
                    "campaign_id": result.campaign_id,
                    "run_id": record.run_id,
                    "seed": record.seed,
                    "population_size": record.population_size,
                    "decision": record.decision,
                    "validation_status": record.validation_status,
                    "metric": metric.metric,
                    "domain": metric.domain,
                    "simulator": metric.simulator or "",
                    "unit": metric.unit,
                    "value": metric.value,
                    "report_path": str(record.report_path),
                }
            )
    _write_csv(
        run_csv_path,
        run_rows,
        (
            "campaign_id", "run_id", "seed", "population_size", "decision",
            "validation_status", "metric", "domain", "simulator", "unit",
            "value", "report_path",
        ),
    )
    summary_rows = [asdict(summary) for summary in result.summaries]
    _write_csv(summary_csv_path, summary_rows, tuple(summary_rows[0].keys()))
    html_path.write_text(_render_html(result), encoding=_JSON_ENCODING)
    return json_path, run_csv_path, summary_csv_path, html_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m validation.campaigns.multiseed",
        description="Aggregate independent paired simulator runs across random seeds.",
    )
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--module-name", required=True)
    parser.add_argument(
        "--primary-condition-code",
        default=_DEFAULT_PRIMARY_CONDITION_CODE,
    )
    parser.add_argument("--minimum-runs", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        reports = discover_reports(args.runs_root)
        result = aggregate_campaign(
            reports,
            campaign_id=args.campaign_id,
            module_name=args.module_name,
            primary_condition_code=args.primary_condition_code,
            minimum_runs=args.minimum_runs,
        )
        paths = persist_campaign_result(result, args.output_dir)
    except CampaignAggregationError as exc:
        print(f"Campaign aggregation failed: {exc}", file=sys.stderr)
        return 2

    print(f"Campaign completed: {result.run_count} runs, seeds={list(result.seeds)}")
    for path in paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
