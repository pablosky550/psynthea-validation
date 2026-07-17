"""Production cohort-normalization stage.

This stage transforms the raw simulator cohorts loaded in the previous pipeline
stage into deterministic, schema-aligned datasets suitable for scientific
comparison.

Responsibilities
----------------
* Consume the verified cohort-loading manifest.
* Revalidate raw source artefacts before reading them.
* Load both cohorts through the canonical simulator-specific loaders.
* Normalize identifiers, dates, sex values, codes and column ordering.
* Derive age and age bands from the experiment reference date.
* Validate patient uniqueness and event referential integrity.
* Persist deterministic normalized CSV files.
* Persist one normalization manifest containing provenance and hashes.

The stage deliberately performs no statistical comparison, clinical
interpretation, root-cause attribution or report generation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Final

import pandas as pd

from validation.constants import (
    AGE_BAND_COLUMN,
    AGE_COLUMN,
    CONDITION_CODE_COLUMN,
    CONDITION_DESCRIPTION_COLUMN,
    CONDITION_PATIENT_COLUMN,
    CONDITION_START_COLUMN,
    CONDITION_STOP_COLUMN,
    CSV_FILES,
    ENCOUNTER_CLASS_COLUMN,
    ENCOUNTER_PATIENT_COLUMN,
    MEDICATION_CODE_COLUMN,
    MEDICATION_DESCRIPTION_COLUMN,
    MEDICATION_DISPENSES_COLUMN,
    MEDICATION_PATIENT_COLUMN,
    MEDICATION_START_COLUMN,
    MEDICATION_STOP_COLUMN,
    OBSERVATION_CODE_COLUMN,
    OBSERVATION_DATE_COLUMN,
    OBSERVATION_DESCRIPTION_COLUMN,
    OBSERVATION_PATIENT_COLUMN,
    OBSERVATION_UNITS_COLUMN,
    OBSERVATION_VALUE_COLUMN,
    PATIENT_BIRTHDATE_COLUMN,
    PATIENT_GENDER_COLUMN,
    PATIENT_ID_COLUMN,
    PROCEDURE_BASE_COST_COLUMN,
    PROCEDURE_CODE_COLUMN,
    PROCEDURE_DESCRIPTION_COLUMN,
    PROCEDURE_PATIENT_COLUMN,
    PROCEDURE_START_COLUMN,
    PROCEDURE_STOP_COLUMN,
    SOURCE_PSYNTHEA,
    SOURCE_SYNTHEA,
)
from validation.loaders import load_psynthea, load_synthea
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
from validation.utils import prepare_patients

__all__ = [
    "CohortNormalizationError",
    "CohortNormalizationStageHandler",
    "CohortNormalizer",
    "normalize_validation_cohort",
]


_NORMALIZATION_SCHEMA_VERSION: Final = "1.0"
_SUPPORTED_LOADING_SCHEMA_VERSION: Final = "1.0"

_NORMALIZATION_MANIFEST_PATH: Final = (
    "normalized/cohort_normalization_manifest.json"
)

_NORMALIZATION_PRODUCER: Final = "cohort_normalization_stage"
_LOADING_PRODUCER: Final = "cohort_loading_stage"

_TABLE_ORDER: Final = tuple(CSV_FILES)

_EXPECTED_SOURCE: Final[Mapping[SimulatorKind, str]] = MappingProxyType(
    {
        SimulatorKind.SYNTHEA: SOURCE_SYNTHEA,
        SimulatorKind.PSYNTHEA: SOURCE_PSYNTHEA,
    }
)

_DATE_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "patients": (
            PATIENT_BIRTHDATE_COLUMN,
            "DEATHDATE",
        ),
        "encounters": (
            "START",
            "STOP",
        ),
        "conditions": (
            CONDITION_START_COLUMN,
            CONDITION_STOP_COLUMN,
        ),
        "medications": (
            MEDICATION_START_COLUMN,
            MEDICATION_STOP_COLUMN,
        ),
        "procedures": (
            PROCEDURE_START_COLUMN,
            PROCEDURE_STOP_COLUMN,
        ),
        "observations": (
            OBSERVATION_DATE_COLUMN,
        ),
    }
)

_CODE_COLUMNS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "conditions": CONDITION_CODE_COLUMN,
        "medications": MEDICATION_CODE_COLUMN,
        "procedures": PROCEDURE_CODE_COLUMN,
        "observations": OBSERVATION_CODE_COLUMN,
    }
)

_DESCRIPTION_COLUMNS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "conditions": CONDITION_DESCRIPTION_COLUMN,
        "medications": MEDICATION_DESCRIPTION_COLUMN,
        "procedures": PROCEDURE_DESCRIPTION_COLUMN,
        "observations": OBSERVATION_DESCRIPTION_COLUMN,
    }
)

_PATIENT_REFERENCE_COLUMNS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "encounters": ENCOUNTER_PATIENT_COLUMN,
        "conditions": CONDITION_PATIENT_COLUMN,
        "medications": MEDICATION_PATIENT_COLUMN,
        "procedures": PROCEDURE_PATIENT_COLUMN,
        "observations": OBSERVATION_PATIENT_COLUMN,
    }
)

_NUMERIC_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "medications": (
            MEDICATION_DISPENSES_COLUMN,
        ),
        "procedures": (
            PROCEDURE_BASE_COST_COLUMN,
        ),
    }
)

_CANONICAL_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "patients": (
            PATIENT_ID_COLUMN,
            PATIENT_GENDER_COLUMN,
            PATIENT_BIRTHDATE_COLUMN,
            "DEATHDATE",
            AGE_COLUMN,
            AGE_BAND_COLUMN,
        ),
        "encounters": (
            "Id",
            ENCOUNTER_PATIENT_COLUMN,
            "START",
            "STOP",
            ENCOUNTER_CLASS_COLUMN,
            "CODE",
            "DESCRIPTION",
        ),
        "conditions": (
            CONDITION_PATIENT_COLUMN,
            CONDITION_CODE_COLUMN,
            CONDITION_START_COLUMN,
            CONDITION_STOP_COLUMN,
            CONDITION_DESCRIPTION_COLUMN,
        ),
        "medications": (
            MEDICATION_PATIENT_COLUMN,
            MEDICATION_CODE_COLUMN,
            MEDICATION_START_COLUMN,
            MEDICATION_STOP_COLUMN,
            MEDICATION_DESCRIPTION_COLUMN,
            MEDICATION_DISPENSES_COLUMN,
        ),
        "procedures": (
            PROCEDURE_PATIENT_COLUMN,
            PROCEDURE_CODE_COLUMN,
            PROCEDURE_START_COLUMN,
            PROCEDURE_STOP_COLUMN,
            PROCEDURE_DESCRIPTION_COLUMN,
            PROCEDURE_BASE_COST_COLUMN,
        ),
        "observations": (
            OBSERVATION_PATIENT_COLUMN,
            OBSERVATION_CODE_COLUMN,
            OBSERVATION_DATE_COLUMN,
            OBSERVATION_DESCRIPTION_COLUMN,
            OBSERVATION_VALUE_COLUMN,
            OBSERVATION_UNITS_COLUMN,
        ),
    }
)

_SORT_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "patients": (
            PATIENT_ID_COLUMN,
        ),
        "encounters": (
            ENCOUNTER_PATIENT_COLUMN,
            "START",
            "Id",
        ),
        "conditions": (
            CONDITION_PATIENT_COLUMN,
            CONDITION_START_COLUMN,
            CONDITION_CODE_COLUMN,
        ),
        "medications": (
            MEDICATION_PATIENT_COLUMN,
            MEDICATION_START_COLUMN,
            MEDICATION_CODE_COLUMN,
        ),
        "procedures": (
            PROCEDURE_PATIENT_COLUMN,
            PROCEDURE_START_COLUMN,
            PROCEDURE_CODE_COLUMN,
        ),
        "observations": (
            OBSERVATION_PATIENT_COLUMN,
            OBSERVATION_DATE_COLUMN,
            OBSERVATION_CODE_COLUMN,
        ),
    }
)

CohortLoader = Callable[[str | Path], ValidationCohort]
CohortNormalizer = Callable[[ValidationCohort, date], ValidationCohort]


class CohortNormalizationError(RuntimeError):
    """Raised when a cohort cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class CohortNormalizationStageHandler:
    """Normalize both loaded cohorts into deterministic canonical datasets."""

    loaders: Mapping[SimulatorKind, CohortLoader] = field(
        default_factory=lambda: MappingProxyType(
            {
                SimulatorKind.SYNTHEA: load_synthea,
                SimulatorKind.PSYNTHEA: load_psynthea,
            }
        )
    )
    normalizer: CohortNormalizer | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    stage: ExperimentStage = field(
        default=ExperimentStage.COHORT_NORMALIZATION,
        init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.loaders, Mapping):
            raise TypeError("loaders must be a mapping.")

        expected = frozenset(SimulatorKind)
        provided = frozenset(self.loaders)

        if provided != expected:
            missing = sorted(
                simulator.value
                for simulator in expected - provided
            )
            unexpected = sorted(
                repr(simulator)
                for simulator in provided - expected
            )

            details: list[str] = []

            if missing:
                details.append(
                    "missing=" + ",".join(missing)
                )

            if unexpected:
                details.append(
                    "unexpected=" + ",".join(unexpected)
                )

            suffix = (
                f" ({'; '.join(details)})"
                if details
                else ""
            )

            raise ValueError(
                "loaders must define exactly one loader "
                f"per SimulatorKind{suffix}."
            )

        normalized_loaders: dict[
            SimulatorKind,
            CohortLoader,
        ] = {}

        for simulator, loader in self.loaders.items():
            if not isinstance(simulator, SimulatorKind):
                raise TypeError(
                    "loader mapping keys must be "
                    "SimulatorKind members."
                )

            if not callable(loader):
                raise TypeError(
                    f"loader for {simulator.value} "
                    "must be callable."
                )

            normalized_loaders[simulator] = loader

        normalizer = self.normalizer

        if normalizer is None:
            normalizer = normalize_validation_cohort

        if not callable(normalizer):
            raise TypeError("normalizer must be callable.")

        object.__setattr__(
            self,
            "normalizer",
            normalizer,
        )

        if not callable(self.clock):
            raise TypeError("clock must be callable.")

        object.__setattr__(
            self,
            "loaders",
            MappingProxyType(normalized_loaders),
        )

    def execute(
        self,
        context: OrchestrationContext,
    ) -> StageOutput:
        """Normalize and persist both simulator cohorts."""

        if not isinstance(context, OrchestrationContext):
            raise TypeError(
                "context must be an OrchestrationContext."
            )

        generated_at = _aware_datetime(
            self.clock(),
            "clock result",
        )

        loading_artifact = _loading_manifest_artifact(
            context.artifacts
        )

        loading_manifest = _read_verified_json_artifact(
            context,
            loading_artifact,
        )

        _validate_loading_manifest(
            loading_manifest,
            context=context,
        )

        produced_artifacts: list[ArtifactReference] = []
        cohort_payloads: dict[str, Any] = {}

        reference_date = (
            context.config.cohort.reference_date
        )

        for simulator in SimulatorKind:
            source_payload = loading_manifest[
                "cohorts"
            ][simulator.value]

            _verify_source_tables(
                context,
                simulator=simulator,
                cohort_payload=source_payload,
            )

            raw_output_path = context.workspace.resolve(
                source_payload["output_path"]
            )

            cohort = self.loaders[simulator](
                raw_output_path
            )

            normalizer = self.normalizer

            if normalizer is None:
                raise RuntimeError(
                    "Normalizer was not initialized."
                )

            normalized_cohort = normalizer(
                cohort,
                reference_date,
            )

            _validate_normalized_cohort(
                normalized_cohort,
                simulator=simulator,
            )

            cohort_artifacts, cohort_manifest = (
                _persist_normalized_cohort(
                    context,
                    simulator=simulator,
                    cohort=normalized_cohort,
                    generated_at=generated_at,
                )
            )

            produced_artifacts.extend(
                cohort_artifacts
            )

            cohort_payloads[simulator.value] = (
                cohort_manifest
            )

        manifest_payload = {
            "schema_version": (
                _NORMALIZATION_SCHEMA_VERSION
            ),
            "experiment_id": context.config.id,
            "run_id": context.run_id,
            "generated_at": generated_at.isoformat(),
            "reference_date": (
                reference_date.isoformat()
            ),
            "source_loading_artifact": {
                "artifact_id": loading_artifact.id,
                "path": loading_artifact.path.as_posix(),
                "sha256": loading_artifact.sha256,
                "size_bytes": loading_artifact.size_bytes,
            },
            "cohorts": cohort_payloads,
        }

        manifest_path = context.workspace.write_json(
            _NORMALIZATION_MANIFEST_PATH,
            manifest_payload,
        )

        manifest_artifact = (
            context.workspace.artifact_reference(
                artifact_id=(
                    f"{context.config.id}:"
                    f"{context.run_id}:"
                    "cohort-normalization"
                ),
                kind=(
                    ArtifactKind.COHORT_NORMALIZATION_RESULT
                ),
                path=manifest_path,
                media_type="application/json",
                producer=_NORMALIZATION_PRODUCER,
                created_at=generated_at,
                metadata={
                    "schema_version": (
                        _NORMALIZATION_SCHEMA_VERSION
                    ),
                    "cohort_count": len(
                        cohort_payloads
                    ),
                    "dataset_count": len(
                        produced_artifacts
                    ),
                    "reference_date": (
                        reference_date.isoformat()
                    ),
                },
            )
        )

        all_artifacts = (
            *produced_artifacts,
            manifest_artifact,
        )

        return StageOutput(
            artifacts=all_artifacts,
            summary=(
                "Normalized Synthea and psynthea "
                f"cohorts into {len(produced_artifacts)} "
                "deterministic canonical datasets."
            ),
            metadata={
                "schema_version": (
                    _NORMALIZATION_SCHEMA_VERSION
                ),
                "reference_date": (
                    reference_date.isoformat()
                ),
                "cohort_count": len(
                    cohort_payloads
                ),
                "dataset_count": len(
                    produced_artifacts
                ),
                "patient_counts": {
                    simulator: payload[
                        "summary"
                    ]["patients"]
                    for simulator, payload
                    in cohort_payloads.items()
                },
            },
        )


