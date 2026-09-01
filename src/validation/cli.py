"""Command-line orchestration for reproducible validation runs.

This module is the composition root of the validation package. It converts a
validated run configuration into a complete set of scientific artefacts while
keeping clinical metrics, statistical inference, plotting and report rendering
inside their dedicated layers.

Output publication is transactional: artefacts are built in an isolated staging
directory and committed only after every pipeline stage succeeds. Existing
results therefore remain intact when a new execution fails.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from enum import IntEnum
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import logging
from pathlib import Path
import platform
import shutil
import sys
import time
from typing import Any, Iterator, TextIO
from uuid import uuid4

import pandas as pd

from validation.comparison.statistical_comparison import (
    ModuleStatisticalComparisonResult,
    compare_module_statistics,
)
from validation.config import (
    CONFIG_SCHEMA_VERSION,
    ConfigurationError,
    OutputConfig,
    ValidationRunConfig,
)
from validation.loaders import load_psynthea, load_synthea
from validation.orchestration import (
    ExecutionStatus,
    ExperimentConfig,
    apply_experiment_overrides,
    ExperimentConfigurationError,
    ExperimentRunnerError,
    OrchestrationError,
    dump_experiment_config,
    load_experiment_config,
    run_experiment,
)
from validation.orchestration.orchestrator import OrchestrationExecution

__all__ = [
    "ExitCode",
    "ValidationRunArtifacts",
    "ValidationCliError",
    "InputDataError",
    "PipelineExecutionError",
    "ArtifactPersistenceError",
    "build_parser",
    "load_config",
    "run_validation",
    "run_full_experiment",
    "main",
]

_LOGGER = logging.getLogger("validation.cli")
_CONFIG_ENCODING = "utf-8"
_MANIFEST_FILENAME = "run_manifest.json"
_RESOLVED_CONFIG_FILENAME = "resolved_config.json"
_TABLE_FORMAT = "csv"
_PACKAGE_NAME = "psynthea-validation"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"
_DECISION_ORDER = ("pass", "warning", "fail", "skipped")


class ExitCode(IntEnum):
    """Stable process exit codes exposed by the validation CLI."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_ARGUMENTS = 2
    CONFIGURATION_ERROR = 3
    INPUT_DATA_ERROR = 4
    PIPELINE_ERROR = 5
    INTERRUPTED = 130


class ValidationCliError(RuntimeError):
    """Base class for expected technical failures in CLI orchestration."""


class InputDataError(ValidationCliError):
    """Raised when cohort or configuration input cannot be read safely."""


class PipelineExecutionError(ValidationCliError):
    """Raised when a scientific pipeline stage cannot complete."""


class ArtifactPersistenceError(ValidationCliError):
    """Raised when generated artefacts cannot be persisted or committed."""


