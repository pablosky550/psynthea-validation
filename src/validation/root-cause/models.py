"""
Immutable domain contracts for deterministic root-cause analysis.

Phase 3 transforms validated discrepancies into evidence-backed, reproducible
causal explanations.  This module defines the stable data exchanged by evidence
collection, signal extraction, candidate generation, ranking, verification,
source attribution, reproduction planning and reporting.

The central scientific rule is deliberately strict::

    discrepancy != cause
    correlation != verification
    ranking != attribution

Consequently, this module keeps observations, candidate hypotheses, evidence
assessments, verification outcomes, source attribution and final findings as
separate immutable concepts.  No evidence collection, causal rule execution,
ranking algorithm, verifier invocation, filesystem access or report rendering
belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from math import isfinite
from pathlib import Path, PurePath
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Mapping, Sequence, TypeVar

from validation.knowledge.taxonomy import RootCauseCategory, ValidationDomain
from validation.orchestration.models import ArtifactReference

__all__ = [
    "AttributionLevel",
    "CandidateAssessment",
    "CandidateStatus",
    "CausalCandidate",
    "CausalConfidence",
    "DifferenceClassification",
    "DiscrepancySignal",
    "EvidenceDirection",
    "EvidenceReference",
    "ReproductionPlan",
    "RootCauseFinding",
    "RootCauseReport",
    "RootCauseRequest",
    "RootCauseStatus",
    "SourceAttribution",
    "VerificationOutcome",
    "VerificationResult",
]


# =============================================================================
# Enumerations
# =============================================================================


class RootCauseStatus(str, Enum):
    """Scientific classification assigned to a completed causal investigation."""

    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    PLAUSIBLE = "plausible"
    MULTIFACTORIAL = "multifactorial"
    EXPECTED_DIFFERENCE = "expected_difference"
    IMPLEMENTATION_LIMITATION = "implementation_limitation"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


class CausalConfidence(str, Enum):
    """Ordered confidence in a causal conclusion, independent of its status."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class CandidateStatus(str, Enum):
    """Lifecycle of one causal candidate during automatic investigation."""

    GENERATED = "generated"
    PRIORITIZED = "prioritized"
    UNDER_VERIFICATION = "under_verification"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_TESTABLE = "not_testable"
    SUPERSEDED = "superseded"


class VerificationOutcome(str, Enum):
    """Deterministic result of executing one candidate verification procedure."""

    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"
    SKIPPED = "skipped"


class AttributionLevel(str, Enum):
    """Most precise system location supported by available causal evidence."""

    UNKNOWN = "unknown"
    COMPONENT = "component"
    MODULE = "module"
    STATE = "state"
    TRANSITION = "transition"
    LOGIC = "logic"
    EXPORTER = "exporter"
    METRIC = "metric"
    CONFIGURATION = "configuration"
    ENVIRONMENT = "environment"


class DifferenceClassification(str, Enum):
    """Mechanistic nature of the discrepancy, not its causal certainty."""

    INPUT = "input"
    CONFIGURATION = "configuration"
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    TEMPORAL = "temporal"
    PROBABILISTIC = "probabilistic"
    CLINICAL_RECORDING = "clinical_recording"
    TERMINOLOGY = "terminology"
    EXPORT_ONLY = "export_only"
    VALIDATION_PIPELINE = "validation_pipeline"
    EXECUTION_ENVIRONMENT = "execution_environment"
    STATISTICAL_ARTIFACT = "statistical_artifact"
    EXPECTED_ADAPTATION = "expected_adaptation"
    IMPLEMENTATION_LIMITATION = "implementation_limitation"
    MULTIFACTORIAL = "multifactorial"
    UNKNOWN = "unknown"


