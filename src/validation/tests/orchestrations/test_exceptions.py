from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
import json
from pathlib import Path
import pickle

import pytest

from validation.orchestration.exceptions import (
    ErrorCategory,
    ErrorCode,
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


ALL_EXCEPTION_TYPES = (
    Phase2BError,
    WorkspaceError,
    WorkspaceCollisionError,
    WorkspaceIntegrityError,
    WorkspacePathError,
    RunnerError,
    RunnerConfigurationError,
    RunnerIntegrityError,
    ManifestError,
    ManifestSerializationError,
    ManifestIntegrityError,
    ManifestCollisionError,
    OrchestrationError,
    OrchestrationIntegrityError,
    OrchestrationStageError,
    OrchestrationFinalizationError,
)


@pytest.mark.parametrize("exception_type", ALL_EXCEPTION_TYPES)
def test_all_exceptions_are_runtime_and_phase2b_errors(exception_type):
    error = exception_type("failure")
    assert isinstance(error, RuntimeError)
    assert isinstance(error, Phase2BError)
    assert str(error) == "failure"


def test_hierarchy_preserves_component_catch_boundaries():
    assert issubclass(WorkspaceCollisionError, WorkspaceError)
    assert issubclass(WorkspacePathError, WorkspaceIntegrityError)
    assert issubclass(RunnerConfigurationError, RunnerError)
    assert issubclass(RunnerIntegrityError, RunnerError)
    assert issubclass(ManifestSerializationError, ManifestError)
    assert issubclass(ManifestIntegrityError, ManifestError)
    assert issubclass(ManifestCollisionError, ManifestError)
    assert issubclass(OrchestrationIntegrityError, OrchestrationError)
    assert issubclass(OrchestrationStageError, OrchestrationError)
    assert issubclass(OrchestrationFinalizationError, OrchestrationError)


@pytest.mark.parametrize(
    ("exception_type", "code", "category", "component"),
    (
        (
            WorkspaceCollisionError,
            ErrorCode.WORKSPACE_COLLISION,
            ErrorCategory.COLLISION,
            "workspace",
        ),
        (
            WorkspacePathError,
            ErrorCode.WORKSPACE_PATH,
            ErrorCategory.PATH,
            "workspace",
        ),
        (
            RunnerConfigurationError,
            ErrorCode.RUNNER_CONFIGURATION,
            ErrorCategory.CONFIGURATION,
            "runner",
        ),
        (
            RunnerIntegrityError,
            ErrorCode.RUNNER_INTEGRITY,
            ErrorCategory.INTEGRITY,
            "runner",
        ),
        (
            ManifestSerializationError,
            ErrorCode.MANIFEST_SERIALIZATION,
            ErrorCategory.SERIALIZATION,
            "manifest",
        ),
        (
            ManifestCollisionError,
            ErrorCode.MANIFEST_COLLISION,
            ErrorCategory.COLLISION,
            "manifest",
        ),
        (
            OrchestrationStageError,
            ErrorCode.ORCHESTRATION_STAGE,
            ErrorCategory.EXECUTION,
            "orchestrator",
        ),
        (
            OrchestrationFinalizationError,
            ErrorCode.ORCHESTRATION_FINALIZATION,
            ErrorCategory.FINALIZATION,
            "orchestrator",
        ),
    ),
)
def test_error_metadata_is_stable(
    exception_type,
    code,
    category,
    component,
):
    error = exception_type("failure")
    assert error.code is code
    assert error.category is category
    assert error.component == component


def test_message_is_normalized_and_empty_values_are_rejected():
    assert str(Phase2BError("  failure  ")) == "failure"

    with pytest.raises(ValueError):
        Phase2BError("   ")

    with pytest.raises(TypeError):
        Phase2BError(123)  # type: ignore[arg-type]


class ExampleEnum(str, Enum):
    VALUE = "value"


def test_context_is_deeply_immutable_and_json_compatible():
    error = RunnerIntegrityError(
        "integrity failure",
        context={
            "path": Path("simulators/synthea/output.csv"),
            "timestamp": datetime(2026, 7, 14, 10, 0, tzinfo=UTC),
            "day": date(2026, 7, 14),
            "enum": ExampleEnum.VALUE,
            "nested": {
                "items": [1, 2],
                "set": {"b", "a"},
            },
        },
    )

    with pytest.raises(TypeError):
        error.context["new"] = "value"  # type: ignore[index]

    nested = error.context["nested"]
    with pytest.raises(TypeError):
        nested["new"] = "value"  # type: ignore[index]

    payload = error.as_dict()
    assert payload["context"]["path"] == "simulators/synthea/output.csv"
    assert payload["context"]["timestamp"] == "2026-07-14T10:00:00+00:00"
    assert payload["context"]["day"] == "2026-07-14"
    assert payload["context"]["enum"] == "value"
    assert payload["context"]["nested"]["items"] == [1, 2]
    assert payload["context"]["nested"]["set"] == ["a", "b"]
    json.dumps(payload, allow_nan=False, sort_keys=True)


def test_context_rejects_unsafe_or_ambiguous_values():
    with pytest.raises(TypeError, match="mapping keys"):
        Phase2BError("failure", context={1: "value"})  # type: ignore[dict-item]

    with pytest.raises(TypeError, match="unsupported"):
        Phase2BError("failure", context={"object": object()})

    with pytest.raises(ValueError, match="NaN"):
        Phase2BError("failure", context={"value": float("nan")})

    with pytest.raises(ValueError, match="timezone-aware"):
        Phase2BError(
            "failure",
            context={"when": datetime(2026, 7, 14, 10, 0)},
        )


@pytest.mark.parametrize("exception_type", ALL_EXCEPTION_TYPES)
def test_pickle_round_trip_preserves_concrete_type_message_and_context(
    exception_type,
):
    original = exception_type(
        "failure",
        context={"run_id": "run-001", "nested": {"attempt": 2}},
    )

    restored = pickle.loads(pickle.dumps(original))

    assert type(restored) is exception_type
    assert str(restored) == "failure"
    assert restored.as_dict() == original.as_dict()


def test_as_dict_returns_fresh_mutable_payload_without_mutating_exception():
    error = ManifestIntegrityError(
        "hash mismatch",
        context={"artifact_id": "validation.metrics"},
    )

    first = error.as_dict()
    first["context"]["artifact_id"] = "changed"

    second = error.as_dict()
    assert second["context"]["artifact_id"] == "validation.metrics"


def test_exception_chaining_remains_available():
    cause = OSError("disk failure")

    try:
        raise WorkspaceIntegrityError("workspace invalid") from cause
    except WorkspaceIntegrityError as error:
        assert error.__cause__ is cause


def test_public_export_list_contains_every_public_exception():
    import validation.orchestration.exceptions as module

    assert set(module.__all__) == {
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
    }