def normalize_validation_cohort(
    cohort: ValidationCohort,
    reference_date: date,
) -> ValidationCohort:
    """Return a deterministic normalized copy of a validation cohort."""

    if not isinstance(cohort, ValidationCohort):
        raise TypeError(
            "cohort must be a ValidationCohort."
        )

    if (
        isinstance(reference_date, datetime)
        or not isinstance(reference_date, date)
    ):
        raise TypeError(
            "reference_date must be a date."
        )

    if cohort.patients is None:
        raise CohortNormalizationError(
            "The patients table is required."
        )

    normalized_tables: dict[
        str,
        pd.DataFrame,
    ] = {}

    for table_name in _TABLE_ORDER:
        table = getattr(cohort, table_name)

        if table is None:
            table = pd.DataFrame()

        if not isinstance(table, pd.DataFrame):
            raise CohortNormalizationError(
                f"{table_name} must be a pandas "
                "DataFrame."
            )

        normalized_tables[table_name] = (
            _normalize_table(
                table_name,
                table,
                reference_date=reference_date,
            )
        )

    _validate_patient_table(
        normalized_tables["patients"],
        reference_date=reference_date,
    )

    _validate_referential_integrity(
        normalized_tables
    )

    return ValidationCohort(
        source=cohort.source,
        output_path=cohort.output_path,
        patients=normalized_tables["patients"],
        encounters=normalized_tables["encounters"],
        conditions=normalized_tables["conditions"],
        medications=normalized_tables["medications"],
        procedures=normalized_tables["procedures"],
        observations=normalized_tables["observations"],
    )


