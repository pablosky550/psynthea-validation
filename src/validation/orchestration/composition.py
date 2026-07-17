"""Canonical construction of the complete experiment orchestrator.

This module is the application-composition boundary for Phase 2B. It combines
infrastructure-independent stage handlers with the canonical scientific
pipeline, preserving the mandatory orchestration order without teaching the
core ``ExperimentOrchestrator`` how individual stages are implemented.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from validation.orchestration.manifest import ExperimentManifest
from validation.orchestration.models import (
    ExperimentConfig,
    ExperimentStage,
)
from validation.orchestration.orchestrator import (
    ExperimentOrchestrator,
    ManifestWriter,
    OrchestrationExecution,
    OrchestrationPolicy,
    RunnerAdapter,
    StageHandler,
)
from validation.orchestration.runners import runner_for
from validation.orchestration.scientific_pipeline import ScientificPipeline
from validation.orchestration.workspace import ExperimentWorkspace

__all__ = [
    "ScientificExperimentOrchestrator",
    "build_experiment_orchestrator",
]


class ScientificExperimentOrchestrator(ExperimentOrchestrator):
    """Experiment orchestrator with run-scoped scientific cleanup.

    Scientific interpretation objects are deliberately exchanged in memory
    between Knowledge and Root Cause. They are transient execution products,
    not persistent application state, and are therefore removed in ``finally``
    after every successful or failed orchestration attempt.
    """

    __slots__ = ("_scientific_pipeline",)

    def __init__(
        self,
        handlers: tuple[StageHandler, ...],
        *,
        scientific_pipeline: ScientificPipeline,
        policy: OrchestrationPolicy | None = None,
        orchestrator_version: str = "1.0.0",
        runner_factory: Callable[[Any], RunnerAdapter] = runner_for,
        workspace_factory: Callable[..., ExperimentWorkspace] = (
            ExperimentWorkspace.create
        ),
        manifest_factory: Callable[..., ManifestWriter] = ExperimentManifest,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(scientific_pipeline, ScientificPipeline):
            raise TypeError(
                "scientific_pipeline must be a ScientificPipeline."
            )

        super().__init__(
            handlers=handlers,
            policy=policy,
            orchestrator_version=orchestrator_version,
            runner_factory=runner_factory,
            workspace_factory=workspace_factory,
            manifest_factory=manifest_factory,
            clock=clock,
            monotonic_clock=monotonic_clock,
        )
        self._scientific_pipeline = scientific_pipeline

    @property
    def scientific_pipeline(self) -> ScientificPipeline:
        """Return the canonical scientific stage composition."""

        return self._scientific_pipeline

    def execute(
        self,
        config: ExperimentConfig,
        *,
        run_id: str | None = None,
    ) -> OrchestrationExecution:
        """Execute one run and always release transient scientific products."""

        normalized_run_id = self._normalize_run_id(run_id)
        try:
            return super().execute(
                config,
                run_id=normalized_run_id,
            )
        finally:
            self._scientific_pipeline.clear_run(
                normalized_run_id
            )


def build_experiment_orchestrator(
    *,
    cohort_loading_handler: StageHandler,
    cohort_normalization_handler: StageHandler,
    validation_handler: StageHandler,
    scientific_pipeline: ScientificPipeline,
    report_generation_handler: StageHandler,
    policy: OrchestrationPolicy | None = None,
    orchestrator_version: str = "1.0.0",
    runner_factory: Callable[[Any], RunnerAdapter] = runner_for,
    workspace_factory: Callable[..., ExperimentWorkspace] = (
        ExperimentWorkspace.create
    ),
    manifest_factory: Callable[..., ManifestWriter] = ExperimentManifest,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic_clock: Callable[[], float] = monotonic,
) -> ExperimentOrchestrator:
    """Build the complete orchestrator with canonical scientific wiring.

    The non-scientific handlers remain explicit dependencies. Knowledge and
    root-cause handlers must come from one ``ScientificPipeline`` so they
    necessarily share the same run-scoped product store.
    """

    if not isinstance(scientific_pipeline, ScientificPipeline):
        raise TypeError(
            "scientific_pipeline must be a ScientificPipeline."
        )

    handlers = (
        _require_stage(
            cohort_loading_handler,
            ExperimentStage.COHORT_LOADING,
            "cohort_loading_handler",
        ),
        _require_stage(
            cohort_normalization_handler,
            ExperimentStage.COHORT_NORMALIZATION,
            "cohort_normalization_handler",
        ),
        _require_stage(
            validation_handler,
            ExperimentStage.VALIDATION,
            "validation_handler",
        ),
        *scientific_pipeline.handlers,
        _require_stage(
            report_generation_handler,
            ExperimentStage.REPORT_GENERATION,
            "report_generation_handler",
        ),
    )

    return ScientificExperimentOrchestrator(
        handlers=handlers,
        scientific_pipeline=scientific_pipeline,
        policy=policy,
        orchestrator_version=orchestrator_version,
        runner_factory=runner_factory,
        workspace_factory=workspace_factory,
        manifest_factory=manifest_factory,
        clock=clock,
        monotonic_clock=monotonic_clock,
    )


def _require_stage(
    handler: StageHandler,
    expected_stage: ExperimentStage,
    field_name: str,
) -> StageHandler:
    stage = getattr(handler, "stage", None)
    if stage is not expected_stage:
        observed = (
            stage.value
            if isinstance(stage, ExperimentStage)
            else repr(stage)
        )
        raise ValueError(
            f"{field_name}.stage must be {expected_stage.value!r}; "
            f"observed {observed}."
        )

    execute = getattr(handler, "execute", None)
    if not callable(execute):
        raise TypeError(
            f"{field_name} must define callable execute(context)."
        )

    return handler