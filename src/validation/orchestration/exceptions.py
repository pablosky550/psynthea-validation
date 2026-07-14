"""Canonical exception taxonomy for Phase 2B experiment orchestration.

All Phase 2B components should import their public exception classes from this
module. Centralising the hierarchy provides stable catch boundaries for the CLI,
application services, tests and future API integrations while preserving
component-specific failure types.

Normal simulator exits, timeouts and scientific validation failures should be
represented by immutable domain results whenever possible. These exceptions are
reserved for failures where continuing would make an experiment unsafe,
ambiguous or scientifically unverifiable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, ClassVar

__all__ = [
    "ErrorCategory",
    "ErrorCode",
    "ManifestCollisionError",
    "ManifestError",
    "ManifestIntegrityError",
    "ManifestSerializationError",
    "OrchestrationError",
    "OrchestrationFinalizationError",
    "OrchestrationIntegrityError",
    "OrchestrationStageError",
    "Phase2BError",
    "RunnerConfigurationError",
    "RunnerError",
    "RunnerIntegrityError",
    "WorkspaceCollisionError",
    "WorkspaceError",
    "WorkspaceIntegrityError",
    "WorkspacePathError",
]


class ErrorCategory(str, Enum):
    """Stable machine-readable categories for orchestration failures."""

    CONFIGURATION = "configuration"
    INTEGRITY = "integrity"
    COLLISION = "collision"
    PATH = "path"
    SERIALIZATION = "serialization"
    EXECUTION = "execution"
    FINALIZATION = "finalization"
    UNKNOWN = "unknown"


class ErrorCode(str, Enum):
    """Stable error identifiers suitable for logs, reports and CLI output."""

    PHASE_2B_ERROR = "phase_2b.error"

    WORKSPACE_ERROR = "phase_2b.workspace.error"
    WORKSPACE_COLLISION = "phase_2b.workspace.collision"
    WORKSPACE_INTEGRITY = "phase_2b.workspace.integrity"
    WORKSPACE_PATH = "phase_2b.workspace.path"

    RUNNER_ERROR = "phase_2b.runner.error"
    RUNNER_CONFIGURATION = "phase_2b.runner.configuration"
    RUNNER_INTEGRITY = "phase_2b.runner.integrity"

    MANIFEST_ERROR = "phase_2b.manifest.error"
    MANIFEST_SERIALIZATION = "phase_2b.manifest.serialization"
    MANIFEST_INTEGRITY = "phase_2b.manifest.integrity"
    MANIFEST_COLLISION = "phase_2b.manifest.collision"

    ORCHESTRATION_ERROR = "phase_2b.orchestrator.error"
    ORCHESTRATION_INTEGRITY = "phase_2b.orchestrator.integrity"
    ORCHESTRATION_STAGE = "phase_2b.orchestrator.stage"
    ORCHESTRATION_FINALIZATION = "phase_2b.orchestrator.finalization"


def _normalize_context_value(value: Any, *, path: str) -> Any:
    """Return a deeply immutable and deterministically serializable value."""

    if value is None or isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError(f"{path} must not contain NaN or infinity.")
        return value

    if isinstance(value, Enum):
        return _normalize_context_value(value.value, path=path)

    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{path} datetime values must be timezone-aware.")
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, PurePath):
        return value.as_posix()

    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} mapping keys must be strings.")
            normalized[key] = _normalize_context_value(
                item,
                path=f"{path}.{key}",
            )
        return MappingProxyType(normalized)

    if isinstance(value, (set, frozenset)):
        normalized_items = [
            _normalize_context_value(item, path=f"{path}[]")
            for item in value
        ]
        return tuple(sorted(normalized_items, key=repr))

    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return tuple(
            _normalize_context_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )

    raise TypeError(
        f"{path} contains unsupported diagnostic value type "
        f"{type(value).__name__}."
    )


def _freeze_context(
    value: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    """Return deeply immutable, string-keyed diagnostic metadata."""

    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise TypeError("context must be a mapping or None.")

    normalized = _normalize_context_value(value, path="context")
    if not isinstance(normalized, Mapping):  # Defensive invariant.
        raise TypeError("context must normalize to a mapping.")
    return normalized


def _thaw(value: Any) -> Any:
    """Convert immutable context structures into plain JSON-compatible values."""

    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _rebuild_exception(
    exception_type: type["Phase2BError"],
    message: str,
    context: Mapping[str, Any],
) -> "Phase2BError":
    """Reconstruct an exception during pickle deserialization."""

    return exception_type(message, context=context)


class Phase2BError(RuntimeError):
    """Root exception for unsafe or unverifiable Phase 2B failures.

    Parameters
    ----------
    message:
        Human-readable explanation suitable for logs and CLI output.
    context:
        Optional diagnostic metadata. Values are normalized into a deeply
        immutable and JSON-compatible representation. Context must never contain
        secrets, real patient data or non-synthetic clinical information.

    Existing call sites remain compatible with ``Phase2BError("message")``.
    """

    code: ClassVar[ErrorCode] = ErrorCode.PHASE_2B_ERROR
    category: ClassVar[ErrorCategory] = ErrorCategory.UNKNOWN
    component: ClassVar[str] = "orchestration"

    __slots__ = ("_context",)

    def __init__(
        self,
        message: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(message, str):
            raise TypeError("message must be a string.")
        normalized = message.strip()
        if not normalized:
            raise ValueError("message must not be empty.")

        super().__init__(normalized)
        self._context = _freeze_context(context)

    @property
    def context(self) -> Mapping[str, Any]:
        """Deeply immutable diagnostic metadata attached to the failure."""

        return self._context

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation for logs and APIs."""

        return {
            "type": type(self).__name__,
            "code": self.code.value,
            "category": self.category.value,
            "component": self.component,
            "message": str(self),
            "context": _thaw(self.context),
        }

    def __reduce_ex__(
        self,
        protocol: int,
    ) -> tuple[Any, tuple[type["Phase2BError"], str, Mapping[str, Any]]]:
        """Preserve concrete type, message and context during pickling."""

        del protocol
        return (
            _rebuild_exception,
            (type(self), str(self), _thaw(self.context)),
        )


