"""Tests for transactional validation command-line orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
import json
from pathlib import Path

import pandas as pd
import pytest

from validation.cli import (
    ArtifactPersistenceError,
    ExitCode,
    InputDataError,
    PipelineExecutionError,
    ValidationRunArtifacts,
    build_parser,
    load_config,
    main,
    run_validation,
)
from validation.comparison.module_validation import ModuleValidationResult
from validation.comparison.statistical_comparison import ModuleStatisticalComparisonResult
from validation.config import (
    CohortInputConfig,
    ConfigurationError,
    ModuleConfig,
    OutputConfig,
    PresentationConfig,
    StatisticalConfig,
    ValidationRunConfig,
)
from validation.models import ValidationCohort


def _write_patients(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"Id": "P1", "GENDER": "M", "BIRTHDATE": "1980-01-01"}]).to_csv(
        directory / "patients.csv",
        index=False,
    )


def _config(tmp_path: Path, *, overwrite: bool = False) -> ValidationRunConfig:
    synthea = tmp_path / "synthea"
    psynthea = tmp_path / "psynthea"
    _write_patients(synthea)
    _write_patients(psynthea)
    return ValidationRunConfig(
        inputs=CohortInputConfig(synthea, psynthea),
        output=OutputConfig(tmp_path / "output", overwrite=overwrite),
        modules=(
            ModuleConfig(
                "Hypertension",
                expected_condition_terms=("hypertension",),
            ),
        ),
        statistics=StatisticalConfig(alpha=0.05, top_n_codes=5),
        presentation=PresentationConfig(figure_format="png", dpi=72),
        run_name="test-run",
    )


def _comparison(tmp_path: Path, *, significant: int = 0) -> ModuleStatisticalComparisonResult:
    cohort = ValidationCohort(
        source="synthea",
        output_path=tmp_path,
        patients=pd.DataFrame(),
        encounters=pd.DataFrame(),
        conditions=pd.DataFrame(),
        medications=pd.DataFrame(),
        procedures=pd.DataFrame(),
        observations=pd.DataFrame(),
    )
    validation = ModuleValidationResult(
        module_name="Hypertension",
        synthea_cohort=cohort,
        psynthea_cohort=cohort,
        table_status=pd.DataFrame([{"table": "patients"}]),
        clinical_signal=pd.DataFrame([{"domain": "conditions"}]),
        distributional_similarity=pd.DataFrame([{"domain": "conditions"}]),
        issues=pd.DataFrame(columns=["issue"]),
        summary=pd.DataFrame([{"status": "comparable"}]),
    )
    summary = pd.DataFrame(
        [{
            "module_name": "Hypertension",
            "validation_status": "comparable",
            "valid_for_statistical_comparison": True,
            "skipped": False,
            "skip_reason": None,
            "continuous_test_count": 0,
            "categorical_test_count": 0,
            "prevalence_test_count": 0,
            "distribution_test_count": 0,
            "significant_test_count": significant,
            "significant_after_fdr_count": 0,
            "mean_jensen_shannon_divergence": None,
        }]
    )
    return ModuleStatisticalComparisonResult(
        module_name="Hypertension",
        validation=validation,
        continuous_tests=pd.DataFrame(),
        categorical_tests=pd.DataFrame(),
        prevalence_tests=pd.DataFrame(),
        distribution_tests=pd.DataFrame(),
        summary=summary,
    )


def _patch_success_pipeline(monkeypatch, comparison: ModuleStatisticalComparisonResult) -> None:
    monkeypatch.setattr("validation.cli.load_synthea", lambda path: object())
    monkeypatch.setattr("validation.cli.load_psynthea", lambda path: object())
    monkeypatch.setattr(
        "validation.cli.compare_module_statistics",
        lambda **kwargs: comparison,
    )
    monkeypatch.setattr("validation.cli._write_figures", lambda comparisons, config: [])


def test_exit_codes_are_stable() -> None:
    assert tuple(int(code) for code in ExitCode) == (0, 1, 2, 3, 4, 5, 130)


def test_main_invalid_arguments_returns_two_and_uses_injected_stderr() -> None:
    stderr = StringIO()
    code = main([], stdout=StringIO(), stderr=stderr)
    assert code == ExitCode.INVALID_ARGUMENTS
    assert "usage:" in stderr.getvalue()
    assert "--config" in stderr.getvalue()


def test_main_help_returns_success_and_uses_injected_stdout() -> None:
    stdout = StringIO()
    code = main(["--help"], stdout=stdout, stderr=StringIO())
    assert code == ExitCode.SUCCESS
    assert "--validate-only" in stdout.getvalue()
    assert "--no-plots" in stdout.getvalue()


def test_build_parser_version_uses_schema_constant() -> None:
    stdout = StringIO()
    parser = build_parser(stdout=stdout, stderr=StringIO())
    with pytest.raises(Exception) as error:
        parser.parse_args(["--version"])
    assert getattr(error.value, "status") == 0
    assert "config schema 1" in stdout.getvalue()


def test_load_config_round_trip(tmp_path: Path) -> None:
    config = _config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    loaded = load_config(path)
    assert loaded == config
    assert loaded.scientific_fingerprint == config.scientific_fingerprint


def test_load_config_missing_file_is_input_error(tmp_path: Path) -> None:
    with pytest.raises(InputDataError, match="not found"):
        load_config(tmp_path / "missing.json")


def test_load_config_reports_json_location(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"inputs":', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="line 1"):
        load_config(path)


def test_validate_only_does_not_call_run_validation(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    monkeypatch.setattr(
        "validation.cli.run_validation",
        lambda *args, **kwargs: pytest.fail("run_validation must not be called"),
    )
    stdout = StringIO()
    code = main(["--config", str(path), "--validate-only"], stdout=stdout, stderr=StringIO())
    assert code == ExitCode.SUCCESS
    assert "validation succeeded" in stdout.getvalue()


def test_main_maps_pipeline_error_to_five(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    monkeypatch.setattr(
        "validation.cli.run_validation",
        lambda *args, **kwargs: (_ for _ in ()).throw(PipelineExecutionError("boom")),
    )
    stderr = StringIO()
    code = main(["--config", str(path)], stderr=stderr)
    assert code == ExitCode.PIPELINE_ERROR
    assert "boom" in stderr.getvalue()


def test_scientific_warning_still_returns_success(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    output = config.output.root_dir
    output.mkdir()
    manifest = output / "run_manifest.json"
    manifest.write_text(
        json.dumps({"module_results": [{"decision": "warning"}]}),
        encoding="utf-8",
    )
    artifacts = ValidationRunArtifacts(
        report_path=output / "validation_report.md",
        manifest_path=manifest,
        resolved_config_path=output / "resolved_config.json",
        table_paths=(),
        figure_paths=(),
        comparisons=(_comparison(tmp_path, significant=1),),
    )
    monkeypatch.setattr("validation.cli.run_validation", lambda *a, **k: artifacts)
    stdout = StringIO()
    code = main(["--config", str(path)], stdout=stdout, stderr=StringIO())
    assert code == ExitCode.SUCCESS
    assert "warning=1" in stdout.getvalue()


def test_run_validation_persists_complete_audit_bundle(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    comparison = _comparison(tmp_path)
    _patch_success_pipeline(monkeypatch, comparison)

    artifacts = run_validation(
        config,
        generated_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
        config_source=tmp_path / "config.json",
    )

    assert artifacts.report_path.exists()
    assert artifacts.manifest_path.exists()
    assert artifacts.resolved_config_path.exists()
    assert len(artifacts.table_paths) == 10
    assert all(path.is_relative_to(config.output.root_dir) for path in artifacts.table_paths)

    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert manifest["configuration_fingerprint"] == config.configuration_fingerprint
    assert manifest["scientific_fingerprint"] == config.scientific_fingerprint
    assert manifest["decision_counts"]["pass"] == 1
    assert manifest["artefact_counts"]["tables"] == 10
    assert manifest["module_results"][0]["module_name"] == "Hypertension"
    assert manifest["completed_at"]
    assert manifest["duration_seconds"] >= 0
    assert manifest["python_version"]


def test_transaction_preserves_previous_run_when_new_run_fails(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path, overwrite=True)
    config.output.root_dir.mkdir(parents=True)
    previous_report = config.output.report_path
    previous_report.write_text("previous valid report", encoding="utf-8")
    comparison = _comparison(tmp_path)
    monkeypatch.setattr("validation.cli.load_synthea", lambda path: object())
    monkeypatch.setattr("validation.cli.load_psynthea", lambda path: object())
    monkeypatch.setattr("validation.cli.compare_module_statistics", lambda **kwargs: comparison)
    monkeypatch.setattr(
        "validation.cli._write_report",
        lambda *args, **kwargs: (_ for _ in ()).throw(ArtifactPersistenceError("write failed")),
    )

    with pytest.raises(ArtifactPersistenceError, match="write failed"):
        run_validation(config)

    assert previous_report.read_text(encoding="utf-8") == "previous valid report"
    assert not list(tmp_path.glob(".output.staging-*"))
    assert not list(tmp_path.glob(".output.backup-*"))


def test_successful_overwrite_replaces_previous_run(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path, overwrite=True)
    config.output.root_dir.mkdir(parents=True)
    stale = config.output.root_dir / "stale.txt"
    stale.write_text("old", encoding="utf-8")
    _patch_success_pipeline(monkeypatch, _comparison(tmp_path))

    artifacts = run_validation(config)

    assert artifacts.report_path.exists()
    assert not stale.exists()
    assert not list(tmp_path.glob(".output.backup-*"))


def test_comparison_error_includes_module_name(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr("validation.cli.load_synthea", lambda path: object())
    monkeypatch.setattr("validation.cli.load_psynthea", lambda path: object())
    monkeypatch.setattr(
        "validation.cli.compare_module_statistics",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("bad test")),
    )

    with pytest.raises(PipelineExecutionError, match="Hypertension"):
        run_validation(config)


def test_no_tables_and_no_plots_create_zero_optional_artifacts(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    _patch_success_pipeline(monkeypatch, _comparison(tmp_path))

    artifacts = run_validation(
        config,
        generate_tables=False,
        generate_plots=False,
    )

    assert artifacts.table_paths == ()
    assert artifacts.figure_paths == ()
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artefact_counts"] == {"figures": 0, "tables": 0}


def test_help_exposes_explicit_experiment_mode() -> None:
    stdout = StringIO()
    code = main(["--help"], stdout=stdout, stderr=StringIO())
    assert code == ExitCode.SUCCESS
    help_text = stdout.getvalue()
    assert "--experiment" in help_text
    assert "--run-id" in help_text
    assert "--module-name" in help_text


def test_experiment_validate_only_does_not_execute(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "experiment.json"
    config_path.write_text("{}", encoding="utf-8")
    sentinel = object()
    monkeypatch.setattr(
        "validation.cli.load_experiment_config",
        lambda path: sentinel,
    )
    monkeypatch.setattr(
        "validation.cli.run_full_experiment",
        lambda *args, **kwargs: pytest.fail(
            "run_full_experiment must not be called"
        ),
    )

    stdout = StringIO()
    code = main(
        ["--config", str(config_path), "--experiment", "--validate-only"],
        stdout=stdout,
        stderr=StringIO(),
    )

    assert code == ExitCode.SUCCESS
    assert "Experiment configuration validation succeeded." in stdout.getvalue()


def test_experiment_mode_executes_runner_and_prints_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace
    from validation.orchestration import ExecutionStatus

    config_path = tmp_path / "experiment.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "validation.cli.load_experiment_config",
        lambda path: object(),
    )

    captured = {}

    def fake_run(config, *, run_id=None, module_name=None):
        captured.update(
            config=config,
            run_id=run_id,
            module_name=module_name,
        )
        return SimpleNamespace(
            result=SimpleNamespace(
                status=ExecutionStatus.SUCCEEDED,
                run_id="run-001",
                workspace=tmp_path / "workspace",
                error_message=None,
            ),
            manifest=SimpleNamespace(path=Path("manifest.json")),
        )

    monkeypatch.setattr("validation.cli.run_full_experiment", fake_run)

    stdout = StringIO()
    code = main(
        [
            "--config",
            str(config_path),
            "--experiment",
            "--run-id",
            "run-001",
            "--module-name",
            "Hypertension",
        ],
        stdout=stdout,
        stderr=StringIO(),
    )

    assert code == ExitCode.SUCCESS
    assert captured == {
        "config": config_path,
        "run_id": "run-001",
        "module_name": "Hypertension",
    }
    assert "status=succeeded" in stdout.getvalue()
    assert "run_id=run-001" in stdout.getvalue()
    assert "Manifest: manifest.json" in stdout.getvalue()


def test_experiment_failed_result_maps_to_pipeline_exit_code(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace
    from validation.orchestration import ExecutionStatus

    config_path = tmp_path / "experiment.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "validation.cli.load_experiment_config",
        lambda path: object(),
    )
    monkeypatch.setattr(
        "validation.cli.run_full_experiment",
        lambda *args, **kwargs: SimpleNamespace(
            result=SimpleNamespace(
                status=ExecutionStatus.FAILED,
                run_id="run-failed",
                workspace=tmp_path / "workspace",
                error_message="root cause stage failed",
            ),
            manifest=None,
        ),
    )

    stderr = StringIO()
    code = main(
        ["--config", str(config_path), "--experiment"],
        stdout=StringIO(),
        stderr=stderr,
    )

    assert code == ExitCode.PIPELINE_ERROR
    assert "root cause stage failed" in stderr.getvalue()


def test_experiment_only_options_are_rejected_in_legacy_mode(tmp_path: Path) -> None:
    stderr = StringIO()
    code = main(
        ["--config", str(tmp_path / "config.json"), "--run-id", "run-1"],
        stdout=StringIO(),
        stderr=stderr,
    )
    assert code == ExitCode.INVALID_ARGUMENTS
    assert "require --experiment" in stderr.getvalue()


def test_legacy_only_output_flags_are_rejected_in_experiment_mode(
    tmp_path: Path,
) -> None:
    stderr = StringIO()
    code = main(
        [
            "--config",
            str(tmp_path / "experiment.json"),
            "--experiment",
            "--no-plots",
        ],
        stdout=StringIO(),
        stderr=stderr,
    )
    assert code == ExitCode.INVALID_ARGUMENTS
    assert "legacy validation mode" in stderr.getvalue()


def test_experiment_cli_applies_all_general_overrides_to_executed_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from validation.orchestration.configuration import parse_experiment_config
    from validation.orchestration.models import ExecutionStatus

    config_path = tmp_path / "experiment.json"
    config_path.write_text("{}", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "id": "baseline",
        "name": "Baseline",
        "cohort": {
            "population": 10,
            "seed": 1,
            "modules": ["Hypertension"],
            "reference_date": "2025-01-01",
            "min_age": 18,
            "max_age": 85,
            "step_days": 1,
            "years_of_history": 5,
            "wellness_encounters": False,
            "vitals": True,
            "mortality": True,
            "keystone": False,
            "ground_truth": False,
            "output_format": "csv",
        },
        "simulators": [
            {
                "kind": "synthea",
                "command": ["synthea"],
                "working_directory": str(tmp_path),
                "output_subdirectory": "synthea",
            },
            {
                "kind": "psynthea",
                "command": ["psynthea"],
                "working_directory": str(tmp_path),
                "output_subdirectory": "psynthea",
            },
        ],
        "output_root": str(tmp_path / "runs"),
    }
    original = parse_experiment_config(payload)
    monkeypatch.setattr("validation.cli.load_experiment_config", lambda _: original)

    captured: dict[str, object] = {}

    class _Result:
        status = ExecutionStatus.SUCCEEDED
        error_message = None

    class _Execution:
        result = _Result()
        workspace = None

    def fake_run(config, *, run_id=None, module_name=None):
        captured["config"] = config
        captured["run_id"] = run_id
        captured["module_name"] = module_name
        return _Execution()

    monkeypatch.setattr("validation.cli.run_full_experiment", fake_run)
    monkeypatch.setattr("validation.cli._print_experiment_summary", lambda *_: None)

    profile_file = tmp_path / "profiles" / "spain.json"
    module_file = tmp_path / "modules" / "diabetes.json"
    code = main(
        [
            "--config", str(config_path),
            "--experiment",
            "--population", "250",
            "--seed", "42",
            "--module-file", str(module_file),
            "--reference-date", "2026-07-21",
            "--min-age", "21",
            "--max-age", "90",
            "--step-days", "7",
            "--years-of-history", "12",
            "--wellness-encounters",
            "--no-vitals",
            "--no-mortality",
            "--keystone",
            "--ground-truth",
            "--output-format", "omop",
            "--profile-file", str(profile_file),
            "--output-root", str(tmp_path / "custom"),
            "--experiment-id", "diabetes-run",
            "--experiment-name", "Diabetes run",
            "--run-id", "run-001",
            "--module-name", "Diabetes",
        ],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert code == ExitCode.SUCCESS
    resolved = captured["config"]
    assert resolved.cohort.population == 250
    assert resolved.cohort.seed == 42
    assert resolved.cohort.modules == ()
    assert resolved.cohort.module_files == (module_file.resolve(),)
    assert resolved.cohort.reference_date.isoformat() == "2026-07-21"
    assert resolved.cohort.min_age == 21
    assert resolved.cohort.max_age == 90
    assert resolved.cohort.step_days == 7
    assert resolved.cohort.years_of_history == 12
    assert resolved.cohort.wellness_encounters is True
    assert resolved.cohort.vitals is False
    assert resolved.cohort.mortality is False
    assert resolved.cohort.keystone is True
    assert resolved.cohort.ground_truth is True
    assert resolved.cohort.output_format == "omop"
    assert resolved.cohort.profile_file == profile_file.resolve()
    assert resolved.output_root == (tmp_path / "custom").resolve()
    assert resolved.id == "diabetes-run"
    assert resolved.name == "Diabetes run"
    assert captured["run_id"] == "run-001"
    assert captured["module_name"] == "Diabetes"


def test_experiment_cli_preserves_path_execution_without_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace
    from validation.orchestration import ExecutionStatus

    config_path = tmp_path / "experiment.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("validation.cli.load_experiment_config", lambda _: object())

    captured: dict[str, object] = {}

    def fake_run(config, *, run_id=None, module_name=None):
        captured["config"] = config
        return SimpleNamespace(
            result=SimpleNamespace(
                status=ExecutionStatus.SUCCEEDED,
                error_message=None,
                run_id="run-001",
                workspace=tmp_path,
            ),
            manifest=None,
        )

    monkeypatch.setattr("validation.cli.run_full_experiment", fake_run)
    monkeypatch.setattr("validation.cli._print_experiment_summary", lambda *_: None)

    code = main(
        ["--config", str(config_path), "--experiment"],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert code == ExitCode.SUCCESS
    assert captured["config"] == config_path


def test_help_exposes_all_experiment_override_options() -> None:
    stdout = StringIO()

    code = main(["--help"], stdout=stdout, stderr=StringIO())

    assert code == ExitCode.SUCCESS
    help_text = stdout.getvalue()
    for option in (
        "--population",
        "--seed",
        "--module",
        "--module-file",
        "--reference-date",
        "--min-age",
        "--max-age",
        "--step-days",
        "--years-of-history",
        "--wellness-encounters",
        "--no-wellness-encounters",
        "--vitals",
        "--no-vitals",
        "--mortality",
        "--no-mortality",
        "--keystone",
        "--no-keystone",
        "--ground-truth",
        "--no-ground-truth",
        "--output-format",
        "--profile-file",
        "--output-root",
        "--experiment-id",
        "--experiment-name",
    ):
        assert option in help_text


@pytest.mark.parametrize(
    "arguments",
    [
        ["--population", "100"],
        ["--seed", "42"],
        ["--module", "Hypertension"],
        ["--module-file", "modules/hypertension.json"],
        ["--reference-date", "2026-07-21"],
        ["--min-age", "18"],
        ["--max-age", "90"],
        ["--step-days", "7"],
        ["--years-of-history", "10"],
        ["--wellness-encounters"],
        ["--no-wellness-encounters"],
        ["--vitals"],
        ["--no-vitals"],
        ["--mortality"],
        ["--no-mortality"],
        ["--keystone"],
        ["--no-keystone"],
        ["--ground-truth"],
        ["--no-ground-truth"],
        ["--output-format", "csv"],
        ["--profile-file", "profiles/spain.json"],
        ["--output-root", "runs"],
        ["--experiment-id", "experiment-1"],
        ["--experiment-name", "Experiment 1"],
    ],
)
def test_experiment_override_options_are_rejected_without_experiment(
    arguments: list[str],
    tmp_path: Path,
) -> None:
    stderr = StringIO()

    code = main(
        ["--config", str(tmp_path / "config.json"), *arguments],
        stdout=StringIO(),
        stderr=stderr,
    )

    assert code == ExitCode.INVALID_ARGUMENTS
    assert "require --experiment" in stderr.getvalue()


def test_module_and_module_file_are_mutually_exclusive(tmp_path: Path) -> None:
    stderr = StringIO()

    code = main(
        [
            "--config", str(tmp_path / "experiment.json"),
            "--experiment",
            "--module", "Hypertension",
            "--module-file", "modules/hypertension.json",
        ],
        stdout=StringIO(),
        stderr=stderr,
    )

    assert code == ExitCode.INVALID_ARGUMENTS
    assert "not allowed with argument" in stderr.getvalue()


@pytest.mark.parametrize(
    "arguments, expected_fragment",
    [
        (["--reference-date", "21-07-2026"], "invalid ISO date"),
        (["--reference-date", "2026-02-30"], "invalid ISO date"),
        (["--output-format", "parquet"], "invalid choice"),
    ],
)
def test_invalid_experiment_override_syntax_is_rejected_by_parser(
    arguments: list[str],
    expected_fragment: str,
    tmp_path: Path,
) -> None:
    stderr = StringIO()

    code = main(
        [
            "--config", str(tmp_path / "experiment.json"),
            "--experiment",
            *arguments,
        ],
        stdout=StringIO(),
        stderr=stderr,
    )

    assert code == ExitCode.INVALID_ARGUMENTS
    assert expected_fragment in stderr.getvalue()


def test_boolean_override_absence_preserves_json_value(monkeypatch, tmp_path: Path) -> None:
    from validation.orchestration.configuration import parse_experiment_config
    from validation.orchestration.models import ExecutionStatus

    config_path = tmp_path / "experiment.json"
    config_path.write_text("{}", encoding="utf-8")
    original = parse_experiment_config(
        {
            "schema_version": 1,
            "id": "baseline",
            "name": "Baseline",
            "cohort": {
                "population": 10,
                "seed": 1,
                "modules": ["Hypertension"],
                "vitals": True,
                "mortality": False,
            },
            "simulators": [
                {
                    "kind": "synthea",
                    "command": ["synthea"],
                    "working_directory": str(tmp_path),
                    "output_subdirectory": "synthea",
                },
                {
                    "kind": "psynthea",
                    "command": ["psynthea"],
                    "working_directory": str(tmp_path),
                    "output_subdirectory": "psynthea",
                },
            ],
            "output_root": str(tmp_path / "runs"),
        }
    )
    monkeypatch.setattr("validation.cli.load_experiment_config", lambda _: original)

    captured: dict[str, object] = {}

    class _Result:
        status = ExecutionStatus.SUCCEEDED
        error_message = None

    class _Execution:
        result = _Result()
        workspace = None

    def fake_run(config, *, run_id=None, module_name=None):
        captured["config"] = config
        return _Execution()

    monkeypatch.setattr("validation.cli.run_full_experiment", fake_run)
    monkeypatch.setattr("validation.cli._print_experiment_summary", lambda *_: None)

    code = main(
        [
            "--config", str(config_path),
            "--experiment",
            "--population", "20",
        ],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert code == ExitCode.SUCCESS
    resolved = captured["config"]
    assert resolved.cohort.vitals is True
    assert resolved.cohort.mortality is False