"""Filesystem boundary for reproducible Phase 2B experiment runs.

The orchestration layer needs a deterministic, auditable and safe workspace for
all simulator outputs, normalized cohorts, validation results, scientific
knowledge artefacts and reports.  This module owns that boundary.

Design constraints
------------------
* A workspace is created once for one ``experiment_id`` / ``run_id`` pair.
* Existing non-empty directories are never silently reused.
* All managed paths remain below the workspace root, including through
  symlinks.
* Writes are atomic at the target-path level.
* Persisted files can be converted into immutable ``ArtifactReference`` values.
* The service performs no simulation, validation, interpretation or reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from enum import Enum
from json import dumps, loads
import os
from pathlib import Path, PurePath
from tempfile import NamedTemporaryFile
from typing import Any, Mapping

from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
    ExperimentConfig,
    SimulatorKind,
)

__all__ = [
    "ExperimentWorkspace",
    "WorkspaceCollisionError",
    "WorkspaceError",
    "WorkspaceIntegrityError",
    "WorkspaceLayout",
    "WorkspacePathError",
]


_MARKER_FILENAME = ".orchestration-workspace.json"
_MARKER_SCHEMA_VERSION = 2
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


def _canonical_json_value(value: Any) -> Any:
    """Convert supported domain values into deterministic JSON-compatible data."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return _require_datetime(value, "datetime").isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical_json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Configuration mappings must use string keys.")
            normalized[key] = _canonical_json_value(item)
        return normalized
    if isinstance(value, (tuple, list)):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical_json_value(item) for item in value), key=repr)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported configuration value for fingerprinting: {type(value).__name__}.")