# =============================================================================
# Workspace boundary
# =============================================================================


class WorkspaceError(Phase2BError):
    """Base class for workspace lifecycle and filesystem-boundary failures."""

    code = ErrorCode.WORKSPACE_ERROR
    component = "workspace"


class WorkspaceCollisionError(WorkspaceError):
    """Raised when an immutable workspace path or artefact already exists."""

    code = ErrorCode.WORKSPACE_COLLISION
    category = ErrorCategory.COLLISION


class WorkspaceIntegrityError(WorkspaceError):
    """Raised when workspace ownership, layout or content is inconsistent."""

    code = ErrorCode.WORKSPACE_INTEGRITY
    category = ErrorCategory.INTEGRITY


class WorkspacePathError(WorkspaceIntegrityError):
    """Raised when a managed path escapes or violates the workspace boundary."""

    code = ErrorCode.WORKSPACE_PATH
    category = ErrorCategory.PATH


# =============================================================================
# Simulator execution boundary
# =============================================================================


class RunnerError(Phase2BError):
    """Base class for failures outside normal simulator process results."""

    code = ErrorCode.RUNNER_ERROR
    component = "runner"


class RunnerConfigurationError(RunnerError):
    """Raised when a simulator execution contract is invalid or ambiguous."""

    code = ErrorCode.RUNNER_CONFIGURATION
    category = ErrorCategory.CONFIGURATION


class RunnerIntegrityError(RunnerError):
    """Raised when produced outputs violate the runner/workspace contract."""

    code = ErrorCode.RUNNER_INTEGRITY
    category = ErrorCategory.INTEGRITY


# =============================================================================
# Canonical manifest boundary
# =============================================================================


class ManifestError(Phase2BError):
    """Base class for manifest serialization, persistence and verification."""

    code = ErrorCode.MANIFEST_ERROR
    component = "manifest"


class ManifestSerializationError(ManifestError):
    """Raised when a value cannot be represented as canonical manifest JSON."""

    code = ErrorCode.MANIFEST_SERIALIZATION
    category = ErrorCategory.SERIALIZATION


class ManifestIntegrityError(ManifestError):
    """Raised when manifest or referenced-artefact integrity validation fails."""

    code = ErrorCode.MANIFEST_INTEGRITY
    category = ErrorCategory.INTEGRITY


class ManifestCollisionError(ManifestError):
    """Raised when an immutable manifest already exists for the run."""

    code = ErrorCode.MANIFEST_COLLISION
    category = ErrorCategory.COLLISION


# =============================================================================
# Experiment coordination boundary
# =============================================================================


class OrchestrationError(Phase2BError):
    """Base class for experiment-coordination and lifecycle failures."""

    code = ErrorCode.ORCHESTRATION_ERROR
    component = "orchestrator"


class OrchestrationIntegrityError(OrchestrationError):
    """Raised when collaborators return inconsistent or unsafe domain data."""

    code = ErrorCode.ORCHESTRATION_INTEGRITY
    category = ErrorCategory.INTEGRITY


class OrchestrationStageError(OrchestrationError):
    """Raised when a stage handler violates its declared runtime contract."""

    code = ErrorCode.ORCHESTRATION_STAGE
    category = ErrorCategory.EXECUTION


class OrchestrationFinalizationError(OrchestrationError):
    """Raised when the final auditable manifest cannot be produced."""

    code = ErrorCode.ORCHESTRATION_FINALIZATION
    category = ErrorCategory.FINALIZATION