@dataclass(frozen=True, slots=True)
class ValidationRunArtifacts:
    """Paths and results produced by one successfully committed run."""

    report_path: Path
    manifest_path: Path
    resolved_config_path: Path
    table_paths: tuple[Path, ...]
    figure_paths: tuple[Path, ...]
    comparisons: tuple[ModuleStatisticalComparisonResult, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class _ParserExit(Exception):
    status: int
    message: str | None = None


class _ArgumentParser(argparse.ArgumentParser):
    """Argument parser using injectable streams and non-terminating exits."""

    def __init__(
        self,
        *args: Any,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr

    def _print_message(self, message: str | None, file: TextIO | None = None) -> None:
        if not message:
            return
        target = self.stderr if file is self.stderr or file is sys.stderr else self.stdout
        target.write(message)

    def print_help(self, file: TextIO | None = None) -> None:
        super().print_help(file or self.stdout)

    def print_usage(self, file: TextIO | None = None) -> None:
        super().print_usage(file or self.stderr)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if message:
            self._print_message(message, self.stdout if status == 0 else self.stderr)
        raise _ParserExit(int(status), message)

    def error(self, message: str) -> None:
        self.print_usage(self.stderr)
        self.exit(
            int(ExitCode.INVALID_ARGUMENTS),
            f"{self.prog}: error: {message}\n",
        )


def _parse_iso_date(value: str) -> date:
    """Parse an ISO-8601 calendar date for argparse."""

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid ISO date {value!r}; expected YYYY-MM-DD"
        ) from exc


def build_parser(
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> argparse.ArgumentParser:
    """Build the CLI parser without reading process-global arguments."""

    parser = _ArgumentParser(
        prog="psynthea-validation",
        description=(
            "Run reproducible functional and statistical validation of "
            "Synthea Java against psynthea cohorts."
        ),
        stdout=stdout,
        stderr=stderr,
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to a UTF-8 JSON ValidationRunConfig document.",
    )
    parser.add_argument(
        "--experiment",
        action="store_true",
        help=(
            "Execute the complete Experiment Orchestrator pipeline instead "
            "of the legacy validation-only workflow."
        ),
    )
    parser.add_argument(
        "--run-id",
        help="Optional explicit run identifier for --experiment mode.",
    )
    parser.add_argument(
        "--module-name",
        help=(
            "Root-cause module scope for --experiment mode; required only "
            "for multi-module experiment configurations."
        ),
    )
    module_selection = parser.add_mutually_exclusive_group()
    module_selection.add_argument(
        "--module",
        dest="modules",
        action="append",
        metavar="MODULE",
        help=(
            "Override a configured cohort module identifier; repeat to select "
            "multiple modules. Mutually exclusive with --module-file. "
            "Experiment mode only."
        ),
    )
    module_selection.add_argument(
        "--module-file",
        dest="module_files",
        action="append",
        type=Path,
        metavar="PATH",
        help=(
            "Override a cohort module JSON file; repeat to select multiple files. "
            "Mutually exclusive with --module. Experiment mode only."
        ),
    )
    parser.add_argument(
        "--population",
        type=int,
        metavar="N",
        help="Override cohort population size. Experiment mode only.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        metavar="INTEGER",
        help="Override cohort random seed. Experiment mode only.",
    )
    parser.add_argument(
        "--reference-date",
        type=_parse_iso_date,
        metavar="YYYY-MM-DD",
        help="Override the cohort reference date. Experiment mode only.",
    )
    parser.add_argument(
        "--min-age",
        type=int,
        metavar="YEARS",
        help="Override the minimum generated age. Experiment mode only.",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        metavar="YEARS",
        help="Override the maximum generated age. Experiment mode only.",
    )
    parser.add_argument(
        "--step-days",
        type=int,
        metavar="DAYS",
        help="Override the simulation time-step length. Experiment mode only.",
    )
    parser.add_argument(
        "--years-of-history",
        type=int,
        metavar="YEARS",
        help="Override the generated clinical-history horizon. Experiment mode only.",
    )
    for option, destination, description in (
        ("wellness-encounters", "wellness_encounters", "wellness encounters"),
        ("vitals", "vitals", "vital-sign generation"),
        ("mortality", "mortality", "mortality modelling"),
        ("keystone", "keystone", "keystone compatibility"),
        ("ground-truth", "ground_truth", "ground-truth export"),
    ):
        parser.add_argument(
            f"--{option}",
            dest=destination,
            action=argparse.BooleanOptionalAction,
            default=None,
            help=(
                f"Enable or disable {description}; use --{option} or "
                f"--no-{option}. Experiment mode only."
            ),
        )
    parser.add_argument(
        "--output-format",
        choices=("csv", "omop"),
        help="Override the generated cohort output format. Experiment mode only.",
    )
    parser.add_argument(
        "--profile-file",
        type=Path,
        metavar="PATH",
        help="Override the Psynthea population profile file. Experiment mode only.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        metavar="PATH",
        help="Override experiment output root directory. Experiment mode only.",
    )
    parser.add_argument(
        "--experiment-id",
        help="Override the experiment identifier. Experiment mode only.",
    )
    parser.add_argument(
        "--experiment-name",
        help="Override the human-readable experiment name. Experiment mode only.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate configuration and filesystem inputs without running analyses.",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the canonical normalized configuration JSON before execution.",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip figure generation while retaining reports and tables.",
    )
    parser.add_argument(
        "--no-tables",
        action="store_true",
        help="Skip machine-readable CSV table generation.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Console logging threshold (default: INFO).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=(
            f"%(prog)s {_distribution_version()} "
            f"(config schema {CONFIG_SCHEMA_VERSION})"
        ),
    )
    return parser


def load_config(path: str | Path) -> ValidationRunConfig:
    """Load and validate a JSON run configuration from disk."""

    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise InputDataError(f"Configuration file not found: {config_path}")
    if not config_path.is_file():
        raise InputDataError(f"Configuration path is not a file: {config_path}")

    try:
        text = config_path.read_text(encoding=_CONFIG_ENCODING)
    except UnicodeDecodeError as error:
        raise ConfigurationError(
            f"Configuration must be UTF-8 encoded: {config_path}"
        ) from error
    except OSError as error:
        raise InputDataError(
            f"Unable to read configuration file {config_path}: {error}"
        ) from error

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            f"Invalid JSON in {config_path} at line {error.lineno}, "
            f"column {error.colno}: {error.msg}."
        ) from error

    return ValidationRunConfig.from_mapping(payload)


