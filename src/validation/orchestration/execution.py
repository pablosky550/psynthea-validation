"""Public application runner for complete validation experiments.

This module is the stable boundary used by command-line interfaces, notebooks
and external applications.  It accepts either an already validated
``ExperimentConfig`` or a JSON configuration path, composes the production
orchestrator and executes exactly one experiment.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from validation.orchestration.configuration import (
    load_experiment_config,
    resolve_cohort_modules,
)

from validation.orchestration.models import ExperimentConfig
from validation.orchestration.orchestrator import OrchestrationExecution
from validation.orchestration.production import build_production_orchestrator

__all__ = [
    "ExperimentRunnerError",
    "run_experiment",
]


class ExperimentRunnerError(ValueError):
    """Raised when the public experiment runner cannot resolve its inputs."""


class _ExecutableOrchestrator(Protocol):
    def execute(
        self,
        config: ExperimentConfig,
        *,
        run_id: str | None = None,
    ) -> OrchestrationExecution:
        """Execute one experiment."""


ProductionOrchestratorFactory = Callable[..., _ExecutableOrchestrator]


def run_experiment(
    config: ExperimentConfig | Path | str,
    *,
    run_id: str | None = None,
    module_name: str | None = None,
    orchestrator_options: Mapping[str, Any] | None = None,
    orchestrator_factory: ProductionOrchestratorFactory = (
        build_production_orchestrator
    ),
) -> OrchestrationExecution:
    """Execute one complete production experiment.

    ``config`` may be an immutable domain object or a path to the strict JSON
    format handled by :func:`load_experiment_config`.  When ``module_name`` is
    omitted it is inferred only if the cohort contains exactly one module;
    multi-module experiments must select the root-cause scope explicitly.

    ``orchestrator_options`` is an explicit dependency-injection boundary for
    applications and tests.  The mapping is copied before use and may not
    override ``module_name``.
    """

    resolved_config = _resolve_config(config)
    resolved_module = _resolve_module_name(
        resolved_config,
        module_name,
    )
    resolved_run_id = _optional_text(run_id, "run_id")

    if not callable(orchestrator_factory):
        raise TypeError("orchestrator_factory must be callable.")

    options = _options(orchestrator_options)
    if "module_name" in options:
        raise ExperimentRunnerError(
            "orchestrator_options must not contain module_name."
        )

    orchestrator = orchestrator_factory(
        module_name=resolved_module,
        **options,
    )

    execute = getattr(orchestrator, "execute", None)
    if not callable(execute):
        raise TypeError(
            "orchestrator_factory must return an object with a callable "
            "execute method."
        )

    return orchestrator.execute(
        resolved_config,
        run_id=resolved_run_id,
    )


def _resolve_config(
    value: ExperimentConfig | Path | str,
) -> ExperimentConfig:
    if isinstance(value, ExperimentConfig):
        return value
    if isinstance(value, (Path, str)):
        return load_experiment_config(value)
    raise TypeError(
        "config must be an ExperimentConfig or a filesystem path."
    )


def _resolve_module_name(
    config: ExperimentConfig,
    value: str | None,
) -> str:
    resolved_names = resolve_cohort_modules(config.cohort)

    file_module_names = tuple(
        module_file.stem
        for module_file in config.cohort.module_files
    )

    configured = tuple(
        dict.fromkeys((*resolved_names, *file_module_names))
    )

    if value is None:
        if len(configured) != 1:
            raise ExperimentRunnerError(
                "module_name is required when the experiment configures "
                f"{len(configured)} modules."
            )
        return configured[0]

    normalized = _required_text(value, "module_name")

    if normalized not in configured:
        raise ExperimentRunnerError(
            f"module_name {normalized!r} is not configured for experiment "
            f"{config.id!r}. Configured modules: {configured!r}."
        )

    return normalized


def _options(
    value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("orchestrator_options must be a mapping or None.")
    for key in value:
        if not isinstance(key, str):
            raise TypeError(
                "orchestrator_options keys must be strings."
            )
    return dict(value)


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ExperimentRunnerError(
            f"{field_name} must not be empty."
        )
    return normalized


def _optional_text(
    value: str | None,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)