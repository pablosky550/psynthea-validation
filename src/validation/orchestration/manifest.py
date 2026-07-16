"""Canonical manifest persistence for reproducible validation experiments.

The manifest is the immutable, portable audit record of one experiment run. It
captures the requested configuration, execution result and references to every
persisted artefact without executing simulations or reimplementing validation,
scientific knowledge, root-cause analysis or report-rendering functionality.

Scientific guarantees
---------------------
* Canonical UTF-8 JSON with deterministic ordering and no non-finite numbers.
* Portable content: host-specific absolute workspace paths are never persisted.
* Explicit schema and producer versions.
* SHA-256 fingerprint binding the manifest to the exact ExperimentConfig.
* Verification of every referenced artefact before finalization.
* Atomic, collision-safe persistence through ExperimentWorkspace.
* Strict validation when reopening historical manifests.
* Deeply immutable payloads returned to callers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from hashlib import sha256
from json import JSONDecodeError, dumps, loads
from math import isfinite
from pathlib import Path, PurePath
from types import MappingProxyType
from typing import Any, Final

from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
    ExperimentConfig,
    ExperimentResult,
)
from validation.orchestration.workspace import (
    ExperimentWorkspace,
    WorkspaceCollisionError,
    WorkspaceIntegrityError,
    WorkspacePathError,
)

__all__ = [
    "MANIFEST_RELATIVE_PATH",
    "MANIFEST_SCHEMA_VERSION",
    "ExperimentManifest",
    "ManifestCollisionError",
    "ManifestError",
    "ManifestIntegrityError",
    "ManifestSerializationError",
]

MANIFEST_SCHEMA_VERSION: Final[int] = 3
MANIFEST_RELATIVE_PATH: Final[Path] = Path("manifest.json")
_MANIFEST_MEDIA_TYPE: Final[str] = "application/json"
_MANIFEST_PRODUCER: Final[str] = "experiment_orchestrator"
_LOGICAL_WORKSPACE: Final[str] = "."
_SHA256_HEX_LENGTH: Final[int] = 64


class ManifestError(RuntimeError):
    """Base class for manifest serialization, persistence and integrity errors."""


class ManifestSerializationError(ManifestError):
    """Raised when a domain value cannot be represented canonically as JSON."""


class ManifestIntegrityError(ManifestError):
    """Raised when manifest or referenced-artefact integrity validation fails."""


class ManifestCollisionError(ManifestError):
    """Raised when an immutable manifest already exists for the workspace."""


def _require_workspace(value: ExperimentWorkspace) -> ExperimentWorkspace:
    if not isinstance(value, ExperimentWorkspace):
        raise TypeError("workspace must be an ExperimentWorkspace.")
    return value


def _require_result(value: ExperimentResult) -> ExperimentResult:
    if not isinstance(value, ExperimentResult):
        raise TypeError("result must be an ExperimentResult.")
    return value


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


def _normalize_sha256(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name).lower()
    if len(normalized) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest.")
    return normalized


def _canonical_json_value(value: Any, *, field_path: str = "$") -> Any:
    """Convert supported domain values into deterministic JSON-compatible data."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ManifestSerializationError(
                f"{field_path} contains a non-finite floating-point value."
            )
        return value
    if isinstance(value, Enum):
        return _canonical_json_value(value.value, field_path=field_path)
    if isinstance(value, datetime):
        return _require_datetime(value, field_path).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, PurePath):
        return Path(value).as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_json_value(
                getattr(value, item.name), field_path=f"{field_path}.{item.name}"
            )
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        invalid_keys = [key for key in value if not isinstance(key, str)]
        if invalid_keys:
            raise ManifestSerializationError(
                f"{field_path} contains non-string mapping key {invalid_keys[0]!r}."
            )
        return {
            key: _canonical_json_value(value[key], field_path=f"{field_path}.{key}")
            for key in sorted(value)
        }
    if isinstance(value, (set, frozenset)):
        converted = [
            _canonical_json_value(item, field_path=f"{field_path}[]") for item in value
        ]
        return sorted(converted, key=_canonical_sort_key)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _canonical_json_value(item, field_path=f"{field_path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ManifestSerializationError(
        f"{field_path} contains unsupported value type {type(value).__name__}."
    )