def run_validation(
    config: ValidationRunConfig,
    *,
    generated_at: datetime | None = None,
    config_source: str | Path | None = None,
    generate_plots: bool = True,
    generate_tables: bool = True,
) -> ValidationRunArtifacts:
    """Execute and transactionally persist a complete validation run.

    Scientific ``fail`` and ``warning`` decisions are successful executions.
    Exceptions represent technical failures only.
    """

    if not isinstance(config, ValidationRunConfig):
        raise TypeError("config must be a ValidationRunConfig instance.")
    if not isinstance(generate_plots, bool) or not isinstance(generate_tables, bool):
        raise TypeError("generate_plots and generate_tables must be booleans.")

    config.validate_filesystem()
    started_at = _normalise_timestamp(generated_at or datetime.now(UTC))
    monotonic_start = time.monotonic()

    synthea_cohort, psynthea_cohort = _load_cohorts(config)
    comparisons = _run_comparisons(config, synthea_cohort, psynthea_cohort)

    with _output_transaction(config) as staged_config:
        resolved_config_path = _write_resolved_config(staged_config)
        report, module_decisions = _build_report(comparisons, staged_config, started_at)
        report_path = _write_report(report, staged_config)
        table_paths = (
            _write_comparison_tables(comparisons, staged_config.output.tables_dir)
            if generate_tables
            else []
        )
        figure_paths = (
            _write_figures(comparisons, staged_config)
            if generate_plots
            else []
        )

        completed_at = datetime.now(UTC)
        manifest_path = _write_manifest(
            config=staged_config,
            original_config=config,
            comparisons=comparisons,
            module_decisions=module_decisions,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=max(0.0, time.monotonic() - monotonic_start),
            config_source=config_source,
            report_path=report_path,
            resolved_config_path=resolved_config_path,
            table_paths=table_paths,
            figure_paths=figure_paths,
        )

    final_artifacts = _rebase_artifacts(
        config=config,
        comparisons=comparisons,
        report_path=report_path,
        manifest_path=manifest_path,
        resolved_config_path=resolved_config_path,
        table_paths=table_paths,
        figure_paths=figure_paths,
    )
    _LOGGER.info("Validation completed: %s", final_artifacts.report_path)
    return final_artifacts


