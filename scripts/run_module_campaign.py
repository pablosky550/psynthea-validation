#!/usr/bin/env python3
"""Execute one isolated scientific experiment per configured Synthea module.

The campaign reuses a validated multi-module experiment configuration only as a
configuration template.  Each subprocess overrides the cohort to exactly one
module, assigns a stable experiment identifier and persists independent logs.
Campaign state is written atomically after every attempt so interrupted runs can
be resumed without repeating completed modules.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

_SCHEMA_VERSION = "1.0"
_ENCODING = "utf-8"
_SAFE_IDENTIFIER = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class ModuleAttempt:
    """Persisted result of one module-level experiment attempt."""

    module: str
    attempt: int
    status: str
    return_code: int | None
    started_at: str
    completed_at: str
    duration_seconds: float
    experiment_id: str
    log_path: str
    command: tuple[str, ...]
    error: str | None = None


def _parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one isolated Synthea/Psynthea scientific experiment for every "
            "module listed in an experiment configuration."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Validated experiment JSON used as the campaign template.",
    )
    parser.add_argument(
        "--population",
        type=int,
        required=True,
        help="Population generated independently for each module.",
    )
    parser.add_argument(
        "--campaign-dir",
        type=Path,
        required=True,
        help="Directory for campaign state and per-module logs.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to invoke validation.cli.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Additional attempts after the first failed attempt.",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=2.0,
        help="Delay between attempts for one failed module.",
    )
    parser.add_argument(
        "--module",
        dest="selected_modules",
        action="append",
        help="Run only this configured module; repeat to select several.",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Abort the campaign after the first module that exhausts retries.",
    )
    parser.add_argument(
        "--rerun-succeeded",
        action="store_true",
        help="Repeat modules already marked as succeeded in campaign state.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing subprocesses.",
    )
    arguments = parser.parse_args(argv)

    if arguments.population <= 0:
        parser.error("--population must be greater than zero.")
    if arguments.retries < 0:
        parser.error("--retries must be zero or greater.")
    if arguments.retry_delay_seconds < 0:
        parser.error("--retry-delay-seconds must be zero or greater.")

    return arguments


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding=_ENCODING))
    except OSError as error:
        raise ValueError(f"Cannot read configuration: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON configuration {path}: {error}") from error

    if not isinstance(payload, dict):
        raise ValueError(f"Configuration root must be an object: {path}")
    return payload


def _configured_modules(payload: Mapping[str, Any]) -> tuple[str, ...]:
    cohort = payload.get("cohort")
    if not isinstance(cohort, Mapping):
        raise ValueError("Configuration must contain a cohort object.")

    modules = cohort.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValueError("cohort.modules must be a non-empty list.")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(modules):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"cohort.modules[{index}] must be a non-empty string.")
        module = value.strip()
        if module in seen:
            raise ValueError(f"Duplicate configured module: {module}")
        seen.add(module)
        normalized.append(module)

    return tuple(normalized)


def _select_modules(
    configured: Sequence[str],
    selected: Sequence[str] | None,
) -> tuple[str, ...]:
    if not selected:
        return tuple(configured)

    selected_set = {value.strip() for value in selected if value.strip()}
    unknown = sorted(selected_set.difference(configured))
    if unknown:
        raise ValueError(
            "Requested module(s) are not configured: " + ", ".join(unknown)
        )
    return tuple(module for module in configured if module in selected_set)


def _safe_identifier(value: str) -> str:
    normalized = _SAFE_IDENTIFIER.sub("-", value.strip()).strip("-._")
    if not normalized:
        raise ValueError(f"Cannot derive a safe identifier from {value!r}.")
    return normalized.lower()


def _experiment_id(base_id: str, module: str, population: int) -> str:
    return (
        f"{_safe_identifier(base_id)}-module-"
        f"{_safe_identifier(module)}-p{population}"
    )


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": _SCHEMA_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "attempts": [],
        }
    payload = _load_json(path)
    attempts = payload.get("attempts")
    if not isinstance(attempts, list):
        raise ValueError(f"Invalid campaign state attempts: {path}")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding=_ENCODING) as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _latest_status_by_module(state: Mapping[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for attempt in state.get("attempts", []):
        if isinstance(attempt, Mapping):
            module = attempt.get("module")
            status = attempt.get("status")
            if isinstance(module, str) and isinstance(status, str):
                statuses[module] = status
    return statuses


def _attempt_count(state: Mapping[str, Any], module: str) -> int:
    return sum(
        1
        for item in state.get("attempts", [])
        if isinstance(item, Mapping) and item.get("module") == module
    )


def _build_command(
    *,
    python: str,
    config: Path,
    module: str,
    population: int,
    experiment_id: str,
) -> tuple[str, ...]:
    return (
        python,
        "-m",
        "validation.cli",
        "--config",
        str(config),
        "--experiment",
        "--module",
        module,
        "--module-name",
        module,
        "--population",
        str(population),
        "--experiment-id",
        experiment_id,
    )


def _execute_attempt(
    *,
    module: str,
    attempt: int,
    command: tuple[str, ...],
    experiment_id: str,
    log_path: Path,
    dry_run: bool,
) -> ModuleAttempt:
    started = datetime.now(UTC)
    monotonic_start = time.monotonic()
    error_message: str | None = None
    return_code: int | None = None

    log_path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        status = "dry_run"
    else:
        try:
            with log_path.open("w", encoding=_ENCODING) as stream:
                stream.write("COMMAND: " + " ".join(command) + "\n\n")
                stream.flush()
                completed = subprocess.run(
                    command,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
            return_code = completed.returncode
            status = "succeeded" if return_code == 0 else "failed"
        except OSError as error:
            status = "failed"
            error_message = str(error)

    completed_at = datetime.now(UTC)
    return ModuleAttempt(
        module=module,
        attempt=attempt,
        status=status,
        return_code=return_code,
        started_at=started.isoformat(),
        completed_at=completed_at.isoformat(),
        duration_seconds=round(time.monotonic() - monotonic_start, 6),
        experiment_id=experiment_id,
        log_path=str(log_path),
        command=command,
        error=error_message,
    )


def _persist_attempt(
    *,
    state_path: Path,
    state: dict[str, Any],
    attempt: ModuleAttempt,
    config: Path,
    population: int,
    module_count: int,
) -> None:
    state["updated_at"] = datetime.now(UTC).isoformat()
    state["config"] = str(config)
    state["population"] = population
    state["module_count"] = module_count
    state["attempts"].append(asdict(attempt))
    _write_json_atomic(state_path, state)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)

    try:
        config_path = arguments.config.expanduser().resolve(strict=True)
        config = _load_json(config_path)
        base_id = config.get("id")
        if not isinstance(base_id, str) or not base_id.strip():
            raise ValueError("Configuration id must be a non-empty string.")

        configured = _configured_modules(config)
        modules = _select_modules(configured, arguments.selected_modules)
        campaign_dir = arguments.campaign_dir.expanduser().resolve()
        state_path = campaign_dir / "campaign_state.json"
        state = _load_state(state_path)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    latest_status = _latest_status_by_module(state)
    pending = tuple(
        module
        for module in modules
        if arguments.rerun_succeeded or latest_status.get(module) != "succeeded"
    )

    print(f"Configured modules: {len(configured)}")
    print(f"Selected modules: {len(modules)}")
    print(f"Already succeeded: {len(modules) - len(pending)}")
    print(f"Pending: {len(pending)}")
    print(f"Campaign state: {state_path}")

    failed_modules: list[str] = []
    for position, module in enumerate(pending, start=1):
        experiment_id = _experiment_id(base_id, module, arguments.population)
        succeeded = False

        for retry_index in range(arguments.retries + 1):
            attempt_number = _attempt_count(state, module) + 1
            log_path = (
                campaign_dir
                / "logs"
                / _safe_identifier(module)
                / f"attempt-{attempt_number:02d}.log"
            )
            command = _build_command(
                python=arguments.python,
                config=config_path,
                module=module,
                population=arguments.population,
                experiment_id=experiment_id,
            )

            print(
                f"[{position}/{len(pending)}] {module} "
                f"(attempt {attempt_number}) ... ",
                end="",
                flush=True,
            )
            result = _execute_attempt(
                module=module,
                attempt=attempt_number,
                command=command,
                experiment_id=experiment_id,
                log_path=log_path,
                dry_run=arguments.dry_run,
            )
            _persist_attempt(
                state_path=state_path,
                state=state,
                attempt=result,
                config=config_path,
                population=arguments.population,
                module_count=len(modules),
            )
            print(
                f"{result.status.upper()} "
                f"({result.duration_seconds:.2f}s, log={log_path})"
            )

            if result.status in {"succeeded", "dry_run"}:
                succeeded = True
                break
            if retry_index < arguments.retries:
                time.sleep(arguments.retry_delay_seconds)

        if not succeeded:
            failed_modules.append(module)
            if arguments.stop_on_failure:
                break

    succeeded_total = sum(
        1
        for module, status in _latest_status_by_module(state).items()
        if module in modules and status == "succeeded"
    )
    print("\nCampaign summary")
    print(f"Succeeded: {succeeded_total}/{len(modules)}")
    print(f"Failed in this invocation: {len(failed_modules)}")
    if failed_modules:
        print("Failed modules: " + ", ".join(failed_modules))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())