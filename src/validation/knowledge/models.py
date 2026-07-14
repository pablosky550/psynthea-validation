"""
Canonical models for evidence-backed root-cause knowledge.

This module defines the immutable domain contract for Phase 2A of the
psynthea validation project.  It represents what was observed, which causal
hypotheses were investigated, how those hypotheses were verified, and which
conclusions are sufficiently supported to enter the scientific knowledge base.

The central design rule is deliberately strict:

    an observed validation failure is not a demonstrated root cause.

Consequently, these models keep detection signals, evidence, hypotheses,
verification outcomes and validated knowledge entries as separate concepts.
No causal inference, pattern matching, registry persistence or report rendering
belongs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Mapping, Sequence, TypeVar

__all__ = [
    "ActionPriority",
    "CausalCertainty",
    "CausalHypothesis",
    "DetectionSignal",
    "EvidenceDirection",
    "EvidenceItem",
    "HypothesisEvidenceAssessment",
    "EvidenceSourceKind",
    "HypothesisStatus",
    "InvestigationCase",
    "InvestigationStatus",
    "KnowledgeEntry",
    "KnowledgeEntryStatus",
    "RecommendedAction",
    "VerificationCheck",
    "VerificationStatus",
]


# =============================================================================
# Enumerations
# =============================================================================


class EvidenceSourceKind(str, Enum):
    """Origin of an evidence item used during causal investigation."""

    PIPELINE_RESULT = "pipeline_result"
    RAW_DATA = "raw_data"
    SOURCE_CODE = "source_code"
    MODULE_DEFINITION = "module_definition"
    CONFIGURATION = "configuration"
    EXECUTION_LOG = "execution_log"
    EXPORT_ARTIFACT = "export_artifact"
    REPRODUCTION = "reproduction"
    EXTERNAL_REFERENCE = "external_reference"
    EXPERT_REVIEW = "expert_review"


class EvidenceDirection(str, Enum):
    """Relationship of an evidence item to one specific causal hypothesis.

    Direction is deliberately modelled on :class:`HypothesisEvidenceAssessment`,
    not on :class:`EvidenceItem`, because the same observation may support one
    hypothesis while refuting another.
    """

    SUPPORTS = "supports"
    REFUTES = "refutes"
    CONTEXT = "context"
    LIMITATION = "limitation"


class HypothesisStatus(str, Enum):
    """Scientific lifecycle state of a causal hypothesis."""

    PROPOSED = "proposed"
    UNDER_INVESTIGATION = "under_investigation"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class CausalCertainty(str, Enum):
    """Strength of a causal conclusion, independently of finding severity."""

    UNASSESSED = "unassessed"
    HYPOTHETICAL = "hypothetical"
    PLAUSIBLE = "plausible"
    PROBABLE = "probable"
    CONFIRMED = "confirmed"


class VerificationStatus(str, Enum):
    """Outcome of one reproducible verification step."""

    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


class InvestigationStatus(str, Enum):
    """Lifecycle state of a root-cause investigation."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    CLOSED_INCONCLUSIVE = "closed_inconclusive"
    REJECTED = "rejected"


class KnowledgeEntryStatus(str, Enum):
    """Publication state of an entry in the scientific knowledge base."""

    DRAFT = "draft"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