def run_full_experiment(
    config: ExperimentConfig | str | Path,
    *,
    run_id: str | None = None,
    module_name: str | None = None,
) -> OrchestrationExecution:
    """Execute the complete production Experiment Orchestrator pipeline."""

    return run_experiment(
        config,
        run_id=run_id,
        module_name=module_name,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """CLI entry point that always returns a stable integer exit code."""

    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser(stdout=stdout, stderr=stderr)

    try:
        try:
            args = parser.parse_args(argv)
        except _ParserExit as error:
            return error.status

        if args.experiment and (args.no_plots or args.no_tables):
            parser.print_usage(stderr)
            print(
                f"{parser.prog}: error: --no-plots and --no-tables are "
                "available only in legacy validation mode.",
                file=stderr,
            )
            return int(ExitCode.INVALID_ARGUMENTS)

        if (
            not args.experiment
            and any(
                value is not None
                for value in (
                    args.run_id,
                    args.module_name,
                    args.modules,
                    args.module_files,
                    args.population,
                    args.seed,
                    args.reference_date,
                    args.min_age,
                    args.max_age,
                    args.step_days,
                    args.years_of_history,
                    args.wellness_encounters,
                    args.vitals,
                    args.mortality,
                    args.keystone,
                    args.ground_truth,
                    args.output_format,
                    args.profile_file,
                    args.output_root,
                    args.experiment_id,
                    args.experiment_name,
                )
            )
        ):
            parser.print_usage(stderr)
            print(
                f"{parser.prog}: error: experiment overrides require --experiment.",
                file=stderr,
            )
            return int(ExitCode.INVALID_ARGUMENTS)

        with _configured_logging(args.log_level, stderr):
            if args.experiment:
                config = load_experiment_config(args.config)
                has_overrides = any(
                    value is not None
                    for value in (
                        args.experiment_id,
                        args.experiment_name,
                        args.population,
                        args.seed,
                        args.modules,
                        args.module_files,
                        args.reference_date,
                        args.min_age,
                        args.max_age,
                        args.step_days,
                        args.years_of_history,
                        args.wellness_encounters,
                        args.vitals,
                        args.mortality,
                        args.keystone,
                        args.ground_truth,
                        args.output_format,
                        args.profile_file,
                        args.output_root,
                    )
                )
                if has_overrides:
                    config = apply_experiment_overrides(
                        config,
                        experiment_id=args.experiment_id,
                        experiment_name=args.experiment_name,
                        population=args.population,
                        seed=args.seed,
                        modules=args.modules,
                        module_files=args.module_files,
                        reference_date=args.reference_date,
                        min_age=args.min_age,
                        max_age=args.max_age,
                        step_days=args.step_days,
                        years_of_history=args.years_of_history,
                        wellness_encounters=args.wellness_encounters,
                        vitals=args.vitals,
                        mortality=args.mortality,
                        keystone=args.keystone,
                        ground_truth=args.ground_truth,
                        output_format=args.output_format,
                        profile_file=args.profile_file,
                        output_root=args.output_root,
                    )

                if args.print_config:
                    print(dump_experiment_config(config), file=stdout)

                if args.validate_only:
                    print(
                        "Experiment configuration validation succeeded.",
                        file=stdout,
                    )
                    return int(ExitCode.SUCCESS)

                execution = run_full_experiment(
                    config if has_overrides else args.config,
                    run_id=args.run_id,
                    module_name=args.module_name,
                )
                _print_experiment_summary(execution, stdout)

                if execution.result.status is ExecutionStatus.SUCCEEDED:
                    return int(ExitCode.SUCCESS)

                message = execution.result.error_message or (
                    "Experiment completed with status "
                    f"{execution.result.status.value}."
                )
                print(f"Pipeline error: {message}", file=stderr)
                return int(ExitCode.PIPELINE_ERROR)

            config = load_config(args.config)

            if args.print_config:
                print(config.canonical_json(), file=stdout)

            if args.validate_only:
                config.validate_filesystem()
                print(
                    "Configuration and filesystem validation succeeded.",
                    file=stdout,
                )
                return int(ExitCode.SUCCESS)

            artifacts = run_validation(
                config,
                config_source=args.config,
                generate_plots=not args.no_plots,
                generate_tables=not args.no_tables,
            )
            _print_success_summary(artifacts, stdout)
            return int(ExitCode.SUCCESS)

    except KeyboardInterrupt:
        print("Validation interrupted by user.", file=stderr)
        return int(ExitCode.INTERRUPTED)
    except (
        ConfigurationError,
        ExperimentConfigurationError,
        ExperimentRunnerError,
    ) as error:
        print(f"Configuration error: {error}", file=stderr)
        return int(ExitCode.CONFIGURATION_ERROR)
    except InputDataError as error:
        print(f"Input data error: {error}", file=stderr)
        return int(ExitCode.INPUT_DATA_ERROR)
    except (
        PipelineExecutionError,
        ArtifactPersistenceError,
        OrchestrationError,
    ) as error:
        print(f"Pipeline error: {error}", file=stderr)
        return int(ExitCode.PIPELINE_ERROR)
    except Exception as error:  # pragma: no cover - final process safety net
        _LOGGER.exception("Unexpected validation failure")
        print(f"Unexpected error: {error}", file=stderr)
        return int(ExitCode.GENERAL_ERROR)


def _load_cohorts(config: ValidationRunConfig) -> tuple[Any, Any]:
    try:
        _LOGGER.info("Loading Synthea cohort from %s", config.inputs.synthea_dir)
        synthea = load_synthea(config.inputs.synthea_dir)
        _LOGGER.info("Loading psynthea cohort from %s", config.inputs.psynthea_dir)
        psynthea = load_psynthea(config.inputs.psynthea_dir)
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, pd.errors.ParserError) as error:
        raise InputDataError(f"Unable to load validation cohorts: {error}") from error
    except (UnicodeDecodeError, ValueError, OSError) as error:
        raise InputDataError(f"Invalid or unreadable cohort data: {error}") from error
    return synthea, psynthea


