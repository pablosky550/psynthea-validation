from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from validation.orchestration.configuration import (
    ExperimentConfigurationError,
    apply_experiment_overrides,
    experiment_config_to_dict,
    parse_experiment_config,
)


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": "hypertension-window",
        "name": "Hypertension temporal validation",
        "output_root": "results",
        "cohort": {
            "population": 100,
            "seed": 42,
            "modules": ["Hypertension"],
            "reference_date": "2024-12-31",
        },
        "simulators": [
            {
                "kind": "synthea",
                "command": ["synthea"],
                "working_directory": ".",
                "output_subdirectory": "synthea",
            },
            {
                "kind": "psynthea",
                "command": ["psynthea"],
                "working_directory": ".",
                "output_subdirectory": "psynthea",
            },
        ],
    }


def test_parse_and_serialize_observation_window_round_trip(tmp_path: Path) -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["observation_start_date"] = "2020-01-01"
    cohort["observation_end_date"] = "2024-12-31"

    config = parse_experiment_config(payload, base_directory=tmp_path)

    assert config.cohort.observation_start_date == date(2020, 1, 1)
    assert config.cohort.observation_end_date == date(2024, 12, 31)

    canonical = experiment_config_to_dict(config)
    canonical_cohort = canonical["cohort"]
    assert isinstance(canonical_cohort, dict)
    assert canonical_cohort["observation_start_date"] == "2020-01-01"
    assert canonical_cohort["observation_end_date"] == "2024-12-31"
    assert parse_experiment_config(canonical) == config


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("observation_start_date", "01-01-2020"),
        ("observation_end_date", "2024-02-30"),
        ("observation_start_date", 20200101),
        ("observation_end_date", True),
        ("observation_start_date", "2020-01-01T00:00:00"),
    ],
)
def test_invalid_observation_date_is_rejected(
    field_name: str,
    value: object,
) -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["observation_start_date"] = "2020-01-01"
    cohort["observation_end_date"] = "2024-12-31"
    cohort[field_name] = value

    with pytest.raises(
        ExperimentConfigurationError,
        match=rf"configuration\.cohort\.{field_name}.*ISO-8601 date",
    ):
        parse_experiment_config(payload)


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("2020-01-01", None, "must be provided together"),
        (None, "2024-12-31", "must be provided together"),
        ("2025-01-01", "2024-12-31", "must not exceed"),
        ("2020-01-01", "2025-01-01", "must not exceed reference_date"),
    ],
)
def test_temporal_contract_errors_are_wrapped_with_cohort_context(
    start: str | None,
    end: str | None,
    message: str,
) -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["observation_start_date"] = start
    cohort["observation_end_date"] = end

    with pytest.raises(
        ExperimentConfigurationError,
        match=rf"Invalid configuration\.cohort: .*{message}",
    ):
        parse_experiment_config(payload)


def test_absent_window_serializes_as_explicit_nulls(tmp_path: Path) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path)

    canonical = experiment_config_to_dict(config)
    cohort = canonical["cohort"]
    assert isinstance(cohort, dict)
    assert cohort["observation_start_date"] is None
    assert cohort["observation_end_date"] is None


def test_overrides_apply_complete_window_without_mutating_source(
    tmp_path: Path,
) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path)

    resolved = apply_experiment_overrides(
        config,
        observation_start_date=date(2021, 1, 1),
        observation_end_date=date(2024, 12, 31),
    )

    assert resolved.cohort.observation_start_date == date(2021, 1, 1)
    assert resolved.cohort.observation_end_date == date(2024, 12, 31)
    assert config.cohort.observation_start_date is None
    assert config.cohort.observation_end_date is None


def test_partial_override_is_rejected_when_source_has_no_window(
    tmp_path: Path,
) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path)

    with pytest.raises(
        ExperimentConfigurationError,
        match="must be provided together",
    ):
        apply_experiment_overrides(
            config,
            observation_start_date=date(2021, 1, 1),
        )


def test_single_boundary_override_can_update_existing_window(
    tmp_path: Path,
) -> None:
    payload = _payload()
    cohort = payload["cohort"]
    assert isinstance(cohort, dict)
    cohort["observation_start_date"] = "2020-01-01"
    cohort["observation_end_date"] = "2024-12-31"
    config = parse_experiment_config(payload, base_directory=tmp_path)

    resolved = apply_experiment_overrides(
        config,
        observation_start_date=date(2021, 1, 1),
    )

    assert resolved.cohort.observation_start_date == date(2021, 1, 1)
    assert resolved.cohort.observation_end_date == date(2024, 12, 31)


def test_datetime_override_is_rejected_even_though_it_is_date_subclass(
    tmp_path: Path,
) -> None:
    config = parse_experiment_config(_payload(), base_directory=tmp_path)

    with pytest.raises(
        ExperimentConfigurationError,
        match="observation_start_date must be a date or None",
    ):
        apply_experiment_overrides(
            config,
            observation_start_date=datetime(2021, 1, 1),
            observation_end_date=date(2024, 12, 31),
        )