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

Configuration
    apply_experiment_overrides

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


from .configuration import (
    apply_experiment_overrides,
    ExperimentConfigurationError,
    dump_experiment_config,
    experiment_config_to_dict,
    load_experiment_config,
    parse_experiment_config,
)


from .execution import (
    ExperimentRunnerError,
    run_experiment,
)

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

from .composition import (
    build_experiment_orchestrator,
)

from .production import (
    build_production_orchestrator,
)

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

from validation.orchestration.adapters import (
    RootCauseRequestAdapter,
    RootCauseRequestSource,
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

    # Configuration codec and overrides
    "ExperimentConfigurationError",
    "apply_experiment_overrides",
    "load_experiment_config",
    "parse_experiment_config",
    "experiment_config_to_dict",
    "dump_experiment_config",

    # Public execution runner
    "ExperimentRunnerError",
    "run_experiment",

    # Workspace
    "ExperimentWorkspace",

    # Manifest
    "ExperimentManifest",

    # Orchestrator
    "ExperimentOrchestrator",
    "build_experiment_orchestrator",
    "build_production_orchestrator",
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

    "RootCauseRequestAdapter",
    "RootCauseRequestSource",
]