def _run_comparisons(
    config: ValidationRunConfig,
    synthea_cohort: Any,
    psynthea_cohort: Any,
) -> list[ModuleStatisticalComparisonResult]:
    comparisons: list[ModuleStatisticalComparisonResult] = []
    for module in config.modules:
        _LOGGER.info("Comparing module: %s", module.name)
        try:
            result = compare_module_statistics(
                module_name=module.name,
                synthea_cohort=synthea_cohort,
                psynthea_cohort=psynthea_cohort,
                required_tables=module.required_tables or None,
                required_signal_domains=module.required_signal_domains or None,
                expected_condition_terms=module.expected_condition_terms,
                expected_medication_terms=module.expected_medication_terms,
                expected_procedure_terms=module.expected_procedure_terms,
                expected_observation_terms=module.expected_observation_terms,
                top_n_codes=config.statistics.top_n_codes,
                alpha=config.statistics.alpha,
            )
        except Exception as error:
            raise PipelineExecutionError(
                f"Statistical comparison failed for module {module.name!r}: {error}"
            ) from error
        if not isinstance(result, ModuleStatisticalComparisonResult):
            raise PipelineExecutionError(
                f"Comparison for module {module.name!r} returned "
                f"{type(result).__name__}, expected ModuleStatisticalComparisonResult."
            )
        comparisons.append(result)
    return comparisons


def _build_report(
    comparisons: Sequence[ModuleStatisticalComparisonResult],
    config: ValidationRunConfig,
    generated_at: datetime,
) -> tuple[Any, dict[str, str]]:
    try:
        from validation.report import build_validation_report

        report = build_validation_report(
            comparisons,
            generated_at=generated_at,
            top_n_prevalence_differences=(
                config.presentation.top_n_prevalence_differences
            ),
        )
    except Exception as error:
        raise PipelineExecutionError(f"Unable to build validation report: {error}") from error

    decisions = {module.module_name: module.decision for module in report.modules}
    return report, decisions


