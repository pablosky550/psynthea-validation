"""
Spanish healthcare-system adaptation validation.

This module evaluates whether a synthetic cohort contains descriptive signals
expected from an adaptation to the Spanish National Health System (SNS):
primary-care activity, referrals, encounter continuity, emergency/inpatient
activity and clinical-event linkage to encounters.

The module is intentionally descriptive. It does not load CSV files, compute
low-level cohort profiles, perform statistical inference, generate plots or
write reports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

from validation.constants import (
    CONDITION_PATIENT_COLUMN,
    ENCOUNTER_CLASS_COLUMN,
    ENCOUNTER_PATIENT_COLUMN,
    MEDICATION_PATIENT_COLUMN,
    OBSERVATION_PATIENT_COLUMN,
    PROCEDURE_PATIENT_COLUMN,
)
from validation.models import ValidationCohort

__all__ = [
    "SpanishAdaptationValidation",
    "SpanishValidationIndicator",
    "validate_spanish_adaptation",
]


# =============================================================================
# Configuration
# =============================================================================

_INDICATOR_COLUMNS = [
    "domain",
    "indicator",
    "value",
    "numerator",
    "denominator",
    "fraction",
    "available",
    "evidence",
]

_PRIMARY_CARE_PATTERNS = [
    "primary",
    "primary care",
    "atencion primaria",
    "atención primaria",
    "centro de salud",
    "general practice",
    "general practitioner",
    "gp",
    "family medicine",
    "medicina familiar",
    "medicina de familia",
    "wellness",
    "ambulatory",
    "outpatient",
]

_REFERRAL_PATTERNS = [
    "referral",
    "refer",
    "referred",
    "derivacion",
    "derivación",
    "derivado",
    "interconsulta",
    "specialist",
    "especialista",
]

_EMERGENCY_PATTERNS = [
    "emergency",
    "urgent",
    "urgency",
    "urgencias",
    "urgente",
    "er",
]

_INPATIENT_PATTERNS = [
    "inpatient",
    "hospital",
    "hospitalization",
    "hospitalisation",
    "admission",
    "ingreso",
    "hospitalario",
]

_TEXT_COLUMNS = [
    "DESCRIPTION",
    "REASONDESCRIPTION",
    "STOP_REASON",
    "TYPE",
    "CLASS",
    "ENCOUNTERCLASS",
]

_ENCOUNTER_REFERENCE_COLUMNS = [
    "ENCOUNTER",
    "ENCOUNTER_ID",
    "ENCOUNTERID",
]


# =============================================================================
# Models
# =============================================================================

@dataclass(slots=True)
class SpanishValidationIndicator:
    """
    One descriptive indicator of Spanish healthcare-system adaptation.
    """

    domain: str
    indicator: str
    value: float | int | str | None

    numerator: int | None = None
    denominator: int | None = None
    fraction: float | None = None

    available: bool = True
    evidence: str | None = None


@dataclass(slots=True)
class SpanishAdaptationValidation:
    """
    Complete descriptive validation of Spanish healthcare-system adaptation.
    """

    cohort: ValidationCohort

    primary_care: pd.DataFrame
    referrals: pd.DataFrame
    healthcare_flow: pd.DataFrame
    clinical_context: pd.DataFrame

    summary: pd.DataFrame


# =============================================================================
# Generic helpers
# =============================================================================

def _empty_indicator_table() -> pd.DataFrame:
    """
    Return an empty indicator table with the canonical schema.
    """

    return pd.DataFrame(columns=_INDICATOR_COLUMNS)


def _indicator_table(
    indicators: list[SpanishValidationIndicator],
) -> pd.DataFrame:
    """
    Convert indicators into a stable DataFrame.
    """

    if not indicators:
        return _empty_indicator_table()

    return pd.DataFrame(
        [
            asdict(indicator)
            for indicator in indicators
        ],
        columns=_INDICATOR_COLUMNS,
    )


def _safe_fraction(
    numerator: int,
    denominator: int,
) -> float | None:
    """
    Return a fraction, preserving missing denominators as None.
    """

    if denominator == 0:
        return None

    return numerator / denominator


def _available_table(
    table: pd.DataFrame | None,
) -> bool:
    """
    Return whether a cohort table is available and non-empty.
    """

    return table is not None and not table.empty


def _normalise_text_series(
    series: pd.Series,
) -> pd.Series:
    """
    Convert a text-like series to lower-case strings for pattern matching.
    """

    return (
        series
        .fillna("")
        .astype(str)
        .str.lower()
    )


def _existing_columns(
    table: pd.DataFrame,
    columns: Iterable[str],
) -> list[str]:
    """
    Return the subset of columns present in a table.
    """

    return [
        column
        for column in columns
        if column in table.columns
    ]


def _contains_any_pattern(
    table: pd.DataFrame,
    columns: Iterable[str],
    patterns: Iterable[str],
) -> pd.Series:
    """
    Return a row-level mask for case-insensitive pattern matches.
    """

    existing_columns = _existing_columns(
        table,
        columns,
    )

    if not existing_columns:
        return pd.Series(
            False,
            index=table.index,
        )

    mask = pd.Series(
        False,
        index=table.index,
    )

    for column in existing_columns:
        values = _normalise_text_series(table[column])

        for pattern in patterns:
            mask = mask | values.str.contains(
                pattern.lower(),
                regex=False,
            )

    return mask


def _patients_with_records(
    table: pd.DataFrame | None,
    patient_column: str,
) -> int:
    """
    Return the number of distinct patients represented in a clinical table.
    """

    if not _available_table(table):
        return 0

    if patient_column not in table.columns:
        return 0

    return int(table[patient_column].nunique())


def _records_with_encounter_reference(
    table: pd.DataFrame | None,
) -> tuple[int, int, str | None]:
    """
    Count records linked to an encounter using the first available reference column.
    """

    if not _available_table(table):
        return 0, 0, None

    reference_columns = _existing_columns(
        table,
        _ENCOUNTER_REFERENCE_COLUMNS,
    )

    if not reference_columns:
        return 0, len(table), None

    reference_column = reference_columns[0]
    linked = int(table[reference_column].notna().sum())

    return linked, len(table), reference_column


def _classified_count(
    table: pd.DataFrame | None,
    columns: Iterable[str],
    patterns: Iterable[str],
) -> int:
    """
    Count records matching a healthcare-flow classification.
    """

    if not _available_table(table):
        return 0

    return int(
        _contains_any_pattern(
            table,
            columns,
            patterns,
        ).sum()
    )


# =============================================================================
# Domain builders
# =============================================================================

def _primary_care_indicators(
    cohort: ValidationCohort,
) -> pd.DataFrame:
    """
    Build indicators describing primary-care representation.
    """

    encounters = cohort.encounters
    available = _available_table(encounters)
    n_encounters = 0 if encounters is None else len(encounters)

    if not available:
        return _indicator_table(
            [
                SpanishValidationIndicator(
                    domain="primary_care",
                    indicator="primary_care_encounters",
                    value=0,
                    numerator=0,
                    denominator=0,
                    fraction=None,
                    available=False,
                    evidence="encounters table is missing or empty",
                )
            ]
        )

    primary_care_count = _classified_count(
        encounters,
        [
            ENCOUNTER_CLASS_COLUMN,
            *_TEXT_COLUMNS,
        ],
        _PRIMARY_CARE_PATTERNS,
    )

    patients_with_primary_care = 0
    if ENCOUNTER_PATIENT_COLUMN in encounters.columns:
        primary_care_mask = _contains_any_pattern(
            encounters,
            [
                ENCOUNTER_CLASS_COLUMN,
                *_TEXT_COLUMNS,
            ],
            _PRIMARY_CARE_PATTERNS,
        )
        patients_with_primary_care = int(
            encounters.loc[
                primary_care_mask,
                ENCOUNTER_PATIENT_COLUMN,
            ].nunique()
        )

    return _indicator_table(
        [
            SpanishValidationIndicator(
                domain="primary_care",
                indicator="primary_care_encounters",
                value=primary_care_count,
                numerator=primary_care_count,
                denominator=n_encounters,
                fraction=_safe_fraction(
                    primary_care_count,
                    n_encounters,
                ),
                evidence="encounter-class/text pattern match",
            ),
            SpanishValidationIndicator(
                domain="primary_care",
                indicator="patients_with_primary_care",
                value=patients_with_primary_care,
                numerator=patients_with_primary_care,
                denominator=cohort.n_patients,
                fraction=_safe_fraction(
                    patients_with_primary_care,
                    cohort.n_patients,
                ),
                evidence="distinct patients with primary-care-like encounters",
            ),
        ]
    )


def _referral_indicators(
    cohort: ValidationCohort,
) -> pd.DataFrame:
    """
    Build indicators describing referral or specialist-transition signals.
    """

    encounters = cohort.encounters
    procedures = cohort.procedures

    referral_encounters = _classified_count(
        encounters,
        [
            ENCOUNTER_CLASS_COLUMN,
            *_TEXT_COLUMNS,
        ],
        _REFERRAL_PATTERNS,
    )
    referral_procedures = _classified_count(
        procedures,
        _TEXT_COLUMNS,
        _REFERRAL_PATTERNS,
    )

    encounter_denominator = 0 if encounters is None else len(encounters)
    procedure_denominator = 0 if procedures is None else len(procedures)

    return _indicator_table(
        [
            SpanishValidationIndicator(
                domain="referrals",
                indicator="referral_like_encounters",
                value=referral_encounters,
                numerator=referral_encounters,
                denominator=encounter_denominator,
                fraction=_safe_fraction(
                    referral_encounters,
                    encounter_denominator,
                ),
                available=_available_table(encounters),
                evidence="encounter-class/text pattern match",
            ),
            SpanishValidationIndicator(
                domain="referrals",
                indicator="referral_like_procedures",
                value=referral_procedures,
                numerator=referral_procedures,
                denominator=procedure_denominator,
                fraction=_safe_fraction(
                    referral_procedures,
                    procedure_denominator,
                ),
                available=_available_table(procedures),
                evidence="procedure text pattern match",
            ),
        ]
    )


def _healthcare_flow_indicators(
    cohort: ValidationCohort,
) -> pd.DataFrame:
    """
    Build indicators describing broad healthcare-utilisation flow.
    """

    encounters = cohort.encounters
    n_encounters = 0 if encounters is None else len(encounters)

    patients_with_encounters = _patients_with_records(
        encounters,
        ENCOUNTER_PATIENT_COLUMN,
    )

    emergency_encounters = _classified_count(
        encounters,
        [
            ENCOUNTER_CLASS_COLUMN,
            *_TEXT_COLUMNS,
        ],
        _EMERGENCY_PATTERNS,
    )
    inpatient_encounters = _classified_count(
        encounters,
        [
            ENCOUNTER_CLASS_COLUMN,
            *_TEXT_COLUMNS,
        ],
        _INPATIENT_PATTERNS,
    )

    return _indicator_table(
        [
            SpanishValidationIndicator(
                domain="healthcare_flow",
                indicator="patients_with_encounters",
                value=patients_with_encounters,
                numerator=patients_with_encounters,
                denominator=cohort.n_patients,
                fraction=_safe_fraction(
                    patients_with_encounters,
                    cohort.n_patients,
                ),
                available=_available_table(encounters),
                evidence="distinct patients in encounters table",
            ),
            SpanishValidationIndicator(
                domain="healthcare_flow",
                indicator="emergency_encounters",
                value=emergency_encounters,
                numerator=emergency_encounters,
                denominator=n_encounters,
                fraction=_safe_fraction(
                    emergency_encounters,
                    n_encounters,
                ),
                available=_available_table(encounters),
                evidence="encounter-class/text pattern match",
            ),
            SpanishValidationIndicator(
                domain="healthcare_flow",
                indicator="inpatient_encounters",
                value=inpatient_encounters,
                numerator=inpatient_encounters,
                denominator=n_encounters,
                fraction=_safe_fraction(
                    inpatient_encounters,
                    n_encounters,
                ),
                available=_available_table(encounters),
                evidence="encounter-class/text pattern match",
            ),
        ]
    )


def _clinical_context_indicators(
    cohort: ValidationCohort,
) -> pd.DataFrame:
    """
    Build indicators checking whether clinical events remain encounter-contextual.
    """

    domain_specs = [
        (
            "conditions_linked_to_encounters",
            cohort.conditions,
            CONDITION_PATIENT_COLUMN,
        ),
        (
            "medications_linked_to_encounters",
            cohort.medications,
            MEDICATION_PATIENT_COLUMN,
        ),
        (
            "procedures_linked_to_encounters",
            cohort.procedures,
            PROCEDURE_PATIENT_COLUMN,
        ),
        (
            "observations_linked_to_encounters",
            cohort.observations,
            OBSERVATION_PATIENT_COLUMN,
        ),
    ]

    indicators: list[SpanishValidationIndicator] = []

    for indicator_name, table, _patient_column in domain_specs:
        linked, denominator, reference_column = _records_with_encounter_reference(
            table,
        )

        indicators.append(
            SpanishValidationIndicator(
                domain="clinical_context",
                indicator=indicator_name,
                value=linked,
                numerator=linked,
                denominator=denominator,
                fraction=_safe_fraction(
                    linked,
                    denominator,
                ),
                available=_available_table(table) and reference_column is not None,
                evidence=(
                    f"encounter reference column: {reference_column}"
                    if reference_column is not None
                    else "no encounter reference column found"
                ),
            )
        )

    return _indicator_table(indicators)


def _build_summary(
    tables: list[pd.DataFrame],
) -> pd.DataFrame:
    """
    Concatenate all available Spanish-adaptation indicator tables.
    """

    available_tables = [
        table
        for table in tables
        if not table.empty
    ]

    if not available_tables:
        return _empty_indicator_table()

    return pd.concat(
        available_tables,
        ignore_index=True,
    )


# =============================================================================
# Public API
# =============================================================================

def validate_spanish_adaptation(
    cohort: ValidationCohort,
) -> SpanishAdaptationValidation:
    """
    Evaluate descriptive Spanish healthcare-system adaptation indicators.

    Parameters
    ----------
    cohort
        Canonical validation cohort generated by psynthea or another compatible
        simulator.

    Returns
    -------
    SpanishAdaptationValidation
    """

    primary_care = _primary_care_indicators(cohort)
    referrals = _referral_indicators(cohort)
    healthcare_flow = _healthcare_flow_indicators(cohort)
    clinical_context = _clinical_context_indicators(cohort)

    return SpanishAdaptationValidation(
        cohort=cohort,
        primary_care=primary_care,
        referrals=referrals,
        healthcare_flow=healthcare_flow,
        clinical_context=clinical_context,
        summary=_build_summary(
            [
                primary_care,
                referrals,
                healthcare_flow,
                clinical_context,
            ]
        ),
    )
