from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from validation.orchestration.configuration import (
    ExperimentConfigurationError,
    apply_experiment_overrides,
    dump_experiment_config,
    experiment_config_to_dict,
    load_experiment_config,
    parse_experiment_config,
)
from validation.orchestration.models import (
    ReportFormat,
    SimulatorKind,
)


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": "hypertension-pilot",
        "name": "Hypertension equivalence pilot",
        "description": "Reproducible comparison.",
        "tags": ["pilot", "hypertension"],
        "output_root": "results",
        "report_formats": ["html", "json"],
        "cohort": {
            "population": 100,
            "seed": 42,
            "modules": ["Hypertension"],
            "reference_date": "2024-12-31",
            "min_age": 18,
            "max_age": 90,
            "parameters": {"country": "ES"},
        },
        "simulators": [
            {
                "kind": "synthea",
                "command": ["./gradlew", "run"],
                "working_directory": "engines/synthea",
                "output_subdirectory": "synthea",
                "timeout_seconds": 7200,
                "environment": {"JAVA_HOME": "/java"},
                "arguments": {"state": "Massachusetts"},
                "expected_output_files": ["csv/patients.csv"],
            },
            {
                "kind": "psynthea",
                "command": ["python", "-m", "psynthea"],
                "working_directory": "engines/psynthea",
                "output_subdirectory": "psynthea",
                "expected_output_files": ["patients.csv"],
            },
        ],
        "metadata": {
            "knowledge": {
                "research_use": True,
                "strict_evidence": True,
            }
        },
    }


def test_load_resolves_paths_relative_to_configuration_file(
    tmp_path: Path,
) -> None:
    configuration_path = tmp_path / "configs" / "experiment.json"
    configuration_path.parent.mkdir()
    configuration_path.write_text(
        json.dumps(_payload()),
        encoding="utf-8",
    )

    config = load_experiment_config(configuration_path)

    assert config.id == "hypertension-pilot"
    assert config.output_root == (
        configuration_path.parent / "results"
    ).resolve()
    assert config.cohort.reference_date.isoformat() == "2024-12-31"
    assert config.report_formats == (
        ReportFormat.HTML,
        ReportFormat.JSON,
    )
    assert config.simulator(SimulatorKind.SYNTHEA).working_directory == (
        configuration_path.parent / "engines" / "synthea"
    ).resolve()


def test_canonical_serialization_round_trips(tmp_path: Path) -> None:
    config = parse_experiment_config(
        _payload(),
        base_directory=tmp_path,
    )

    canonical = experiment_config_to_dict(config)
    restored = parse_experiment_config(canonical)

    assert restored == config
    assert dump_experiment_config(config).endswith("\n")
    assert json.loads(dump_experiment_config(config)) == canonical


def test_unknown_fields_are_rejected() -> None:
    payload = _payload()
    payload["unexpected"] = True

    with pytest.raises(
        ExperimentConfigurationError,
        match="unknown field",
    ):
        parse_experiment_config(payload)


def test_unknown_nested_fields_are_rejected() -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["silent_typo"] = 1

    with pytest.raises(
        ExperimentConfigurationError,
        match="configuration.cohort contains unknown field",
    ):
        parse_experiment_config(payload)


def test_duplicate_json_fields_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"schema_version": 1, "schema_version": 1}',
        encoding="utf-8",
    )

    with pytest.raises(
        ExperimentConfigurationError,
        match="Duplicate JSON field",
    ):
        load_experiment_config(path)


def test_invalid_enum_reports_allowed_values() -> None:
    payload = _payload()
    simulators = payload["simulators"]
    assert isinstance(simulators, list)
    assert isinstance(simulators[0], dict)
    simulators[0]["kind"] = "java"

    with pytest.raises(
        ExperimentConfigurationError,
        match="must be one of: synthea, psynthea",
    ):
        parse_experiment_config(payload)