def _config_fingerprint(config: ExperimentConfig) -> str:
    payload = dumps(
        _canonical_json_value(config),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync for durable rename/link metadata."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class WorkspaceError(RuntimeError):
    """Base class for workspace lifecycle and integrity failures."""


class WorkspaceCollisionError(WorkspaceError):
    """Raised when a requested workspace path is already occupied."""


class WorkspaceIntegrityError(WorkspaceError):
    """Raised when an existing workspace marker is missing or inconsistent."""


class WorkspacePathError(WorkspaceError):
    """Raised when a path escapes the managed workspace boundary."""


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
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


def _relative_path(value: Path | str, field_name: str) -> Path:
    if isinstance(value, str):
        value = _require_text(value, field_name)
    elif not isinstance(value, PurePath):
        raise TypeError(f"{field_name} must be a path or string.")

    path = Path(value)
    if path.is_absolute():
        raise WorkspacePathError(f"{field_name} must be relative to the workspace root.")
    if str(path).strip() in {"", "."}:
        raise WorkspacePathError(f"{field_name} must identify a concrete path.")
    if ".." in path.parts:
        raise WorkspacePathError(f"{field_name} must not escape the workspace root.")
    return path


def _media_type(value: str) -> str:
    normalized = _require_text(value, "media_type")
    if "/" not in normalized or normalized.startswith("/") or normalized.endswith("/"):
        raise ValueError("media_type must be a valid type/subtype value.")
    return normalized


def _safe_component(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    forbidden = set('<>:"/\\|?*')
    if (
        normalized in {".", ".."}
        or any(character in forbidden or ord(character) < 32 for character in normalized)
        or normalized.endswith((" ", "."))
        or normalized.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
    ):
        raise ValueError(
            f"{field_name} must be a portable single path component without reserved characters."
        )
    return normalized


@dataclass(frozen=True, slots=True)
class WorkspaceLayout:
    """Canonical directory layout for one experiment run."""

    root: Path
    config: Path
    simulators: Path
    synthea: Path
    psynthea: Path
    normalized: Path
    validation: Path
    knowledge: Path
    report: Path
    logs: Path
    temporary: Path

    @classmethod
    def from_root(cls, root: Path) -> "WorkspaceLayout":
        root = Path(root)
        simulators = root / "simulators"
        return cls(
            root=root,
            config=root / "config",
            simulators=simulators,
            synthea=simulators / SimulatorKind.SYNTHEA.value,
            psynthea=simulators / SimulatorKind.PSYNTHEA.value,
            normalized=root / "normalized",
            validation=root / "validation",
            knowledge=root / "knowledge",
            report=root / "report",
            logs=root / "logs",
            temporary=root / ".tmp",
        )

    def directories(self) -> tuple[Path, ...]:
        """Return the full deterministic directory set in creation order."""

        return (
            self.root,
            self.config,
            self.simulators,
            self.synthea,
            self.synthea / "raw",
            self.synthea / "logs",
            self.psynthea,
            self.psynthea / "raw",
            self.psynthea / "logs",
            self.normalized,
            self.validation,
            self.validation / "figures",
            self.knowledge,
            self.knowledge / "evidence",
            self.report,
            self.report / "assets",
            self.logs,
            self.temporary,
        )


class ExperimentWorkspace:
    """Create and manage one safe experiment workspace.

    Instances are obtained through :meth:`create` or :meth:`open`.  Direct
    construction is intentionally unsupported so marker validation cannot be
    bypassed accidentally.
    """

    __slots__ = ("_config", "_run_id", "_layout", "_created_at")

    def __init__(
        self,
        *,
        config: ExperimentConfig,
        run_id: str,
        layout: WorkspaceLayout,
        created_at: datetime,
    ) -> None:
        self._config = config
        self._run_id = run_id
        self._layout = layout
        self._created_at = created_at

    @property
    def config(self) -> ExperimentConfig:
        return self._config

    @property
    def experiment_id(self) -> str:
        return self._config.id

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def root(self) -> Path:
        return self._layout.root

    @property
    def layout(self) -> WorkspaceLayout:
        return self._layout

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @classmethod
    def create(
        cls,
        config: ExperimentConfig,
        run_id: str,
        *,
        created_at: datetime | None = None,
    ) -> "ExperimentWorkspace":
        """Create a new workspace and fail closed on any collision.

        ``output_root / experiment_id / run_id`` is the only path constructed.
        A pre-existing run directory is rejected, even when empty, because silent
        reuse would weaken reproducibility and provenance guarantees.
        """

        if not isinstance(config, ExperimentConfig):
            raise TypeError("config must be an ExperimentConfig.")
        safe_run_id = _safe_component(run_id, "run_id")
        timestamp = _require_datetime(created_at or datetime.now(UTC), "created_at")

        output_root = config.output_root.expanduser().resolve(strict=False)
        experiment_root = output_root / _safe_component(config.id, "experiment_id")
        root = experiment_root / safe_run_id

        if root.exists() or root.is_symlink():
            raise WorkspaceCollisionError(f"Workspace already exists: {root}")

        layout = WorkspaceLayout.from_root(root)
        try:
            for directory in layout.directories():
                directory.mkdir(parents=True, exist_ok=False)
            workspace = cls(
                config=config,
                run_id=safe_run_id,
                layout=layout,
                created_at=timestamp,
            )
            workspace._write_marker(exclusive=True)
            return workspace
        except Exception:
            # Best-effort rollback is intentionally conservative: remove only
            # directories created by this call and only while they are empty.
            for directory in reversed(layout.directories()):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise

    @classmethod
    def open(cls, config: ExperimentConfig, run_id: str) -> "ExperimentWorkspace":
        """Open an existing workspace after validating its ownership marker."""

        if not isinstance(config, ExperimentConfig):
            raise TypeError("config must be an ExperimentConfig.")
        safe_run_id = _safe_component(run_id, "run_id")
        root = (
            config.output_root.expanduser().resolve(strict=False)
            / _safe_component(config.id, "experiment_id")
            / safe_run_id
        )
        layout = WorkspaceLayout.from_root(root)
        marker = root / _MARKER_FILENAME
        if root.is_symlink() or not root.is_dir() or marker.is_symlink() or not marker.is_file():
            raise WorkspaceIntegrityError(
                f"Workspace is missing a regular ownership marker: {marker}"
            )

        payload = cls._read_marker(marker)
        cls._validate_marker(payload, config=config, run_id=safe_run_id, root=root)

        for directory in layout.directories():
            if directory.is_symlink() or not directory.is_dir():
                raise WorkspaceIntegrityError(
                    f"Workspace directory is missing, symbolic, or not a directory: {directory}"
                )

        created_at_raw = payload.get("created_at")
        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except (TypeError, ValueError) as exc:
            raise WorkspaceIntegrityError("Workspace marker contains invalid created_at.") from exc

        return cls(
            config=config,
            run_id=safe_run_id,
            layout=layout,
            created_at=_require_datetime(created_at, "created_at"),
        )

    def resolve(self, relative_path: Path | str, *, parent: bool = False) -> Path:
        """Resolve a managed path and reject lexical or symlink escapes.

        When ``parent`` is true, the parent directory is created after the
        boundary check.  The target itself is never created by this method.
        """

        relative = _relative_path(relative_path, "relative_path")
        candidate = self.root / relative
        root_resolved = self.root.resolve(strict=True)

        # Resolve the nearest existing ancestor to detect symlink escapes while
        # still allowing new files below not-yet-created directories.
        ancestor = candidate
        suffix: list[str] = []
        while not ancestor.exists() and not ancestor.is_symlink():
            suffix.append(ancestor.name)
            ancestor = ancestor.parent
        ancestor_resolved = ancestor.resolve(strict=True)
        reconstructed = ancestor_resolved.joinpath(*reversed(suffix))

        try:
            reconstructed.relative_to(root_resolved)
        except ValueError as exc:
            raise WorkspacePathError(
                f"Managed path escapes workspace root: {relative}"
            ) from exc

        if parent:
            reconstructed.parent.mkdir(parents=True, exist_ok=True)
            # Validate again because a concurrent actor could have inserted a
            # symlink while parent directories were being created.
            parent_resolved = reconstructed.parent.resolve(strict=True)
            try:
                parent_resolved.relative_to(root_resolved)
            except ValueError as exc:
                raise WorkspacePathError(
                    f"Managed path parent escapes workspace root: {relative}"
                ) from exc

        return reconstructed

    def relative(self, path: Path | str) -> Path:
        """Return a workspace-relative path after strict boundary validation."""

        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            return _relative_path(candidate, "path")

        root_resolved = self.root.resolve(strict=True)
        candidate_resolved = candidate.resolve(strict=False)
        try:
            return candidate_resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise WorkspacePathError(f"Path is outside workspace: {candidate}") from exc

    def write_bytes(
        self,
        relative_path: Path | str,
        content: bytes,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Atomically persist bytes below the workspace root."""

        if not isinstance(content, bytes):
            raise TypeError("content must be bytes.")
        target = self.resolve(relative_path, parent=True)
        if target.exists() and not overwrite:
            raise WorkspaceCollisionError(f"Artifact already exists: {target}")
        if target.exists() and not target.is_file():
            raise WorkspaceCollisionError(f"Target exists and is not a file: {target}")

        temporary_directory = self.layout.temporary.resolve(strict=True)
        with NamedTemporaryFile(
            mode="wb",
            prefix="write-",
            suffix=".tmp",
            dir=temporary_directory,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            try:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise

        try:
            if overwrite:
                os.replace(temporary_path, target)
            else:
                try:
                    os.link(temporary_path, target)
                except FileExistsError as exc:
                    raise WorkspaceCollisionError(f"Artifact already exists: {target}") from exc
                temporary_path.unlink()
            _fsync_directory(target.parent)
        finally:
            temporary_path.unlink(missing_ok=True)

        return target

    def write_text(
        self,
        relative_path: Path | str,
        content: str,
        *,
        encoding: str = "utf-8",
        overwrite: bool = False,
    ) -> Path:
        """Atomically persist text using an explicit encoding."""

        if not isinstance(content, str):
            raise TypeError("content must be a string.")
        normalized_encoding = _require_text(encoding, "encoding")
        return self.write_bytes(
            relative_path,
            content.encode(normalized_encoding),
            overwrite=overwrite,
        )

    def write_json(
        self,
        relative_path: Path | str,
        payload: Mapping[str, Any],
        *,
        overwrite: bool = False,
    ) -> Path:
        """Persist deterministic UTF-8 JSON suitable for hashing and auditing."""

        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping.")
        serialized = dumps(
            dict(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self.write_text(
            relative_path,
            serialized + "\n",
            overwrite=overwrite,
        )

    def artifact_reference(
        self,
        *,
        artifact_id: str,
        kind: ArtifactKind,
        path: Path | str,
        media_type: str,
        producer: str | None = None,
        created_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ArtifactReference:
        """Build a verified immutable reference for an existing regular file."""

        if not isinstance(kind, ArtifactKind):
            raise TypeError("kind must be an ArtifactKind member.")
        relative = self.relative(path)
        absolute = self.resolve(relative)
        if not absolute.is_file() or absolute.is_symlink():
            raise WorkspaceIntegrityError(
                f"Artifact path must be an existing regular non-symlink file: {absolute}"
            )

        digest = sha256()
        size = 0
        with absolute.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)

        timestamp = _require_datetime(created_at or datetime.now(UTC), "created_at")
        return ArtifactReference(
            id=artifact_id,
            kind=kind,
            path=relative,
            media_type=_media_type(media_type),
            created_at=timestamp,
            sha256=digest.hexdigest(),
            size_bytes=size,
            producer=producer,
            metadata=metadata or {},
        )

    def simulator_raw_directory(self, simulator: SimulatorKind) -> Path:
        """Return the canonical raw-output directory for a simulator."""

        if not isinstance(simulator, SimulatorKind):
            raise TypeError("simulator must be a SimulatorKind member.")
        base = self.layout.synthea if simulator is SimulatorKind.SYNTHEA else self.layout.psynthea
        return base / "raw"

    def simulator_log_directory(self, simulator: SimulatorKind) -> Path:
        """Return the canonical log directory for a simulator."""

        if not isinstance(simulator, SimulatorKind):
            raise TypeError("simulator must be a SimulatorKind member.")
        base = self.layout.synthea if simulator is SimulatorKind.SYNTHEA else self.layout.psynthea
        return base / "logs"

    def _write_marker(self, *, exclusive: bool) -> None:
        marker = self.root / _MARKER_FILENAME
        payload = {
            "schema_version": _MARKER_SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "workspace_root": str(self.root.resolve(strict=True)),
            "config_sha256": _config_fingerprint(self.config),
        }
        serialized = (
            dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        mode = "x" if exclusive else "w"
        with marker.open(mode, encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(marker.parent)

    @staticmethod
    def _read_marker(marker: Path) -> Mapping[str, Any]:
        try:
            payload = loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WorkspaceIntegrityError(f"Cannot read workspace marker: {marker}") from exc
        if not isinstance(payload, dict):
            raise WorkspaceIntegrityError("Workspace marker must contain a JSON object.")
        return payload

    @staticmethod
    def _validate_marker(
        payload: Mapping[str, Any],
        *,
        config: ExperimentConfig,
        run_id: str,
        root: Path,
    ) -> None:
        expected = {
            "schema_version": _MARKER_SCHEMA_VERSION,
            "experiment_id": config.id,
            "run_id": run_id,
            "workspace_root": str(root.resolve(strict=True)),
            "config_sha256": _config_fingerprint(config),
        }
        for key, expected_value in expected.items():
            if payload.get(key) != expected_value:
                raise WorkspaceIntegrityError(
                    f"Workspace marker field {key!r} is inconsistent: "
                    f"expected {expected_value!r}, got {payload.get(key)!r}."
                )