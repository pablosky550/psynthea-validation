"""Production composition for the complete validation experiment pipeline.

This module is the only place where concrete stage implementations are
instantiated for application use.  Tests and alternative front-ends may still
inject explicit handlers through :func:`build_experiment_orchestrator`, while
CLI and service entry points use :func:`build_production_orchestrator`.

Concrete stage imports are deliberately deferred until construction time.  This
keeps package import side effects minimal and allows composition tests to replace
factories without importing optional reporting dependencies.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Final

from validation.interpretation import InterpretationWorkflow
from validation.orchestration.adapters.root_cause import RootCauseRequestAdapter
from validation.orchestration.composition import (
    ScientificExperimentOrchestrator,
    build_experiment_orchestrator,
)
from validation.orchestration.manifest import ExperimentManifest
from validation.orchestration.orchestrator import (
    ManifestWriter,
    OrchestrationPolicy,
    RunnerAdapter,
    StageHandler,
)
from validation.orchestration.runners import runner_for
from validation.orchestration.scientific_pipeline import build_scientific_pipeline
from validation.orchestration.stage_products import ScientificStageProductStore
from validation.orchestration.stages.knowledge import InterpretationWorkflowFactory
from validation.orchestration.workspace import ExperimentWorkspace
from validation.root_cause.engine import RootCauseEngine
from validation.root_cause.evidence import EvidenceSource
from validation.root_cause.report import ReportConfiguration

__all__ = [
    "build_production_orchestrator",
]

_ORCHESTRATOR_VERSION: Final = "1.0.0"


def build_production_orchestrator(
    *,
    module_name: str,
    evidence_sources: Sequence[EvidenceSource] = (),
    product_store: ScientificStageProductStore | None = None,
    workflow_factory: InterpretationWorkflowFactory = InterpretationWorkflow,
    knowledge_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    root_cause_engine: RootCauseEngine | None = None,
    request_adapter: RootCauseRequestAdapter | None = None,
    report_configuration: ReportConfiguration | None = None,
    root_cause_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    provider_metadata: Mapping[str, Any] | None = None,
    policy: OrchestrationPolicy | None = None,
    orchestrator_version: str = _ORCHESTRATOR_VERSION,
    runner_factory: Callable[[Any], RunnerAdapter] = runner_for,
    workspace_factory: Callable[..., ExperimentWorkspace] = (
        ExperimentWorkspace.create
    ),
    manifest_factory: Callable[..., ManifestWriter] = ExperimentManifest,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic_clock: Callable[[], float] = monotonic,
) -> ScientificExperimentOrchestrator:
    """Build the application-ready orchestrator with concrete stage handlers.

    ``module_name`` remains explicit because root-cause analysis is currently
    module-scoped.  The remaining handlers are the canonical production
    implementations developed in the preceding orchestration blocks.
    """

    scientific_pipeline = build_scientific_pipeline(
        module_name=module_name,
        evidence_sources=evidence_sources,
        product_store=product_store,
        workflow_factory=workflow_factory,
        knowledge_clock=knowledge_clock,
        root_cause_engine=root_cause_engine,
        request_adapter=request_adapter,
        report_configuration=report_configuration,
        root_cause_clock=root_cause_clock,
        provider_metadata=provider_metadata,
    )

    orchestrator = build_experiment_orchestrator(
        cohort_loading_handler=_cohort_loading_handler(),
        cohort_normalization_handler=_cohort_normalization_handler(),
        validation_handler=_validation_handler(),
        scientific_pipeline=scientific_pipeline,
        report_generation_handler=_report_generation_handler(),
        policy=policy,
        orchestrator_version=orchestrator_version,
        runner_factory=runner_factory,
        workspace_factory=workspace_factory,
        manifest_factory=manifest_factory,
        clock=clock,
        monotonic_clock=monotonic_clock,
    )

    if not isinstance(orchestrator, ScientificExperimentOrchestrator):
        raise TypeError(
            "build_experiment_orchestrator returned an unexpected "
            f"{type(orchestrator).__name__}."
        )

    return orchestrator


def _cohort_loading_handler() -> StageHandler:
    from validation.orchestration.stages.cohort_loading import (
        CohortLoadingStageHandler,
    )

    return CohortLoadingStageHandler()


def _cohort_normalization_handler() -> StageHandler:
    from validation.orchestration.stages.cohort_normalization import (
        CohortNormalizationStageHandler,
    )

    return CohortNormalizationStageHandler()


def _validation_handler() -> StageHandler:
    from validation.orchestration.stages.validation import ValidationStageHandler

    return ValidationStageHandler()


def _report_generation_handler() -> StageHandler:
    from validation.orchestration.stages.report import ReportGenerationStageHandler

    return ReportGenerationStageHandler()