class EvidenceDirection(str, Enum):
    """Interpretation of one evidence item relative to one causal candidate."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


# =============================================================================
# Validation and normalization helpers
# =============================================================================


_IDENTIFIER_PATTERN = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SHA256_PATTERN = compile_pattern(r"^[0-9a-f]{64}$")
_EnumT = TypeVar("_EnumT", bound=Enum)
_ModelT = TypeVar("_ModelT")

_STATUS_CONFIDENCE = {
    RootCauseStatus.CONFIRMED: {CausalConfidence.HIGH, CausalConfidence.VERY_HIGH},
    RootCauseStatus.PROBABLE: {CausalConfidence.MODERATE, CausalConfidence.HIGH},
    RootCauseStatus.PLAUSIBLE: {CausalConfidence.LOW, CausalConfidence.MODERATE},
    RootCauseStatus.MULTIFACTORIAL: {
        CausalConfidence.MODERATE,
        CausalConfidence.HIGH,
        CausalConfidence.VERY_HIGH,
    },
    RootCauseStatus.EXPECTED_DIFFERENCE: {
        CausalConfidence.MODERATE,
        CausalConfidence.HIGH,
        CausalConfidence.VERY_HIGH,
    },
    RootCauseStatus.IMPLEMENTATION_LIMITATION: {
        CausalConfidence.MODERATE,
        CausalConfidence.HIGH,
        CausalConfidence.VERY_HIGH,
    },
    RootCauseStatus.INCONCLUSIVE: {CausalConfidence.NONE, CausalConfidence.LOW},
    RootCauseStatus.NOT_APPLICABLE: {CausalConfidence.NONE},
}


def _require_enum(value: _EnumT, enum_type: type[_EnumT], field_name: str) -> _EnumT:
    if not isinstance(value, enum_type):
        raise TypeError(
            f"{field_name} must be a {enum_type.__name__} member, "
            f"got {type(value).__name__}."
        )
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _optional_text(value: str | None, field_name: str) -> str | None:
    return None if value is None else _require_text(value, field_name)


def _require_identifier(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, '.', '_', ':', or '-'."
        )
    return normalized


def _optional_identifier(value: str | None, field_name: str) -> str | None:
    return None if value is None else _require_identifier(value, field_name)


def _require_bool(value: bool, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool.")
    return value


def _require_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return value


def _require_score(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite.")
    return normalized


def _require_unit_interval(value: float, field_name: str) -> float:
    normalized = _require_score(value, field_name)
    if not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0 inclusive.")
    return normalized


def _normalize_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _optional_datetime(value: datetime | None, field_name: str) -> datetime | None:
    return None if value is None else _normalize_datetime(value, field_name)


def _normalize_path(value: Path | str, field_name: str) -> Path:
    if isinstance(value, str):
        value = _require_text(value, field_name)
    elif not isinstance(value, PurePath):
        raise TypeError(f"{field_name} must be a path or string.")
    path = Path(value).expanduser()
    if str(path).strip() in {"", "."}:
        raise ValueError(f"{field_name} must identify a concrete path.")
    return path


def _normalize_text_tuple(
    values: Sequence[str],
    field_name: str,
    *,
    identifiers: bool = False,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    validator = _require_identifier if identifiers else _require_text
    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = validator(value, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return tuple(normalized)


def _normalize_model_tuple(
    values: Sequence[_ModelT],
    expected_type: type[_ModelT],
    field_name: str,
) -> tuple[_ModelT, ...]:
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


def _normalize_artifact_tuple(
    values: Sequence[ArtifactReference], field_name: str
) -> tuple[ArtifactReference, ...]:
    return _normalize_model_tuple(values, ArtifactReference, field_name)

def _require_unique_ids(values: Sequence[Any], field_name: str) -> None:
    ids = [value.id for value in values]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{field_name} must contain unique ids.")


def _validate_reference_ids(
    reference_ids: Sequence[str],
    available_ids: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(reference_ids) - available_ids)
    if unknown:
        raise ValueError(f"{field_name} references unknown ids: {', '.join(unknown)}.")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("mapping keys must be strings.")
            frozen[key] = _deep_freeze(item)
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_deep_freeze(item) for item in value), key=repr))
    return value


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        normalized[_require_text(key, f"{field_name} key")] = _deep_freeze(item)
    return MappingProxyType(normalized)


def _normalize_sha256(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None.")
    normalized = value.strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must contain exactly 64 lowercase hexadecimal characters.")
    return normalized


# =============================================================================
# Request and discrepancy signals
# =============================================================================


@dataclass(frozen=True, slots=True)
class RootCauseRequest:
    """Complete, immutable input contract for one Phase 3 investigation.

    References identify already persisted upstream objects.  The request does
    not embed Phase 1, Phase 2A or orchestration models, keeping the root-cause
    engine independently testable and serializable.
    """

    id: str
    experiment_id: str
    run_id: str
    validation_result_ids: tuple[str, ...]
    interpretation_finding_ids: tuple[str, ...] = ()
    investigation_case_ids: tuple[str, ...] = ()
    knowledge_entry_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    requested_domains: tuple[ValidationDomain, ...] = ()
    max_candidates: int = 20
    execute_verifications: bool = True
    strict_integrity: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self, "experiment_id", _require_identifier(self.experiment_id, "experiment_id")
        )
        object.__setattr__(self, "run_id", _require_identifier(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "validation_result_ids",
            _normalize_text_tuple(
                self.validation_result_ids,
                "validation_result_ids",
                identifiers=True,
                allow_empty=False,
            ),
        )
        for field_name in (
            "interpretation_finding_ids",
            "investigation_case_ids",
            "knowledge_entry_ids",
            "artifact_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_text_tuple(
                    getattr(self, field_name), field_name, identifiers=True
                ),
            )
        if isinstance(self.requested_domains, (str, bytes)) or not isinstance(
            self.requested_domains, Sequence
        ):
            raise TypeError("requested_domains must be a sequence of ValidationDomain members.")
        domains: list[ValidationDomain] = []
        for index, domain in enumerate(self.requested_domains):
            normalized = _require_enum(domain, ValidationDomain, f"requested_domains[{index}]")
            if normalized not in domains:
                domains.append(normalized)
        object.__setattr__(self, "requested_domains", tuple(domains))
        object.__setattr__(
            self, "max_candidates", _require_non_negative_int(self.max_candidates, "max_candidates")
        )
        if self.max_candidates == 0:
            raise ValueError("max_candidates must be greater than zero.")
        object.__setattr__(
            self,
            "execute_verifications",
            _require_bool(self.execute_verifications, "execute_verifications"),
        )
        object.__setattr__(
            self, "strict_integrity", _require_bool(self.strict_integrity, "strict_integrity")
        )
        object.__setattr__(self, "created_at", _normalize_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class DiscrepancySignal:
    """Typed, non-causal representation of an observed discrepancy."""

    id: str
    domain: ValidationDomain
    classification: DifferenceClassification
    summary: str
    source_id: str
    metric_id: str | None = None
    cohort_id: str | None = None
    synthea_value: Any = None
    psynthea_value: Any = None
    absolute_difference: float | None = None
    relative_difference: float | None = None
    effect_size: float | None = None
    statistically_significant: bool | None = None
    clinically_relevant: bool | None = None
    affected_entity_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "domain", _require_enum(self.domain, ValidationDomain, "domain"))
        object.__setattr__(
            self,
            "classification",
            _require_enum(self.classification, DifferenceClassification, "classification"),
        )
        object.__setattr__(self, "summary", _require_text(self.summary, "summary"))
        object.__setattr__(self, "source_id", _require_identifier(self.source_id, "source_id"))
        object.__setattr__(self, "metric_id", _optional_identifier(self.metric_id, "metric_id"))
        object.__setattr__(self, "cohort_id", _optional_identifier(self.cohort_id, "cohort_id"))
        object.__setattr__(self, "synthea_value", _deep_freeze(self.synthea_value))
        object.__setattr__(self, "psynthea_value", _deep_freeze(self.psynthea_value))
        for field_name in ("absolute_difference", "relative_difference", "effect_size"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _require_score(value, field_name))
        for field_name in ("statistically_significant", "clinically_relevant"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _require_bool(value, field_name))
        object.__setattr__(
            self,
            "affected_entity_ids",
            _normalize_text_tuple(self.affected_entity_ids, "affected_entity_ids", identifiers=True),
        )
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_text_tuple(self.evidence_ids, "evidence_ids", identifiers=True),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


# =============================================================================
# Evidence, candidates and ranking assessments
# =============================================================================


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """One immutable and auditable evidence item collected for Phase 3."""

    id: str
    source_type: str
    summary: str
    locator: str
    direction: EvidenceDirection = EvidenceDirection.NEUTRAL
    related_candidate_id: str | None = None
    artifact_id: str | None = None
    sha256: str | None = None
    observed_at: datetime | None = None
    details: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "source_type", _require_identifier(self.source_type, "source_type"))
        object.__setattr__(self, "summary", _require_text(self.summary, "summary"))
        object.__setattr__(self, "locator", _require_text(self.locator, "locator"))
        object.__setattr__(
            self, "direction", _require_enum(self.direction, EvidenceDirection, "direction")
        )
        object.__setattr__(
            self,
            "related_candidate_id",
            _optional_identifier(self.related_candidate_id, "related_candidate_id"),
        )
        object.__setattr__(
            self, "artifact_id", _optional_identifier(self.artifact_id, "artifact_id")
        )
        object.__setattr__(self, "sha256", _normalize_sha256(self.sha256, "sha256"))
        object.__setattr__(
            self, "observed_at", _optional_datetime(self.observed_at, "observed_at")
        )
        object.__setattr__(self, "details", _optional_text(self.details, "details"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.direction is not EvidenceDirection.NEUTRAL and self.related_candidate_id is None:
            raise ValueError(
                "Directional evidence requires related_candidate_id so its interpretation is explicit."
            )


@dataclass(frozen=True, slots=True)
class CausalCandidate:
    """One testable candidate explanation generated from rules or prior knowledge."""

    id: str
    category: RootCauseCategory
    statement: str
    mechanism: str
    signal_ids: tuple[str, ...]
    status: CandidateStatus = CandidateStatus.GENERATED
    source_rule_id: str | None = None
    knowledge_entry_id: str | None = None
    investigation_protocol_id: str | None = None
    expected_observations: tuple[str, ...] = ()
    falsification_criteria: tuple[str, ...] = ()
    prerequisite_evidence_ids: tuple[str, ...] = ()
    alternative_candidate_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self, "category", _require_enum(self.category, RootCauseCategory, "category")
        )
        object.__setattr__(self, "statement", _require_text(self.statement, "statement"))
        object.__setattr__(self, "mechanism", _require_text(self.mechanism, "mechanism"))
        object.__setattr__(
            self,
            "signal_ids",
            _normalize_text_tuple(
                self.signal_ids, "signal_ids", identifiers=True, allow_empty=False
            ),
        )
        object.__setattr__(
            self, "status", _require_enum(self.status, CandidateStatus, "status")
        )
        for field_name in (
            "source_rule_id",
            "knowledge_entry_id",
            "investigation_protocol_id",
        ):
            object.__setattr__(
                self, field_name, _optional_identifier(getattr(self, field_name), field_name)
            )
        object.__setattr__(
            self,
            "expected_observations",
            _normalize_text_tuple(self.expected_observations, "expected_observations"),
        )
        object.__setattr__(
            self,
            "falsification_criteria",
            _normalize_text_tuple(self.falsification_criteria, "falsification_criteria"),
        )
        object.__setattr__(
            self,
            "prerequisite_evidence_ids",
            _normalize_text_tuple(
                self.prerequisite_evidence_ids,
                "prerequisite_evidence_ids",
                identifiers=True,
            ),
        )
        object.__setattr__(
            self,
            "alternative_candidate_ids",
            _normalize_text_tuple(
                self.alternative_candidate_ids,
                "alternative_candidate_ids",
                identifiers=True,
            ),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.id in self.alternative_candidate_ids:
            raise ValueError("A candidate cannot list itself as an alternative.")
        if not any(
            (self.source_rule_id, self.knowledge_entry_id, self.investigation_protocol_id)
        ):
            raise ValueError(
                "CausalCandidate requires source_rule_id, knowledge_entry_id, "
                "investigation_protocol_id, or a combination of them."
            )


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    """Explainable ranking and evidence assessment for one causal candidate."""

    candidate_id: str
    rank: int
    total_score: float
    evidence_support: float = 0.0
    knowledge_match: float = 0.0
    provenance_match: float = 0.0
    reproducibility: float = 0.0
    mechanism_specificity: float = 0.0
    contradictory_evidence: float = 0.0
    missing_evidence: float = 0.0
    alternative_explanations: float = 0.0
    supporting_evidence_ids: tuple[str, ...] = ()
    contradictory_evidence_ids: tuple[str, ...] = ()
    missing_evidence_descriptions: tuple[str, ...] = ()
    rationale: str = "Not yet assessed."
    score_components: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_id", _require_identifier(self.candidate_id, "candidate_id")
        )
        rank = _require_non_negative_int(self.rank, "rank")
        if rank == 0:
            raise ValueError("rank is one-based and must be greater than zero.")
        object.__setattr__(self, "rank", rank)
        for field_name in (
            "total_score",
            "evidence_support",
            "knowledge_match",
            "provenance_match",
            "reproducibility",
            "mechanism_specificity",
            "contradictory_evidence",
            "missing_evidence",
            "alternative_explanations",
        ):
            object.__setattr__(self, field_name, _require_score(getattr(self, field_name), field_name))
        for field_name in ("supporting_evidence_ids", "contradictory_evidence_ids"):
            object.__setattr__(
                self,
                field_name,
                _normalize_text_tuple(getattr(self, field_name), field_name, identifiers=True),
            )
        object.__setattr__(
            self,
            "missing_evidence_descriptions",
            _normalize_text_tuple(
                self.missing_evidence_descriptions, "missing_evidence_descriptions"
            ),
        )
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))
        if not isinstance(self.score_components, Mapping):
            raise TypeError("score_components must be a mapping.")
        normalized_components = {
            _require_identifier(key, "score_components key"): _require_score(
                value, f"score_components[{key!r}]"
            )
            for key, value in self.score_components.items()
        }
        object.__setattr__(
            self, "score_components", MappingProxyType(normalized_components)
        )

        overlap = set(self.supporting_evidence_ids) & set(self.contradictory_evidence_ids)
        if overlap:
            raise ValueError(
                "Evidence cannot simultaneously support and contradict a candidate: "
                + ", ".join(sorted(overlap))
                + "."
            )

        expected_total = (
            self.evidence_support
            + self.knowledge_match
            + self.provenance_match
            + self.reproducibility
            + self.mechanism_specificity
            - self.contradictory_evidence
            - self.missing_evidence
            - self.alternative_explanations
        )
        if abs(self.total_score - expected_total) > 1e-9:
            raise ValueError(
                "total_score must equal the documented explainable ranking formula."
            )


# =============================================================================
# Verification and attribution
# =============================================================================


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Outcome of one deterministic verifier execution against one candidate."""

    id: str
    candidate_id: str
    verifier_id: str
    outcome: VerificationOutcome
    procedure: str
    expected_result: str
    observed_result: str | None = None
    input_artifact_ids: tuple[str, ...] = ()
    output_artifacts: tuple[ArtifactReference, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    command: tuple[str, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self, "candidate_id", _require_identifier(self.candidate_id, "candidate_id")
        )
        object.__setattr__(self, "verifier_id", _require_identifier(self.verifier_id, "verifier_id"))
        object.__setattr__(
            self, "outcome", _require_enum(self.outcome, VerificationOutcome, "outcome")
        )
        object.__setattr__(self, "procedure", _require_text(self.procedure, "procedure"))
        object.__setattr__(
            self, "expected_result", _require_text(self.expected_result, "expected_result")
        )
        object.__setattr__(
            self, "observed_result", _optional_text(self.observed_result, "observed_result")
        )
        object.__setattr__(
            self,
            "input_artifact_ids",
            _normalize_text_tuple(self.input_artifact_ids, "input_artifact_ids", identifiers=True),
        )
        artifacts = _normalize_artifact_tuple(self.output_artifacts, "output_artifacts")
        _require_unique_ids(artifacts, "output_artifacts")
        object.__setattr__(self, "output_artifacts", artifacts)
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_text_tuple(self.evidence_ids, "evidence_ids", identifiers=True),
        )
        object.__setattr__(
            self, "command", _normalize_text_tuple(self.command, "command")
        )
        object.__setattr__(self, "started_at", _optional_datetime(self.started_at, "started_at"))
        object.__setattr__(
            self, "finished_at", _optional_datetime(self.finished_at, "finished_at")
        )
        if self.duration_seconds is not None:
            duration = _require_score(self.duration_seconds, "duration_seconds")
            if duration < 0:
                raise ValueError("duration_seconds must be non-negative.")
            object.__setattr__(self, "duration_seconds", duration)
        object.__setattr__(
            self, "error_message", _optional_text(self.error_message, "error_message")
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at.")
        if self.outcome is VerificationOutcome.NOT_RUN:
            if any((self.observed_result, self.started_at, self.finished_at, self.error_message)):
                raise ValueError("A not-run verification cannot contain execution results.")
        elif self.outcome is VerificationOutcome.ERROR:
            if self.error_message is None:
                raise ValueError("An errored verification requires error_message.")
        else:
            if self.observed_result is None:
                raise ValueError(f"A {self.outcome.value} verification requires observed_result.")
            if self.error_message is not None:
                raise ValueError("Only an errored verification may contain error_message.")
        if self.finished_at is not None and self.started_at is None:
            raise ValueError("finished_at requires started_at.")


@dataclass(frozen=True, slots=True)
class SourceAttribution:
    """Evidence-backed localization of a discrepancy within the system."""

    level: AttributionLevel
    component: str | None = None
    module: str | None = None
    state: str | None = None
    transition: str | None = None
    logic: str | None = None
    exporter: str | None = None
    metric: str | None = None
    configuration_key: str | None = None
    environment_key: str | None = None
    confidence: CausalConfidence = CausalConfidence.NONE
    evidence_ids: tuple[str, ...] = ()
    rationale: str = "Attribution unavailable."

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", _require_enum(self.level, AttributionLevel, "level"))
        for field_name in (
            "component",
            "module",
            "state",
            "transition",
            "logic",
            "exporter",
            "metric",
            "configuration_key",
            "environment_key",
        ):
            object.__setattr__(
                self, field_name, _optional_text(getattr(self, field_name), field_name)
            )
        object.__setattr__(
            self,
            "confidence",
            _require_enum(self.confidence, CausalConfidence, "confidence"),
        )
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_text_tuple(self.evidence_ids, "evidence_ids", identifiers=True),
        )
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))

        required_field_by_level = {
            AttributionLevel.COMPONENT: "component",
            AttributionLevel.MODULE: "module",
            AttributionLevel.STATE: "state",
            AttributionLevel.TRANSITION: "transition",
            AttributionLevel.LOGIC: "logic",
            AttributionLevel.EXPORTER: "exporter",
            AttributionLevel.METRIC: "metric",
            AttributionLevel.CONFIGURATION: "configuration_key",
            AttributionLevel.ENVIRONMENT: "environment_key",
        }
        required_field = required_field_by_level.get(self.level)
        if required_field is not None and getattr(self, required_field) is None:
            raise ValueError(f"{self.level.value} attribution requires {required_field}.")
        if self.level is AttributionLevel.UNKNOWN:
            attributed_values = (
                self.component,
                self.module,
                self.state,
                self.transition,
                self.logic,
                self.exporter,
                self.metric,
                self.configuration_key,
                self.environment_key,
            )
            if any(attributed_values):
                raise ValueError("Unknown attribution cannot contain a concrete source location.")
            if self.confidence is not CausalConfidence.NONE:
                raise ValueError("Unknown attribution requires confidence NONE.")
        elif not self.evidence_ids:
            raise ValueError("A concrete source attribution requires supporting evidence_ids.")


# =============================================================================
# Reproduction and final causal findings
# =============================================================================


@dataclass(frozen=True, slots=True)
class ReproductionPlan:
    """Exact, non-executing procedure for reproducing a causal discrepancy."""

    id: str
    experiment_id: str
    run_id: str
    title: str
    objective: str
    commands: tuple[tuple[str, ...], ...]
    working_directory: Path
    seeds: tuple[int, ...] = ()
    module_paths: tuple[str, ...] = ()
    patient_ids: tuple[str, ...] = ()
    cohort_ids: tuple[str, ...] = ()
    required_artifact_ids: tuple[str, ...] = ()
    required_hashes: Mapping[str, str] = field(default_factory=dict)
    configuration: Mapping[str, Any] = field(default_factory=dict)
    software_versions: Mapping[str, str] = field(default_factory=dict)
    verification_steps: tuple[str, ...] = ()
    expected_result: str = "The discrepancy is reproduced deterministically."
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self, "experiment_id", _require_identifier(self.experiment_id, "experiment_id")
        )
        object.__setattr__(self, "run_id", _require_identifier(self.run_id, "run_id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "objective", _require_text(self.objective, "objective"))
        if isinstance(self.commands, (str, bytes)) or not isinstance(self.commands, Sequence):
            raise TypeError("commands must be a sequence of command-token sequences.")
        commands: list[tuple[str, ...]] = []
        for index, command in enumerate(self.commands):
            commands.append(
                _normalize_text_tuple(
                    command, f"commands[{index}]", allow_empty=False
                )
            )
        if not commands:
            raise ValueError("ReproductionPlan requires at least one command.")
        object.__setattr__(self, "commands", tuple(commands))
        object.__setattr__(
            self,
            "working_directory",
            _normalize_path(self.working_directory, "working_directory"),
        )
        if isinstance(self.seeds, (str, bytes)) or not isinstance(self.seeds, Sequence):
            raise TypeError("seeds must be a sequence of integers.")
        seeds: list[int] = []
        for index, seed in enumerate(self.seeds):
            if isinstance(seed, bool) or not isinstance(seed, int):
                raise TypeError(f"seeds[{index}] must be an integer.")
            if seed not in seeds:
                seeds.append(seed)
        object.__setattr__(self, "seeds", tuple(seeds))
        for field_name, identifiers in (
            ("module_paths", False),
            ("patient_ids", True),
            ("cohort_ids", True),
            ("required_artifact_ids", True),
            ("verification_steps", False),
            ("limitations", False),
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_text_tuple(
                    getattr(self, field_name), field_name, identifiers=identifiers
                ),
            )
        if not isinstance(self.required_hashes, Mapping):
            raise TypeError("required_hashes must be a mapping.")
        hashes = {
            _require_identifier(key, "required_hashes key"): _normalize_sha256(
                value, f"required_hashes[{key!r}]"
            )
            for key, value in self.required_hashes.items()
        }
        object.__setattr__(self, "required_hashes", MappingProxyType(hashes))
        object.__setattr__(
            self, "configuration", _freeze_mapping(self.configuration, "configuration")
        )
        if not isinstance(self.software_versions, Mapping):
            raise TypeError("software_versions must be a mapping.")
        versions = {
            _require_identifier(key, "software_versions key"): _require_text(
                value, f"software_versions[{key!r}]"
            )
            for key, value in self.software_versions.items()
        }
        object.__setattr__(self, "software_versions", MappingProxyType(versions))
        object.__setattr__(
            self, "expected_result", _require_text(self.expected_result, "expected_result")
        )


@dataclass(frozen=True, slots=True)
class RootCauseFinding:
    """One final, evidence-backed causal conclusion for one or more signals."""

    id: str
    status: RootCauseStatus
    confidence: CausalConfidence
    classification: DifferenceClassification
    domain: ValidationDomain
    summary: str
    explanation: str
    signal_ids: tuple[str, ...]
    selected_candidate_ids: tuple[str, ...] = ()
    alternative_candidate_ids: tuple[str, ...] = ()
    rejected_candidate_ids: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = ()
    contradictory_evidence_ids: tuple[str, ...] = ()
    verification_result_ids: tuple[str, ...] = ()
    attribution: SourceAttribution = field(
        default_factory=lambda: SourceAttribution(level=AttributionLevel.UNKNOWN)
    )
    reproduction_plan_id: str | None = None
    limitations: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self, "status", _require_enum(self.status, RootCauseStatus, "status")
        )
        object.__setattr__(
            self,
            "confidence",
            _require_enum(self.confidence, CausalConfidence, "confidence"),
        )
        object.__setattr__(
            self,
            "classification",
            _require_enum(self.classification, DifferenceClassification, "classification"),
        )
        object.__setattr__(self, "domain", _require_enum(self.domain, ValidationDomain, "domain"))
        object.__setattr__(self, "summary", _require_text(self.summary, "summary"))
        object.__setattr__(self, "explanation", _require_text(self.explanation, "explanation"))
        for field_name in (
            "signal_ids",
            "selected_candidate_ids",
            "alternative_candidate_ids",
            "rejected_candidate_ids",
            "supporting_evidence_ids",
            "contradictory_evidence_ids",
            "verification_result_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_text_tuple(
                    getattr(self, field_name),
                    field_name,
                    identifiers=True,
                    allow_empty=field_name != "signal_ids",
                ),
            )
        if not isinstance(self.attribution, SourceAttribution):
            raise TypeError("attribution must be a SourceAttribution.")
        object.__setattr__(
            self,
            "reproduction_plan_id",
            _optional_identifier(self.reproduction_plan_id, "reproduction_plan_id"),
        )
        object.__setattr__(self, "limitations", _normalize_text_tuple(self.limitations, "limitations"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.confidence not in _STATUS_CONFIDENCE[self.status]:
            allowed = ", ".join(item.value for item in _STATUS_CONFIDENCE[self.status])
            raise ValueError(
                f"{self.status.value} status permits confidence values: {allowed}."
            )
        candidate_groups = (
            set(self.selected_candidate_ids),
            set(self.alternative_candidate_ids),
            set(self.rejected_candidate_ids),
        )
        if candidate_groups[0] & candidate_groups[1] or candidate_groups[0] & candidate_groups[2] or candidate_groups[1] & candidate_groups[2]:
            raise ValueError(
                "selected, alternative and rejected candidate ids must be mutually exclusive."
            )
        evidence_overlap = set(self.supporting_evidence_ids) & set(
            self.contradictory_evidence_ids
        )
        if evidence_overlap:
            raise ValueError(
                "Evidence cannot simultaneously support and contradict a finding: "
                + ", ".join(sorted(evidence_overlap))
                + "."
            )
        if self.status is RootCauseStatus.CONFIRMED:
            if len(self.selected_candidate_ids) != 1:
                raise ValueError("A confirmed finding requires exactly one selected candidate.")
            if not self.supporting_evidence_ids:
                raise ValueError("A confirmed finding requires supporting evidence.")
            if not self.verification_result_ids:
                raise ValueError("A confirmed finding requires a positive verification result.")
            if self.attribution.level is AttributionLevel.UNKNOWN:
                raise ValueError("A confirmed finding requires concrete source attribution.")
        elif self.status is RootCauseStatus.PROBABLE:
            if not self.selected_candidate_ids or not self.supporting_evidence_ids:
                raise ValueError(
                    "A probable finding requires a selected candidate and supporting evidence."
                )
        elif self.status is RootCauseStatus.PLAUSIBLE:
            if not self.selected_candidate_ids:
                raise ValueError("A plausible finding requires at least one selected candidate.")
        elif self.status is RootCauseStatus.MULTIFACTORIAL:
            if len(self.selected_candidate_ids) < 2:
                raise ValueError("A multifactorial finding requires at least two selected candidates.")
            if self.classification is not DifferenceClassification.MULTIFACTORIAL:
                raise ValueError(
                    "A multifactorial finding requires MULTIFACTORIAL difference classification."
                )
        elif self.status is RootCauseStatus.EXPECTED_DIFFERENCE:
            if self.classification is not DifferenceClassification.EXPECTED_ADAPTATION:
                raise ValueError(
                    "EXPECTED_DIFFERENCE requires EXPECTED_ADAPTATION classification."
                )
        elif self.status is RootCauseStatus.IMPLEMENTATION_LIMITATION:
            if self.classification is not DifferenceClassification.IMPLEMENTATION_LIMITATION:
                raise ValueError(
                    "IMPLEMENTATION_LIMITATION status requires matching classification."
                )
        elif self.status in {RootCauseStatus.INCONCLUSIVE, RootCauseStatus.NOT_APPLICABLE}:
            if self.selected_candidate_ids:
                raise ValueError(f"{self.status.value} cannot select a causal candidate.")


# =============================================================================
# Aggregate report
# =============================================================================


@dataclass(frozen=True, slots=True)
class RootCauseReport:
    """Canonical, self-consistent output of one complete Phase 3 investigation."""

    id: str
    request_id: str
    experiment_id: str
    run_id: str
    status: RootCauseStatus
    confidence: CausalConfidence
    generated_at: datetime
    signals: tuple[DiscrepancySignal, ...]
    evidence: tuple[EvidenceReference, ...]
    candidates: tuple[CausalCandidate, ...]
    assessments: tuple[CandidateAssessment, ...]
    verifications: tuple[VerificationResult, ...]
    findings: tuple[RootCauseFinding, ...]
    reproduction_plans: tuple[ReproductionPlan, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    executive_summary: str = "Root-cause analysis completed."
    unresolved_questions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("id", "request_id", "experiment_id", "run_id"):
            object.__setattr__(
                self, field_name, _require_identifier(getattr(self, field_name), field_name)
            )
        object.__setattr__(
            self, "status", _require_enum(self.status, RootCauseStatus, "status")
        )
        object.__setattr__(
            self,
            "confidence",
            _require_enum(self.confidence, CausalConfidence, "confidence"),
        )
        object.__setattr__(
            self, "generated_at", _normalize_datetime(self.generated_at, "generated_at")
        )

        typed_collections = (
            ("signals", DiscrepancySignal),
            ("evidence", EvidenceReference),
            ("candidates", CausalCandidate),
            ("assessments", CandidateAssessment),
            ("verifications", VerificationResult),
            ("findings", RootCauseFinding),
            ("reproduction_plans", ReproductionPlan),
        )
        for field_name, model_type in typed_collections:
            normalized = _normalize_model_tuple(getattr(self, field_name), model_type, field_name)
            if field_name != "assessments":
                _require_unique_ids(normalized, field_name)
            object.__setattr__(self, field_name, normalized)

        artifacts = _normalize_artifact_tuple(self.artifacts, "artifacts")
        _require_unique_ids(artifacts, "artifacts")
        object.__setattr__(self, "artifacts", artifacts)

        object.__setattr__(
            self,
            "executive_summary",
            _require_text(self.executive_summary, "executive_summary"),
        )
        object.__setattr__(
            self,
            "unresolved_questions",
            _normalize_text_tuple(self.unresolved_questions, "unresolved_questions"),
        )
        object.__setattr__(self, "limitations", _normalize_text_tuple(self.limitations, "limitations"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if not self.signals:
            raise ValueError("RootCauseReport requires at least one discrepancy signal.")
        if not self.findings:
            raise ValueError("RootCauseReport requires at least one causal finding.")
        if self.confidence not in _STATUS_CONFIDENCE[self.status]:
            allowed = ", ".join(item.value for item in _STATUS_CONFIDENCE[self.status])
            raise ValueError(
                f"Report status {self.status.value} permits confidence values: {allowed}."
            )

        signal_ids = {item.id for item in self.signals}
        evidence_ids = {item.id for item in self.evidence}
        candidate_ids = {item.id for item in self.candidates}
        verification_ids = {item.id for item in self.verifications}
        reproduction_plan_ids = {item.id for item in self.reproduction_plans}
        artifact_ids = {item.id for item in self.artifacts}

        for candidate in self.candidates:
            _validate_reference_ids(candidate.signal_ids, signal_ids, f"candidate {candidate.id}.signal_ids")
            _validate_reference_ids(
                candidate.prerequisite_evidence_ids,
                evidence_ids,
                f"candidate {candidate.id}.prerequisite_evidence_ids",
            )
            _validate_reference_ids(
                candidate.alternative_candidate_ids,
                candidate_ids,
                f"candidate {candidate.id}.alternative_candidate_ids",
            )

        assessed_candidate_ids = [item.candidate_id for item in self.assessments]
        if len(assessed_candidate_ids) != len(set(assessed_candidate_ids)):
            raise ValueError("assessments must contain at most one assessment per candidate.")
        ranks = [item.rank for item in self.assessments]
        if len(ranks) != len(set(ranks)):
            raise ValueError("assessment ranks must be unique.")
        if ranks and set(ranks) != set(range(1, len(ranks) + 1)):
            raise ValueError("assessment ranks must form a contiguous one-based sequence.")
        for assessment in self.assessments:
            _validate_reference_ids(
                (assessment.candidate_id,), candidate_ids, "assessment.candidate_id"
            )
            _validate_reference_ids(
                assessment.supporting_evidence_ids,
                evidence_ids,
                f"assessment {assessment.candidate_id}.supporting_evidence_ids",
            )
            _validate_reference_ids(
                assessment.contradictory_evidence_ids,
                evidence_ids,
                f"assessment {assessment.candidate_id}.contradictory_evidence_ids",
            )

        for item in self.evidence:
            if item.related_candidate_id is not None:
                _validate_reference_ids(
                    (item.related_candidate_id,), candidate_ids, f"evidence {item.id}.related_candidate_id"
                )
            if item.artifact_id is not None:
                _validate_reference_ids(
                    (item.artifact_id,), artifact_ids, f"evidence {item.id}.artifact_id"
                )

        for verification in self.verifications:
            _validate_reference_ids(
                (verification.candidate_id,), candidate_ids, f"verification {verification.id}.candidate_id"
            )
            _validate_reference_ids(
                verification.evidence_ids,
                evidence_ids,
                f"verification {verification.id}.evidence_ids",
            )
            _validate_reference_ids(
                verification.input_artifact_ids,
                artifact_ids,
                f"verification {verification.id}.input_artifact_ids",
            )
            _validate_reference_ids(
                tuple(artifact.id for artifact in verification.output_artifacts),
                artifact_ids,
                f"verification {verification.id}.output_artifacts",
            )

        positive_verification_ids = {
            item.id for item in self.verifications if item.outcome is VerificationOutcome.PASSED
        }
        candidate_by_id = {item.id: item for item in self.candidates}
        verification_by_id = {item.id: item for item in self.verifications}
        for finding in self.findings:
            _validate_reference_ids(finding.signal_ids, signal_ids, f"finding {finding.id}.signal_ids")
            for field_name in (
                "selected_candidate_ids",
                "alternative_candidate_ids",
                "rejected_candidate_ids",
            ):
                _validate_reference_ids(
                    getattr(finding, field_name), candidate_ids, f"finding {finding.id}.{field_name}"
                )
            _validate_reference_ids(
                finding.supporting_evidence_ids,
                evidence_ids,
                f"finding {finding.id}.supporting_evidence_ids",
            )
            _validate_reference_ids(
                finding.contradictory_evidence_ids,
                evidence_ids,
                f"finding {finding.id}.contradictory_evidence_ids",
            )
            _validate_reference_ids(
                finding.verification_result_ids,
                verification_ids,
                f"finding {finding.id}.verification_result_ids",
            )
            _validate_reference_ids(
                finding.attribution.evidence_ids,
                evidence_ids,
                f"finding {finding.id}.attribution.evidence_ids",
            )
            if finding.reproduction_plan_id is not None:
                _validate_reference_ids(
                    (finding.reproduction_plan_id,),
                    reproduction_plan_ids,
                    f"finding {finding.id}.reproduction_plan_id",
                )
            selected_candidates = [
                candidate_by_id[candidate_id]
                for candidate_id in finding.selected_candidate_ids
            ]
            if finding.status is RootCauseStatus.CONFIRMED:
                passed = set(finding.verification_result_ids) & positive_verification_ids
                if not passed:
                    raise ValueError(
                        f"Confirmed finding {finding.id!r} must reference at least one PASSED verification."
                    )
                if any(
                    candidate.status is not CandidateStatus.SUPPORTED
                    for candidate in selected_candidates
                ):
                    raise ValueError(
                        f"Confirmed finding {finding.id!r} may select only SUPPORTED candidates."
                    )
                if not any(
                    verification_by_id[verification_id].candidate_id
                    in finding.selected_candidate_ids
                    for verification_id in passed
                ):
                    raise ValueError(
                        f"Confirmed finding {finding.id!r} requires a PASSED verification "
                        "for its selected candidate."
                    )
            if any(
                candidate.status is CandidateStatus.REFUTED
                for candidate in selected_candidates
            ):
                raise ValueError(
                    f"Finding {finding.id!r} cannot select a REFUTED candidate."
                )

        for plan in self.reproduction_plans:
            if plan.experiment_id != self.experiment_id or plan.run_id != self.run_id:
                raise ValueError(
                    f"Reproduction plan {plan.id!r} must match report experiment_id and run_id."
                )
            _validate_reference_ids(
                plan.required_artifact_ids,
                artifact_ids,
                f"reproduction plan {plan.id}.required_artifact_ids",
            )

        finding_statuses = {item.status for item in self.findings}
        if self.status is RootCauseStatus.CONFIRMED and finding_statuses != {
            RootCauseStatus.CONFIRMED
        }:
            raise ValueError(
                "A report may be CONFIRMED only when all findings are confirmed."
            )
        if self.status is RootCauseStatus.NOT_APPLICABLE and finding_statuses != {
            RootCauseStatus.NOT_APPLICABLE
        }:
            raise ValueError(
                "A NOT_APPLICABLE report may contain only not-applicable findings."
            )
        if self.status is RootCauseStatus.INCONCLUSIVE and any(
            status in {
                RootCauseStatus.CONFIRMED,
                RootCauseStatus.PROBABLE,
                RootCauseStatus.EXPECTED_DIFFERENCE,
                RootCauseStatus.IMPLEMENTATION_LIMITATION,
            }
            for status in finding_statuses
        ):
            raise ValueError(
                "An INCONCLUSIVE report cannot contain a conclusive causal finding."
            )