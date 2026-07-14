"""
Canonical models for scientific interpretation of validation evidence.

The interpretation layer never reasons directly over arbitrary dictionaries,
CSV rows or report text. Pipeline outputs must first be normalized into the
models defined here. This provides a stable, auditable contract between the
validation engine, deterministic interpretation rules and report renderers.

The models deliberately distinguish:

* observed evidence from interpretation;
* severity from confidence;
* unavailable data from observed zero values;
* causal hypotheses from demonstrated causes;
* failed validation from inconclusive or non-applicable validation.

No interpretation rules or reporting logic belong in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from math import isfinite
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Mapping, Sequence, TypeVar

__all__ = [
    "Confidence",
    "EvidenceAvailability",
    "EvidenceReference",
    "EvidenceRole",
    "EvidenceStrength",
    "EvidenceValue",
    "FindingStatus",
    "InterpretationFinding",
    "InterpretationReport",
    "Recommendation",
    "RecommendationPriority",
    "RootCauseHypothesis",
    "Severity",
]


# =============================================================================
# Enumerations
# =============================================================================


class FindingStatus(str, Enum):
    """Scientific decision assigned to an interpreted validation finding."""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"
    NOT_EVALUATED = "not_evaluated"


class Severity(str, Enum):
    """Potential impact of a finding on validation or downstream research use."""

    INFO = "info"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(str, Enum):
    """Confidence in the interpretation, independently of finding severity."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class EvidenceStrength(str, Enum):
    """Strength of the evidence supporting an interpretation."""

    INSUFFICIENT = "insufficient"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class EvidenceAvailability(str, Enum):
    """Availability state of a metric or source value.

    ``AVAILABLE`` includes legitimate zero values. The remaining states must
    never be converted silently into zero because they describe different
    failure or applicability conditions.
    """

    AVAILABLE = "available"
    SOURCE_MISSING = "source_missing"
    FIELD_MISSING = "field_missing"
    EMPTY = "empty"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"
    NOT_COMPUTED = "not_computed"


class EvidenceRole(str, Enum):
    """Role played by one evidence item in a finding."""

    PRIMARY = "primary"
    SUPPORTING = "supporting"
    CONTRADICTORY = "contradictory"
    CONTEXT = "context"
    LIMITATION = "limitation"


class RecommendationPriority(str, Enum):
    """Execution priority assigned to a recommended action."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# =============================================================================
# Internal validation helpers
# =============================================================================


_IDENTIFIER_PATTERN = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")

_EnumT = TypeVar("_EnumT", bound=Enum)



def _require_enum(value: _EnumT, enum_type: type[_EnumT], field_name: str) -> _EnumT:
    """Require an actual enum member; reject raw strings at model boundaries."""

    if not isinstance(value, enum_type):
        raise TypeError(
            f"{field_name} must be a {enum_type.__name__} member, "
            f"got {type(value).__name__}."
        )
    return value


def _deep_freeze(value: Any) -> Any:
    """Recursively detach and freeze nested containers used as metadata."""

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _normalize_model_tuple(
    values: Sequence[Any],
    expected_type: type[Any],
    field_name: str,
) -> tuple[Any, ...]:
    """Detach a model collection and validate every member type."""

    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {expected_type.__name__} values.")
    normalized = tuple(values)
    for index, value in enumerate(normalized):
        if not isinstance(value, expected_type):
            raise TypeError(
                f"{field_name}[{index}] must be {expected_type.__name__}, "
                f"got {type(value).__name__}."
            )
    return normalized


def _require_text(value: str, field_name: str) -> str:
    """Return normalized non-empty text or raise a descriptive error."""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _require_identifier(value: str, field_name: str) -> str:
    """Validate a stable identifier used for rules, metrics and findings."""

    normalized = _require_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, '.', '_', ':', or '-'."
        )
    return normalized


def _validate_probability(value: float | None, field_name: str) -> None:
    """Validate an optional probability-like score in the closed interval [0, 1]."""

    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric or None.")
    if not isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{field_name} must be finite and between 0 and 1.")


def _validate_non_negative_integer(value: int | None, field_name: str) -> None:
    """Validate an optional count or denominator."""

    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer or None.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")


def _normalize_datetime(value: datetime | None, field_name: str) -> datetime | None:
    """Require timezone-aware datetimes and normalize them to UTC."""

    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    """Copy a mapping to prevent external mutation after model construction."""

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return _deep_freeze(dict(value))


def _normalize_text_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    """Normalize a sequence of strings while preserving order and uniqueness."""

    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = _require_text(value, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


def _serialize(value: Any) -> Any:
    """Convert nested model values into stable JSON-compatible structures."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_serialize(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    return value


