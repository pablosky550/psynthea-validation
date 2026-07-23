"""Tests for reproducible Synthea module catalogue synchronisation."""

from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


_SCRIPT = Path(__file__).parents[3] / "scripts" / "sync_synthea_modules.py"
_SPEC = importlib.util.spec_from_file_location("sync_synthea_modules", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

SynchronisationError = _MODULE.SynchronisationError
synchronise_catalogue = _MODULE.synchronise_catalogue


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _synthea_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "synthea"
    modules = repository / "src/main/resources/modules"
    (modules / "medications").mkdir(parents=True)
    (modules / "hypertension.json").write_text('{"name":"Hypertension"}\n', encoding="utf-8")
    (modules / "medications/hypertension_medication.json").write_text(
        '{"name":"Hypertension Medication"}\n',
        encoding="utf-8",
    )
    (modules / ".DS_Store").write_bytes(b"ignored")

    subprocess.run(("git", "init", str(repository)), check=True, capture_output=True)
    _git(repository, "config", "user.email", "tests@example.org")
    _git(repository, "config", "user.name", "Validation Tests")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "test catalogue")
    return repository


def test_synchronise_copies_catalogue_and_writes_manifest(tmp_path: Path) -> None:
    repository = _synthea_repository(tmp_path)
    project_root = tmp_path / "validation"
    generated_at = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)

    snapshot = synchronise_catalogue(
        synthea_repository=repository,
        project_root=project_root,
        generated_at=generated_at,
    )

    target = project_root / "resources/synthea/modules"
    assert snapshot.total_files == 2
    assert snapshot.json_files == 2
    assert (target / "hypertension.json").is_file()
    assert (target / "medications/hypertension_medication.json").is_file()
    assert not (target / ".DS_Store").exists()

    manifest = json.loads(
        (project_root / "resources/synthea/MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == "1.0"
    assert manifest["source"]["commit"] == _git(repository, "rev-parse", "HEAD")
    assert manifest["source"]["working_tree_dirty"] is False
    assert manifest["import"]["generated_at"] == "2026-07-22T08:00:00Z"
    assert manifest["import"]["total_files"] == 2
    assert manifest["import"]["catalogue_sha256"] == snapshot.sha256


def test_synchronise_removes_files_absent_from_source(tmp_path: Path) -> None:
    repository = _synthea_repository(tmp_path)
    project_root = tmp_path / "validation"
    target = project_root / "resources/synthea/modules"
    target.mkdir(parents=True)
    (target / "obsolete.json").write_text("{}", encoding="utf-8")

    synchronise_catalogue(synthea_repository=repository, project_root=project_root)

    assert not (target / "obsolete.json").exists()


def test_check_detects_target_drift(tmp_path: Path) -> None:
    repository = _synthea_repository(tmp_path)
    project_root = tmp_path / "validation"
    synchronise_catalogue(synthea_repository=repository, project_root=project_root)
    target_file = project_root / "resources/synthea/modules/hypertension.json"
    target_file.write_text('{"modified":true}\n', encoding="utf-8")

    with pytest.raises(SynchronisationError, match="differs from the source"):
        synchronise_catalogue(
            synthea_repository=repository,
            project_root=project_root,
            check_only=True,
        )


def test_require_clean_source_rejects_uncommitted_changes(tmp_path: Path) -> None:
    repository = _synthea_repository(tmp_path)
    project_root = tmp_path / "validation"
    source_file = repository / "src/main/resources/modules/hypertension.json"
    source_file.write_text('{"changed":true}\n', encoding="utf-8")

    with pytest.raises(SynchronisationError, match="uncommitted changes"):
        synchronise_catalogue(
            synthea_repository=repository,
            project_root=project_root,
            require_clean_source=True,
        )
