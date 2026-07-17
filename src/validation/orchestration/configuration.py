"""Strict JSON codec for :class:`ExperimentConfig`.

The orchestration configuration is a scientific input and therefore must be
validated as rigorously as any generated artefact.  This module owns only the
boundary between JSON-compatible data and the immutable orchestration domain
models.  It performs no workspace creation, simulator execution or stage
composition.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
import json
from pathlib import Path
from typing import Any, Final, NoReturn

from validation.orchestration.models import (
    CohortConfig,
    ExperimentConfig,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
)

__all__ = [
    "ExperimentConfigurationError",
    "dump_experiment_config",
    "experiment_config_to_dict",
    "load_experiment_config",
    "parse_experiment_config",
]


_EXPERIMENT_CONFIGURATION_SCHEMA_VERSION: Final = 1

_ROOT_FIELDS: Final = frozenset(
    {
        "schema_version",
        "id",
        "name",
        "cohort",
        "simulators",
        "output_root",
        "report_formats",
        "description",
        "tags",
        "metadata",
    }
)

_COHORT_FIELDS: Final = frozenset(
    {
        "population",
        "seed",
        "modules",
        "reference_date",
        "min_age",
        "max_age",
        "parameters",
    }
)

_SIMULATOR_FIELDS: Final = frozenset(
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


class ExperimentConfigurationError(ValueError):
    """Raised when an experiment configuration is unsafe or invalid."""


def load_experiment_config(path: Path | str) -> ExperimentConfig:
    """Load and validate one UTF-8 JSON experiment configuration.

    Relative filesystem paths are resolved against the directory containing the
    configuration file.  Duplicate JSON object keys are rejected because they
    make the effective scientific configuration parser-dependent.
    """

    configuration_path = _configuration_path(path)

    if not configuration_path.is_file() or configuration_path.is_symlink():
        raise ExperimentConfigurationError(
            "Experiment configuration must be a regular file: "
            f"{configuration_path}."
        )

    try:
        text = configuration_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ExperimentConfigurationError(
            "Unable to read experiment configuration "
            f"{configuration_path}: {exc}"
        ) from exc

    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
        )
    except json.JSONDecodeError as exc:
        raise ExperimentConfigurationError(
            "Invalid JSON in experiment configuration "
            f"{configuration_path}: line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}."
        ) from exc

    return parse_experiment_config(
        payload,
        base_directory=configuration_path.parent,
    )


def parse_experiment_config(
    payload: Mapping[str, Any],
    *,
    base_directory: Path | str | None = None,
) -> ExperimentConfig:
    """Construct an immutable :class:`ExperimentConfig` from a mapping."""

    root = _mapping(payload, "configuration")
    _reject_unknown(root, _ROOT_FIELDS, "configuration")

    schema_version = _required(root, "schema_version", "configuration")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != _EXPERIMENT_CONFIGURATION_SCHEMA_VERSION
    ):
        raise ExperimentConfigurationError(
            "configuration.schema_version must be exactly "
            f"{_EXPERIMENT_CONFIGURATION_SCHEMA_VERSION}."
        )

    base = _base_directory(base_directory)

    cohort = _parse_cohort(
        _required(root, "cohort", "configuration")
    )

    simulator_payloads = _sequence(
        _required(root, "simulators", "configuration"),
        "configuration.simulators",
    )

    simulators = tuple(
        _parse_simulator(
            item,
            index=index,
            base_directory=base,
        )
        for index, item in enumerate(simulator_payloads)
    )

    report_formats = tuple(
        _enum(
            item,
            ReportFormat,
            f"configuration.report_formats[{index}]",
        )
        for index, item in enumerate(
            _sequence(
                root.get("report_formats", [ReportFormat.HTML.value]),
                "configuration.report_formats",
            )
        )
    )

    try:
        return ExperimentConfig(
            id=_required(root, "id", "configuration"),
            name=_required(root, "name", "configuration"),
            cohort=cohort,
            simulators=simulators,
            output_root=_resolve_path(
                _required(root, "output_root", "configuration"),
                base_directory=base,
                field_name="configuration.output_root",
            ),
            report_formats=report_formats,
            description=root.get("description"),
            tags=tuple(
                _sequence(
                    root.get("tags", []),
                    "configuration.tags",
                )
            ),
            metadata=_mapping(
                root.get("metadata", {}),
                "configuration.metadata",
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ExperimentConfigurationError(
            f"Invalid experiment configuration: {exc}"
        ) from exc


def experiment_config_to_dict(
    config: ExperimentConfig,
) -> dict[str, Any]:
    """Return the canonical JSON-compatible representation of ``config``."""

    if not isinstance(config, ExperimentConfig):
        raise TypeError("config must be an ExperimentConfig.")

    return {
        "schema_version": _EXPERIMENT_CONFIGURATION_SCHEMA_VERSION,
        "id": config.id,
        "name": config.name,
        "description": config.description,
        "tags": list(config.tags),
        "output_root": str(config.output_root),
        "report_formats": [
            item.value for item in config.report_formats
        ],
        "cohort": {
            "population": config.cohort.population,
            "seed": config.cohort.seed,
            "modules": list(config.cohort.modules),
            "reference_date": (
                config.cohort.reference_date.isoformat()
                if config.cohort.reference_date is not None
                else None
            ),
            "min_age": config.cohort.min_age,
            "max_age": config.cohort.max_age,
            "parameters": _plain_value(config.cohort.parameters),
        },
        "simulators": [
            {
                "kind": simulator.kind.value,
                "command": list(simulator.command),
                "working_directory": str(simulator.working_directory),
                "output_subdirectory": simulator.output_subdirectory,
                "timeout_seconds": simulator.timeout_seconds,
                "environment": dict(simulator.environment),
                "arguments": _plain_value(simulator.arguments),
                "expected_output_files": list(
                    simulator.expected_output_files
                ),
            }
            for simulator in config.simulators
        ],
        "metadata": _plain_value(config.metadata),
    }


def dump_experiment_config(
    config: ExperimentConfig,
    *,
    indent: int = 2,
) -> str:
    """Serialize ``config`` as deterministic UTF-8 JSON text."""

    if isinstance(indent, bool) or not isinstance(indent, int):
        raise TypeError("indent must be an integer.")
    if indent < 0:
        raise ValueError("indent must be non-negative.")

    return json.dumps(
        experiment_config_to_dict(config),
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def _parse_cohort(payload: Any) -> CohortConfig:
    cohort = _mapping(payload, "configuration.cohort")
    _reject_unknown(cohort, _COHORT_FIELDS, "configuration.cohort")

    reference_date = cohort.get("reference_date")
    if reference_date is not None:
        if not isinstance(reference_date, str):
            raise ExperimentConfigurationError(
                "configuration.cohort.reference_date must be an "
                "ISO-8601 date string or null."
            )
        try:
            reference_date = date.fromisoformat(reference_date)
        except ValueError as exc:
            raise ExperimentConfigurationError(
                "configuration.cohort.reference_date must be a valid "
                "ISO-8601 date."
            ) from exc

    try:
        return CohortConfig(
            population=_required(
                cohort,
                "population",
                "configuration.cohort",
            ),
            seed=_required(
                cohort,
                "seed",
                "configuration.cohort",
            ),
            modules=tuple(
                _sequence(
                    _required(
                        cohort,
                        "modules",
                        "configuration.cohort",
                    ),
                    "configuration.cohort.modules",
                )
            ),
            reference_date=reference_date,
            min_age=cohort.get("min_age"),
            max_age=cohort.get("max_age"),
            parameters=_mapping(
                cohort.get("parameters", {}),
                "configuration.cohort.parameters",
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ExperimentConfigurationError(
            f"Invalid configuration.cohort: {exc}"
        ) from exc


def _parse_simulator(
    payload: Any,
    *,
    index: int,
    base_directory: Path | None,
) -> SimulatorConfig:
    field = f"configuration.simulators[{index}]"
    simulator = _mapping(payload, field)
    _reject_unknown(simulator, _SIMULATOR_FIELDS, field)

    kind = _enum(
        _required(simulator, "kind", field),
        SimulatorKind,
        f"{field}.kind",
    )

    try:
        return SimulatorConfig(
            kind=kind,
            command=tuple(
                _sequence(
                    _required(simulator, "command", field),
                    f"{field}.command",
                )
            ),
            working_directory=_resolve_path(
                _required(simulator, "working_directory", field),
                base_directory=base_directory,
                field_name=f"{field}.working_directory",
            ),
            output_subdirectory=_required(
                simulator,
                "output_subdirectory",
                field,
            ),
            timeout_seconds=simulator.get(
                "timeout_seconds",
                3600.0,
            ),
            environment=_mapping(
                simulator.get("environment", {}),
                f"{field}.environment",
            ),
            arguments=_mapping(
                simulator.get("arguments", {}),
                f"{field}.arguments",
            ),
            expected_output_files=tuple(
                _sequence(
                    simulator.get("expected_output_files", []),
                    f"{field}.expected_output_files",
                )
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ExperimentConfigurationError(
            f"Invalid {field}: {exc}"
        ) from exc


def _configuration_path(value: Path | str) -> Path:
    if isinstance(value, str):
        if not value.strip():
            raise ExperimentConfigurationError(
                "Experiment configuration path must not be empty."
            )
        path = Path(value).expanduser()
    elif isinstance(value, Path):
        path = value.expanduser()
    else:
        raise TypeError("path must be a Path or string.")
    return path.resolve(strict=False)


def _base_directory(value: Path | str | None) -> Path | None:
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            raise ExperimentConfigurationError(
                "base_directory must not be empty."
            )
        path = Path(value).expanduser()
    elif isinstance(value, Path):
        path = value.expanduser()
    else:
        raise TypeError("base_directory must be a Path, string or None.")
    return path.resolve(strict=False)


def _resolve_path(
    value: Any,
    *,
    base_directory: Path | None,
    field_name: str,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ExperimentConfigurationError(
            f"{field_name} must be a non-empty path string."
        )

    path = Path(value).expanduser()
    if not path.is_absolute() and base_directory is not None:
        path = base_directory / path
    return path.resolve(strict=False)


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExperimentConfigurationError(
            f"{field_name} must be a JSON object."
        )
    for key in value:
        if not isinstance(key, str):
            raise ExperimentConfigurationError(
                f"{field_name} keys must be strings."
            )
    return value


def _sequence(value: Any, field_name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ExperimentConfigurationError(
            f"{field_name} must be a JSON array."
        )
    return value


def _required(
    payload: Mapping[str, Any],
    name: str,
    field_name: str,
) -> Any:
    if name not in payload:
        raise ExperimentConfigurationError(
            f"{field_name}.{name} is required."
        )
    return payload[name]


def _reject_unknown(
    payload: Mapping[str, Any],
    allowed: frozenset[str],
    field_name: str,
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ExperimentConfigurationError(
            f"{field_name} contains unknown field(s): "
            + ", ".join(unknown)
            + "."
        )


def _enum(
    value: Any,
    enum_type: type[SimulatorKind] | type[ReportFormat],
    field_name: str,
) -> SimulatorKind | ReportFormat:
    if not isinstance(value, str):
        raise ExperimentConfigurationError(
            f"{field_name} must be a string."
        )
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ExperimentConfigurationError(
            f"{field_name} must be one of: {allowed}."
        ) from exc


def _unique_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExperimentConfigurationError(
                f"Duplicate JSON field {key!r}."
            )
        result[key] = value
    return result


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _plain_value(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_plain_value(item) for item in value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        enum_value = getattr(value, "value")
        if isinstance(enum_value, str):
            return enum_value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    _unsupported_json_value(value)


def _unsupported_json_value(value: Any) -> NoReturn:
    raise ExperimentConfigurationError(
        "Configuration metadata contains a value that is not JSON-compatible: "
        f"{type(value).__name__}."
    )