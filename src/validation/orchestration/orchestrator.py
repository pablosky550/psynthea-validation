"""Experiment Orchestrator for Phase 2B scientific validation.

This module coordinates one complete, reproducible comparison experiment:

    configuration
        -> workspace
        -> Synthea
        -> psynthea
        -> cohort loading
        -> cohort normalization
        -> Validation Engine
        -> Scientific Knowledge Engine
        -> scientific report
        -> canonical manifest

It deliberately contains no simulator implementation, cohort parsing,
statistical validation, knowledge inference or report rendering. Those
responsibilities are supplied through explicit stage handlers.

Scientific design guarantees
----------------------------
* Both simulators execute from the same immutable ``ExperimentConfig``.
* Simulator runs are attempted in a deterministic order.
* Dependent pipeline stages never run after an upstream failure.
* Every stage produces an immutable ``PipelineStageResult``.
* Every nested artefact is collected into one canonical catalogue.
* Failures are represented as auditable domain results whenever possible.
* A canonical manifest is written for successful and failed experiments.
* Infrastructure or integrity failures fail loudly rather than producing a
  misleading scientific result.
* Runtime collaborators are injected, making the orchestration independently
  testable without invoking Java, psynthea or the Validation Engine.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable
from uuid import uuid4

from validation.orchestration.manifest import (
    ExperimentManifest,
    ManifestError,
)
from validation.orchestration.models import (
    ArtifactReference,
    ExecutionStatus,
    ExperimentConfig,
    ExperimentResult,
    ExperimentStage,
    PipelineStageResult,
    SimulatorKind,
    SimulatorRunResult,
)
from validation.orchestration.runners import (
    RunnerError,
    runner_for,
)
from validation.orchestration.workspace import (
    ExperimentWorkspace,
    WorkspaceError,
)

__all__ = [
    "ExperimentOrchestrator",
    "OrchestrationContext",
    "OrchestrationError",
    "OrchestrationExecution",
    "OrchestrationFinalizationError",
    "OrchestrationIntegrityError",
    "OrchestrationPolicy",
    "OrchestrationStageError",
    "ManifestWriter",
    "RunnerAdapter",
    "StageHandler",
    "StageOutput",
]


_ORCHESTRATOR_PRODUCER: Final[str] = "experiment_orchestrator"
_DEFAULT_ORCHESTRATOR_VERSION: Final[str] = "1.0.0"

_INTERNAL_STAGES: Final = frozenset(
    {
        ExperimentStage.WORKSPACE_INITIALIZATION,
        ExperimentStage.SYNTHEA_EXECUTION,
        ExperimentStage.PSYNTHEA_EXECUTION,
        ExperimentStage.MANIFEST_FINALIZATION,
    }
)

_EXTERNAL_STAGE_ORDER: Final[tuple[ExperimentStage, ...]] = (
    ExperimentStage.COHORT_LOADING,
    ExperimentStage.COHORT_NORMALIZATION,
    ExperimentStage.VALIDATION,
    ExperimentStage.KNOWLEDGE_ENRICHMENT,
    ExperimentStage.ROOT_CAUSE_ANALYSIS,
    ExperimentStage.REPORT_GENERATION,
)

_SIMULATOR_ORDER: Final = (
    SimulatorKind.SYNTHEA,
    SimulatorKind.PSYNTHEA,
)


# =============================================================================
# Errors
# =============================================================================


class OrchestrationError(RuntimeError):
    """Base class for orchestration boundary and lifecycle failures."""


class OrchestrationIntegrityError(OrchestrationError):
    """Raised when collaborators return inconsistent or unsafe domain data."""


class OrchestrationStageError(OrchestrationError):
    """Raised when a stage handler violates its declared contract."""


class OrchestrationFinalizationError(OrchestrationError):
    """Raised when an auditable manifest cannot be produced."""


# =============================================================================
# Runtime contracts
# =============================================================================


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _require_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _freeze_mapping(
    value: Mapping[str, Any],
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")

    def freeze(item: Any) -> Any:
        if isinstance(item, Mapping):
            normalized: dict[str, Any] = {}
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise TypeError(f"{field_name} mapping keys must be strings.")
                normalized[key] = freeze(nested)
            return MappingProxyType(normalized)
        if isinstance(item, list):
            return tuple(freeze(nested) for nested in item)
        if isinstance(item, tuple):
            return tuple(freeze(nested) for nested in item)
        if isinstance(item, (set, frozenset)):
            return frozenset(freeze(nested) for nested in item)
        return item

    return freeze(dict(value))


@dataclass(frozen=True, slots=True)
class StageOutput:
    """Successful output returned by one injected pipeline-stage handler.

    Handlers return only stage-specific products. Timing, status, identifiers,
    failure capture and final catalogue assembly remain the orchestrator's
    responsibility.
    """

    artifacts: tuple[ArtifactReference, ...] = ()
    summary: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.artifacts, (str, bytes)) or not isinstance(
            self.artifacts, Sequence
        ):
            raise TypeError("artifacts must be a sequence of ArtifactReference values.")
        artifacts = tuple(self.artifacts)
        seen_ids: set[str] = set()
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, ArtifactReference):
                raise TypeError(
                    f"artifacts[{index}] must be an ArtifactReference."
                )
            if artifact.id in seen_ids:
                raise ValueError(
                    f"artifacts contains duplicate id {artifact.id!r}."
                )
            seen_ids.add(artifact.id)
        object.__setattr__(self, "artifacts", artifacts)

        if self.summary is not None:
            object.__setattr__(
                self,
                "summary",
                _require_text(self.summary, "summary"),
            )
        object.__setattr__(
            self,
            "metadata",
            _freeze_mapping(self.metadata, "metadata"),
        )


@dataclass(frozen=True, slots=True)
class OrchestrationContext:
    """Read-only context supplied to each external pipeline-stage handler."""

    config: ExperimentConfig
    workspace: ExperimentWorkspace
    run_id: str
    simulator_runs: tuple[SimulatorRunResult, ...]
    stage_results: tuple[PipelineStageResult, ...]
    artifacts: tuple[ArtifactReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.config, ExperimentConfig):
            raise TypeError("config must be an ExperimentConfig.")
        if not isinstance(self.workspace, ExperimentWorkspace):
            raise TypeError("workspace must be an ExperimentWorkspace.")
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))

        simulator_runs = tuple(self.simulator_runs)
        if any(not isinstance(item, SimulatorRunResult) for item in simulator_runs):
            raise TypeError(
                "simulator_runs must contain only SimulatorRunResult values."
            )
        stage_results = tuple(self.stage_results)
        if any(not isinstance(item, PipelineStageResult) for item in stage_results):
            raise TypeError(
                "stage_results must contain only PipelineStageResult values."
            )
        artifacts = tuple(self.artifacts)
        if any(not isinstance(item, ArtifactReference) for item in artifacts):
            raise TypeError(
                "artifacts must contain only ArtifactReference values."
            )

        object.__setattr__(self, "simulator_runs", simulator_runs)
        object.__setattr__(self, "stage_results", stage_results)
        object.__setattr__(self, "artifacts", artifacts)

    def simulator_run(
        self,
        simulator: SimulatorKind,
    ) -> SimulatorRunResult | None:
        """Return the recorded run for ``simulator`` when available."""

        if not isinstance(simulator, SimulatorKind):
            raise TypeError("simulator must be a SimulatorKind member.")
        return next(
            (item for item in self.simulator_runs if item.simulator is simulator),
            None,
        )

    def stage_result(
        self,
        stage: ExperimentStage,
    ) -> PipelineStageResult | None:
        """Return the recorded result for ``stage`` when available."""

        if not isinstance(stage, ExperimentStage):
            raise TypeError("stage must be an ExperimentStage member.")
        return next(
            (item for item in self.stage_results if item.stage is stage),
            None,
        )


@runtime_checkable
class StageHandler(Protocol):
    """Injected implementation of one non-simulator orchestration stage."""

    stage: ExperimentStage

    def execute(self, context: OrchestrationContext) -> StageOutput:
        """Execute the stage and return its immutable outputs."""


@runtime_checkable
class RunnerAdapter(Protocol):
    """Minimal simulator-runner contract consumed by the orchestrator."""

    def run(
        self,
        *,
        experiment: ExperimentConfig,
        workspace: ExperimentWorkspace,
        run_id: str,
    ) -> SimulatorRunResult:
        """Execute one simulator and return its immutable result."""


@runtime_checkable
class ManifestWriter(Protocol):
    """Minimal manifest persistence contract consumed by the orchestrator."""

    def write(
        self,
        result: ExperimentResult,
        *,
        generated_at: datetime | None = None,
        verify_artifacts: bool = True,
        overwrite: bool = False,
    ) -> ArtifactReference:
        """Persist a canonical manifest and return its reference."""


@dataclass(frozen=True, slots=True)
class OrchestrationPolicy:
    """Operational policy controlling failure propagation and manifest creation."""

    continue_simulators_after_failure: bool = True
    write_manifest_on_failure: bool = True
    verify_manifest_artifacts: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "continue_simulators_after_failure",
            "write_manifest_on_failure",
            "verify_manifest_artifacts",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean.")


@dataclass(frozen=True, slots=True)
class OrchestrationExecution:
    """Complete runtime output, including the self-referential manifest artefact.

    ``ExperimentResult`` intentionally does not contain the manifest reference,
    because a manifest cannot include its own hash. This wrapper preserves both
    values without weakening that invariant.
    """

    result: ExperimentResult
    manifest: ArtifactReference | None

    def __post_init__(self) -> None:
        if not isinstance(self.result, ExperimentResult):
            raise TypeError("result must be an ExperimentResult.")
        if self.manifest is not None and not isinstance(
            self.manifest, ArtifactReference
        ):
            raise TypeError("manifest must be an ArtifactReference or None.")


# =============================================================================
# Orchestrator
# =============================================================================


class ExperimentOrchestrator:
    """Coordinate one complete Phase 2B experiment.

    External stages are injected as handlers so this component remains an
    application-service coordinator rather than a second implementation of the
    Validation Engine or Scientific Knowledge Engine.
    """

    __slots__ = (
        "_handlers",
        "_policy",
        "_orchestrator_version",
        "_runner_factory",
        "_workspace_factory",
        "_manifest_factory",
        "_clock",
        "_monotonic",
    )

    def __init__(
        self,
        handlers: Sequence[StageHandler],
        *,
        policy: OrchestrationPolicy | None = None,
        orchestrator_version: str = _DEFAULT_ORCHESTRATOR_VERSION,
        runner_factory: Callable[[Any], RunnerAdapter] = runner_for,
        workspace_factory: Callable[..., ExperimentWorkspace] = (
            ExperimentWorkspace.create
        ),
        manifest_factory: Callable[..., ManifestWriter] = ExperimentManifest,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._handlers = self._validate_handlers(handlers)
        self._policy = policy or OrchestrationPolicy()
        if not isinstance(self._policy, OrchestrationPolicy):
            raise TypeError("policy must be an OrchestrationPolicy.")

        self._orchestrator_version = _require_text(
            orchestrator_version,
            "orchestrator_version",
        )

        for field_name, collaborator in (
            ("runner_factory", runner_factory),
            ("workspace_factory", workspace_factory),
            ("manifest_factory", manifest_factory),
            ("clock", clock),
            ("monotonic_clock", monotonic_clock),
        ):
            if not callable(collaborator):
                raise TypeError(f"{field_name} must be callable.")

        self._runner_factory = runner_factory
        self._workspace_factory = workspace_factory
        self._manifest_factory = manifest_factory
        self._clock = clock
        self._monotonic = monotonic_clock

    @property
    def policy(self) -> OrchestrationPolicy:
        return self._policy

    @property
    def orchestrator_version(self) -> str:
        return self._orchestrator_version

    @property
    def handlers(self) -> Mapping[ExperimentStage, StageHandler]:
        return self._handlers

    def execute(
        self,
        config: ExperimentConfig,
        *,
        run_id: str | None = None,
    ) -> OrchestrationExecution:
        """Execute one complete experiment and persist its canonical manifest.

        Domain/process failures are returned as ``ExperimentResult(status=FAILED)``
        with a manifest whenever policy permits. Workspace, integrity and manifest
        failures raise explicit exceptions because returning an unverifiable
        experiment would violate the project's scientific contract.
        """

        if not isinstance(config, ExperimentConfig):
            raise TypeError("config must be an ExperimentConfig.")
        normalized_run_id = self._normalize_run_id(run_id)

        experiment_started_at = self._now()
        experiment_started_clock = self._monotonic()

        workspace = self._create_workspace(
            config=config,
            run_id=normalized_run_id,
            created_at=experiment_started_at,
        )

        simulator_runs: list[SimulatorRunResult] = []
        stage_results: list[PipelineStageResult] = []
        artifacts: list[ArtifactReference] = []

        stage_results.append(
            self._successful_internal_stage(
                config=config,
                run_id=normalized_run_id,
                stage=ExperimentStage.WORKSPACE_INITIALIZATION,
                started_at=experiment_started_at,
                finished_at=self._now(),
                summary="Experiment workspace created and ownership verified.",
                metadata={
                    "workspace": workspace.root.as_posix(),
                    "orchestrator_version": self.orchestrator_version,
                },
            )
        )

        failure_message: str | None = None

        for simulator in _SIMULATOR_ORDER:
            if (
                failure_message is not None
                and not self.policy.continue_simulators_after_failure
            ):
                break

            simulator_config = config.simulator(simulator)
            try:
                runner = self._runner_factory(simulator_config)
                if not isinstance(runner, RunnerAdapter):
                    raise OrchestrationIntegrityError(
                        "runner_factory must return an object implementing RunnerAdapter."
                    )
                run_result = runner.run(
                    experiment=config,
                    workspace=workspace,
                    run_id=normalized_run_id,
                )
            except (RunnerError, WorkspaceError) as exc:
                raise OrchestrationIntegrityError(
                    f"{simulator.value} runner failed outside its domain-result "
                    f"contract: {exc}"
                ) from exc

            self._validate_simulator_result(
                expected=simulator,
                result=run_result,
                config=config,
                run_id=normalized_run_id,
            )
            simulator_runs.append(run_result)
            self._extend_catalog(artifacts, run_result.artifacts)

            if run_result.status is not ExecutionStatus.SUCCEEDED:
                failure_message = (
                    run_result.error_message
                    or f"{simulator.value} execution failed."
                )

        if failure_message is None and len(simulator_runs) == len(_SIMULATOR_ORDER):
            for stage in _EXTERNAL_STAGE_ORDER:
                result = self._execute_external_stage(
                    stage=stage,
                    config=config,
                    workspace=workspace,
                    run_id=normalized_run_id,
                    simulator_runs=simulator_runs,
                    stage_results=stage_results,
                    artifacts=artifacts,
                )
                stage_results.append(result)
                self._extend_catalog(artifacts, result.artifacts)

                if result.status is ExecutionStatus.FAILED:
                    failure_message = (
                        result.error_message or f"{stage.value} failed."
                    )
                    break
        elif failure_message is None:
            failure_message = "Not all required simulator runs were executed."

        completed_external = {item.stage for item in stage_results}
        for stage in _EXTERNAL_STAGE_ORDER:
            if stage not in completed_external:
                stage_results.append(
                    self._skipped_stage(
                        config=config,
                        run_id=normalized_run_id,
                        stage=stage,
                        reason="Skipped because an upstream dependency failed.",
                    )
                )

        manifest_started_at = self._now()
        stage_results.append(
            self._successful_internal_stage(
                config=config,
                run_id=normalized_run_id,
                stage=ExperimentStage.MANIFEST_FINALIZATION,
                started_at=manifest_started_at,
                finished_at=self._now(),
                summary=(
                    "Manifest preconditions and artefact catalogue finalized."
                ),
                metadata={
                    "artifact_count": len(artifacts),
                    "verify_artifacts": self.policy.verify_manifest_artifacts,
                },
            )
        )

        experiment_finished_at = self._now()
        duration = max(0.0, self._monotonic() - experiment_started_clock)
        status = (
            ExecutionStatus.SUCCEEDED
            if failure_message is None
            else ExecutionStatus.FAILED
        )

        result = ExperimentResult(
            experiment_id=config.id,
            run_id=normalized_run_id,
            status=status,
            config=config,
            workspace=workspace.root,
            simulator_runs=tuple(simulator_runs),
            stage_results=tuple(stage_results),
            artifacts=tuple(artifacts),
            started_at=experiment_started_at,
            finished_at=experiment_finished_at,
            duration_seconds=duration,
            error_message=failure_message,
            metadata={
                "orchestrator": _ORCHESTRATOR_PRODUCER,
                "orchestrator_version": self.orchestrator_version,
                "simulator_order": tuple(item.value for item in _SIMULATOR_ORDER),
                "external_stage_order": tuple(
                    item.value for item in _EXTERNAL_STAGE_ORDER
                ),
            },
        )

        manifest_reference: ArtifactReference | None = None
        should_write_manifest = (
            result.status is ExecutionStatus.SUCCEEDED
            or self.policy.write_manifest_on_failure
        )
        if should_write_manifest:
            manifest_reference = self._write_manifest(
                workspace=workspace,
                result=result,
            )

        return OrchestrationExecution(
            result=result,
            manifest=manifest_reference,
        )

    def _execute_external_stage(
        self,
        *,
        stage: ExperimentStage,
        config: ExperimentConfig,
        workspace: ExperimentWorkspace,
        run_id: str,
        simulator_runs: Sequence[SimulatorRunResult],
        stage_results: Sequence[PipelineStageResult],
        artifacts: Sequence[ArtifactReference],
    ) -> PipelineStageResult:
        handler = self.handlers[stage]
        started_at = self._now()
        started_clock = self._monotonic()

        context = OrchestrationContext(
            config=config,
            workspace=workspace,
            run_id=run_id,
            simulator_runs=tuple(simulator_runs),
            stage_results=tuple(stage_results),
            artifacts=tuple(artifacts),
        )

        try:
            output = handler.execute(context)
            if not isinstance(output, StageOutput):
                raise OrchestrationStageError(
                    f"Handler for {stage.value} must return StageOutput, "
                    f"got {type(output).__name__}."
                )
            self._validate_stage_artifacts(
                stage=stage,
                workspace=workspace,
                artifacts=output.artifacts,
            )
        except OrchestrationStageError:
            raise
        except Exception as exc:
            finished_at = self._now()
            return PipelineStageResult(
                id=self._stage_id(config.id, run_id, stage),
                stage=stage,
                status=ExecutionStatus.FAILED,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=max(
                    0.0,
                    self._monotonic() - started_clock,
                ),
                artifacts=(),
                error_message=(
                    f"{type(exc).__name__}: {exc}"
                    if str(exc)
                    else type(exc).__name__
                ),
                metadata={
                    "handler": type(handler).__qualname__,
                    "exception_type": type(exc).__name__,
                },
            )

        finished_at = self._now()
        return PipelineStageResult(
            id=self._stage_id(config.id, run_id, stage),
            stage=stage,
            status=ExecutionStatus.SUCCEEDED,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=max(0.0, self._monotonic() - started_clock),
            artifacts=output.artifacts,
            summary=output.summary,
            metadata={
                **dict(output.metadata),
                "handler": type(handler).__qualname__,
            },
        )

    def _write_manifest(
        self,
        *,
        workspace: ExperimentWorkspace,
        result: ExperimentResult,
    ) -> ArtifactReference:
        try:
            manifest = self._manifest_factory(
                workspace,
                producer_version=self.orchestrator_version,
            )
            if not isinstance(manifest, ManifestWriter):
                raise OrchestrationFinalizationError(
                    "manifest_factory must return an object implementing ManifestWriter."
                )
            return manifest.write(
                result,
                generated_at=result.finished_at,
                verify_artifacts=self.policy.verify_manifest_artifacts,
                overwrite=False,
            )
        except ManifestError as exc:
            raise OrchestrationFinalizationError(
                "The experiment completed but its canonical manifest could not "
                "be finalized."
            ) from exc

    def _create_workspace(
        self,
        *,
        config: ExperimentConfig,
        run_id: str,
        created_at: datetime,
    ) -> ExperimentWorkspace:
        try:
            workspace = self._workspace_factory(
                config,
                run_id,
                created_at=created_at,
            )
        except WorkspaceError:
            raise
        except Exception as exc:
            raise OrchestrationIntegrityError(
                f"workspace_factory failed: {exc}"
            ) from exc

        if not isinstance(workspace, ExperimentWorkspace):
            raise OrchestrationIntegrityError(
                "workspace_factory must return an ExperimentWorkspace."
            )
        if workspace.config != config or workspace.run_id != run_id:
            raise OrchestrationIntegrityError(
                "workspace_factory returned a workspace bound to a different "
                "experiment or run."
            )
        return workspace

    def _successful_internal_stage(
        self,
        *,
        config: ExperimentConfig,
        run_id: str,
        stage: ExperimentStage,
        started_at: datetime,
        finished_at: datetime,
        summary: str,
        metadata: Mapping[str, Any],
    ) -> PipelineStageResult:
        return PipelineStageResult(
            id=self._stage_id(config.id, run_id, stage),
            stage=stage,
            status=ExecutionStatus.SUCCEEDED,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=max(
                0.0,
                (finished_at - started_at).total_seconds(),
            ),
            summary=summary,
            metadata=metadata,
        )

    def _skipped_stage(
        self,
        *,
        config: ExperimentConfig,
        run_id: str,
        stage: ExperimentStage,
        reason: str,
    ) -> PipelineStageResult:
        return PipelineStageResult(
            id=self._stage_id(config.id, run_id, stage),
            stage=stage,
            status=ExecutionStatus.SKIPPED,
            summary=reason,
            metadata={"skip_reason": reason},
        )

    def _validate_simulator_result(
        self,
        *,
        expected: SimulatorKind,
        result: SimulatorRunResult,
        config: ExperimentConfig,
        run_id: str,
    ) -> None:
        if not isinstance(result, SimulatorRunResult):
            raise OrchestrationIntegrityError(
                "SimulatorRunner.run must return SimulatorRunResult."
            )
        if result.simulator is not expected:
            raise OrchestrationIntegrityError(
                f"Runner for {expected.value} returned a result for "
                f"{result.simulator.value}."
            )
        expected_id = f"{config.id}:{run_id}:{expected.value}"
        if result.id != expected_id:
            raise OrchestrationIntegrityError(
                f"Simulator result id mismatch: expected {expected_id!r}, "
                f"got {result.id!r}."
            )

    def _validate_stage_artifacts(
        self,
        *,
        stage: ExperimentStage,
        workspace: ExperimentWorkspace,
        artifacts: Sequence[ArtifactReference],
    ) -> None:
        for artifact in artifacts:
            try:
                absolute = workspace.resolve(artifact.path)
            except WorkspaceError as exc:
                raise OrchestrationStageError(
                    f"Handler for {stage.value} returned an artefact outside "
                    "the workspace."
                ) from exc
            if absolute.is_symlink() or not absolute.is_file():
                raise OrchestrationStageError(
                    f"Handler for {stage.value} returned a missing or symbolic "
                    f"artefact: {artifact.path.as_posix()}."
                )
            verified = workspace.artifact_reference(
                artifact_id=artifact.id,
                kind=artifact.kind,
                path=artifact.path,
                media_type=artifact.media_type,
                producer=artifact.producer,
                created_at=artifact.created_at,
                metadata=artifact.metadata,
            )
            if verified.sha256 != artifact.sha256:
                raise OrchestrationStageError(
                    f"Handler for {stage.value} returned an artefact with an "
                    f"invalid SHA-256 digest: {artifact.id}."
                )
            if verified.size_bytes != artifact.size_bytes:
                raise OrchestrationStageError(
                    f"Handler for {stage.value} returned an artefact with an "
                    f"invalid size: {artifact.id}."
                )

    @staticmethod
    def _extend_catalog(
        catalogue: list[ArtifactReference],
        new_artifacts: Sequence[ArtifactReference],
    ) -> None:
        existing_by_id = {artifact.id: artifact for artifact in catalogue}
        existing_by_path = {artifact.path: artifact for artifact in catalogue}

        for artifact in new_artifacts:
            existing_id = existing_by_id.get(artifact.id)
            if existing_id is not None:
                raise OrchestrationIntegrityError(
                    f"Artefact id {artifact.id!r} was produced more than once; "
                    "artefact identity must be globally unique within a run."
                )

            existing_path = existing_by_path.get(artifact.path)
            if existing_path is not None:
                raise OrchestrationIntegrityError(
                    f"Artefact path {artifact.path.as_posix()!r} was produced more "
                    "than once; each persisted file must have one canonical owner."
                )

            catalogue.append(artifact)
            existing_by_id[artifact.id] = artifact
            existing_by_path[artifact.path] = artifact

    @staticmethod
    def _validate_handlers(
        handlers: Sequence[StageHandler],
    ) -> Mapping[ExperimentStage, StageHandler]:
        if isinstance(handlers, (str, bytes)) or not isinstance(
            handlers, Sequence
        ):
            raise TypeError("handlers must be a sequence of StageHandler values.")

        normalized: dict[ExperimentStage, StageHandler] = {}
        for index, handler in enumerate(handlers):
            stage = getattr(handler, "stage", None)
            if not isinstance(stage, ExperimentStage):
                raise TypeError(
                    f"handlers[{index}].stage must be an ExperimentStage."
                )
            if stage in _INTERNAL_STAGES:
                raise ValueError(
                    f"{stage.value} is managed internally and cannot be "
                    "registered as an external handler."
                )
            if stage not in _EXTERNAL_STAGE_ORDER:
                raise ValueError(
                    f"{stage.value} is not a supported external orchestration stage."
                )
            execute = getattr(handler, "execute", None)
            if not callable(execute):
                raise TypeError(
                    f"handlers[{index}] must define callable execute(context)."
                )
            if stage in normalized:
                raise ValueError(
                    f"Duplicate handler registered for stage {stage.value!r}."
                )
            normalized[stage] = handler

        missing = set(_EXTERNAL_STAGE_ORDER) - set(normalized)
        if missing:
            raise ValueError(
                "Missing required stage handler(s): "
                + ", ".join(sorted(stage.value for stage in missing))
                + "."
            )
        return MappingProxyType(normalized)

    def _now(self) -> datetime:
        return _require_datetime(self._clock(), "clock result")

    def _normalize_run_id(self, run_id: str | None) -> str:
        if run_id is None:
            timestamp = self._now().strftime("%Y%m%dT%H%M%S%fZ")
            return f"run-{timestamp}-{uuid4().hex[:12]}"
        return _require_text(run_id, "run_id")

    @staticmethod
    def _stage_id(
        experiment_id: str,
        run_id: str,
        stage: ExperimentStage,
    ) -> str:
        return f"{experiment_id}:{run_id}:{stage.value}"