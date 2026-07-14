from __future__ import annotations

from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path
from types import MappingProxyType

import pytest

from validation.orchestration.manifest import (
    MANIFEST_SCHEMA_VERSION,
    ExperimentManifest,
    ManifestCollisionError,
    ManifestIntegrityError,
    ManifestSerializationError,
)
from validation.orchestration.models import (
    ArtifactKind,
    CohortConfig,
    ExecutionStatus,
    ExperimentConfig,
    ExperimentResult,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
)
from validation.orchestration.workspace import ExperimentWorkspace

NOW = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 14, 10, 1, tzinfo=UTC)


def _config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        id="hypertension-equivalence",
        name="Hypertension equivalence",
        cohort=CohortConfig(population=100, seed=42, modules=("hypertension",)),
        simulators=(
            SimulatorConfig(
                kind=SimulatorKind.SYNTHEA,
                command=("java", "-jar", "synthea.jar"),
                working_directory=tmp_path,
                output_subdirectory="synthea-output",
            ),
            SimulatorConfig(
                kind=SimulatorKind.PSYNTHEA,
                command=("python", "-m", "psynthea"),
                working_directory=tmp_path,
                output_subdirectory="psynthea-output",
            ),
        ),
        output_root=tmp_path / "runs",
        report_formats=(ReportFormat.HTML,),
        metadata={"protocol": {"version": 1}},
    )


def _workspace_and_result(tmp_path: Path, *, with_artifact: bool = True):
    config = _config(tmp_path)
    workspace = ExperimentWorkspace.create(config, "run-001", created_at=NOW)
    artifacts = ()
    if with_artifact:
        path = workspace.write_text("validation/result.json", "{\"ok\":true}\n")
        artifacts = (
            workspace.artifact_reference(
                artifact_id="validation.result",
                kind=ArtifactKind.VALIDATION_RESULT,
                path=path,
                media_type="application/json",
                producer="validation_engine",
                created_at=NOW,
            ),
        )
    result = ExperimentResult(
        experiment_id=config.id,
        run_id=workspace.run_id,
        status=ExecutionStatus.FAILED,
        config=config,
        workspace=workspace.root,
        artifacts=artifacts,
        started_at=NOW,
        finished_at=LATER,
        duration_seconds=60.0,
        error_message="Controlled test failure.",
    )
    return workspace, result


