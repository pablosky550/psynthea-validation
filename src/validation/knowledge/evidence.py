"""Evidence acquisition and protocol-coverage services for Phase 2A.

This module creates auditable evidence observations, preserves byte-level
integrity where possible, evaluates explicit protocol requirements, and appends
new evidence to immutable investigations.

Scientific boundary
-------------------
Evidence collection is not causal interpretation.  An observation may later be
assessed as supporting, refuting, contextual or limiting for a hypothesis, but
this module never performs that assessment, changes hypothesis certainty,
selects a root cause, executes protocol procedures or publishes knowledge.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from json import dumps
from pathlib import Path
from re import compile as compile_pattern
from types import MappingProxyType
from typing import Any, Callable, Protocol, runtime_checkable

from validation.knowledge.models import EvidenceItem, EvidenceSourceKind, InvestigationCase
from validation.knowledge.protocols import (
    EvidenceRequirement,
    EvidenceRequirementLevel,
    InvestigationProtocol,
    ProtocolStep,
)

__all__ = [
    "ConcurrentEvidenceModificationError",
    "DuplicateEvidenceError",
    "EvidenceAcquisitionError",
    "EvidenceCollection",
    "EvidenceCollector",
    "EvidenceCoverage",
    "EvidenceProtocolMismatchError",
    "EvidenceRequirementCoverage",
    "EvidenceRequirementMismatchError",
    "EvidenceSourceReader",
    "FileEvidenceReader",
    "MissingRequiredEvidenceError",
    "ProtocolEvidenceAudit",
    "attach_evidence",
    "audit_protocol_evidence",
    "canonical_json_bytes",
]


class EvidenceAcquisitionError(RuntimeError):
    """Base class for evidence acquisition and validation failures."""


class DuplicateEvidenceError(EvidenceAcquisitionError):
    """Raised when one identifier describes different evidence observations."""


class ConcurrentEvidenceModificationError(EvidenceAcquisitionError):
    """Raised when a file changes while evidence bytes are being acquired."""


class EvidenceRequirementMismatchError(EvidenceAcquisitionError):
    """Raised when evidence claims an unknown or incompatible requirement."""


class EvidenceProtocolMismatchError(EvidenceAcquisitionError):
    """Raised when evidence provenance belongs to another protocol or step."""


class MissingRequiredEvidenceError(EvidenceAcquisitionError):
    """Raised when a protocol audit lacks mandatory evidence."""


_IDENTIFIER_PATTERN = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_REQUIREMENT_IDS_KEY = "protocol_requirement_ids"
_PROTOCOL_ID_KEY = "protocol_id"
_PROTOCOL_VERSION_KEY = "protocol_version"
_STEP_ID_KEY = "protocol_step_id"
_CONTENT_LENGTH_KEY = "content_length_bytes"
_MEDIA_TYPE_KEY = "media_type"
_SERIALIZATION_KEY = "serialization"
_FILE_SIZE_KEY = "file_size_bytes"
_FILE_MTIME_NS_KEY = "file_mtime_ns"
_FILE_DEVICE_KEY = "file_device"
_FILE_INODE_KEY = "file_inode"


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


def _normalize_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(UTC)


def _normalize_identifiers(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of identifiers.")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = _require_identifier(value, f"{field_name}[{index}]")
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _freeze_metadata(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise TypeError("metadata must be a mapping or None.")
    return _deep_freeze(dict(value))


def _merge_metadata(
    metadata: Mapping[str, Any] | None,
    additions: Mapping[str, Any],
) -> Mapping[str, Any]:
    merged = dict(metadata or {})
    for key, value in additions.items():
        if key in merged and merged[key] != value:
            raise ValueError(f"metadata contains reserved key {key!r} with a conflicting value.")
        merged[key] = value
    return _freeze_metadata(merged)


def _require_source_kind(value: EvidenceSourceKind) -> EvidenceSourceKind:
    if not isinstance(value, EvidenceSourceKind):
        raise TypeError(
            "source_kind must be an EvidenceSourceKind member, "
            f"got {type(value).__name__}."
        )
    return value


def _canonical_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("Structured evidence cannot contain non-finite floats.")
        return value
    if isinstance(value, datetime):
        return _normalize_datetime(value, "structured datetime").isoformat()
    if isinstance(value, Enum):
        return _canonical_json_value(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_canonical_json_value(item) for item in value]
        return sorted(
            items,
            key=lambda item: dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    raise TypeError(
        "Structured evidence contains unsupported value type "
        f"{type(value).__name__}."
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return the deterministic UTF-8 representation used for evidence hashing."""

    return dumps(
        _canonical_json_value(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _requirement_ids(item: EvidenceItem) -> tuple[str, ...]:
    raw = item.metadata.get(_REQUIREMENT_IDS_KEY, ())
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = (raw,)
    if not isinstance(raw, Sequence):
        raise EvidenceRequirementMismatchError(
            f"Evidence {item.id!r} metadata field {_REQUIREMENT_IDS_KEY!r} "
            "must be a sequence."
        )
    return _normalize_identifiers(raw, _REQUIREMENT_IDS_KEY)


@runtime_checkable
class EvidenceSourceReader(Protocol):
    """Port for reading stable bytes from an external evidence source."""

    @property
    def locator(self) -> str:
        """Return a human-auditable source locator."""

    def read(self) -> tuple[bytes, Mapping[str, Any]]:
        """Return stable source bytes and acquisition metadata."""


@dataclass(frozen=True, slots=True)
class FileEvidenceReader:
    """Read a file snapshot and reject observable concurrent modification."""

    path: Path

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            normalized = Path(self.path)
        elif isinstance(self.path, Path):
            normalized = self.path
        else:
            raise TypeError("path must be a pathlib.Path or string.")
        object.__setattr__(self, "path", normalized.expanduser())

    @property
    def locator(self) -> str:
        return str(self.path.resolve(strict=False))

    def read(self) -> tuple[bytes, Mapping[str, Any]]:
        try:
            before = self.path.stat()
            content = self.path.read_bytes()
            after = self.path.stat()
        except OSError as error:
            raise EvidenceAcquisitionError(
                f"Unable to read evidence file {self.path!s}: {error}."
            ) from error

        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if before_identity != after_identity or len(content) != after.st_size:
            raise ConcurrentEvidenceModificationError(
                f"Evidence file {self.path!s} changed while it was being read."
            )

        return content, MappingProxyType(
            {
                _FILE_SIZE_KEY: after.st_size,
                _FILE_MTIME_NS_KEY: after.st_mtime_ns,
                _FILE_DEVICE_KEY: after.st_dev,
                _FILE_INODE_KEY: after.st_ino,
            }
        )


@dataclass(frozen=True, slots=True)
class EvidenceCollection:
    """Immutable and duplicate-safe evidence collection."""

    items: tuple[EvidenceItem, ...] = ()
    _by_id: Mapping[str, EvidenceItem] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.items, (str, bytes)) or not isinstance(self.items, Sequence):
            raise TypeError("items must be a sequence of EvidenceItem values.")
        by_id: dict[str, EvidenceItem] = {}
        for index, item in enumerate(self.items):
            if not isinstance(item, EvidenceItem):
                raise TypeError(
                    f"items[{index}] must be EvidenceItem, got {type(item).__name__}."
                )
            previous = by_id.get(item.id)
            if previous is not None and previous != item:
                raise DuplicateEvidenceError(
                    f"Evidence id {item.id!r} identifies different observations."
                )
            by_id[item.id] = item
        ordered = tuple(sorted(by_id.values(), key=lambda item: item.id))
        object.__setattr__(self, "items", ordered)
        object.__setattr__(self, "_by_id", MappingProxyType(dict(by_id)))

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[EvidenceItem]:
        return iter(self.items)

    def __contains__(self, evidence_id: object) -> bool:
        return isinstance(evidence_id, str) and evidence_id in self._by_id

    def get(self, evidence_id: str) -> EvidenceItem:
        normalized = _require_identifier(evidence_id, "evidence_id")
        try:
            return self._by_id[normalized]
        except KeyError as error:
            raise KeyError(f"Unknown evidence item {normalized!r}.") from error

    def add(self, *items: EvidenceItem) -> EvidenceCollection:
        return EvidenceCollection(self.items + tuple(items))

    def merge(self, *collections: EvidenceCollection) -> EvidenceCollection:
        merged = list(self.items)
        for index, collection in enumerate(collections):
            if not isinstance(collection, EvidenceCollection):
                raise TypeError(
                    f"collections[{index}] must be EvidenceCollection, "
                    f"got {type(collection).__name__}."
                )
            merged.extend(collection.items)
        return EvidenceCollection(tuple(merged))

    def satisfying_requirement(self, requirement_id: str) -> tuple[EvidenceItem, ...]:
        normalized = _require_identifier(requirement_id, "requirement_id")
        return tuple(item for item in self.items if normalized in _requirement_ids(item))


class EvidenceCollector:
    """Create integrity-protected evidence within an optional protocol context."""

    def __init__(
        self,
        *,
        protocol: InvestigationProtocol | None = None,
        step: ProtocolStep | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if protocol is not None and not isinstance(protocol, InvestigationProtocol):
            raise TypeError("protocol must be an InvestigationProtocol or None.")
        if step is not None and not isinstance(step, ProtocolStep):
            raise TypeError("step must be a ProtocolStep or None.")
        if step is not None and protocol is None:
            raise ValueError("step requires protocol.")
        if protocol is not None and step is not None:
            try:
                canonical = protocol.step(step.id)
            except KeyError as error:
                raise ValueError(
                    f"Step {step.id!r} does not belong to {protocol.qualified_id!r}."
                ) from error
            if canonical != step:
                raise ValueError("step must equal the canonical protocol step.")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable or None.")
        self._protocol = protocol
        self._step = step
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def protocol(self) -> InvestigationProtocol | None:
        return self._protocol

    @property
    def step(self) -> ProtocolStep | None:
        return self._step

    def from_file(
        self,
        *,
        id: str,
        source_kind: EvidenceSourceKind,
        summary: str,
        path: str | Path,
        details: str | None = None,
        requirement_ids: Sequence[str] = (),
        media_type: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        collected_at: datetime | None = None,
    ) -> EvidenceItem:
        return self.from_reader(
            id=id,
            source_kind=source_kind,
            summary=summary,
            reader=FileEvidenceReader(Path(path)),
            details=details,
            requirement_ids=requirement_ids,
            media_type=media_type,
            metadata=metadata,
            collected_at=collected_at,
        )

    def from_reader(
        self,
        *,
        id: str,
        source_kind: EvidenceSourceKind,
        summary: str,
        reader: EvidenceSourceReader,
        details: str | None = None,
        requirement_ids: Sequence[str] = (),
        media_type: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        collected_at: datetime | None = None,
    ) -> EvidenceItem:
        if not isinstance(reader, EvidenceSourceReader):
            raise TypeError("reader must satisfy EvidenceSourceReader.")
        content, reader_metadata = reader.read()
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise TypeError("EvidenceSourceReader.read() must return bytes-like content.")
        payload = bytes(content)
        additions = dict(reader_metadata)
        additions[_CONTENT_LENGTH_KEY] = len(payload)
        if media_type is not None:
            additions[_MEDIA_TYPE_KEY] = _require_text(media_type, "media_type")
        return self._build(
            id=id,
            source_kind=source_kind,
            summary=summary,
            locator=reader.locator,
            details=details,
            content=payload,
            requirement_ids=requirement_ids,
            metadata=_merge_metadata(metadata, additions),
            collected_at=collected_at,
        )

    def from_bytes(
        self,
        *,
        id: str,
        source_kind: EvidenceSourceKind,
        summary: str,
        locator: str,
        content: bytes | bytearray | memoryview,
        details: str | None = None,
        requirement_ids: Sequence[str] = (),
        media_type: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        collected_at: datetime | None = None,
    ) -> EvidenceItem:
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise TypeError("content must be bytes-like.")
        payload = bytes(content)
        additions: dict[str, Any] = {_CONTENT_LENGTH_KEY: len(payload)}
        if media_type is not None:
            additions[_MEDIA_TYPE_KEY] = _require_text(media_type, "media_type")
        return self._build(
            id=id,
            source_kind=source_kind,
            summary=summary,
            locator=locator,
            details=details,
            content=payload,
            requirement_ids=requirement_ids,
            metadata=_merge_metadata(metadata, additions),
            collected_at=collected_at,
        )

    def from_text(
        self,
        *,
        id: str,
        source_kind: EvidenceSourceKind,
        summary: str,
        locator: str,
        text: str,
        details: str | None = None,
        requirement_ids: Sequence[str] = (),
        media_type: str = "text/plain; charset=utf-8",
        metadata: Mapping[str, Any] | None = None,
        collected_at: datetime | None = None,
    ) -> EvidenceItem:
        if not isinstance(text, str):
            raise TypeError(f"text must be a string, got {type(text).__name__}.")
        return self.from_bytes(
            id=id,
            source_kind=source_kind,
            summary=summary,
            locator=locator,
            content=text.encode("utf-8"),
            details=details,
            requirement_ids=requirement_ids,
            media_type=media_type,
            metadata=metadata,
            collected_at=collected_at,
        )

    def from_structure(
        self,
        *,
        id: str,
        source_kind: EvidenceSourceKind,
        summary: str,
        locator: str,
        value: Any,
        details: str | None = None,
        requirement_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
        collected_at: datetime | None = None,
    ) -> EvidenceItem:
        payload = canonical_json_bytes(value)
        return self._build(
            id=id,
            source_kind=source_kind,
            summary=summary,
            locator=locator,
            details=details,
            content=payload,
            requirement_ids=requirement_ids,
            metadata=_merge_metadata(
                metadata,
                {
                    _CONTENT_LENGTH_KEY: len(payload),
                    _MEDIA_TYPE_KEY: "application/json; charset=utf-8",
                    _SERIALIZATION_KEY: "canonical-json-v1",
                },
            ),
            collected_at=collected_at,
        )

    def observation(
        self,
        *,
        id: str,
        source_kind: EvidenceSourceKind,
        summary: str,
        locator: str,
        details: str | None = None,
        requirement_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
        collected_at: datetime | None = None,
    ) -> EvidenceItem:
        """Record non-byte evidence without claiming a content digest."""

        return self._build(
            id=id,
            source_kind=source_kind,
            summary=summary,
            locator=locator,
            details=details,
            content=None,
            requirement_ids=requirement_ids,
            metadata=_freeze_metadata(metadata),
            collected_at=collected_at,
        )

    def _validate_requirements(self, requirement_ids: Sequence[str]) -> tuple[str, ...]:
        normalized = _normalize_identifiers(requirement_ids, "requirement_ids")
        if not normalized:
            return ()
        if self._protocol is None:
            raise EvidenceRequirementMismatchError(
                "requirement_ids require an InvestigationProtocol."
            )
        protocol_ids = {
            requirement.id
            for step in self._protocol.steps
            for requirement in step.evidence_requirements
        }
        unknown = sorted(set(normalized) - protocol_ids)
        if unknown:
            raise EvidenceRequirementMismatchError(
                f"Unknown requirements for {self._protocol.qualified_id!r}: "
                + ", ".join(unknown)
                + "."
            )
        if self._step is not None:
            step_ids = {item.id for item in self._step.evidence_requirements}
            outside = sorted(set(normalized) - step_ids)
            if outside:
                raise EvidenceRequirementMismatchError(
                    f"Evidence for step {self._step.id!r} claims requirements from "
                    "another step: " + ", ".join(outside) + "."
                )
        return normalized

    def _build(
        self,
        *,
        id: str,
        source_kind: EvidenceSourceKind,
        summary: str,
        locator: str,
        details: str | None,
        content: bytes | None,
        requirement_ids: Sequence[str],
        metadata: Mapping[str, Any],
        collected_at: datetime | None,
    ) -> EvidenceItem:
        requirements = self._validate_requirements(requirement_ids)
        additions: dict[str, Any] = {}
        if requirements:
            additions[_REQUIREMENT_IDS_KEY] = requirements
        if self._protocol is not None:
            additions[_PROTOCOL_ID_KEY] = self._protocol.id
            additions[_PROTOCOL_VERSION_KEY] = self._protocol.version
        if self._step is not None:
            additions[_STEP_ID_KEY] = self._step.id
        timestamp = self._clock() if collected_at is None else collected_at
        return EvidenceItem(
            id=_require_identifier(id, "id"),
            source_kind=_require_source_kind(source_kind),
            summary=_require_text(summary, "summary"),
            locator=_require_text(locator, "locator"),
            collected_at=_normalize_datetime(timestamp, "collected_at"),
            details=_optional_text(details, "details"),
            sha256=None if content is None else sha256(content).hexdigest(),
            metadata=_merge_metadata(metadata, additions),
        )


@dataclass(frozen=True, slots=True)
class EvidenceRequirementCoverage:
    """Coverage and rejection details for one protocol requirement."""

    requirement: EvidenceRequirement
    step_id: str
    evidence: tuple[EvidenceItem, ...] = ()
    rejected_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, EvidenceRequirement):
            raise TypeError("requirement must be an EvidenceRequirement.")
        object.__setattr__(self, "step_id", _require_identifier(self.step_id, "step_id"))
        collection = EvidenceCollection(tuple(self.evidence))
        object.__setattr__(self, "evidence", collection.items)
        object.__setattr__(
            self,
            "rejected_evidence_ids",
            _normalize_identifiers(self.rejected_evidence_ids, "rejected_evidence_ids"),
        )

    @property
    def satisfied(self) -> bool:
        return bool(self.evidence)


@dataclass(frozen=True, slots=True)
class EvidenceCoverage:
    """Coverage summary for one protocol step."""

    step: ProtocolStep
    requirements: tuple[EvidenceRequirementCoverage, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.step, ProtocolStep):
            raise TypeError("step must be a ProtocolStep.")
        expected = tuple(item.id for item in self.step.evidence_requirements)
        actual = tuple(item.requirement.id for item in self.requirements)
        if actual != expected:
            raise ValueError(
                "requirements must cover every step requirement exactly once in "
                "declaration order."
            )
        if any(item.step_id != self.step.id for item in self.requirements):
            raise ValueError("All requirement coverage must reference the owning step.")
        object.__setattr__(self, "requirements", tuple(self.requirements))

    @property
    def missing_required(self) -> tuple[EvidenceRequirement, ...]:
        return tuple(
            item.requirement
            for item in self.requirements
            if item.requirement.level is EvidenceRequirementLevel.REQUIRED
            and not item.satisfied
        )

    @property
    def missing_corroborating(self) -> tuple[EvidenceRequirement, ...]:
        return tuple(
            item.requirement
            for item in self.requirements
            if item.requirement.level is EvidenceRequirementLevel.CORROBORATING
            and not item.satisfied
        )

    @property
    def complete(self) -> bool:
        return not self.missing_required


@dataclass(frozen=True, slots=True)
class ProtocolEvidenceAudit:
    """Deterministic coverage audit for one investigation protocol."""

    protocol: InvestigationProtocol
    steps: tuple[EvidenceCoverage, ...]
    unclaimed_evidence: tuple[EvidenceItem, ...] = ()
    invalid_claims: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.protocol, InvestigationProtocol):
            raise TypeError("protocol must be an InvestigationProtocol.")
        expected = tuple(step.id for step in self.protocol.steps)
        actual = tuple(coverage.step.id for coverage in self.steps)
        if actual != expected:
            raise ValueError(
                "steps must cover every protocol step exactly once in declaration order."
            )
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(
            self,
            "unclaimed_evidence",
            EvidenceCollection(tuple(self.unclaimed_evidence)).items,
        )
        if not isinstance(self.invalid_claims, Mapping):
            raise TypeError("invalid_claims must be a mapping.")
        object.__setattr__(
            self,
            "invalid_claims",
            MappingProxyType(
                {
                    _require_identifier(key, "invalid_claims key"): tuple(values)
                    for key, values in self.invalid_claims.items()
                }
            ),
        )

    @property
    def missing_required(self) -> tuple[EvidenceRequirement, ...]:
        return tuple(item for step in self.steps for item in step.missing_required)

    @property
    def missing_corroborating(self) -> tuple[EvidenceRequirement, ...]:
        return tuple(item for step in self.steps for item in step.missing_corroborating)

    @property
    def complete(self) -> bool:
        return not self.missing_required and not self.invalid_claims

    def requirement(self, requirement_id: str) -> EvidenceRequirementCoverage:
        normalized = _require_identifier(requirement_id, "requirement_id")
        for step in self.steps:
            for coverage in step.requirements:
                if coverage.requirement.id == normalized:
                    return coverage
        raise KeyError(f"Unknown evidence requirement {normalized!r}.")

    def require_complete(self) -> ProtocolEvidenceAudit:
        problems: list[str] = []
        if self.missing_required:
            problems.append(
                "missing required evidence: "
                + ", ".join(item.id for item in self.missing_required)
            )
        if self.invalid_claims:
            problems.append(
                "invalid claims: "
                + "; ".join(
                    f"{item_id} -> {', '.join(reasons)}"
                    for item_id, reasons in sorted(self.invalid_claims.items())
                )
            )
        if problems:
            raise MissingRequiredEvidenceError(
                f"Protocol {self.protocol.qualified_id!r} evidence is incomplete ("
                + "; ".join(problems)
                + ")."
            )
        return self


