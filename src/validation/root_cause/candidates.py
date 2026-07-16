"""Deterministic generation of causal candidates for Phase 3.

This module transforms typed discrepancy signals into immutable, testable
:class:`~validation.root_cause.models.CausalCandidate` objects.  Candidate
sources are deliberately plural and independently injectable:

* deterministic rules derived from the observed difference classification;
* validated entries from the Scientific Knowledge Engine;
* prior investigation hypotheses explicitly supplied to the request;
* applicable investigation protocols.

Scientific boundary
-------------------
Candidate generation proposes explanations; it does not assess, rank, verify,
select or confirm them.  Every emitted candidate therefore starts in
``CandidateStatus.GENERATED`` and must include explicit expected observations
and falsification criteria whenever its source provides them.

A statistical association, a domain match or a prior knowledge match is never
promoted to a causal conclusion here.  Zero generated candidates is a valid,
auditable scientific result.  Exceptions are reserved for malformed inputs,
broken source contracts or inconsistent candidate graphs.

Design guarantees
-----------------

* Candidate identifiers are content-addressed and independent of input order.
* Every candidate retains the signals and source objects that generated it.
* Knowledge matching is constraint-based, never fuzzy or probabilistic.
* Deprecated, draft or superseded knowledge is excluded by default.
* Protocol applicability is evaluated by canonical validation-domain identity.
* Extension failures are normalized at the component boundary.
* Strict and permissive execution modes are explicit and auditable.
* Duplicate identifiers are accepted only for equivalent candidates.
* No candidate is silently converted into a supported or refuted hypothesis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from json import dumps
from math import isfinite
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable

from validation.knowledge.models import (
    CausalHypothesis,
    HypothesisStatus,
    InvestigationCase,
    KnowledgeEntry,
    KnowledgeEntryStatus,
)
from validation.knowledge.protocols import (
    CANONICAL_PROTOCOLS,
    EvidenceRequirementLevel,
    InvestigationProtocol,
    ProtocolCatalog,
)
from validation.knowledge.registry import KnowledgeRegistry, UnknownInvestigationError
from validation.knowledge.taxonomy import RootCauseCategory, ValidationDomain
from validation.root_cause.exceptions import (
    CandidateGenerationError,
    RootCauseInputError,
    RootCauseIntegrityError,
)
from validation.root_cause.models import (
    CandidateStatus,
    CausalCandidate,
    DifferenceClassification,
    DiscrepancySignal,
    EvidenceReference,
    RootCauseRequest,
)
from validation.root_cause.signals import SignalExtraction

__all__ = [
    "CandidateDiagnostic",
    "CandidateGeneration",
    "CandidateGenerationContext",
    "CandidateGenerationSeverity",
    "CandidateGenerator",
    "CandidateRule",
    "ClassificationCandidateRule",
    "InvestigationHypothesisSource",
    "KnowledgeEntrySource",
    "ProtocolCandidateSource",
    "generate_candidates",
]


# =============================================================================
# Public contracts
# =============================================================================


class CandidateGenerationSeverity(str, Enum):
    """Severity of a non-fatal candidate-generation diagnostic."""

    INFO = "info"
    WARNING = "warning"


_IDENTIFIER_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_CANDIDATE_PREFIX: Final = "candidate"
_SCHEMA_VERSION: Final[int] = 1


@dataclass(frozen=True, slots=True)
class CandidateDiagnostic:
    """Auditable event emitted when permissive generation skips one source."""

    code: str
    message: str
    severity: CandidateGenerationSeverity = CandidateGenerationSeverity.WARNING
    signal_id: str | None = None
    source_name: str | None = None
    source_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_identifier(self.code, "code"))
        object.__setattr__(self, "message", _require_text(self.message, "message"))
        if not isinstance(self.severity, CandidateGenerationSeverity):
            raise TypeError("severity must be a CandidateGenerationSeverity member.")
        object.__setattr__(
            self, "signal_id", _optional_identifier(self.signal_id, "signal_id")
        )
        object.__setattr__(
            self, "source_name", _optional_identifier(self.source_name, "source_name")
        )
        object.__setattr__(
            self, "source_id", _optional_identifier(self.source_id, "source_id")
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class CandidateGenerationContext:
    """Immutable inputs shared by all candidate sources for one investigation."""

    request: RootCauseRequest
    signals: tuple[DiscrepancySignal, ...]
    evidence: tuple[EvidenceReference, ...] = ()
    knowledge_entries: tuple[KnowledgeEntry, ...] = ()
    investigations: tuple[InvestigationCase, ...] = ()
    protocols: tuple[InvestigationProtocol, ...] = ()
    strict: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, RootCauseRequest):
            raise TypeError("request must be a RootCauseRequest.")

        signals = _normalize_models(self.signals, DiscrepancySignal, "signals")
        evidence = _normalize_models(self.evidence, EvidenceReference, "evidence")
        entries = _normalize_models(
            self.knowledge_entries, KnowledgeEntry, "knowledge_entries"
        )
        investigations = _normalize_models(
            self.investigations, InvestigationCase, "investigations"
        )
        protocols = _normalize_models(
            self.protocols, InvestigationProtocol, "protocols"
        )

        _require_unique_ids(signals, "signals")
        _require_unique_ids(evidence, "evidence")
        _require_unique_ids(entries, "knowledge_entries")
        _require_unique_ids(investigations, "investigations")
        _require_unique_protocol_ids(protocols)

        object.__setattr__(self, "signals", tuple(sorted(signals, key=lambda item: item.id)))
        object.__setattr__(
            self, "evidence", tuple(sorted(evidence, key=lambda item: item.id))
        )
        object.__setattr__(
            self,
            "knowledge_entries",
            tuple(sorted(entries, key=lambda item: item.id)),
        )
        object.__setattr__(
            self,
            "investigations",
            tuple(sorted(investigations, key=lambda item: item.id)),
        )
        object.__setattr__(
            self,
            "protocols",
            tuple(sorted(protocols, key=lambda item: item.qualified_id)),
        )

        if self.strict is not None and not isinstance(self.strict, bool):
            raise TypeError("strict must be bool or None.")
        object.__setattr__(
            self,
            "strict",
            self.request.strict_integrity if self.strict is None else self.strict,
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        _validate_context_scope(self)

    @property
    def signal_catalog(self) -> Mapping[str, DiscrepancySignal]:
        return MappingProxyType({item.id: item for item in self.signals})

    @property
    def evidence_catalog(self) -> Mapping[str, EvidenceReference]:
        return MappingProxyType({item.id: item for item in self.evidence})

    @property
    def knowledge_catalog(self) -> Mapping[str, KnowledgeEntry]:
        return MappingProxyType({item.id: item for item in self.knowledge_entries})

    @property
    def investigation_catalog(self) -> Mapping[str, InvestigationCase]:
        return MappingProxyType({item.id: item for item in self.investigations})

    @property
    def protocol_catalog(self) -> Mapping[str, InvestigationProtocol]:
        return MappingProxyType({item.qualified_id: item for item in self.protocols})


@dataclass(frozen=True, slots=True)
class CandidateGeneration:
    """Complete deterministic output of the candidate-generation stage."""

    request_id: str
    candidates: tuple[CausalCandidate, ...]
    diagnostics: tuple[CandidateDiagnostic, ...] = ()
    source_counts: Mapping[str, int] = field(default_factory=dict)
    unhandled_signal_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _require_identifier(self.request_id, "request_id")
        )
        candidates = _normalize_models(self.candidates, CausalCandidate, "candidates")
        diagnostics = _normalize_models(
            self.diagnostics, CandidateDiagnostic, "diagnostics"
        )
        _require_unique_ids(candidates, "candidates")
        object.__setattr__(
            self, "candidates", tuple(sorted(candidates, key=lambda item: item.id))
        )
        object.__setattr__(
            self,
            "diagnostics",
            tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.code,
                        item.signal_id or "",
                        item.source_name or "",
                        item.source_id or "",
                    ),
                )
            ),
        )
        object.__setattr__(
            self,
            "source_counts",
            _normalize_count_mapping(self.source_counts, "source_counts"),
        )
        object.__setattr__(
            self,
            "unhandled_signal_ids",
            _normalize_identifier_tuple(
                self.unhandled_signal_ids, "unhandled_signal_ids"
            ),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        referenced_signal_ids = {
            signal_id for candidate in self.candidates for signal_id in candidate.signal_ids
        }
        overlap = referenced_signal_ids.intersection(self.unhandled_signal_ids)
        if overlap:
            raise ValueError(
                "A signal cannot be both handled and unhandled: "
                + ", ".join(sorted(overlap))
                + "."
            )


@runtime_checkable
class CandidateRule(Protocol):
    """Injectable deterministic source of candidate explanations."""

    @property
    def name(self) -> str:
        """Stable identifier used in provenance and diagnostics."""

    @property
    def priority(self) -> int:
        """Execution priority; larger values run first."""

    def generate(
        self,
        signal: DiscrepancySignal,
        context: CandidateGenerationContext,
    ) -> Sequence[CausalCandidate]:
        """Return zero or more generated candidates for one signal."""


# =============================================================================
# Deterministic rule source
# =============================================================================


@dataclass(frozen=True, slots=True)
class _CategoryTemplate:
    category: RootCauseCategory
    mechanism: str
    expected_observations: tuple[str, ...]
    falsification_criteria: tuple[str, ...]


_CLASSIFICATION_TEMPLATES: Final[Mapping[DifferenceClassification, tuple[_CategoryTemplate, ...]]] = MappingProxyType(
    {
        DifferenceClassification.INPUT: (
            _CategoryTemplate(
                RootCauseCategory.INPUT_DATA,
                "The compared simulators received non-equivalent source populations, module inputs, reference data or preprocessing inputs.",
                (
                    "Input manifests, cohort definitions or source datasets differ before simulation or validation begins.",
                ),
                (
                    "Canonicalized inputs, cohort definitions and hashes are identical across both execution paths.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.DATA_QUALITY,
                "Malformed, incomplete or inconsistent source data altered one execution or validation path.",
                (
                    "Data-quality checks identify missing, duplicated, malformed or internally inconsistent source records.",
                ),
                (
                    "All relevant source inputs pass equivalent integrity and completeness checks.",
                ),
            ),
        ),
        DifferenceClassification.CONFIGURATION: (
            _CategoryTemplate(
                RootCauseCategory.CONFIGURATION,
                "A simulation or validation configuration parameter differs between the compared executions.",
                (
                    "A canonical configuration diff identifies at least one behaviorally relevant parameter mismatch.",
                ),
                (
                    "Configurations are canonically identical or controlled reruns show the mismatch has no effect.",
                ),
            ),
        ),
        DifferenceClassification.STRUCTURAL: (
            _CategoryTemplate(
                RootCauseCategory.MODULE_DEFINITION,
                "The executable module graph, state parameters or transition structure differs between implementations.",
                (
                    "Module graph comparison identifies a state, transition, parameter or reference mismatch.",
                ),
                (
                    "Canonical module representations and executable graphs are equivalent for the affected pathway.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.PARSER_IMPORT,
                "The compatibility parser transformed the source GMF module into a non-equivalent internal representation.",
                (
                    "The imported IR differs from the source GMF semantics at the affected state or transition.",
                ),
                (
                    "Independent import inspection and round-trip checks preserve the relevant module structure and semantics.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.UNSUPPORTED_GMF,
                "The affected module uses a GMF construction that Psynthea does not implement with equivalent semantics.",
                (
                    "The affected path contains an unsupported or deliberately limited state, transition or logic type.",
                ),
                (
                    "Every GMF construction on the affected path is supported and verified against Synthea behavior.",
                ),
            ),
        ),
        DifferenceClassification.SEMANTIC: (
            _CategoryTemplate(
                RootCauseCategory.ENGINE_EXECUTION,
                "Equivalent module instructions are executed differently by the two simulation engines.",
                (
                    "A controlled trace diverges while inputs, module IR and configuration remain equivalent.",
                ),
                (
                    "State-by-state controlled execution produces equivalent state, record and transition outcomes.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.MODULE_DEFINITION,
                "The module encodes behavior whose interpreted clinical meaning differs across the compared implementations.",
                (
                    "The affected module instruction or parameter explains the observed semantic divergence.",
                ),
                (
                    "The module definition is semantically equivalent and controlled execution still reproduces the discrepancy elsewhere.",
                ),
            ),
        ),
        DifferenceClassification.TEMPORAL: (
            _CategoryTemplate(
                RootCauseCategory.TEMPORAL_SEMANTICS,
                "The engines differ in time advancement, delay completion, event dating, age calculation or boundary handling.",
                (
                    "A deterministic trace shows divergent timestamps or temporal state progression under equivalent inputs.",
                ),
                (
                    "Temporal traces, boundary cases and event dates are equivalent for the affected pathway.",
                ),
            ),
        ),
        DifferenceClassification.PROBABILISTIC: (
            _CategoryTemplate(
                RootCauseCategory.PROBABILISTIC_SEMANTICS,
                "The engines differ in random-number consumption, weighted sampling, seed derivation or probabilistic transition semantics.",
                (
                    "Seed-controlled traces diverge at a probabilistic decision or consume random values in a different order.",
                ),
                (
                    "Equivalent seeds and identical random streams produce the same probabilistic decisions and downstream events.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.STATISTICAL_ARTIFACT,
                "The observed discrepancy is compatible with finite-sample variability rather than a stable implementation difference.",
                (
                    "The effect is unstable across seeds, repetitions or larger cohorts and remains within the prespecified uncertainty model.",
                ),
                (
                    "The effect persists reproducibly across independent seeds, repetitions and adequate cohort sizes.",
                ),
            ),
        ),
        DifferenceClassification.CLINICAL_RECORDING: (
            _CategoryTemplate(
                RootCauseCategory.CLINICAL_RECORDING,
                "Equivalent clinical state transitions are recorded differently in the internal longitudinal health record.",
                (
                    "Execution traces agree before record mutation but internal clinical entries differ in creation, closure or linkage.",
                ),
                (
                    "Internal record entries and encounter associations are equivalent before export.",
                ),
            ),
        ),
        DifferenceClassification.TERMINOLOGY: (
            _CategoryTemplate(
                RootCauseCategory.TERMINOLOGY_MAPPING,
                "Clinical concepts are mapped, normalized or compared using non-equivalent terminology identifiers or coding rules.",
                (
                    "The affected concepts resolve to different canonical codes, systems, versions or equivalence mappings.",
                ),
                (
                    "Terminology normalization produces identical canonical concepts before metric computation.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.VALIDATION_HARMONIZATION,
                "The validation harmonization layer converts equivalent source values into non-equivalent comparison values.",
                (
                    "The discrepancy appears after harmonization despite equivalent raw simulator outputs.",
                ),
                (
                    "Raw-to-canonical transformations are identical and preserve the affected concepts.",
                ),
            ),
        ),
        DifferenceClassification.EXPORT_ONLY: (
            _CategoryTemplate(
                RootCauseCategory.EXPORT,
                "The internal simulations are equivalent but exporter serialization, field mapping or output filtering differs.",
                (
                    "Internal records agree while exported resources or tabular outputs diverge.",
                ),
                (
                    "Canonicalized exports are equivalent or the discrepancy is already present in internal records.",
                ),
            ),
        ),
        DifferenceClassification.VALIDATION_PIPELINE: (
            _CategoryTemplate(
                RootCauseCategory.VALIDATION_INGESTION,
                "The validation loader ingests one simulator output incorrectly or incompletely.",
                (
                    "The discrepancy first appears between raw output and the loaded validation representation.",
                ),
                (
                    "Loaded representations preserve all relevant raw records and values from both simulators.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.VALIDATION_HARMONIZATION,
                "Normalization or harmonization introduces the observed discrepancy.",
                (
                    "Raw loaded data are equivalent but canonicalized data diverge.",
                ),
                (
                    "Harmonization applies equivalent transformations and preserves the affected values.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.VALIDATION_METRIC,
                "The metric implementation computes non-equivalent values from equivalent canonical inputs.",
                (
                    "Independent recomputation disagrees with the framework metric for the affected domain.",
                ),
                (
                    "Independent and framework computations agree on the same canonical inputs.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.VALIDATION_STATISTICS,
                "The statistical method, assumptions or implementation produce a misleading discrepancy classification.",
                (
                    "Alternative validated analysis or assumption checks change the statistical conclusion.",
                ),
                (
                    "Statistical assumptions hold and independent implementation reproduces the same conclusion.",
                ),
            ),
            _CategoryTemplate(
                RootCauseCategory.VALIDATION_INTERPRETATION,
                "Interpretation logic converts valid statistical results into an incorrect scientific conclusion.",
                (
                    "The statistical result is correct but the generated interpretation violates the declared decision rules.",
                ),
                (
                    "Interpretation output follows the configured scientific rules for the same result.",
                ),
            ),
        ),
        DifferenceClassification.EXECUTION_ENVIRONMENT: (
            _CategoryTemplate(
                RootCauseCategory.EXECUTION_ENVIRONMENT,
                "Runtime, dependency, locale, platform or resource differences changed execution behavior.",
                (
                    "The discrepancy co-varies with a documented environment difference and disappears in a controlled environment.",
                ),
                (
                    "Equivalent environments reproduce the discrepancy unchanged.",
                ),
            ),
        ),
        DifferenceClassification.STATISTICAL_ARTIFACT: (
            _CategoryTemplate(
                RootCauseCategory.STATISTICAL_ARTIFACT,
                "The discrepancy is explained by sampling variability, multiplicity, low power or an unstable estimator.",
                (
                    "Sensitivity analyses, repeated cohorts or uncertainty estimates show the effect is not stable.",
                ),
                (
                    "The effect remains stable, clinically relevant and reproducible under adequate statistical controls.",
                ),
            ),
        ),
        DifferenceClassification.EXPECTED_ADAPTATION: (
            _CategoryTemplate(
                RootCauseCategory.WORKFLOW_ADAPTATION,
                "A deliberate workflow adaptation changes the simulated care pathway while preserving its documented clinical intent.",
                (
                    "The divergence is explicitly specified, documented and traceable to an approved adaptation rule or module change.",
                ),
                (
                    "No approved adaptation accounts for the observed pathway or outcome difference.",
                ),
            ),
        ),
        DifferenceClassification.IMPLEMENTATION_LIMITATION: (
            _CategoryTemplate(
                RootCauseCategory.UNSUPPORTED_GMF,
                "A known unsupported GMF capability prevents equivalent execution of the affected pathway.",
                (
                    "Compatibility metadata or deterministic inspection identifies the missing capability on the affected path.",
                ),
                (
                    "The capability is fully supported and behaves equivalently in controlled tests.",
                ),
            ),
        ),
        DifferenceClassification.MULTIFACTORIAL: (
            _CategoryTemplate(
                RootCauseCategory.UNKNOWN,
                "Multiple mechanisms may jointly contribute and no single mechanism is sufficient at candidate-generation time.",
                (
                    "Independent verification supports more than one non-redundant mechanism contributing to the same discrepancy.",
                ),
                (
                    "A single verified mechanism fully reproduces and removes the discrepancy.",
                ),
            ),
        ),
    }
)


@dataclass(frozen=True, slots=True)
class ClassificationCandidateRule:
    """Generate conservative candidates from explicit difference classifications."""

    name: str = "classification_rule"
    priority: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_identifier(self.name, "name"))
        object.__setattr__(self, "priority", _require_int(self.priority, "priority"))

    def generate(
        self,
        signal: DiscrepancySignal,
        context: CandidateGenerationContext,
    ) -> tuple[CausalCandidate, ...]:
        _require_signal(signal)
        _require_context(context)
        templates = _CLASSIFICATION_TEMPLATES.get(signal.classification, ())
        return tuple(
            _build_candidate(
                signal=signal,
                category=template.category,
                statement=_statement_for(signal, template.category),
                mechanism=template.mechanism,
                source_rule_id=self.name,
                expected_observations=template.expected_observations,
                falsification_criteria=template.falsification_criteria,
                metadata={
                    "source_kind": "deterministic_rule",
                    "classification": signal.classification.value,
                    "domain": signal.domain.value,
                    "schema_version": _SCHEMA_VERSION,
                },
            )
            for template in templates
        )


# =============================================================================
# Knowledge and protocol sources
# =============================================================================


@dataclass(frozen=True, slots=True)
class KnowledgeEntrySource:
    """Generate candidates from active validated knowledge entries.

    Matching is deliberately constraint-based.  A knowledge entry is applicable
    only when its canonical domain metadata includes the signal domain and every
    optional selector declared by the entry matches the signal exactly.
    """

    name: str = "knowledge_entry"
    priority: int = 80

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_identifier(self.name, "name"))
        object.__setattr__(self, "priority", _require_int(self.priority, "priority"))

    def generate(
        self,
        signal: DiscrepancySignal,
        context: CandidateGenerationContext,
    ) -> tuple[CausalCandidate, ...]:
        _require_signal(signal)
        _require_context(context)
        candidates: list[CausalCandidate] = []
        for entry in context.knowledge_entries:
            if not _knowledge_entry_matches(entry, signal):
                continue
            category = _root_cause_category(entry.category_id)
            candidates.append(
                _build_candidate(
                    signal=signal,
                    category=category,
                    statement=entry.root_cause,
                    mechanism=(
                        f"Validated knowledge entry {entry.id!r} matches the affected "
                        f"domain and explicit applicability constraints: {entry.detection_pattern}"
                    ),
                    knowledge_entry_id=entry.id,
                    expected_observations=tuple(
                        check.expected_result for check in entry.verifications
                    ),
                    falsification_criteria=tuple(entry.limitations),
                    metadata={
                        "source_kind": "validated_knowledge",
                        "knowledge_title": entry.title,
                        "causal_certainty": entry.causal_certainty.value,
                        "source_investigation_id": entry.source_investigation_id,
                        "source_hypothesis_id": entry.source_hypothesis_id,
                        "applicability": entry.applicability,
                        "schema_version": _SCHEMA_VERSION,
                    },
                )
            )
        return tuple(candidates)


@dataclass(frozen=True, slots=True)
class InvestigationHypothesisSource:
    """Reuse non-refuted hypotheses from explicitly requested investigations."""

    name: str = "investigation_hypothesis"
    priority: int = 70

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_identifier(self.name, "name"))
        object.__setattr__(self, "priority", _require_int(self.priority, "priority"))

    def generate(
        self,
        signal: DiscrepancySignal,
        context: CandidateGenerationContext,
    ) -> tuple[CausalCandidate, ...]:
        _require_signal(signal)
        _require_context(context)
        candidates: list[CausalCandidate] = []
        for investigation in context.investigations:
            if not _investigation_matches(investigation, signal):
                continue
            for hypothesis in investigation.hypotheses:
                if hypothesis.status is HypothesisStatus.REFUTED:
                    continue
                category = _root_cause_category(hypothesis.category_id)
                candidates.append(
                    _build_candidate(
                        signal=signal,
                        category=category,
                        statement=hypothesis.statement,
                        mechanism=hypothesis.rationale,
                        source_rule_id=f"{self.name}:{investigation.id}:{hypothesis.id}",
                        expected_observations=_hypothesis_expected_observations(
                            investigation, hypothesis
                        ),
                        falsification_criteria=tuple(hypothesis.limitations),
                        metadata={
                            "source_kind": "prior_investigation",
                            "investigation_id": investigation.id,
                            "hypothesis_id": hypothesis.id,
                            "hypothesis_status": hypothesis.status.value,
                            "hypothesis_certainty": hypothesis.certainty.value,
                            "schema_version": _SCHEMA_VERSION,
                        },
                    )
                )
        return tuple(candidates)


@dataclass(frozen=True, slots=True)
class ProtocolCandidateSource:
    """Generate investigable categories from applicable canonical protocols."""

    name: str = "investigation_protocol"
    priority: int = 60

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_identifier(self.name, "name"))
        object.__setattr__(self, "priority", _require_int(self.priority, "priority"))

    def generate(
        self,
        signal: DiscrepancySignal,
        context: CandidateGenerationContext,
    ) -> tuple[CausalCandidate, ...]:
        _require_signal(signal)
        _require_context(context)
        candidates: list[CausalCandidate] = []
        compatible_categories = _compatible_categories(signal.classification)

        for protocol in context.protocols:
            if signal.domain.value not in protocol.domain_ids:
                continue
            for category_id in protocol.candidate_category_ids:
                category = _root_cause_category(category_id)
                if compatible_categories and category not in compatible_categories:
                    continue
                steps = tuple(
                    step
                    for step in protocol.steps
                    if category.value in step.investigates_category_ids
                )
                if not steps:
                    continue
                candidates.append(
                    _build_candidate(
                        signal=signal,
                        category=category,
                        statement=(
                            f"Investigate {category.value} as a possible explanation for "
                            f"signal {signal.id!r} using protocol {protocol.qualified_id!r}."
                        ),
                        mechanism=(
                            f"Protocol applicability matched validation domain "
                            f"{signal.domain.value!r}. The protocol does not assert causality; "
                            "it defines deterministic evidence and verification steps for this category."
                        ),
                        investigation_protocol_id=protocol.qualified_id,
                        expected_observations=tuple(
                            _unique_texts(step.expected_result for step in steps)
                        ),
                        falsification_criteria=tuple(
                            _unique_texts(
                                text
                                for step in steps
                                for text in (
                                    step.interpretation_boundary,
                                    step.stop_if,
                                )
                                if text is not None
                            )
                        ),
                        metadata={
                            "source_kind": "investigation_protocol",
                            "protocol_id": protocol.id,
                            "protocol_version": protocol.version,
                            "protocol_step_ids": tuple(step.id for step in steps),
                            "required_evidence_requirement_ids": tuple(
                                requirement.id
                                for step in steps
                                for requirement in step.evidence_requirements
                                if requirement.level is EvidenceRequirementLevel.REQUIRED
                            ),
                            "schema_version": _SCHEMA_VERSION,
                        },
                    )
                )
        return tuple(candidates)


# =============================================================================
# Generation engine
# =============================================================================


@dataclass(slots=True)
class _CandidateRegistry:
    """Mutable internal registry enforcing candidate identity integrity."""

    _candidates: dict[str, CausalCandidate] = field(default_factory=dict)
    _insertion_order: list[str] = field(default_factory=list)

    def add(self, candidate: CausalCandidate) -> bool:
        """Register ``candidate`` and report whether it was newly inserted."""

        if not isinstance(candidate, CausalCandidate):
            raise TypeError("candidate must be a CausalCandidate.")
        existing = self._candidates.get(candidate.id)
        if existing is not None and existing != candidate:
            raise RootCauseIntegrityError(
                "Candidate identifier collision with non-equivalent content.",
                context={"candidate_id": candidate.id},
            )
        if existing is not None:
            return False
        self._insertion_order.append(candidate.id)
        self._candidates[candidate.id] = candidate
        return True

    def values(self) -> tuple[CausalCandidate, ...]:
        return tuple(sorted(self._candidates.values(), key=lambda item: item.id))

    def prioritized_values(self) -> tuple[CausalCandidate, ...]:
        """Return candidates in deterministic source-execution order."""

        return tuple(self._candidates[item_id] for item_id in self._insertion_order)


class CandidateGenerator:
    """Coordinate deterministic candidate sources without ranking their output."""

    def __init__(self, rules: Sequence[CandidateRule] | None = None) -> None:
        selected = (
            (
                ClassificationCandidateRule(),
                KnowledgeEntrySource(),
                InvestigationHypothesisSource(),
                ProtocolCandidateSource(),
            )
            if rules is None
            else tuple(rules)
        )
        if not selected:
            raise ValueError("CandidateGenerator requires at least one candidate rule.")
        for index, rule in enumerate(selected):
            _validate_rule(rule, f"rules[{index}]")
        names = tuple(rule.name for rule in selected)
        if len(names) != len(set(names)):
            raise ValueError("Candidate rule names must be unique.")
        self._rules = tuple(sorted(selected, key=lambda item: (-item.priority, item.name)))

    @property
    def rules(self) -> tuple[CandidateRule, ...]:
        """Rules in deterministic execution order."""

        return self._rules

    def generate(self, context: CandidateGenerationContext) -> CandidateGeneration:
        """Generate all investigable candidates for the supplied signals."""

        _require_context(context)
        registry = _CandidateRegistry()
        diagnostics: list[CandidateDiagnostic] = []
        handled_signals: set[str] = set()
        source_counts: dict[str, int] = {rule.name: 0 for rule in self._rules}

        for signal in context.signals:
            signal_generated = False
            for rule in self._rules:
                try:
                    emitted = _invoke_rule(rule, signal, context)
                    for candidate in emitted:
                        _validate_candidate(candidate, signal, context, rule.name)
                        inserted = registry.add(candidate)
                        if inserted:
                            source_counts[rule.name] += 1
                        signal_generated = True
                except (
                    CandidateGenerationError,
                    RootCauseInputError,
                    RootCauseIntegrityError,
                    TypeError,
                    ValueError,
                ) as exc:
                    if context.strict:
                        if isinstance(exc, CandidateGenerationError):
                            raise
                        raise CandidateGenerationError(
                            "Candidate source failed to generate a valid candidate.",
                            context={
                                "signal_id": signal.id,
                                "source_name": rule.name,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                                "error_context": getattr(exc, "context", {}),
                            },
                        ) from exc
                    diagnostics.append(
                        CandidateDiagnostic(
                            code="candidates.source_skipped",
                            message="Candidate source could not be evaluated safely.",
                            signal_id=signal.id,
                            source_name=rule.name,
                            metadata={
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                                "error_context": getattr(exc, "context", {}),
                            },
                        )
                    )
            if signal_generated:
                handled_signals.add(signal.id)

        all_candidates = registry.prioritized_values()
        _validate_candidate_graph(all_candidates, context)
        candidates, omitted_candidate_ids = _limit_candidate_graph(
            all_candidates,
            context.request.max_candidates,
        )
        _validate_candidate_graph(candidates, context)
        limit_applied = bool(omitted_candidate_ids)
        if limit_applied:
            diagnostics.append(
                CandidateDiagnostic(
                    code="candidates.limit_applied",
                    message=(
                        "Candidate generation exceeded RootCauseRequest.max_candidates; "
                        "complete alternative-candidate components were retained in "
                        "deterministic source-priority order."
                    ),
                    severity=CandidateGenerationSeverity.INFO,
                    metadata={
                        "generated_count": len(all_candidates),
                        "retained_count": len(candidates),
                        "max_candidates": context.request.max_candidates,
                        "omitted_candidate_ids": omitted_candidate_ids,
                    },
                )
            )
        retained_signal_ids = {
            signal_id for candidate in candidates for signal_id in candidate.signal_ids
        }
        unhandled = tuple(
            signal.id for signal in context.signals if signal.id not in retained_signal_ids
        )
        return CandidateGeneration(
            request_id=context.request.id,
            candidates=candidates,
            diagnostics=tuple(diagnostics),
            source_counts=source_counts,
            unhandled_signal_ids=unhandled,
            metadata={
                "rule_names": tuple(rule.name for rule in self._rules),
                "strict": context.strict,
                "schema_version": _SCHEMA_VERSION,
                "signal_count": len(context.signals),
                "candidate_count": len(candidates),
                "generated_before_limit": len(all_candidates),
                "limit_applied": limit_applied,
                "context_metadata": context.metadata,
            },
        )


def generate_candidates(
    request: RootCauseRequest,
    signals: SignalExtraction | Sequence[DiscrepancySignal],
    *,
    evidence: Sequence[EvidenceReference] = (),
    knowledge_registry: KnowledgeRegistry | None = None,
    knowledge_entries: Sequence[KnowledgeEntry] | None = None,
    investigations: Sequence[InvestigationCase] | None = None,
    protocol_catalog: ProtocolCatalog | None = CANONICAL_PROTOCOLS,
    protocols: Sequence[InvestigationProtocol] | None = None,
    rules: Sequence[CandidateRule] | None = None,
    strict: bool | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CandidateGeneration:
    """Functional convenience API for deterministic candidate generation.

    ``knowledge_registry`` and explicit ``knowledge_entries`` / ``investigations``
    are mutually exclusive to avoid ambiguous snapshots.  Likewise,
    ``protocol_catalog`` and explicit ``protocols`` cannot both provide protocol
    sources.
    """

    if not isinstance(request, RootCauseRequest):
        raise TypeError("request must be a RootCauseRequest.")

    normalized_signals = signals.signals if isinstance(signals, SignalExtraction) else tuple(signals)
    if isinstance(signals, SignalExtraction) and signals.request_id != request.id:
        raise RootCauseIntegrityError(
            "Signal extraction belongs to a different root-cause request.",
            context={
                "request_id": request.id,
                "signal_extraction_request_id": signals.request_id,
            },
        )

    if knowledge_registry is not None and (
        knowledge_entries is not None or investigations is not None
    ):
        raise ValueError(
            "knowledge_registry cannot be combined with explicit knowledge_entries or investigations."
        )
    if knowledge_registry is not None:
        if not isinstance(knowledge_registry, KnowledgeRegistry):
            raise TypeError("knowledge_registry must be a KnowledgeRegistry.")
        active_entries = knowledge_registry.knowledge_entries(active_only=True)
        if request.knowledge_entry_ids:
            active_by_id = {entry.id: entry for entry in active_entries}
            missing_entry_ids = tuple(
                entry_id
                for entry_id in request.knowledge_entry_ids
                if entry_id not in active_by_id
            )
            if missing_entry_ids:
                raise RootCauseInputError(
                    "RootCauseRequest references unavailable validated knowledge entries.",
                    context={"missing_knowledge_entry_ids": missing_entry_ids},
                )
            selected_entries = tuple(
                active_by_id[entry_id] for entry_id in request.knowledge_entry_ids
            )
        else:
            selected_entries = active_entries

        try:
            requested_investigations = tuple(
                knowledge_registry.investigation(item_id)
                for item_id in request.investigation_case_ids
            )
        except UnknownInvestigationError as exc:
            raise RootCauseInputError(
                "RootCauseRequest references an unavailable investigation case.",
                context={"error": str(exc)},
            ) from exc
    else:
        selected_entries = tuple(knowledge_entries or ())
        requested_investigations = tuple(investigations or ())

    if protocols is not None and protocol_catalog is not None:
        raise ValueError("protocol_catalog cannot be combined with explicit protocols.")
    if protocols is not None:
        selected_protocols = tuple(protocols)
    elif protocol_catalog is None:
        selected_protocols = ()
    else:
        if not isinstance(protocol_catalog, ProtocolCatalog):
            raise TypeError("protocol_catalog must be a ProtocolCatalog or None.")
        selected_protocols = tuple(protocol_catalog.protocols)

    context = CandidateGenerationContext(
        request=request,
        signals=tuple(normalized_signals),
        evidence=tuple(evidence),
        knowledge_entries=tuple(selected_entries),
        investigations=tuple(requested_investigations),
        protocols=tuple(selected_protocols),
        strict=strict,
        metadata=metadata or {},
    )
    return CandidateGenerator(rules).generate(context)


# =============================================================================
# Matching and integrity helpers
# =============================================================================


def _knowledge_entry_matches(
    entry: KnowledgeEntry,
    signal: DiscrepancySignal,
) -> bool:
    if entry.status is not KnowledgeEntryStatus.VALIDATED:
        return False

    metadata = entry.metadata
    domains = _selector_values(metadata.get("domain_ids"))
    if signal.domain.value not in domains:
        return False

    selectors: tuple[tuple[str, str | None], ...] = (
        ("difference_classifications", signal.classification.value),
        ("metric_ids", signal.metric_id),
        ("source_ids", signal.source_id),
        ("cohort_ids", signal.cohort_id),
    )
    for key, observed in selectors:
        declared = _selector_values(metadata.get(key))
        if not declared:
            continue
        if observed is None or observed not in declared:
            return False
    return True


def _investigation_matches(
    investigation: InvestigationCase,
    signal: DiscrepancySignal,
) -> bool:
    return any(
        item.domain == signal.domain.value
        for item in investigation.signals
    )


def _hypothesis_expected_observations(
    investigation: InvestigationCase,
    hypothesis: CausalHypothesis,
) -> tuple[str, ...]:
    return tuple(
        _unique_texts(
            check.expected_result
            for check in investigation.verifications
            if check.hypothesis_id == hypothesis.id
        )
    )


def _compatible_categories(
    classification: DifferenceClassification,
) -> frozenset[RootCauseCategory]:
    templates = _CLASSIFICATION_TEMPLATES.get(classification, ())
    return frozenset(item.category for item in templates)


def _build_candidate(
    *,
    signal: DiscrepancySignal,
    category: RootCauseCategory,
    statement: str,
    mechanism: str,
    source_rule_id: str | None = None,
    knowledge_entry_id: str | None = None,
    investigation_protocol_id: str | None = None,
    expected_observations: Sequence[str] = (),
    falsification_criteria: Sequence[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> CausalCandidate:
    payload = {
        "category": category.value,
        "statement": _require_text(statement, "statement"),
        "mechanism": _require_text(mechanism, "mechanism"),
        "signal_ids": (signal.id,),
        "source_rule_id": source_rule_id,
        "knowledge_entry_id": knowledge_entry_id,
        "investigation_protocol_id": investigation_protocol_id,
        "expected_observations": tuple(_unique_texts(expected_observations)),
        "falsification_criteria": tuple(_unique_texts(falsification_criteria)),
    }
    candidate_id = _content_id(_CANDIDATE_PREFIX, payload)
    return CausalCandidate(
        id=candidate_id,
        category=category,
        statement=payload["statement"],
        mechanism=payload["mechanism"],
        signal_ids=payload["signal_ids"],
        status=CandidateStatus.GENERATED,
        source_rule_id=source_rule_id,
        knowledge_entry_id=knowledge_entry_id,
        investigation_protocol_id=investigation_protocol_id,
        expected_observations=payload["expected_observations"],
        falsification_criteria=payload["falsification_criteria"],
        prerequisite_evidence_ids=signal.evidence_ids,
        metadata=metadata or {},
    )


def _statement_for(
    signal: DiscrepancySignal,
    category: RootCauseCategory,
) -> str:
    return (
        f"The discrepancy described by signal {signal.id!r} may be caused by "
        f"{category.value}."
    )


def _invoke_rule(
    rule: CandidateRule,
    signal: DiscrepancySignal,
    context: CandidateGenerationContext,
) -> tuple[CausalCandidate, ...]:
    try:
        emitted = rule.generate(signal, context)
    except (
        CandidateGenerationError,
        RootCauseInputError,
        RootCauseIntegrityError,
        TypeError,
        ValueError,
    ):
        raise
    except Exception as exc:  # pragma: no cover - defensive plugin boundary
        raise CandidateGenerationError(
            "Candidate source raised an unexpected exception.",
            context={
                "signal_id": signal.id,
                "source_name": rule.name,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        ) from exc

    if isinstance(emitted, (str, bytes)) or not isinstance(emitted, Sequence):
        raise TypeError(
            f"Candidate rule {rule.name!r} must return a sequence of CausalCandidate values."
        )
    return _normalize_models(
        emitted, CausalCandidate, f"rule[{rule.name}].candidates"
    )


def _validate_candidate(
    candidate: CausalCandidate,
    signal: DiscrepancySignal,
    context: CandidateGenerationContext,
    source_name: str,
) -> None:
    if candidate.status is not CandidateStatus.GENERATED:
        raise RootCauseIntegrityError(
            "Candidate generation may only emit GENERATED candidates.",
            context={
                "candidate_id": candidate.id,
                "candidate_status": candidate.status.value,
                "source_name": source_name,
            },
        )
    if signal.id not in candidate.signal_ids:
        raise RootCauseIntegrityError(
            "Candidate does not reference the signal currently being processed.",
            context={
                "candidate_id": candidate.id,
                "signal_id": signal.id,
                "source_name": source_name,
            },
        )
    unknown_signal_ids = sorted(
        set(candidate.signal_ids).difference(context.signal_catalog)
    )
    if unknown_signal_ids:
        raise RootCauseIntegrityError(
            "Candidate references unknown signals.",
            context={
                "candidate_id": candidate.id,
                "unknown_signal_ids": unknown_signal_ids,
            },
        )
    unknown_evidence_ids = sorted(
        set(candidate.prerequisite_evidence_ids).difference(context.evidence_catalog)
    )
    if unknown_evidence_ids:
        raise RootCauseIntegrityError(
            "Candidate references prerequisite evidence outside the generation context.",
            context={
                "candidate_id": candidate.id,
                "unknown_evidence_ids": unknown_evidence_ids,
            },
        )
    if candidate.knowledge_entry_id is not None:
        entry = context.knowledge_catalog.get(candidate.knowledge_entry_id)
        if entry is None:
            raise RootCauseIntegrityError(
                "Candidate references an unavailable knowledge entry.",
                context={
                    "candidate_id": candidate.id,
                    "knowledge_entry_id": candidate.knowledge_entry_id,
                },
            )
        if entry.status is not KnowledgeEntryStatus.VALIDATED:
            raise RootCauseIntegrityError(
                "Candidate references knowledge that is not validated.",
                context={
                    "candidate_id": candidate.id,
                    "knowledge_entry_id": entry.id,
                    "knowledge_status": entry.status.value,
                },
            )
    if candidate.investigation_protocol_id is not None:
        if candidate.investigation_protocol_id not in context.protocol_catalog:
            raise RootCauseIntegrityError(
                "Candidate references an unavailable investigation protocol.",
                context={
                    "candidate_id": candidate.id,
                    "investigation_protocol_id": candidate.investigation_protocol_id,
                },
            )


def _limit_candidate_graph(
    candidates: Sequence[CausalCandidate],
    max_candidates: int,
) -> tuple[tuple[CausalCandidate, ...], tuple[str, ...]]:
    """Retain complete alternative-candidate components within ``max_candidates``.

    A plain sequence slice can orphan ``alternative_candidate_ids`` and produce an
    internally invalid result.  Components are therefore treated atomically.  The
    first candidate encountered determines component priority, preserving the
    deterministic rule/signal execution order.
    """

    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int):
        raise TypeError("max_candidates must be an integer.")
    if max_candidates <= 0:
        raise ValueError("max_candidates must be greater than zero.")

    catalog = {candidate.id: candidate for candidate in candidates}
    visited: set[str] = set()
    retained_ids: set[str] = set()

    for candidate in candidates:
        if candidate.id in visited:
            continue
        pending = [candidate.id]
        component: set[str] = set()
        while pending:
            candidate_id = pending.pop()
            if candidate_id in component:
                continue
            component.add(candidate_id)
            pending.extend(catalog[candidate_id].alternative_candidate_ids)
        visited.update(component)

        if len(retained_ids) + len(component) <= max_candidates:
            retained_ids.update(component)

    retained = tuple(candidate for candidate in candidates if candidate.id in retained_ids)
    omitted = tuple(candidate.id for candidate in candidates if candidate.id not in retained_ids)
    return retained, omitted


def _validate_candidate_graph(
    candidates: Sequence[CausalCandidate],
    context: CandidateGenerationContext,
) -> None:
    catalog = {item.id: item for item in candidates}
    for candidate in candidates:
        unknown_alternatives = sorted(
            set(candidate.alternative_candidate_ids).difference(catalog)
        )
        if unknown_alternatives:
            raise RootCauseIntegrityError(
                "Candidate references unknown alternatives.",
                context={
                    "candidate_id": candidate.id,
                    "unknown_alternative_candidate_ids": unknown_alternatives,
                },
            )
        for alternative_id in candidate.alternative_candidate_ids:
            alternative = catalog[alternative_id]
            if candidate.id not in alternative.alternative_candidate_ids:
                raise RootCauseIntegrityError(
                    "Alternative-candidate relationships must be symmetric.",
                    context={
                        "candidate_id": candidate.id,
                        "alternative_candidate_id": alternative_id,
                    },
                )

    referenced_signals = {
        signal_id for candidate in candidates for signal_id in candidate.signal_ids
    }
    unknown_signals = sorted(referenced_signals.difference(context.signal_catalog))
    if unknown_signals:
        raise RootCauseIntegrityError(
            "Candidate graph references unknown signals.",
            context={"unknown_signal_ids": unknown_signals},
        )


def _validate_context_scope(context: CandidateGenerationContext) -> None:
    requested_domains = set(context.request.requested_domains)
    if requested_domains:
        out_of_scope = tuple(
            signal.id for signal in context.signals if signal.domain not in requested_domains
        )
        if out_of_scope:
            raise RootCauseInputError(
                "Candidate-generation signals fall outside requested validation domains.",
                context={
                    "request_id": context.request.id,
                    "out_of_scope_signal_ids": out_of_scope,
                    "requested_domains": tuple(
                        item.value for item in context.request.requested_domains
                    ),
                },
            )

    evidence_ids = set(context.evidence_catalog)
    unknown_signal_evidence = {
        signal.id: tuple(sorted(set(signal.evidence_ids).difference(evidence_ids)))
        for signal in context.signals
        if set(signal.evidence_ids).difference(evidence_ids)
    }
    if unknown_signal_evidence:
        raise RootCauseIntegrityError(
            "Signals reference evidence outside the candidate-generation context.",
            context={"unknown_signal_evidence": unknown_signal_evidence},
        )

    required_entry_ids = set(context.request.knowledge_entry_ids)
    supplied_entry_ids = set(context.knowledge_catalog)
    missing_entries = sorted(required_entry_ids.difference(supplied_entry_ids))
    if missing_entries:
        raise RootCauseInputError(
            "RootCauseRequest references knowledge entries that were not supplied.",
            context={"missing_knowledge_entry_ids": missing_entries},
        )
    unexpected_entries = sorted(supplied_entry_ids.difference(required_entry_ids))
    if required_entry_ids and unexpected_entries:
        raise RootCauseIntegrityError(
            "Candidate context contains knowledge entries outside the request scope.",
            context={"unexpected_knowledge_entry_ids": unexpected_entries},
        )

    required_investigation_ids = set(context.request.investigation_case_ids)
    supplied_investigation_ids = set(context.investigation_catalog)
    missing_investigations = sorted(
        required_investigation_ids.difference(supplied_investigation_ids)
    )
    if missing_investigations:
        raise RootCauseInputError(
            "RootCauseRequest references investigations that were not supplied.",
            context={"missing_investigation_case_ids": missing_investigations},
        )
    unexpected_investigations = sorted(
        supplied_investigation_ids.difference(required_investigation_ids)
    )
    if required_investigation_ids and unexpected_investigations:
        raise RootCauseIntegrityError(
            "Candidate context contains investigations outside the request scope.",
            context={"unexpected_investigation_case_ids": unexpected_investigations},
        )


def _validate_rule(rule: CandidateRule, field_name: str) -> None:
    if not isinstance(rule, CandidateRule):
        raise TypeError(f"{field_name} must satisfy CandidateRule.")
    _require_identifier(rule.name, f"{field_name}.name")
    _require_int(rule.priority, f"{field_name}.priority")


def _require_signal(value: DiscrepancySignal) -> None:
    if not isinstance(value, DiscrepancySignal):
        raise TypeError("signal must be a DiscrepancySignal.")


def _require_context(value: CandidateGenerationContext) -> None:
    if not isinstance(value, CandidateGenerationContext):
        raise TypeError("context must be a CandidateGenerationContext.")


def _root_cause_category(value: str) -> RootCauseCategory:
    try:
        return RootCauseCategory(value)
    except ValueError as exc:
        raise RootCauseIntegrityError(
            "Knowledge source references a non-canonical root-cause category.",
            context={"category_id": value},
        ) from exc


def _selector_values(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        normalized = value.strip()
        return frozenset((normalized,)) if normalized else frozenset()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        result: set[str] = set()
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise RootCauseIntegrityError(
                    "Knowledge applicability selector must contain strings.",
                    context={"selector_index": index, "value_type": type(item).__name__},
                )
            normalized = item.strip()
            if normalized:
                result.add(normalized)
        return frozenset(result)
    raise RootCauseIntegrityError(
        "Knowledge applicability selector must be a string or sequence of strings.",
        context={"value_type": type(value).__name__},
    )


# =============================================================================
# Generic normalization helpers
# =============================================================================


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


def _require_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _normalize_models(
    values: Sequence[Any],
    model_type: type[Any],
    field_name: str,
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {model_type.__name__} values.")
    normalized = tuple(values)
    for index, value in enumerate(normalized):
        if not isinstance(value, model_type):
            raise TypeError(
                f"{field_name}[{index}] must be {model_type.__name__}, "
                f"got {type(value).__name__}."
            )
    return normalized


def _require_unique_ids(values: Sequence[Any], field_name: str) -> None:
    identifiers = tuple(item.id for item in values)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{field_name} contains duplicate ids.")


def _require_unique_protocol_ids(values: Sequence[InvestigationProtocol]) -> None:
    identifiers = tuple(item.qualified_id for item in values)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("protocols contains duplicate qualified ids.")


def _normalize_identifier_tuple(
    values: Sequence[str], field_name: str
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of identifiers.")
    normalized = tuple(sorted({_require_identifier(item, field_name) for item in values}))
    return normalized


def _normalize_count_mapping(
    value: Mapping[str, int], field_name: str
) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized: dict[str, int] = {}
    for key, count in value.items():
        identifier = _require_identifier(key, f"{field_name}.key")
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError(f"{field_name}[{identifier!r}] must be an integer.")
        if count < 0:
            raise ValueError(f"{field_name}[{identifier!r}] must be non-negative.")
        normalized[identifier] = count
    return MappingProxyType(dict(sorted(normalized.items())))


def _unique_texts(values: Sequence[str] | Any) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _require_text(value, "text")
        if text not in seen:
            result.append(text)
            seen.add(text)
    return tuple(result)


def _content_id(prefix: str, payload: Mapping[str, Any]) -> str:
    encoded = dumps(
        _canonicalize(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return f"{prefix}:{sha256(encoded).hexdigest()[:32]}"


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return MappingProxyType(
        {
            _require_text(str(key), f"{field_name}.key"): _deep_freeze(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    )


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _deep_freeze(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        )
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_deep_freeze(item) for item in value), key=repr))
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Metadata values must be finite.")
    if isinstance(value, Enum):
        return value.value
    return value


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonicalize(item) for item in value), key=repr)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("Canonical payload values must be finite.")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return repr(value)