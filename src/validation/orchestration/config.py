"""Strict JSON loading for reproducible experiment configurations.

The loader is intentionally limited to deserialization and boundary validation.
Scientific validation belongs to the domain models; filesystem execution checks
belong to runners and workspaces.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from .exceptions import ExperimentConfigurationError, ExperimentConfigurationIOError
from .models import (
    CohortConfig,
    ExperimentConfig,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
)

__all__ = [
    "EXPERIMENT_CONFIG_SCHEMA_VERSION",
    "load_experiment_config",
    "parse_experiment_config",
]

EXPERIMENT_CONFIG_SCHEMA_VERSION = 1
_ENCODING = "utf-8"

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "id",
        "name",
        "description",
        "cohort",
        "simulators",
        "output_root",
        "report_formats",
        "tags",
        "metadata",
    }
)
_COHORT_FIELDS = frozenset(
    {
        "population",
        "seed",
        "modules",
        "module_files",
        "reference_date",
        "min_age",
        "max_age",
        "step_days",
        "years_of_history",
        "wellness_encounters",
        "vitals",
        "mortality",
        "keystone",
        "ground_truth",
        "output_format",
        "profile_file",
        "parameters",
    }
)
_SIMULATOR_FIELDS = frozenset(
    {
        "kind",
        "command",
        "working_directory",
        "output_subdirectory",
        "timeout_seconds",
        "environment",
        "arguments",
        "expected_output_files",
    }
)


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    """Load one UTF-8 JSON experiment specification from ``path``.

    Relative paths are resolved against the configuration file directory. This
    makes configuration semantics independent from the caller's working directory.
    """

    source = Path(path).expanduser()
    if not source.exists():
        raise ExperimentConfigurationIOError(
            f"Experiment configuration file not found: {source}",
            context={"path": source},
        )
    if not source.is_file():
        raise ExperimentConfigurationIOError(
            f"Experiment configuration path is not a file: {source}",
            context={"path": source},
        )

    try:
        text = source.read_text(encoding=_ENCODING)
    except UnicodeDecodeError as error:
        raise ExperimentConfigurationError(
            f"Experiment configuration must be UTF-8 encoded: {source}",
            context={"path": source},
        ) from error
    except OSError as error:
        raise ExperimentConfigurationIOError(
            f"Unable to read experiment configuration {source}: {error}",
            context={"path": source},
        ) from error

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ExperimentConfigurationError(
            f"Invalid JSON in {source} at line {error.lineno}, "
            f"column {error.colno}: {error.msg}.",
            context={
                "path": source,
                "line": error.lineno,
                "column": error.colno,
            },
        ) from error

    return parse_experiment_config(payload, base_directory=source.parent)


def parse_experiment_config(
    payload: Mapping[str, Any],
    *,
    base_directory: str | Path,
) -> ExperimentConfig:
    """Convert a decoded mapping into the immutable experiment domain model."""

    root = _mapping(payload, "configuration")
    _reject_unknown_fields(root, _ROOT_FIELDS, "configuration")
    _require_fields(
        root,
        {"schema_version", "id", "name", "cohort", "simulators", "output_root"},
        "configuration",
    )

    schema_version = _integer(root["schema_version"], "schema_version")
    if schema_version != EXPERIMENT_CONFIG_SCHEMA_VERSION:
        raise ExperimentConfigurationError(
            "Unsupported experiment configuration schema_version "
            f"{schema_version}; expected {EXPERIMENT_CONFIG_SCHEMA_VERSION}.",
            context={
                "schema_version": schema_version,
                "supported_schema_version": EXPERIMENT_CONFIG_SCHEMA_VERSION,
            },
        )

    base = Path(base_directory).expanduser()
    cohort = _parse_cohort(_mapping(root["cohort"], "cohort"), base)
    simulators = _parse_simulators(root["simulators"], base)

    try:
        return ExperimentConfig(
            id=_string(root["id"], "id"),
            name=_string(root["name"], "name"),
            description=_optional_string(root.get("description"), "description"),
            cohort=cohort,
            simulators=simulators,
            output_root=_resolve_path(root["output_root"], base, "output_root"),
            report_formats=_parse_report_formats(root.get("report_formats", ["html"])),
            tags=_string_sequence(root.get("tags", []), "tags"),
            metadata=_mapping(root.get("metadata", {}), "metadata"),
        )
    except (TypeError, ValueError) as error:
        raise ExperimentConfigurationError(
            f"Invalid experiment configuration: {error}",
            context={"field": "configuration"},
        ) from error


def _parse_cohort(payload: Mapping[str, Any], base: Path) -> CohortConfig:
    _reject_unknown_fields(payload, _COHORT_FIELDS, "cohort")
    _require_fields(payload, {"population", "seed"}, "cohort")
    if "modules" not in payload and "module_files" not in payload:
        raise ExperimentConfigurationError(
            "cohort requires at least one of: modules or module_files.",
            context={"field": "cohort"},
        )

    reference_date = payload.get("reference_date")
    parsed_reference_date: date | None = None
    if reference_date is not None:
        text = _string(reference_date, "cohort.reference_date")
        try:
            parsed_reference_date = date.fromisoformat(text)
        except ValueError as error:
            raise ExperimentConfigurationError(
                "cohort.reference_date must use ISO format YYYY-MM-DD.",
                context={"field": "cohort.reference_date", "value": text},
            ) from error

    try:
        return CohortConfig(
            population=_integer(payload["population"], "cohort.population"),
            seed=_integer(payload["seed"], "cohort.seed"),
            modules=_string_sequence(payload.get("modules", []), "cohort.modules"),
            reference_date=parsed_reference_date,
            min_age=_optional_integer(payload.get("min_age"), "cohort.min_age"),
            max_age=_optional_integer(payload.get("max_age"), "cohort.max_age"),
            parameters=_mapping(payload.get("parameters", {}), "cohort.parameters"),
            module_files=tuple(
                _resolve_path(item, base, "cohort.module_files")
                for item in payload.get("module_files", [])
            ),
            step_days=_optional_integer(payload.get("step_days"), "cohort.step_days"),
            years_of_history=_optional_integer(payload.get("years_of_history"), "cohort.years_of_history"),
            wellness_encounters=_boolean(payload.get("wellness_encounters", False),"cohort.wellness_encounters"),
            vitals=_boolean(payload.get("vitals", False),"cohort.vitals"),
            mortality=_boolean(payload.get("mortality", False),"cohort.mortality"),
            keystone=_boolean(payload.get("keystone", False),"cohort.keystone"),
            ground_truth=_boolean(payload.get("ground_truth", False),"cohort.ground_truth"),
            output_format=_string(payload.get("output_format","csv"),"cohort.output_format"),
            profile_file=None if payload.get("profile_file") is None else _resolve_path(payload["profile_file"], base, "cohort.profile_file"),
        )
    except (TypeError, ValueError) as error:
        raise ExperimentConfigurationError(
            f"Invalid cohort configuration: {error}",
            context={"field": "cohort"},
        ) from error


def _parse_simulators(value: Any, base: Path) -> tuple[SimulatorConfig, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ExperimentConfigurationError(
            "simulators must be an array.",
            context={"field": "simulators"},
        )

    simulators: list[SimulatorConfig] = []
    for index, item in enumerate(value):
        field = f"simulators[{index}]"
        payload = _mapping(item, field)
        _reject_unknown_fields(payload, _SIMULATOR_FIELDS, field)
        _require_fields(
            payload,
            {"kind", "command", "working_directory", "output_subdirectory"},
            field,
        )
        try:
            kind = SimulatorKind(_string(payload["kind"], f"{field}.kind"))
        except ValueError as error:
            allowed = ", ".join(item.value for item in SimulatorKind)
            raise ExperimentConfigurationError(
                f"{field}.kind must be one of: {allowed}.",
                context={"field": f"{field}.kind"},
            ) from error

        try:
            simulators.append(
                SimulatorConfig(
                    kind=kind,
                    command=_string_sequence(payload["command"], f"{field}.command"),
                    working_directory=_resolve_path(
                        payload["working_directory"],
                        base,
                        f"{field}.working_directory",
                    ),
                    output_subdirectory=_string(
                        payload["output_subdirectory"],
                        f"{field}.output_subdirectory",
                    ),
                    timeout_seconds=_number(
                        payload.get("timeout_seconds", 3600.0),
                        f"{field}.timeout_seconds",
                    ),
                    environment=_string_mapping(
                        payload.get("environment", {}),
                        f"{field}.environment",
                    ),
                    arguments=_mapping(
                        payload.get("arguments", {}),
                        f"{field}.arguments",
                    ),
                    expected_output_files=_string_sequence(
                        payload.get("expected_output_files", []),
                        f"{field}.expected_output_files",
                    ),
                )
            )
        except (TypeError, ValueError) as error:
            raise ExperimentConfigurationError(
                f"Invalid {field} configuration: {error}",
                context={"field": field},
            ) from error

    try:
        # ExperimentConfig performs the authoritative exactly-one-of-each check.
        return tuple(simulators)
    except TypeError as error:  # pragma: no cover - defensive boundary
        raise ExperimentConfigurationError(str(error)) from error


def _parse_report_formats(value: Any) -> tuple[ReportFormat, ...]:
    formats: list[ReportFormat] = []
    for index, item in enumerate(_string_sequence(value, "report_formats")):
        try:
            formats.append(ReportFormat(item))
        except ValueError as error:
            allowed = ", ".join(item.value for item in ReportFormat)
            raise ExperimentConfigurationError(
                f"report_formats[{index}] must be one of: {allowed}.",
                context={"field": f"report_formats[{index}]"},
            ) from error
    return tuple(formats)


def _resolve_path(value: Any, base: Path, field: str) -> Path:
    path = Path(_string(value, field)).expanduser()
    return path if path.is_absolute() else base / path


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExperimentConfigurationError(
            f"{field} must be an object.",
            context={"field": field},
        )
    for key in value:
        if not isinstance(key, str):
            raise ExperimentConfigurationError(
                f"{field} keys must be strings.",
                context={"field": field},
            )
    return value


def _string_mapping(value: Any, field: str) -> Mapping[str, str]:
    payload = _mapping(value, field)
    return {key: _string(item, f"{field}.{key}") for key, item in payload.items()}


def _string_sequence(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ExperimentConfigurationError(
            f"{field} must be an array of strings.",
            context={"field": field},
        )
    return tuple(_string(item, f"{field}[{index}]") for index, item in enumerate(value))


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExperimentConfigurationError(
            f"{field} must be a non-empty string.",
            context={"field": field},
        )
    return value.strip()


def _optional_string(value: Any, field: str) -> str | None:
    return None if value is None else _string(value, field)


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExperimentConfigurationError(
            f"{field} must be an integer.",
            context={"field": field},
        )
    return value


def _optional_integer(value: Any, field: str) -> int | None:
    return None if value is None else _integer(value, field)



def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ExperimentConfigurationError(
            f"{field} must be a boolean.",
            context={"field": field},
        )
    return value

def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentConfigurationError(
            f"{field} must be numeric.",
            context={"field": field},
        )
    return float(value)


def _reject_unknown_fields(
    payload: Mapping[str, Any],
    allowed: frozenset[str],
    field: str,
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ExperimentConfigurationError(
            f"{field} contains unknown fields: {', '.join(unknown)}.",
            context={"field": field, "unknown_fields": unknown},
        )


def _require_fields(
    payload: Mapping[str, Any],
    required: set[str],
    field: str,
) -> None:
    missing = sorted(required - set(payload))
    if missing:
        raise ExperimentConfigurationError(
            f"{field} is missing required fields: {', '.join(missing)}.",
            context={"field": field, "missing_fields": missing},
        )