def _provenance_claim_errors(
    item: EvidenceItem,
    protocol: InvestigationProtocol,
    requirement_step: ProtocolStep,
) -> tuple[str, ...]:
    errors: list[str] = []
    claimed_protocol = item.metadata.get(_PROTOCOL_ID_KEY)
    claimed_version = item.metadata.get(_PROTOCOL_VERSION_KEY)
    claimed_step = item.metadata.get(_STEP_ID_KEY)
    if claimed_protocol is not None and claimed_protocol != protocol.id:
        errors.append(f"protocol_id={claimed_protocol!r}")
    if claimed_version is not None and claimed_version != protocol.version:
        errors.append(f"protocol_version={claimed_version!r}")
    if claimed_step is not None and claimed_step != requirement_step.id:
        errors.append(f"protocol_step_id={claimed_step!r}")
    return tuple(errors)


def audit_protocol_evidence(
    protocol: InvestigationProtocol,
    evidence: Sequence[EvidenceItem] | EvidenceCollection,
) -> ProtocolEvidenceAudit:
    """Evaluate explicit and provenance-compatible requirement claims.

    Source-kind equality alone never satisfies a requirement.  The evidence must
    explicitly claim the requirement and, when protocol provenance is present,
    it must match protocol id, version and owning step.
    """

    if not isinstance(protocol, InvestigationProtocol):
        raise TypeError("protocol must be an InvestigationProtocol.")
    collection = evidence if isinstance(evidence, EvidenceCollection) else EvidenceCollection(tuple(evidence))
    index = {
        requirement.id: (step, requirement)
        for step in protocol.steps
        for requirement in step.evidence_requirements
    }
    accepted: dict[str, list[EvidenceItem]] = {key: [] for key in index}
    rejected: dict[str, list[str]] = {key: [] for key in index}
    unclaimed: list[EvidenceItem] = []
    invalid: dict[str, list[str]] = {}

    for item in collection:
        claims = _requirement_ids(item)
        if not claims:
            unclaimed.append(item)
            continue
        for claim in claims:
            target = index.get(claim)
            if target is None:
                invalid.setdefault(item.id, []).append(f"unknown requirement {claim!r}")
                continue
            step, requirement = target
            provenance_errors = _provenance_claim_errors(item, protocol, step)
            if provenance_errors:
                invalid.setdefault(item.id, []).extend(provenance_errors)
                rejected[claim].append(item.id)
                continue
            if item.source_kind is not requirement.source_kind:
                invalid.setdefault(item.id, []).append(
                    f"requirement {claim!r} expects {requirement.source_kind.value}, "
                    f"got {item.source_kind.value}"
                )
                rejected[claim].append(item.id)
                continue
            accepted[claim].append(item)

    step_coverage = tuple(
        EvidenceCoverage(
            step=step,
            requirements=tuple(
                EvidenceRequirementCoverage(
                    requirement=requirement,
                    step_id=step.id,
                    evidence=tuple(accepted[requirement.id]),
                    rejected_evidence_ids=tuple(rejected[requirement.id]),
                )
                for requirement in step.evidence_requirements
            ),
        )
        for step in protocol.steps
    )
    return ProtocolEvidenceAudit(
        protocol=protocol,
        steps=step_coverage,
        unclaimed_evidence=tuple(unclaimed),
        invalid_claims={key: tuple(dict.fromkeys(values)) for key, values in invalid.items()},
    )


def attach_evidence(
    investigation: InvestigationCase,
    evidence: EvidenceItem | Sequence[EvidenceItem] | EvidenceCollection,
    *,
    updated_at: datetime | None = None,
    note: str | None = None,
) -> InvestigationCase:
    """Return a new investigation with additional uninterpreted evidence."""

    if not isinstance(investigation, InvestigationCase):
        raise TypeError("investigation must be an InvestigationCase.")
    if isinstance(evidence, EvidenceItem):
        incoming = EvidenceCollection((evidence,))
    elif isinstance(evidence, EvidenceCollection):
        incoming = evidence
    else:
        incoming = EvidenceCollection(tuple(evidence))
    merged = EvidenceCollection(investigation.evidence).merge(incoming)
    timestamp = datetime.now(UTC) if updated_at is None else _normalize_datetime(updated_at, "updated_at")
    if timestamp < investigation.updated_at:
        raise ValueError("updated_at must not precede investigation.updated_at.")
    notes = investigation.notes
    if note is not None:
        normalized_note = _require_text(note, "note")
        if normalized_note not in notes:
            notes = notes + (normalized_note,)
    return replace(
        investigation,
        evidence=merged.items,
        updated_at=timestamp,
        notes=notes,
    )