class ActionPriority(str, Enum):
    """Operational priority of a recommended follow-up action."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# =============================================================================
# Validation and normalization helpers
# =============================================================================


_IDENTIFIER_PATTERN = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SHA256_PATTERN = compile_pattern(r"^[0-9a-f]{64}$")
_EnumT = TypeVar("_EnumT", bound=Enum)


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


def _normalize_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _normalize_text_tuple(
    values: Sequence[str],
    field_name: str,
    *,
    identifiers: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")

    normalized: list[str] = []
    seen: set[str] = set()
    validator = _require_identifier if identifiers else _require_text
    for index, value in enumerate(values):
        item = validator(value, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


def _normalize_model_tuple(
    values: Sequence[Any],
    expected_type: type[Any],
    field_name: str,
) -> tuple[Any, ...]:
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


def _require_unique_ids(values: Sequence[Any], field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        item_id = value.id
        if item_id in seen:
            raise ValueError(f"{field_name} contains duplicate id {item_id!r}.")
        seen.add(item_id)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return _deep_freeze(dict(value))


def _validate_reference_ids(
    reference_ids: Sequence[str],
    available_ids: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(reference_ids) - available_ids)
    if unknown:
        raise ValueError(f"{field_name} references unknown ids: {', '.join(unknown)}.")


# =============================================================================
# Detection and evidence
# =============================================================================


@dataclass(frozen=True, slots=True)
class DetectionSignal:
    """A non-causal signal emitted by the validation or interpretation layer.

    At least one of ``finding_id`` or ``metric_id`` must be provided.  This
    object records what triggered an investigation; it never states why the
    signal occurred.
    """

    id: str
    domain: str
    summary: str
    finding_id: str | None = None
    metric_id: str | None = None
    observed_value: Any = None
    source: str = "validation_engine"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "domain", _require_identifier(self.domain, "domain"))
        object.__setattr__(self, "summary", _require_text(self.summary, "summary"))
        object.__setattr__(
            self,
            "finding_id",
            None if self.finding_id is None else _require_identifier(self.finding_id, "finding_id"),
        )
        object.__setattr__(
            self,
            "metric_id",
            None if self.metric_id is None else _require_identifier(self.metric_id, "metric_id"),
        )
        object.__setattr__(self, "source", _require_identifier(self.source, "source"))
        object.__setattr__(self, "observed_value", _deep_freeze(self.observed_value))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.finding_id is None and self.metric_id is None:
            raise ValueError("DetectionSignal requires finding_id, metric_id, or both.")


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One auditable observation collected during causal investigation."""

    id: str
    source_kind: EvidenceSourceKind
    summary: str
    locator: str
    collected_at: datetime
    details: str | None = None
    sha256: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self,
            "source_kind",
            _require_enum(self.source_kind, EvidenceSourceKind, "source_kind"),
        )
        object.__setattr__(self, "summary", _require_text(self.summary, "summary"))
        object.__setattr__(self, "locator", _require_text(self.locator, "locator"))
        object.__setattr__(self, "collected_at", _normalize_datetime(self.collected_at, "collected_at"))
        object.__setattr__(self, "details", _optional_text(self.details, "details"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.sha256 is not None:
            if not isinstance(self.sha256, str):
                raise TypeError("sha256 must be a string or None.")
            normalized = self.sha256.strip().lower()
            if not _SHA256_PATTERN.fullmatch(normalized):
                raise ValueError("sha256 must contain exactly 64 lowercase hexadecimal characters.")
            object.__setattr__(self, "sha256", normalized)


@dataclass(frozen=True, slots=True)
class HypothesisEvidenceAssessment:
    """Auditable interpretation of one evidence item for one hypothesis.

    Evidence remains an observation.  This link records how an investigator
    interprets that observation in the context of a particular hypothesis and
    requires an explicit rationale, preventing direction from being treated as
    an intrinsic property of the evidence itself.
    """

    evidence_id: str
    direction: EvidenceDirection
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_id",
            _require_identifier(self.evidence_id, "evidence_id"),
        )
        object.__setattr__(
            self,
            "direction",
            _require_enum(self.direction, EvidenceDirection, "direction"),
        )
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))


# =============================================================================
# Hypotheses and verification
# =============================================================================


