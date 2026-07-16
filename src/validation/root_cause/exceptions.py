"""Canonical technical exception taxonomy for Phase 3 root-cause analysis.

The Root Cause Engine must distinguish operational failures from scientific
conclusions.  A parser error, missing artefact, verifier crash or attribution
failure is never evidence that a causal hypothesis is true or false.  Such
conditions cross this exception boundary; expected scientific uncertainty is
represented by immutable domain results from :mod:`validation.root_cause.models`.

All Phase 3 components should raise or translate failures to the most specific
public class defined here.  The hierarchy provides stable catch boundaries for
engines, tests, CLIs and future orchestration adapters while retaining
machine-readable error metadata and deterministic diagnostic context.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, ClassVar

__all__ = [
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
]


class ErrorCategory(str, Enum):
    """Stable machine-readable categories for Phase 3 technical failures."""

    INPUT = "input"
    INTEGRITY = "integrity"
    COLLECTION = "collection"
    GENERATION = "generation"
    EXECUTION = "execution"
    ATTRIBUTION = "attribution"
    REPRODUCTION = "reproduction"
    UNKNOWN = "unknown"


class ErrorCode(str, Enum):
    """Stable identifiers suitable for logs, manifests, APIs and CLI output."""

    ROOT_CAUSE_ERROR = "root_cause.error"
    ROOT_CAUSE_INPUT = "root_cause.input"
    ROOT_CAUSE_INTEGRITY = "root_cause.integrity"
    EVIDENCE_COLLECTION = "root_cause.evidence.collection"
    CANDIDATE_GENERATION = "root_cause.candidate.generation"
    VERIFICATION_EXECUTION = "root_cause.verification.execution"
    ATTRIBUTION = "root_cause.attribution"
    REPRODUCTION = "root_cause.reproduction"


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
            _normalize_context_value(item, path=f"{path}[]") for item in value
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


def _freeze_context(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
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
    exception_type: type["RootCauseError"],
    message: str,
    context: Mapping[str, Any],
) -> "RootCauseError":
    """Reconstruct a concrete exception during pickle deserialization."""

    return exception_type(message, context=context)


class RootCauseError(RuntimeError):
    """Root exception for unsafe or unverifiable Phase 3 technical failures.

    Parameters
    ----------
    message:
        Human-readable diagnostic explanation suitable for logs and CLI output.
    context:
        Optional machine-readable metadata. Values are normalized into a deeply
        immutable, deterministic and JSON-compatible representation. Context
        must contain identifiers and technical metadata only; it must never
        contain secrets, real patient data or non-synthetic clinical content.

    Notes
    -----
    Scientific outcomes such as ``INCONCLUSIVE``, ``NOT_RUN`` or ``REFUTED``
    are domain results and must not be represented with these exceptions.
    """

    code: ClassVar[ErrorCode] = ErrorCode.ROOT_CAUSE_ERROR
    category: ClassVar[ErrorCategory] = ErrorCategory.UNKNOWN
    component: ClassVar[str] = "root_cause"
    stage: ClassVar[str | None] = None

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
        """Return a stable JSON-compatible representation for external systems."""

        return {
            "type": type(self).__name__,
            "code": self.code.value,
            "category": self.category.value,
            "component": self.component,
            "stage": self.stage,
            "message": str(self),
            "context": _thaw(self.context),
        }

    def __reduce_ex__(
        self,
        protocol: int,
    ) -> tuple[Any, tuple[type["RootCauseError"], str, Mapping[str, Any]]]:
        """Preserve concrete type, message and context during pickling."""

        del protocol
        return (
            _rebuild_exception,
            (type(self), str(self), _thaw(self.context)),
        )


class RootCauseInputError(RootCauseError):
    """Raised when a Phase 3 request or external input is invalid or ambiguous."""

    code = ErrorCode.ROOT_CAUSE_INPUT
    category = ErrorCategory.INPUT
    component = "root_cause"
    stage = "input_validation"


class RootCauseIntegrityError(RootCauseError):
    """Raised when internal references, hashes or collaborator data disagree.

    This class is reserved for violations that indicate a programming defect,
    corrupted artefact or broken pipeline contract. Ordinary absence of causal
    evidence is not an integrity failure.
    """

    code = ErrorCode.ROOT_CAUSE_INTEGRITY
    category = ErrorCategory.INTEGRITY
    component = "root_cause"
    stage = "integrity_validation"


class EvidenceCollectionError(RootCauseError):
    """Raised when required causal evidence cannot be safely collected.

    Missing optional evidence should normally be recorded in the domain model.
    This exception is for unreadable, malformed, contradictory or inaccessible
    required sources where continuing would make the investigation unreliable.
    """

    code = ErrorCode.EVIDENCE_COLLECTION
    category = ErrorCategory.COLLECTION
    component = "evidence"
    stage = "evidence_collection"


class CandidateGenerationError(RootCauseError):
    """Raised when candidate rules, knowledge or protocols cannot be evaluated.

    Generating zero candidates is a valid scientific result when inputs are
    valid. This exception represents technical failure of candidate generation,
    not the absence of a plausible cause.
    """

    code = ErrorCode.CANDIDATE_GENERATION
    category = ErrorCategory.GENERATION
    component = "candidates"
    stage = "candidate_generation"


class VerificationExecutionError(RootCauseError):
    """Raised when a deterministic verifier cannot execute its declared contract.

    A verifier that runs correctly and returns ``FAILED`` or ``INCONCLUSIVE``
    must produce a :class:`VerificationResult`; only infrastructure, contract or
    unexpected execution failures cross this exception boundary.
    """

    code = ErrorCode.VERIFICATION_EXECUTION
    category = ErrorCategory.EXECUTION
    component = "verification"
    stage = "verification"


class AttributionError(RootCauseError):
    """Raised when source attribution cannot be computed safely.

    Insufficient precision is represented by a partial or ``UNKNOWN``
    attribution. This exception is reserved for malformed provenance, invalid
    source graphs or attribution-component failures.
    """

    code = ErrorCode.ATTRIBUTION
    category = ErrorCategory.ATTRIBUTION
    component = "attribution"
    stage = "source_attribution"


class ReproductionError(RootCauseError):
    """Raised when an exact reproduction plan cannot be constructed safely.

    The reproduction component only builds plans and never executes commands.
    Missing required hashes, versions, seeds or artefact references are typical
    reasons to raise this exception.
    """

    code = ErrorCode.REPRODUCTION
    category = ErrorCategory.REPRODUCTION
    component = "reproduction"
    stage = "reproduction_planning"