def test_invalid_reference_date_is_rejected() -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["reference_date"] = "31-12-2024"

    with pytest.raises(
        ExperimentConfigurationError,
        match="ISO-8601 date",
    ):
        parse_experiment_config(payload)

def test_modules_dir_is_resolved_relative_to_configuration_file(
    tmp_path: Path,
) -> None:
    configuration_path = (
        tmp_path
        / "configs"
        / "experiment.json"
    )
    configuration_path.parent.mkdir(parents=True)

    modules_dir = (
        tmp_path
        / "resources"
        / "synthea"
        / "modules"
    )
    modules_dir.mkdir(parents=True)

    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)

    cohort["modules_dir"] = "../resources/synthea/modules"

    configuration_path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    config = load_experiment_config(configuration_path)

    assert config.cohort.modules_dir == modules_dir.resolve()


def test_modules_dir_is_preserved_in_canonical_serialization(
    tmp_path: Path,
) -> None:
    modules_dir = tmp_path / "resources" / "synthea" / "modules"
    modules_dir.mkdir(parents=True)

    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["modules_dir"] = str(modules_dir)

    config = parse_experiment_config(
        payload,
        base_directory=tmp_path,
    )

    canonical = experiment_config_to_dict(config)

    canonical_cohort = canonical["cohort"]
    assert isinstance(canonical_cohort, dict)
    assert canonical_cohort["modules_dir"] == str(modules_dir.resolve())

    restored = parse_experiment_config(canonical)

    assert restored.cohort.modules_dir == modules_dir.resolve()
    assert restored == config


def test_missing_modules_dir_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["modules_dir"] = "missing/modules"

    with pytest.raises(
        ValueError,
        match="modules_dir does not exist",
    ):
        parse_experiment_config(
            payload,
            base_directory=tmp_path,
        )


def test_modules_dir_pointing_to_file_is_rejected(
    tmp_path: Path,
) -> None:
    modules_file = tmp_path / "modules.json"
    modules_file.write_text("{}", encoding="utf-8")

    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["modules_dir"] = str(modules_file)

    with pytest.raises(
        ValueError,
        match="modules_dir must be a directory",
    ):
        parse_experiment_config(
            payload,
            base_directory=tmp_path,
        )


def test_non_json_metadata_is_rejected_during_serialization(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["metadata"] = {"unsafe": object()}
    config = parse_experiment_config(payload, base_directory=tmp_path)

    with pytest.raises(
        ExperimentConfigurationError,
        match="not JSON-compatible",
    ):
        experiment_config_to_dict(config)

def test_apply_experiment_overrides_applies_complete_cohort_controls(
    tmp_path: Path,
) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path)
    module_file = tmp_path / "modules" / "diabetes.json"
    profile_file = tmp_path / "profiles" / "spain.json"

    resolved = apply_experiment_overrides(
        config,
        experiment_id="diabetes-validation",
        experiment_name="Diabetes validation",
        population=250,
        seed=987,
        module_files=[module_file],
        reference_date=date(2026, 7, 21),
        min_age=30,
        max_age=80,
        step_days=7,
        years_of_history=12,
        wellness_encounters=True,
        vitals=True,
        mortality=True,
        keystone=True,
        ground_truth=True,
        output_format="omop",
        profile_file=profile_file,
        output_root=tmp_path / "custom-runs",
    )

    assert resolved.id == "diabetes-validation"
    assert resolved.name == "Diabetes validation"
    assert resolved.output_root == (tmp_path / "custom-runs").resolve()
    assert resolved.cohort.population == 250
    assert resolved.cohort.seed == 987
    assert resolved.cohort.modules == ()
    assert resolved.cohort.module_files == (module_file.resolve(),)
    assert resolved.cohort.reference_date == date(2026, 7, 21)
    assert resolved.cohort.min_age == 30
    assert resolved.cohort.max_age == 80
    assert resolved.cohort.step_days == 7
    assert resolved.cohort.years_of_history == 12
    assert resolved.cohort.wellness_encounters is True
    assert resolved.cohort.vitals is True
    assert resolved.cohort.mortality is True
    assert resolved.cohort.keystone is True
    assert resolved.cohort.ground_truth is True
    assert resolved.cohort.output_format == "omop"
    assert resolved.cohort.profile_file == profile_file.resolve()

    # Scientific protocol and simulator execution contracts remain untouched.
    assert resolved.simulators == config.simulators
    assert resolved.report_formats == config.report_formats
    assert resolved.metadata == config.metadata

    # The immutable source configuration must not be mutated.
    assert config.cohort.population == 100
    assert config.cohort.modules == ("Hypertension",)
    assert config.cohort.module_files == ()
    assert config.cohort.reference_date == date(2024, 12, 31)
    assert config.cohort.output_format == "csv"
    assert config.cohort.profile_file is None