@dataclass(frozen=True, slots=True)
class CausalHypothesis:
    """A testable causal explanation, explicitly separated from evidence."""

    id: str
    category_id: str
    statement: str
    rationale: str
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    certainty: CausalCertainty = CausalCertainty.HYPOTHETICAL
    evidence_assessments: tuple[HypothesisEvidenceAssessment, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "category_id", _require_identifier(self.category_id, "category_id"))
        object.__setattr__(self, "statement", _require_text(self.statement, "statement"))
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))
        object.__setattr__(self, "status", _require_enum(self.status, HypothesisStatus, "status"))
        object.__setattr__(
            self,
            "certainty",
            _require_enum(self.certainty, CausalCertainty, "certainty"),
        )
        object.__setattr__(
            self,
            "evidence_assessments",
            _normalize_model_tuple(
                self.evidence_assessments,
                HypothesisEvidenceAssessment,
                "evidence_assessments",
            ),
        )
        assessment_ids = [item.evidence_id for item in self.evidence_assessments]
        if len(assessment_ids) != len(set(assessment_ids)):
            raise ValueError("evidence_assessments must reference each evidence item at most once.")
        supporting_evidence_ids = tuple(
            item.evidence_id
            for item in self.evidence_assessments
            if item.direction is EvidenceDirection.SUPPORTS
        )
        refuting_evidence_ids = tuple(
            item.evidence_id
            for item in self.evidence_assessments
            if item.direction is EvidenceDirection.REFUTES
        )
        object.__setattr__(
            self,
            "limitations",
            _normalize_text_tuple(self.limitations, "limitations"),
        )

        overlap = set(supporting_evidence_ids) & set(refuting_evidence_ids)
        if overlap:
            raise ValueError(
                "The same evidence cannot simultaneously support and refute a hypothesis: "
                + ", ".join(sorted(overlap))
                + "."
            )
        if self.status is HypothesisStatus.SUPPORTED and not supporting_evidence_ids:
            raise ValueError("A supported hypothesis requires supporting evidence.")
        if self.status is HypothesisStatus.REFUTED and not refuting_evidence_ids:
            raise ValueError("A refuted hypothesis requires refuting evidence.")
        if self.certainty is CausalCertainty.CONFIRMED and self.status is not HypothesisStatus.SUPPORTED:
            raise ValueError("Confirmed certainty requires a supported hypothesis.")
        if self.certainty in {CausalCertainty.PROBABLE, CausalCertainty.CONFIRMED} and not supporting_evidence_ids:
            raise ValueError(f"{self.certainty.value} certainty requires supporting evidence.")
        if self.status is HypothesisStatus.REFUTED and self.certainty not in {
            CausalCertainty.UNASSESSED,
            CausalCertainty.HYPOTHETICAL,
        }:
            raise ValueError("A refuted hypothesis cannot retain positive causal certainty.")

    @property
    def supporting_evidence_ids(self) -> tuple[str, ...]:
        """Evidence explicitly assessed as supporting this hypothesis."""

        return tuple(
            item.evidence_id
            for item in self.evidence_assessments
            if item.direction is EvidenceDirection.SUPPORTS
        )

    @property
    def refuting_evidence_ids(self) -> tuple[str, ...]:
        """Evidence explicitly assessed as refuting this hypothesis."""

        return tuple(
            item.evidence_id
            for item in self.evidence_assessments
            if item.direction is EvidenceDirection.REFUTES
        )


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    """One predefined, reproducible check used to test a hypothesis."""

    id: str
    hypothesis_id: str
    description: str
    procedure: str
    expected_result: str
    status: VerificationStatus = VerificationStatus.NOT_RUN
    actual_result: str | None = None
    evidence_ids: tuple[str, ...] = ()
    executed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self,
            "hypothesis_id",
            _require_identifier(self.hypothesis_id, "hypothesis_id"),
        )
        object.__setattr__(self, "description", _require_text(self.description, "description"))
        object.__setattr__(self, "procedure", _require_text(self.procedure, "procedure"))
        object.__setattr__(
            self,
            "expected_result",
            _require_text(self.expected_result, "expected_result"),
        )
        object.__setattr__(
            self,
            "status",
            _require_enum(self.status, VerificationStatus, "status"),
        )
        object.__setattr__(self, "actual_result", _optional_text(self.actual_result, "actual_result"))
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_text_tuple(self.evidence_ids, "evidence_ids", identifiers=True),
        )
        if self.executed_at is not None:
            object.__setattr__(
                self,
                "executed_at",
                _normalize_datetime(self.executed_at, "executed_at"),
            )

        completed = self.status in {
            VerificationStatus.PASSED,
            VerificationStatus.FAILED,
            VerificationStatus.INCONCLUSIVE,
        }
        if completed and self.actual_result is None:
            raise ValueError(f"{self.status.value} verification requires actual_result.")
        if completed and self.executed_at is None:
            raise ValueError(f"{self.status.value} verification requires executed_at.")
        if self.status in {VerificationStatus.PASSED, VerificationStatus.FAILED} and not self.evidence_ids:
            raise ValueError(f"{self.status.value} verification requires evidence_ids.")
        if self.status is VerificationStatus.NOT_RUN and (
            self.actual_result is not None or self.evidence_ids or self.executed_at is not None
        ):
            raise ValueError("A not-run verification cannot contain execution results.")


