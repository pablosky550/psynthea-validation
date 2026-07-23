#!/usr/bin/env python3
"""Audit root Synthea modules against Psynthea's JSON compatibility loader."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from psynthea.compat.synthea_json import load_module_file


@dataclass(frozen=True, slots=True)
class ModuleCompatibilityResult:
    """Compatibility result for one root Synthea module."""

    module: str
    path: str
    sha256: str
    compatible: bool
    error_type: str | None = None
    error_message: str | None = None


def _parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit every root JSON module in a Synthea modules directory "
            "using Psynthea's production module loader."
        ),
    )
    parser.add_argument(
        "--modules-dir",
        type=Path,
        required=True,
        help="Directory containing Synthea root module JSON files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination JSON evidence file.",
    )
    parser.add_argument(
        "--compatible-config",
        type=Path,
        help=(
            "Optional experiment configuration to create from --base-config, "
            "containing only compatible modules."
        ),
    )
    parser.add_argument(
        "--base-config",
        type=Path,
        help="Base experiment configuration used with --compatible-config.",
    )

    arguments = parser.parse_args(argv)

    if (arguments.compatible_config is None) != (
        arguments.base_config is None
    ):
        parser.error(
            "--compatible-config and --base-config must be supplied together."
        )

    return arguments


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _discover_root_modules(modules_dir: Path) -> tuple[Path, ...]:
    if not modules_dir.is_dir():
        raise ValueError(
            f"Modules directory does not exist: {modules_dir}"
        )

    module_paths = tuple(
        sorted(
            (
                path.resolve()
                for path in modules_dir.glob("*.json")
                if path.is_file()
            ),
            key=lambda path: path.name,
        )
    )

    if not module_paths:
        raise ValueError(
            f"No root JSON modules were found in: {modules_dir}"
        )

    return module_paths


def _audit_module(path: Path) -> ModuleCompatibilityResult:
    try:
        load_module_file(path)
    except Exception as error:  # noqa: BLE001 - evidence must capture all failures
        return ModuleCompatibilityResult(
            module=path.stem,
            path=str(path),
            sha256=_sha256(path),
            compatible=False,
            error_type=(
                f"{error.__class__.__module__}."
                f"{error.__class__.__qualname__}"
            ),
            error_message=str(error),
        )

    return ModuleCompatibilityResult(
        module=path.stem,
        path=str(path),
        sha256=_sha256(path),
        compatible=True,
    )


def _build_evidence(
    *,
    modules_dir: Path,
    results: tuple[ModuleCompatibilityResult, ...],
) -> dict[str, Any]:
    compatible = tuple(
        result.module
        for result in results
        if result.compatible
    )
    incompatible = tuple(
        result.module
        for result in results
        if not result.compatible
    )

    failure_counts: dict[str, int] = {}
    for result in results:
        if result.compatible:
            continue

        key = result.error_message or result.error_type or "unknown"
        failure_counts[key] = failure_counts.get(key, 0) + 1

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer": {
            "name": "audit_psynthea_module_compatibility",
            "version": "1.0.0",
        },
        "loader": (
            "psynthea.compat.synthea_json.load_module_file"
        ),
        "modules_dir": str(modules_dir.resolve()),
        "summary": {
            "root_modules": len(results),
            "compatible": len(compatible),
            "incompatible": len(incompatible),
            "coverage": (
                len(compatible) / len(results)
                if results
                else 0.0
            ),
            "failure_counts": dict(sorted(failure_counts.items())),
        },
        "compatible_modules": list(compatible),
        "incompatible_modules": list(incompatible),
        "results": [asdict(result) for result in results],
    }


def _write_compatible_config(
    *,
    base_config_path: Path,
    output_path: Path,
    compatible_modules: Sequence[str],
    modules_dir: Path,
) -> None:
    with base_config_path.open(encoding="utf-8") as stream:
        payload = json.load(stream)

    cohort = payload.get("cohort")
    if not isinstance(cohort, dict):
        raise ValueError(
            "Base configuration must contain a cohort object."
        )

    payload["id"] = f"{payload['id']}-psynthea-compatible"
    payload["name"] = (
        f"{payload.get('name', payload['id'])} — "
        "Psynthea-compatible modules"
    )
    payload["description"] = (
        "Explicit execution subset generated by the Psynthea module "
        "compatibility audit. Excluded modules remain documented in the "
        "associated compatibility evidence."
    )

    tags = payload.get("tags", [])
    if not isinstance(tags, list):
        raise ValueError("Base configuration tags must be a list.")

    payload["tags"] = list(
        dict.fromkeys(
            (
                *tags,
                "psynthea-compatible",
                "compatibility-audited",
            )
        )
    )

    cohort["module_selection"] = "explicit"
    cohort["modules"] = list(compatible_modules)
    cohort["module_files"] = []
    cohort["modules_dir"] = str(modules_dir.resolve())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)

    try:
        modules_dir = arguments.modules_dir.resolve()
        module_paths = _discover_root_modules(modules_dir)
        results = tuple(_audit_module(path) for path in module_paths)

        evidence = _build_evidence(
            modules_dir=modules_dir,
            results=results,
        )

        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        if arguments.compatible_config is not None:
            _write_compatible_config(
                base_config_path=arguments.base_config.resolve(),
                output_path=arguments.compatible_config.resolve(),
                compatible_modules=evidence["compatible_modules"],
                modules_dir=modules_dir,
            )

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    summary = evidence["summary"]

    print(f"Root modules: {summary['root_modules']}")
    print(f"Compatible: {summary['compatible']}")
    print(f"Incompatible: {summary['incompatible']}")
    print(f"Coverage: {summary['coverage']:.2%}")
    print(f"Evidence: {arguments.output}")

    if arguments.compatible_config is not None:
        print(f"Compatible config: {arguments.compatible_config}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())