def _write_report(report: Any, config: ValidationRunConfig) -> Path:
    try:
        from validation.report import render_markdown_report

        content = render_markdown_report(report)
        _atomic_write_text(config.output.report_path, content)
        return config.output.report_path
    except Exception as error:
        raise ArtifactPersistenceError(
            f"Unable to write Markdown report {config.output.report_path}: {error}"
        ) from error


@contextmanager
def _output_transaction(config: ValidationRunConfig) -> Iterator[ValidationRunConfig]:
    """Yield a staging configuration and atomically commit its root directory."""

    final_root = config.output.root_dir
    parent = final_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging_root = parent / f".{final_root.name}.staging-{uuid4().hex}"
    backup_root = parent / f".{final_root.name}.backup-{uuid4().hex}"

    staged_output = replace(
        config.output,
        root_dir=staging_root,
        overwrite=True,
    )
    staged_config = replace(config, output=staged_output)

    try:
        _prepare_staging_directories(staged_config)
        yield staged_config
        _commit_output_root(
            staging_root=staging_root,
            final_root=final_root,
            backup_root=backup_root,
            overwrite=config.output.overwrite,
        )
    except Exception:
        _remove_path(staging_root)
        if backup_root.exists() and not final_root.exists():
            backup_root.replace(final_root)
        raise
    finally:
        _remove_path(staging_root)
        _remove_path(backup_root)


def _prepare_staging_directories(config: ValidationRunConfig) -> None:
    try:
        config.output.root_dir.mkdir(parents=True, exist_ok=False)
        config.output.figures_dir.mkdir(parents=True, exist_ok=False)
        config.output.tables_dir.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise ArtifactPersistenceError(
            f"Unable to create staging output directories: {error}"
        ) from error


def _commit_output_root(
    *,
    staging_root: Path,
    final_root: Path,
    backup_root: Path,
    overwrite: bool,
) -> None:
    try:
        if final_root.exists():
            if not overwrite:
                raise FileExistsError(
                    f"Validation output already exists and overwrite=False: {final_root}"
                )
            final_root.replace(backup_root)
        staging_root.replace(final_root)
        _remove_path(backup_root)
    except Exception as error:
        if not final_root.exists() and backup_root.exists():
            backup_root.replace(final_root)
        raise ArtifactPersistenceError(
            f"Unable to commit validation output to {final_root}: {error}"
        ) from error


def _write_comparison_tables(
    comparisons: Sequence[ModuleStatisticalComparisonResult],
    output_dir: Path,
) -> list[Path]:
    _ensure_unique_module_slugs(comparisons)
    paths: list[Path] = []
    for comparison in comparisons:
        module_dir = output_dir / _slugify(comparison.module_name)
        module_dir.mkdir(parents=True, exist_ok=True)
        tables = _comparison_tables(comparison)
        for name, frame in tables.items():
            if not isinstance(frame, pd.DataFrame):
                raise PipelineExecutionError(
                    f"Table {name!r} for module {comparison.module_name!r} is not a DataFrame."
                )
            path = module_dir / f"{name}.{_TABLE_FORMAT}"
            try:
                _atomic_write_dataframe(frame, path)
            except Exception as error:
                raise ArtifactPersistenceError(
                    f"Unable to write table {path}: {error}"
                ) from error
            paths.append(path)
    return sorted(paths, key=lambda path: path.as_posix())


def _comparison_tables(
    comparison: ModuleStatisticalComparisonResult,
) -> Mapping[str, pd.DataFrame]:
    return {
        "functional_summary": comparison.validation.summary,
        "functional_table_status": comparison.validation.table_status,
        "functional_clinical_signals": comparison.validation.clinical_signal,
        "functional_similarity": comparison.validation.distributional_similarity,
        "functional_issues": comparison.validation.issues,
        "statistical_summary": comparison.summary,
        "continuous_tests": comparison.continuous_tests,
        "categorical_tests": comparison.categorical_tests,
        "prevalence_tests": comparison.prevalence_tests,
        "distribution_tests": comparison.distribution_tests,
    }


