#!/usr/bin/env python3
"""Synchronise the vendored Synthea module catalogue reproducibly.

The script copies ``src/main/resources/modules`` from a local Synthea checkout
into ``resources/synthea/modules`` in psynthea-validation and writes a
machine-readable provenance manifest. Synchronisation is atomic: the existing
catalogue is replaced only after the staged copy passes integrity validation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Final, Iterable, Sequence

_SCHEMA_VERSION: Final[str] = "1.0"
_SOURCE_RELATIVE_PATH: Final[Path] = Path("src/main/resources/modules")
_DEFAULT_TARGET_RELATIVE_PATH: Final[Path] = Path("resources/synthea/modules")
_DEFAULT_MANIFEST_NAME: Final[str] = "MANIFEST.json"
_HASH_ALGORITHM: Final[str] = "sha256"
_COPY_BUFFER_SIZE: Final[int] = 1024 * 1024
_IGNORED_NAMES: Final[frozenset[str]] = frozenset({".DS_Store"})


class SynchronisationError(RuntimeError):
    """Raised when the Synthea catalogue cannot be synchronised safely."""


@dataclass(frozen=True, slots=True)
class CatalogueSnapshot:
    """Deterministic integrity summary for a module catalogue."""

    total_files: int
    json_files: int
    total_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, int | str]:
        return {
            "total_files": self.total_files,
            "json_files": self.json_files,
            "total_bytes": self.total_bytes,
            "hash_algorithm": _HASH_ALGORITHM,
            "catalogue_sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class GitProvenance:
    """Git provenance for the source Synthea checkout."""

    repository_root: Path
    commit: str
    branch: str | None
    dirty: bool
    remote_url: str | None


def _run_git(repository: Path, *arguments: str, required: bool = True) -> str | None:
    command = ("git", "-C", os.fspath(repository), *arguments)
    try:
        completed = subprocess.run(
            command,
            check=required,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise SynchronisationError("Git is required but was not found on PATH.") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or "unknown Git error"
        raise SynchronisationError(f"Git command failed: {' '.join(command)}: {detail}") from error

    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _read_git_provenance(repository: Path) -> GitProvenance:
    root_value = _run_git(repository, "rev-parse", "--show-toplevel")
    if root_value is None:
        raise SynchronisationError(f"Not a Git repository: {repository}")
    root = Path(root_value).resolve()

    commit = _run_git(root, "rev-parse", "HEAD")
    if commit is None:
        raise SynchronisationError(f"Unable to determine HEAD commit for {root}")

    branch = _run_git(root, "branch", "--show-current", required=False)
    status = _run_git(root, "status", "--porcelain", "--untracked-files=normal")
    remote_url = _run_git(root, "remote", "get-url", "origin", required=False)
    return GitProvenance(
        repository_root=root,
        commit=commit,
        branch=branch,
        dirty=bool(status),
        remote_url=remote_url,
    )


def _iter_catalogue_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name in _IGNORED_NAMES:
            continue
        yield path


def _catalogue_snapshot(root: Path) -> CatalogueSnapshot:
    if not root.is_dir():
        raise SynchronisationError(f"Module catalogue directory not found: {root}")

    digest = hashlib.sha256()
    total_files = 0
    json_files = 0
    total_bytes = 0

    for path in _iter_catalogue_files(root):
        relative_path = path.relative_to(root).as_posix()
        encoded_path = relative_path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, byteorder="big"))
        digest.update(encoded_path)

        file_size = path.stat().st_size
        digest.update(file_size.to_bytes(8, byteorder="big"))
        with path.open("rb") as stream:
            while chunk := stream.read(_COPY_BUFFER_SIZE):
                digest.update(chunk)

        total_files += 1
        json_files += path.suffix.casefold() == ".json"
        total_bytes += file_size

    if total_files == 0:
        raise SynchronisationError(f"Module catalogue is empty: {root}")
    if json_files == 0:
        raise SynchronisationError(f"Module catalogue contains no JSON files: {root}")

    return CatalogueSnapshot(
        total_files=total_files,
        json_files=json_files,
        total_bytes=total_bytes,
        sha256=digest.hexdigest(),
    )


def _copy_catalogue(source: Path, destination: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in _IGNORED_NAMES}

    shutil.copytree(
        source,
        destination,
        copy_function=shutil.copy2,
        ignore=ignore,
        symlinks=False,
    )


def _replace_directory_atomically(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.parent / f".{target.name}.backup"

    if backup.exists():
        shutil.rmtree(backup)

    try:
        if target.exists():
            target.rename(backup)
        staged.rename(target)
    except OSError as error:
        if target.exists() and not backup.exists():
            shutil.rmtree(target)
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise SynchronisationError(f"Unable to replace catalogue atomically: {error}") from error
    else:
        if backup.exists():
            shutil.rmtree(backup)


def _manifest_payload(
    *,
    provenance: GitProvenance,
    source: Path,
    project_root: Path,
    target: Path,
    snapshot: CatalogueSnapshot,
    generated_at: datetime,
) -> dict[str, object]:
    try:
        target_display = target.relative_to(project_root).as_posix()
    except ValueError:
        target_display = target.as_posix()

    return {
        "schema_version": _SCHEMA_VERSION,
        "source": {
            "repository": provenance.remote_url or "synthetichealth/synthea",
            "commit": provenance.commit,
            "branch": provenance.branch,
            "working_tree_dirty": provenance.dirty,
            "source_path": source.relative_to(provenance.repository_root).as_posix(),
        },
        "import": {
            "target_path": target_display,
            "generated_at": generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "method": "python-shutil-atomic-copy",
            **snapshot.to_dict(),
        },
    }


def _write_json_atomically(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def synchronise_catalogue(
    *,
    synthea_repository: Path,
    project_root: Path,
    target: Path | None = None,
    check_only: bool = False,
    require_clean_source: bool = False,
    generated_at: datetime | None = None,
) -> CatalogueSnapshot:
    """Synchronise or verify the vendored Synthea catalogue.

    Returns the verified source snapshot. In ``check_only`` mode no files are
    modified and the function fails if target contents or manifest provenance
    do not match the source checkout.
    """

    project_root = project_root.expanduser().resolve()
    synthea_repository = synthea_repository.expanduser().resolve()
    target = (target or (project_root / _DEFAULT_TARGET_RELATIVE_PATH)).expanduser().resolve()
    manifest_path = target.parent / _DEFAULT_MANIFEST_NAME

    provenance = _read_git_provenance(synthea_repository)
    if require_clean_source and provenance.dirty:
        raise SynchronisationError(
            "The Synthea working tree contains uncommitted changes; "
            "commit or discard them before synchronising."
        )

    source = provenance.repository_root / _SOURCE_RELATIVE_PATH
    source_snapshot = _catalogue_snapshot(source)

    if check_only:
        target_snapshot = _catalogue_snapshot(target)
        if target_snapshot != source_snapshot:
            raise SynchronisationError(
                "Vendored catalogue differs from the source checkout: "
                f"source={source_snapshot.sha256}, target={target_snapshot.sha256}."
            )
        if not manifest_path.is_file():
            raise SynchronisationError(f"Manifest not found: {manifest_path}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SynchronisationError(f"Unable to read manifest {manifest_path}: {error}") from error
        manifest_source = manifest.get("source", {})
        manifest_import = manifest.get("import", {})
        if manifest_source.get("commit") != provenance.commit:
            raise SynchronisationError("Manifest commit does not match the Synthea checkout.")
        if manifest_import.get("catalogue_sha256") != source_snapshot.sha256:
            raise SynchronisationError("Manifest catalogue hash does not match the verified catalogue.")
        return source_snapshot

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{target.name}.stage-", dir=target.parent) as temporary:
        staged = Path(temporary) / target.name
        _copy_catalogue(source, staged)
        staged_snapshot = _catalogue_snapshot(staged)
        if staged_snapshot != source_snapshot:
            raise SynchronisationError(
                "Staged catalogue failed integrity verification: "
                f"source={source_snapshot.sha256}, staged={staged_snapshot.sha256}."
            )
        _replace_directory_atomically(staged, target)

    final_snapshot = _catalogue_snapshot(target)
    if final_snapshot != source_snapshot:
        raise SynchronisationError("Final catalogue failed post-replacement integrity verification.")

    payload = _manifest_payload(
        provenance=provenance,
        source=source,
        project_root=project_root,
        target=target,
        snapshot=final_snapshot,
        generated_at=generated_at or datetime.now(UTC),
    )
    _write_json_atomically(manifest_path, payload)
    return final_snapshot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronise Synthea GMF modules into psynthea-validation.",
    )
    parser.add_argument(
        "--synthea-repository",
        type=Path,
        required=True,
        help="Path to the local synthetichealth/synthea Git checkout.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="psynthea-validation root (default: current working directory).",
    )
    parser.add_argument(
        "--target",
        type=Path,
        help="Optional catalogue destination; defaults to resources/synthea/modules.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify source, vendored catalogue and manifest without modifying files.",
    )
    parser.add_argument(
        "--require-clean-source",
        action="store_true",
        help="Reject a Synthea checkout with uncommitted or untracked changes.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        snapshot = synchronise_catalogue(
            synthea_repository=arguments.synthea_repository,
            project_root=arguments.project_root,
            target=arguments.target,
            check_only=arguments.check,
            require_clean_source=arguments.require_clean_source,
        )
    except SynchronisationError as error:
        parser.exit(1, f"error: {error}\n")

    action = "verified" if arguments.check else "synchronised"
    print(
        f"Synthea catalogue {action}: "
        f"files={snapshot.total_files}, json={snapshot.json_files}, "
        f"bytes={snapshot.total_bytes}, sha256={snapshot.sha256}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
