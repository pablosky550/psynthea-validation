"""
Experiment Orchestration (Phase 2B).

This package coordinates complete scientific validation experiments between
Synthea and psynthea while preserving reproducibility, traceability and
separation of concerns.

Public API
----------
Domain
    ExperimentConfig
    ExperimentResult
    CohortConfig
    SimulatorConfig
    SimulatorRunResult
    PipelineStageResult
    ArtifactReference

Execution
    ExperimentWorkspace
    ExperimentOrchestrator
    ExperimentManifest

Runners
    SimulatorRunner
    runner_for

Contracts
    StageHandler
    StageOutput
    OrchestrationContext
    OrchestrationExecution
    OrchestrationPolicy

Enums
    ArtifactKind
    ExecutionStatus
    ExperimentStage
    ReportFormat
    SimulatorKind

Exceptions
    Phase2BError
    WorkspaceError
    WorkspaceCollisionError
    WorkspaceIntegrityError
    WorkspacePathError
    RunnerError
    RunnerConfigurationError
    RunnerIntegrityError
    ManifestError
    ManifestSerializationError
    ManifestIntegrityError
    ManifestCollisionError
    OrchestrationError
    OrchestrationIntegrityError
    OrchestrationStageError
    OrchestrationFinalizationError
"""

from .exceptions import (
    ManifestCollisionError,
    ManifestError,
    ManifestIntegrityError,
    ManifestSerializationError,
    OrchestrationError,
    OrchestrationFinalizationError,
    OrchestrationIntegrityError,
    OrchestrationStageError,
    Phase2BError,
    RunnerConfigurationError,
    RunnerError,
    RunnerIntegrityError,
    WorkspaceCollisionError,
    WorkspaceError,
    WorkspaceIntegrityError,
    WorkspacePathError,
)

from .manifest import ExperimentManifest

from .models import (
    ArtifactKind,
    ArtifactReference,
    CohortConfig,
    ExecutionStatus,
    ExperimentConfig,
    ExperimentResult,
    ExperimentStage,
    PipelineStageResult,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
    SimulatorRunResult,
)

from .orchestrator import (
    ExperimentOrchestrator,
    OrchestrationContext,
    OrchestrationExecution,
    OrchestrationPolicy,
    StageHandler,
    StageOutput,
)

from .runners import (
    SimulatorRunner,
    runner_for,
)

from .workspace import (
    ExperimentWorkspace,
)

__all__ = [
    # Domain
    "ExperimentConfig",
    "ExperimentResult",
    "CohortConfig",
    "SimulatorConfig",
    "SimulatorRunResult",
    "PipelineStageResult",
    "ArtifactReference",

    # Workspace
    "ExperimentWorkspace",

    # Manifest
    "ExperimentManifest",

    # Orchestrator
    "ExperimentOrchestrator",
    "OrchestrationContext",
    "OrchestrationExecution",
    "OrchestrationPolicy",
    "StageHandler",
    "StageOutput",

    # Runners
    "SimulatorRunner",
    "runner_for",

    # Enums
    "ArtifactKind",
    "ExecutionStatus",
    "ExperimentStage",
    "ReportFormat",
    "SimulatorKind",

    # Exceptions
    "Phase2BError",
    "WorkspaceError",
    "WorkspaceCollisionError",
    "WorkspaceIntegrityError",
    "WorkspacePathError",
    "RunnerError",
    "RunnerConfigurationError",
    "RunnerIntegrityError",
    "ManifestError",
    "ManifestSerializationError",
    "ManifestIntegrityError",
    "ManifestCollisionError",
    "OrchestrationError",
    "OrchestrationIntegrityError",
    "OrchestrationStageError",
    "OrchestrationFinalizationError",
]