def _canonical_sort_key(value: Any) -> str:
    return dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        serialized = dumps(
            _deep_thaw(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ManifestSerializationError(
            "Manifest payload cannot be serialized deterministically."
        ) from exc
    return (serialized + "\n").encode("utf-8")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _sha256_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise ManifestIntegrityError(f"Cannot read artefact: {path}") from exc
    return digest.hexdigest(), size


def _config_payload(config: ExperimentConfig) -> dict[str, Any]:
    payload = _canonical_json_value(config, field_path="$.config")
    if not isinstance(payload, dict):
        raise ManifestSerializationError("Canonical ExperimentConfig must be an object.")
    return payload


def _config_sha256(config_payload: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical_bytes(config_payload))


def _validate_workspace_binding(
    workspace: ExperimentWorkspace, result: ExperimentResult
) -> None:
    if result.experiment_id != workspace.experiment_id:
        raise ManifestIntegrityError(
            "ExperimentResult.experiment_id does not match workspace.experiment_id."
        )
    if result.run_id != workspace.run_id:
        raise ManifestIntegrityError(
            "ExperimentResult.run_id does not match workspace.run_id."
        )
    if result.config != workspace.config:
        raise ManifestIntegrityError(
            "ExperimentResult.config does not match workspace.config."
        )
    expected_root = workspace.root.resolve(strict=True)
    actual_root = result.workspace.expanduser().resolve(strict=False)
    if actual_root != expected_root:
        raise ManifestIntegrityError(
            "ExperimentResult.workspace does not match the managed workspace root."
        )


def _validate_artifact_reference(
    workspace: ExperimentWorkspace, artifact: ArtifactReference
) -> None:
    if not isinstance(artifact, ArtifactReference):
        raise TypeError("artifact must be an ArtifactReference.")
    try:
        absolute = workspace.resolve(artifact.path)
    except (WorkspaceIntegrityError, WorkspacePathError) as exc:
        raise ManifestIntegrityError(
            f"Referenced artefact escapes or violates workspace integrity: {artifact.id}"
        ) from exc
    if absolute.is_symlink() or not absolute.is_file():
        raise ManifestIntegrityError(
            "Referenced artefact is missing, symbolic or not a regular file: "
            f"{artifact.path.as_posix()}"
        )
    if artifact.sha256 is None or artifact.size_bytes is None:
        raise ManifestIntegrityError(
            f"Referenced artefact lacks complete hash metadata: {artifact.id}"
        )
    digest, size = _sha256_file(absolute)
    if digest != artifact.sha256:
        raise ManifestIntegrityError(
            f"SHA-256 mismatch for artefact {artifact.id}: "
            f"expected {artifact.sha256}, observed {digest}."
        )
    if size != artifact.size_bytes:
        raise ManifestIntegrityError(
            f"Size mismatch for artefact {artifact.id}: "
            f"expected {artifact.size_bytes}, observed {size}."
        )


def _validate_artifact_catalog(
    workspace: ExperimentWorkspace, result: ExperimentResult
) -> None:
    ids: set[str] = set()
    paths: set[Path] = set()
    for artifact in result.artifacts:
        if artifact.kind is ArtifactKind.MANIFEST:
            raise ManifestIntegrityError(
                "ExperimentResult.artifacts must not contain its own manifest reference."
            )
        if artifact.id in ids:
            raise ManifestIntegrityError(
                f"Duplicate artefact id in result catalogue: {artifact.id}"
            )
        if artifact.path in paths:
            raise ManifestIntegrityError(
                "Multiple artefact references target the same path: "
                f"{artifact.path.as_posix()}"
            )
        ids.add(artifact.id)
        paths.add(artifact.path)
        _validate_artifact_reference(workspace, artifact)


class ExperimentManifest:
    """Build, persist, read and verify one canonical experiment manifest."""

    __slots__ = ("_workspace", "_producer_version")

    def __init__(
        self, workspace: ExperimentWorkspace, *, producer_version: str
    ) -> None:
        self._workspace = _require_workspace(workspace)
        self._producer_version = _require_text(producer_version, "producer_version")

    @property
    def workspace(self) -> ExperimentWorkspace:
        return self._workspace

    @property
    def producer_version(self) -> str:
        return self._producer_version

    @property
    def path(self) -> Path:
        return self.workspace.root / MANIFEST_RELATIVE_PATH

    def build(
        self,
        result: ExperimentResult,
        *,
        generated_at: datetime | None = None,
        verify_artifacts: bool = True,
    ) -> Mapping[str, Any]:
        """Return a deeply immutable canonical payload without writing to disk."""

        normalized_result = _require_result(result)
        timestamp = _require_datetime(
            generated_at if generated_at is not None else datetime.now(UTC),
            "generated_at",
        )
        if not isinstance(verify_artifacts, bool):
            raise TypeError("verify_artifacts must be a boolean.")

        _validate_workspace_binding(self.workspace, normalized_result)
        if verify_artifacts:
            _validate_artifact_catalog(self.workspace, normalized_result)

        config = _config_payload(normalized_result.config)
        result_payload = _canonical_json_value(normalized_result, field_path="$.result")
        if not isinstance(result_payload, dict):
            raise ManifestSerializationError("Canonical ExperimentResult must be an object.")

        payload = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "producer": {
                "name": _MANIFEST_PRODUCER,
                "version": self.producer_version,
            },
            "generated_at": timestamp.isoformat(),
            "experiment_id": normalized_result.experiment_id,
            "run_id": normalized_result.run_id,
            "workspace": _LOGICAL_WORKSPACE,
            "config_sha256": _config_sha256(config),
            "config": config,
            "result": result_payload,
        }
        canonical = _canonical_json_value(payload)
        if not isinstance(canonical, dict):
            raise ManifestSerializationError("Canonical manifest root must be an object.")
        return _deep_freeze(canonical)

    def write(
        self,
        result: ExperimentResult,
        *,
        generated_at: datetime | None = None,
        verify_artifacts: bool = True,
        overwrite: bool = False,
    ) -> ArtifactReference:
        """Atomically persist the immutable manifest and return its reference."""

        if not isinstance(overwrite, bool):
            raise TypeError("overwrite must be a boolean.")
        payload = self.build(
            result,
            generated_at=generated_at,
            verify_artifacts=verify_artifacts,
        )
        try:
            path = self.workspace.write_bytes(
                MANIFEST_RELATIVE_PATH,
                _canonical_bytes(payload),
                overwrite=overwrite,
            )
        except WorkspaceCollisionError as exc:
            raise ManifestCollisionError(
                f"Manifest already exists for run {self.workspace.run_id}."
            ) from exc
        except (WorkspaceIntegrityError, WorkspacePathError) as exc:
            raise ManifestIntegrityError(
                "Workspace rejected manifest persistence."
            ) from exc

        return self.workspace.artifact_reference(
            artifact_id="experiment.manifest",
            kind=ArtifactKind.MANIFEST,
            path=path,
            media_type=_MANIFEST_MEDIA_TYPE,
            producer=_MANIFEST_PRODUCER,
            metadata={
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "producer_version": self.producer_version,
                "config_sha256": payload["config_sha256"],
            },
        )

    def read(
        self,
        *,
        verify_self_hash: str | None = None,
    ) -> Mapping[str, Any]:
        """Read and strictly validate an existing UTF-8 JSON manifest."""

        try:
            path = self.workspace.resolve(MANIFEST_RELATIVE_PATH)
        except (WorkspaceIntegrityError, WorkspacePathError) as exc:
            raise ManifestIntegrityError("Manifest path violates workspace integrity.") from exc
        if path.is_symlink() or not path.is_file():
            raise ManifestIntegrityError(
                f"Manifest is missing, symbolic or not a regular file: {path}"
            )

        digest, _ = _sha256_file(path)
        if verify_self_hash is not None:
            expected = _normalize_sha256(verify_self_hash, "verify_self_hash")
            if digest != expected:
                raise ManifestIntegrityError(
                    f"Manifest SHA-256 mismatch: expected {expected}, observed {digest}."
                )

        try:
            payload = loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, JSONDecodeError) as exc:
            raise ManifestIntegrityError("Manifest is not valid UTF-8 JSON.") from exc
        if not isinstance(payload, dict):
            raise ManifestIntegrityError("Manifest root must be a JSON object.")

        self._validate_loaded_payload(payload)
        canonical = _canonical_json_value(payload)
        if not isinstance(canonical, dict):
            raise ManifestIntegrityError("Canonical manifest root must be an object.")
        return _deep_freeze(canonical)

    def reference(self) -> ArtifactReference:
        """Return a verified reference for an already persisted manifest."""

        return self.workspace.artifact_reference(
            artifact_id="experiment.manifest",
            kind=ArtifactKind.MANIFEST,
            path=MANIFEST_RELATIVE_PATH,
            media_type=_MANIFEST_MEDIA_TYPE,
            producer=_MANIFEST_PRODUCER,
            metadata={
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "producer_version": self.producer_version,
            },
        )

    def verify(
        self,
        *,
        expected_reference: ArtifactReference | None = None,
    ) -> Mapping[str, Any]:
        """Verify manifest structure and an optional external hash reference."""

        expected_hash: str | None = None
        if expected_reference is not None:
            if not isinstance(expected_reference, ArtifactReference):
                raise TypeError("expected_reference must be an ArtifactReference.")
            if expected_reference.kind is not ArtifactKind.MANIFEST:
                raise ManifestIntegrityError(
                    "expected_reference must have ArtifactKind.MANIFEST."
                )
            if expected_reference.path != MANIFEST_RELATIVE_PATH:
                raise ManifestIntegrityError(
                    "expected_reference points to an unexpected manifest path."
                )
            if expected_reference.sha256 is None:
                raise ManifestIntegrityError(
                    "expected_reference must contain a SHA-256 digest."
                )
            expected_hash = expected_reference.sha256

        payload = self.read(verify_self_hash=expected_hash)
        if expected_reference is not None:
            _validate_artifact_reference(self.workspace, expected_reference)
        return payload

    def _validate_loaded_payload(self, payload: Mapping[str, Any]) -> None:
        if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise ManifestIntegrityError(
                f"Unsupported manifest schema_version {payload.get('schema_version')!r}; "
                f"expected {MANIFEST_SCHEMA_VERSION}."
            )
        if payload.get("experiment_id") != self.workspace.experiment_id:
            raise ManifestIntegrityError(
                "Manifest experiment_id does not match workspace ownership."
            )
        if payload.get("run_id") != self.workspace.run_id:
            raise ManifestIntegrityError(
                "Manifest run_id does not match workspace ownership."
            )
        if payload.get("workspace") != _LOGICAL_WORKSPACE:
            raise ManifestIntegrityError(
                "Manifest workspace must use the portable logical root '.'."
            )

        producer = payload.get("producer")
        if not isinstance(producer, Mapping):
            raise ManifestIntegrityError("Manifest producer must be an object.")
        if producer.get("name") != _MANIFEST_PRODUCER:
            raise ManifestIntegrityError("Manifest producer name is invalid.")
        if producer.get("version") != self.producer_version:
            raise ManifestIntegrityError(
                "Manifest producer version does not match the active orchestrator."
            )

        generated_at = payload.get("generated_at")
        try:
            parsed = datetime.fromisoformat(generated_at)
        except (TypeError, ValueError) as exc:
            raise ManifestIntegrityError(
                "Manifest generated_at must be a valid ISO-8601 datetime."
            ) from exc
        _require_datetime(parsed, "generated_at")

        config = payload.get("config")
        result = payload.get("result")
        if not isinstance(config, Mapping):
            raise ManifestIntegrityError("Manifest config must be an object.")
        if not isinstance(result, Mapping):
            raise ManifestIntegrityError("Manifest result must be an object.")

        expected_config = _config_payload(self.workspace.config)
        if dict(config) != expected_config:
            raise ManifestIntegrityError(
                "Manifest config does not match the workspace ExperimentConfig."
            )
        observed_config_hash = payload.get("config_sha256")
        if not isinstance(observed_config_hash, str):
            raise ManifestIntegrityError("Manifest config_sha256 must be a string.")
        try:
            normalized_hash = _normalize_sha256(
                observed_config_hash, "config_sha256"
            )
        except (TypeError, ValueError) as exc:
            raise ManifestIntegrityError("Manifest config_sha256 is invalid.") from exc
        expected_hash = _config_sha256(expected_config)
        if normalized_hash != expected_hash:
            raise ManifestIntegrityError(
                "Manifest config_sha256 does not match its canonical configuration."
            )

        if result.get("experiment_id") != self.workspace.experiment_id:
            raise ManifestIntegrityError(
                "Manifest result.experiment_id does not match workspace ownership."
            )
        if result.get("run_id") != self.workspace.run_id:
            raise ManifestIntegrityError(
                "Manifest result.run_id does not match workspace ownership."
            )
        if result.get("config") != config:
            raise ManifestIntegrityError(
                "Manifest top-level config differs from result.config."
            )
        if result.get("workspace") != self.workspace.root.as_posix():
            raise ManifestIntegrityError(
                "Manifest result.workspace does not match the managed workspace root."
            )