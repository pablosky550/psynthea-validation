"""
Immutable domain models for reproducible experiment orchestration.

Phase 2B coordinates complete validation experiments without reimplementing
simulation, statistical validation, scientific knowledge acquisition or report
rendering.  This module defines the stable contracts exchanged by those
components.

The central design rule is deliberately strict:

    orchestration records what was requested, executed and produced;
    it does not perform the work itself.

Consequently, these models keep experiment configuration, simulator execution,
pipeline-stage execution, persisted artefacts and the final experiment result as
separate concepts.  Filesystem creation, subprocess execution, hashing,
serialization, validation-engine invocation and report generation do not belong
in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from math import isfinite
from pathlib import Path, PurePath
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Mapping, Sequence, TypeVar

__all__ = [
    "ArtifactKind",
    "ArtifactReference",
    "CohortConfig",
    "ExecutionStatus",
    "ExperimentConfig",
    "ExperimentResult",
    "ExperimentStage",
    "ModuleSelectionMode",
    "PipelineStageResult",
    "ReportFormat",
    "SimulatorConfig",
    "SimulatorKind",
    "SimulatorRunResult",
]


# =============================================================================
# Enumerations
# =============================================================================


class SimulatorKind(str, Enum):
    """Simulator implementation participating in a comparison experiment."""

    SYNTHEA = "synthea"
    PSYNTHEA = "psynthea"


class ExecutionStatus(str, Enum):
    """Lifecycle state shared by simulator runs, pipeline stages and experiments."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class ExperimentStage(str, Enum):
    """Canonical stages coordinated by the experiment pipeline."""

    WORKSPACE_INITIALIZATION = "workspace_initialization"
    SYNTHEA_EXECUTION = "synthea_execution"
    PSYNTHEA_EXECUTION = "psynthea_execution"
    COHORT_LOADING = "cohort_loading"
    COHORT_NORMALIZATION = "cohort_normalization"
    VALIDATION = "validation"
    KNOWLEDGE_ENRICHMENT = "knowledge_enrichment"
    ROOT_CAUSE_ANALYSIS = "root_cause_analysis"
    REPORT_GENERATION = "report_generation"
    MANIFEST_FINALIZATION = "manifest_finalization"


class ArtifactKind(str, Enum):
    """Semantic role of a persisted artefact produced by an experiment."""

    CONFIGURATION = "configuration"
    MANIFEST = "manifest"
    LOG = "log"
    SIMULATOR_OUTPUT = "simulator_output"
    COHORT_LOAD_RESULT = "cohort_load_result"
    COHORT_NORMALIZATION_RESULT = "cohort_normalization_result"
    NORMALIZED_DATASET = "normalized_dataset"
    VALIDATION_RESULT = "validation_result"
    KNOWLEDGE_RESULT = "knowledge_result"
    ROOT_CAUSE_RESULT = "root_cause_result"
    REPORT = "report"
    FIGURE = "figure"
    EVIDENCE = "evidence"
    OTHER = "other"


class ReportFormat(str, Enum):
    """Supported final scientific-report representations."""

    HTML = "html"
    PDF = "pdf"
    JSON = "json"

class ModuleSelectionMode(str, Enum):
    """Strategy used to select modules for a cohort execution."""

    EXPLICIT = "explicit"
    ALL = "all"

# =============================================================================
# Validation and normalization helpers
# =============================================================================


_IDENTIFIER_PATTERN = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SHA256_PATTERN = compile_pattern(r"^[0-9a-f]{64}$")
_EnumT = TypeVar("_EnumT", bound=Enum)


_TERMINAL_STATUSES = frozenset(
    {
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.SKIPPED,
    }
)

_REQUIRED_SUCCESS_STAGES = frozenset(
    {
        ExperimentStage.WORKSPACE_INITIALIZATION,
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
        ExperimentStage.KNOWLEDGE_ENRICHMENT,
        ExperimentStage.ROOT_CAUSE_ANALYSIS,
        ExperimentStage.REPORT_GENERATION,
        ExperimentStage.MANIFEST_FINALIZATION,
    }
)


def _require_enum(value: _EnumT, enum_type: type[_EnumT], field_name: str) -> _EnumT:
    if not isinstance(value, enum_type):
        raise TypeError(
            f"{field_name} must be a {enum_type.__name__} member, "
            f"got {type(value).__name__}."
        )
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _optional_text(value: str | None, field_name: str) -> str | None:
    return None if value is None else _require_text(value, field_name)


