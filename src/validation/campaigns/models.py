"""Immutable models for cross-run scientific campaign aggregation.

Campaign analysis is intentionally separated from single-run validation.  A
single run establishes a paired comparison for one random seed; a campaign
summarises the reproducibility and stability of those paired comparisons across
independent seeds without re-running clinical or statistical tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "CampaignResult",
    "MetricSummary",
    "RunMetric",
    "RunRecord",
]


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _finite_or_none(value: float | int | None, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric or None.")
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"{field_name} must be finite.")
    return numeric


@dataclass(frozen=True, slots=True)
class RunMetric:
    """One scalar measurement extracted from one paired simulator run."""

    metric: str
    value: float | None
    unit: str
    domain: str
    simulator: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", _text(self.metric, "metric"))
        object.__setattr__(self, "unit", _text(self.unit, "unit"))
        object.__setattr__(self, "domain", _text(self.domain, "domain"))
        if self.simulator is not None:
            object.__setattr__(self, "simulator", _text(self.simulator, "simulator"))
        object.__setattr__(self, "value", _finite_or_none(self.value, "value"))


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Validated metadata and scalar measurements for one campaign run."""

    run_id: str
    experiment_id: str
    seed: int
    population_size: int
    module_name: str
    reference_date: str
    min_age: int
    max_age: int
    decision: str
    validation_status: str
    report_path: Path
    metrics: tuple[RunMetric, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        object.__setattr__(self, "experiment_id", _text(self.experiment_id, "experiment_id"))
        object.__setattr__(self, "module_name", _text(self.module_name, "module_name"))
        object.__setattr__(self, "reference_date", _text(self.reference_date, "reference_date"))
        object.__setattr__(self, "decision", _text(self.decision, "decision"))
        object.__setattr__(
            self,
            "validation_status",
            _text(self.validation_status, "validation_status"),
        )
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer.")
        if isinstance(self.population_size, bool) or not isinstance(self.population_size, int):
            raise TypeError("population_size must be an integer.")
        if self.population_size <= 0:
            raise ValueError("population_size must be positive.")
        if self.min_age < 0 or self.max_age < self.min_age:
            raise ValueError("age bounds are invalid.")
        path = Path(self.report_path)
        object.__setattr__(self, "report_path", path)
        object.__setattr__(self, "metrics", tuple(self.metrics))


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """Across-seed descriptive summary for one scalar campaign metric."""

    metric: str
    domain: str
    unit: str
    simulator: str | None
    n: int
    missing: int
    mean: float | None
    standard_deviation: float | None
    standard_error: float | None
    ci_lower: float | None
    ci_upper: float | None
    minimum: float | None
    maximum: float | None
    coefficient_of_variation: float | None
    directional_consistency: float | None


@dataclass(frozen=True, slots=True)
class CampaignResult:
    """Complete deterministic result of one multiseed aggregation."""

    schema_version: str
    generated_at: datetime
    campaign_id: str
    module_name: str
    primary_condition_code: str
    run_count: int
    seeds: tuple[int, ...]
    population_size_per_run: int
    reference_date: str
    min_age: int
    max_age: int
    decisions: Mapping[str, int]
    validation_statuses: Mapping[str, int]
    records: tuple[RunRecord, ...]
    summaries: tuple[MetricSummary, ...]
    conclusions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation with stable tuple ordering."""

        payload = asdict(self)
        payload["generated_at"] = self.generated_at.astimezone(UTC).isoformat()
        for record in payload["records"]:
            record["report_path"] = str(record["report_path"])
        return payload
