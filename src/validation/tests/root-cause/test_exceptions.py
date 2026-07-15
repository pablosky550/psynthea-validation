from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
import json
from pathlib import Path
import pickle

import pytest

from validation.root_cause.exceptions import (
    AttributionError,
    CandidateGenerationError,
    ErrorCategory,
    ErrorCode,
    EvidenceCollectionError,
    ReproductionError,
    RootCauseError,
    RootCauseInputError,
    RootCauseIntegrityError,
    VerificationExecutionError,
)


ALL_EXCEPTION_TYPES = (
    RootCauseError,
    RootCauseInputError,
    RootCauseIntegrityError,
    EvidenceCollectionError,
    CandidateGenerationError,
    VerificationExecutionError,
    AttributionError,
    ReproductionError,
)


@pytest.mark.parametrize("exception_type", ALL_EXCEPTION_TYPES)
def test_all_exceptions_are_runtime_and_root_cause_errors(exception_type):
    error = exception_type("failure")

    assert isinstance(error, RuntimeError)
    assert isinstance(error, RootCauseError)
    assert str(error) == "failure"


def test_hierarchy_preserves_phase_and_component_catch_boundaries():
    assert issubclass(RootCauseInputError, RootCauseError)
    assert issubclass(RootCauseIntegrityError, RootCauseError)
    assert issubclass(EvidenceCollectionError, RootCauseError)
    assert issubclass(CandidateGenerationError, RootCauseError)
    assert issubclass(VerificationExecutionError, RootCauseError)
    assert issubclass(AttributionError, RootCauseError)
    assert issubclass(ReproductionError, RootCauseError)


@pytest.mark.parametrize(
    ("exception_type", "code", "category", "component", "stage"),
    (
        (
            RootCauseInputError,
            ErrorCode.ROOT_CAUSE_INPUT,
            ErrorCategory.INPUT,
            "root_cause",
            "input_validation",
        ),
        (
            RootCauseIntegrityError,
            ErrorCode.ROOT_CAUSE_INTEGRITY,
            ErrorCategory.INTEGRITY,
            "root_cause",
            "integrity_validation",
        ),
        (
            EvidenceCollectionError,
            ErrorCode.EVIDENCE_COLLECTION,
            ErrorCategory.COLLECTION,
            "evidence",
            "evidence_collection",
        ),
        (
            CandidateGenerationError,
            ErrorCode.CANDIDATE_GENERATION,
            ErrorCategory.GENERATION,
            "candidates",
            "candidate_generation",
        ),
        (
            VerificationExecutionError,
            ErrorCode.VERIFICATION_EXECUTION,
            ErrorCategory.EXECUTION,
            "verification",
            "verification",
        ),
        (
            AttributionError,
            ErrorCode.ATTRIBUTION,
            ErrorCategory.ATTRIBUTION,
            "attribution",
            "source_attribution",
        ),
        (
            ReproductionError,
            ErrorCode.REPRODUCTION,
            ErrorCategory.REPRODUCTION,
            "reproduction",
            "reproduction_planning",
        ),
    ),
)
def test_error_metadata_is_stable(
    exception_type,
    code,
    category,
    component,
    stage,
):
    error = exception_type("failure")

    assert error.code is code
    assert error.category is category
    assert error.component == component
    assert error.stage == stage


def test_message_is_normalized_and_empty_values_are_rejected():
    assert str(RootCauseError("  failure  ")) == "failure"

    with pytest.raises(ValueError, match="must not be empty"):
        RootCauseError("   ")

    with pytest.raises(TypeError, match="must be a string"):
        RootCauseError(123)  # type: ignore[arg-type]


class ExampleEnum(str, Enum):
    VALUE = "value"


def test_context_is_deeply_immutable_deterministic_and_json_compatible():
    error = VerificationExecutionError(
        "verifier failed",
        context={
            "path": Path("artifacts/check.json"),
            "timestamp": datetime(2026, 7, 15, 8, 0, tzinfo=UTC),
            "day": date(2026, 7, 15),
            "enum": ExampleEnum.VALUE,
            "nested": {"items": [1, 2], "set": {"b", "a"}},
        },
    )

    with pytest.raises(TypeError):
        error.context["new"] = "value"  # type: ignore[index]

    nested = error.context["nested"]
    with pytest.raises(TypeError):
        nested["new"] = "value"  # type: ignore[index]

    payload = error.as_dict()
    assert payload == {
        "type": "VerificationExecutionError",
        "code": "root_cause.verification.execution",
        "category": "execution",
        "component": "verification",
        "stage": "verification",
        "message": "verifier failed",
        "context": {
            "path": "artifacts/check.json",
            "timestamp": "2026-07-15T08:00:00+00:00",
            "day": "2026-07-15",
            "enum": "value",
            "nested": {"items": [1, 2], "set": ["a", "b"]},
        },
    }
    json.dumps(payload, allow_nan=False, sort_keys=True)


def test_context_rejects_unsafe_or_ambiguous_values():
    with pytest.raises(TypeError, match="mapping keys"):
        RootCauseError("failure", context={1: "value"})  # type: ignore[dict-item]

    with pytest.raises(TypeError, match="unsupported"):
        RootCauseError("failure", context={"object": object()})

    with pytest.raises(ValueError, match="NaN"):
        RootCauseError("failure", context={"value": float("nan")})

    with pytest.raises(ValueError, match="timezone-aware"):
        RootCauseError(
            "failure",
            context={"when": datetime(2026, 7, 15, 8, 0)},
        )

    with pytest.raises(TypeError, match="mapping or None"):
        RootCauseError("failure", context=[("key", "value")])  # type: ignore[arg-type]


@pytest.mark.parametrize("exception_type", ALL_EXCEPTION_TYPES)
def test_pickle_round_trip_preserves_concrete_type_message_and_context(
    exception_type,
):
    original = exception_type(
        "failure",
        context={"request_id": "rc-request-001", "nested": {"attempt": 2}},
    )

    restored = pickle.loads(pickle.dumps(original))

    assert type(restored) is exception_type
    assert str(restored) == "failure"
    assert restored.as_dict() == original.as_dict()


def test_as_dict_returns_fresh_mutable_payload_without_mutating_exception():
    error = EvidenceCollectionError(
        "artefact unavailable",
        context={"artifact_id": "validation.metrics"},
    )

    first = error.as_dict()
    first["context"]["artifact_id"] = "changed"

    second = error.as_dict()
    assert second["context"]["artifact_id"] == "validation.metrics"


def test_exception_chaining_remains_available():
    cause = OSError("disk failure")

    try:
        raise EvidenceCollectionError("could not read evidence") from cause
    except EvidenceCollectionError as error:
        assert error.__cause__ is cause


def test_scientific_outcomes_are_not_exception_types():
    public_names = {exception_type.__name__ for exception_type in ALL_EXCEPTION_TYPES}

    assert "InconclusiveError" not in public_names
    assert "RefutedError" not in public_names
    assert "VerificationFailedError" not in public_names
    assert "NoCandidateError" not in public_names


def test_public_export_list_is_exact_and_stable():
    import validation.root_cause.exceptions as module

    assert set(module.__all__) == {
        "AttributionError",
        "CandidateGenerationError",
        "ErrorCategory",
        "ErrorCode",
        "EvidenceCollectionError",
        "ReproductionError",
        "RootCauseError",
        "RootCauseInputError",
        "RootCauseIntegrityError",
        "VerificationExecutionError",
    }