def _write_figures(
    comparisons: Sequence[ModuleStatisticalComparisonResult],
    config: ValidationRunConfig,
) -> list[Path]:
    try:
        from validation.plots import (
            build_module_figures,
            build_validation_figures,
            save_module_figures,
            save_validation_figures,
        )

        paths: list[Path] = []
        plot_config = config.to_plot_config()
        for comparison in comparisons:
            figures = build_module_figures(comparison, config=plot_config)
            generated = save_module_figures(
                figures,
                config.output.figures_dir,
                file_format=config.presentation.figure_format,
                dpi=config.presentation.dpi,
                close=True,
            )
            paths.extend(generated.values())

        validation_figures = build_validation_figures(
            comparisons,
            annotate_values=config.presentation.annotate_values,
        )
        generated = save_validation_figures(
            validation_figures,
            config.output.figures_dir,
            file_format=config.presentation.figure_format,
            dpi=config.presentation.dpi,
            close=True,
        )
        paths.extend(generated.values())
        return sorted(paths, key=lambda path: path.as_posix())
    except Exception as error:
        raise ArtifactPersistenceError(f"Unable to generate validation figures: {error}") from error


def _write_resolved_config(config: ValidationRunConfig) -> Path:
    path = config.output.root_dir / _RESOLVED_CONFIG_FILENAME
    try:
        _atomic_write_text(path, config.canonical_json() + "\n")
    except OSError as error:
        raise ArtifactPersistenceError(
            f"Unable to write resolved configuration {path}: {error}"
        ) from error
    return path