def test_build_is_portable_deterministic_and_deeply_immutable(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")

    first = manifest.build(result, generated_at=NOW)
    second = manifest.build(result, generated_at=NOW)

    assert first == second
    assert first["workspace"] == "."
    assert str(workspace.root) not in dumps(first["config"], default=lambda value: dict(value) if isinstance(value, MappingProxyType) else list(value))
    assert first["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert len(first["config_sha256"]) == 64
    assert isinstance(first, MappingProxyType)
    assert isinstance(first["producer"], MappingProxyType)
    assert isinstance(first["result"]["artifacts"], tuple)
    with pytest.raises(TypeError):
        first["producer"]["version"] = "tampered"


def test_write_read_reference_and_verify_round_trip(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")

    reference = manifest.write(result, generated_at=NOW)
    loaded = manifest.read(verify_self_hash=reference.sha256)

    assert reference.kind is ArtifactKind.MANIFEST
    assert reference.path == Path("manifest.json")
    assert loaded["experiment_id"] == result.experiment_id
    assert loaded["config"] == loaded["result"]["config"]
    assert manifest.reference().sha256 == reference.sha256
    assert manifest.verify(expected_reference=reference) == loaded


def test_manifest_bytes_are_canonical(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")
    manifest.write(result, generated_at=NOW)

    content = manifest.path.read_bytes()
    assert content.endswith(b"\n")
    parsed = loads(content)
    expected = (dumps(parsed, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert content == expected


def test_write_fails_closed_on_existing_manifest(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")
    manifest.write(result, generated_at=NOW)

    with pytest.raises(ManifestCollisionError):
        manifest.write(result, generated_at=NOW)


def test_build_rejects_artifact_content_tampering(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    workspace.resolve(result.artifacts[0].path).write_text("tampered", encoding="utf-8")

    with pytest.raises(ManifestIntegrityError, match="SHA-256 mismatch"):
        ExperimentManifest(workspace, producer_version="2.0.0").build(
            result, generated_at=NOW
        )


def test_build_can_explicitly_skip_artifact_verification(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    workspace.resolve(result.artifacts[0].path).write_text("tampered", encoding="utf-8")

    payload = ExperimentManifest(workspace, producer_version="2.0.0").build(
        result, generated_at=NOW, verify_artifacts=False
    )
    assert payload["experiment_id"] == result.experiment_id


def test_build_rejects_workspace_or_config_mismatch(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    other_config = _config(tmp_path / "other")
    bad_result = ExperimentResult(
        experiment_id=other_config.id,
        run_id=result.run_id,
        status=ExecutionStatus.FAILED,
        config=other_config,
        workspace=workspace.root,
        started_at=NOW,
        finished_at=LATER,
        duration_seconds=60,
        error_message="failure",
    )
    with pytest.raises(ManifestIntegrityError, match="config"):
        ExperimentManifest(workspace, producer_version="2.0.0").build(
            bad_result, generated_at=NOW, verify_artifacts=False
        )


def test_read_rejects_tampered_config_even_when_json_is_valid(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")
    manifest.write(result, generated_at=NOW)
    payload = loads(manifest.path.read_text())
    payload["config"]["cohort"]["population"] = 999
    payload["result"]["config"] = payload["config"]
    manifest.path.write_text(dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestIntegrityError, match="ExperimentConfig"):
        manifest.read()


def test_read_rejects_tampered_config_hash(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")
    manifest.write(result, generated_at=NOW)
    payload = loads(manifest.path.read_text())
    payload["config_sha256"] = "0" * 64
    manifest.path.write_text(dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestIntegrityError, match="config_sha256"):
        manifest.read()


def test_read_rejects_absolute_workspace_field(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")
    manifest.write(result, generated_at=NOW)
    payload = loads(manifest.path.read_text())
    payload["workspace"] = workspace.root.as_posix()
    manifest.path.write_text(dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestIntegrityError, match="portable logical root"):
        manifest.read()


def test_read_rejects_wrong_schema_and_producer_version(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")
    manifest.write(result, generated_at=NOW)

    payload = loads(manifest.path.read_text())
    payload["schema_version"] = 999
    manifest.path.write_text(dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestIntegrityError, match="schema_version"):
        manifest.read()

    manifest.write(result, generated_at=NOW, overwrite=True)
    with pytest.raises(ManifestIntegrityError, match="producer version"):
        ExperimentManifest(workspace, producer_version="3.0.0").read()


def test_read_rejects_invalid_json_and_hash(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")
    reference = manifest.write(result, generated_at=NOW)

    with pytest.raises(ManifestIntegrityError, match="SHA-256 mismatch"):
        manifest.read(verify_self_hash="0" * 64)

    manifest.path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ManifestIntegrityError, match="UTF-8 JSON"):
        manifest.read()


def test_build_rejects_non_finite_metadata(tmp_path: Path) -> None:
    config = _config(tmp_path)
    workspace = ExperimentWorkspace.create(config, "run-001", created_at=NOW)
    result = ExperimentResult(
        experiment_id=config.id,
        run_id=workspace.run_id,
        status=ExecutionStatus.FAILED,
        config=config,
        workspace=workspace.root,
        started_at=NOW,
        finished_at=LATER,
        duration_seconds=60,
        error_message="failure",
        metadata={"invalid": float("nan")},
    )
    with pytest.raises(ManifestSerializationError, match="non-finite"):
        ExperimentManifest(workspace, producer_version="2.0.0").build(
            result, generated_at=NOW, verify_artifacts=False
        )


def test_constructor_and_boundary_types_are_strict(tmp_path: Path) -> None:
    workspace, result = _workspace_and_result(tmp_path)
    with pytest.raises(ValueError):
        ExperimentManifest(workspace, producer_version=" ")
    manifest = ExperimentManifest(workspace, producer_version="2.0.0")
    with pytest.raises(TypeError):
        manifest.build(result, generated_at=NOW, verify_artifacts=1)
    with pytest.raises(TypeError):
        manifest.write(result, generated_at=NOW, overwrite=1)
    manifest.write(result, generated_at=NOW)
    with pytest.raises(ValueError):
        manifest.read(verify_self_hash="abc")