def _normalize_table(
    table_name: str,
    dataframe: pd.DataFrame,
    *,
    reference_date: date,
) -> pd.DataFrame:
    result = dataframe.copy(deep=True)

    result = _canonicalize_column_names(
        table_name,
        result,
    )

    if result.empty:
        return _ordered_columns(
            table_name,
            result,
        )

    patient_reference = (
        PATIENT_ID_COLUMN
        if table_name == "patients"
        else _PATIENT_REFERENCE_COLUMNS.get(
            table_name
        )
    )

    if patient_reference is not None:
        if patient_reference not in result.columns:
            raise CohortNormalizationError(
                f"{table_name} is missing required "
                f"column {patient_reference!r}."
            )

        result[patient_reference] = (
            _normalize_identifier_series(
                result[patient_reference]
            )
        )

    if table_name == "patients":
        required = (
            PATIENT_ID_COLUMN,
            PATIENT_GENDER_COLUMN,
            PATIENT_BIRTHDATE_COLUMN,
        )

        missing = [
            column
            for column in required
            if column not in result.columns
        ]

        if missing:
            raise CohortNormalizationError(
                "patients is missing required "
                "column(s): "
                + ", ".join(missing)
                + "."
            )

        result[PATIENT_GENDER_COLUMN] = (
            _normalize_gender_series(
                result[PATIENT_GENDER_COLUMN]
            )
        )

    for column in _DATE_COLUMNS.get(
        table_name,
        (),
    ):
        if column in result.columns:
            result[column] = (
                _normalize_date_series(
                    result[column],
                    table_name=table_name,
                    column_name=column,
                )
            )

    code_column = _CODE_COLUMNS.get(
        table_name
    )

    if (
        code_column is not None
        and code_column in result.columns
    ):
        result[code_column] = (
            _normalize_code_series(
                result[code_column]
            )
        )

    description_column = (
        _DESCRIPTION_COLUMNS.get(table_name)
    )

    if (
        description_column is not None
        and description_column in result.columns
    ):
        result[description_column] = (
            _normalize_text_series(
                result[description_column]
            )
        )

    for column in _NUMERIC_COLUMNS.get(
        table_name,
        (),
    ):
        if column in result.columns:
            result[column] = (
                _normalize_numeric_series(
                    result[column],
                    table_name=table_name,
                    column_name=column,
                )
            )

    if table_name == "patients":
        result = prepare_patients(
            result,
            pd.Timestamp(reference_date),
        )

        result[AGE_COLUMN] = pd.to_numeric(
            result[AGE_COLUMN],
            errors="raise",
        ).round(8)

        result[AGE_BAND_COLUMN] = (
            result[AGE_BAND_COLUMN]
            .astype("string")
            .replace("<NA>", pd.NA)
        )

    result = _ordered_columns(
        table_name,
        result,
    )

    result = _stable_sort(
        table_name,
        result,
    )

    return result.reset_index(drop=True)


