from __future__ import annotations

from datetime import UTC, datetime
from json import loads
from pathlib import Path

import pytest

from validation.orchestration.models import (
    ArtifactKind,
    CohortConfig,
    ExperimentConfig,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
)
from validation.orchestration.workspace import (
    ExperimentWorkspace,
    WorkspaceCollisionError,
    WorkspaceIntegrityError,
    WorkspacePathError,
)


def _config(tmp_path: Path) -> ExperimentConfig:
    cohort = CohortConfig(population=100, seed=42, modules=("hypertension",))
    simulators = (
        SimulatorConfig(
            kind=SimulatorKind.SYNTHEA,
            command=("java", "-jar", "synthea.jar"),
            working_directory=tmp_path / "synthea-src",
            output_subdirectory="synthea",
        ),
        SimulatorConfig(
            kind=SimulatorKind.PSYNTHEA,
            command=("python", "-m", "psynthea"),
            working_directory=tmp_path / "psynthea-src",
            output_subdirectory="psynthea",
        ),
    )
    return ExperimentConfig(
        id="hypertension-equivalence",
        name="Hypertension equivalence",
        cohort=cohort,
        simulators=simulators,
        output_root=tmp_path / "runs",
        report_formats=(ReportFormat.HTML, ReportFormat.JSON),
    )


def test_create_builds_canonical_layout_and_marker(tmp_path: Path) -> None:
    config = _config(tmp_path)
    created_at = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)

    workspace = ExperimentWorkspace.create(config, "run-001", created_at=created_at)

    assert workspace.root == (config.output_root / config.id / "run-001").resolve()
    assert all(path.is_dir() for path in workspace.layout.directories())
    marker = workspace.root / ".orchestration-workspace.json"
    payload = loads(marker.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["experiment_id"] == config.id
    assert payload["run_id"] == "run-001"
    assert payload["created_at"] == created_at.isoformat()


def test_create_rejects_existing_workspace_even_when_empty(tmp_path: Path) -> None:
    config = _config(tmp_path)
    root = config.output_root / config.id / "run-001"
    root.mkdir(parents=True)

    with pytest.raises(WorkspaceCollisionError):
        ExperimentWorkspace.create(config, "run-001")


def test_open_validates_marker_and_layout(tmp_path: Path) -> None:
    config = _config(tmp_path)
    created = ExperimentWorkspace.create(config, "run-001")

    reopened = ExperimentWorkspace.open(config, "run-001")

    assert reopened.root == created.root
    assert reopened.created_at == created.created_at


def test_open_rejects_tampered_marker(tmp_path: Path) -> None:
    config = _config(tmp_path)
    workspace = ExperimentWorkspace.create(config, "run-001")
    marker = workspace.root / ".orchestration-workspace.json"
    payload = loads(marker.read_text(encoding="utf-8"))
    payload["experiment_id"] = "other"
    marker.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(WorkspaceIntegrityError, match="experiment_id"):
        ExperimentWorkspace.open(config, "run-001")


def test_resolve_rejects_lexical_escape(tmp_path: Path) -> None:
    workspace = ExperimentWorkspace.create(_config(tmp_path), "run-001")

    with pytest.raises(WorkspacePathError):
        workspace.resolve("../outside.txt")


def test_resolve_rejects_symlink_escape(tmp_path: Path) -> None:
    workspace = ExperimentWorkspace.create(_config(tmp_path), "run-001")
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace.root / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(WorkspacePathError):
        workspace.resolve("escape/file.txt", parent=True)


def test_atomic_writes_are_collision_safe_and_overwritable(tmp_path: Path) -> None:
    workspace = ExperimentWorkspace.create(_config(tmp_path), "run-001")

    target = workspace.write_text("config/config.json", "first")
    assert target.read_text(encoding="utf-8") == "first"

    with pytest.raises(WorkspaceCollisionError):
        workspace.write_text("config/config.json", "second")

    workspace.write_text("config/config.json", "second", overwrite=True)
    assert target.read_text(encoding="utf-8") == "second"
    assert not tuple(workspace.layout.temporary.iterdir())


def test_write_json_is_deterministic(tmp_path: Path) -> None:
    workspace = ExperimentWorkspace.create(_config(tmp_path), "run-001")

    path = workspace.write_json("config/snapshot.json", {"b": 2, "a": 1})

    assert path.read_bytes() == b'{"a":1,"b":2}\n'


def test_artifact_reference_hashes_existing_file(tmp_path: Path) -> None:
    workspace = ExperimentWorkspace.create(_config(tmp_path), "run-001")
    path = workspace.write_bytes("validation/metrics.json", b"{}\n")
    created_at = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)

    artifact = workspace.artifact_reference(
        artifact_id="validation.metrics",
        kind=ArtifactKind.VALIDATION_RESULT,
        path=path,
        media_type="application/json",
        producer="validation_engine",
        created_at=created_at,
    )

    assert artifact.path == Path("validation/metrics.json")
    assert artifact.size_bytes == 3
    assert artifact.sha256 == "ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356"
    assert artifact.created_at == created_at


