"""Deterministic evidence normalization for Phase 3 root-cause analysis.

The Root Cause Engine consumes outputs produced by several independent layers:
validation, scientific interpretation, the Knowledge Engine, experiment
orchestration, simulator provenance and persisted artefacts.  This module
provides the boundary that converts those heterogeneous inputs into immutable
:class:`~validation.root_cause.models.EvidenceReference` objects.

Scientific boundary
-------------------
Evidence collection records observations and provenance only.  It does **not**:

* infer a causal mechanism;
* decide whether evidence supports or contradicts a candidate;
* generate or rank candidates;
* execute verification procedures;
* assign causal confidence or a final root-cause status.

All references emitted here are therefore neutral.  Candidate-specific direction
is assigned later, when an explicit evidence-to-candidate assessment exists.

Integrity guarantees
--------------------

* Stable identifiers are preserved whenever the upstream source exposes one.
* Synthetic identifiers are content-addressed and deterministic.
* Duplicate identifiers are accepted only for byte-equivalent normalized data.
* Requested artefacts are resolved against a typed artefact catalogue.
* Hashes are propagated, never guessed, and may be verified through an injected
  verifier without coupling this module to the filesystem.
* Collection order never changes the canonical result order.
* Strict and permissive collection modes are explicit and auditable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from hashlib import sha256
from json import dumps
from math import isfinite
from pathlib import PurePath
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Final, Protocol, TypeAlias, runtime_checkable

from validation.interpretation.models import (
    EvidenceValue,
    InterpretationFinding,
)
from validation.knowledge.models import (
    EvidenceItem,
    InvestigationCase,
    KnowledgeEntry,
)

from validation.knowledge.taxonomy import ValidationDomain

from validation.orchestration.models import ArtifactReference, ExperimentResult
from validation.root_cause.exceptions import (
    EvidenceCollectionError,
    RootCauseInputError,
    RootCauseIntegrityError,
)
from validation.root_cause.models import (
    EvidenceDirection,
    EvidenceReference,
    RootCauseRequest,
)

__all__ = [
    "ArtifactIntegrityVerifier",
    "ArtifactReferenceAdapter",
    "CollectionDiagnostic",
    "CollectionSeverity",
    "EvidenceAdapter",
    "EvidenceCollection",
    "EvidenceCollectionContext",
    "EvidenceCollector",
    "EvidenceRegistry",
    "InterpretationEvidenceAdapter",
    "InterpretationFindingAdapter",
    "InvestigationCaseAdapter",
    "KnowledgeEntryAdapter",
    "KnowledgeEvidenceAdapter",
    "ExperimentResultAdapter",
    "MappingEvidenceAdapter",
    "SourceFamily",
    "UpstreamBindingKind",
    "collect_evidence",
]


# =============================================================================
# Public source taxonomy and immutable collection contracts
# =============================================================================


class SourceFamily(str, Enum):
    """Canonical upstream family from which an evidence item was collected."""

    VALIDATION = "validation"
    INTERPRETATION = "interpretation"
    KNOWLEDGE = "knowledge"
    ORCHESTRATION = "orchestration"
    MANIFEST = "manifest"
    ARTIFACT = "artifact"
    SIMULATOR_OUTPUT = "simulator_output"
    PROVENANCE = "provenance"
    MODULE_DEFINITION = "module_definition"
    EXECUTION_ENVIRONMENT = "execution_environment"
    EXTERNAL = "external"


class CollectionSeverity(str, Enum):
    """Severity of one non-fatal collection diagnostic."""

    INFO = "info"
    WARNING = "warning"


class UpstreamBindingKind(str, Enum):
    """Canonical request-bound upstream object families.

    Bindings are deliberately closed rather than free-form.  This prevents a
    descriptor typo from satisfying request completeness checks accidentally.
    """

    VALIDATION_RESULT = "validation_result"
    INTERPRETATION_FINDING = "interpretation_finding"
    INVESTIGATION_CASE = "investigation_case"
    KNOWLEDGE_ENTRY = "knowledge_entry"
    EXPERIMENT_RESULT = "experiment_result"


_IDENTIFIER_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SHA256_PATTERN: Final = compile_pattern(r"^[0-9a-f]{64}$")
_SYNTHETIC_ID_PREFIX: Final = "evidence"
_SCHEMA_VERSION: Final[int] = 1


@dataclass(frozen=True, slots=True)
class CollectionDiagnostic:
    """Auditable non-fatal event produced during permissive collection."""

    code: str
    message: str
    severity: CollectionSeverity = CollectionSeverity.WARNING
    source_type: str | None = None
    source_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_identifier(self.code, "code"))
        object.__setattr__(self, "message", _require_text(self.message, "message"))
        if not isinstance(self.severity, CollectionSeverity):
            raise TypeError("severity must be a CollectionSeverity member.")
        object.__setattr__(
            self,
            "source_type",
            _optional_identifier(self.source_type, "source_type"),
        )
        object.__setattr__(
            self,
            "source_id",
            _optional_identifier(self.source_id, "source_id"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class EvidenceCollectionContext:
    """Immutable context shared by all evidence adapters for one request."""

    request: RootCauseRequest
    artifacts: tuple[ArtifactReference, ...] = ()
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    strict: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, RootCauseRequest):
            raise TypeError("request must be a RootCauseRequest.")
        artifacts = _normalize_model_tuple(
            self.artifacts,
            ArtifactReference,
            "artifacts",
        )
        _require_unique(artifacts, key=lambda item: item.id, field_name="artifacts")
        object.__setattr__(self, "artifacts", tuple(sorted(artifacts, key=lambda item: item.id)))
        object.__setattr__(
            self,
            "collected_at",
            _normalize_datetime(self.collected_at, "collected_at"),
        )
        if self.strict is None:
            object.__setattr__(self, "strict", self.request.strict_integrity)
        elif not isinstance(self.strict, bool):
            raise TypeError("strict must be a boolean or None.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    @property
    def artifact_catalog(self) -> Mapping[str, ArtifactReference]:
        """Return an immutable catalogue indexed by stable artefact identifier."""

        return MappingProxyType({artifact.id: artifact for artifact in self.artifacts})


@dataclass(frozen=True, slots=True)
class EvidenceCollection:
    """Canonical output of one evidence-collection operation."""

    request_id: str
    evidence: tuple[EvidenceReference, ...]
    artifacts: tuple[ArtifactReference, ...] = ()
    diagnostics: tuple[CollectionDiagnostic, ...] = ()
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: int = _SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require_identifier(self.request_id, "request_id"))
        evidence = _normalize_model_tuple(self.evidence, EvidenceReference, "evidence")
        _require_unique(evidence, key=lambda item: item.id, field_name="evidence")
        object.__setattr__(self, "evidence", tuple(sorted(evidence, key=lambda item: item.id)))

        artifacts = _normalize_model_tuple(self.artifacts, ArtifactReference, "artifacts")
        _require_unique(artifacts, key=lambda item: item.id, field_name="artifacts")
        object.__setattr__(self, "artifacts", tuple(sorted(artifacts, key=lambda item: item.id)))

        diagnostics = _normalize_model_tuple(
            self.diagnostics,
            CollectionDiagnostic,
            "diagnostics",
        )
        object.__setattr__(
            self,
            "diagnostics",
            tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.severity.value,
                        item.code,
                        item.source_type or "",
                        item.source_id or "",
                        item.message,
                    ),
                )
            ),
        )
        object.__setattr__(
            self,
            "collected_at",
            _normalize_datetime(self.collected_at, "collected_at"),
        )
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an integer.")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be greater than zero.")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        artifact_ids = {artifact.id for artifact in self.artifacts}
        dangling = sorted(
            reference.artifact_id
            for reference in self.evidence
            if reference.artifact_id is not None and reference.artifact_id not in artifact_ids
        )
        if dangling:
            raise ValueError(
                "EvidenceCollection contains evidence referring to unregistered artefacts: "
                + ", ".join(dangling)
            )

    @property
    def evidence_by_id(self) -> Mapping[str, EvidenceReference]:
        """Return the collected evidence indexed by identifier."""

        return MappingProxyType({item.id: item for item in self.evidence})

    @property
    def has_warnings(self) -> bool:
        """Return whether permissive collection emitted at least one warning."""

        return any(item.severity is CollectionSeverity.WARNING for item in self.diagnostics)


# =============================================================================
# Adapter and integrity-verifier protocols
# =============================================================================


@runtime_checkable
class EvidenceAdapter(Protocol):
    """Adapter that normalizes one supported upstream object.

    Implementations must be stateless or safely reusable.  ``collect`` may
    return more than one reference for compound sources, but every reference
    must remain neutral and independently auditable.
    """

    @property
    def name(self) -> str:
        """Stable adapter identifier used in diagnostics and metadata."""

    @property
    def priority(self) -> int:
        """Selection priority; larger values are evaluated first."""

    def supports(self, source: Any) -> bool:
        """Return whether this adapter can normalize ``source``."""

    def collect(
        self,
        source: Any,
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        """Normalize ``source`` into one or more neutral evidence references."""


@runtime_checkable
class ArtifactIntegrityVerifier(Protocol):
    """Injected artefact verifier used without introducing filesystem coupling."""

    def verify(self, artifact: ArtifactReference) -> bool:
        """Return whether the artefact matches its declared integrity metadata."""


def _canonical_interpretation_domain(domain: str) -> ValidationDomain:
    """Map Phase 2A rule domains to canonical Root Cause validation domains."""

    normalized = _require_text(
        domain,
        "interpretation_finding.domain",
    ).lower()

    aliases = {
        "clinical": ValidationDomain.GLOBAL,
        "epidemiological": ValidationDomain.GLOBAL,
        "statistical": ValidationDomain.GLOBAL,
        "prevalence": ValidationDomain.CONDITIONS,
        "distribution": ValidationDomain.GLOBAL,
        "structural": ValidationDomain.VALIDATION_PIPELINE,
        "spanish_adaptation": ValidationDomain.INTEROPERABILITY,
    }

    try:
        return aliases[normalized]
    except KeyError as exc:
        raise RootCauseInputError(
            "Interpretation finding contains an unsupported rule domain.",
            context={
                "domain": normalized,
                "supported_domains": tuple(sorted(aliases)),
            },
        ) from exc

# =============================================================================
# Built-in adapters
# =============================================================================


@dataclass(frozen=True, slots=True)
class ArtifactReferenceAdapter:
    """Normalize one orchestration artefact reference without reading its bytes."""

    name: str = "artifact_reference"
    priority: int = 100

    def supports(self, source: Any) -> bool:
        return isinstance(source, ArtifactReference)

    def collect(
        self,
        source: Any,
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        del context
        if not isinstance(source, ArtifactReference):
            raise TypeError("ArtifactReferenceAdapter requires ArtifactReference input.")
        metadata = {
            "source_family": SourceFamily.ARTIFACT.value,
            "artifact_kind": source.kind.value,
            "media_type": source.media_type,
            "size_bytes": source.size_bytes,
            "producer": source.producer,
            "created_at": source.created_at,
            "artifact_metadata": source.metadata,
        }
        return (
            EvidenceReference(
                id=_evidence_id("artifact", source.id),
                source_type=SourceFamily.ARTIFACT.value,
                summary=f"Persisted artefact {source.id} ({source.kind.value}).",
                locator=source.path.as_posix(),
                artifact_id=source.id,
                sha256=source.sha256,
                observed_at=source.created_at,
                metadata=metadata,
            ),
        )


@dataclass(frozen=True, slots=True)
class InterpretationEvidenceAdapter:
    """Normalize one Phase 2A interpretation :class:`EvidenceValue`."""

    name: str = "interpretation_evidence"
    priority: int = 90

    def supports(self, source: Any) -> bool:
        return isinstance(source, EvidenceValue)

    def collect(
        self,
        source: Any,
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        del context
        if not isinstance(source, EvidenceValue):
            raise TypeError("InterpretationEvidenceAdapter requires EvidenceValue input.")
        metadata = {
            "source_family": SourceFamily.INTERPRETATION.value,
            "metric_id": source.metric_id,
            "availability": source.availability.value,
            "value": source.value,
            "unit": source.unit,
            "sample_size": source.sample_size,
            "denominator": source.denominator,
            "upstream_source": source.source,
            "upstream_metadata": source.metadata,
        }
        details = source.description
        summary = f"{source.name}: {source.availability.value}."
        return (
            EvidenceReference(
                id=_evidence_id("interpretation", source.metric_id),
                source_type=SourceFamily.INTERPRETATION.value,
                summary=summary,
                locator=f"interpretation.evidence[{source.metric_id}]",
                observed_at=source.observed_at,
                details=details,
                metadata=metadata,
            ),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeEvidenceAdapter:
    """Normalize one existing Knowledge Engine :class:`EvidenceItem`."""

    name: str = "knowledge_evidence"
    priority: int = 80

    def supports(self, source: Any) -> bool:
        return isinstance(source, EvidenceItem)

    def collect(
        self,
        source: Any,
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        del context
        if not isinstance(source, EvidenceItem):
            raise TypeError("KnowledgeEvidenceAdapter requires EvidenceItem input.")
        metadata = {
            "source_family": SourceFamily.KNOWLEDGE.value,
            "knowledge_source_kind": source.source_kind.value,
            "knowledge_evidence_id": source.id,
            "upstream_metadata": source.metadata,
        }
        return (
            EvidenceReference(
                id=_evidence_id("knowledge", source.id),
                source_type=SourceFamily.KNOWLEDGE.value,
                summary=source.summary,
                locator=source.locator,
                sha256=source.sha256,
                observed_at=source.collected_at,
                details=source.details,
                metadata=metadata,
            ),
        )


@dataclass(frozen=True, slots=True)
class InterpretationFindingAdapter:
    """Normalize one complete deterministic interpretation finding."""

    name: str = "interpretation_finding"
    priority: int = 95

    def supports(self, source: Any) -> bool:
        return isinstance(source, InterpretationFinding)

    def collect(
        self,
        source: Any,
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        del context
        if not isinstance(source, InterpretationFinding):
            raise TypeError(
                "InterpretationFindingAdapter requires "
                "InterpretationFinding input."
            )
        validation_domain = _canonical_interpretation_domain(
            source.domain,
        )

        return (
            EvidenceReference(
                id=_evidence_id(
                    "interpretation_finding",
                    source.finding_id
                ),
                source_type=SourceFamily.INTERPRETATION.value,
                summary=source.title,
                locator=(
                    f"interpretation.findings[{source.finding_id}]"
                ),
                observed_at=source.created_at,
                details=source.observation,
                metadata={
                    "source_family": SourceFamily.INTERPRETATION.value,
                    "binding_kind": "interpretation_finding",
                    "binding_id": source.finding_id,
                    "rule_id": source.rule_id,
                    "domain": validation_domain.value,
                    "interpretation_domain": source.domain,
                    "status": source.status.value,
                    "severity": source.severity.value,
                    "confidence": source.confidence.value,
                    "evidence_strength": source.evidence_strength.value,
                    "interpretation": source.interpretation,
                    "impact": source.impact,
                    "limitations": source.limitations,
                    "tags": source.tags,
                    "confidence_score": source.confidence_score,
                    "clinically_relevant": source.clinically_relevant,
                    "blocks_research_use": source.blocks_research_use,
                    "referenced_metric_ids": tuple(
                        item.metric_id
                        for item in source.evidence
                    ),
                    "evidence_roles": {
                        item.metric_id: item.role.value
                        for item in source.evidence
                    },
                    "evidence_rationales": {
                        item.metric_id: item.rationale
                        for item in source.evidence
                        if item.rationale is not None
                    },
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class InvestigationCaseAdapter:
    """Normalize one existing Knowledge Engine investigation case."""

    name: str = "investigation_case"
    priority: int = 95

    def supports(self, source: Any) -> bool:
        return isinstance(source, InvestigationCase)

    def collect(
        self,
        source: Any,
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        del context
        if not isinstance(source, InvestigationCase):
            raise TypeError("InvestigationCaseAdapter requires InvestigationCase input.")
        root = EvidenceReference(
            id=_evidence_id("investigation_case", source.id),
            source_type=SourceFamily.KNOWLEDGE.value,
            summary=source.title,
            locator=f"knowledge.investigations[{source.id}]",
            observed_at=source.updated_at,
            metadata={
                "source_family": SourceFamily.KNOWLEDGE.value,
                "binding_kind": "investigation_case",
                "binding_id": source.id,
                "status": source.status.value,
                "selected_hypothesis_id": source.selected_hypothesis_id,
                "signal_ids": tuple(item.id for item in source.signals),
                "hypothesis_ids": tuple(item.id for item in source.hypotheses),
                "verification_ids": tuple(item.id for item in source.verifications),
                "opened_at": source.opened_at,
                "owner": source.owner,
                "notes": source.notes,
                "upstream_metadata": source.metadata,
            },
        )
        children = tuple(
            KnowledgeEvidenceAdapter().collect(item, context)[0]
            for item in source.evidence
        )
        return (root, *children)


@dataclass(frozen=True, slots=True)
class KnowledgeEntryAdapter:
    """Normalize one reusable Knowledge Engine entry and its evidence."""

    name: str = "knowledge_entry"
    priority: int = 95

    def supports(self, source: Any) -> bool:
        return isinstance(source, KnowledgeEntry)

    def collect(
        self,
        source: Any,
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        del context
        if not isinstance(source, KnowledgeEntry):
            raise TypeError("KnowledgeEntryAdapter requires KnowledgeEntry input.")
        root = EvidenceReference(
            id=_evidence_id("knowledge_entry", source.id),
            source_type=SourceFamily.KNOWLEDGE.value,
            summary=source.title,
            locator=f"knowledge.entries[{source.id}]",
            observed_at=source.updated_at,
            details=source.root_cause,
            metadata={
                "source_family": SourceFamily.KNOWLEDGE.value,
                "binding_kind": "knowledge_entry",
                "binding_id": source.id,
                "status": source.status.value,
                "category_id": source.category_id,
                "causal_certainty": source.causal_certainty.value,
                "detection_pattern": source.detection_pattern,
                "source_investigation_id": source.source_investigation_id,
                "source_hypothesis_id": source.source_hypothesis_id,
                "verification_ids": tuple(item.id for item in source.verifications),
                "applicability": source.applicability,
                "limitations": source.limitations,
                "supersedes": source.supersedes,
                "upstream_metadata": source.metadata,
            },
        )
        children = tuple(
            KnowledgeEvidenceAdapter().collect(item, context)[0]
            for item in source.evidence
        )
        return (root, *children)


@dataclass(frozen=True, slots=True)
class ExperimentResultAdapter:
    """Normalize the immutable Phase 2B experiment result without reading files."""

    name: str = "experiment_result"
    priority: int = 95

    def supports(self, source: Any) -> bool:
        return isinstance(source, ExperimentResult)

    def collect(
        self,
        source: Any,
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        if not isinstance(source, ExperimentResult):
            raise TypeError("ExperimentResultAdapter requires ExperimentResult input.")
        if (
            source.experiment_id != context.request.experiment_id
            or source.run_id != context.request.run_id
        ):
            raise RootCauseIntegrityError(
                "ExperimentResult identity does not match the root-cause request.",
                context={
                    "request_experiment_id": context.request.experiment_id,
                    "request_run_id": context.request.run_id,
                    "result_experiment_id": source.experiment_id,
                    "result_run_id": source.run_id,
                },
            )
        return (
            EvidenceReference(
                id=_evidence_id("experiment_result", f"{source.experiment_id}:{source.run_id}"),
                source_type=SourceFamily.ORCHESTRATION.value,
                summary="Canonical Phase 2B experiment execution result.",
                locator=f"orchestration.results[{source.experiment_id}:{source.run_id}]",
                observed_at=source.finished_at or source.started_at,
                metadata={
                    "source_family": SourceFamily.ORCHESTRATION.value,
                    "binding_kind": "experiment_result",
                    "binding_id": f"{source.experiment_id}:{source.run_id}",
                    "status": source.status.value,
                    "workspace": source.workspace,
                    "simulator_run_ids": tuple(item.id for item in source.simulator_runs),
                    "stage_result_ids": tuple(item.id for item in source.stage_results),
                    "artifact_ids": tuple(item.id for item in source.artifacts),
                    "duration_seconds": source.duration_seconds,
                    "error_message": source.error_message,
                    "upstream_metadata": source.metadata,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class MappingEvidenceAdapter:
    """Normalize explicit mapping descriptors and canonical manifest sections.

    General mappings are accepted only when they contain the required descriptor
    fields ``summary`` and ``locator``.  This prevents arbitrary dictionaries
    from being silently interpreted as scientific evidence.
    """

    name: str = "mapping_evidence"
    priority: int = 10

    def supports(self, source: Any) -> bool:
        if not isinstance(source, Mapping):
            return False
        return _looks_like_descriptor(source) or _looks_like_manifest(source)

    def collect(
        self,
        source: Any,
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        if not isinstance(source, Mapping):
            raise TypeError("MappingEvidenceAdapter requires a mapping input.")
        if _looks_like_manifest(source):
            return self._collect_manifest(source, context)
        return (self._collect_descriptor(source, context),)

    def _collect_descriptor(
        self,
        source: Mapping[str, Any],
        context: EvidenceCollectionContext,
    ) -> EvidenceReference:
        source_type = _coerce_source_type(source.get("source_type", SourceFamily.EXTERNAL.value))
        source_id = source.get("id")
        if source_id is None:
            source_id = _content_identifier(source_type, source)
        else:
            source_id = _require_identifier(source_id, "source['id']")

        artifact_id = _optional_identifier(source.get("artifact_id"), "source['artifact_id']")
        if artifact_id is not None and artifact_id not in context.artifact_catalog:
            raise RootCauseIntegrityError(
                "Evidence descriptor refers to an artefact absent from the collection context.",
                context={"source_id": source_id, "artifact_id": artifact_id},
            )

        declared_sha256 = _optional_sha256(source.get("sha256"), "source['sha256']")
        if artifact_id is not None:
            catalogued = context.artifact_catalog[artifact_id]
            if declared_sha256 is not None and declared_sha256 != catalogued.sha256:
                raise RootCauseIntegrityError(
                    "Evidence descriptor hash conflicts with the registered artefact hash.",
                    context={
                        "source_id": source_id,
                        "artifact_id": artifact_id,
                        "descriptor_sha256": declared_sha256,
                        "artifact_sha256": catalogued.sha256,
                    },
                )
            declared_sha256 = catalogued.sha256

        direction = source.get("direction", EvidenceDirection.NEUTRAL)
        if isinstance(direction, str):
            try:
                direction = EvidenceDirection(direction)
            except ValueError as exc:
                raise RootCauseInputError(
                    "Evidence descriptor contains an unsupported direction.",
                    context={"source_id": source_id, "direction": direction},
                ) from exc
        if direction is not EvidenceDirection.NEUTRAL:
            raise RootCauseInputError(
                "Evidence collection accepts only neutral observations; directional assessment "
                "belongs to candidate evaluation.",
                context={"source_id": source_id, "direction": direction.value},
            )

        metadata = dict(source.get("metadata") or {})
        metadata.setdefault("source_family", source_type)
        metadata.setdefault("collection_schema_version", _SCHEMA_VERSION)
        binding_kind = source.get("binding_kind")
        binding_id = source.get("binding_id")
        if (binding_kind is None) != (binding_id is None):
            raise RootCauseInputError(
                "Evidence descriptor binding_kind and binding_id must be provided together.",
                context={"source_id": source_id},
            )
        if binding_kind is not None:
            normalized_binding_kind = _coerce_binding_kind(
                binding_kind, "source['binding_kind']"
            )
            metadata["binding_kind"] = normalized_binding_kind.value
            metadata["binding_id"] = _require_identifier(
                binding_id, "source['binding_id']"
            )

        return EvidenceReference(
            id=_evidence_id(source_type, source_id),
            source_type=source_type,
            summary=_require_text(source["summary"], "source['summary']"),
            locator=_require_text(source["locator"], "source['locator']"),
            artifact_id=artifact_id,
            sha256=declared_sha256,
            observed_at=_optional_datetime(source.get("observed_at"), "source['observed_at']"),
            details=_optional_text(source.get("details"), "source['details']"),
            metadata=metadata,
        )

    def _collect_manifest(
        self,
        source: Mapping[str, Any],
        context: EvidenceCollectionContext,
    ) -> tuple[EvidenceReference, ...]:
        experiment_id = _require_identifier(source["experiment_id"], "manifest.experiment_id")
        run_id = _require_identifier(source["run_id"], "manifest.run_id")
        if experiment_id != context.request.experiment_id or run_id != context.request.run_id:
            raise RootCauseIntegrityError(
                "Manifest identity does not match the root-cause request.",
                context={
                    "request_experiment_id": context.request.experiment_id,
                    "request_run_id": context.request.run_id,
                    "manifest_experiment_id": experiment_id,
                    "manifest_run_id": run_id,
                },
            )

        generated_at = _parse_datetime(source.get("generated_at"), "manifest.generated_at")
        producer = source.get("producer")
        producer_name = None
        producer_version = None
        if isinstance(producer, Mapping):
            producer_name = producer.get("name")
            producer_version = producer.get("version")

        base_metadata = {
            "source_family": SourceFamily.MANIFEST.value,
            "schema_version": source.get("schema_version"),
            "producer_name": producer_name,
            "producer_version": producer_version,
            "experiment_id": experiment_id,
            "run_id": run_id,
            "config_sha256": source.get("config_sha256"),
        }
        root = EvidenceReference(
            id=_evidence_id("manifest", f"{experiment_id}:{run_id}"),
            source_type=SourceFamily.MANIFEST.value,
            summary="Canonical experiment manifest identity and integrity metadata.",
            locator="manifest:$",
            observed_at=generated_at,
            metadata=base_metadata,
        )

        references = [root]
        config = source.get("config")
        if isinstance(config, Mapping):
            references.append(
                EvidenceReference(
                    id=_evidence_id("manifest", f"{experiment_id}:{run_id}:config"),
                    source_type=SourceFamily.ORCHESTRATION.value,
                    summary="Experiment configuration recorded by the canonical manifest.",
                    locator="manifest:$.config",
                    observed_at=generated_at,
                    metadata={
                        **base_metadata,
                        "source_family": SourceFamily.ORCHESTRATION.value,
                        "payload": config,
                    },
                )
            )
        result = source.get("result")
        if isinstance(result, Mapping):
            references.append(
                EvidenceReference(
                    id=_evidence_id("manifest", f"{experiment_id}:{run_id}:result"),
                    source_type=SourceFamily.ORCHESTRATION.value,
                    summary="Experiment execution result recorded by the canonical manifest.",
                    locator="manifest:$.result",
                    observed_at=generated_at,
                    metadata={
                        **base_metadata,
                        "source_family": SourceFamily.ORCHESTRATION.value,
                        "payload": result,
                    },
                )
            )
        return tuple(references)


# =============================================================================
# Adapter registry
# =============================================================================


_DEFAULT_ADAPTERS: Final[tuple[EvidenceAdapter, ...]] = (
    ArtifactReferenceAdapter(),
    InterpretationFindingAdapter(),
    InterpretationEvidenceAdapter(),
    InvestigationCaseAdapter(),
    KnowledgeEntryAdapter(),
    KnowledgeEvidenceAdapter(),
    ExperimentResultAdapter(),
    MappingEvidenceAdapter(),
)


class EvidenceRegistry:
    """Deterministic registry of evidence adapters.

    Adapter resolution is based on descending priority and then stable adapter
    name.  Equal-priority ambiguity is rejected rather than relying on
    registration order.
    """

    __slots__ = ("_adapters",)

    def __init__(self, adapters: Iterable[EvidenceAdapter] = _DEFAULT_ADAPTERS) -> None:
        normalized: list[EvidenceAdapter] = []
        names: set[str] = set()
        for index, adapter in enumerate(adapters):
            if not isinstance(adapter, EvidenceAdapter):
                raise TypeError(f"adapters[{index}] does not satisfy EvidenceAdapter.")
            name = _require_identifier(adapter.name, f"adapters[{index}].name")
            if name in names:
                raise ValueError(f"Duplicate evidence adapter name: {name}.")
            if isinstance(adapter.priority, bool) or not isinstance(adapter.priority, int):
                raise TypeError(f"adapters[{index}].priority must be an integer.")
            names.add(name)
            normalized.append(adapter)
        self._adapters = tuple(sorted(normalized, key=lambda item: (-item.priority, item.name)))

    @property
    def adapters(self) -> tuple[EvidenceAdapter, ...]:
        return self._adapters

    def resolve(self, source: Any) -> EvidenceAdapter | None:
        matches = [adapter for adapter in self._adapters if adapter.supports(source)]
        if not matches:
            return None
        highest_priority = matches[0].priority
        highest = [adapter for adapter in matches if adapter.priority == highest_priority]
        if len(highest) > 1:
            raise RootCauseIntegrityError(
                "Multiple evidence adapters have equal priority for the same source.",
                context={
                    "source_type": type(source).__name__,
                    "adapter_names": [adapter.name for adapter in highest],
                    "priority": highest_priority,
                },
            )
        return highest[0]


# =============================================================================
# Collector
# =============================================================================


EvidenceSource: TypeAlias = Any


class EvidenceCollector:
    """Collect heterogeneous upstream evidence into one canonical collection."""

    __slots__ = ("_registry", "_artifact_verifier")

    def __init__(
        self,
        registry: EvidenceRegistry | None = None,
        *,
        artifact_verifier: ArtifactIntegrityVerifier | None = None,
    ) -> None:
        if registry is not None and not isinstance(registry, EvidenceRegistry):
            raise TypeError("registry must be an EvidenceRegistry or None.")
        if artifact_verifier is not None and not isinstance(
            artifact_verifier,
            ArtifactIntegrityVerifier,
        ):
            raise TypeError(
                "artifact_verifier must satisfy ArtifactIntegrityVerifier or be None."
            )
        self._registry = registry or EvidenceRegistry()
        self._artifact_verifier = artifact_verifier

    @property
    def registry(self) -> EvidenceRegistry:
        return self._registry

    def collect(
        self,
        sources: Iterable[EvidenceSource],
        *,
        context: EvidenceCollectionContext,
    ) -> EvidenceCollection:
        """Normalize all sources while enforcing request and artefact integrity."""

        if not isinstance(context, EvidenceCollectionContext):
            raise TypeError("context must be an EvidenceCollectionContext.")
        if isinstance(sources, (str, bytes, bytearray, Mapping)):
            raise TypeError("sources must be an iterable of source objects, not a scalar container.")

        diagnostics: list[CollectionDiagnostic] = []
        references: dict[str, EvidenceReference] = {}
        source_count = 0

        self._validate_requested_artifacts(context)
        self._verify_artifacts(context)

        try:
            iterator = iter(sources)
        except TypeError as exc:
            raise TypeError("sources must be iterable.") from exc

        for index, source in enumerate(iterator):
            source_count += 1
            adapter = self.registry.resolve(source)
            if adapter is None:
                self._handle_unsupported_source(
                    source,
                    index=index,
                    strict=bool(context.strict),
                    diagnostics=diagnostics,
                )
                continue
            try:
                normalized = adapter.collect(source, context)
                normalized = _normalize_model_tuple(
                    normalized,
                    EvidenceReference,
                    f"adapter[{adapter.name}].collect",
                )
                if not normalized:
                    raise RootCauseIntegrityError(
                        "Evidence adapter returned no references for a supported source.",
                        context={
                            "adapter": adapter.name,
                            "source_type": type(source).__name__,
                            "source_index": index,
                        },
                    )
                for reference in normalized:
                    self._register_reference(
                        reference,
                        references=references,
                        adapter_name=adapter.name,
                    )
            except (RootCauseInputError, RootCauseIntegrityError, EvidenceCollectionError):
                raise
            except (TypeError, ValueError, KeyError) as exc:
                if context.strict:
                    raise EvidenceCollectionError(
                        (
                            "An evidence adapter could not normalize its source safely."
                            f"adapter={adapter.name!r}, "
                            f"source_type={type(source).__name__!r}, "
                            f"source_index={index}, "
                            f"error_type={type(exc).__name__!r}, "
                            f"error={str(exc)!r}."
                        ),
                        context={
                            "adapter": adapter.name,
                            "source_type": type(source).__name__,
                            "source_index": index,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    ) from exc
                diagnostics.append(
                    CollectionDiagnostic(
                        code="evidence.adapter_failed",
                        message="Evidence source was skipped because normalization failed.",
                        source_type=type(source).__name__,
                        metadata={
                            "adapter": adapter.name,
                            "source_index": index,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive plugin boundary
                raise EvidenceCollectionError(
                    (
                        "Unexpected failure while collecting evidence through an adapter: "
                        f"adapter={adapter.name!r}, "
                        f"source_type={type(source).__name__!r}, "
                        f"source_index={index}, "
                        f"error_type={type(exc).__name__!r}, "
                        f"error={str(exc)!r}."
                    ),
                    context={
                        "adapter": adapter.name,
                        "source_type": type(source).__name__,
                        "source_index": index,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                },
            ) from exc

        if source_count == 0:
            diagnostics.append(
                CollectionDiagnostic(
                    code="evidence.no_sources",
                    message="No evidence sources were supplied for collection.",
                    severity=CollectionSeverity.INFO,
                )
            )

        self._validate_requested_bindings(context, references.values())

        metadata = {
            "experiment_id": context.request.experiment_id,
            "run_id": context.request.run_id,
            "strict": context.strict,
            "source_count": source_count,
            "evidence_count": len(references),
            "artifact_count": len(context.artifacts),
            "collection_context": context.metadata,
        }
        return EvidenceCollection(
            request_id=context.request.id,
            evidence=tuple(references.values()),
            artifacts=context.artifacts,
            diagnostics=tuple(diagnostics),
            collected_at=context.collected_at,
            metadata=metadata,
        )

    @staticmethod
    def _validate_requested_bindings(
        context: EvidenceCollectionContext,
        references: Iterable[EvidenceReference],
    ) -> None:
        observed: dict[str, set[str]] = {}
        for reference in references:
            kind = reference.metadata.get("binding_kind")
            identifier = reference.metadata.get("binding_id")
            if kind is None and identifier is None:
                continue
            if not isinstance(kind, str) or not isinstance(identifier, str):
                raise RootCauseIntegrityError(
                    "Collected evidence contains an invalid upstream binding.",
                    context={"evidence_id": reference.id},
                )
            try:
                normalized_kind = UpstreamBindingKind(kind)
            except ValueError as exc:
                raise RootCauseIntegrityError(
                    "Collected evidence contains an unsupported upstream binding kind.",
                    context={"evidence_id": reference.id, "binding_kind": kind},
                ) from exc
            observed.setdefault(normalized_kind.value, set()).add(identifier)

        required = {
            UpstreamBindingKind.VALIDATION_RESULT.value: set(
                context.request.validation_result_ids
            ),
            UpstreamBindingKind.INTERPRETATION_FINDING.value: set(
                context.request.interpretation_finding_ids
            ),
            UpstreamBindingKind.INVESTIGATION_CASE.value: set(
                context.request.investigation_case_ids
            ),
            UpstreamBindingKind.KNOWLEDGE_ENTRY.value: set(
                context.request.knowledge_entry_ids
            ),
        }
        missing = {
            kind: sorted(identifiers - observed.get(kind, set()))
            for kind, identifiers in required.items()
            if identifiers - observed.get(kind, set())
        }
        if missing:
            raise EvidenceCollectionError(
                "Required upstream objects declared by RootCauseRequest were not collected.",
                context={
                    "request_id": context.request.id,
                    "missing_bindings": missing,
                    "observed_bindings": {
                        kind: sorted(identifiers) for kind, identifiers in observed.items()
                    },
                },
            )

        unexpected = {
            kind: sorted(observed.get(kind, set()) - identifiers)
            for kind, identifiers in required.items()
            if observed.get(kind, set()) - identifiers
        }
        if unexpected:
            raise RootCauseIntegrityError(
                "Collected evidence contains request-bound objects from another investigation.",
                context={
                    "request_id": context.request.id,
                    "unexpected_bindings": unexpected,
                },
            )

    def _validate_requested_artifacts(self, context: EvidenceCollectionContext) -> None:
        requested = set(context.request.artifact_ids)
        available = set(context.artifact_catalog)
        missing = sorted(requested - available)
        if missing:
            raise EvidenceCollectionError(
                "Required artefacts declared by RootCauseRequest are unavailable.",
                context={
                    "request_id": context.request.id,
                    "missing_artifact_ids": missing,
                    "available_artifact_ids": sorted(available),
                },
            )

    def _verify_artifacts(self, context: EvidenceCollectionContext) -> None:
        if self._artifact_verifier is None:
            return
        for artifact in context.artifacts:
            try:
                valid = self._artifact_verifier.verify(artifact)
            except Exception as exc:  # pragma: no cover - injected collaborator boundary
                raise EvidenceCollectionError(
                    "Injected artefact integrity verifier failed.",
                    context={
                        "artifact_id": artifact.id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                ) from exc
            if not isinstance(valid, bool):
                raise RootCauseIntegrityError(
                    "Artefact integrity verifier returned a non-boolean result.",
                    context={
                        "artifact_id": artifact.id,
                        "result_type": type(valid).__name__,
                    },
                )
            if not valid:
                raise RootCauseIntegrityError(
                    "Artefact integrity verification failed.",
                    context={
                        "artifact_id": artifact.id,
                        "declared_sha256": artifact.sha256,
                    },
                )

    @staticmethod
    def _handle_unsupported_source(
        source: Any,
        *,
        index: int,
        strict: bool,
        diagnostics: list[CollectionDiagnostic],
    ) -> None:
        if strict:
            raise EvidenceCollectionError(
                "No registered adapter can normalize an evidence source.",
                context={
                    "source_index": index,
                    "source_type": type(source).__name__,
                },
            )
        diagnostics.append(
            CollectionDiagnostic(
                code="evidence.unsupported_source",
                message="Unsupported evidence source was skipped.",
                source_type=_safe_identifier(type(source).__name__),
                metadata={"source_index": index},
            )
        )

    @staticmethod
    def _register_reference(
        reference: EvidenceReference,
        *,
        references: dict[str, EvidenceReference],
        adapter_name: str,
    ) -> None:
        if reference.direction is not EvidenceDirection.NEUTRAL:
            raise RootCauseIntegrityError(
                "Evidence adapters must emit neutral evidence only.",
                context={
                    "adapter": adapter_name,
                    "evidence_id": reference.id,
                    "direction": reference.direction.value,
                },
            )
        existing = references.get(reference.id)
        if existing is None:
            references[reference.id] = reference
            return
        if existing != reference:
            raise RootCauseIntegrityError(
                "Conflicting evidence references share the same stable identifier.",
                context={
                    "adapter": adapter_name,
                    "evidence_id": reference.id,
                    "existing_fingerprint": _fingerprint(existing),
                    "incoming_fingerprint": _fingerprint(reference),
                },
            )


def collect_evidence(
    request: RootCauseRequest,
    sources: Iterable[EvidenceSource],
    *,
    artifacts: Sequence[ArtifactReference] = (),
    registry: EvidenceRegistry | None = None,
    artifact_verifier: ArtifactIntegrityVerifier | None = None,
    collected_at: datetime | None = None,
    strict: bool | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> EvidenceCollection:
    """Convenience façade for one-shot deterministic evidence collection."""

    context = EvidenceCollectionContext(
        request=request,
        artifacts=tuple(artifacts),
        collected_at=collected_at or datetime.now(UTC),
        strict=strict,
        metadata=metadata or {},
    )
    return EvidenceCollector(
        registry=registry,
        artifact_verifier=artifact_verifier,
    ).collect(sources, context=context)


# =============================================================================
# Internal normalization helpers
# =============================================================================


def _coerce_binding_kind(value: Any, field_name: str) -> UpstreamBindingKind:
    if isinstance(value, UpstreamBindingKind):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or UpstreamBindingKind.")
    try:
        return UpstreamBindingKind(value.strip())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in UpstreamBindingKind)
        raise RootCauseInputError(
            f"{field_name} is unsupported; expected one of: {allowed}.",
            context={"field": field_name, "value": value},
        ) from exc


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _optional_text(value: Any, field_name: str) -> str | None:
    return None if value is None else _require_text(value, field_name)


def _require_identifier(value: Any, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, '.', '_', ':', or '-'."
        )
    return normalized


def _optional_identifier(value: Any, field_name: str) -> str | None:
    return None if value is None else _require_identifier(value, field_name)


def _safe_identifier(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value)
    cleaned = cleaned.strip("_") or "unknown"
    if not cleaned[0].isalnum():
        cleaned = f"source_{cleaned}"
    return cleaned


def _optional_sha256(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = _require_text(value, field_name).lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must contain exactly 64 hexadecimal characters.")
    return normalized


def _normalize_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _optional_datetime(value: Any, field_name: str) -> datetime | None:
    return None if value is None else _normalize_datetime(value, field_name)


def _parse_datetime(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _normalize_datetime(value, field_name)
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 string, datetime, or None.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO-8601 datetime.") from exc
    return _normalize_datetime(parsed, field_name)


def _normalize_model_tuple(
    values: Any,
    model_type: type[Any],
    field_name: str,
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {model_type.__name__} objects.")
    normalized = tuple(values)
    for index, value in enumerate(normalized):
        if not isinstance(value, model_type):
            raise TypeError(
                f"{field_name}[{index}] must be a {model_type.__name__}, "
                f"got {type(value).__name__}."
            )
    return normalized


def _require_unique(
    values: Sequence[Any],
    *,
    key: Any,
    field_name: str,
) -> None:
    seen: set[Any] = set()
    duplicates: list[Any] = []
    for value in values:
        identifier = key(value)
        if identifier in seen:
            duplicates.append(identifier)
        seen.add(identifier)
    if duplicates:
        raise ValueError(
            f"{field_name} must not contain duplicate identifiers: "
            + ", ".join(str(item) for item in sorted(set(duplicates)))
        )


def _deep_freeze(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError(f"{path} must not contain NaN or infinity.")
        return value
    if isinstance(value, Enum):
        return _deep_freeze(value.value, path=path)
    if isinstance(value, datetime):
        return _normalize_datetime(value, path)
    if isinstance(value, date):
        return value
    if isinstance(value, PurePath):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return MappingProxyType(
            {
                item.name: _deep_freeze(
                    getattr(value, item.name),
                    path=f"{path}.{item.name}",
                )
                for item in fields(value)
            }
        )
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} mapping keys must be strings.")
            normalized[key] = _deep_freeze(item, path=f"{path}.{key}")
        return MappingProxyType(normalized)
    if isinstance(value, (set, frozenset)):
        normalized = [_deep_freeze(item, path=f"{path}[]") for item in value]
        return tuple(sorted(normalized, key=_canonical_sort_key))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(
            _deep_freeze(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}.")


def _freeze_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized = _deep_freeze(value, path=field_name)
    if not isinstance(normalized, Mapping):  # defensive invariant
        raise TypeError(f"{field_name} must normalize to a mapping.")
    return normalized


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("Canonical values must not contain NaN or infinity.")
        return value
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, datetime):
        return _normalize_datetime(value, "datetime").isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, PurePath):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _canonical_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        for candidate_id, result in self.attribution_results.items():
            metadata_candidate_id = result.metadata.get("candidate_id")
        if (
            metadata_candidate_id is not None
            and metadata_candidate_id != candidate_id
        ):
            raise ValueError(
                "attribution_results keys must match "
                "AttributionResult.metadata['candidate_id'] when present."
            )
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (set, frozenset)):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=_canonical_sort_key)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"Unsupported canonical value type: {type(value).__name__}.")


def _canonical_sort_key(value: Any) -> str:
    return dumps(
        _canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _fingerprint(value: Any) -> str:
    serialized = dumps(
        _canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def _content_identifier(namespace: str, value: Any) -> str:
    return f"{namespace}:{_fingerprint(value)[:24]}"


def _evidence_id(namespace: str, source_id: str) -> str:
    normalized_namespace = _safe_identifier(namespace).lower()
    normalized_source = _require_identifier(source_id, "source_id")
    identifier = f"{_SYNTHETIC_ID_PREFIX}:{normalized_namespace}:{normalized_source}"
    return _require_identifier(identifier, "evidence_id")


def _coerce_source_type(value: Any) -> str:
    if isinstance(value, SourceFamily):
        return value.value
    return _require_identifier(value, "source_type")


def _looks_like_descriptor(source: Mapping[str, Any]) -> bool:
    return "summary" in source and "locator" in source


def _looks_like_manifest(source: Mapping[str, Any]) -> bool:
    required = {"schema_version", "experiment_id", "run_id", "config", "result"}
    return required.issubset(source)