#!/usr/bin/env python3
"""Run every root Synthea module independently through Psynthea."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from psynthea.compat.synthea_json import load_module_with_submodules


CSV_OUTPUTS = (
    "patients.csv",
    "encounters.csv",
    "conditions.csv",
    "medications.csv",
    "procedures.csv",
    "observations.csv",
    "devices.csv",
    "imaging_studies.csv",
    "supplies.csv",
)

CLINICAL_ACTIVITY_OUTPUTS = (
    "conditions.csv",
    "medications.csv",
    "procedures.csv",
    "observations.csv",
    "devices.csv",
    "imaging_studies.csv",
    "supplies.csv",
)

ACTIVITY_CLASSIFICATIONS = (
    "CLINICAL_ACTIVITY",
    "ENCOUNTERS_ONLY",
    "NO_ACTIVITY",
    "NOT_APPLICABLE",
)


@dataclass(frozen=True, slots=True)
class ModuleSmokeResult:
    """Runtime smoke-test result for one root Synthea module."""

    module: str
    module_path: str
    status: str
    parse_ok: bool
    execution_ok: bool
    export_ok: bool
    return_code: int | None
    duration_seconds: float
    row_counts: dict[str, int]
    non_patient_rows: int
    stdout_log: str | None = None
    stderr_log: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    encounter_rows: int = 0
    clinical_rows: int = 0
    activity_classification: str = "NOT_APPLICABLE"


def _parse_arguments(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute each root Synthea module independently using "
            "Psynthea and record parser, runtime and CSV-export results."
        ),
    )
    parser.add_argument(
        "--modules-dir",
        type=Path,
        required=True,
        help="Directory containing root Synthea module JSON files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Root output directory for evidence and per-module outputs.",
    )
    parser.add_argument(
        "--population",
        type=int,
        default=3,
        help="Patients generated per module.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )
    parser.add_argument(
        "--end-date",
        default="2024-12-31",
    )
    parser.add_argument(
        "--min-age",
        type=float,
        default=0,
    )
    parser.add_argument(
        "--max-age",
        type=float,
        default=90,
    )
    parser.add_argument(
        "--step-days",
        type=float,
        default=7,
    )
    parser.add_argument(
        "--years-of-history",
        type=float,
        default=5,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=90,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of modules to test.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Keep prior PASS results and automatically retry "
            "previously failed modules."
        ),
    )
    parser.add_argument(
        "--source-evidence",
        type=Path,
        default=None,
        help=(
            "Optional smoke-test evidence used to select a subset "
            "of modules for a follow-up run."
        ),
    )
    parser.add_argument(
        "--activity-filter",
        choices=ACTIVITY_CLASSIFICATIONS,
        default=None,
        help=(
            "Run only modules with this activity classification in "
            "--source-evidence."
        ),
    )

    arguments = parser.parse_args(argv)

    if arguments.population < 1:
        parser.error("--population must be >= 1")

    if arguments.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be > 0")

    if (
        arguments.source_evidence is None
        and arguments.activity_filter is not None
    ):
        parser.error(
            "--activity-filter requires --source-evidence"
        )

    if (
        arguments.source_evidence is not None
        and arguments.activity_filter is None
    ):
        parser.error(
            "--source-evidence requires --activity-filter"
        )

    return arguments


def _discover_modules(modules_dir: Path) -> tuple[Path, ...]:
    if not modules_dir.is_dir():
        raise ValueError(
            f"Modules directory does not exist: {modules_dir}"
        )

    modules = tuple(
        sorted(
            (
                path.resolve()
                for path in modules_dir.glob("*.json")
                if path.is_file()
            ),
            key=lambda path: path.name.lower(),
        )
    )

    if not modules:
        raise ValueError(
            f"No root JSON modules found in: {modules_dir}"
        )

    return modules


def _filter_modules_from_evidence(
    *,
    module_paths: Sequence[Path],
    source_evidence: Path,
    activity_filter: str,
) -> list[Path]:
    source_evidence = source_evidence.resolve()

    if not source_evidence.is_file():
        raise ValueError(
            f"Source evidence does not exist: {source_evidence}"
        )

    source_results = _load_completed_results(source_evidence)

    selected_names = {
        result.module
        for result in source_results
        if (
            result.status == "PASS"
            and result.activity_classification == activity_filter
        )
    }

    available_by_name = {
        path.stem: path
        for path in module_paths
    }

    missing_modules = sorted(
        selected_names.difference(available_by_name)
    )

    if missing_modules:
        raise ValueError(
            "Source evidence references modules that are not present "
            f"in --modules-dir: {', '.join(missing_modules)}"
        )

    return [
        available_by_name[module_name]
        for module_name in sorted(
            selected_names,
            key=str.lower,
        )
    ]


def _count_csv_rows(path: Path) -> int:
    if not path.is_file():
        return 0

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        reader = csv.reader(stream)
        next(reader, None)
        return sum(1 for _ in reader)


def _collect_row_counts(output_dir: Path) -> dict[str, int]:
    return {
        filename: _count_csv_rows(output_dir / filename)
        for filename in CSV_OUTPUTS
    }


def _classify_activity(
    row_counts: dict[str, int],
) -> tuple[int, int, str]:
    encounter_rows = row_counts.get("encounters.csv", 0)

    clinical_rows = sum(
        row_counts.get(filename, 0)
        for filename in CLINICAL_ACTIVITY_OUTPUTS
    )

    if clinical_rows > 0:
        classification = "CLINICAL_ACTIVITY"
    elif encounter_rows > 0:
        classification = "ENCOUNTERS_ONLY"
    else:
        classification = "NO_ACTIVITY"

    return encounter_rows, clinical_rows, classification


def _write_evidence(
    *,
    path: Path,
    modules_dir: Path,
    arguments: argparse.Namespace,
    results: Sequence[ModuleSmokeResult],
) -> None:
    status_counts: dict[str, int] = {}

    for result in results:
        status_counts[result.status] = (
            status_counts.get(result.status, 0) + 1
        )

    completed = len(results)
    passed = status_counts.get("PASS", 0)

    activity_counts: dict[str, int] = {}

    for result in results:
        classification = result.activity_classification
        activity_counts[classification] = (
            activity_counts.get(classification, 0) + 1
        )

    payload: dict[str, Any] = {
        "schema_version": "1.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer": {
            "name": "smoke_test_psynthea_modules",
            "version": "1.2.0",
        },
        "modules_dir": str(modules_dir),
        "parameters": {
            "population": arguments.population,
            "seed": arguments.seed,
            "end_date": arguments.end_date,
            "min_age": arguments.min_age,
            "max_age": arguments.max_age,
            "step_days": arguments.step_days,
            "years_of_history": arguments.years_of_history,
            "timeout_seconds": arguments.timeout_seconds,
            "source_evidence": (
                str(arguments.source_evidence.resolve())
                if arguments.source_evidence is not None
                else None
            ),
            "activity_filter": arguments.activity_filter,
        },
        "summary": {
            "completed_modules": completed,
            "passed_modules": passed,
            "pass_fraction": (
                passed / completed
                if completed
                else 0.0
            ),
            "status_counts": dict(sorted(status_counts.items())),
            "activity_counts": dict(
                sorted(activity_counts.items())
            ),
        },
        "results": [asdict(result) for result in results],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_completed_results(
    path: Path,
) -> list[ModuleSmokeResult]:
    if not path.is_file():
        return []

    payload = json.loads(path.read_text(encoding="utf-8"))
    results: list[ModuleSmokeResult] = []

    for raw_result in payload.get("results", []):
        result = dict(raw_result)
        row_counts = result.get("row_counts", {})

        if result.get("status") == "PASS":
            (
                encounter_rows,
                clinical_rows,
                classification,
            ) = _classify_activity(row_counts)
        else:
            encounter_rows = 0
            clinical_rows = 0
            classification = "NOT_APPLICABLE"

        result.setdefault(
            "encounter_rows",
            encounter_rows,
        )
        result.setdefault(
            "clinical_rows",
            clinical_rows,
        )
        result.setdefault(
            "activity_classification",
            classification,
        )

        results.append(ModuleSmokeResult(**result))

    return results


def _smoke_test_module(
    *,
    module_path: Path,
    modules_dir: Path,
    output_root: Path,
    arguments: argparse.Namespace,
) -> ModuleSmokeResult:
    module_name = module_path.stem
    module_output = output_root / "modules" / module_name
    logs_dir = output_root / "logs"

    module_output.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = logs_dir / f"{module_name}.stdout.log"
    stderr_path = logs_dir / f"{module_name}.stderr.log"

    started = time.monotonic()

    try:
        load_module_with_submodules(
            module_path,
            modules_dir,
        )
    except Exception as error:  # noqa: BLE001
        duration = time.monotonic() - started

        stderr_path.write_text(
            f"{error.__class__.__module__}."
            f"{error.__class__.__qualname__}: {error}\n",
            encoding="utf-8",
        )

        return ModuleSmokeResult(
            module=module_name,
            module_path=str(module_path),
            status="PARSE_ERROR",
            parse_ok=False,
            execution_ok=False,
            export_ok=False,
            return_code=None,
            duration_seconds=round(duration, 6),
            row_counts={},
            non_patient_rows=0,
            stderr_log=str(stderr_path),
            error_type=(
                f"{error.__class__.__module__}."
                f"{error.__class__.__qualname__}"
            ),
            error_message=str(error),
        )

    command = [
        sys.executable,
        "-m",
        "psynthea.cli",
        "generate",
        "-p",
        str(arguments.population),
        "-s",
        str(arguments.seed),
        "-m",
        module_name,
        "-d",
        str(modules_dir),
        "--min-age",
        str(arguments.min_age),
        "--max-age",
        str(arguments.max_age),
        "--end-date",
        arguments.end_date,
        "--step-days",
        str(arguments.step_days),
        "--years-of-history",
        str(arguments.years_of_history),
        "--wellness-encounters",
        "--vitals",
        "--mortality",
        "--keystone",
        "--format",
        "csv",
        "--output",
        str(module_output),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=arguments.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        duration = time.monotonic() - started

        stdout_path.write_text(
            error.stdout or "",
            encoding="utf-8",
        )
        stderr_path.write_text(
            error.stderr or "",
            encoding="utf-8",
        )

        return ModuleSmokeResult(
            module=module_name,
            module_path=str(module_path),
            status="TIMEOUT",
            parse_ok=True,
            execution_ok=False,
            export_ok=False,
            return_code=None,
            duration_seconds=round(duration, 6),
            row_counts={},
            non_patient_rows=0,
            stdout_log=str(stdout_path),
            stderr_log=str(stderr_path),
            error_type="subprocess.TimeoutExpired",
            error_message=(
                f"Execution exceeded "
                f"{arguments.timeout_seconds} seconds."
            ),
        )

    duration = time.monotonic() - started

    stdout_path.write_text(
        completed.stdout,
        encoding="utf-8",
    )
    stderr_path.write_text(
        completed.stderr,
        encoding="utf-8",
    )

    if completed.returncode != 0:
        return ModuleSmokeResult(
            module=module_name,
            module_path=str(module_path),
            status="RUNTIME_ERROR",
            parse_ok=True,
            execution_ok=False,
            export_ok=False,
            return_code=completed.returncode,
            duration_seconds=round(duration, 6),
            row_counts={},
            non_patient_rows=0,
            stdout_log=str(stdout_path),
            stderr_log=str(stderr_path),
            error_type="subprocess.CalledProcessError",
            error_message=(
                completed.stderr.strip()
                or completed.stdout.strip()
                or "Psynthea exited with a non-zero return code."
            ),
        )

    row_counts = _collect_row_counts(module_output)

    patients_path = module_output / "patients.csv"
    export_ok = (
        patients_path.is_file()
        and row_counts["patients.csv"] == arguments.population
    )

    non_patient_rows = sum(
        count
        for filename, count in row_counts.items()
        if filename != "patients.csv"
    )

    (
        encounter_rows,
        clinical_rows,
        classification,
    ) = _classify_activity(row_counts)

    if not export_ok:
        return ModuleSmokeResult(
            module=module_name,
            module_path=str(module_path),
            status="EXPORT_ERROR",
            parse_ok=True,
            execution_ok=True,
            export_ok=False,
            return_code=completed.returncode,
            duration_seconds=round(duration, 6),
            row_counts=row_counts,
            non_patient_rows=non_patient_rows,
            stdout_log=str(stdout_path),
            stderr_log=str(stderr_path),
            error_type="CSVExportError",
            error_message=(
                "patients.csv is missing or does not contain "
                f"{arguments.population} patients."
            ),
            encounter_rows=encounter_rows,
            clinical_rows=clinical_rows,
            activity_classification=classification,
        )

    return ModuleSmokeResult(
        module=module_name,
        module_path=str(module_path),
        status="PASS",
        parse_ok=True,
        execution_ok=True,
        export_ok=True,
        return_code=completed.returncode,
        duration_seconds=round(duration, 6),
        row_counts=row_counts,
        non_patient_rows=non_patient_rows,
        stdout_log=str(stdout_path),
        stderr_log=str(stderr_path),
        encounter_rows=encounter_rows,
        clinical_rows=clinical_rows,
        activity_classification=classification,
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)

    try:
        modules_dir = arguments.modules_dir.resolve()
        output_root = arguments.output.resolve()
        evidence_path = output_root / "smoke_test_result.json"

        discovered_module_paths = list(
            _discover_modules(modules_dir)
        )
        module_paths = discovered_module_paths

        if arguments.source_evidence is not None:
            module_paths = _filter_modules_from_evidence(
                module_paths=module_paths,
                source_evidence=arguments.source_evidence,
                activity_filter=arguments.activity_filter,
            )

        if arguments.limit is not None:
            module_paths = module_paths[: arguments.limit]

        loaded_results = (
            _load_completed_results(evidence_path)
            if arguments.resume
            else []
        )

        results = [
            result
            for result in loaded_results
            if result.status == "PASS"
        ]

        completed_modules = {
            result.module
            for result in results
        }

        pending_modules = [
            path
            for path in module_paths
            if path.stem not in completed_modules
        ]

        print(
            f"Modules discovered: "
            f"{len(discovered_module_paths)}"
        )

        if arguments.source_evidence is not None:
            print(
                f"Activity filter: "
                f"{arguments.activity_filter}"
            )
            print(
                f"Modules selected: "
                f"{len(module_paths)}"
            )
            print(
                f"Source evidence: "
                f"{arguments.source_evidence.resolve()}"
            )

        print(f"Already completed: {len(completed_modules)}")
        print(f"Pending: {len(pending_modules)}")

        for index, module_path in enumerate(
            pending_modules,
            start=len(results) + 1,
        ):
            print(
                f"[{index}/{len(module_paths)}] "
                f"{module_path.stem} ...",
                end=" ",
                flush=True,
            )

            result = _smoke_test_module(
                module_path=module_path,
                modules_dir=modules_dir,
                output_root=output_root,
                arguments=arguments,
            )
            results.append(result)

            _write_evidence(
                path=evidence_path,
                modules_dir=modules_dir,
                arguments=arguments,
                results=results,
            )

            print(
                f"{result.status} "
                f"({result.duration_seconds:.2f}s, "
                f"encounters={result.encounter_rows}, "
                f"clinical={result.clinical_rows}, "
                f"activity={result.activity_classification})"
            )

        _write_evidence(
            path=evidence_path,
            modules_dir=modules_dir,
            arguments=arguments,
            results=results,
        )

        summary_payload = json.loads(
            evidence_path.read_text(encoding="utf-8")
        )
        summary = summary_payload["summary"]

        print()
        print("=" * 72)
        print("PSYNTHEA MODULE RUNTIME SMOKE TEST")
        print("=" * 72)
        print(f"Completed: {summary['completed_modules']}")
        print(f"Passed: {summary['passed_modules']}")
        print(f"Pass fraction: {summary['pass_fraction']:.2%}")

        for status, count in summary["status_counts"].items():
            print(f"{status}: {count}")

        print()
        print("Activity classification:")

        for classification, count in (
            summary.get("activity_counts", {}).items()
        ):
            print(f"{classification}: {count}")

        print(f"Evidence: {evidence_path}")

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())