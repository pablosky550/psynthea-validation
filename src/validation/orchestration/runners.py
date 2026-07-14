"""Simulator execution adapters for Phase 2B experiment orchestration.

This module owns the subprocess boundary between the validation framework and
Synthea / psynthea.  It turns immutable orchestration configuration into a
fully auditable :class:`~validation.orchestration.models.SimulatorRunResult`
without leaking process-management concerns into the orchestrator.

Design guarantees
-----------------
* Commands are executed directly (``shell=False``); no shell interpolation.
* Both simulators receive the same immutable ``CohortConfig``.
* Dynamic arguments are rendered deterministically from explicit templates.
* stdout and stderr are persisted separately inside the experiment workspace.
* Timeouts terminate the complete process group on a best-effort basis.
* Expected outputs are verified before a run can be reported as successful.
* Every persisted log and simulator output is represented by an immutable,
  hashed ``ArtifactReference``.
* Process failures are returned as failed domain results; invalid runner
  configuration and workspace-integrity failures raise explicit exceptions.

The runners do not load cohorts, normalize data, calculate statistics, consult
scientific knowledge or generate reports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
import os
from pathlib import Path, PurePath
import signal
import subprocess
from time import monotonic
from types import MappingProxyType
from typing import Any, Final

from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
    CohortConfig,
    ExecutionStatus,
    ExperimentConfig,
    SimulatorConfig,
    SimulatorKind,
    SimulatorRunResult,
)
from validation.orchestration.workspace import ExperimentWorkspace

__all__ = [
    "CommandPlan",
    "PsyntheaRunner",
    "RunnerConfigurationError",
    "RunnerError",
    "RunnerIntegrityError",
    "SimulatorRunner",
    "SyntheaRunner",
    "runner_for",
]


# =============================================================================
# Constants and errors
# =============================================================================


_ARGUMENT_TEMPLATE_KEY: Final = "command_arguments"
_MODULE_SEPARATOR_KEY: Final = "module_separator"
_INHERIT_ENVIRONMENT_KEY: Final = "inherit_environment"
_DISCOVER_OUTPUTS_KEY: Final = "discover_outputs"

_ALLOWED_ARGUMENT_KEYS: Final = frozenset(
    {
        _ARGUMENT_TEMPLATE_KEY,
        _MODULE_SEPARATOR_KEY,
        _INHERIT_ENVIRONMENT_KEY,
        _DISCOVER_OUTPUTS_KEY,
    }
)

_ALLOWED_PLACEHOLDERS: Final = frozenset(
    {
        "population",
        "seed",
        "modules",
        "module",
        "output_dir",
        "reference_date",
        "min_age",
        "max_age",
    }
)

_DEFAULT_ARGUMENT_TEMPLATES: Final[Mapping[SimulatorKind, tuple[str, ...]]] = MappingProxyType(
    {
        SimulatorKind.SYNTHEA: (
            "-p",
            "{population}",
            "-s",
            "{seed}",
            "-m",
            "{modules}",
        ),
        SimulatorKind.PSYNTHEA: (
            "generate",
            "-p",
            "{population}",
            "-m",
            "{modules}",
            "-o",
            "{output_dir}",
            "--seed",
            "{seed}",
        ),
    }
)


class RunnerError(RuntimeError):
    """Base class for simulator-runner failures outside normal process results."""


class RunnerConfigurationError(RunnerError):
    """Raised when a simulator execution contract is invalid or ambiguous."""


class RunnerIntegrityError(RunnerError):
    """Raised when produced artefacts violate the expected workspace contract."""


# =============================================================================
# Command planning
# =============================================================================


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise RunnerConfigurationError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )
    normalized = value.strip()
    if not normalized:
        raise RunnerConfigurationError(f"{field_name} must not be empty.")
    if "\x00" in normalized:
        raise RunnerConfigurationError(f"{field_name} must not contain NUL bytes.")
    return normalized


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise RunnerConfigurationError(f"{field_name} must be a boolean.")
    return value


def _normalize_template(value: Any) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RunnerConfigurationError(
            f"{_ARGUMENT_TEMPLATE_KEY} must be a sequence of argument strings."
        )
    normalized = tuple(
        _require_text(item, f"{_ARGUMENT_TEMPLATE_KEY}[{index}]")
        for index, item in enumerate(value)
    )
    if not normalized:
        raise RunnerConfigurationError(f"{_ARGUMENT_TEMPLATE_KEY} must not be empty.")
    return normalized


def _validate_argument_options(arguments: Mapping[str, Any]) -> None:
    unknown = sorted(set(arguments) - _ALLOWED_ARGUMENT_KEYS)
    if unknown:
        raise RunnerConfigurationError(
            "Unsupported simulator argument option(s): " + ", ".join(unknown) + "."
        )


def _path_text(path: Path) -> str:
    """Return a native absolute path suitable for the local subprocess."""

    return str(path.resolve(strict=False))


def _cohort_context(
    cohort: CohortConfig,
    *,
    output_directory: Path,
    module_separator: str,
) -> Mapping[str, str | None]:
    modules = module_separator.join(cohort.modules)
    return MappingProxyType(
        {
            "population": str(cohort.population),
            "seed": str(cohort.seed),
            "modules": modules,
            "module": modules,
            "output_dir": _path_text(output_directory),
            "reference_date": (
                cohort.reference_date.isoformat() if cohort.reference_date is not None else None
            ),
            "min_age": str(cohort.min_age) if cohort.min_age is not None else None,
            "max_age": str(cohort.max_age) if cohort.max_age is not None else None,
        }
    )


def _placeholder_names(template: str) -> tuple[str, ...]:
    """Extract simple ``{name}`` placeholders without accepting format expressions."""

    names: list[str] = []
    index = 0
    while index < len(template):
        character = template[index]
        if character == "{":
            if index + 1 < len(template) and template[index + 1] == "{":
                index += 2
                continue
            end = template.find("}", index + 1)
            if end < 0:
                raise RunnerConfigurationError(
                    f"Unclosed placeholder in command argument {template!r}."
                )
            name = template[index + 1 : end]
            if not name or any(token in name for token in ("!", ":", ".", "[", "]")):
                raise RunnerConfigurationError(
                    f"Only simple named placeholders are allowed in {template!r}."
                )
            names.append(name)
            index = end + 1
            continue
        if character == "}" and not (
            index + 1 < len(template) and template[index + 1] == "}"
        ):
            raise RunnerConfigurationError(
                f"Unmatched closing brace in command argument {template!r}."
            )
        index += 1
    return tuple(names)


def _render_template(
    template: Sequence[str],
    context: Mapping[str, str | None],
) -> tuple[str, ...]:
    rendered: list[str] = []
    for index, argument in enumerate(template):
        names = _placeholder_names(argument)
        unknown = sorted(set(names) - _ALLOWED_PLACEHOLDERS)
        if unknown:
            raise RunnerConfigurationError(
                f"command argument {index} contains unsupported placeholder(s): "
                + ", ".join(unknown)
                + "."
            )
        missing = sorted(name for name in names if context[name] is None)
        if missing:
            raise RunnerConfigurationError(
                f"command argument {index} requires unset cohort field(s): "
                + ", ".join(missing)
                + "."
            )

        value = argument
        for name in names:
            replacement = context[name]
            assert replacement is not None
            value = value.replace("{" + name + "}", replacement)
        value = value.replace("{{", "{").replace("}}", "}")
        rendered.append(_require_text(value, f"rendered command argument {index}"))
    return tuple(rendered)


@dataclass(frozen=True, slots=True)
class CommandPlan:
    """Fully resolved subprocess contract for one simulator execution."""

    simulator: SimulatorKind
    command: tuple[str, ...]
    working_directory: Path
    output_directory: Path
    environment: Mapping[str, str]
    timeout_seconds: float
    expected_output_files: tuple[Path, ...]
    discover_outputs: bool

    def __post_init__(self) -> None:
        if not isinstance(self.simulator, SimulatorKind):
            raise TypeError("simulator must be a SimulatorKind member.")
        if not self.command or any(not isinstance(item, str) or not item for item in self.command):
            raise ValueError("command must contain at least one non-empty argument.")
        if not self.working_directory.is_absolute():
            raise ValueError("working_directory must be absolute.")
        if not self.output_directory.is_absolute():
            raise ValueError("output_directory must be absolute.")
        if isinstance(self.timeout_seconds, bool) or not isinstance(
            self.timeout_seconds, (int, float)
        ):
            raise TypeError("timeout_seconds must be a number.")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        if not isinstance(self.discover_outputs, bool):
            raise TypeError("discover_outputs must be a boolean.")

        environment: dict[str, str] = {}
        for key, value in self.environment.items():
            normalized_key = _require_text(key, "environment key")
            if not isinstance(value, str):
                raise TypeError(
                    f"environment[{normalized_key!r}] must be a string, "
                    f"got {type(value).__name__}."
                )
            if "\x00" in value:
                raise ValueError(
                    f"environment[{normalized_key!r}] must not contain NUL bytes."
                )
            environment[normalized_key] = value
        object.__setattr__(self, "environment", MappingProxyType(environment))

        normalized_expected: list[Path] = []
        for path in self.expected_output_files:
            candidate = Path(path)
            if not candidate.is_absolute():
                raise ValueError("expected_output_files entries must be absolute.")
            try:
                candidate.resolve(strict=False).relative_to(
                    self.output_directory.resolve(strict=False)
                )
            except ValueError as exc:
                raise ValueError(
                    "expected_output_files entries must remain below output_directory."
                ) from exc
            normalized_expected.append(candidate.resolve(strict=False))
        object.__setattr__(self, "expected_output_files", tuple(normalized_expected))


# =============================================================================
# Runner base class
# =============================================================================


class SimulatorRunner(ABC):
    """Base adapter for one simulator implementation.

    Subclasses define only the default command-line shape.  Process execution,
    logging, timeout handling, output verification and result construction are
    intentionally shared so both engines receive identical operational treatment.
    """

    kind: SimulatorKind

    def __init__(self, config: SimulatorConfig) -> None:
        if not isinstance(config, SimulatorConfig):
            raise TypeError("config must be a SimulatorConfig.")
        if config.kind is not self.kind:
            raise RunnerConfigurationError(
                f"{type(self).__name__} requires a {self.kind.value} configuration, "
                f"got {config.kind.value}."
            )
        _validate_argument_options(config.arguments)
        self._config = config

    @property
    def config(self) -> SimulatorConfig:
        return self._config

    @abstractmethod
    def default_argument_template(self) -> tuple[str, ...]:
        """Return the simulator-specific default argument template."""

    def build_plan(
        self,
        *,
        experiment: ExperimentConfig,
        workspace: ExperimentWorkspace,
    ) -> CommandPlan:
        """Resolve configuration into a deterministic, executable command plan."""

        if not isinstance(experiment, ExperimentConfig):
            raise TypeError("experiment must be an ExperimentConfig.")
        if not isinstance(workspace, ExperimentWorkspace):
            raise TypeError("workspace must be an ExperimentWorkspace.")
        if workspace.config != experiment:
            raise RunnerIntegrityError(
                "Workspace configuration does not match the requested experiment."
            )
        if experiment.simulator(self.kind) != self.config:
            raise RunnerIntegrityError(
                f"Experiment {self.kind.value} configuration does not match this runner."
            )

        working_directory = self.config.working_directory.resolve(strict=False)
        if not working_directory.is_dir():
            raise RunnerConfigurationError(
                f"working_directory does not exist or is not a directory: {working_directory}"
            )

        output_directory = (
            workspace.simulator_raw_directory(self.kind) / self.config.output_subdirectory
        ).resolve(strict=False)
        if output_directory.exists():
            raise RunnerIntegrityError(
                f"Simulator output directory already exists for {self.kind.value}: "
                f"{output_directory}"
            )

        options = self.config.arguments
        module_separator = _require_text(
            options.get(_MODULE_SEPARATOR_KEY, ","),
            _MODULE_SEPARATOR_KEY,
        )
        if any(character.isspace() for character in module_separator):
            raise RunnerConfigurationError("module_separator must not contain whitespace.")

        raw_template = options.get(_ARGUMENT_TEMPLATE_KEY)
        template = (
            self.default_argument_template()
            if raw_template is None
            else _normalize_template(raw_template)
        )
        context = _cohort_context(
            experiment.cohort,
            output_directory=output_directory,
            module_separator=module_separator,
        )
        dynamic_arguments = _render_template(template, context)

        inherit_environment = _require_bool(
            options.get(_INHERIT_ENVIRONMENT_KEY, True),
            _INHERIT_ENVIRONMENT_KEY,
        )
        environment = dict(os.environ) if inherit_environment else {}
        environment.update(self.config.environment)

        discover_outputs = _require_bool(
            options.get(_DISCOVER_OUTPUTS_KEY, not self.config.expected_output_files),
            _DISCOVER_OUTPUTS_KEY,
        )
        expected = tuple(output_directory / relative for relative in self.config.expected_output_files)

        return CommandPlan(
            simulator=self.kind,
            command=tuple(self.config.command) + dynamic_arguments,
            working_directory=working_directory,
            output_directory=output_directory,
            environment=environment,
            timeout_seconds=self.config.timeout_seconds,
            expected_output_files=expected,
            discover_outputs=discover_outputs,
        )

    def run(
        self,
        *,
        experiment: ExperimentConfig,
        workspace: ExperimentWorkspace,
        run_id: str,
    ) -> SimulatorRunResult:
        """Execute the simulator and return a complete immutable run result.

        Normal subprocess failures, missing executables and timeouts are encoded
        as ``ExecutionStatus.FAILED`` results.  Invalid configuration, workspace
        mismatches and unsafe produced paths raise explicit runner exceptions.
        """

        plan = self.build_plan(experiment=experiment, workspace=workspace)
        try:
            plan.output_directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise RunnerIntegrityError(
                f"Simulator output directory already exists for {self.kind.value}: "
                f"{plan.output_directory}"
            ) from exc
        normalized_run_id = _require_text(run_id, "run_id")
        result_id = f"{experiment.id}:{normalized_run_id}:{self.kind.value}"

        log_directory = workspace.simulator_log_directory(self.kind)
        stdout_path = log_directory / "stdout.log"
        stderr_path = log_directory / "stderr.log"
        if stdout_path.exists() or stderr_path.exists():
            raise RunnerIntegrityError(
                f"Simulator log files already exist for {self.kind.value}; refusing to overwrite."
            )

        started_at = datetime.now(UTC)
        started_clock = monotonic()
        process: subprocess.Popen[bytes] | None = None
        return_code: int | None = None
        timed_out = False
        error_message: str | None = None

        popen_kwargs: dict[str, Any] = {
            "cwd": plan.working_directory,
            "env": dict(plan.environment),
            "stdin": subprocess.DEVNULL,
            "shell": False,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        elif os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        try:
            with _exclusive_log_streams(stdout_path, stderr_path) as (
                stdout_stream,
                stderr_stream,
            ):
                try:
                    process = subprocess.Popen(
                        plan.command,
                        stdout=stdout_stream,
                        stderr=stderr_stream,
                        **popen_kwargs,
                    )
                    return_code = process.wait(timeout=plan.timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    error_message = (
                        f"{self.kind.value} exceeded timeout of "
                        f"{plan.timeout_seconds:g} seconds."
                    )
                    if process is not None:
                        _terminate_process_tree(process)
                        return_code = process.returncode
                finally:
                    stdout_stream.flush()
                    stderr_stream.flush()
                    os.fsync(stdout_stream.fileno())
                    os.fsync(stderr_stream.fileno())
        except FileNotFoundError as exc:
            error_message = f"Simulator executable not found: {plan.command[0]!r}."
            _append_runner_error(stderr_path, error_message, exc)
        except PermissionError as exc:
            error_message = f"Simulator executable is not permitted: {plan.command[0]!r}."
            _append_runner_error(stderr_path, error_message, exc)
        except OSError as exc:
            error_message = f"Unable to execute {self.kind.value}: {exc}."
            _append_runner_error(stderr_path, error_message, exc)

        finished_at = datetime.now(UTC)
        duration_seconds = max(0.0, monotonic() - started_clock)

        log_artifacts = self._log_artifacts(workspace, stdout_path, stderr_path)
        output_artifacts, verification_error = self._collect_output_artifacts(
            workspace=workspace,
            plan=plan,
        )

        if error_message is None and return_code != 0:
            error_message = (
                f"{self.kind.value} exited with return code {return_code}."
                if return_code is not None
                else f"{self.kind.value} did not produce a return code."
            )
        if error_message is None and verification_error is not None:
            error_message = verification_error

        status = ExecutionStatus.SUCCEEDED if error_message is None else ExecutionStatus.FAILED
        subprocess_return_code = return_code
        if status is ExecutionStatus.SUCCEEDED:
            return_code = 0
        elif verification_error is not None and return_code == 0:
            # The process itself succeeded, but the runner contract failed.  The
            # domain model intentionally reserves return_code=0 for SUCCEEDED.
            return_code = None

        return SimulatorRunResult(
            id=result_id,
            simulator=self.kind,
            status=status,
            command=plan.command,
            working_directory=plan.working_directory,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            return_code=return_code,
            artifacts=log_artifacts + output_artifacts,
            error_message=error_message,
            metadata={
                "output_directory": workspace.relative(plan.output_directory).as_posix(),
                "timeout_seconds": plan.timeout_seconds,
                "timed_out": timed_out,
                "subprocess_return_code": subprocess_return_code,
                "expected_output_count": len(plan.expected_output_files),
                "discovered_output_count": len(output_artifacts),
            },
        )

    def _log_artifacts(
        self,
        workspace: ExperimentWorkspace,
        stdout_path: Path,
        stderr_path: Path,
    ) -> tuple[ArtifactReference, ArtifactReference]:
        return (
            workspace.artifact_reference(
                artifact_id=f"{self.kind.value}.stdout",
                kind=ArtifactKind.LOG,
                path=stdout_path,
                media_type="text/plain; charset=utf-8",
                producer=f"{self.kind.value}_runner",
                metadata={"stream": "stdout"},
            ),
            workspace.artifact_reference(
                artifact_id=f"{self.kind.value}.stderr",
                kind=ArtifactKind.LOG,
                path=stderr_path,
                media_type="text/plain; charset=utf-8",
                producer=f"{self.kind.value}_runner",
                metadata={"stream": "stderr"},
            ),
        )

    def _collect_output_artifacts(
        self,
        *,
        workspace: ExperimentWorkspace,
        plan: CommandPlan,
    ) -> tuple[tuple[ArtifactReference, ...], str | None]:
        missing: list[str] = []
        expected_files: list[Path] = []
        for expected in plan.expected_output_files:
            safe_expected = _require_output_file(expected, plan.output_directory)
            if not safe_expected.is_file():
                missing.append(safe_expected.relative_to(plan.output_directory).as_posix())
            else:
                expected_files.append(safe_expected)

        files: set[Path] = set(expected_files)
        if plan.discover_outputs:
            for candidate in sorted(plan.output_directory.rglob("*")):
                if candidate.is_symlink():
                    raise RunnerIntegrityError(
                        f"Simulator output must not contain symlinks: {candidate}"
                    )
                if candidate.is_file():
                    files.add(_require_output_file(candidate, plan.output_directory))

        artifacts: list[ArtifactReference] = []
        for path in sorted(files, key=lambda item: item.as_posix()):
            relative_output = path.relative_to(plan.output_directory).as_posix()
            artifact_token = sha256(relative_output.encode("utf-8")).hexdigest()[:16]
            artifacts.append(
                workspace.artifact_reference(
                    artifact_id=f"{self.kind.value}.output.{artifact_token}",
                    kind=ArtifactKind.SIMULATOR_OUTPUT,
                    path=path,
                    media_type=_guess_media_type(path),
                    producer=f"{self.kind.value}_runner",
                    metadata={"output_path": relative_output},
                )
            )

        if missing:
            return tuple(artifacts), (
                f"{self.kind.value} completed without required output file(s): "
                + ", ".join(sorted(missing))
                + "."
            )
        if not artifacts:
            return tuple(), f"{self.kind.value} produced no simulator output files."
        return tuple(artifacts), None


# =============================================================================
# Concrete adapters and registry
# =============================================================================


class SyntheaRunner(SimulatorRunner):
    """Subprocess adapter for the Java Synthea command-line entry point."""

    kind = SimulatorKind.SYNTHEA

    def default_argument_template(self) -> tuple[str, ...]:
        return _DEFAULT_ARGUMENT_TEMPLATES[self.kind]


class PsyntheaRunner(SimulatorRunner):
    """Subprocess adapter for the Python-native psynthea CLI."""

    kind = SimulatorKind.PSYNTHEA

    def default_argument_template(self) -> tuple[str, ...]:
        return _DEFAULT_ARGUMENT_TEMPLATES[self.kind]


_RUNNER_TYPES: Final[Mapping[SimulatorKind, type[SimulatorRunner]]] = MappingProxyType(
    {
        SimulatorKind.SYNTHEA: SyntheaRunner,
        SimulatorKind.PSYNTHEA: PsyntheaRunner,
    }
)


def runner_for(config: SimulatorConfig) -> SimulatorRunner:
    """Return the registered runner for ``config.kind``."""

    if not isinstance(config, SimulatorConfig):
        raise TypeError("config must be a SimulatorConfig.")
    try:
        runner_type = _RUNNER_TYPES[config.kind]
    except KeyError as exc:  # Defensive for future enum expansion.
        raise RunnerConfigurationError(
            f"No simulator runner is registered for {config.kind.value!r}."
        ) from exc
    return runner_type(config)


# =============================================================================
# Process and artefact helpers
# =============================================================================


@contextmanager
def _exclusive_log_streams(stdout_path: Path, stderr_path: Path):
    """Create both log files exclusively or leave neither behind on failure."""

    stdout_stream = None
    stderr_stream = None
    try:
        stdout_stream = stdout_path.open("xb")
        try:
            stderr_stream = stderr_path.open("xb")
        except Exception:
            stdout_stream.close()
            stdout_path.unlink(missing_ok=True)
            raise
        yield stdout_stream, stderr_stream
    finally:
        if stderr_stream is not None and not stderr_stream.closed:
            stderr_stream.close()
        if stdout_stream is not None and not stdout_stream.closed:
            stdout_stream.close()


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate a timed-out process group, escalating to a hard kill."""

    if process.poll() is not None:
        return

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=5.0)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=5.0)
    except (OSError, subprocess.TimeoutExpired):
        process.kill()
        process.wait()


def _append_runner_error(path: Path, message: str, exc: BaseException) -> None:
    """Ensure stderr exists and contains a deterministic launch failure record."""

    payload = f"{message}\n{type(exc).__name__}: {exc}\n".encode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _require_output_file(candidate: Path, output_root: Path) -> Path:
    """Validate that one simulator output is a regular file below output_root."""

    if candidate.is_symlink():
        raise RunnerIntegrityError(f"Simulator output must not be a symlink: {candidate}")
    resolved_root = output_root.resolve(strict=True)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise RunnerIntegrityError(
            f"Simulator output escapes its managed directory: {candidate}"
        ) from exc
    return resolved_candidate


def _guess_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".csv": "text/csv",
        ".json": "application/json",
        ".jsonl": "application/x-ndjson",
        ".ndjson": "application/x-ndjson",
        ".parquet": "application/vnd.apache.parquet",
        ".txt": "text/plain; charset=utf-8",
        ".log": "text/plain; charset=utf-8",
        ".xml": "application/xml",
        ".zip": "application/zip",
    }.get(suffix, "application/octet-stream")