def _require_identifier(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, '.', '_', ':', or '-'."
        )
    return normalized


def _normalize_path(value: Path | str, field_name: str) -> Path:
    if isinstance(value, str):
        value = _require_text(value, field_name)
    elif not isinstance(value, PurePath):
        raise TypeError(f"{field_name} must be a path or string.")

    path = Path(value).expanduser()
    if str(path).strip() in {"", "."}:
        raise ValueError(f"{field_name} must identify a concrete path.")
    return path


def _normalize_relative_path(value: Path | str, field_name: str) -> Path:
    path = _normalize_path(value, field_name)
    if path.is_absolute():
        raise ValueError(f"{field_name} must be relative to the experiment workspace.")
    if ".." in path.parts:
        raise ValueError(f"{field_name} must not escape the experiment workspace.")
    return path


def _normalize_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _require_datetime(value: datetime, field_name: str) -> datetime:
    normalized = _normalize_datetime(value, field_name)
    if normalized is None:
        raise TypeError(f"{field_name} must be a datetime.")
    return normalized


def _normalize_date(value: date | None, field_name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{field_name} must be a date or None.")
    return value


def _normalize_text_tuple(
    values: Sequence[str],
    field_name: str,
    *,
    identifiers: bool = False,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")

    validator = _require_identifier if identifiers else _require_text
    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = validator(value, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)

    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return tuple(normalized)


def _normalize_enum_tuple(
    values: Sequence[_EnumT],
    enum_type: type[_EnumT],
    field_name: str,
    *,
    allow_empty: bool = True,
) -> tuple[_EnumT, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {enum_type.__name__} members.")

    normalized: list[_EnumT] = []
    seen: set[_EnumT] = set()
    for index, value in enumerate(values):
        item = _require_enum(value, enum_type, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)

    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return tuple(normalized)


def _normalize_model_tuple(
    values: Sequence[Any],
    expected_type: type[Any],
    field_name: str,
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {expected_type.__name__} values.")

    normalized = tuple(values)
    for index, value in enumerate(normalized):
        if not isinstance(value, expected_type):
            raise TypeError(
                f"{field_name}[{index}] must be {expected_type.__name__}, "
                f"got {type(value).__name__}."
            )
    return normalized


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("mapping keys must be strings.")
            frozen[key] = _deep_freeze(item)
        return MappingProxyType(frozen)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return _deep_freeze(dict(value))


def _freeze_string_mapping(value: Mapping[str, str], field_name: str) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping of strings to strings.")

    normalized: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = _require_text(key, f"{field_name} key")
        normalized[normalized_key] = _require_text(item, f"{field_name}[{normalized_key!r}]")
    return MappingProxyType(normalized)


def _require_positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return value


def _require_non_negative_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return value


def _optional_non_negative_integer(value: int | None, field_name: str) -> int | None:
    return None if value is None else _require_non_negative_integer(value, field_name)


def _optional_positive_integer(value: int | None, field_name: str) -> int | None:
    return None if value is None else _require_positive_integer(value, field_name)


def _require_boolean(value: bool, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean.")
    return value


def _normalize_path_tuple(
    values: Sequence[Path | str],
    field_name: str,
    *,
    relative: bool = False,
) -> tuple[Path, ...]:
    if isinstance(values, (str, bytes, PurePath)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of paths.")

    normalizer = _normalize_relative_path if relative else _normalize_path
    normalized: list[Path] = []
    seen: set[Path] = set()
    for index, value in enumerate(values):
        path = normalizer(value, f"{field_name}[{index}]")
        if path not in seen:
            normalized.append(path)
            seen.add(path)
    return tuple(normalized)


def _require_positive_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{field_name} must be finite and greater than zero.")
    return normalized


def _require_non_negative_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative.")
    return normalized


def _normalize_sha256(value: str | None, field_name: str = "sha256") -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None.")
    normalized = value.strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain exactly 64 lowercase hexadecimal characters."
        )
    return normalized


def _require_unique_ids(values: Sequence[Any], field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        item_id = value.id
        if item_id in seen:
            raise ValueError(f"{field_name} contains duplicate id {item_id!r}.")
        seen.add(item_id)


def _validate_execution_window(
    *,
    status: ExecutionStatus,
    started_at: datetime | None,
    finished_at: datetime | None,
    duration_seconds: float | None,
    field_prefix: str,
) -> None:
    if started_at is not None and finished_at is not None and finished_at < started_at:
        raise ValueError(f"{field_prefix}.finished_at must not precede started_at.")

    if duration_seconds is not None:
        _require_non_negative_number(duration_seconds, f"{field_prefix}.duration_seconds")

    if status is ExecutionStatus.PENDING:
        if started_at is not None or finished_at is not None or duration_seconds is not None:
            raise ValueError(f"A pending {field_prefix} cannot contain execution timing.")
    elif status is ExecutionStatus.RUNNING:
        if started_at is None:
            raise ValueError(f"A running {field_prefix} requires started_at.")
        if finished_at is not None:
            raise ValueError(f"A running {field_prefix} cannot contain finished_at.")
    elif status is ExecutionStatus.SKIPPED:
        if started_at is not None or finished_at is not None or duration_seconds is not None:
            raise ValueError(f"A skipped {field_prefix} cannot contain execution timing.")
    elif status in _TERMINAL_STATUSES:
        if started_at is None:
            raise ValueError(f"A terminal {field_prefix} requires started_at.")
        if finished_at is None:
            raise ValueError(f"A terminal {field_prefix} requires finished_at.")


# =============================================================================
# Experiment configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class CohortConfig:
    """Scientific cohort parameters shared by both simulator executions.

    Module selection supports two explicit modes:

    ``explicit``
        Execute the modules named in ``modules`` and/or supplied through
        ``module_files``.

    ``all``
        Discover every supported root module from ``modules_dir``. Concrete
        discovery is intentionally deferred to the orchestration module
        resolver so this model remains independent from filesystem execution.

    ``parameters`` remains in its historical positional location for backwards
    compatibility. New code should instantiate this model with keyword arguments.
    """

    population: int
    seed: int
    modules: tuple[str, ...]
    reference_date: date | None = None
    min_age: int | None = None
    max_age: int | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    module_files: tuple[Path, ...] = ()
    module_selection: ModuleSelectionMode = ModuleSelectionMode.EXPLICIT
    modules_dir: Path | None = None

    step_days: int | None = None
    years_of_history: int | None = None
    wellness_encounters: bool = False
    vitals: bool = False
    mortality: bool = False
    keystone: bool = False
    ground_truth: bool = False
    output_format: str = "csv"
    profile_file: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "population",
            _require_positive_integer(self.population, "population"),
        )

        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer.")
        if not -(2**63) <= self.seed <= (2**63 - 1):
            raise ValueError("seed must fit in a signed 64-bit integer.")

        selection = _require_enum(
            self.module_selection,
            ModuleSelectionMode,
            "module_selection",
        )
        modules = _normalize_text_tuple(
            self.modules,
            "modules",
            identifiers=True,
            allow_empty=True,
        )
        module_files = _normalize_path_tuple(
            self.module_files,
            "module_files",
            relative=False,
        )
        modules_dir = (
            None
            if self.modules_dir is None
            else _normalize_path(self.modules_dir, "modules_dir")
        )

        if selection is ModuleSelectionMode.EXPLICIT:
            if not modules and not module_files:
                raise ValueError(
                    "Explicit module selection requires at least one module "
                    "or module_file."
                )
        elif selection is ModuleSelectionMode.ALL:
            if modules or module_files:
                raise ValueError(
                    "All-module selection must not define modules or "
                    "module_files."
                )
            if modules_dir is None:
                raise ValueError(
                    "All-module selection requires modules_dir."
                )

        object.__setattr__(self, "module_selection", selection)
        object.__setattr__(self, "modules", modules)
        object.__setattr__(self, "module_files", module_files)
        object.__setattr__(self, "modules_dir", modules_dir)

        object.__setattr__(
            self,
            "reference_date",
            _normalize_date(self.reference_date, "reference_date"),
        )
        object.__setattr__(
            self,
            "min_age",
            _optional_non_negative_integer(self.min_age, "min_age"),
        )
        object.__setattr__(
            self,
            "max_age",
            _optional_non_negative_integer(self.max_age, "max_age"),
        )
        if (
            self.min_age is not None
            and self.max_age is not None
            and self.min_age > self.max_age
        ):
            raise ValueError("min_age must not exceed max_age.")

        object.__setattr__(
            self,
            "step_days",
            _optional_positive_integer(self.step_days, "step_days"),
        )
        object.__setattr__(
            self,
            "years_of_history",
            _optional_positive_integer(
                self.years_of_history,
                "years_of_history",
            ),
        )

        for field_name in (
            "wellness_encounters",
            "vitals",
            "mortality",
            "keystone",
            "ground_truth",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_boolean(getattr(self, field_name), field_name),
            )

        output_format = _require_identifier(
            self.output_format,
            "output_format",
        ).lower()
        if output_format not in {"csv", "omop"}:
            raise ValueError(
                "output_format must be either 'csv' or 'omop'."
            )
        object.__setattr__(self, "output_format", output_format)

        profile_file = (
            None
            if self.profile_file is None
            else _normalize_path(self.profile_file, "profile_file")
        )
        object.__setattr__(self, "profile_file", profile_file)
        object.__setattr__(
            self,
            "parameters",
            _freeze_mapping(self.parameters, "parameters"),
        )

@dataclass(frozen=True, slots=True)
class SimulatorConfig:
    """Execution contract for one simulator adapter.

    ``command`` contains the executable and fixed arguments only.  Dynamic
    cohort arguments are derived by the simulator runner from ``CohortConfig``.
    """

    kind: SimulatorKind
    command: tuple[str, ...]
    working_directory: Path
    output_subdirectory: str
    timeout_seconds: float = 3600.0
    environment: Mapping[str, str] = field(default_factory=dict)
    arguments: Mapping[str, Any] = field(default_factory=dict)
    expected_output_files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _require_enum(self.kind, SimulatorKind, "kind"))
        object.__setattr__(
            self,
            "command",
            _normalize_text_tuple(self.command, "command", allow_empty=False),
        )
        object.__setattr__(
            self,
            "working_directory",
            _normalize_path(self.working_directory, "working_directory"),
        )
        object.__setattr__(
            self,
            "output_subdirectory",
            _require_identifier(self.output_subdirectory, "output_subdirectory"),
        )
        object.__setattr__(
            self,
            "timeout_seconds",
            _require_positive_number(self.timeout_seconds, "timeout_seconds"),
        )
        object.__setattr__(
            self,
            "environment",
            _freeze_string_mapping(self.environment, "environment"),
        )
        object.__setattr__(self, "arguments", _freeze_mapping(self.arguments, "arguments"))
        expected_output_files = _normalize_text_tuple(
            self.expected_output_files,
            "expected_output_files",
        )
        object.__setattr__(
            self,
            "expected_output_files",
            tuple(
                str(_normalize_relative_path(item, f"expected_output_files[{index}]"))
                for index, item in enumerate(expected_output_files)
            ),
        )


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """Complete, immutable specification of one reproducible experiment."""

    id: str
    name: str
    cohort: CohortConfig
    simulators: tuple[SimulatorConfig, ...]
    output_root: Path
    report_formats: tuple[ReportFormat, ...] = (ReportFormat.HTML,)
    description: str | None = None
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        if not isinstance(self.cohort, CohortConfig):
            raise TypeError("cohort must be a CohortConfig.")

        simulators = _normalize_model_tuple(self.simulators, SimulatorConfig, "simulators")
        if len(simulators) != 2:
            raise ValueError("simulators must contain exactly one Synthea and one psynthea config.")
        simulator_kinds = [item.kind for item in simulators]
        if set(simulator_kinds) != {SimulatorKind.SYNTHEA, SimulatorKind.PSYNTHEA}:
            raise ValueError("simulators must contain exactly one Synthea and one psynthea config.")
        if len(simulator_kinds) != len(set(simulator_kinds)):
            raise ValueError("simulators must not contain duplicate simulator kinds.")
        object.__setattr__(self, "simulators", simulators)

        object.__setattr__(self, "output_root", _normalize_path(self.output_root, "output_root"))
        object.__setattr__(
            self,
            "report_formats",
            _normalize_enum_tuple(
                self.report_formats,
                ReportFormat,
                "report_formats",
                allow_empty=False,
            ),
        )
        object.__setattr__(self, "description", _optional_text(self.description, "description"))
        object.__setattr__(self, "tags", _normalize_text_tuple(self.tags, "tags"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    def simulator(self, kind: SimulatorKind) -> SimulatorConfig:
        """Return the configuration for ``kind`` or fail on an invalid boundary value."""

        normalized_kind = _require_enum(kind, SimulatorKind, "kind")
        return next(item for item in self.simulators if item.kind is normalized_kind)


# =============================================================================
# Persisted artefacts
# =============================================================================


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """Auditable reference to one artefact persisted by the experiment pipeline."""

    id: str
    kind: ArtifactKind
    path: Path
    media_type: str
    created_at: datetime
    sha256: str | None = None
    size_bytes: int | None = None
    producer: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "kind", _require_enum(self.kind, ArtifactKind, "kind"))
        object.__setattr__(self, "path", _normalize_relative_path(self.path, "path"))
        object.__setattr__(self, "media_type", _require_text(self.media_type, "media_type"))
        object.__setattr__(
            self,
            "created_at",
            _require_datetime(self.created_at, "created_at"),
        )
        object.__setattr__(self, "sha256", _normalize_sha256(self.sha256))
        object.__setattr__(
            self,
            "size_bytes",
            _optional_non_negative_integer(self.size_bytes, "size_bytes"),
        )
        object.__setattr__(self, "producer", _optional_text(self.producer, "producer"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        if self.sha256 is not None and self.size_bytes is None:
            raise ValueError("size_bytes is required when sha256 is provided.")


# =============================================================================
# Execution results
# =============================================================================


@dataclass(frozen=True, slots=True)
class SimulatorRunResult:
    """Outcome of executing one simulator for one experiment."""

    id: str
    simulator: SimulatorKind
    status: ExecutionStatus
    command: tuple[str, ...]
    working_directory: Path
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    return_code: int | None = None
    artifacts: tuple[ArtifactReference, ...] = ()
    error_message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(
            self,
            "simulator",
            _require_enum(self.simulator, SimulatorKind, "simulator"),
        )
        object.__setattr__(self, "status", _require_enum(self.status, ExecutionStatus, "status"))
        object.__setattr__(
            self,
            "command",
            _normalize_text_tuple(self.command, "command", allow_empty=False),
        )
        object.__setattr__(
            self,
            "working_directory",
            _normalize_path(self.working_directory, "working_directory"),
        )
        object.__setattr__(
            self,
            "started_at",
            _normalize_datetime(self.started_at, "started_at"),
        )
        object.__setattr__(
            self,
            "finished_at",
            _normalize_datetime(self.finished_at, "finished_at"),
        )
        if self.duration_seconds is not None:
            object.__setattr__(
                self,
                "duration_seconds",
                _require_non_negative_number(self.duration_seconds, "duration_seconds"),
            )
        if self.return_code is not None:
            if isinstance(self.return_code, bool) or not isinstance(self.return_code, int):
                raise TypeError("return_code must be an integer or None.")
        artifacts = _normalize_model_tuple(self.artifacts, ArtifactReference, "artifacts")
        _require_unique_ids(artifacts, "artifacts")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(
            self,
            "error_message",
            _optional_text(self.error_message, "error_message"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        _validate_execution_window(
            status=self.status,
            started_at=self.started_at,
            finished_at=self.finished_at,
            duration_seconds=self.duration_seconds,
            field_prefix="simulator run",
        )

        if self.status is ExecutionStatus.SUCCEEDED:
            if self.return_code != 0:
                raise ValueError("A successful simulator run requires return_code == 0.")
            if self.error_message is not None:
                raise ValueError("A successful simulator run cannot contain error_message.")
        elif self.status is ExecutionStatus.FAILED:
            if self.return_code == 0:
                raise ValueError("A failed simulator run cannot have return_code == 0.")
            if self.error_message is None:
                raise ValueError("A failed simulator run requires error_message.")
        elif self.status in {ExecutionStatus.PENDING, ExecutionStatus.RUNNING}:
            if self.return_code is not None or self.error_message is not None:
                raise ValueError(
                    "A non-terminal simulator run cannot contain return_code or error_message."
                )


@dataclass(frozen=True, slots=True)
class PipelineStageResult:
    """Outcome of one non-simulator orchestration stage."""

    id: str
    stage: ExperimentStage
    status: ExecutionStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    artifacts: tuple[ArtifactReference, ...] = ()
    summary: str | None = None
    error_message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        object.__setattr__(self, "stage", _require_enum(self.stage, ExperimentStage, "stage"))
        object.__setattr__(self, "status", _require_enum(self.status, ExecutionStatus, "status"))
        object.__setattr__(
            self,
            "started_at",
            _normalize_datetime(self.started_at, "started_at"),
        )
        object.__setattr__(
            self,
            "finished_at",
            _normalize_datetime(self.finished_at, "finished_at"),
        )
        if self.duration_seconds is not None:
            object.__setattr__(
                self,
                "duration_seconds",
                _require_non_negative_number(self.duration_seconds, "duration_seconds"),
            )
        artifacts = _normalize_model_tuple(self.artifacts, ArtifactReference, "artifacts")
        _require_unique_ids(artifacts, "artifacts")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "summary", _optional_text(self.summary, "summary"))
        object.__setattr__(
            self,
            "error_message",
            _optional_text(self.error_message, "error_message"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        _validate_execution_window(
            status=self.status,
            started_at=self.started_at,
            finished_at=self.finished_at,
            duration_seconds=self.duration_seconds,
            field_prefix="pipeline stage",
        )

        if self.status is ExecutionStatus.SUCCEEDED and self.error_message is not None:
            raise ValueError("A successful pipeline stage cannot contain error_message.")
        if self.status is ExecutionStatus.FAILED and self.error_message is None:
            raise ValueError("A failed pipeline stage requires error_message.")
        if self.status in {ExecutionStatus.PENDING, ExecutionStatus.RUNNING} and self.error_message:
            raise ValueError("A non-terminal pipeline stage cannot contain error_message.")


# =============================================================================
# Final experiment result
# =============================================================================


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    """Canonical output of the Phase 2B Experiment Orchestrator.

    The result contains domain objects and artefact references only.  It is safe
    to pass to manifest serializers, report indexes, APIs or later Phase 3
    components without exposing subprocess or filesystem implementation details.
    """

    experiment_id: str
    run_id: str
    status: ExecutionStatus
    config: ExperimentConfig
    workspace: Path
    simulator_runs: tuple[SimulatorRunResult, ...] = ()
    stage_results: tuple[PipelineStageResult, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "experiment_id",
            _require_identifier(self.experiment_id, "experiment_id"),
        )
        object.__setattr__(self, "run_id", _require_identifier(self.run_id, "run_id"))
        object.__setattr__(self, "status", _require_enum(self.status, ExecutionStatus, "status"))
        if not isinstance(self.config, ExperimentConfig):
            raise TypeError("config must be an ExperimentConfig.")
        if self.experiment_id != self.config.id:
            raise ValueError("experiment_id must match config.id.")
        object.__setattr__(self, "workspace", _normalize_path(self.workspace, "workspace"))

        simulator_runs = _normalize_model_tuple(
            self.simulator_runs,
            SimulatorRunResult,
            "simulator_runs",
        )
        _require_unique_ids(simulator_runs, "simulator_runs")
        simulator_kinds = [item.simulator for item in simulator_runs]
        if len(simulator_kinds) != len(set(simulator_kinds)):
            raise ValueError("simulator_runs must contain at most one result per simulator kind.")
        object.__setattr__(self, "simulator_runs", simulator_runs)

        stage_results = _normalize_model_tuple(
            self.stage_results,
            PipelineStageResult,
            "stage_results",
        )
        _require_unique_ids(stage_results, "stage_results")
        stage_kinds = [item.stage for item in stage_results]
        if len(stage_kinds) != len(set(stage_kinds)):
            raise ValueError("stage_results must contain at most one result per experiment stage.")
        object.__setattr__(self, "stage_results", stage_results)

        artifacts = _normalize_model_tuple(self.artifacts, ArtifactReference, "artifacts")
        _require_unique_ids(artifacts, "artifacts")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(
            self,
            "started_at",
            _normalize_datetime(self.started_at, "started_at"),
        )
        object.__setattr__(
            self,
            "finished_at",
            _normalize_datetime(self.finished_at, "finished_at"),
        )
        if self.duration_seconds is not None:
            object.__setattr__(
                self,
                "duration_seconds",
                _require_non_negative_number(self.duration_seconds, "duration_seconds"),
            )
        object.__setattr__(
            self,
            "error_message",
            _optional_text(self.error_message, "error_message"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        _validate_execution_window(
            status=self.status,
            started_at=self.started_at,
            finished_at=self.finished_at,
            duration_seconds=self.duration_seconds,
            field_prefix="experiment",
        )

        if self.status is ExecutionStatus.SUCCEEDED:
            expected = {SimulatorKind.SYNTHEA, SimulatorKind.PSYNTHEA}
            actual = {item.simulator for item in self.simulator_runs}
            if actual != expected:
                raise ValueError(
                    "A successful experiment requires successful run records for both simulators."
                )
            unsuccessful_runs = [
                item.simulator.value
                for item in self.simulator_runs
                if item.status is not ExecutionStatus.SUCCEEDED
            ]
            if unsuccessful_runs:
                raise ValueError(
                    "A successful experiment cannot contain unsuccessful simulator runs: "
                    + ", ".join(sorted(unsuccessful_runs))
                    + "."
                )
            unsuccessful_stages = [
                item.stage.value
                for item in self.stage_results
                if item.status not in {ExecutionStatus.SUCCEEDED, ExecutionStatus.SKIPPED}
            ]
            if unsuccessful_stages:
                raise ValueError(
                    "A successful experiment cannot contain incomplete pipeline stages: "
                    + ", ".join(sorted(unsuccessful_stages))
                    + "."
                )
            completed_stages = {item.stage for item in self.stage_results}
            missing_stages = _REQUIRED_SUCCESS_STAGES - completed_stages
            if missing_stages:
                raise ValueError(
                    "A successful experiment is missing required pipeline stages: "
                    + ", ".join(sorted(item.value for item in missing_stages))
                    + "."
                )
            nested_artifacts = {
                artifact.id: artifact
                for result in (*self.simulator_runs, *self.stage_results)
                for artifact in result.artifacts
            }
            catalog = {artifact.id: artifact for artifact in self.artifacts}
            missing_artifact_ids = set(nested_artifacts) - set(catalog)
            if missing_artifact_ids:
                raise ValueError(
                    "A successful experiment artifact catalogue is missing nested artefacts: "
                    + ", ".join(sorted(missing_artifact_ids))
                    + "."
                )
            inconsistent_artifact_ids = {
                artifact_id
                for artifact_id, artifact in nested_artifacts.items()
                if catalog[artifact_id] != artifact
            }
            if inconsistent_artifact_ids:
                raise ValueError(
                    "A successful experiment contains inconsistent artefact references: "
                    + ", ".join(sorted(inconsistent_artifact_ids))
                    + "."
                )
            if self.error_message is not None:
                raise ValueError("A successful experiment cannot contain error_message.")
        elif self.status is ExecutionStatus.FAILED and self.error_message is None:
            raise ValueError("A failed experiment requires error_message.")
        elif self.status in {ExecutionStatus.PENDING, ExecutionStatus.RUNNING} and self.error_message:
            raise ValueError("A non-terminal experiment cannot contain error_message.")

    @property
    def synthea_run(self) -> SimulatorRunResult | None:
        """Return the Synthea run result when it has been recorded."""

        return next(
            (item for item in self.simulator_runs if item.simulator is SimulatorKind.SYNTHEA),
            None,
        )

    @property
    def psynthea_run(self) -> SimulatorRunResult | None:
        """Return the psynthea run result when it has been recorded."""

        return next(
            (item for item in self.simulator_runs if item.simulator is SimulatorKind.PSYNTHEA),
            None,
        )

    def stage(self, stage: ExperimentStage) -> PipelineStageResult | None:
        """Return the result for ``stage`` when that stage has been recorded."""

        normalized_stage = _require_enum(stage, ExperimentStage, "stage")
        return next((item for item in self.stage_results if item.stage is normalized_stage), None)

    def artifacts_of_kind(self, kind: ArtifactKind) -> tuple[ArtifactReference, ...]:
        """Return final experiment artefacts with the requested semantic role."""

        normalized_kind = _require_enum(kind, ArtifactKind, "kind")
        return tuple(item for item in self.artifacts if item.kind is normalized_kind)