def _canonicalize_column_names(
    table_name: str,
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    canonical = _CANONICAL_COLUMNS[
        table_name
    ]

    canonical_by_casefold = {
        column.casefold(): column
        for column in canonical
    }

    rename: dict[Any, str] = {}
    seen: set[str] = set()

    for original in dataframe.columns:
        normalized_original = str(
            original
        ).strip()

        if not normalized_original:
            raise CohortNormalizationError(
                f"{table_name} contains an empty "
                "column name."
            )

        target = canonical_by_casefold.get(
            normalized_original.casefold(),
            normalized_original,
        )

        target_key = target.casefold()

        if target_key in seen:
            raise CohortNormalizationError(
                f"{table_name} contains colliding "
                f"columns after normalization: "
                f"{target!r}."
            )

        seen.add(target_key)
        rename[original] = target

    return dataframe.rename(columns=rename)


def _normalize_identifier_series(
    values: pd.Series,
) -> pd.Series:
    result = (
        values.astype("string")
        .str.strip()
        .replace("", pd.NA)
    )

    if result.isna().any():
        raise CohortNormalizationError(
            "Patient identifiers must not be "
            "missing or empty."
        )

    return result


def _normalize_gender_series(
    values: pd.Series,
) -> pd.Series:
    result = (
        values.astype("string")
        .str.strip()
        .str.upper()
    )

    replacements = {
        "MALE": "M",
        "FEMALE": "F",
        "HOMBRE": "M",
        "MUJER": "F",
    }

    return result.replace(replacements)


def _normalize_date_series(
    values: pd.Series,
    *,
    table_name: str,
    column_name: str,
) -> pd.Series:
    original = (
        values.astype("string")
        .str.strip()
    )

    missing = original.isna() | original.eq("")

    parsed = pd.to_datetime(
        original.mask(missing),
        errors="coerce",
        utc=True,
    )

    invalid = ~missing & parsed.isna()

    if invalid.any():
        examples = sorted(
            {
                str(value)
                for value in original[invalid].head(5)
            }
        )

        raise CohortNormalizationError(
            f"{table_name}.{column_name} contains "
            "invalid date value(s): "
            + ", ".join(examples)
            + "."
        )

    return (
        parsed.dt.strftime("%Y-%m-%d")
        .astype("string")
    )


def _normalize_code_series(
    values: pd.Series,
) -> pd.Series:
    result = (
        values.astype("string")
        .str.strip()
        .replace("", pd.NA)
    )

    numeric_float_pattern = re.compile(
        r"^-?\d+\.0+$"
    )

    def remove_artificial_decimal(
        value: Any,
    ) -> Any:
        if pd.isna(value):
            return pd.NA

        text = str(value)

        if numeric_float_pattern.fullmatch(text):
            return text.split(".", 1)[0]

        return text

    return result.map(
        remove_artificial_decimal,
        na_action=None,
    ).astype("string")


def _normalize_text_series(
    values: pd.Series,
) -> pd.Series:
    return (
        values.astype("string")
        .str.strip()
        .replace("", pd.NA)
    )


def _normalize_numeric_series(
    values: pd.Series,
    *,
    table_name: str,
    column_name: str,
) -> pd.Series:
    original = (
        values.astype("string")
        .str.strip()
    )

    missing = original.isna() | original.eq("")

    numeric = pd.to_numeric(
        original.mask(missing),
        errors="coerce",
    )

    invalid = ~missing & numeric.isna()

    if invalid.any():
        examples = sorted(
            {
                str(value)
                for value in original[invalid].head(5)
            }
        )

        raise CohortNormalizationError(
            f"{table_name}.{column_name} contains "
            "invalid numeric value(s): "
            + ", ".join(examples)
            + "."
        )

    return numeric


def _ordered_columns(
    table_name: str,
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    canonical = [
        column
        for column in _CANONICAL_COLUMNS[
            table_name
        ]
        if column in dataframe.columns
    ]

    extras = sorted(
        (
            column
            for column in dataframe.columns
            if column not in canonical
        ),
        key=lambda value: value.casefold(),
    )

    return dataframe.loc[
        :,
        [*canonical, *extras],
    ]


def _stable_sort(
    table_name: str,
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    sort_columns = [
        column
        for column in _SORT_COLUMNS[
            table_name
        ]
        if column in dataframe.columns
    ]

    if not sort_columns or dataframe.empty:
        return dataframe

    return dataframe.sort_values(
        sort_columns,
        kind="mergesort",
        na_position="last",
    )


def _validate_patient_table(
    patients: pd.DataFrame,
    *,
    reference_date: date,
) -> None:
    if patients.empty:
        raise CohortNormalizationError(
            "The normalized patients table "
            "contains zero rows."
        )

    duplicated = patients[
        PATIENT_ID_COLUMN
    ].duplicated(keep=False)

    if duplicated.any():
        duplicates = sorted(
            set(
                patients.loc[
                    duplicated,
                    PATIENT_ID_COLUMN,
                ].astype(str)
            )
        )

        raise CohortNormalizationError(
            "Duplicate patient identifiers found: "
            + ", ".join(duplicates[:10])
            + "."
        )

    birthdates = pd.to_datetime(
        patients[PATIENT_BIRTHDATE_COLUMN],
        errors="coerce",
    )

    future_birthdates = (
        birthdates
        > pd.Timestamp(reference_date)
    )

    if future_birthdates.any():
        raise CohortNormalizationError(
            "Patient birth dates must not occur "
            "after the experiment reference date."
        )

    if patients[AGE_COLUMN].isna().any():
        raise CohortNormalizationError(
            "Patient age could not be derived for "
            "all patients."
        )

    if (patients[AGE_COLUMN] < 0).any():
        raise CohortNormalizationError(
            "Normalized patient age must not be "
            "negative."
        )


def _validate_referential_integrity(
    tables: Mapping[str, pd.DataFrame],
) -> None:
    patients = set(
        tables["patients"][
            PATIENT_ID_COLUMN
        ].astype(str)
    )

    for table_name, patient_column in (
        _PATIENT_REFERENCE_COLUMNS.items()
    ):
        table = tables[table_name]

        if table.empty:
            continue

        references = set(
            table[patient_column]
            .dropna()
            .astype(str)
        )

        unknown = sorted(
            references - patients
        )

        if unknown:
            raise CohortNormalizationError(
                f"{table_name} references unknown "
                "patient identifier(s): "
                + ", ".join(unknown[:10])
                + "."
            )


def _loading_manifest_artifact(
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
            is ArtifactKind.COHORT_LOAD_RESULT
            and artifact.producer
            == _LOADING_PRODUCER
        )
    ]

    if len(candidates) != 1:
        raise CohortNormalizationError(
            "Normalization requires exactly one "
            "cohort-loading result artifact; "
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
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CohortNormalizationError(
            "Unable to read cohort-loading "
            f"manifest {artifact.path}."
        ) from exc

    if not isinstance(payload, dict):
        raise CohortNormalizationError(
            "The cohort-loading manifest root "
            "must be a JSON object."
        )

    return payload


def _validate_loading_manifest(
    payload: Mapping[str, Any],
    *,
    context: OrchestrationContext,
) -> None:
    if (
        payload.get("schema_version")
        != _SUPPORTED_LOADING_SCHEMA_VERSION
    ):
        raise CohortNormalizationError(
            "Unsupported cohort-loading manifest "
            f"schema: {payload.get('schema_version')!r}."
        )

    if payload.get("experiment_id") != context.config.id:
        raise CohortNormalizationError(
            "Cohort-loading manifest experiment_id "
            "does not match the active experiment."
        )

    if payload.get("run_id") != context.run_id:
        raise CohortNormalizationError(
            "Cohort-loading manifest run_id does "
            "not match the active run."
        )

    cohorts = payload.get("cohorts")

    if not isinstance(cohorts, dict):
        raise CohortNormalizationError(
            "Cohort-loading manifest must contain "
            "a cohorts object."
        )

    expected = {
        simulator.value
        for simulator in SimulatorKind
    }

    if set(cohorts) != expected:
        raise CohortNormalizationError(
            "Cohort-loading manifest must contain "
            "exactly the Synthea and psynthea "
            "cohorts."
        )


def _verify_source_tables(
    context: OrchestrationContext,
    *,
    simulator: SimulatorKind,
    cohort_payload: Mapping[str, Any],
) -> None:
    if not isinstance(cohort_payload, Mapping):
        raise CohortNormalizationError(
            f"Invalid loading payload for "
            f"{simulator.value}."
        )

    expected_source = _EXPECTED_SOURCE[
        simulator
    ]

    if cohort_payload.get("source") != expected_source:
        raise CohortNormalizationError(
            f"Unexpected source for "
            f"{simulator.value} cohort."
        )

    output_path = cohort_payload.get(
        "output_path"
    )

    if not isinstance(output_path, str):
        raise CohortNormalizationError(
            f"Missing output_path for "
            f"{simulator.value}."
        )

    output_directory = context.workspace.resolve(
        output_path
    )

    if not output_directory.is_dir():
        raise CohortNormalizationError(
            f"Raw cohort directory no longer "
            f"exists for {simulator.value}: "
            f"{output_directory}"
        )

    tables = cohort_payload.get("tables")

    if not isinstance(tables, Mapping):
        raise CohortNormalizationError(
            f"Missing table provenance for "
            f"{simulator.value}."
        )

    for table_name, table_payload in (
        tables.items()
    ):
        if not isinstance(table_payload, Mapping):
            raise CohortNormalizationError(
                f"Invalid provenance for "
                f"{simulator.value}.{table_name}."
            )

        if not table_payload.get(
            "present",
            False,
        ):
            continue

        relative_path = table_payload.get(
            "path"
        )
        expected_hash = table_payload.get(
            "sha256"
        )
        expected_size = table_payload.get(
            "size_bytes"
        )

        if not isinstance(relative_path, str):
            raise CohortNormalizationError(
                f"Missing path for "
                f"{simulator.value}.{table_name}."
            )

        source_path = context.workspace.resolve(
            relative_path
        )

        _verify_file_identity(
            source_path,
            expected_sha256=expected_hash,
            expected_size=expected_size,
            description=(
                f"{simulator.value}.{table_name}"
            ),
        )


def _verify_file_identity(
    path: Path,
    *,
    expected_sha256: str | None,
    expected_size: int | None,
    description: str,
) -> None:
    if not path.is_file() or path.is_symlink():
        raise CohortNormalizationError(
            f"Verified source artefact is missing "
            f"or unsafe: {description}."
        )

    content = path.read_bytes()
    actual_size = len(content)
    actual_sha256 = sha256(
        content
    ).hexdigest()

    if (
        expected_size is not None
        and actual_size != expected_size
    ):
        raise CohortNormalizationError(
            f"Source artefact size changed after "
            f"loading: {description}."
        )

    if (
        expected_sha256 is not None
        and actual_sha256 != expected_sha256
    ):
        raise CohortNormalizationError(
            f"Source artefact hash changed after "
            f"loading: {description}."
        )


def _validate_normalized_cohort(
    cohort: ValidationCohort,
    *,
    simulator: SimulatorKind,
) -> None:
    if not isinstance(cohort, ValidationCohort):
        raise CohortNormalizationError(
            f"Normalizer for {simulator.value} "
            "did not return a ValidationCohort."
        )

    if (
        cohort.source
        != _EXPECTED_SOURCE[simulator]
    ):
        raise CohortNormalizationError(
            f"Normalized source mismatch for "
            f"{simulator.value}."
        )

    if (
        cohort.patients is None
        or cohort.patients.empty
    ):
        raise CohortNormalizationError(
            f"Normalized cohort for "
            f"{simulator.value} contains no "
            "patients."
        )

    required_patient_columns = {
        PATIENT_ID_COLUMN,
        PATIENT_GENDER_COLUMN,
        PATIENT_BIRTHDATE_COLUMN,
        AGE_COLUMN,
        AGE_BAND_COLUMN,
    }

    missing = sorted(
        required_patient_columns
        - set(cohort.patients.columns)
    )

    if missing:
        raise CohortNormalizationError(
            f"Normalized patients table for "
            f"{simulator.value} is missing: "
            + ", ".join(missing)
            + "."
        )


def _persist_normalized_cohort(
    context: OrchestrationContext,
    *,
    simulator: SimulatorKind,
    cohort: ValidationCohort,
    generated_at: datetime,
) -> tuple[
    tuple[ArtifactReference, ...],
    Mapping[str, Any],
]:
    artifacts: list[ArtifactReference] = []
    table_payloads: dict[str, Any] = {}

    for table_name in _TABLE_ORDER:
        dataframe = getattr(
            cohort,
            table_name,
        )

        if dataframe is None:
            dataframe = pd.DataFrame()

        relative_path = Path(
            "normalized"
        ) / simulator.value / CSV_FILES[
            table_name
        ]

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
                    f"{simulator.value}:"
                    f"normalized:{table_name}"
                ),
                kind=(
                    ArtifactKind.NORMALIZED_DATASET
                ),
                path=path,
                media_type="text/csv",
                producer=_NORMALIZATION_PRODUCER,
                created_at=generated_at,
                metadata={
                    "schema_version": (
                        _NORMALIZATION_SCHEMA_VERSION
                    ),
                    "simulator": simulator.value,
                    "source": cohort.source,
                    "table": table_name,
                    "rows": int(
                        len(dataframe)
                    ),
                    "columns": tuple(
                        str(column)
                        for column
                        in dataframe.columns
                    ),
                },
            )
        )

        artifacts.append(artifact)

        table_payloads[table_name] = {
            "artifact_id": artifact.id,
            "path": artifact.path.as_posix(),
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "rows": int(len(dataframe)),
            "columns": [
                str(column)
                for column in dataframe.columns
            ],
        }

    return (
        tuple(artifacts),
        {
            "simulator": simulator.value,
            "source": cohort.source,
            "summary": {
                key: (
                    int(value)
                    if isinstance(value, int)
                    else value
                )
                for key, value
                in cohort.summary.items()
            },
            "tables": table_payloads,
        },
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