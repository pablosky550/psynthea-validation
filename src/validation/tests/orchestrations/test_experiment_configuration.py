from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation.orchestration.configuration import (
    ExperimentConfigurationError,
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