def _write_manifest(
    *,
    config: ValidationRunConfig,
    original_config: ValidationRunConfig,
    comparisons: Sequence[ModuleStatisticalComparisonResult],
    module_decisions: Mapping[str, str],
    started_at: datetime,
    completed_at: datetime,
    duration_seconds: float,
    config_source: str | Path | None,
    report_path: Path,
    resolved_config_path: Path,
    table_paths: Sequence[Path],
    figure_paths: Sequence[Path],
) -> Path:
    decision_counts = {decision: 0 for decision in _DECISION_ORDER}
    module_results: list[dict[str, Any]] = []

    for comparison in comparisons:
        decision = module_decisions.get(comparison.module_name, "fail")
        decision_counts.setdefault(decision, 0)
        decision_counts[decision] += 1
        summary = _first_row(comparison.summary)
        module_results.append(
            {
                "module_name": comparison.module_name,
                "decision": decision,
                "validation_status": summary.get("validation_status"),
                "skipped": bool(summary.get("skipped", False)),
                "skip_reason": summary.get("skip_reason"),
                "significant_test_count": _safe_int(
                    summary.get("significant_test_count")
                ),
                "significant_after_fdr_count": _safe_int(
                    summary.get("significant_after_fdr_count")
                ),
            }
        )

    manifest = {
        "run_name": original_config.run_name,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": round(float(duration_seconds), 6),
        "schema_version": original_config.schema_version,
        "package_version": _distribution_version(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "configuration_fingerprint": original_config.configuration_fingerprint,
        "scientific_fingerprint": original_config.scientific_fingerprint,
        "config_source": str(Path(config_source).expanduser()) if config_source else None,
        "module_count": len(comparisons),
        "decision_counts": decision_counts,
        "module_results": module_results,
        "artefact_counts": {
            "tables": len(table_paths),
            "figures": len(figure_paths),
        },
        "artifacts": {
            "report": _relative_path(report_path, config.output.root_dir),
            "resolved_config": _relative_path(
                resolved_config_path,
                config.output.root_dir,
            ),
            "tables": [
                _relative_path(path, config.output.root_dir) for path in table_paths
            ],
            "figures": [
                _relative_path(path, config.output.root_dir) for path in figure_paths
            ],
        },
    }

    path = config.output.root_dir / _MANIFEST_FILENAME
    try:
        _atomic_write_text(
            path,
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
    except OSError as error:
        raise ArtifactPersistenceError(f"Unable to write run manifest {path}: {error}") from error
    return path


def _rebase_artifacts(
    *,
    config: ValidationRunConfig,
    comparisons: Sequence[ModuleStatisticalComparisonResult],
    report_path: Path,
    manifest_path: Path,
    resolved_config_path: Path,
    table_paths: Sequence[Path],
    figure_paths: Sequence[Path],
) -> ValidationRunArtifacts:
    staging_root = report_path.parent

    def rebase(path: Path) -> Path:
        return config.output.root_dir / path.relative_to(staging_root)

    return ValidationRunArtifacts(
        report_path=rebase(report_path),
        manifest_path=rebase(manifest_path),
        resolved_config_path=rebase(resolved_config_path),
        table_paths=tuple(sorted((rebase(path) for path in table_paths), key=str)),
        figure_paths=tuple(sorted((rebase(path) for path in figure_paths), key=str)),
        comparisons=tuple(comparisons),
    )


def _print_success_summary(artifacts: ValidationRunArtifacts, stream: TextIO) -> None:
    decisions = _decisions_from_report_manifest(artifacts.manifest_path)
    counts = {decision: decisions.count(decision) for decision in _DECISION_ORDER}
    print(
        "Validation completed successfully: "
        + ", ".join(f"{name}={count}" for name, count in counts.items()),
        file=stream,
    )
    print(f"Report: {artifacts.report_path}", file=stream)
    print(f"Manifest: {artifacts.manifest_path}", file=stream)


def _print_experiment_summary(
    execution: OrchestrationExecution,
    stream: TextIO,
) -> None:
    result = execution.result
    print(
        "Experiment completed: "
        f"status={result.status.value}, "
        f"run_id={result.run_id}",
        file=stream,
    )
    print(f"Workspace: {result.workspace}", file=stream)
    if execution.manifest is not None:
        print(f"Manifest: {execution.manifest.path}", file=stream)


def _decisions_from_report_manifest(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [str(item["decision"]) for item in payload.get("module_results", [])]
    except (OSError, ValueError, KeyError, TypeError):
        return []


@contextmanager
def _configured_logging(level: str, stream: TextIO) -> Iterator[None]:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    previous_level = _LOGGER.level
    previous_propagate = _LOGGER.propagate
    _LOGGER.setLevel(getattr(logging, level))
    _LOGGER.propagate = False
    _LOGGER.addHandler(handler)
    try:
        yield
    finally:
        _LOGGER.removeHandler(handler)
        handler.close()
        _LOGGER.setLevel(previous_level)
        _LOGGER.propagate = previous_propagate


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        _remove_path(temporary)


def _atomic_write_dataframe(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    try:
        frame.to_csv(temporary, index=False)
        temporary.replace(path)
    finally:
        _remove_path(temporary)


def _ensure_unique_module_slugs(
    comparisons: Sequence[ModuleStatisticalComparisonResult],
) -> None:
    seen: dict[str, str] = {}
    for comparison in comparisons:
        slug = _slugify(comparison.module_name)
        existing = seen.get(slug)
        if existing is not None:
            raise PipelineExecutionError(
                "Module names produce the same output slug: "
                f"{existing!r} and {comparison.module_name!r} -> {slug!r}."
            )
        seen[slug] = comparison.module_name


def _distribution_version() -> str:
    try:
        return package_version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "development"


def _normalise_timestamp(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("generated_at must be a datetime or None.")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _first_row(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    return frame.iloc[0].to_dict()


def _safe_int(value: object) -> int:
    if value is None or pd.isna(value):
        return 0
    return int(value)


def _remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _slugify(value: str) -> str:
    slug = "".join(
        character.lower() if character.isalnum() else "-" for character in value
    )
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or "module"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())