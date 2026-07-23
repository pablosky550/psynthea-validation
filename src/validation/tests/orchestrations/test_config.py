from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation.orchestration.config import (
    EXPERIMENT_CONFIG_SCHEMA_VERSION,
    load_experiment_config,
    parse_experiment_config,
)
from validation.orchestration.exceptions import (
    ExperimentConfigurationError,
    ExperimentConfigurationIOError,
)
from validation.orchestration.models import ReportFormat, SimulatorKind


def _payload() -> dict[str, object]:
    return {
        "schema_version": EXPERIMENT_CONFIG_SCHEMA_VERSION,
        "id": "hypertension-equivalence",
        "name": "Hypertension equivalence",
        "description": "Deterministic comparison.",
        "cohort": {
            "population": 100,
            "seed": 42,
            "modules": ["hypertension"],
            "reference_date": "2024-12-31",
            "min_age": 18,
            "max_age": 90,
            "parameters": {"profile": {"country": "ES"}},
        },
        "simulators": [
            {
                "kind": "synthea",
                "command": ["./gradlew", "run"],
                "working_directory": "../synthea",
                "output_subdirectory": "synthea",
                "timeout_seconds": 600,
                "expected_output_files": ["csv/patients.csv"],
            },
            {
                "kind": "psynthea",
                "command": ["python", "-m", "psynthea"],
                "working_directory": "../psynthea",
                "output_subdirectory": "psynthea",
                "environment": {"PYTHONHASHSEED": "0"},
                "expected_output_files": ["patients.csv"],
            },
        ],
        "output_root": "runs",
        "report_formats": ["html", "json"],
        "tags": ["phase-6"],
        "metadata": {"protocol": {"version": 1}},
    }


def test_parse_builds_immutable_domain_models_and_resolves_relative_paths(
    tmp_path: Path,
) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path / "configs")

    assert config.id == "hypertension-equivalence"
    assert config.cohort.population == 100
    assert config.cohort.reference_date is not None
    assert config.output_root == tmp_path / "configs" / "runs"
    assert config.report_formats == (ReportFormat.HTML, ReportFormat.JSON)
    assert config.simulator(SimulatorKind.SYNTHEA).working_directory == (
        tmp_path / "configs" / "../synthea"
    )
    assert config.simulator(SimulatorKind.PSYNTHEA).environment["PYTHONHASHSEED"] == "0"


def test_parse_preserves_absolute_paths(tmp_path: Path) -> None:
    payload = _payload()
    payload["output_root"] = str(tmp_path / "absolute-runs")

    config = parse_experiment_config(payload, base_directory=tmp_path / "configs")

    assert config.output_root == tmp_path / "absolute-runs"


def test_loader_reads_utf8_json_from_disk(tmp_path: Path) -> None:
    source = tmp_path / "experiment.json"
    source.write_text(json.dumps(_payload()), encoding="utf-8")

    config = load_experiment_config(source)

    assert config.name == "Hypertension equivalence"
    assert config.output_root == tmp_path / "runs"


def test_loader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ExperimentConfigurationIOError, match="not found"):
        load_experiment_config(tmp_path / "missing.json")


def test_loader_reports_json_location(tmp_path: Path) -> None:
    source = tmp_path / "invalid.json"
    source.write_text('{"schema_version": 1,', encoding="utf-8")

    with pytest.raises(ExperimentConfigurationError, match="line 1, column"):
        load_experiment_config(source)


def test_parse_rejects_unsupported_schema_version() -> None:
    payload = _payload()
    payload["schema_version"] = 2

    with pytest.raises(ExperimentConfigurationError, match="Unsupported"):
        parse_experiment_config(payload, base_directory=Path("configs"))


def test_parse_rejects_unknown_fields_fail_loud() -> None:
    payload = _payload()
    payload["unexpected"] = True

    with pytest.raises(ExperimentConfigurationError, match="unknown fields: unexpected"):
        parse_experiment_config(payload, base_directory=Path("configs"))


def test_parse_rejects_missing_required_fields() -> None:
    payload = _payload()
    del payload["cohort"]

    with pytest.raises(ExperimentConfigurationError, match="missing required fields: cohort"):
        parse_experiment_config(payload, base_directory=Path("configs"))

def test_parse_resolves_modules_dir_relative_to_base_directory(
    tmp_path: Path,
) -> None:
    base_directory = tmp_path / "configs"
    base_directory.mkdir()

    modules_dir = tmp_path / "resources" / "synthea" / "modules"
    modules_dir.mkdir(parents=True)

    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["modules_dir"] = "../resources/synthea/modules"

    config = parse_experiment_config(
        payload,
        base_directory=base_directory,
    )

    assert config.cohort.modules_dir == modules_dir.resolve()


def test_parse_rejects_missing_modules_dir(
    tmp_path: Path,
) -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["modules_dir"] = "missing/modules"

    with pytest.raises(
        ExperimentConfigurationError,
        match="modules_dir does not exist",
    ):
        parse_experiment_config(
            payload,
            base_directory=tmp_path,
        )

def test_parse_rejects_invalid_reference_date() -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["reference_date"] = "31-12-2024"

    with pytest.raises(ExperimentConfigurationError, match="YYYY-MM-DD"):
        parse_experiment_config(payload, base_directory=Path("configs"))


def test_parse_rejects_invalid_simulator_kind() -> None:
    payload = _payload()
    simulators = payload["simulators"]
    assert isinstance(simulators, list)
    assert isinstance(simulators[0], dict)
    simulators[0]["kind"] = "java"

    with pytest.raises(ExperimentConfigurationError, match="must be one of"):
        parse_experiment_config(payload, base_directory=Path("configs"))


def test_parse_rejects_duplicate_or_missing_simulator_contract() -> None:
    payload = _payload()
    simulators = payload["simulators"]
    assert isinstance(simulators, list)
    simulators.pop()

    with pytest.raises(ExperimentConfigurationError, match="exactly one Synthea"):
        parse_experiment_config(payload, base_directory=Path("configs"))
