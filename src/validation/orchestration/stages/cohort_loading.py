"""Production cohort-loading stage for the experiment pipeline.

The stage is the boundary between simulator output artefacts and the canonical
``ValidationCohort`` representation consumed by the validation framework.
It deliberately performs no normalization and no statistical comparison.

For each simulator, the handler:

* locates the canonical CSV output directory from verified runner artefacts;
* invokes the existing simulator-specific loader;
* validates the loaded cohort contract;
* records table-level provenance, shape and source artefact hashes;
* persists one deterministic cohort-loading manifest in the workspace.

The persisted manifest becomes the auditable input contract for the following
normalization stage. Raw simulator files are never modified or copied.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import pandas as pd

from validation.constants import (
    CSV_FILES,
    SOURCE_PSYNTHEA,
    SOURCE_SYNTHEA,
)
from validation.loaders import load_psynthea, load_synthea
from validation.models import ValidationCohort
from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
    ExecutionStatus,
    ExperimentStage,
    SimulatorKind,
    SimulatorRunResult,
)
from validation.orchestration.orchestrator import (
    OrchestrationContext,
    StageOutput,
)

__all__ = [
    "CohortLoader",
    "CohortLoadingError",
    "CohortLoadingStageHandler",
]


_COHORT_LOAD_SCHEMA_VERSION: Final = "1.0"
_COHORT_LOAD_PATH: Final = "loaded/cohort_loading_manifest.json"
_COHORT_LOAD_PRODUCER: Final = "cohort_loading_stage"
_TABLE_ORDER: Final = tuple(CSV_FILES)

_EXPECTED_SOURCE: Final[Mapping[SimulatorKind, str]] = MappingProxyType(
    {
        SimulatorKind.SYNTHEA: SOURCE_SYNTHEA,
        SimulatorKind.PSYNTHEA: SOURCE_PSYNTHEA,
    }
)

CohortLoader = Callable[[str | Path], ValidationCohort]


class CohortLoadingError(RuntimeError):
    """Raised when simulator outputs cannot form a trustworthy cohort."""


@dataclass(frozen=True, slots=True)
class CohortLoadingStageHandler:
    """Load both simulator cohorts and persist their provenance manifest."""

    loaders: Mapping[SimulatorKind, CohortLoader] = field(
        default_factory=lambda: MappingProxyType(
            {
                SimulatorKind.SYNTHEA: load_synthea,
                SimulatorKind.PSYNTHEA: load_psynthea,
            }
        )
    )
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    stage: ExperimentStage = field(
        default=ExperimentStage.COHORT_LOADING,
        init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.loaders, Mapping):
            raise TypeError("loaders must be a mapping.")

        required = frozenset(SimulatorKind)
        provided = frozenset(self.loaders)

        if provided != required:
            missing = sorted(
                item.value for item in required - provided
            )
            extra = sorted(
                repr(item) for item in provided - required
            )

            details: list[str] = []

            if missing:
                details.append("missing=" + ",".join(missing))

            if extra:
                details.append("unexpected=" + ",".join(extra))

            raise ValueError(
                "loaders must define exactly one loader per SimulatorKind"
                + (
                    f" ({'; '.join(details)})"
                    if details
                    else ""
                )
                + "."
            )

        normalized: dict[SimulatorKind, CohortLoader] = {}

        for simulator, loader in self.loaders.items():
            if not isinstance(simulator, SimulatorKind):
                raise TypeError(
                    "loader mapping keys must be SimulatorKind members."
                )

            if not callable(loader):
                raise TypeError(
                    f"loader for {simulator.value} must be callable."
                )

            normalized[simulator] = loader

        if not callable(self.clock):
            raise TypeError("clock must be callable.")

        object.__setattr__(
            self,
            "loaders",
            MappingProxyType(normalized),
        )

    def execute(
        self,
        context: OrchestrationContext,
    ) -> StageOutput:
        """Load Synthea and psynthea into canonical cohort contracts."""

        if not isinstance(context, OrchestrationContext):
            raise TypeError(
                "context must be an OrchestrationContext."
            )

        generated_at = _aware_datetime(
            self.clock(),
            "clock result",
        )

        runs = _successful_runs_by_simulator(
            context.simulator_runs
        )

        cohort_payloads: dict[str, Any] = {}
        total_source_artifacts = 0

        for simulator in SimulatorKind:
            run = runs[simulator]

            source_artifacts = _canonical_csv_artifacts(run)
            total_source_artifacts += len(source_artifacts)

            output_directory = _cohort_output_directory(
                context,
                simulator=simulator,
                artifacts=source_artifacts,
            )

            cohort = self.loaders[simulator](
                output_directory
            )

            _validate_loaded_cohort(
                cohort,
                simulator=simulator,
                output_directory=output_directory,
            )

            cohort_payloads[simulator.value] = _cohort_payload(
                context,
                simulator=simulator,
                cohort=cohort,
                artifacts=source_artifacts,
            )

        payload = {
            "schema_version": _COHORT_LOAD_SCHEMA_VERSION,
            "experiment_id": context.config.id,
            "run_id": context.run_id,
            "generated_at": generated_at.isoformat(),
            "requested_population": (
                context.config.cohort.population
            ),
            "cohorts": cohort_payloads,
        }

        manifest_path = context.workspace.write_json(
            _COHORT_LOAD_PATH,
            payload,
        )

        artifact = context.workspace.artifact_reference(
            artifact_id=(
                f"{context.config.id}:"
                f"{context.run_id}:"
                "cohort-loading"
            ),
            kind=ArtifactKind.COHORT_LOAD_RESULT,
            path=manifest_path,
            media_type="application/json",
            producer=_COHORT_LOAD_PRODUCER,
            created_at=generated_at,
            metadata={
                "schema_version": (
                    _COHORT_LOAD_SCHEMA_VERSION
                ),
                "simulator_count": len(cohort_payloads),
                "source_artifact_count": (
                    total_source_artifacts
                ),
                "synthea_patients": cohort_payloads[
                    SimulatorKind.SYNTHEA.value
                ]["summary"]["patients"],
                "psynthea_patients": cohort_payloads[
                    SimulatorKind.PSYNTHEA.value
                ]["summary"]["patients"],
            },
        )

        return StageOutput(
            artifacts=(artifact,),
            summary=(
                "Loaded and verified Synthea and psynthea "
                f"cohorts from {total_source_artifacts} "
                "canonical CSV artefacts."
            ),
            metadata={
                "schema_version": (
                    _COHORT_LOAD_SCHEMA_VERSION
                ),
                "source_artifact_count": (
                    total_source_artifacts
                ),
                "cohort_count": len(cohort_payloads),
                "patient_counts": {
                    simulator: item["summary"]["patients"]
                    for simulator, item
                    in cohort_payloads.items()
                },
            },
        )


def _successful_runs_by_simulator(
    runs: Sequence[SimulatorRunResult],
) -> Mapping[SimulatorKind, SimulatorRunResult]:
    if isinstance(runs, (str, bytes)) or not isinstance(
        runs,
        Sequence,
    ):
        raise TypeError(
            "runs must be a sequence of SimulatorRunResult values."
        )

    indexed: dict[
        SimulatorKind,
        SimulatorRunResult,
    ] = {}

    for index, run in enumerate(runs):
        if not isinstance(run, SimulatorRunResult):
            raise TypeError(
                f"runs[{index}] must be a SimulatorRunResult."
            )

        if run.simulator in indexed:
            raise CohortLoadingError(
                "Duplicate simulator run for "
                f"{run.simulator.value}."
            )

        indexed[run.simulator] = run

    missing = [
        simulator
        for simulator in SimulatorKind
        if simulator not in indexed
    ]

    if missing:
        raise CohortLoadingError(
            "Missing simulator run(s): "
            + ", ".join(
                item.value for item in missing
            )
            + "."
        )

    failed = [
        run.simulator.value
        for run in indexed.values()
        if run.status is not ExecutionStatus.SUCCEEDED
    ]

    if failed:
        raise CohortLoadingError(
            "Cohort loading requires successful "
            "simulator runs: "
            + ", ".join(sorted(failed))
            + "."
        )

    return MappingProxyType(indexed)


def _canonical_csv_artifacts(
    run: SimulatorRunResult,
) -> Mapping[str, ArtifactReference]:
    expected_filenames = frozenset(
        CSV_FILES.values()
    )

    indexed: dict[str, ArtifactReference] = {}

    for artifact in run.artifacts:
        if artifact.kind is not ArtifactKind.SIMULATOR_OUTPUT:
            continue

        filename = artifact.path.name

        if filename not in expected_filenames:
            continue

        if filename in indexed:
            raise CohortLoadingError(
                f"Simulator {run.simulator.value} produced "
                "duplicate canonical CSV artefact "
                f"{filename!r}."
            )

        indexed[filename] = artifact

    patients_filename = CSV_FILES["patients"]

    if patients_filename not in indexed:
        raise CohortLoadingError(
            f"Simulator {run.simulator.value} did not "
            f"produce required {patients_filename!r}."
        )

    return MappingProxyType(indexed)


def _cohort_output_directory(
    context: OrchestrationContext,
    *,
    simulator: SimulatorKind,
    artifacts: Mapping[str, ArtifactReference],
) -> Path:
    parents = {
        artifact.path.parent
        for artifact in artifacts.values()
    }

    if len(parents) != 1:
        raise CohortLoadingError(
            "Canonical CSV artefacts for "
            f"{simulator.value} must share one "
            "output directory."
        )

    relative_directory = next(iter(parents))

    output_directory = context.workspace.resolve(
        relative_directory
    )

    if (
        output_directory.is_symlink()
        or not output_directory.is_dir()
    ):
        raise CohortLoadingError(
            "Cohort output directory for "
            f"{simulator.value} is invalid: "
            f"{output_directory}"
        )

    return output_directory


def _validate_loaded_cohort(
    cohort: ValidationCohort,
    *,
    simulator: SimulatorKind,
    output_directory: Path,
) -> None:
    if not isinstance(cohort, ValidationCohort):
        raise CohortLoadingError(
            f"Loader for {simulator.value} returned "
            f"{type(cohort).__name__}, expected "
            "ValidationCohort."
        )

    expected_source = _EXPECTED_SOURCE[simulator]

    if cohort.source != expected_source:
        raise CohortLoadingError(
            f"Loader for {simulator.value} returned "
            f"source {cohort.source!r}; expected "
            f"{expected_source!r}."
        )

    if cohort.output_path is None:
        raise CohortLoadingError(
            f"Loaded cohort for {simulator.value} "
            "has no output_path."
        )

    if (
        cohort.output_path.resolve(strict=False)
        != output_directory.resolve(strict=False)
    ):
        raise CohortLoadingError(
            "Loaded cohort output_path for "
            f"{simulator.value} does not match the "
            "verified simulator artefact directory."
        )

    if not isinstance(
        cohort.patients,
        pd.DataFrame,
    ):
        raise CohortLoadingError(
            f"Loaded cohort for {simulator.value} "
            "has no patients DataFrame."
        )

    if cohort.patients.empty:
        raise CohortLoadingError(
            f"Loaded cohort for {simulator.value} "
            "contains zero patients."
        )

    for table_name in _TABLE_ORDER:
        table = getattr(cohort, table_name)

        if table is not None and not isinstance(
            table,
            pd.DataFrame,
        ):
            raise CohortLoadingError(
                "Loaded table "
                f"{simulator.value}.{table_name} "
                "must be a pandas DataFrame or None."
            )


def _cohort_payload(
    context: OrchestrationContext,
    *,
    simulator: SimulatorKind,
    cohort: ValidationCohort,
    artifacts: Mapping[str, ArtifactReference],
) -> Mapping[str, Any]:
    tables: dict[str, Any] = {}

    for table_name in _TABLE_ORDER:
        filename = CSV_FILES[table_name]
        table = getattr(cohort, table_name)
        artifact = artifacts.get(filename)

        if artifact is None:
            tables[table_name] = {
                "present": False,
                "filename": filename,
                "rows": 0,
                "columns": [],
                "artifact_id": None,
                "path": None,
                "sha256": None,
                "size_bytes": None,
            }
            continue

        if table is None:
            raise CohortLoadingError(
                "Loader did not expose table "
                f"{simulator.value}.{table_name} "
                "despite the presence of "
                f"{filename!r}."
            )

        tables[table_name] = {
            "present": True,
            "filename": filename,
            "rows": int(len(table)),
            "columns": [
                str(column)
                for column in table.columns
            ],
            "artifact_id": artifact.id,
            "path": artifact.path.as_posix(),
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
        }

    output_path = context.workspace.relative(
        cohort.output_path
    ).as_posix()

    summary = {
        key: (
            int(value)
            if isinstance(value, int)
            else value
        )
        for key, value in cohort.summary.items()
    }

    return {
        "simulator": simulator.value,
        "source": cohort.source,
        "output_path": output_path,
        "summary": summary,
        "tables": tables,
    }


def _aware_datetime(
    value: datetime,
    field_name: str,
) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(
            f"{field_name} must be a datetime."
        )

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_name} must be timezone-aware."
        )

    return value.astimezone(UTC)