def test_apply_experiment_overrides_modules_clear_module_files(
    tmp_path: Path,
) -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["modules"] = []
    cohort["module_files"] = ["modules/hypertension.json"]
    config = parse_experiment_config(payload, base_directory=tmp_path)

    resolved = apply_experiment_overrides(
        config,
        modules=["Diabetes"],
    )

    assert resolved.cohort.modules == ("Diabetes",)
    assert resolved.cohort.module_files == ()


def test_apply_experiment_overrides_boolean_false_is_explicit(
    tmp_path: Path,
) -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort.update(
        {
            "wellness_encounters": True,
            "vitals": True,
            "mortality": True,
            "keystone": True,
            "ground_truth": True,
        }
    )
    config = parse_experiment_config(payload, base_directory=tmp_path)

    resolved = apply_experiment_overrides(
        config,
        wellness_encounters=False,
        vitals=False,
        mortality=False,
        keystone=False,
        ground_truth=False,
    )

    assert resolved.cohort.wellness_encounters is False
    assert resolved.cohort.vitals is False
    assert resolved.cohort.mortality is False
    assert resolved.cohort.keystone is False
    assert resolved.cohort.ground_truth is False


def test_apply_experiment_overrides_without_values_preserves_configuration(
    tmp_path: Path,
) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path)

    resolved = apply_experiment_overrides(config)

    assert resolved == config
    assert resolved.cohort is config.cohort


@pytest.mark.parametrize(
    ("overrides", "expected_message"),
    [
        ({"population": 0}, "population"),
        ({"min_age": 91, "max_age": 90}, "min_age"),
        ({"step_days": 0}, "step_days"),
        ({"years_of_history": 0}, "years_of_history"),
        ({"output_format": "parquet"}, "output_format"),
    ],
)
def test_apply_experiment_overrides_rejects_invalid_cohort_values(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_message: str,
) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path)

    with pytest.raises(
        ExperimentConfigurationError,
        match=expected_message,
    ):
        apply_experiment_overrides(config, **overrides)


def test_apply_experiment_overrides_rejects_both_module_sources(
    tmp_path: Path,
) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path)

    with pytest.raises(
        ExperimentConfigurationError,
        match="mutually exclusive",
    ):
        apply_experiment_overrides(
            config,
            modules=["Hypertension"],
            module_files=[tmp_path / "hypertension.json"],
        )


@pytest.mark.parametrize(
    ("keyword", "value", "expected_message"),
    [
        ("modules", "Hypertension", "modules override must be a sequence"),
        ("module_files", "hypertension.json", "module_files override must be a sequence"),
    ],
)
def test_apply_experiment_overrides_rejects_scalar_module_sources(
    tmp_path: Path,
    keyword: str,
    value: object,
    expected_message: str,
) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path)

    with pytest.raises(
        ExperimentConfigurationError,
        match=expected_message,
    ):
        apply_experiment_overrides(config, **{keyword: value})