# =============================================================================
# Evidence models
# =============================================================================


@dataclass(frozen=True, slots=True)
class EvidenceValue:
    """One normalized value produced by the validation pipeline.

    ``value=0`` with ``availability=AVAILABLE`` is a valid observation.
    Missing tables, missing fields, empty outputs and failed computations must
    instead use the corresponding availability state.
    """

    metric_id: str
    name: str
    availability: EvidenceAvailability
    value: Any = None
    source: str | None = None
    unit: str | None = None
    sample_size: int | None = None
    denominator: int | None = None
    observed_at: datetime | None = None
    description: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _require_identifier(self.metric_id, "metric_id"))
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        _require_enum(self.availability, EvidenceAvailability, "availability")

        if self.source is not None:
            object.__setattr__(self, "source", _require_text(self.source, "source"))
        if self.unit is not None:
            object.__setattr__(self, "unit", _require_text(self.unit, "unit"))
        if self.description is not None:
            object.__setattr__(
                self,
                "description",
                _require_text(self.description, "description"),
            )

        _validate_non_negative_integer(self.sample_size, "sample_size")
        _validate_non_negative_integer(self.denominator, "denominator")
        object.__setattr__(
            self,
            "observed_at",
            _normalize_datetime(self.observed_at, "observed_at"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.availability is EvidenceAvailability.AVAILABLE and self.value is None:
            raise ValueError("Available evidence must contain a value; None is not an observation.")
        if self.availability is not EvidenceAvailability.AVAILABLE and self.value is not None:
            raise ValueError(
                "Unavailable evidence must use value=None to prevent accidental interpretation."
            )

    @property
    def is_available(self) -> bool:
        """Return whether this evidence contains an observed or computed value."""

        return self.availability is EvidenceAvailability.AVAILABLE

    @property
    def is_zero(self) -> bool:
        """Return whether available numeric evidence is exactly zero."""

        return (
            self.is_available
            and isinstance(self.value, (int, float))
            and not isinstance(self.value, bool)
            and float(self.value) == 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable serializable representation."""

        return {
            "metric_id": self.metric_id,
            "name": self.name,
            "availability": self.availability.value,
            "value": _serialize(self.value),
            "source": self.source,
            "unit": self.unit,
            "sample_size": self.sample_size,
            "denominator": self.denominator,
            "observed_at": _serialize(self.observed_at),
            "description": self.description,
            "metadata": _serialize(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Traceable reference from a finding to one normalized evidence item."""

    metric_id: str
    role: EvidenceRole = EvidenceRole.SUPPORTING
    rationale: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _require_identifier(self.metric_id, "metric_id"))
        _require_enum(self.role, EvidenceRole, "role")
        if self.rationale is not None:
            object.__setattr__(
                self,
                "rationale",
                _require_text(self.rationale, "rationale"),
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable serializable representation."""

        return {
            "metric_id": self.metric_id,
            "role": self.role.value,
            "rationale": self.rationale,
        }


# =============================================================================
# Interpretation support models
# =============================================================================


@dataclass(frozen=True, slots=True)
class RootCauseHypothesis:
    """Explicitly non-proven explanation for an observed finding."""

    hypothesis_id: str
    statement: str
    plausibility: Confidence
    rationale: str
    verification_steps: tuple[str, ...] = ()
    supporting_evidence: tuple[EvidenceReference, ...] = ()
    competing_hypotheses: tuple[str, ...] = ()
    probability: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hypothesis_id",
            _require_identifier(self.hypothesis_id, "hypothesis_id"),
        )
        object.__setattr__(self, "statement", _require_text(self.statement, "statement"))
        _require_enum(self.plausibility, Confidence, "plausibility")
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))
        object.__setattr__(
            self,
            "verification_steps",
            _normalize_text_tuple(self.verification_steps, "verification_steps"),
        )
        object.__setattr__(
            self,
            "competing_hypotheses",
            _normalize_text_tuple(self.competing_hypotheses, "competing_hypotheses"),
        )
        object.__setattr__(self, "supporting_evidence", _normalize_model_tuple(self.supporting_evidence, EvidenceReference, "supporting_evidence"))
        _validate_probability(self.probability, "probability")

        if self.probability is not None and self.plausibility is Confidence.VERY_LOW:
            if self.probability > 0.25:
                raise ValueError(
                    "A VERY_LOW plausibility hypothesis cannot have probability above 0.25."
                )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable serializable representation."""

        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "plausibility": self.plausibility.value,
            "rationale": self.rationale,
            "verification_steps": list(self.verification_steps),
            "supporting_evidence": [item.to_dict() for item in self.supporting_evidence],
            "competing_hypotheses": list(self.competing_hypotheses),
            "probability": self.probability,
        }


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Concrete, verifiable action derived from a finding."""

    recommendation_id: str
    action: str
    priority: RecommendationPriority
    rationale: str
    expected_outcome: str
    verification: str
    owner: str | None = None
    blocking: bool = False
    related_hypothesis_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "recommendation_id",
            _require_identifier(self.recommendation_id, "recommendation_id"),
        )
        object.__setattr__(self, "action", _require_text(self.action, "action"))
        _require_enum(self.priority, RecommendationPriority, "priority")
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))
        object.__setattr__(
            self,
            "expected_outcome",
            _require_text(self.expected_outcome, "expected_outcome"),
        )
        object.__setattr__(
            self,
            "verification",
            _require_text(self.verification, "verification"),
        )
        if self.owner is not None:
            object.__setattr__(self, "owner", _require_text(self.owner, "owner"))
        related = tuple(
            _require_identifier(value, "related_hypothesis_ids")
            for value in self.related_hypothesis_ids
        )
        if len(related) != len(set(related)):
            raise ValueError("related_hypothesis_ids must not contain duplicates.")
        object.__setattr__(self, "related_hypothesis_ids", related)

    def to_dict(self) -> dict[str, Any]:
        """Return a stable serializable representation."""

        return {
            "recommendation_id": self.recommendation_id,
            "action": self.action,
            "priority": self.priority.value,
            "rationale": self.rationale,
            "expected_outcome": self.expected_outcome,
            "verification": self.verification,
            "owner": self.owner,
            "blocking": self.blocking,
            "related_hypothesis_ids": list(self.related_hypothesis_ids),
        }


# =============================================================================
# Finding and report models
# =============================================================================


@dataclass(frozen=True, slots=True)
class InterpretationFinding:
    """Auditable scientific interpretation produced by one deterministic rule."""

    finding_id: str
    rule_id: str
    domain: str
    title: str
    status: FindingStatus
    severity: Severity
    confidence: Confidence
    evidence_strength: EvidenceStrength
    observation: str
    interpretation: str
    impact: str
    evidence: tuple[EvidenceReference, ...] = ()
    hypotheses: tuple[RootCauseHypothesis, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    limitations: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    confidence_score: float | None = None
    clinically_relevant: bool | None = None
    blocks_research_use: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _require_identifier(self.finding_id, "finding_id"))
        object.__setattr__(self, "rule_id", _require_identifier(self.rule_id, "rule_id"))
        object.__setattr__(self, "domain", _require_identifier(self.domain, "domain"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        _require_enum(self.status, FindingStatus, "status")
        _require_enum(self.severity, Severity, "severity")
        _require_enum(self.confidence, Confidence, "confidence")
        _require_enum(self.evidence_strength, EvidenceStrength, "evidence_strength")
        object.__setattr__(self, "observation", _require_text(self.observation, "observation"))
        object.__setattr__(
            self,
            "interpretation",
            _require_text(self.interpretation, "interpretation"),
        )
        object.__setattr__(self, "impact", _require_text(self.impact, "impact"))
        object.__setattr__(
            self,
            "limitations",
            _normalize_text_tuple(self.limitations, "limitations"),
        )
        object.__setattr__(self, "tags", _normalize_text_tuple(self.tags, "tags"))
        object.__setattr__(
            self,
            "created_at",
            _normalize_datetime(self.created_at, "created_at"),
        )
        _validate_probability(self.confidence_score, "confidence_score")
        object.__setattr__(self, "evidence", _normalize_model_tuple(self.evidence, EvidenceReference, "evidence"))
        object.__setattr__(self, "hypotheses", _normalize_model_tuple(self.hypotheses, RootCauseHypothesis, "hypotheses"))
        object.__setattr__(self, "recommendations", _normalize_model_tuple(self.recommendations, Recommendation, "recommendations"))

        evidence_ids = [item.metric_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("A finding cannot reference the same metric more than once.")

        hypothesis_ids = [item.hypothesis_id for item in self.hypotheses]
        if len(hypothesis_ids) != len(set(hypothesis_ids)):
            raise ValueError("Hypothesis identifiers must be unique within a finding.")

        recommendation_ids = [item.recommendation_id for item in self.recommendations]
        if len(recommendation_ids) != len(set(recommendation_ids)):
            raise ValueError("Recommendation identifiers must be unique within a finding.")

        known_hypotheses = set(hypothesis_ids)
        for recommendation in self.recommendations:
            unknown = set(recommendation.related_hypothesis_ids) - known_hypotheses
            if unknown:
                raise ValueError(
                    "Recommendation references unknown hypothesis identifiers: "
                    f"{sorted(unknown)}."
                )

        evidence_optional_statuses = {
            FindingStatus.NOT_APPLICABLE,
            FindingStatus.NOT_EVALUATED,
        }
        if not self.evidence and self.status not in evidence_optional_statuses:
            raise ValueError(
                "Evaluated findings must reference at least one evidence item."
            )

        if self.status is FindingStatus.PASS and self.blocks_research_use:
            raise ValueError("A passing finding cannot block research use.")
        if self.status in {FindingStatus.NOT_APPLICABLE, FindingStatus.NOT_EVALUATED}:
            if self.blocks_research_use:
                raise ValueError("Non-evaluated findings cannot block research use directly.")
            if self.severity is not Severity.INFO:
                raise ValueError("NOT_APPLICABLE and NOT_EVALUATED findings must use INFO severity.")
        if self.status is FindingStatus.NOT_APPLICABLE and self.clinically_relevant:
            raise ValueError("A non-applicable finding cannot be clinically relevant.")
        if self.evidence_strength is EvidenceStrength.INSUFFICIENT and self.status in {
            FindingStatus.PASS,
            FindingStatus.FAIL,
        }:
            raise ValueError(
                "PASS and FAIL require more than insufficient evidence; use INCONCLUSIVE."
            )

    @property
    def is_actionable(self) -> bool:
        """Return whether the finding contains at least one recommended action."""

        return bool(self.recommendations)

    @property
    def is_conclusive(self) -> bool:
        """Return whether the finding expresses a conclusive evaluated decision."""

        return self.status in {
            FindingStatus.PASS,
            FindingStatus.WARNING,
            FindingStatus.FAIL,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a stable serializable representation."""

        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "domain": self.domain,
            "title": self.title,
            "status": self.status.value,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "confidence_score": self.confidence_score,
            "evidence_strength": self.evidence_strength.value,
            "observation": self.observation,
            "interpretation": self.interpretation,
            "impact": self.impact,
            "evidence": [item.to_dict() for item in self.evidence],
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "recommendations": [item.to_dict() for item in self.recommendations],
            "limitations": list(self.limitations),
            "tags": list(self.tags),
            "clinically_relevant": self.clinically_relevant,
            "blocks_research_use": self.blocks_research_use,
            "created_at": _serialize(self.created_at),
        }


@dataclass(frozen=True, slots=True)
class InterpretationReport:
    """Complete machine-readable output of the interpretation engine."""

    report_id: str
    pipeline_run_id: str
    findings: tuple[InterpretationFinding, ...]
    evidence: tuple[EvidenceValue, ...]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "1.1.0"
    engine_version: str | None = None
    module_name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_id", _require_identifier(self.report_id, "report_id"))
        object.__setattr__(
            self,
            "pipeline_run_id",
            _require_identifier(self.pipeline_run_id, "pipeline_run_id"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _require_identifier(self.schema_version, "schema_version"),
        )
        if self.engine_version is not None:
            object.__setattr__(
                self,
                "engine_version",
                _require_identifier(self.engine_version, "engine_version"),
            )
        if self.module_name is not None:
            object.__setattr__(
                self,
                "module_name",
                _require_text(self.module_name, "module_name"),
            )
        object.__setattr__(
            self,
            "generated_at",
            _normalize_datetime(self.generated_at, "generated_at"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        object.__setattr__(self, "findings", _normalize_model_tuple(self.findings, InterpretationFinding, "findings"))
        object.__setattr__(self, "evidence", _normalize_model_tuple(self.evidence, EvidenceValue, "evidence"))

        metric_ids = [item.metric_id for item in self.evidence]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("Evidence metric identifiers must be unique within a report.")

        finding_ids = [item.finding_id for item in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("Finding identifiers must be unique within a report.")

        known_metrics = set(metric_ids)
        for finding in self.findings:
            unknown = {item.metric_id for item in finding.evidence} - known_metrics
            if unknown:
                raise ValueError(
                    f"Finding {finding.finding_id!r} references unknown metrics: "
                    f"{sorted(unknown)}."
                )

    @property
    def status_counts(self) -> dict[str, int]:
        """Return finding counts grouped by scientific status."""

        counts = {status.value: 0 for status in FindingStatus}
        for finding in self.findings:
            counts[finding.status.value] += 1
        return counts

    @property
    def severity_counts(self) -> dict[str, int]:
        """Return finding counts grouped by severity."""

        counts = {severity.value: 0 for severity in Severity}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        return counts

    @property
    def blocking_findings(self) -> tuple[InterpretationFinding, ...]:
        """Return findings that explicitly block research use."""

        return tuple(finding for finding in self.findings if finding.blocks_research_use)

    @property
    def overall_status(self) -> FindingStatus:
        """Derive a conservative report-level decision from all findings."""

        statuses = {finding.status for finding in self.findings}
        if FindingStatus.FAIL in statuses:
            return FindingStatus.FAIL
        if FindingStatus.INCONCLUSIVE in statuses:
            return FindingStatus.INCONCLUSIVE
        if FindingStatus.WARNING in statuses:
            return FindingStatus.WARNING
        if FindingStatus.PASS in statuses:
            return FindingStatus.PASS
        if FindingStatus.NOT_EVALUATED in statuses:
            return FindingStatus.NOT_EVALUATED
        return FindingStatus.NOT_APPLICABLE

    @property
    def research_use_allowed(self) -> bool:
        """Return whether no finding explicitly blocks research use."""

        return not self.blocking_findings

    def evidence_by_id(self) -> Mapping[str, EvidenceValue]:
        """Return an immutable lookup of normalized evidence by metric id."""

        return MappingProxyType({item.metric_id: item for item in self.evidence})

    def to_dict(self) -> dict[str, Any]:
        """Return the complete report as a stable serializable dictionary."""

        return {
            "report_id": self.report_id,
            "pipeline_run_id": self.pipeline_run_id,
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "module_name": self.module_name,
            "generated_at": _serialize(self.generated_at),
            "overall_status": self.overall_status.value,
            "research_use_allowed": self.research_use_allowed,
            "status_counts": self.status_counts,
            "severity_counts": self.severity_counts,
            "findings": [item.to_dict() for item in self.findings],
            "evidence": [item.to_dict() for item in self.evidence],
            "metadata": _serialize(self.metadata),
        }