"""Explainable and deterministic prioritisation of causal candidates.

The ranking stage orders candidate explanations so that the most informative and
verifiable hypotheses are investigated first.  It does **not** establish
causality, confirm a hypothesis or replace deterministic verification.

The documented score is preserved exactly::

    score = (
        evidence_support
        + knowledge_match
        + provenance_match
        + reproducibility
        + mechanism_specificity
        - contradictory_evidence
        - missing_evidence
        - alternative_explanations
    )

Every component is independently inspectable, bounded and produced by injected
``RankingCriterion`` objects.  The default criteria use only explicit model
fields and auditable metadata; no fuzzy matching, statistical learning or hidden
weights are used.

Scientific guarantees
---------------------
* Input order never changes scores, ranks or tie resolution.
* Ranking changes ``GENERATED`` candidates only to ``PRIORITIZED``.
* Supporting and contradictory evidence must be explicitly candidate-bound.
* Neutral evidence is never silently interpreted as causal support.
* Missing evidence is represented as a penalty and a human-readable obligation.
* Ties are preserved through equal scores but receive deterministic ordinal ranks.
* Criterion failures are isolated and translated at the component boundary.
* Empty candidate sets are valid scientific outputs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from math import isclose, isfinite
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable

from validation.knowledge.models import KnowledgeEntry, KnowledgeEntryStatus
from validation.root_cause.candidates import CandidateGeneration
from validation.root_cause.exceptions import (
    RootCauseInputError,
    RootCauseIntegrityError,
)
from validation.root_cause.models import (
    CandidateAssessment,
    CandidateStatus,
    CausalCandidate,
    DiscrepancySignal,
    EvidenceDirection,
    EvidenceReference,
    RootCauseRequest,
)

__all__ = [
    "AlternativeExplanationCriterion",
    "CandidateRanker",
    "CandidateRanking",
    "CriterionAssessment",
    "EvidenceCriterion",
    "KnowledgeMatchCriterion",
    "MechanismSpecificityCriterion",
    "MissingEvidenceCriterion",
    "ProvenanceCriterion",
    "RankingContext",
    "RankingCriterion",
    "RankingDiagnostic",
    "RankingSeverity",
    "ReproducibilityCriterion",
    "rank_candidates",
]


_IDENTIFIER_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SCORE_TOLERANCE: Final = 1e-9
_DEFAULT_MAX_COMPONENT: Final = 1.0


class RankingSeverity(str, Enum):
    """Severity of an auditable, non-fatal ranking diagnostic."""

    INFO = "info"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class RankingDiagnostic:
    """One deterministic diagnostic emitted by permissive ranking."""

    code: str
    message: str
    severity: RankingSeverity = RankingSeverity.WARNING
    candidate_id: str | None = None
    criterion_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_identifier(self.code, "code"))
        object.__setattr__(self, "message", _require_text(self.message, "message"))
        if not isinstance(self.severity, RankingSeverity):
            raise TypeError("severity must be a RankingSeverity member.")
        object.__setattr__(
            self, "candidate_id", _optional_identifier(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self, "criterion_id", _optional_identifier(self.criterion_id, "criterion_id")
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class CriterionAssessment:
    """Auditable contribution produced by one ranking criterion.

    ``value`` is always non-negative.  Whether it is added or subtracted is
    defined by the criterion's stable ``component`` name and validated by the
    ranking engine.
    """

    value: float
    rationale: str
    evidence_ids: tuple[str, ...] = ()
    missing_evidence_descriptions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _require_component_score(self.value, "value"))
        object.__setattr__(self, "rationale", _require_text(self.rationale, "rationale"))
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_identifier_tuple(self.evidence_ids, "evidence_ids"),
        )
        object.__setattr__(
            self,
            "missing_evidence_descriptions",
            _normalize_text_tuple(
                self.missing_evidence_descriptions,
                "missing_evidence_descriptions",
            ),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class RankingContext:
    """Immutable catalogue used to assess one candidate collection."""

    request: RootCauseRequest
    candidates: tuple[CausalCandidate, ...]
    signals: tuple[DiscrepancySignal, ...]
    evidence: tuple[EvidenceReference, ...] = ()
    knowledge_entries: tuple[KnowledgeEntry, ...] = ()
    strict: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, RootCauseRequest):
            raise TypeError("request must be a RootCauseRequest.")
        candidates = _normalize_models(self.candidates, CausalCandidate, "candidates")
        signals = _normalize_models(self.signals, DiscrepancySignal, "signals")
        evidence = _normalize_models(self.evidence, EvidenceReference, "evidence")
        knowledge = _normalize_models(
            self.knowledge_entries, KnowledgeEntry, "knowledge_entries"
        )
        _require_unique_ids(candidates, "candidates")
        _require_unique_ids(signals, "signals")
        _require_unique_ids(evidence, "evidence")
        _require_unique_ids(knowledge, "knowledge_entries")

        object.__setattr__(
            self, "candidates", tuple(sorted(candidates, key=lambda item: item.id))
        )
        object.__setattr__(
            self, "signals", tuple(sorted(signals, key=lambda item: item.id))
        )
        object.__setattr__(
            self, "evidence", tuple(sorted(evidence, key=lambda item: item.id))
        )
        object.__setattr__(
            self,
            "knowledge_entries",
            tuple(sorted(knowledge, key=lambda item: item.id)),
        )
        if self.strict is not None and not isinstance(self.strict, bool):
            raise TypeError("strict must be bool or None.")
        object.__setattr__(
            self,
            "strict",
            self.request.strict_integrity if self.strict is None else self.strict,
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))
        _validate_context(self)

    @property
    def candidate_catalog(self) -> Mapping[str, CausalCandidate]:
        return MappingProxyType({item.id: item for item in self.candidates})

    @property
    def signal_catalog(self) -> Mapping[str, DiscrepancySignal]:
        return MappingProxyType({item.id: item for item in self.signals})

    @property
    def evidence_catalog(self) -> Mapping[str, EvidenceReference]:
        return MappingProxyType({item.id: item for item in self.evidence})

    @property
    def knowledge_catalog(self) -> Mapping[str, KnowledgeEntry]:
        return MappingProxyType({item.id: item for item in self.knowledge_entries})


@dataclass(frozen=True, slots=True)
class CandidateRanking:
    """Complete deterministic output of the ranking stage."""

    request_id: str
    candidates: tuple[CausalCandidate, ...]
    assessments: tuple[CandidateAssessment, ...]
    diagnostics: tuple[RankingDiagnostic, ...] = ()
    criterion_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _require_identifier(self.request_id, "request_id")
        )
        candidates = _normalize_models(self.candidates, CausalCandidate, "candidates")
        assessments = _normalize_models(
            self.assessments, CandidateAssessment, "assessments"
        )
        diagnostics = _normalize_models(
            self.diagnostics, RankingDiagnostic, "diagnostics"
        )
        _require_unique_ids(candidates, "candidates")
        assessment_ids = [item.candidate_id for item in assessments]
        if len(assessment_ids) != len(set(assessment_ids)):
            raise ValueError("assessments must reference each candidate at most once.")

        ordered_assessments = tuple(sorted(assessments, key=lambda item: item.rank))
        object.__setattr__(self, "assessments", ordered_assessments)
        candidate_by_id = {item.id: item for item in candidates}
        assessment_id_set = set(assessment_ids)
        if assessment_id_set != set(candidate_by_id):
            missing = sorted(set(candidate_by_id) - assessment_id_set)
            unknown = sorted(assessment_id_set - set(candidate_by_id))
            raise ValueError(
                "assessments must cover candidates exactly; "
                f"missing={missing}, unknown={unknown}."
            )
        expected_ranks = tuple(range(1, len(ordered_assessments) + 1))
        actual_ranks = tuple(item.rank for item in ordered_assessments)
        if actual_ranks != expected_ranks:
            raise ValueError("assessment ranks must be contiguous and one-based.")
        for assessment in ordered_assessments:
            component_keys = set(assessment.score_components)
            if component_keys != _ALLOWED_COMPONENTS:
                raise ValueError(
                    "assessment score_components must cover the documented formula exactly; "
                    f"candidate_id={assessment.candidate_id!r}, "
                    f"missing={sorted(_ALLOWED_COMPONENTS - component_keys)}, "
                    f"unknown={sorted(component_keys - _ALLOWED_COMPONENTS)}."
                )
            for component in _ALLOWED_COMPONENTS:
                if not isclose(
                    assessment.score_components[component],
                    getattr(assessment, component),
                    abs_tol=_SCORE_TOLERANCE,
                ):
                    raise ValueError(
                        "assessment score_components disagree with named component fields; "
                        f"candidate_id={assessment.candidate_id!r}, component={component!r}."
                    )

        ordered_candidates = tuple(
            candidate_by_id[item.candidate_id] for item in ordered_assessments
        )
        for candidate in ordered_candidates:
            if candidate.status is not CandidateStatus.PRIORITIZED:
                raise ValueError(
                    "CandidateRanking candidates must have status PRIORITIZED."
                )
        object.__setattr__(self, "candidates", ordered_candidates)
        object.__setattr__(
            self,
            "diagnostics",
            tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.code,
                        item.candidate_id or "",
                        item.criterion_id or "",
                    ),
                )
            ),
        )
        object.__setattr__(
            self,
            "criterion_ids",
            _normalize_identifier_tuple(self.criterion_ids, "criterion_ids"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@runtime_checkable
class RankingCriterion(Protocol):
    """Injectable deterministic assessment of one documented score component."""

    @property
    def id(self) -> str:
        """Stable criterion identifier."""

    @property
    def component(self) -> str:
        """One field of :class:`CandidateAssessment` except ``total_score``."""

    def assess(
        self,
        candidate: CausalCandidate,
        context: RankingContext,
    ) -> CriterionAssessment:
        """Return the criterion contribution for one candidate."""


# =============================================================================
# Canonical criteria
# =============================================================================


@dataclass(frozen=True, slots=True)
class EvidenceCriterion:
    """Assess explicitly candidate-bound supporting or contradictory evidence."""

    id: str = "ranking.evidence"
    component: str = "evidence_support"

    def assess(
        self, candidate: CausalCandidate, context: RankingContext
    ) -> CriterionAssessment:
        related = tuple(
            item
            for item in context.evidence
            if item.related_candidate_id == candidate.id
        )
        supporting = tuple(
            item.id for item in related if item.direction is EvidenceDirection.SUPPORTS
        )
        contradictory = tuple(
            item.id
            for item in related
            if item.direction is EvidenceDirection.CONTRADICTS
        )
        if self.component == "evidence_support":
            return CriterionAssessment(
                value=_saturating_fraction(len(supporting), 3),
                rationale=(
                    f"{len(supporting)} explicit supporting evidence item(s) are bound "
                    "to the candidate."
                ),
                evidence_ids=supporting,
            )
        if self.component == "contradictory_evidence":
            return CriterionAssessment(
                value=_saturating_fraction(len(contradictory), 3),
                rationale=(
                    f"{len(contradictory)} explicit contradictory evidence item(s) are "
                    "bound to the candidate."
                ),
                evidence_ids=contradictory,
            )
        raise ValueError("EvidenceCriterion component is not supported.")


@dataclass(frozen=True, slots=True)
class KnowledgeMatchCriterion:
    """Reward an exact, explicitly referenced validated knowledge entry."""

    id: str = "ranking.knowledge_match"
    component: str = "knowledge_match"

    def assess(
        self, candidate: CausalCandidate, context: RankingContext
    ) -> CriterionAssessment:
        if candidate.knowledge_entry_id is None:
            return CriterionAssessment(
                value=0.0,
                rationale="Candidate is not derived from a validated knowledge entry.",
            )
        entry = context.knowledge_catalog.get(candidate.knowledge_entry_id)
        if entry is None:
            return CriterionAssessment(
                value=0.0,
                rationale="Referenced knowledge entry is unavailable to the ranking context.",
            )
        if entry.status is not KnowledgeEntryStatus.VALIDATED:
            return CriterionAssessment(
                value=0.0,
                rationale=(
                    f"Referenced knowledge entry {entry.id!r} is {entry.status.value!r}, "
                    "not validated."
                ),
                metadata={
                    "knowledge_entry_id": entry.id,
                    "knowledge_entry_status": entry.status.value,
                },
            )
        return CriterionAssessment(
            value=1.0,
            rationale=f"Exact validated knowledge entry {entry.id!r} is available.",
            metadata={
                "knowledge_entry_id": entry.id,
                "knowledge_entry_status": entry.status.value,
            },
        )


@dataclass(frozen=True, slots=True)
class ProvenanceCriterion:
    """Assess explicit source-module/state provenance overlap."""

    id: str = "ranking.provenance_match"
    component: str = "provenance_match"

    def assess(
        self, candidate: CausalCandidate, context: RankingContext
    ) -> CriterionAssessment:
        candidate_tokens = _provenance_tokens(candidate.metadata)
        signal_tokens: set[str] = set()
        for signal_id in candidate.signal_ids:
            signal = context.signal_catalog[signal_id]
            signal_tokens.update(_provenance_tokens(signal.metadata))
            signal_tokens.update(signal.affected_entity_ids)
        overlap = candidate_tokens & signal_tokens
        denominator = max(len(candidate_tokens), 1)
        score = min(len(overlap) / denominator, 1.0) if candidate_tokens else 0.0
        return CriterionAssessment(
            value=score,
            rationale=(
                f"{len(overlap)} of {len(candidate_tokens)} explicit candidate provenance "
                "token(s) match affected signal provenance."
            ),
            metadata={"matched_tokens": tuple(sorted(overlap))},
        )


@dataclass(frozen=True, slots=True)
class ReproducibilityCriterion:
    """Assess whether the candidate exposes deterministic verification inputs."""

    id: str = "ranking.reproducibility"
    component: str = "reproducibility"

    def assess(
        self, candidate: CausalCandidate, context: RankingContext
    ) -> CriterionAssessment:
        checks = (
            bool(candidate.expected_observations),
            bool(candidate.falsification_criteria),
            bool(candidate.prerequisite_evidence_ids),
            bool(_provenance_tokens(candidate.metadata)),
        )
        score = sum(checks) / len(checks)
        return CriterionAssessment(
            value=score,
            rationale=(
                f"Candidate satisfies {sum(checks)} of {len(checks)} explicit "
                "reproducibility prerequisites."
            ),
        )


@dataclass(frozen=True, slots=True)
class MechanismSpecificityCriterion:
    """Assess structural specificity without using linguistic similarity."""

    id: str = "ranking.mechanism_specificity"
    component: str = "mechanism_specificity"

    def assess(
        self, candidate: CausalCandidate, context: RankingContext
    ) -> CriterionAssessment:
        provenance = _provenance_tokens(candidate.metadata)
        source_anchors = tuple(
            value
            for value in (
                candidate.source_rule_id,
                candidate.knowledge_entry_id,
                candidate.investigation_protocol_id,
            )
            if value is not None
        )
        checks = (
            candidate.category.value != "root_cause.unknown",
            bool(provenance),
            bool(candidate.expected_observations),
            bool(candidate.falsification_criteria),
            len(source_anchors) == 1,
        )
        return CriterionAssessment(
            value=sum(checks) / len(checks),
            rationale=(
                f"Candidate satisfies {sum(checks)} of {len(checks)} explicit "
                "mechanism-specificity criteria."
            ),
        )


@dataclass(frozen=True, slots=True)
class MissingEvidenceCriterion:
    """Penalise absent prerequisite evidence and unspecified test obligations."""

    id: str = "ranking.missing_evidence"
    component: str = "missing_evidence"

    def assess(
        self, candidate: CausalCandidate, context: RankingContext
    ) -> CriterionAssessment:
        available = set(context.evidence_catalog)
        missing_ids = tuple(
            item_id
            for item_id in candidate.prerequisite_evidence_ids
            if item_id not in available
        )
        descriptions = [f"Missing prerequisite evidence {item_id!r}." for item_id in missing_ids]
        if not candidate.expected_observations:
            descriptions.append("Expected observations are not specified.")
        if not candidate.falsification_criteria:
            descriptions.append("Falsification criteria are not specified.")
        obligation_count = max(
            len(candidate.prerequisite_evidence_ids) + 2,
            1,
        )
        return CriterionAssessment(
            value=min(len(descriptions) / obligation_count, 1.0),
            rationale=f"{len(descriptions)} evidence or test obligation(s) are missing.",
            missing_evidence_descriptions=tuple(descriptions),
            metadata={"missing_prerequisite_ids": missing_ids},
        )


@dataclass(frozen=True, slots=True)
class AlternativeExplanationCriterion:
    """Penalise unresolved alternatives linked to the same discrepancy."""

    id: str = "ranking.alternative_explanations"
    component: str = "alternative_explanations"

    def assess(
        self, candidate: CausalCandidate, context: RankingContext
    ) -> CriterionAssessment:
        alternatives = tuple(
            item_id
            for item_id in candidate.alternative_candidate_ids
            if item_id in context.candidate_catalog
        )
        return CriterionAssessment(
            value=_saturating_fraction(len(alternatives), 3),
            rationale=f"{len(alternatives)} unresolved alternative candidate(s) remain.",
            metadata={"alternative_candidate_ids": alternatives},
        )


_DEFAULT_CRITERIA: Final[tuple[RankingCriterion, ...]] = (
    EvidenceCriterion(component="evidence_support"),
    KnowledgeMatchCriterion(),
    ProvenanceCriterion(),
    ReproducibilityCriterion(),
    MechanismSpecificityCriterion(),
    EvidenceCriterion(id="ranking.contradictory_evidence", component="contradictory_evidence"),
    MissingEvidenceCriterion(),
    AlternativeExplanationCriterion(),
)

_ALLOWED_COMPONENTS: Final = frozenset(
    {
        "evidence_support",
        "knowledge_match",
        "provenance_match",
        "reproducibility",
        "mechanism_specificity",
        "contradictory_evidence",
        "missing_evidence",
        "alternative_explanations",
    }
)


class CandidateRanker:
    """Coordinate deterministic, explainable candidate ranking."""

    def __init__(
        self,
        criteria: Sequence[RankingCriterion] = _DEFAULT_CRITERIA,
    ) -> None:
        self._criteria = _normalize_criteria(criteria)

    @property
    def criteria(self) -> tuple[RankingCriterion, ...]:
        return self._criteria

    def rank(self, context: RankingContext) -> CandidateRanking:
        if not isinstance(context, RankingContext):
            raise TypeError("context must be a RankingContext.")

        raw: list[tuple[CausalCandidate, dict[str, float], dict[str, CriterionAssessment]]] = []
        diagnostics: list[RankingDiagnostic] = []

        for candidate in context.candidates:
            components = {name: 0.0 for name in _ALLOWED_COMPONENTS}
            details: dict[str, CriterionAssessment] = {}
            for criterion in self._criteria:
                try:
                    assessment = criterion.assess(candidate, context)
                    if not isinstance(assessment, CriterionAssessment):
                        raise TypeError(
                            "criterion assess() must return CriterionAssessment."
                        )
                except Exception as exc:  # extension boundary
                    if context.strict:
                        raise RootCauseIntegrityError(
                            "Candidate ranking criterion violated its execution contract.",
                            context={
                                "candidate_id": candidate.id,
                                "criterion_id": criterion.id,
                                "exception_type": type(exc).__name__,
                                "exception_message": str(exc),
                            },
                        ) from exc
                    diagnostics.append(
                        RankingDiagnostic(
                            code="ranking.criterion_failed",
                            message="Ranking criterion failed and contributed zero.",
                            candidate_id=candidate.id,
                            criterion_id=criterion.id,
                            metadata={"exception_type": type(exc).__name__},
                        )
                    )
                    assessment = CriterionAssessment(
                        value=0.0,
                        rationale="Criterion failed in permissive mode and contributed zero.",
                    )
                components[criterion.component] = assessment.value
                details[criterion.component] = assessment
            raw.append((candidate, components, details))

        scored = [
            (candidate, _calculate_total(components), components, details)
            for candidate, components, details in raw
        ]
        scored.sort(key=lambda item: (-item[1], item[0].id))

        assessments: list[CandidateAssessment] = []
        prioritized: list[CausalCandidate] = []
        for rank, (candidate, total, components, details) in enumerate(scored, start=1):
            supporting = details["evidence_support"].evidence_ids
            contradictory = details["contradictory_evidence"].evidence_ids
            missing = details["missing_evidence"].missing_evidence_descriptions
            rationale = _compose_rationale(candidate, total, components, details)
            assessments.append(
                CandidateAssessment(
                    candidate_id=candidate.id,
                    rank=rank,
                    total_score=total,
                    supporting_evidence_ids=supporting,
                    contradictory_evidence_ids=contradictory,
                    missing_evidence_descriptions=missing,
                    rationale=rationale,
                    score_components=components,
                    **components,
                )
            )
            prioritized.append(replace(candidate, status=CandidateStatus.PRIORITIZED))

        return CandidateRanking(
            request_id=context.request.id,
            candidates=tuple(prioritized),
            assessments=tuple(assessments),
            diagnostics=tuple(diagnostics),
            criterion_ids=tuple(item.id for item in self._criteria),
            metadata={
                "formula": (
                    "evidence_support + knowledge_match + provenance_match + "
                    "reproducibility + mechanism_specificity - contradictory_evidence - "
                    "missing_evidence - alternative_explanations"
                ),
                "tie_breaker": "candidate_id_ascending",
                "context": context.metadata,
            },
        )


# =============================================================================
# Functional API
# =============================================================================


def rank_candidates(
    request: RootCauseRequest,
    candidates: CandidateGeneration | Sequence[CausalCandidate],
    *,
    signals: Sequence[DiscrepancySignal],
    evidence: Sequence[EvidenceReference] = (),
    knowledge_entries: Sequence[KnowledgeEntry] = (),
    criteria: Sequence[RankingCriterion] = _DEFAULT_CRITERIA,
    strict: bool | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CandidateRanking:
    """Rank candidates through the canonical deterministic pipeline."""

    if isinstance(candidates, CandidateGeneration):
        if candidates.request_id != request.id:
            raise RootCauseInputError(
                "Candidate generation belongs to a different request.",
                context={
                    "request_id": request.id,
                    "candidate_generation_request_id": candidates.request_id,
                },
            )
        candidate_values = candidates.candidates
    else:
        candidate_values = tuple(candidates)

    context = RankingContext(
        request=request,
        candidates=tuple(candidate_values),
        signals=tuple(signals),
        evidence=tuple(evidence),
        knowledge_entries=tuple(knowledge_entries),
        strict=strict,
        metadata={} if metadata is None else metadata,
    )
    return CandidateRanker(criteria).rank(context)


# =============================================================================
# Validation and deterministic helpers
# =============================================================================


def _validate_context(context: RankingContext) -> None:
    signal_ids = set(context.signal_catalog)
    evidence_ids = set(context.evidence_catalog)
    candidate_ids = set(context.candidate_catalog)
    knowledge_ids = set(context.knowledge_catalog)
    requested_domains = set(context.request.requested_domains)

    for signal in context.signals:
        if requested_domains and signal.domain not in requested_domains:
            raise RootCauseInputError(
                "Ranking signal is outside the request's validation domains.",
                context={
                    "signal_id": signal.id,
                    "signal_domain": signal.domain.value,
                    "requested_domains": tuple(
                        sorted(domain.value for domain in requested_domains)
                    ),
                },
            )
        missing_signal_evidence = sorted(set(signal.evidence_ids) - evidence_ids)
        if missing_signal_evidence:
            raise RootCauseIntegrityError(
                "Ranking signal references unavailable evidence.",
                context={
                    "signal_id": signal.id,
                    "missing_evidence_ids": missing_signal_evidence,
                },
            )

    for candidate in context.candidates:
        if candidate.status is not CandidateStatus.GENERATED:
            raise RootCauseInputError(
                "Ranking accepts only newly generated candidates.",
                context={"candidate_id": candidate.id, "status": candidate.status.value},
            )
        missing_signals = sorted(set(candidate.signal_ids) - signal_ids)
        if missing_signals:
            raise RootCauseIntegrityError(
                "Candidate references unavailable signals.",
                context={"candidate_id": candidate.id, "missing_signal_ids": missing_signals},
            )
        missing_alternatives = sorted(
            set(candidate.alternative_candidate_ids) - candidate_ids
        )
        if missing_alternatives:
            raise RootCauseIntegrityError(
                "Candidate references unavailable alternatives.",
                context={
                    "candidate_id": candidate.id,
                    "missing_alternative_candidate_ids": missing_alternatives,
                },
            )
        if candidate.knowledge_entry_id is not None:
            if candidate.knowledge_entry_id not in knowledge_ids:
                raise RootCauseIntegrityError(
                    "Candidate knowledge entry is unavailable to ranking.",
                    context={
                        "candidate_id": candidate.id,
                        "knowledge_entry_id": candidate.knowledge_entry_id,
                    },
                )
            entry = context.knowledge_catalog[candidate.knowledge_entry_id]
            if entry.status is not KnowledgeEntryStatus.VALIDATED:
                raise RootCauseIntegrityError(
                    "Candidate references a knowledge entry that is not validated.",
                    context={
                        "candidate_id": candidate.id,
                        "knowledge_entry_id": entry.id,
                        "knowledge_entry_status": entry.status.value,
                    },
                )

    for item in context.evidence:
        if item.direction is EvidenceDirection.NEUTRAL:
            if item.related_candidate_id is not None:
                raise RootCauseIntegrityError(
                    "Neutral evidence must not be candidate-bound during ranking.",
                    context={"evidence_id": item.id},
                )
            continue
        if item.related_candidate_id not in candidate_ids:
            raise RootCauseIntegrityError(
                "Directional evidence references an unavailable candidate.",
                context={
                    "evidence_id": item.id,
                    "related_candidate_id": item.related_candidate_id,
                },
            )

    # Prerequisite IDs may deliberately be absent; MissingEvidenceCriterion must
    # record them rather than treating scientific incompleteness as corruption.
    _ = evidence_ids


def _normalize_criteria(
    values: Sequence[RankingCriterion],
) -> tuple[RankingCriterion, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("criteria must be a sequence of RankingCriterion objects.")
    normalized = tuple(values)
    seen_ids: set[str] = set()
    seen_components: set[str] = set()
    for index, item in enumerate(normalized):
        if not isinstance(item, RankingCriterion):
            raise TypeError(f"criteria[{index}] does not satisfy RankingCriterion.")
        try:
            criterion_id = _require_identifier(item.id, f"criteria[{index}].id")
            component = _require_identifier(
                item.component, f"criteria[{index}].component"
            )
        except Exception as exc:
            raise TypeError(
                f"criteria[{index}] exposes an invalid ranking contract."
            ) from exc
        if component not in _ALLOWED_COMPONENTS:
            raise ValueError(f"Unsupported ranking component {component!r}.")
        if criterion_id in seen_ids:
            raise ValueError(f"Duplicate ranking criterion id {criterion_id!r}.")
        if component in seen_components:
            raise ValueError(f"Duplicate ranking component {component!r}.")
        seen_ids.add(criterion_id)
        seen_components.add(component)
    missing = sorted(_ALLOWED_COMPONENTS - seen_components)
    if missing:
        raise ValueError("criteria must cover every documented score component: " + ", ".join(missing))
    return tuple(sorted(normalized, key=lambda item: item.component))


def _calculate_total(components: Mapping[str, float]) -> float:
    total = (
        components["evidence_support"]
        + components["knowledge_match"]
        + components["provenance_match"]
        + components["reproducibility"]
        + components["mechanism_specificity"]
        - components["contradictory_evidence"]
        - components["missing_evidence"]
        - components["alternative_explanations"]
    )
    return 0.0 if isclose(total, 0.0, abs_tol=_SCORE_TOLERANCE) else total


def _compose_rationale(
    candidate: CausalCandidate,
    total: float,
    components: Mapping[str, float],
    details: Mapping[str, CriterionAssessment],
) -> str:
    ordered = (
        "evidence_support",
        "knowledge_match",
        "provenance_match",
        "reproducibility",
        "mechanism_specificity",
        "contradictory_evidence",
        "missing_evidence",
        "alternative_explanations",
    )
    component_text = "; ".join(
        f"{name}={components[name]:.6g} ({details[name].rationale})"
        for name in ordered
    )
    return (
        f"Candidate {candidate.id!r} received explainable priority score "
        f"{total:.6g}. {component_text} Ranking prioritises verification and "
        "does not establish causality."
    )


def _provenance_tokens(metadata: Mapping[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in (
        "source_module",
        "source_state",
        "module",
        "state",
        "transition",
        "component",
        "exporter",
        "metric_id",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            tokens.add(value.strip())
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            tokens.update(item.strip() for item in value if isinstance(item, str) and item.strip())
    return tokens


def _saturating_fraction(count: int, saturation: int) -> float:
    if count <= 0:
        return 0.0
    return min(count / saturation, 1.0)


def _require_component_score(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a real number.")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite.")
    if normalized < 0.0 or normalized > _DEFAULT_MAX_COMPONENT:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0.")
    return normalized


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _require_identifier(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, '.', '_', ':', or '-'."
        )
    return normalized


def _optional_identifier(value: str | None, field_name: str) -> str | None:
    return None if value is None else _require_identifier(value, field_name)


def _normalize_identifier_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of identifiers.")
    return tuple(sorted({_require_identifier(item, field_name) for item in values}))


def _normalize_text_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    return tuple(sorted({_require_text(item, field_name) for item in values}))


def _normalize_models(values: Sequence[Any], model_type: type[Any], field_name: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {model_type.__name__} values.")
    normalized = tuple(values)
    for index, value in enumerate(normalized):
        if not isinstance(value, model_type):
            raise TypeError(
                f"{field_name}[{index}] must be {model_type.__name__}, got {type(value).__name__}."
            )
    return normalized


def _require_unique_ids(values: Sequence[Any], field_name: str) -> None:
    ids = [item.id for item in values]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{field_name} contains duplicate identifiers.")


def _deep_freeze(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("metadata must not contain NaN or infinity.")
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("metadata mapping keys must be strings.")
            normalized[key] = _deep_freeze(item)
        return MappingProxyType(normalized)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_deep_freeze(item) for item in value), key=repr))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_deep_freeze(item) for item in value)
    raise TypeError(f"Unsupported immutable metadata type {type(value).__name__}.")


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized = _deep_freeze(value)
    if not isinstance(normalized, Mapping):
        raise TypeError(f"{field_name} must normalize to a mapping.")
    return normalized