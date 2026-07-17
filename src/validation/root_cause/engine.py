"""Deterministic coordinator for the Phase 3 Root Cause Engine.

This module contains orchestration only.  It deliberately owns no evidence
adapters, signal heuristics, candidate rules, scoring criteria, verifier logic,
source-location heuristics, or reproduction commands.  Those behaviours are
provided by the specialised Phase 3 components and injected collaborators.

Scientific boundary
-------------------
A technical failure aborts the analysis; it is never translated into a causal
finding.  Conversely, an unresolved scientific investigation is represented by
an ``INCONCLUSIVE`` finding rather than by an exception.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from validation.knowledge.taxonomy import ValidationDomain
from validation.knowledge.models import InvestigationCase, KnowledgeEntry
from validation.knowledge.protocols import CANONICAL_PROTOCOLS, InvestigationProtocol, ProtocolCatalog
from validation.knowledge.registry import KnowledgeRegistry
from validation.orchestration.models import ArtifactReference

from .attribution import AttributionResult, AttributionRule, attribute_source
from .candidates import CandidateGeneration, CandidateRule, generate_candidates
from .evidence import (
    ArtifactIntegrityVerifier,
    EvidenceAdapter,
    EvidenceCollection,
    EvidenceRegistry,
    EvidenceSource,
    collect_evidence,
)
from .exceptions import RootCauseError, RootCauseInputError, RootCauseIntegrityError
from .models import (
    AttributionLevel,
    CandidateAssessment,
    CandidateStatus,
    CausalCandidate,
    CausalConfidence,
    DifferenceClassification,
    DiscrepancySignal,
    EvidenceReference,
    ReproductionPlan,
    RootCauseFinding,
    RootCauseReport,
    RootCauseRequest,
    RootCauseStatus,
    SourceAttribution,
    VerificationOutcome,
    VerificationResult,
)
from .ranking import CandidateRanking, RankingCriterion, rank_candidates
from .reproduction import (
    ReproductionBuild,
    ReproductionContributor,
    ReproductionContext,
    build_reproduction_plan,
)
from .signals import SignalExtraction, SignalRule, extract_signals
from .verification import (
    ExecutionFailurePolicy,
    VerificationExecution,
    VerificationPlanSource,
    VerificationStageContext,
    Verifier,
    execute_verifications,
)

__all__ = [
    "ConservativeFindingPolicy",
    "EngineInputs",
    "EngineServices",
    "EngineStage",
    "FindingDecision",
    "FindingPolicy",
    "RootCauseEngine",
    "RootCauseEngineResult",
    "StageRecord",
    "run_root_cause_analysis",
]

_SCHEMA_VERSION = 2


class EngineStage(str, Enum):
    """Stable stage identifiers for tracing one complete investigation."""

    EVIDENCE_COLLECTION = "evidence_collection"
    SIGNAL_EXTRACTION = "signal_extraction"
    CANDIDATE_GENERATION = "candidate_generation"
    CANDIDATE_RANKING = "candidate_ranking"
    VERIFICATION = "verification"
    ATTRIBUTION = "attribution"
    CLASSIFICATION = "classification"
    REPRODUCTION = "reproduction"
    REPORT_ASSEMBLY = "report_assembly"


@dataclass(frozen=True, slots=True)
class StageRecord:
    """Immutable timing and cardinality trace for one completed engine stage."""

    stage: EngineStage
    started_at: datetime
    finished_at: datetime
    input_count: int
    output_count: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.stage, EngineStage):
            raise TypeError("stage must be an EngineStage member.")
        started = _aware_datetime(self.started_at, "started_at")
        finished = _aware_datetime(self.finished_at, "finished_at")
        if finished < started:
            raise ValueError("finished_at cannot precede started_at.")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "finished_at", finished)
        object.__setattr__(self, "input_count", _non_negative_int(self.input_count, "input_count"))
        object.__setattr__(self, "output_count", _non_negative_int(self.output_count, "output_count"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


@dataclass(frozen=True, slots=True)
class EngineInputs:
    """All upstream data available to a single root-cause investigation."""

    evidence_sources: tuple[EvidenceSource, ...]
    artifacts: tuple[ArtifactReference, ...] = ()
    knowledge_registry: KnowledgeRegistry | None = None
    knowledge_entries: tuple[KnowledgeEntry, ...] = ()
    investigations: tuple[InvestigationCase, ...] = ()
    protocol_catalog: ProtocolCatalog | None = CANONICAL_PROTOCOLS
    protocols: tuple[InvestigationProtocol, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        sources = _tuple(self.evidence_sources, "evidence_sources")
        object.__setattr__(self, "evidence_sources", sources)
        artifacts = _typed_tuple(self.artifacts, ArtifactReference, "artifacts")
        _unique_ids(artifacts, "artifacts")
        object.__setattr__(self, "artifacts", tuple(sorted(artifacts, key=lambda item: item.id)))
        if self.knowledge_registry is not None and not isinstance(
            self.knowledge_registry, KnowledgeRegistry
        ):
            raise TypeError("knowledge_registry must be a KnowledgeRegistry or None.")
        entries = _typed_tuple(self.knowledge_entries, KnowledgeEntry, "knowledge_entries")
        investigations = _typed_tuple(
            self.investigations, InvestigationCase, "investigations"
        )
        protocols = _typed_tuple(self.protocols, InvestigationProtocol, "protocols")
        _unique_ids(entries, "knowledge_entries")
        _unique_ids(investigations, "investigations")
        _unique_ids(protocols, "protocols")
        object.__setattr__(self, "knowledge_entries", tuple(sorted(entries, key=lambda item: item.id)))
        object.__setattr__(self, "investigations", tuple(sorted(investigations, key=lambda item: item.id)))
        object.__setattr__(self, "protocols", tuple(sorted(protocols, key=lambda item: item.id)))
        if self.protocol_catalog is not None and not isinstance(self.protocol_catalog, ProtocolCatalog):
            raise TypeError("protocol_catalog must be a ProtocolCatalog or None.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class EngineServices:
    """Injected behaviour used by the coordinator.

    Empty tuples are meaningful: for example, no verification plan sources means
    that no deterministic checks are currently available.  This is a scientific
    limitation, not an orchestration failure.
    """

    evidence_registry: EvidenceRegistry | None = None
    evidence_adapters: tuple[EvidenceAdapter, ...] = ()
    artifact_verifier: ArtifactIntegrityVerifier | None = None
    signal_rules: tuple[SignalRule, ...] = ()
    candidate_rules: tuple[CandidateRule, ...] = ()
    ranking_criteria: tuple[RankingCriterion, ...] | None = None
    verification_plan_sources: tuple[VerificationPlanSource, ...] = ()
    verifiers: tuple[Verifier, ...] = ()
    verification_failure_policy: ExecutionFailurePolicy = ExecutionFailurePolicy.RECORD_ERROR
    attribution_rules: tuple[AttributionRule, ...] = ()
    reproduction_contributors: tuple[ReproductionContributor, ...] = ()
    finding_policy: FindingPolicy | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        for name in (
            "evidence_adapters",
            "signal_rules",
            "candidate_rules",
            "verification_plan_sources",
            "verifiers",
            "attribution_rules",
            "reproduction_contributors",
        ):
            object.__setattr__(self, name, _tuple(getattr(self, name), name))
        if self.ranking_criteria is not None:
            object.__setattr__(
                self, "ranking_criteria", _tuple(self.ranking_criteria, "ranking_criteria")
            )
        if not isinstance(self.verification_failure_policy, ExecutionFailurePolicy):
            raise TypeError("verification_failure_policy must be an ExecutionFailurePolicy.")
        if self.finding_policy is not None and not isinstance(self.finding_policy, FindingPolicy):
            raise TypeError("finding_policy must satisfy FindingPolicy.")
        if not callable(self.clock):
            raise TypeError("clock must be callable.")


@dataclass(frozen=True, slots=True)
class FindingDecision:
    """Policy output used to construct one canonical ``RootCauseFinding``."""

    status: RootCauseStatus
    confidence: CausalConfidence
    classification: DifferenceClassification
    selected_candidate_ids: tuple[str, ...] = ()
    alternative_candidate_ids: tuple[str, ...] = ()
    rejected_candidate_ids: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = ()
    contradictory_evidence_ids: tuple[str, ...] = ()
    verification_result_ids: tuple[str, ...] = ()
    summary: str = "Root-cause investigation completed."
    explanation: str = "The available evidence was evaluated conservatively."
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, RootCauseStatus):
            raise TypeError("status must be a RootCauseStatus member.")
        if not isinstance(self.confidence, CausalConfidence):
            raise TypeError("confidence must be a CausalConfidence member.")
        if not isinstance(self.classification, DifferenceClassification):
            raise TypeError("classification must be a DifferenceClassification member.")
        for name in (
            "selected_candidate_ids",
            "alternative_candidate_ids",
            "rejected_candidate_ids",
            "supporting_evidence_ids",
            "contradictory_evidence_ids",
            "verification_result_ids",
        ):
            object.__setattr__(self, name, _identifier_tuple(getattr(self, name), name))
        object.__setattr__(self, "summary", _text(self.summary, "summary"))
        object.__setattr__(self, "explanation", _text(self.explanation, "explanation"))
        object.__setattr__(self, "limitations", _text_tuple(self.limitations, "limitations"))


@runtime_checkable
class FindingPolicy(Protocol):
    """Scientific policy converting assessed evidence into one finding per signal."""

    def decide(
        self,
        *,
        signal: DiscrepancySignal,
        candidates: Sequence[CausalCandidate],
        assessments: Sequence[CandidateAssessment],
        evidence: Sequence[EvidenceReference],
        verifications: Sequence[VerificationResult],
        attributions: Mapping[str, SourceAttribution],
    ) -> FindingDecision:
        """Return a conservative, internally consistent decision."""


@dataclass(frozen=True, slots=True)
class ConservativeFindingPolicy:
    """Default deterministic policy with explicit scientific thresholds.

    The score is used only to prioritise candidates.  Confirmation requires a
    supported candidate, supporting evidence, a positive deterministic check,
    and concrete source attribution.  A high score alone can never confirm a
    cause.
    """

    probable_score: float = 1.0
    plausible_score: float = 0.0
    multifactorial_margin: float = 0.15

    def __post_init__(self) -> None:
        for name in ("probable_score", "plausible_score", "multifactorial_margin"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a finite number.")
            value = float(value)
            if not _finite(value):
                raise ValueError(f"{name} must be finite.")
            if name == "multifactorial_margin" and value < 0:
                raise ValueError("multifactorial_margin must be non-negative.")
            object.__setattr__(self, name, value)

    def decide(
        self,
        *,
        signal: DiscrepancySignal,
        candidates: Sequence[CausalCandidate],
        assessments: Sequence[CandidateAssessment],
        evidence: Sequence[EvidenceReference],
        verifications: Sequence[VerificationResult],
        attributions: Mapping[str, SourceAttribution],
    ) -> FindingDecision:
        assessment_by_candidate = {item.candidate_id: item for item in assessments}
        ordered = sorted(
            (item for item in candidates if item.id in assessment_by_candidate),
            key=lambda item: (
                assessment_by_candidate[item.id].rank,
                item.id,
            ),
        )
        rejected = tuple(item.id for item in ordered if item.status is CandidateStatus.REFUTED)
        viable = [item for item in ordered if item.status is not CandidateStatus.REFUTED]

        if not viable:
            return FindingDecision(
                status=RootCauseStatus.INCONCLUSIVE,
                confidence=CausalConfidence.NONE,
                classification=signal.classification,
                rejected_candidate_ids=rejected,
                summary=f"No viable causal explanation for: {signal.summary}",
                explanation="All generated candidates were refuted or no candidate could be assessed.",
                limitations=("No non-refuted candidate remained after deterministic assessment.",),
            )

        top = viable[0]
        top_assessment = assessment_by_candidate[top.id]
        top_results = tuple(item for item in verifications if item.candidate_id == top.id)
        positive_results = tuple(
            item for item in top_results if item.outcome is VerificationOutcome.PASSED
        )
        support_ids = _supporting_ids(top.id, top_assessment, evidence, positive_results)
        contradiction_ids = _contradictory_ids(top.id, top_assessment, evidence, top_results)
        attribution = attributions.get(
            top.id, SourceAttribution(level=AttributionLevel.UNKNOWN)
        )

        semantic_status = _semantic_status(signal.classification)
        if semantic_status is not None and support_ids:
            return FindingDecision(
                status=semantic_status,
                confidence=CausalConfidence.HIGH if positive_results else CausalConfidence.MODERATE,
                classification=signal.classification,
                selected_candidate_ids=(top.id,),
                alternative_candidate_ids=tuple(item.id for item in viable[1:]),
                rejected_candidate_ids=rejected,
                supporting_evidence_ids=support_ids,
                contradictory_evidence_ids=contradiction_ids,
                verification_result_ids=tuple(item.id for item in top_results),
                summary=f"{semantic_status.value.replace('_', ' ').title()}: {signal.summary}",
                explanation=top.statement,
                limitations=_verification_limitations(top_results),
            )

        if (
            top.status is CandidateStatus.SUPPORTED
            and positive_results
            and support_ids
            and attribution.level is not AttributionLevel.UNKNOWN
        ):
            return FindingDecision(
                status=RootCauseStatus.CONFIRMED,
                confidence=CausalConfidence.VERY_HIGH,
                classification=signal.classification,
                selected_candidate_ids=(top.id,),
                alternative_candidate_ids=tuple(item.id for item in viable[1:]),
                rejected_candidate_ids=rejected,
                supporting_evidence_ids=support_ids,
                contradictory_evidence_ids=contradiction_ids,
                verification_result_ids=tuple(item.id for item in positive_results),
                summary=f"Confirmed root cause: {top.statement}",
                explanation=top.mechanism,
                limitations=_verification_limitations(top_results),
            )

        multifactorial = self._multifactorial_candidates(viable, assessment_by_candidate)
        if len(multifactorial) >= 2:
            multi_support = _ordered_union(
                *(
                    _supporting_ids(
                        candidate.id,
                        assessment_by_candidate[candidate.id],
                        evidence,
                        tuple(item for item in verifications if item.candidate_id == candidate.id),
                    )
                    for candidate in multifactorial
                )
            )
            if multi_support:
                return FindingDecision(
                    status=RootCauseStatus.MULTIFACTORIAL,
                    confidence=CausalConfidence.MODERATE,
                    classification=DifferenceClassification.MULTIFACTORIAL,
                    selected_candidate_ids=tuple(item.id for item in multifactorial),
                    alternative_candidate_ids=tuple(
                        item.id for item in viable if item not in multifactorial
                    ),
                    rejected_candidate_ids=rejected,
                    supporting_evidence_ids=multi_support,
                    verification_result_ids=tuple(
                        item.id
                        for item in verifications
                        if item.candidate_id in {candidate.id for candidate in multifactorial}
                    ),
                    summary=f"Multiple mechanisms plausibly explain: {signal.summary}",
                    explanation="Several independently supported candidates remain within the configured ranking margin.",
                    limitations=("The relative causal contribution of each mechanism is unresolved.",),
                )

        if support_ids and top_assessment.total_score >= self.probable_score:
            return FindingDecision(
                status=RootCauseStatus.PROBABLE,
                confidence=CausalConfidence.HIGH if top.status is CandidateStatus.SUPPORTED else CausalConfidence.MODERATE,
                classification=signal.classification,
                selected_candidate_ids=(top.id,),
                alternative_candidate_ids=tuple(item.id for item in viable[1:]),
                rejected_candidate_ids=rejected,
                supporting_evidence_ids=support_ids,
                contradictory_evidence_ids=contradiction_ids,
                verification_result_ids=tuple(item.id for item in top_results),
                summary=f"Probable root cause: {top.statement}",
                explanation=top.mechanism,
                limitations=("Causal confirmation remains incomplete.",) + _verification_limitations(top_results),
            )

        if top_assessment.total_score >= self.plausible_score:
            return FindingDecision(
                status=RootCauseStatus.PLAUSIBLE,
                confidence=CausalConfidence.LOW,
                classification=signal.classification,
                selected_candidate_ids=(top.id,),
                alternative_candidate_ids=tuple(item.id for item in viable[1:]),
                rejected_candidate_ids=rejected,
                contradictory_evidence_ids=contradiction_ids,
                verification_result_ids=tuple(item.id for item in top_results),
                summary=f"Plausible root cause: {top.statement}",
                explanation=top.mechanism,
                limitations=("The leading hypothesis lacks sufficient supporting evidence.",)
                + _verification_limitations(top_results),
            )

        return FindingDecision(
            status=RootCauseStatus.INCONCLUSIVE,
            confidence=CausalConfidence.NONE,
            classification=signal.classification,
            alternative_candidate_ids=tuple(item.id for item in viable),
            rejected_candidate_ids=rejected,
            contradictory_evidence_ids=contradiction_ids,
            verification_result_ids=tuple(item.id for item in top_results),
            summary=f"Root cause unresolved: {signal.summary}",
            explanation="The available evidence does not justify selecting a causal candidate.",
            limitations=("Additional deterministic evidence is required.",),
        )

    def _multifactorial_candidates(
        self,
        candidates: Sequence[CausalCandidate],
        assessments: Mapping[str, CandidateAssessment],
    ) -> tuple[CausalCandidate, ...]:
        supported = [
            item
            for item in candidates
            if item.status is CandidateStatus.SUPPORTED
            and assessments[item.id].supporting_evidence_ids
        ]
        if len(supported) < 2:
            return ()
        top_score = assessments[supported[0].id].total_score
        return tuple(
            item
            for item in supported
            if top_score - assessments[item.id].total_score <= self.multifactorial_margin
        )


@dataclass(frozen=True, slots=True)
class RootCauseEngineResult:
    """Canonical report plus detailed, non-scientific execution trace."""

    report: RootCauseReport
    stages: tuple[StageRecord, ...]
    evidence_collection: EvidenceCollection
    signal_extraction: SignalExtraction
    candidate_generation: CandidateGeneration
    candidate_ranking: CandidateRanking
    verification_execution: VerificationExecution
    attribution_results: Mapping[str, AttributionResult]
    reproduction_builds: Mapping[str, ReproductionBuild]
    schema_version: int = _SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.report, RootCauseReport):
            raise TypeError("report must be a RootCauseReport.")
        stages = _typed_tuple(self.stages, StageRecord, "stages")
        actual_stage_order = tuple(item.stage for item in stages)
        expected_stage_order = tuple(EngineStage)
        if actual_stage_order != expected_stage_order:
            raise ValueError(
                "stages must contain every engine stage exactly once in canonical order: "
                + ", ".join(stage.value for stage in expected_stage_order)
                + "."
            )
        object.__setattr__(self, "stages", stages)
        for name, expected in (
            ("evidence_collection", EvidenceCollection),
            ("signal_extraction", SignalExtraction),
            ("candidate_generation", CandidateGeneration),
            ("candidate_ranking", CandidateRanking),
            ("verification_execution", VerificationExecution),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f"{name} must be a {expected.__name__}.")
        object.__setattr__(
            self,
            "attribution_results",
            _typed_mapping(self.attribution_results, AttributionResult, "attribution_results"),
        )
        object.__setattr__(
            self,
            "reproduction_builds",
            _typed_mapping(self.reproduction_builds, ReproductionBuild, "reproduction_builds"),
        )
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an integer.")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.report.request_id != self.evidence_collection.request_id:
            raise ValueError("report and evidence_collection must belong to the same request.")
        if self.report.request_id != self.signal_extraction.request_id:
            raise ValueError("report and signal_extraction must belong to the same request.")
        report_candidate_ids = {item.id for item in self.report.candidates}
        if set(self.attribution_results) != report_candidate_ids:
            raise ValueError(
                "attribution_results must contain exactly one entry for every report candidate."
            )
        inconsistent_attribution_ids = {
            key: value.metadata.get("candidate_id")
            for key, value in self.attribution_results.items()
            if value.metadata.get("candidate_id") is not None
            and value.metadata.get("candidate_id") != key
        }
        if inconsistent_attribution_ids:
            raise ValueError(
                "attribution_results keys must match metadata candidate_id values when present: "
                f"{inconsistent_attribution_ids!r}."
            )
        report_signal_ids = {item.id for item in self.report.signals}
        if not set(self.reproduction_builds).issubset(report_signal_ids):
            raise ValueError("reproduction_builds may only be keyed by report signal ids.")


class RootCauseEngine:
    """Coordinate one complete, deterministic Phase 3 investigation."""

    def __init__(self, services: EngineServices | None = None) -> None:
        self._services = services or EngineServices()

    def run(self, request: RootCauseRequest, inputs: EngineInputs) -> RootCauseEngineResult:
        if not isinstance(request, RootCauseRequest):
            raise TypeError("request must be a RootCauseRequest.")
        if not isinstance(inputs, EngineInputs):
            raise TypeError("inputs must be EngineInputs.")
        services = self._services
        stages: list[StageRecord] = []

        registry = services.evidence_registry
        if registry is None and services.evidence_adapters:
            registry = EvidenceRegistry(services.evidence_adapters)

        evidence_collection = self._stage(
            stages,
            EngineStage.EVIDENCE_COLLECTION,
            len(inputs.evidence_sources),
            lambda: collect_evidence(
                request,
                inputs.evidence_sources,
                artifacts=inputs.artifacts,
                registry=registry,
                artifact_verifier=services.artifact_verifier,
                collected_at=self._now(),
                strict=request.strict_integrity,
                metadata={"engine_schema_version": _SCHEMA_VERSION},
            ),
            lambda result: len(result.evidence),
        )

        signal_extraction = self._stage(
            stages,
            EngineStage.SIGNAL_EXTRACTION,
            len(evidence_collection.evidence),
            lambda: extract_signals(
                request,
                evidence_collection,
                rules=services.signal_rules or None,
                strict=request.strict_integrity,
                metadata={"evidence_collection_schema_version": evidence_collection.schema_version},
            ),
            lambda result: len(result.signals),
        )
        if not signal_extraction.signals:
            return self._not_applicable_result(
                request=request,
                inputs=inputs,
                stages=stages,
                evidence_collection=evidence_collection,
                signal_extraction=signal_extraction,
            )   
        candidate_generation = self._stage(
            stages,
            EngineStage.CANDIDATE_GENERATION,
            len(signal_extraction.signals),
            lambda: generate_candidates(
                request,
                signal_extraction,
                evidence=evidence_collection.evidence,
                knowledge_registry=inputs.knowledge_registry,
                knowledge_entries=inputs.knowledge_entries or None,
                investigations=inputs.investigations or None,
                protocol_catalog=inputs.protocol_catalog,
                protocols=inputs.protocols or None,
                rules=services.candidate_rules or None,
                strict=request.strict_integrity,
                metadata={"signal_count": len(signal_extraction.signals)},
            ),
            lambda result: len(result.candidates),
        )

        ranking_kwargs: dict[str, Any] = {}
        if services.ranking_criteria is not None:
            ranking_kwargs["criteria"] = services.ranking_criteria
        candidate_ranking = self._stage(
            stages,
            EngineStage.CANDIDATE_RANKING,
            len(candidate_generation.candidates),
            lambda: rank_candidates(
                request,
                candidate_generation,
                signals=signal_extraction.signals,
                evidence=evidence_collection.evidence,
                knowledge_entries=inputs.knowledge_entries,
                strict=request.strict_integrity,
                metadata={"candidate_source_counts": candidate_generation.source_counts},
                **ranking_kwargs,
            ),
            lambda result: len(result.assessments),
        )

        verification_context = VerificationStageContext(
            request=request,
            candidates=candidate_ranking.candidates,
            assessments=candidate_ranking.assessments,
            evidence=evidence_collection.evidence,
            artifacts=evidence_collection.artifacts,
            strict=request.strict_integrity,
            failure_policy=services.verification_failure_policy,
            metadata={"ranking_criterion_ids": candidate_ranking.criterion_ids},
        )
        verification_execution = self._stage(
            stages,
            EngineStage.VERIFICATION,
            len(candidate_ranking.candidates),
            lambda: execute_verifications(
                verification_context,
                plan_sources=services.verification_plan_sources,
                verifiers=services.verifiers,
                clock=self._now,
            ),
            lambda result: len(result.results),
        )

        all_evidence = _merge_evidence(
            evidence_collection.evidence, verification_execution.evidence
        )
        all_artifacts = _merge_artifacts(
            evidence_collection.artifacts, verification_execution.output_artifacts
        )
        assessments_by_id = {
            item.candidate_id: item for item in candidate_ranking.assessments
        }

        attribution_results: dict[str, AttributionResult] = {}
        attribution_started = self._now()
        for candidate in verification_execution.candidates:
            assessment = assessments_by_id[candidate.id]
            attribution_results[candidate.id] = attribute_source(
                candidate=candidate,
                assessment=assessment,
                evidence=all_evidence,
                verifications=tuple(
                    item
                    for item in verification_execution.results
                    if item.candidate_id == candidate.id
                ),
                rules=services.attribution_rules or None,
                strict=request.strict_integrity,
                metadata={"request_id": request.id},
            )
        attribution_finished = self._now()
        stages.append(
            StageRecord(
                stage=EngineStage.ATTRIBUTION,
                started_at=attribution_started,
                finished_at=attribution_finished,
                input_count=len(verification_execution.candidates),
                output_count=len(attribution_results),
            )
        )

        finding_policy = services.finding_policy or ConservativeFindingPolicy()
        findings_started = self._now()
        decisions: list[tuple[DiscrepancySignal, FindingDecision]] = []
        for signal in signal_extraction.signals:
            signal_candidates = tuple(
                item
                for item in verification_execution.candidates
                if signal.id in item.signal_ids
            )
            signal_candidate_ids = {item.id for item in signal_candidates}
            signal_assessments = tuple(
                item
                for item in candidate_ranking.assessments
                if item.candidate_id in signal_candidate_ids
            )
            signal_verifications = tuple(
                item
                for item in verification_execution.results
                if item.candidate_id in signal_candidate_ids
            )
            try:
                decision = finding_policy.decide(
                    signal=signal,
                    candidates=signal_candidates,
                    assessments=signal_assessments,
                    evidence=all_evidence,
                    verifications=signal_verifications,
                    attributions={
                        candidate_id: result.attribution
                        for candidate_id, result in attribution_results.items()
                        if candidate_id in signal_candidate_ids
                    },
                )
            except RootCauseError:
                raise
            except Exception as exc:
                raise RootCauseIntegrityError(
                    "Finding policy failed unexpectedly.",
                    context={
                        "request_id": request.id,
                        "signal_id": signal.id,
                        "policy_type": type(finding_policy).__name__,
                    },
                ) from exc
            _validate_finding_decision(
                decision,
                signal=signal,
                candidate_ids=signal_candidate_ids,
                evidence_ids={item.id for item in all_evidence},
                verification_by_id={item.id: item for item in signal_verifications},
            )
            decisions.append((signal, decision))
        findings_finished = self._now()
        stages.append(
            StageRecord(
                stage=EngineStage.CLASSIFICATION,
                started_at=findings_started,
                finished_at=findings_finished,
                input_count=len(signal_extraction.signals),
                output_count=len(decisions),
            )
        )

        reproduction_builds: dict[str, ReproductionBuild] = {}
        plans_by_signal: dict[str, ReproductionPlan] = {}
        reproduction_started = self._now()
        artifact_map = {item.id: item for item in all_artifacts}
        if services.reproduction_contributors:
            for signal, decision in decisions:
                if not decision.selected_candidate_ids:
                    continue
                attribution = _finding_attribution(
                    decision.selected_candidate_ids,
                    attribution_results,
                )
                selected_results = tuple(
                    item
                    for item in verification_execution.results
                    if item.candidate_id in set(decision.selected_candidate_ids)
                )
                build = build_reproduction_plan(
                    ReproductionContext(
                        request=request,
                        artifacts=artifact_map,
                        verification_results=selected_results,
                        attribution=attribution,
                        title=f"Reproduce discrepancy {signal.id}",
                        objective=decision.summary,
                        strict_integrity=request.strict_integrity,
                        metadata={"signal_id": signal.id, "candidate_ids": decision.selected_candidate_ids},
                    ),
                    services.reproduction_contributors,
                )
                reproduction_builds[signal.id] = build
                plans_by_signal[signal.id] = build.plan
        reproduction_finished = self._now()
        stages.append(
            StageRecord(
                stage=EngineStage.REPRODUCTION,
                started_at=reproduction_started,
                finished_at=reproduction_finished,
                input_count=sum(bool(decision.selected_candidate_ids) for _, decision in decisions),
                output_count=len(plans_by_signal),
            )
        )

        findings = tuple(
            self._finding(
                request=request,
                signal=signal,
                decision=decision,
                attribution_results=attribution_results,
                reproduction_plan=plans_by_signal.get(signal.id),
            )
            for signal, decision in decisions
        )

        report_started = self._now()
        report_status, report_confidence = _aggregate_report_conclusion(findings)
        report = RootCauseReport(
            id=_stable_id(
                "root-cause-report",
                {
                    "request_id": request.id,
                    "signal_ids": [item.id for item in signal_extraction.signals],
                    "finding_ids": [item.id for item in findings],
                },
            ),
            request_id=request.id,
            experiment_id=request.experiment_id,
            run_id=request.run_id,
            status=report_status,
            confidence=report_confidence,
            generated_at=report_started,
            signals=signal_extraction.signals,
            evidence=all_evidence,
            candidates=verification_execution.candidates,
            assessments=candidate_ranking.assessments,
            verifications=verification_execution.results,
            findings=findings,
            reproduction_plans=tuple(sorted(plans_by_signal.values(), key=lambda item: item.id)),
            artifacts=all_artifacts,
            executive_summary=_executive_summary(findings),
            unresolved_questions=_unresolved_questions(findings),
            limitations=_aggregate_limitations(
                findings,
                evidence_collection,
                signal_extraction,
                candidate_generation,
                candidate_ranking,
                verification_execution,
            ),
            metadata={
                "schema_version": _SCHEMA_VERSION,
                "stage_order": tuple(stage.value for stage in EngineStage),
                "input_metadata": inputs.metadata,
            },
        )
        report_finished = self._now()
        stages.append(
            StageRecord(
                stage=EngineStage.REPORT_ASSEMBLY,
                started_at=report_started,
                finished_at=report_finished,
                input_count=len(findings),
                output_count=1,
            )
        )

        return RootCauseEngineResult(
            report=report,
            stages=tuple(stages),
            evidence_collection=evidence_collection,
            signal_extraction=signal_extraction,
            candidate_generation=candidate_generation,
            candidate_ranking=candidate_ranking,
            verification_execution=verification_execution,
            attribution_results=attribution_results,
            reproduction_builds=reproduction_builds,
            metadata={"request_id": request.id},
        )

    def _now(self) -> datetime:
        return _aware_datetime(self._services.clock(), "clock()")

    def _stage(
        self,
        records: list[StageRecord],
        stage: EngineStage,
        input_count: int,
        operation: Callable[[], Any],
        output_counter: Callable[[Any], int],
    ) -> Any:
        started = self._now()
        result = operation()
        finished = self._now()
        output_count = output_counter(result)
        records.append(
            StageRecord(
                stage=stage,
                started_at=started,
                finished_at=finished,
                input_count=input_count,
                output_count=output_count,
            )
        )
        return result

    @staticmethod
    def _finding(
        *,
        request: RootCauseRequest,
        signal: DiscrepancySignal,
        decision: FindingDecision,
        attribution_results: Mapping[str, AttributionResult],
        reproduction_plan: ReproductionPlan | None,
    ) -> RootCauseFinding:
        attribution = _finding_attribution(
            decision.selected_candidate_ids,
            attribution_results,
        )
        if decision.status is RootCauseStatus.CONFIRMED and attribution.level is AttributionLevel.UNKNOWN:
            raise RootCauseIntegrityError(
                "A confirmed decision cannot be assembled without concrete attribution.",
                context={"signal_id": signal.id},
            )
        payload = {
            "request_id": request.id,
            "signal_id": signal.id,
            "status": decision.status.value,
            "candidate_ids": decision.selected_candidate_ids,
        }
        return RootCauseFinding(
            id=_stable_id("root-cause-finding", payload),
            status=decision.status,
            confidence=decision.confidence,
            classification=decision.classification,
            domain=signal.domain,
            summary=decision.summary,
            explanation=decision.explanation,
            signal_ids=(signal.id,),
            selected_candidate_ids=decision.selected_candidate_ids,
            alternative_candidate_ids=decision.alternative_candidate_ids,
            rejected_candidate_ids=decision.rejected_candidate_ids,
            supporting_evidence_ids=decision.supporting_evidence_ids,
            contradictory_evidence_ids=decision.contradictory_evidence_ids,
            verification_result_ids=decision.verification_result_ids,
            attribution=attribution,
            reproduction_plan_id=reproduction_plan.id if reproduction_plan else None,
            limitations=decision.limitations,
            metadata={"policy": "injected", "request_id": request.id},
        )


def _validate_finding_decision(
    decision: FindingDecision,
    *,
    signal: DiscrepancySignal,
    candidate_ids: set[str],
    evidence_ids: set[str],
    verification_by_id: Mapping[str, VerificationResult],
) -> None:
    if not isinstance(decision, FindingDecision):
        raise RootCauseIntegrityError(
            "Finding policy must return FindingDecision.",
            context={"signal_id": signal.id, "returned_type": type(decision).__name__},
        )
    referenced_candidates = set(decision.selected_candidate_ids) | set(
        decision.alternative_candidate_ids
    ) | set(decision.rejected_candidate_ids)
    unknown_candidates = referenced_candidates - candidate_ids
    if unknown_candidates:
        raise RootCauseIntegrityError(
            "Finding policy referenced candidates outside the current signal.",
            context={"signal_id": signal.id, "candidate_ids": tuple(sorted(unknown_candidates))},
        )
    referenced_evidence = set(decision.supporting_evidence_ids) | set(
        decision.contradictory_evidence_ids
    )
    unknown_evidence = referenced_evidence - evidence_ids
    if unknown_evidence:
        raise RootCauseIntegrityError(
            "Finding policy referenced unknown evidence.",
            context={"signal_id": signal.id, "evidence_ids": tuple(sorted(unknown_evidence))},
        )
    unknown_verifications = set(decision.verification_result_ids) - set(verification_by_id)
    if unknown_verifications:
        raise RootCauseIntegrityError(
            "Finding policy referenced unknown verification results.",
            context={
                "signal_id": signal.id,
                "verification_result_ids": tuple(sorted(unknown_verifications)),
            },
        )
    if any(
        verification_by_id[result_id].candidate_id not in referenced_candidates
        for result_id in decision.verification_result_ids
    ):
        raise RootCauseIntegrityError(
            "Finding policy referenced a verification unrelated to its candidate set.",
            context={"signal_id": signal.id},
        )
    if decision.status is RootCauseStatus.CONFIRMED:
        passed_for_selected = {
            verification_by_id[result_id].candidate_id
            for result_id in decision.verification_result_ids
            if verification_by_id[result_id].outcome is VerificationOutcome.PASSED
        }
        if not passed_for_selected.intersection(decision.selected_candidate_ids):
            raise RootCauseIntegrityError(
                "A confirmed decision requires a PASSED verification for its selected candidate.",
                context={"signal_id": signal.id},
            )


def _finding_attribution(
    selected_candidate_ids: Sequence[str],
    attribution_results: Mapping[str, AttributionResult],
) -> SourceAttribution:
    if not selected_candidate_ids:
        return SourceAttribution(level=AttributionLevel.UNKNOWN)
    attributions = tuple(
        attribution_results[candidate_id].attribution for candidate_id in selected_candidate_ids
    )
    first = attributions[0]
    if all(item == first for item in attributions[1:]):
        return first
    return SourceAttribution(
        level=AttributionLevel.UNKNOWN,
        rationale=(
            "Selected candidates do not share a single evidence-backed source location; "
            "the finding therefore retains an unknown aggregate attribution."
        ),
    )


def run_root_cause_analysis(
    request: RootCauseRequest,
    inputs: EngineInputs,
    *,
    services: EngineServices | None = None,
) -> RootCauseEngineResult:
    """Functional entry point for one complete Phase 3 investigation."""

    return RootCauseEngine(services).run(request, inputs)


def _supporting_ids(
    candidate_id: str,
    assessment: CandidateAssessment,
    evidence: Sequence[EvidenceReference],
    results: Sequence[VerificationResult],
) -> tuple[str, ...]:
    directional = tuple(
        item.id
        for item in evidence
        if item.related_candidate_id == candidate_id and item.direction.value == "supports"
    )
    verified = tuple(
        evidence_id
        for result in results
        if result.outcome is VerificationOutcome.PASSED
        for evidence_id in result.evidence_ids
    )
    return _ordered_union(assessment.supporting_evidence_ids, directional, verified)


def _contradictory_ids(
    candidate_id: str,
    assessment: CandidateAssessment,
    evidence: Sequence[EvidenceReference],
    results: Sequence[VerificationResult],
) -> tuple[str, ...]:
    directional = tuple(
        item.id
        for item in evidence
        if item.related_candidate_id == candidate_id and item.direction.value == "contradicts"
    )
    verified = tuple(
        evidence_id
        for result in results
        if result.outcome is VerificationOutcome.FAILED
        for evidence_id in result.evidence_ids
    )
    return _ordered_union(assessment.contradictory_evidence_ids, directional, verified)


def _semantic_status(classification: DifferenceClassification) -> RootCauseStatus | None:
    return {
        DifferenceClassification.EXPECTED_ADAPTATION: RootCauseStatus.EXPECTED_DIFFERENCE,
        DifferenceClassification.IMPLEMENTATION_LIMITATION: RootCauseStatus.IMPLEMENTATION_LIMITATION,
    }.get(classification)


def _verification_limitations(results: Sequence[VerificationResult]) -> tuple[str, ...]:
    limitations: list[str] = []
    if not results:
        limitations.append("No deterministic verification was available.")
    if any(item.outcome is VerificationOutcome.ERROR for item in results):
        limitations.append("At least one verifier ended in a technical error.")
    if any(item.outcome is VerificationOutcome.INCONCLUSIVE for item in results):
        limitations.append("At least one verifier was scientifically inconclusive.")
    if any(item.outcome is VerificationOutcome.NOT_RUN for item in results):
        limitations.append("At least one planned verification was not executed.")
    return tuple(limitations)


def _aggregate_report_conclusion(
    findings: Sequence[RootCauseFinding],
) -> tuple[RootCauseStatus, CausalConfidence]:
    """Aggregate independent findings without inventing multifactoriality.

    ``MULTIFACTORIAL`` is a property of a single discrepancy explained by
    multiple mechanisms.  Heterogeneous statuses across independent signals are
    therefore conservatively reported as ``INCONCLUSIVE`` rather than collapsed
    into a false multifactorial conclusion.
    """

    if not findings:
        raise RootCauseIntegrityError("Cannot aggregate an empty finding collection.")
    statuses = {item.status for item in findings}
    if len(statuses) == 1:
        status = findings[0].status
        confidence = min((item.confidence for item in findings), key=_confidence_rank)
        return status, confidence
    return RootCauseStatus.INCONCLUSIVE, CausalConfidence.NONE

def _confidence_rank(value: CausalConfidence) -> int:
    return {
        CausalConfidence.NONE: 0,
        CausalConfidence.LOW: 1,
        CausalConfidence.MODERATE: 2,
        CausalConfidence.HIGH: 3,
        CausalConfidence.VERY_HIGH: 4,
    }[value]


def _executive_summary(findings: Sequence[RootCauseFinding]) -> str:
    counts: dict[RootCauseStatus, int] = defaultdict(int)
    for finding in findings:
        counts[finding.status] += 1
    parts = [
        f"{count} {status.value.replace('_', ' ')}"
        for status, count in sorted(counts.items(), key=lambda item: item[0].value)
    ]
    return "Root-cause analysis completed: " + ", ".join(parts) + "."


def _unresolved_questions(findings: Sequence[RootCauseFinding]) -> tuple[str, ...]:
    return tuple(
        f"What additional deterministic evidence can resolve signal {finding.signal_ids[0]}?"
        for finding in findings
        if finding.status in {RootCauseStatus.INCONCLUSIVE, RootCauseStatus.PLAUSIBLE}
    )


def _aggregate_limitations(
    findings: Sequence[RootCauseFinding],
    evidence: EvidenceCollection,
    signals: SignalExtraction,
    candidates: CandidateGeneration,
    ranking: CandidateRanking,
    verification: VerificationExecution,
) -> tuple[str, ...]:
    values = [item for finding in findings for item in finding.limitations]
    values.extend(item.message for item in evidence.diagnostics)
    values.extend(item.message for item in signals.diagnostics)
    values.extend(item.message for item in candidates.diagnostics)
    values.extend(item.message for item in ranking.diagnostics)
    values.extend(item.message for item in verification.diagnostics)
    return _ordered_union(values)


def _merge_evidence(
    first: Sequence[EvidenceReference], second: Sequence[EvidenceReference]
) -> tuple[EvidenceReference, ...]:
    by_id: dict[str, EvidenceReference] = {}
    for item in (*first, *second):
        existing = by_id.get(item.id)
        if existing is not None and existing != item:
            raise RootCauseIntegrityError(
                "Evidence identifiers collide with different content.",
                context={"evidence_id": item.id},
            )
        by_id[item.id] = item
    return tuple(sorted(by_id.values(), key=lambda item: item.id))


def _merge_artifacts(
    first: Sequence[ArtifactReference], second: Sequence[ArtifactReference]
) -> tuple[ArtifactReference, ...]:
    by_id: dict[str, ArtifactReference] = {}
    for item in (*first, *second):
        existing = by_id.get(item.id)
        if existing is not None and existing != item:
            raise RootCauseIntegrityError(
                "Artifact identifiers collide with different content.",
                context={"artifact_id": item.id},
            )
        by_id[item.id] = item
    return tuple(sorted(by_id.values(), key=lambda item: item.id))


def _ordered_union(*groups: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for group in groups:
        for value in group:
            if value not in seen:
                seen.add(value)
                output.append(value)
    return tuple(output)


def _stable_id(namespace: str, payload: Mapping[str, Any]) -> str:
    digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]
    return f"{namespace}:{digest}"


def _canonical_json(value: Any) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_canonical(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        )
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return value


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} cannot be empty.")
    return value


def _identifier(value: str, field_name: str) -> str:
    value = _text(value, field_name)
    if any(character.isspace() for character in value):
        raise ValueError(f"{field_name} cannot contain whitespace.")
    return value


def _tuple(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence.")
    return tuple(value)


def _typed_tuple(value: Any, expected: type[Any], field_name: str) -> tuple[Any, ...]:
    values = _tuple(value, field_name)
    for index, item in enumerate(values):
        if not isinstance(item, expected):
            raise TypeError(f"{field_name}[{index}] must be a {expected.__name__}.")
    return values


def _identifier_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    values = tuple(_identifier(item, f"{field_name}[{index}]") for index, item in enumerate(_tuple(value, field_name)))
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} cannot contain duplicates.")
    return values


def _text_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    values = tuple(_text(item, f"{field_name}[{index}]") for index, item in enumerate(_tuple(value, field_name)))
    return _ordered_union(values)


def _unique_ids(values: Sequence[Any], field_name: str) -> None:
    ids = [item.id for item in values]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{field_name} contains duplicate identifiers.")


def _typed_mapping(value: Mapping[str, Any], expected: type[Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    output: dict[str, Any] = {}
    for key, item in value.items():
        key = _identifier(key, f"{field_name} key")
        if not isinstance(item, expected):
            raise TypeError(f"{field_name}[{key!r}] must be a {expected.__name__}.")
        output[key] = item
    return MappingProxyType(dict(sorted(output.items())))


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return MappingProxyType({
        _text(str(key), f"{field_name} key"): _freeze(item)
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
    })


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))