def test_artifact_reference_rejects_symlink(tmp_path: Path) -> None:
    workspace = ExperimentWorkspace.create(_config(tmp_path), "run-001")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = workspace.root / "validation" / "link.txt"
    link.symlink_to(outside)

    with pytest.raises((WorkspaceIntegrityError, WorkspacePathError)):
        workspace.artifact_reference(
            artifact_id="validation.link",
            kind=ArtifactKind.OTHER,
            path=link,
            media_type="text/plain",
        )


def test_simulator_directories_are_stable(tmp_path: Path) -> None:
    workspace = ExperimentWorkspace.create(_config(tmp_path), "run-001")

    assert workspace.simulator_raw_directory(SimulatorKind.SYNTHEA) == (
        workspace.root / "simulators" / "synthea" / "raw"
    )
    assert workspace.simulator_log_directory(SimulatorKind.PSYNTHEA) == (
        workspace.root / "simulators" / "psynthea" / "logs"
    )


def test_open_rejects_configuration_drift(tmp_path: Path) -> None:
    config = _config(tmp_path)
    ExperimentWorkspace.create(config, "run-001")
    changed = ExperimentConfig(
        id=config.id,
        name=config.name,
        cohort=CohortConfig(population=101, seed=42, modules=("hypertension",)),
        simulators=config.simulators,
        output_root=config.output_root,
        report_formats=config.report_formats,
    )

    with pytest.raises(WorkspaceIntegrityError, match="config_sha256"):
        ExperimentWorkspace.open(changed, "run-001")


def test_open_rejects_symlinked_marker(tmp_path: Path) -> None:
    config = _config(tmp_path)
    workspace = ExperimentWorkspace.create(config, "run-001")
    marker = workspace.root / ".orchestration-workspace.json"
    external = tmp_path / "marker.json"
    external.write_bytes(marker.read_bytes())
    marker.unlink()
    marker.symlink_to(external)

    with pytest.raises(WorkspaceIntegrityError, match="regular ownership marker"):
        ExperimentWorkspace.open(config, "run-001")


def test_open_rejects_symlinked_layout_directory(tmp_path: Path) -> None:
    config = _config(tmp_path)
    workspace = ExperimentWorkspace.create(config, "run-001")
    validation = workspace.layout.validation
    (validation / "figures").rmdir()
    validation.rmdir()
    external = tmp_path / "external-validation"
    external.mkdir()
    validation.symlink_to(external, target_is_directory=True)

    with pytest.raises(WorkspaceIntegrityError, match="symbolic"):
        ExperimentWorkspace.open(config, "run-001")


@pytest.mark.parametrize("run_id", ["CON", "run:001", "trailing.", "bad|name"])
def test_create_rejects_non_portable_run_ids(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ValueError, match="portable single path component"):
        ExperimentWorkspace.create(_config(tmp_path), run_id)


def test_non_overwrite_write_fails_closed_on_concurrent_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = ExperimentWorkspace.create(_config(tmp_path), "run-001")
    target = workspace.root / "config" / "race.txt"

    def collision(_source: object, destination: object) -> None:
        Path(destination).write_text("competitor", encoding="utf-8")
        raise FileExistsError

    monkeypatch.setattr("validation.orchestration.workspace.os.link", collision)

    with pytest.raises(WorkspaceCollisionError):
        workspace.write_text("config/race.txt", "ours")

    assert target.read_text(encoding="utf-8") == "competitor"
    assert not tuple(workspace.layout.temporary.iterdir())