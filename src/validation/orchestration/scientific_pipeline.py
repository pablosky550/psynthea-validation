"""Canonical composition of the scientific orchestration stages.

This module owns the dependency wiring between scientific interpretation and
root-cause analysis. It guarantees that both handlers share the same
run-scoped ``ScientificStageProductStore`` and prevents composition code from
constructing incompatible stores or static providers independently.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from validation.interpretation import (
    InterpretationWorkflow,
)
from validation.orchestration.adapters.root_cause import (
    RootCauseRequestAdapter,
)
from validation.orchestration.stage_products import (
    ScientificStageProductStore,
)
from validation.orchestration.stages.knowledge import (
    InterpretationWorkflowFactory,
    KnowledgeStageHandler,
)
from validation.orchestration.stages.root_cause import (
    RootCauseStageHandler,
)
from validation.orchestration.stages.root_cause_input import (
    StoredRootCauseStageInputProvider,
)
from validation.root_cause.engine import RootCauseEngine
from validation.root_cause.evidence import EvidenceSource
from validation.root_cause.report import ReportConfiguration

__all__ = [
    "ScientificPipeline",
    "build_scientific_pipeline",
]


@dataclass(frozen=True, slots=True)
class ScientificPipeline:
    """Fully wired Knowledge -> Root Cause orchestration slice."""

    product_store: ScientificStageProductStore
    knowledge_handler: KnowledgeStageHandler
    root_cause_handler: RootCauseStageHandler

    def __post_init__(self) -> None:
        if not isinstance(
            self.product_store,
            ScientificStageProductStore,
        ):
            raise TypeError(
                "product_store must be a ScientificStageProductStore."
            )
        if not isinstance(
            self.knowledge_handler,
            KnowledgeStageHandler,
        ):
            raise TypeError(
                "knowledge_handler must be a KnowledgeStageHandler."
            )
        if not isinstance(
            self.root_cause_handler,
            RootCauseStageHandler,
        ):
            raise TypeError(
                "root_cause_handler must be a RootCauseStageHandler."
            )

        if self.knowledge_handler.product_store is not self.product_store:
            raise ValueError(
                "knowledge_handler must publish to product_store."
            )

        provider = self.root_cause_handler.input_provider
        if not isinstance(
            provider,
            StoredRootCauseStageInputProvider,
        ):
            raise ValueError(
                "root_cause_handler must use "
                "StoredRootCauseStageInputProvider."
            )
        if provider.product_store is not self.product_store:
            raise ValueError(
                "root_cause_handler must consume from product_store."
            )

    @property
    def handlers(
        self,
    ) -> tuple[
        KnowledgeStageHandler,
        RootCauseStageHandler,
    ]:
        """Return handlers in their mandatory execution order."""

        return (
            self.knowledge_handler,
            self.root_cause_handler,
        )

    def clear_run(self, run_id: str) -> None:
        """Release all in-memory scientific products for one run."""

        self.product_store.clear_run(run_id)


def build_scientific_pipeline(
    *,
    module_name: str,
    evidence_sources: Sequence[EvidenceSource] = (),
    product_store: ScientificStageProductStore | None = None,
    workflow_factory: InterpretationWorkflowFactory = (
        InterpretationWorkflow
    ),
    knowledge_clock: Callable[[], datetime] = (
        lambda: datetime.now(UTC)
    ),
    root_cause_engine: RootCauseEngine | None = None,
    request_adapter: RootCauseRequestAdapter | None = None,
    report_configuration: ReportConfiguration | None = None,
    root_cause_clock: Callable[[], datetime] = (
        lambda: datetime.now(UTC)
    ),
    provider_metadata: Mapping[str, Any] | None = None,
) -> ScientificPipeline:
    """Build the canonical scientific stage composition.

    ``module_name`` is explicit by design. Root-cause analysis is a
    module-scoped investigation, while the Knowledge stage may publish more
    than one interpretation during the same orchestration run.
    """

    normalized_module_name = _require_text(
        module_name,
        "module_name",
    )

    if isinstance(
        evidence_sources,
        (str, bytes),
    ) or not isinstance(
        evidence_sources,
        Sequence,
    ):
        raise TypeError(
            "evidence_sources must be a sequence of EvidenceSource values."
        )

    normalized_evidence = tuple(evidence_sources)
    for index, source in enumerate(normalized_evidence):
        if not isinstance(source, EvidenceSource):
            raise TypeError(
                f"evidence_sources[{index}] must be an EvidenceSource."
            )

    store = (
        ScientificStageProductStore()
        if product_store is None
        else product_store
    )
    if not isinstance(store, ScientificStageProductStore):
        raise TypeError(
            "product_store must be a ScientificStageProductStore or None."
        )

    if provider_metadata is None:
        metadata: Mapping[str, Any] = MappingProxyType({})
    elif not isinstance(provider_metadata, Mapping):
        raise TypeError("provider_metadata must be a mapping or None.")
    else:
        metadata = MappingProxyType(dict(provider_metadata))

    knowledge_handler = KnowledgeStageHandler(
        workflow_factory=workflow_factory,
        clock=knowledge_clock,
        product_store=store,
    )

    input_provider = StoredRootCauseStageInputProvider(
        product_store=store,
        module_name=normalized_module_name,
        evidence_sources=normalized_evidence,
        metadata=metadata,
    )

    root_cause_handler = RootCauseStageHandler(
        input_provider=input_provider,
        engine=(
            RootCauseEngine()
            if root_cause_engine is None
            else root_cause_engine
        ),
        request_adapter=(
            RootCauseRequestAdapter()
            if request_adapter is None
            else request_adapter
        ),
        report_configuration=(
            ReportConfiguration()
            if report_configuration is None
            else report_configuration
        ),
        clock=root_cause_clock,
    )

    return ScientificPipeline(
        product_store=store,
        knowledge_handler=knowledge_handler,
        root_cause_handler=root_cause_handler,
    )


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized