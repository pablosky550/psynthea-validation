"""Tests for the public production experiment runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from validation.orchestration.configuration import parse_experiment_config
from validation.orchestration.execution import (
    ExperimentRunnerError,
    run_experiment,
)
from validation.orchestration.models import ExperimentConfig


def _config(*modules: str) -> ExperimentConfig:
    return parse_experiment_config(
        {
            "schema_version": 1,
            "id": "hypertension-pilot",
            "name": "Hypertension pilot",
            "cohort": {
                "population": 10,
                "seed": 42,
                "modules": list(modules),
                "reference_date": "2026-01-01",
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
            "output_root": "results",
        },
        base_directory=Path("/tmp/experiment"),
    )


@dataclass
class _FakeOrchestrator:
    result: object
    calls: list[tuple[ExperimentConfig, str | None]]

    def execute(
        self,
        config: ExperimentConfig,
        *,
        run_id: str | None = None,
    ) -> Any:
        self.calls.append((config, run_id))
        return self.result


def test_run_experiment_infers_single_module_and_executes() -> None:
    config = _config("Hypertension")
    expected = object()
    calls: list[tuple[ExperimentConfig, str | None]] = []
    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> _FakeOrchestrator:
        captured.update(kwargs)
        return _FakeOrchestrator(expected, calls)

    observed = run_experiment(
        config,
        run_id="run-001",
        orchestrator_factory=factory,
        orchestrator_options={"provider_metadata": {"source": "test"}},
    )

    assert observed is expected
    assert captured == {
        "module_name": "Hypertension",
        "provider_metadata": {"source": "test"},
    }
    assert calls == [(config, "run-001")]


def test_run_experiment_loads_path_with_public_codec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config("Hypertension")
    loaded: list[Path | str] = []

    monkeypatch.setattr(
        "validation.orchestration.execution.load_experiment_config",
        lambda path: loaded.append(path) or config,
    )

    orchestrator = _FakeOrchestrator(object(), [])
    run_experiment(
        "experiment.json",
        orchestrator_factory=lambda **_: orchestrator,
    )

    assert loaded == ["experiment.json"]
    assert orchestrator.calls == [(config, None)]


def test_run_experiment_requires_module_for_multi_module_config() -> None:
    config = _config("Hypertension", "Diabetes")

    with pytest.raises(
        ExperimentRunnerError,
        match="module_name is required",
    ):
        run_experiment(config)


def test_run_experiment_rejects_unconfigured_module() -> None:
    with pytest.raises(
        ExperimentRunnerError,
        match="is not configured",
    ):
        run_experiment(
            _config("Hypertension"),
            module_name="Diabetes",
        )


def test_run_experiment_rejects_module_override_in_options() -> None:
    with pytest.raises(
        ExperimentRunnerError,
        match="must not contain module_name",
    ):
        run_experiment(
            _config("Hypertension"),
            orchestrator_options={"module_name": "Hypertension"},
        )


def test_run_experiment_rejects_invalid_factory_product() -> None:
    with pytest.raises(TypeError, match="callable execute"):
        run_experiment(
            _config("Hypertension"),
            orchestrator_factory=lambda **_: object(),
        )


def test_run_experiment_rejects_empty_run_id() -> None:
    with pytest.raises(ExperimentRunnerError, match="run_id must not be empty"):
        run_experiment(_config("Hypertension"), run_id="  ")