@dataclass(frozen=True, slots=True)
class RecommendedAction:
    """A concrete follow-up action linked to a demonstrated or suspected cause."""

    id: str
    title: str
    description: str
    priority: ActionPriority
    target_component: str
    verification_after_action: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "description", _require_text(self.description, "description"))
        object.__setattr__(self, "priority", _require_enum(self.priority, ActionPriority, "priority"))
        object.__setattr__(
            self,
            "target_component",
            _require_identifier(self.target_component, "target_component"),
        )
        object.__setattr__(
            self,
            "verification_after_action",
            _require_text(self.verification_after_action, "verification_after_action"),
        )


# =============================================================================
# Investigation aggregate
# =============================================================================


@dataclass(frozen=True, slots=True)
class InvestigationCase:
    """Complete, auditable investigation of one validation discrepancy."""

    id: str
    title: str
    status: InvestigationStatus
    signals: tuple[DetectionSignal, ...]
    hypotheses: tuple[CausalHypothesis, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    verifications: tuple[VerificationCheck, ...] = ()
    selected_hypothesis_id: str | None = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    owner: str | None = None
    notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(
            self,
            "status",
            _require_enum(self.status, InvestigationStatus, "status"),
        )
        object.__setattr__(self, "signals", _normalize_model_tuple(self.signals, DetectionSignal, "signals"))
        object.__setattr__(
            self,
            "hypotheses",
            _normalize_model_tuple(self.hypotheses, CausalHypothesis, "hypotheses"),
        )
        object.__setattr__(self, "evidence", _normalize_model_tuple(self.evidence, EvidenceItem, "evidence"))
        object.__setattr__(
            self,
            "verifications",
            _normalize_model_tuple(self.verifications, VerificationCheck, "verifications"),
        )
        object.__setattr__(self, "opened_at", _normalize_datetime(self.opened_at, "opened_at"))
        object.__setattr__(self, "updated_at", _normalize_datetime(self.updated_at, "updated_at"))
        object.__setattr__(self, "owner", _optional_text(self.owner, "owner"))
        object.__setattr__(self, "notes", _normalize_text_tuple(self.notes, "notes"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if not self.signals:
            raise ValueError("InvestigationCase requires at least one detection signal.")
        if self.updated_at < self.opened_at:
            raise ValueError("updated_at must not precede opened_at.")

        _require_unique_ids(self.signals, "signals")
        _require_unique_ids(self.hypotheses, "hypotheses")
        _require_unique_ids(self.evidence, "evidence")
        _require_unique_ids(self.verifications, "verifications")

        hypothesis_ids = {item.id for item in self.hypotheses}
        evidence_ids = {item.id for item in self.evidence}

        for hypothesis in self.hypotheses:
            _validate_reference_ids(
                tuple(item.evidence_id for item in hypothesis.evidence_assessments),
                evidence_ids,
                f"hypothesis {hypothesis.id!r} evidence_assessments",
            )
        for verification in self.verifications:
            if verification.hypothesis_id not in hypothesis_ids:
                raise ValueError(
                    f"verification {verification.id!r} references unknown hypothesis "
                    f"{verification.hypothesis_id!r}."
                )
            _validate_reference_ids(
                verification.evidence_ids,
                evidence_ids,
                f"verification {verification.id!r} evidence_ids",
            )

        selected = self.selected_hypothesis_id
        if selected is not None:
            selected = _require_identifier(selected, "selected_hypothesis_id")
            object.__setattr__(self, "selected_hypothesis_id", selected)
            if selected not in hypothesis_ids:
                raise ValueError("selected_hypothesis_id must reference an existing hypothesis.")

        if self.status is InvestigationStatus.RESOLVED:
            if selected is None:
                raise ValueError("A resolved investigation requires selected_hypothesis_id.")
            selected_hypothesis = next(item for item in self.hypotheses if item.id == selected)
            if selected_hypothesis.status is not HypothesisStatus.SUPPORTED:
                raise ValueError("A resolved investigation must select a supported hypothesis.")
            passed = any(
                check.hypothesis_id == selected and check.status is VerificationStatus.PASSED
                for check in self.verifications
            )
            if not passed:
                raise ValueError(
                    "A resolved investigation requires at least one passed verification "
                    "for the selected hypothesis."
                )
        elif selected is not None:
            raise ValueError("selected_hypothesis_id is only valid for resolved investigations.")

    @property
    def selected_hypothesis(self) -> CausalHypothesis | None:
        """Return the selected root-cause hypothesis for a resolved case."""

        if self.selected_hypothesis_id is None:
            return None
        return next(
            hypothesis
            for hypothesis in self.hypotheses
            if hypothesis.id == self.selected_hypothesis_id
        )


# =============================================================================
# Publishable knowledge
# =============================================================================


@dataclass(frozen=True, slots=True)
class KnowledgeEntry:
    """Reusable, evidence-backed root-cause knowledge derived from a case.

    ``VALIDATED`` entries are safe for deterministic interpretation rules.
    ``DRAFT`` entries may describe useful hypotheses but must not be presented as
    demonstrated causes.
    """

    id: str
    title: str
    status: KnowledgeEntryStatus
    category_id: str
    detection_pattern: str
    root_cause: str
    causal_certainty: CausalCertainty
    source_investigation_id: str
    source_hypothesis_id: str
    evidence: tuple[EvidenceItem, ...]
    verifications: tuple[VerificationCheck, ...]
    recommended_actions: tuple[RecommendedAction, ...]
    applicability: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    supersedes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(
            self,
            "status",
            _require_enum(self.status, KnowledgeEntryStatus, "status"),
        )
        object.__setattr__(self, "category_id", _require_identifier(self.category_id, "category_id"))
        object.__setattr__(
            self,
            "detection_pattern",
            _require_text(self.detection_pattern, "detection_pattern"),
        )
        object.__setattr__(self, "root_cause", _require_text(self.root_cause, "root_cause"))
        object.__setattr__(
            self,
            "causal_certainty",
            _require_enum(self.causal_certainty, CausalCertainty, "causal_certainty"),
        )
        object.__setattr__(
            self,
            "source_investigation_id",
            _require_identifier(self.source_investigation_id, "source_investigation_id"),
        )
        object.__setattr__(
            self,
            "source_hypothesis_id",
            _require_identifier(self.source_hypothesis_id, "source_hypothesis_id"),
        )
        object.__setattr__(self, "evidence", _normalize_model_tuple(self.evidence, EvidenceItem, "evidence"))
        object.__setattr__(
            self,
            "verifications",
            _normalize_model_tuple(self.verifications, VerificationCheck, "verifications"),
        )
        object.__setattr__(
            self,
            "recommended_actions",
            _normalize_model_tuple(
                self.recommended_actions,
                RecommendedAction,
                "recommended_actions",
            ),
        )
        object.__setattr__(
            self,
            "applicability",
            _normalize_text_tuple(self.applicability, "applicability"),
        )
        object.__setattr__(
            self,
            "limitations",
            _normalize_text_tuple(self.limitations, "limitations"),
        )
        object.__setattr__(self, "created_at", _normalize_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _normalize_datetime(self.updated_at, "updated_at"))
        object.__setattr__(
            self,
            "supersedes",
            _normalize_text_tuple(self.supersedes, "supersedes", identifiers=True),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at.")
        if self.id in self.supersedes:
            raise ValueError("A knowledge entry cannot supersede itself.")
        if not self.applicability:
            raise ValueError("KnowledgeEntry requires at least one applicability condition.")

        _require_unique_ids(self.evidence, "evidence")
        _require_unique_ids(self.verifications, "verifications")
        _require_unique_ids(self.recommended_actions, "recommended_actions")

        if self.status is KnowledgeEntryStatus.VALIDATED:
            if self.causal_certainty is not CausalCertainty.CONFIRMED:
                raise ValueError("A validated knowledge entry requires confirmed causal certainty.")
            if not self.evidence:
                raise ValueError("A validated knowledge entry requires evidence.")
            if not any(check.status is VerificationStatus.PASSED for check in self.verifications):
                raise ValueError("A validated knowledge entry requires a passed verification.")
            if not self.recommended_actions:
                raise ValueError("A validated knowledge entry requires at least one recommended action.")
        elif self.causal_certainty is CausalCertainty.CONFIRMED:
            raise ValueError("Confirmed causal certainty is reserved for validated knowledge entries.")

        evidence_ids = {item.id for item in self.evidence}
        for verification in self.verifications:
            if verification.hypothesis_id != self.source_hypothesis_id:
                raise ValueError(
                    f"verification {verification.id!r} must reference source_hypothesis_id "
                    f"{self.source_hypothesis_id!r}."
                )
            _validate_reference_ids(
                verification.evidence_ids,
                evidence_ids,
                f"verification {verification.id!r} evidence_ids",
            )
