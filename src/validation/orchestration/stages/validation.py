"""Production validation stage for the experiment pipeline.

This stage consumes only the deterministic normalized datasets produced by the
cohort-normalization stage. It reconstructs canonical ``ValidationCohort``
objects, executes the real functional and statistical comparison engine for
every configured module and persists fully traceable validation artefacts.

Responsibilities
----------------
* Locate and verify the cohort-normalization result.
* Verify every normalized dataset using its recorded size and SHA-256 hash.
* Reconstruct Synthea and psynthea ``ValidationCohort`` instances.
* Execute ``compare_module_statistics`` for every configured module.
* Persist functional and statistical result tables as deterministic CSV files.
* Persist one canonical machine-readable validation result.

The stage deliberately performs no clinical interpretation, knowledge
enrichment, root-cause attribution or final report rendering.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import pandas as pd

from validation.comparison.statistical_comparison import (
    ModuleStatisticalComparisonResult,
    compare_module_statistics,
)
from validation.constants import (
    CSV_FILES,
    DEFAULT_SIGNIFICANCE_LEVEL,
    SOURCE_PSYNTHEA,
    SOURCE_SYNTHEA,
)
from validation.models import ValidationCohort
from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
    ExperimentStage,
    SimulatorKind,
)
from validation.orchestration.orchestrator import (
    OrchestrationContext,
    StageOutput,
)

__all__ = [
    "ModuleComparator",
    "ValidationStageError",
    "ValidationStageHandler",
]


_VALIDATION_SCHEMA_VERSION: Final = "1.0"
_SUPPORTED_NORMALIZATION_SCHEMA_VERSION: Final = "1.0"

_VALIDATION_RESULT_PATH: Final = (
    "validation/validation_result.json"
)

_VALIDATION_PRODUCER: Final = "validation_stage"
_NORMALIZATION_PRODUCER: Final = "cohort_normalization_stage"

_DEFAULT_TOP_N_CODES: Final = 25

_TABLE_ORDER: Final = tuple(CSV_FILES)

_VALIDATION_TABLES: Final[
    tuple[tuple[str, str], ...]
] = (
    (
        "functional_table_status",
        "validation.table_status",
    ),
    (
        "functional_clinical_signal",
        "validation.clinical_signal",
    ),
    (
        "functional_distributional_similarity",
        "validation.distributional_similarity",
    ),
    (
        "functional_issues",
        "validation.issues",
    ),
    (
        "functional_summary",
        "validation.summary",
    ),
    (
        "continuous_tests",
        "continuous_tests",
    ),
    (
        "categorical_tests",
        "categorical_tests",
    ),
    (
        "prevalence_tests",
        "prevalence_tests",
    ),
    (
        "distribution_tests",
        "distribution_tests",
    ),
    (
        "statistical_summary",
        "summary",
    ),
)

_EXPECTED_SOURCE: Final[
    Mapping[SimulatorKind, str]
] = MappingProxyType(
    {
        SimulatorKind.SYNTHEA: SOURCE_SYNTHEA,
        SimulatorKind.PSYNTHEA: SOURCE_PSYNTHEA,
    }
)

ModuleComparator = Callable[
    ...,
    ModuleStatisticalComparisonResult,
]


class ValidationStageError(RuntimeError):
    """Raised when validation cannot be executed or persisted safely."""


@dataclass(frozen=True, slots=True)
class ValidationStageHandler:
    """Execute the real validation engine over normalized cohorts."""

    comparator: ModuleComparator = compare_module_statistics
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    stage: ExperimentStage = field(
        default=ExperimentStage.VALIDATION,
        init=False,
    )

    def __post_init__(self) -> None:
        if not callable(self.comparator):
            raise TypeError("comparator must be callable.")

        if not callable(self.clock):
            raise TypeError("clock must be callable.")

    def execute(
        self,
        context: OrchestrationContext,
    ) -> StageOutput:
        """Execute functional and statistical validation."""

        if not isinstance(context, OrchestrationContext):
            raise TypeError(
                "context must be an OrchestrationContext."
            )

        generated_at = _aware_datetime(
            self.clock(),
            "clock result",
        )

        normalization_artifact = (
            _normalization_manifest_artifact(
                context.artifacts
            )
        )

        normalization_manifest = (
            _read_verified_json_artifact(
                context,
                normalization_artifact,
            )
        )

        _validate_normalization_manifest(
            normalization_manifest,
            context=context,
        )

        cohorts = {
            simulator: _load_normalized_cohort(
                context,
                simulator=simulator,
                manifest=normalization_manifest,
            )
            for simulator in SimulatorKind
        }

        settings = _validation_settings(
            context.config.metadata
        )

        module_results: list[
            ModuleStatisticalComparisonResult
        ] = []

        evidence_artifacts: list[
            ArtifactReference
        ] = []

        modules_payload: list[
            Mapping[str, Any]
        ] = []

        configured_module_names = tuple(
            dict.fromkeys(
                (
                    *context.config.cohort.modules,
                    *(
                        module_file.stem
                        for module_file in context.config.cohort.module_files
                    ),
                )
            )
        )

        if not configured_module_names:
            raise ValidationStageError(
                "Experiment cohort does not configure any modules "
                "through 'modules' or 'module_files'."
            )

        for module_name in configured_module_names:
            module_settings = _module_settings(
                settings,
                module_name,
            )

            try:
                result = self.comparator(
                    module_name=module_name,
                    synthea_cohort=cohorts[
                        SimulatorKind.SYNTHEA
                    ],
                    psynthea_cohort=cohorts[
                        SimulatorKind.PSYNTHEA
                    ],
                    expected_condition_terms=(
                        module_settings[
                            "expected_condition_terms"
                        ]
                    ),
                    expected_medication_terms=(
                        module_settings[
                            "expected_medication_terms"
                        ]
                    ),
                    expected_procedure_terms=(
                        module_settings[
                            "expected_procedure_terms"
                        ]
                    ),
                    expected_observation_terms=(
                        module_settings[
                            "expected_observation_terms"
                        ]
                    ),
                    top_n_codes=settings[
                        "top_n_codes"
                    ],
                    alpha=settings["alpha"],
                )
            except Exception as exc:
                raise ValidationStageError(
                    "Validation engine failed for "
                    f"module {module_name!r}: {exc}"
                ) from exc

            if not isinstance(
                result,
                ModuleStatisticalComparisonResult,
            ):
                raise ValidationStageError(
                    "Comparator for module "
                    f"{module_name!r} returned "
                    f"{type(result).__name__}; expected "
                    "ModuleStatisticalComparisonResult."
                )

            module_results.append(result)

            (
                module_artifacts,
                module_payload,
            ) = _persist_module_result(
                context,
                result=result,
                generated_at=generated_at,
            )

            evidence_artifacts.extend(
                module_artifacts
            )

            modules_payload.append(
                module_payload
            )

        aggregate = dict(
            _aggregate_validation(
                modules_payload
            )
        )

        result_payload = {
            "schema_version": (
                _VALIDATION_SCHEMA_VERSION
            ),
            "experiment_id": context.config.id,
            "run_id": context.run_id,
            "generated_at": generated_at.isoformat(),
            "source_normalization_artifact": {
                "artifact_id": (
                    normalization_artifact.id
                ),
                "path": (
                    normalization_artifact.path
                    .as_posix()
                ),
                "sha256": (
                    normalization_artifact.sha256
                ),
                "size_bytes": (
                    normalization_artifact.size_bytes
                ),
            },
            "configuration": {
                "alpha": settings["alpha"],
                "top_n_codes": (
                    settings["top_n_codes"]
                ),
                "modules": list(
                    configured_module_names
                ),
            },
            "cohorts": {
                simulator.value: {
                    "source": cohort.source,
                    "patients": cohort.n_patients,
                    "encounters": (
                        cohort.n_encounters
                    ),
                    "conditions": (
                        cohort.n_conditions
                    ),
                    "medications": (
                        cohort.n_medications
                    ),
                    "procedures": (
                        cohort.n_procedures
                    ),
                    "observations": (
                        cohort.n_observations
                    ),
                }
                for simulator, cohort
                in cohorts.items()
            },
            "aggregate": aggregate,
            "modules": modules_payload,
        }

        result_path = context.workspace.write_json(
            _VALIDATION_RESULT_PATH,
            result_payload,
        )

        validation_artifact = (
            context.workspace.artifact_reference(
                artifact_id=(
                    f"{context.config.id}:"
                    f"{context.run_id}:"
                    "validation-result"
                ),
                kind=(
                    ArtifactKind.VALIDATION_RESULT
                ),
                path=result_path,
                media_type="application/json",
                producer=_VALIDATION_PRODUCER,
                created_at=generated_at,
                metadata={
                    "schema_version": (
                        _VALIDATION_SCHEMA_VERSION
                    ),
                    "module_count": (
                        aggregate["module_count"]
                    ),
                    "comparable_module_count": (
                        aggregate[
                            "comparable_module_count"
                        ]
                    ),
                    "skipped_module_count": (
                        aggregate[
                            "skipped_module_count"
                        ]
                    ),
                    "significant_test_count": (
                        aggregate[
                            "significant_test_count"
                        ]
                    ),
                    "significant_after_fdr_count": (
                        aggregate[
                            "significant_after_fdr_count"
                        ]
                    ),
                    "evidence_artifact_count": len(
                        evidence_artifacts
                    ),
                },
            )
        )

        return StageOutput(
            artifacts=(
                *evidence_artifacts,
                validation_artifact,
            ),
            summary=(
                "Executed functional and statistical "
                f"validation for "
                f"{aggregate['module_count']} module(s); "
                f"{aggregate['comparable_module_count']} "
                "were statistically comparable."
            ),
            metadata={
                "schema_version": (
                    _VALIDATION_SCHEMA_VERSION
                ),
                **aggregate,
                "alpha": settings["alpha"],
                "top_n_codes": (
                    settings["top_n_codes"]
                ),
                "validation_result_artifact_id": (
                    validation_artifact.id
                ),
            },
        )


def _normalization_manifest_artifact(
    artifacts: Sequence[ArtifactReference],
) -> ArtifactReference:
    if isinstance(artifacts, (str, bytes)):
        raise TypeError(
            "artifacts must be a sequence."
        )

    candidates = [
        artifact
        for artifact in artifacts
        if (
            artifact.kind
            is ArtifactKind.COHORT_NORMALIZATION_RESULT
            and artifact.producer
            == _NORMALIZATION_PRODUCER
        )
    ]

    if len(candidates) != 1:
        raise ValidationStageError(
            "Validation requires exactly one "
            "cohort-normalization result artifact; "
            f"found {len(candidates)}."
        )

    return candidates[0]


def _read_verified_json_artifact(
    context: OrchestrationContext,
    artifact: ArtifactReference,
) -> Mapping[str, Any]:
    path = context.workspace.resolve(
        artifact.path
    )

    _verify_file_identity(
        path,
        expected_sha256=artifact.sha256,
        expected_size=artifact.size_bytes,
        description=artifact.id,
    )

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValidationStageError(
            "Unable to read normalization "
            f"manifest {artifact.path}."
        ) from exc

    if not isinstance(payload, dict):
        raise ValidationStageError(
            "Normalization manifest root must "
            "be a JSON object."
        )

    return payload


def _validate_normalization_manifest(
    payload: Mapping[str, Any],
    *,
    context: OrchestrationContext,
) -> None:
    if (
        payload.get("schema_version")
        != _SUPPORTED_NORMALIZATION_SCHEMA_VERSION
    ):
        raise ValidationStageError(
            "Unsupported normalization manifest "
            f"schema: "
            f"{payload.get('schema_version')!r}."
        )

    if (
        payload.get("experiment_id")
        != context.config.id
    ):
        raise ValidationStageError(
            "Normalization manifest experiment_id "
            "does not match the active experiment."
        )

    if payload.get("run_id") != context.run_id:
        raise ValidationStageError(
            "Normalization manifest run_id does "
            "not match the active run."
        )

    cohorts = payload.get("cohorts")

    if not isinstance(cohorts, Mapping):
        raise ValidationStageError(
            "Normalization manifest must contain "
            "a cohorts object."
        )

    expected = {
        simulator.value
        for simulator in SimulatorKind
    }

    if set(cohorts) != expected:
        raise ValidationStageError(
            "Normalization manifest must contain "
            "exactly Synthea and psynthea cohorts."
        )


def _load_normalized_cohort(
    context: OrchestrationContext,
    *,
    simulator: SimulatorKind,
    manifest: Mapping[str, Any],
) -> ValidationCohort:
    cohort_payload = manifest[
        "cohorts"
    ][simulator.value]

    if not isinstance(
        cohort_payload,
        Mapping,
    ):
        raise ValidationStageError(
            f"Invalid normalized cohort payload "
            f"for {simulator.value}."
        )

    expected_source = _EXPECTED_SOURCE[
        simulator
    ]

    if (
        cohort_payload.get("source")
        != expected_source
    ):
        raise ValidationStageError(
            f"Unexpected normalized source for "
            f"{simulator.value}."
        )

    tables_payload = cohort_payload.get(
        "tables"
    )

    if not isinstance(
        tables_payload,
        Mapping,
    ):
        raise ValidationStageError(
            f"Missing normalized table catalogue "
            f"for {simulator.value}."
        )

    tables: dict[
        str,
        pd.DataFrame,
    ] = {}

    for table_name in _TABLE_ORDER:
        table_payload = tables_payload.get(
            table_name
        )

        if not isinstance(
            table_payload,
            Mapping,
        ):
            raise ValidationStageError(
                f"Missing normalized table "
                f"{simulator.value}.{table_name}."
            )

        relative_path = table_payload.get(
            "path"
        )

        if not isinstance(
            relative_path,
            str,
        ):
            raise ValidationStageError(
                f"Missing path for normalized table "
                f"{simulator.value}.{table_name}."
            )

        path = context.workspace.resolve(
            relative_path
        )

        _verify_file_identity(
            path,
            expected_sha256=(
                table_payload.get("sha256")
            ),
            expected_size=(
                table_payload.get("size_bytes")
            ),
            description=(
                f"{simulator.value}.{table_name}"
            ),
        )

        tables[table_name] = _read_csv(
            path,
            simulator=simulator,
            table_name=table_name,
        )

        expected_rows = table_payload.get(
            "rows"
        )

        if (
            isinstance(expected_rows, int)
            and len(tables[table_name])
            != expected_rows
        ):
            raise ValidationStageError(
                "Normalized table row count changed "
                f"for "
                f"{simulator.value}.{table_name}."
            )

    cohort = ValidationCohort(
        source=expected_source,
        output_path=context.workspace.resolve(
            Path("normalized")
            / simulator.value
        ),
        patients=tables["patients"],
        encounters=tables["encounters"],
        conditions=tables["conditions"],
        medications=tables["medications"],
        procedures=tables["procedures"],
        observations=tables["observations"],
    )

    if (
        cohort.patients is None
        or cohort.patients.empty
    ):
        raise ValidationStageError(
            f"Normalized cohort for "
            f"{simulator.value} contains no "
            "patients."
        )

    return cohort


def _read_csv(
    path: Path,
    *,
    simulator: SimulatorKind,
    table_name: str,
) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            dtype="string",
            keep_default_na=True,
            na_values=[""],
        )
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except (
        OSError,
        UnicodeError,
        pd.errors.ParserError,
        ValueError,
    ) as exc:
        raise ValidationStageError(
            "Unable to read normalized table "
            f"{simulator.value}.{table_name}: "
            f"{exc}"
        ) from exc


def _validation_settings(
    metadata: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(metadata, Mapping):
        raise TypeError(
            "experiment metadata must be a mapping."
        )

    raw = metadata.get(
        "validation",
        {},
    )

    if raw is None:
        raw = {}

    if not isinstance(raw, Mapping):
        raise ValidationStageError(
            "metadata.validation must be an object."
        )

    alpha = raw.get(
        "alpha",
        DEFAULT_SIGNIFICANCE_LEVEL,
    )

    if (
        isinstance(alpha, bool)
        or not isinstance(alpha, (int, float))
    ):
        raise ValidationStageError(
            "metadata.validation.alpha must be "
            "numeric."
        )

    alpha = float(alpha)

    if not 0.0 < alpha <= 1.0:
        raise ValidationStageError(
            "metadata.validation.alpha must be "
            "greater than zero and at most one."
        )

    top_n_codes = raw.get(
        "top_n_codes",
        _DEFAULT_TOP_N_CODES,
    )

    if (
        isinstance(top_n_codes, bool)
        or not isinstance(top_n_codes, int)
        or top_n_codes <= 0
    ):
        raise ValidationStageError(
            "metadata.validation.top_n_codes must "
            "be a positive integer."
        )

    modules = raw.get(
        "modules",
        {},
    )

    if modules is None:
        modules = {}

    if not isinstance(modules, Mapping):
        raise ValidationStageError(
            "metadata.validation.modules must be "
            "an object."
        )

    return MappingProxyType(
        {
            "alpha": alpha,
            "top_n_codes": top_n_codes,
            "modules": modules,
        }
    )


def _module_settings(
    settings: Mapping[str, Any],
    module_name: str,
) -> Mapping[str, tuple[str, ...] | None]:
    modules = settings["modules"]

    raw = modules.get(
        module_name,
        {},
    )

    if raw is None:
        raw = {}

    if not isinstance(raw, Mapping):
        raise ValidationStageError(
            "Validation settings for module "
            f"{module_name!r} must be an object."
        )

    return MappingProxyType(
        {
            "expected_condition_terms": (
                _optional_terms(
                    raw.get(
                        "expected_condition_terms"
                    ),
                    (
                        f"{module_name}."
                        "expected_condition_terms"
                    ),
                )
            ),
            "expected_medication_terms": (
                _optional_terms(
                    raw.get(
                        "expected_medication_terms"
                    ),
                    (
                        f"{module_name}."
                        "expected_medication_terms"
                    ),
                )
            ),
            "expected_procedure_terms": (
                _optional_terms(
                    raw.get(
                        "expected_procedure_terms"
                    ),
                    (
                        f"{module_name}."
                        "expected_procedure_terms"
                    ),
                )
            ),
            "expected_observation_terms": (
                _optional_terms(
                    raw.get(
                        "expected_observation_terms"
                    ),
                    (
                        f"{module_name}."
                        "expected_observation_terms"
                    ),
                )
            ),
        }
    )


def _optional_terms(
    value: Any,
    field_name: str,
) -> tuple[str, ...] | None:
    if value is None:
        return None

    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
    ):
        raise ValidationStageError(
            f"{field_name} must be an array of "
            "strings."
        )

    normalized: list[str] = []

    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValidationStageError(
                f"{field_name}[{index}] must be "
                "a string."
            )

        text = item.strip()

        if not text:
            raise ValidationStageError(
                f"{field_name}[{index}] must not "
                "be empty."
            )

        normalized.append(text)

    return tuple(normalized)


def _persist_module_result(
    context: OrchestrationContext,
    *,
    result: ModuleStatisticalComparisonResult,
    generated_at: datetime,
) -> tuple[
    tuple[ArtifactReference, ...],
    Mapping[str, Any],
]:
    module_directory = (
        Path("validation")
        / "modules"
        / result.module_name
    )

    artifacts: list[
        ArtifactReference
    ] = []

    table_payloads: dict[
        str,
        Mapping[str, Any],
    ] = {}

    for output_name, attribute_path in (
        _VALIDATION_TABLES
    ):
        dataframe = _resolve_dataframe(
            result,
            attribute_path,
        )

        relative_path = (
            module_directory
            / f"{output_name}.csv"
        )

        csv_content = dataframe.to_csv(
            index=False,
            lineterminator="\n",
            na_rep="",
        )

        path = context.workspace.write_text(
            relative_path,
            csv_content,
        )

        artifact = (
            context.workspace.artifact_reference(
                artifact_id=(
                    f"{context.config.id}:"
                    f"{context.run_id}:"
                    f"validation:"
                    f"{result.module_name}:"
                    f"{output_name}"
                ),
                kind=ArtifactKind.EVIDENCE,
                path=path,
                media_type="text/csv",
                producer=_VALIDATION_PRODUCER,
                created_at=generated_at,
                metadata={
                    "schema_version": (
                        _VALIDATION_SCHEMA_VERSION
                    ),
                    "module": (
                        result.module_name
                    ),
                    "table": output_name,
                    "rows": len(dataframe),
                    "columns": tuple(
                        str(column)
                        for column
                        in dataframe.columns
                    ),
                },
            )
        )

        artifacts.append(artifact)

        table_payloads[output_name] = {
            "artifact_id": artifact.id,
            "path": artifact.path.as_posix(),
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "rows": len(dataframe),
            "columns": [
                str(column)
                for column
                in dataframe.columns
            ],
        }

    functional_summary = _first_row(
        result.validation.summary
    )

    statistical_summary = _first_row(
        result.summary
    )

    return (
        tuple(artifacts),
        {
            "module_name": result.module_name,
            "functional_summary": (
                functional_summary
            ),
            "statistical_summary": (
                statistical_summary
            ),
            "tables": table_payloads,
        },
    )


def _resolve_dataframe(
    result: ModuleStatisticalComparisonResult,
    path: str,
) -> pd.DataFrame:
    current: Any = result

    for component in path.split("."):
        current = getattr(
            current,
            component,
        )

    if not isinstance(
        current,
        pd.DataFrame,
    ):
        raise ValidationStageError(
            f"Validation result attribute "
            f"{path!r} is not a DataFrame."
        )

    return current


def _first_row(
    dataframe: pd.DataFrame,
) -> dict[str, Any]:
    if dataframe.empty:
        return {}

    row = dataframe.iloc[0].to_dict()

    return {
        str(key): _json_scalar(value)
        for key, value in row.items()
    }


def _aggregate_validation(
    modules: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    comparable_statuses = {
        "comparable",
        "partially_comparable",
    }

    comparable_count = 0
    skipped_count = 0
    significant_count = 0
    significant_after_fdr_count = 0
    blocking_issue_count = 0
    warning_count = 0

    for module in modules:
        functional = module[
            "functional_summary"
        ]
        statistical = module[
            "statistical_summary"
        ]

        status = functional.get("status")

        if status in comparable_statuses:
            comparable_count += 1

        if bool(statistical.get("skipped")):
            skipped_count += 1

        significant_count += _safe_int(
            statistical.get(
                "significant_test_count"
            )
        )

        significant_after_fdr_count += (
            _safe_int(
                statistical.get(
                    "significant_after_fdr_count"
                )
            )
        )

        blocking_issue_count += _safe_int(
            functional.get(
                "blocking_issue_count"
            )
        )

        warning_count += _safe_int(
            functional.get(
                "warning_count"
            )
        )

    return MappingProxyType(
        {
            "module_count": len(modules),
            "comparable_module_count": (
                comparable_count
            ),
            "skipped_module_count": (
                skipped_count
            ),
            "significant_test_count": (
                significant_count
            ),
            "significant_after_fdr_count": (
                significant_after_fdr_count
            ),
            "blocking_issue_count": (
                blocking_issue_count
            ),
            "warning_count": warning_count,
        }
    )


def _safe_int(value: Any) -> int:
    if value is None or pd.isna(value):
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None

    if pd.isna(value):
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return value

    if hasattr(value, "item"):
        scalar = value.item()

        if scalar is value:
            return str(value)

        return _json_scalar(scalar)

    if isinstance(value, str):
        return value

    return str(value)


def _verify_file_identity(
    path: Path,
    *,
    expected_sha256: str | None,
    expected_size: int | None,
    description: str,
) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValidationStageError(
            "Verified normalized artefact is "
            f"missing or unsafe: {description}."
        )

    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ValidationStageError(
            "Unable to read normalized artefact "
            f"{description}: {exc}"
        ) from exc

    actual_size = len(content)

    actual_sha256 = sha256(
        content
    ).hexdigest()

    if (
        expected_size is not None
        and actual_size != expected_size
    ):
        raise ValidationStageError(
            "Normalized artefact size changed: "
            f"{description}."
        )

    if (
        expected_sha256 is not None
        and actual_sha256 != expected_sha256
    ):
        raise ValidationStageError(
            "Normalized artefact hash changed: "
            f"{description}."
        )


def _aware_datetime(
    value: datetime,
    field_name: str,
) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(
            f"{field_name} must be a datetime."
        )

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{field_name} must be "
            "timezone-aware."
        )

    return value.astimezone(UTC)