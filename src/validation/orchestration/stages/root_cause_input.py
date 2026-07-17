"""Typed in-memory provider for the root-cause orchestration stage.

The provider converts already-computed scientific domain objects plus the current
``OrchestrationContext`` into the two canonical inputs required by
``RootCauseStageHandler``. It performs no file deserialization and no causal
inference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from validation.interpretation.workflow import InterpretationWorkflowResult
from validation.knowledge.models import InvestigationCase, KnowledgeEntry
from validation.knowledge.protocols import (
    CANONICAL_PROTOCOLS,
    InvestigationProtocol,
    ProtocolCatalog,
)
from validation.knowledge.registry import KnowledgeRegistry
from validation.knowledge.taxonomy import ValidationDomain
from validation.orchestration.adapters.root_cause import RootCauseRequestSource
from validation.orchestration.models import ExecutionStatus, ExperimentResult
from validation.orchestration.orchestrator import OrchestrationContext
from validation.orchestration.stage_products import ScientificStageProductStore
from validation.orchestration.stages.root_cause import RootCauseStagePayload
from validation.root_cause.engine import EngineInputs
from validation.root_cause.evidence import EvidenceSource


@dataclass(frozen=True, slots=True)
class InMemoryRootCauseStageInputProvider:
    """Build root-cause stage inputs from immutable upstream domain objects."""

    interpretation: InterpretationWorkflowResult
    evidence_sources: tuple[EvidenceSource, ...]
    investigation_cases: tuple[InvestigationCase, ...] = ()
    knowledge_entries: tuple[KnowledgeEntry, ...] = ()
    requested_domains: tuple[ValidationDomain, ...] = ()
    artifacts_from_context: bool = True
    knowledge_registry: KnowledgeRegistry | None = None
    protocol_catalog: ProtocolCatalog | None = CANONICAL_PROTOCOLS
    protocols: tuple[InvestigationProtocol, ...] = ()
    max_candidates: int = 20
    execute_verifications: bool = True
    strict_integrity: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.interpretation, InterpretationWorkflowResult):
            raise TypeError(
                "interpretation must be an InterpretationWorkflowResult."
            )

        if isinstance(self.evidence_sources, (str, bytes)) or not isinstance(
            self.evidence_sources,
            Sequence,
        ):
            raise TypeError("evidence_sources must be a sequence.")
        object.__setattr__(self, "evidence_sources", tuple(self.evidence_sources))
        if isinstance(self.evidence_sources, (str, bytes)) or not isinstance(
            self.evidence_sources,
            Sequence,
        ):
            raise TypeError("evidence_sources must be a sequence.")
        object.__setattr__(self, "evidence_sources", tuple(self.evidence_sources))
        object.__setattr__(
            self,
            "investigation_cases",
            _typed_tuple(
                self.investigation_cases,
                InvestigationCase,
                "investigation_cases",
            ),
        )
        object.__setattr__(
            self,
            "knowledge_entries",
            _typed_tuple(self.knowledge_entries, KnowledgeEntry, "knowledge_entries"),
        )
        object.__setattr__(
            self,
            "requested_domains",
            _typed_tuple(
                self.requested_domains,
                ValidationDomain,
                "requested_domains",
            ),
        )
        object.__setattr__(
            self,
            "protocols",
            _typed_tuple(self.protocols, InvestigationProtocol, "protocols"),
        )

        if not isinstance(self.artifacts_from_context, bool):
            raise TypeError("artifacts_from_context must be a bool.")
        if self.knowledge_registry is not None and not isinstance(
            self.knowledge_registry,
            KnowledgeRegistry,
        ):
            raise TypeError(
                "knowledge_registry must be a KnowledgeRegistry or None."
            )
        if self.protocol_catalog is not None and not isinstance(
            self.protocol_catalog,
            ProtocolCatalog,
        ):
            raise TypeError("protocol_catalog must be a ProtocolCatalog or None.")
        if isinstance(self.max_candidates, bool) or not isinstance(
            self.max_candidates,
            int,
        ):
            raise TypeError("max_candidates must be an integer.")
        if self.max_candidates <= 0:
            raise ValueError("max_candidates must be greater than zero.")
        if not isinstance(self.execute_verifications, bool):
            raise TypeError("execute_verifications must be a bool.")
        if not isinstance(self.strict_integrity, bool):
            raise TypeError("strict_integrity must be a bool.")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def load(self, context: OrchestrationContext) -> RootCauseStagePayload:
        """Create a validated payload for the current orchestration snapshot."""

        if not isinstance(context, OrchestrationContext):
            raise TypeError("context must be an OrchestrationContext.")

        report = self.interpretation.execution.report
        if report.pipeline_run_id != context.run_id:
            raise ValueError(
                "Interpretation pipeline_run_id does not match context.run_id."
            )

        experiment = ExperimentResult(
            experiment_id=context.config.id,
            run_id=context.run_id,
            status=ExecutionStatus.RUNNING,
            config=context.config,
            workspace=context.workspace.root,
            simulator_runs=context.simulator_runs,
            stage_results=context.stage_results,
            artifacts=context.artifacts,
            started_at=_experiment_started_at(context),
            metadata={
                "snapshot_stage": "root_cause_analysis",
                **dict(self.metadata),
            },
        )

        artifacts = context.artifacts if self.artifacts_from_context else ()

        validation_artifacts = tuple(
            artifact
            for artifact in context.artifacts
            if artifact.kind.value == "validation_result"
        )

        validation_evidence_sources: tuple[EvidenceSource, ...] = tuple(
            {
                "id": artifact.id,
                "source_type": "validation",
                "summary": (
                    "Canonical validation result produced by the validation stage."
                ),
                "locator": f"orchestration.artifacts[{artifact.id}]",
                "binding_kind": "validation_result",
                "binding_id": artifact.id,
                "artifact_id": artifact.id,
                "sha256": artifact.sha256,
                "observed_at": artifact.created_at,
                "metadata": {
                    "artifact_kind": artifact.kind.value,
                    "media_type": artifact.media_type,
                    "producer": artifact.producer,
                    "path": str(artifact.path),
                },
            }
            for artifact in validation_artifacts
        )

        interpretation_findings: tuple[EvidenceSource, ...] = tuple(report.findings)

        investigation_evidence_sources: tuple[EvidenceSource, ...] = tuple(
            self.investigation_cases
        )
        knowledge_evidence_sources: tuple[EvidenceSource, ...] = tuple(
            self.knowledge_entries
        )

        evidence_sources = (
            tuple(self.evidence_sources)
            + validation_evidence_sources
            + interpretation_findings
            + investigation_evidence_sources
            + knowledge_evidence_sources
        )

        request_source = RootCauseRequestSource(
            experiment_result=experiment,
            interpretation_report=report,
            investigation_cases=self.investigation_cases,
            knowledge_entries=self.knowledge_entries,
            requested_domains=self.requested_domains,
            max_candidates=self.max_candidates,
            execute_verifications=self.execute_verifications,
            strict_integrity=self.strict_integrity,
            metadata={
                "interpretation_workflow_fingerprint": (
                    self.interpretation.workflow_fingerprint
                ),
                "evidence_catalog_fingerprint": (
                    self.interpretation.evidence_catalog_fingerprint
                ),
                **dict(self.metadata),
            },
        )

        engine_inputs = EngineInputs(
            evidence_sources=evidence_sources,
            artifacts=artifacts,
            knowledge_registry=self.knowledge_registry,
            knowledge_entries=self.knowledge_entries,
            investigations=self.investigation_cases,
            protocol_catalog=self.protocol_catalog,
            protocols=self.protocols,
            metadata={
                "experiment_id": context.config.id,
                "orchestrator_run_id": context.run_id,
                "interpretation_report_id": report.report_id,
                "validation_evidence_source_count": len(
                    validation_evidence_sources
                ),
                "interpretation_finding_source_count": len(
                    interpretation_findings
                ),
                "investigation_source_count": len(
                    investigation_evidence_sources
                ),
                "knowledge_entry_source_count": len(
                    knowledge_evidence_sources
                ),
                "explicit_evidence_source_count": len(self.evidence_sources),
                **dict(self.metadata),
            },
        )

        return RootCauseStagePayload(
            request_source=request_source,
            engine_inputs=engine_inputs,
        )


@dataclass(frozen=True, slots=True)
class StoredRootCauseStageInputProvider:
    """Resolve the Knowledge-stage product produced in the current run."""

    product_store: ScientificStageProductStore
    module_name: str | None = None
    evidence_sources: tuple[EvidenceSource, ...] = ()
    investigation_cases: tuple[InvestigationCase, ...] = ()
    knowledge_entries: tuple[KnowledgeEntry, ...] = ()
    requested_domains: tuple[ValidationDomain, ...] = ()
    artifacts_from_context: bool = True
    knowledge_registry: KnowledgeRegistry | None = None
    protocol_catalog: ProtocolCatalog | None = CANONICAL_PROTOCOLS
    protocols: tuple[InvestigationProtocol, ...] = ()
    max_candidates: int = 20
    execute_verifications: bool = True
    strict_integrity: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.product_store, ScientificStageProductStore):
            raise TypeError(
                "product_store must be a ScientificStageProductStore."
            )
        if self.module_name is not None:
            normalized = self.module_name.strip()
            if not normalized:
                raise ValueError("module_name must not be empty.")
            object.__setattr__(self, "module_name", normalized)

        object.__setattr__(
            self,
            "investigation_cases",
            _typed_tuple(
                self.investigation_cases,
                InvestigationCase,
                "investigation_cases",
            ),
        )
        object.__setattr__(
            self,
            "knowledge_entries",
            _typed_tuple(
                self.knowledge_entries,
                KnowledgeEntry,
                "knowledge_entries",
            ),
        )
        object.__setattr__(
            self,
            "requested_domains",
            _typed_tuple(
                self.requested_domains,
                ValidationDomain,
                "requested_domains",
            ),
        )
        object.__setattr__(
            self,
            "protocols",
            _typed_tuple(
                self.protocols,
                InvestigationProtocol,
                "protocols",
            ),
        )
        if not isinstance(self.artifacts_from_context, bool):
            raise TypeError("artifacts_from_context must be a bool.")
        if self.knowledge_registry is not None and not isinstance(
            self.knowledge_registry, KnowledgeRegistry
        ):
            raise TypeError(
                "knowledge_registry must be a KnowledgeRegistry or None."
            )
        if self.protocol_catalog is not None and not isinstance(
            self.protocol_catalog, ProtocolCatalog
        ):
            raise TypeError("protocol_catalog must be a ProtocolCatalog or None.")
        if isinstance(self.max_candidates, bool) or not isinstance(
            self.max_candidates, int
        ):
            raise TypeError("max_candidates must be an integer.")
        if self.max_candidates <= 0:
            raise ValueError("max_candidates must be greater than zero.")
        if not isinstance(self.execute_verifications, bool):
            raise TypeError("execute_verifications must be a bool.")
        if not isinstance(self.strict_integrity, bool):
            raise TypeError("strict_integrity must be a bool.")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def load(self, context: OrchestrationContext) -> RootCauseStagePayload:
        if not isinstance(context, OrchestrationContext):
            raise TypeError("context must be an OrchestrationContext.")

        interpretation = self.product_store.interpretation(
            run_id=context.run_id,
            module_name=self.module_name,
        )
        return InMemoryRootCauseStageInputProvider(
            interpretation=interpretation,
            evidence_sources=self.evidence_sources,
            investigation_cases=self.investigation_cases,
            knowledge_entries=self.knowledge_entries,
            requested_domains=self.requested_domains,
            artifacts_from_context=self.artifacts_from_context,
            knowledge_registry=self.knowledge_registry,
            protocol_catalog=self.protocol_catalog,
            protocols=self.protocols,
            max_candidates=self.max_candidates,
            execute_verifications=self.execute_verifications,
            strict_integrity=self.strict_integrity,
            metadata=self.metadata,
        ).load(context)


def _experiment_started_at(context: OrchestrationContext) -> datetime:
    timestamps = tuple(
        item.started_at
        for item in (*context.simulator_runs, *context.stage_results)
        if item.started_at is not None
    )
    if not timestamps:
        raise ValueError(
            "Root-cause input construction requires at least one upstream "
            "started_at timestamp."
        )
    return min(timestamps).astimezone(UTC)


def _typed_tuple(
    values: Sequence[Any],
    expected_type: type[Any],
    field_name: str,
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(
            f"{field_name} must be a sequence of {expected_type.__name__} values."
        )
    result = tuple(values)
    for index, value in enumerate(result):
        if not isinstance(value, expected_type):
            raise TypeError(
                f"{field_name}[{index}] must be {expected_type.__name__}."
            )
    return result