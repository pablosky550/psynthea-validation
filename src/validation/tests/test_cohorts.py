"""
Temporal cohort definition tests.

These tests validate the epidemiological selection rules implemented in
``validation.metrics.cohorts`` independently from descriptive metric
calculation. The scenarios intentionally exercise inclusive boundaries,
open-ended conditions, patient eligibility, disease-specific incidence
populations and input immutability.
"""

from __future__ import annotations

import pandas as pd
import pandas.testing as pdt
import pytest

from validation.constants import (
    CONDITION_CODE_COLUMN,
    CONDITION_DESCRIPTION_COLUMN,
    CONDITION_PATIENT_COLUMN,
    CONDITION_START_COLUMN,
    CONDITION_STOP_COLUMN,
    PATIENT_BIRTHDATE_COLUMN,
    PATIENT_ID_COLUMN,
    SOURCE_PSYNTHEA,
)
from validation.metrics.cohorts import (
    ObservationWindow,
    TemporalConditionCohorts,
    build_temporal_condition_cohorts,
    calculate_at_risk_patient_ids_by_condition,
    select_eligible_patient_ids,
    select_incident_conditions,
    select_prevalent_conditions,
)
from validation.models import ValidationCohort


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def observation_window() -> ObservationWindow:
    """Return the deterministic closed interval used by temporal tests."""

    return ObservationWindow(
        start="2020-01-01",
        end="2020-12-31",
    )


@pytest.fixture
def temporal_patients() -> pd.DataFrame:
    """Patients covering eligibility, birth and mortality boundaries."""

    return pd.DataFrame(
        [
            {
                PATIENT_ID_COLUMN: "P1",
                PATIENT_BIRTHDATE_COLUMN: "1980-01-01",
                "DEATHDATE": pd.NA,
            },
            {
                PATIENT_ID_COLUMN: "P2",
                PATIENT_BIRTHDATE_COLUMN: "1990-01-01",
                "DEATHDATE": "2020-01-01",
            },
            {
                PATIENT_ID_COLUMN: "P3",
                PATIENT_BIRTHDATE_COLUMN: "2000-01-01",
                "DEATHDATE": "2019-12-31",
            },
            {
                PATIENT_ID_COLUMN: "P4",
                PATIENT_BIRTHDATE_COLUMN: "2020-12-31",
                "DEATHDATE": pd.NA,
            },
            {
                PATIENT_ID_COLUMN: "P5",
                PATIENT_BIRTHDATE_COLUMN: "2021-01-01",
                "DEATHDATE": pd.NA,
            },
            {
                PATIENT_ID_COLUMN: "P6",
                PATIENT_BIRTHDATE_COLUMN: "not-a-date",
                "DEATHDATE": pd.NA,
            },
            {
                PATIENT_ID_COLUMN: pd.NA,
                PATIENT_BIRTHDATE_COLUMN: "1985-01-01",
                "DEATHDATE": pd.NA,
            },
        ]
    )


@pytest.fixture
def temporal_conditions() -> pd.DataFrame:
    """Condition episodes spanning historical, incident and future states."""

    return pd.DataFrame(
        [
            {
                "ROW_ID": "historical-open",
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: "HTN",
                CONDITION_DESCRIPTION_COLUMN: "Hypertension",
                CONDITION_START_COLUMN: "2018-01-01",
                CONDITION_STOP_COLUMN: pd.NA,
            },
            {
                "ROW_ID": "historical-resolved-before",
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: "ASTHMA",
                CONDITION_DESCRIPTION_COLUMN: "Asthma",
                CONDITION_START_COLUMN: "2018-01-01",
                CONDITION_STOP_COLUMN: "2019-12-31",
            },
            {
                "ROW_ID": "starts-at-window-start",
                CONDITION_PATIENT_COLUMN: "P2",
                CONDITION_CODE_COLUMN: "HTN",
                CONDITION_DESCRIPTION_COLUMN: "Hypertension",
                CONDITION_START_COLUMN: "2020-01-01",
                CONDITION_STOP_COLUMN: "2020-02-01",
            },
            {
                "ROW_ID": "inside-window-open",
                CONDITION_PATIENT_COLUMN: "P4",
                CONDITION_CODE_COLUMN: "DIABETES",
                CONDITION_DESCRIPTION_COLUMN: "Diabetes mellitus",
                CONDITION_START_COLUMN: "2020-06-15",
                CONDITION_STOP_COLUMN: pd.NA,
            },
            {
                "ROW_ID": "starts-at-window-end",
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: "COPD",
                CONDITION_DESCRIPTION_COLUMN: "COPD",
                CONDITION_START_COLUMN: "2020-12-31",
                CONDITION_STOP_COLUMN: pd.NA,
            },
            {
                "ROW_ID": "future-condition",
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: "FUTURE",
                CONDITION_DESCRIPTION_COLUMN: "Future condition",
                CONDITION_START_COLUMN: "2021-01-01",
                CONDITION_STOP_COLUMN: pd.NA,
            },
            {
                "ROW_ID": "ineligible-deceased",
                CONDITION_PATIENT_COLUMN: "P3",
                CONDITION_CODE_COLUMN: "HTN",
                CONDITION_DESCRIPTION_COLUMN: "Hypertension",
                CONDITION_START_COLUMN: "2019-01-01",
                CONDITION_STOP_COLUMN: pd.NA,
            },
            {
                "ROW_ID": "ineligible-not-born",
                CONDITION_PATIENT_COLUMN: "P5",
                CONDITION_CODE_COLUMN: "DIABETES",
                CONDITION_DESCRIPTION_COLUMN: "Diabetes mellitus",
                CONDITION_START_COLUMN: "2020-07-01",
                CONDITION_STOP_COLUMN: pd.NA,
            },
            {
                "ROW_ID": "unknown-patient",
                CONDITION_PATIENT_COLUMN: "PX",
                CONDITION_CODE_COLUMN: "HTN",
                CONDITION_DESCRIPTION_COLUMN: "Hypertension",
                CONDITION_START_COLUMN: "2020-08-01",
                CONDITION_STOP_COLUMN: pd.NA,
            },
            {
                "ROW_ID": "missing-start",
                CONDITION_PATIENT_COLUMN: "P1",
                CONDITION_CODE_COLUMN: "UNKNOWN",
                CONDITION_DESCRIPTION_COLUMN: "Unknown onset",
                CONDITION_START_COLUMN: pd.NA,
                CONDITION_STOP_COLUMN: pd.NA,
            },
        ]
    )


@pytest.fixture
def temporal_cohort(
    temporal_patients: pd.DataFrame,
    temporal_conditions: pd.DataFrame,
) -> ValidationCohort:
    """Build a deterministic cohort dedicated to temporal selection tests."""

    return ValidationCohort(
        source=SOURCE_PSYNTHEA,
        patients=temporal_patients,
        conditions=temporal_conditions,
    )


# =============================================================================
# Observation window
# =============================================================================

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2020-01-01", True),
        ("2020-06-01", True),
        ("2020-12-31", True),
        ("2019-12-31", False),
        ("2021-01-01", False),
        (pd.NA, False),
        ("invalid", False),
    ],
)
def test_observation_window_contains_closed_boundaries(
    observation_window: ObservationWindow,
    value: object,
    expected: bool,
) -> None:
    """The observation interval includes both temporal boundaries."""

    result = observation_window.contains(pd.Series([value]))

    assert bool(result.iloc[0]) is expected


def test_observation_window_normalises_timezone_aware_values() -> None:
    """Equivalent timezone-aware values produce deterministic UTC bounds."""

    window = ObservationWindow(
        start="2020-01-01T01:00:00+01:00",
        end="2020-12-31T01:00:00+01:00",
    )

    assert window.start == pd.Timestamp("2020-01-01T00:00:00")
    assert window.end == pd.Timestamp("2020-12-31T00:00:00")
    assert window.start.tzinfo is None
    assert window.end.tzinfo is None


@pytest.mark.parametrize("field", ["start", "end"])
def test_observation_window_rejects_invalid_boundaries(field: str) -> None:
    """Invalid boundaries fail early with a field-specific error."""

    values = {
        "start": "2020-01-01",
        "end": "2020-12-31",
    }
    values[field] = "not-a-date"

    with pytest.raises(
        ValueError,
        match=rf"Observation window {field} must be a valid timestamp",
    ):
        ObservationWindow(**values)


def test_observation_window_rejects_inverted_interval() -> None:
    """A negative observation interval is never accepted silently."""

    with pytest.raises(
        ValueError,
        match="start must be earlier than or equal to end",
    ):
        ObservationWindow(
            start="2020-12-31",
            end="2020-01-01",
        )


def test_observation_window_overlap_handles_open_and_closed_events(
    observation_window: ObservationWindow,
) -> None:
    """Overlap follows interval algebra and treats missing stops as open."""

    starts = pd.Series(
        [
            "2019-01-01",
            "2019-01-01",
            "2020-01-01",
            "2020-12-31",
            "2021-01-01",
            pd.NA,
        ]
    )
    stops = pd.Series(
        [
            "2019-12-31",
            pd.NA,
            "2020-01-01",
            "2020-12-31",
            pd.NA,
            pd.NA,
        ]
    )

    result = observation_window.overlaps(starts, stops)

    assert result.tolist() == [False, True, True, True, False, False]


# =============================================================================
# Patient eligibility
# =============================================================================


def test_select_eligible_patient_ids_applies_birth_and_death_boundaries(
    temporal_cohort: ValidationCohort,
    observation_window: ObservationWindow,
) -> None:
    """Eligibility includes observable boundary cases and excludes invalid ones."""

    eligible = select_eligible_patient_ids(
        temporal_cohort,
        observation_window,
    )

    assert eligible == frozenset({"P1", "P2", "P4"})


def test_select_eligible_patient_ids_supports_patient_table_without_birthdate(
    observation_window: ObservationWindow,
) -> None:
    """Birth date is optional, while patient identity remains mandatory."""

    cohort = ValidationCohort(
        source=SOURCE_PSYNTHEA,
        patients=pd.DataFrame(
            [
                {PATIENT_ID_COLUMN: "P1"},
                {PATIENT_ID_COLUMN: "P2"},
                {PATIENT_ID_COLUMN: pd.NA},
            ]
        ),
    )

    assert select_eligible_patient_ids(cohort, observation_window) == frozenset(
        {"P1", "P2"}
    )


@pytest.mark.parametrize("patients", [None, pd.DataFrame()])
def test_select_eligible_patient_ids_handles_absent_patient_data(
    observation_window: ObservationWindow,
    patients: pd.DataFrame | None,
) -> None:
    """Absent patient data yields an explicit empty denominator."""

    cohort = ValidationCohort(
        source=SOURCE_PSYNTHEA,
        patients=patients,
    )

    assert select_eligible_patient_ids(cohort, observation_window) == frozenset()


def test_select_eligible_patient_ids_requires_patient_identifier(
    observation_window: ObservationWindow,
) -> None:
    """Malformed canonical patient tables fail with a precise schema error."""

    cohort = ValidationCohort(
        source=SOURCE_PSYNTHEA,
        patients=pd.DataFrame({PATIENT_BIRTHDATE_COLUMN: ["1980-01-01"]}),
    )

    with pytest.raises(
        ValueError,
        match=r"patients table is missing required column\(s\): Id",
    ):
        select_eligible_patient_ids(cohort, observation_window)


# =============================================================================
# Prevalent and incident conditions
# =============================================================================


def test_select_prevalent_conditions_uses_window_overlap_and_eligibility(
    temporal_cohort: ValidationCohort,
    observation_window: ObservationWindow,
) -> None:
    """Prevalence includes every eligible episode overlapping the window."""

    result = select_prevalent_conditions(
        temporal_cohort,
        observation_window,
    )

    assert result["ROW_ID"].tolist() == [
        "historical-open",
        "starts-at-window-start",
        "inside-window-open",
        "starts-at-window-end",
    ]


def test_select_incident_conditions_uses_closed_onset_window_and_eligibility(
    temporal_cohort: ValidationCohort,
    observation_window: ObservationWindow,
) -> None:
    """Incidence includes eligible onsets at either closed boundary."""

    result = select_incident_conditions(
        temporal_cohort,
        observation_window,
    )

    assert result["ROW_ID"].tolist() == [
        "starts-at-window-start",
        "inside-window-open",
        "starts-at-window-end",
    ]


@pytest.mark.parametrize(
    "selector",
    [select_prevalent_conditions, select_incident_conditions],
)
def test_condition_selectors_preserve_empty_condition_schema(
    observation_window: ObservationWindow,
    selector: object,
) -> None:
    """Empty condition inputs return independent schema-preserving frames."""

    empty_conditions = pd.DataFrame(
        columns=[
            CONDITION_PATIENT_COLUMN,
            CONDITION_CODE_COLUMN,
            CONDITION_START_COLUMN,
            CONDITION_STOP_COLUMN,
        ]
    )
    cohort = ValidationCohort(
        source=SOURCE_PSYNTHEA,
        patients=pd.DataFrame([{PATIENT_ID_COLUMN: "P1"}]),
        conditions=empty_conditions,
    )

    result = selector(cohort, observation_window)

    assert result.empty
    assert result.columns.tolist() == empty_conditions.columns.tolist()
    assert result is not empty_conditions


@pytest.mark.parametrize(
    ("selector", "conditions", "missing_column"),
    [
        (
            select_prevalent_conditions,
            pd.DataFrame(
                {
                    CONDITION_PATIENT_COLUMN: ["P1"],
                    CONDITION_START_COLUMN: ["2020-01-01"],
                }
            ),
            CONDITION_STOP_COLUMN,
        ),
        (
            select_incident_conditions,
            pd.DataFrame(
                {CONDITION_PATIENT_COLUMN: ["P1"]}
            ),
            CONDITION_START_COLUMN,
        ),
    ],
)
def test_condition_selectors_require_temporal_schema(
    observation_window: ObservationWindow,
    selector: object,
    conditions: pd.DataFrame,
    missing_column: str,
) -> None:
    """Each selector validates exactly the canonical columns it requires."""

    cohort = ValidationCohort(
        source=SOURCE_PSYNTHEA,
        patients=pd.DataFrame([{PATIENT_ID_COLUMN: "P1"}]),
        conditions=conditions,
    )

    with pytest.raises(
        ValueError,
        match=rf"conditions table is missing required column\(s\): {missing_column}",
    ):
        selector(cohort, observation_window)


# =============================================================================
# At-risk denominators and aggregate model
# =============================================================================


def test_calculate_at_risk_patient_ids_by_condition_excludes_prior_disease(
    temporal_cohort: ValidationCohort,
    observation_window: ObservationWindow,
) -> None:
    """Disease-specific denominators exclude documented pre-window onsets."""

    result = calculate_at_risk_patient_ids_by_condition(
        temporal_cohort,
        observation_window,
    )

    assert result == {
        "ASTHMA": frozenset({"P2", "P4"}),
        "COPD": frozenset({"P1", "P2", "P4"}),
        "DIABETES": frozenset({"P1", "P2", "P4"}),
        "HTN": frozenset({"P2", "P4"}),
    }


def test_at_risk_denominator_ignores_future_and_missing_onsets(
    temporal_cohort: ValidationCohort,
    observation_window: ObservationWindow,
) -> None:
    """Unobservable future or unknown onsets cannot define baseline risk sets."""

    result = calculate_at_risk_patient_ids_by_condition(
        temporal_cohort,
        observation_window,
    )

    assert "FUTURE" not in result
    assert "UNKNOWN" not in result


def test_build_temporal_condition_cohorts_composes_consistent_outputs(
    temporal_cohort: ValidationCohort,
    observation_window: ObservationWindow,
) -> None:
    """The aggregate model exposes mutually consistent cohort components."""

    result = build_temporal_condition_cohorts(
        temporal_cohort,
        observation_window,
    )

    assert isinstance(result, TemporalConditionCohorts)
    assert result.window is observation_window

    assert result.eligible_patient_ids == frozenset({"P1", "P2", "P4"})
    assert result.prevalent_patient_ids == frozenset({"P1", "P2", "P4"})
    assert result.incident_patient_ids == frozenset({"P1", "P2", "P4"})

    assert result.n_eligible_patients == 3
    assert result.n_prevalent_patients == 3
    assert result.n_incident_patients == 3

    assert len(result.prevalent_conditions) == 4
    assert len(result.incident_conditions) == 3
    assert result.incident_patient_ids.issubset(result.prevalent_patient_ids)


def test_temporal_cohort_construction_does_not_mutate_source_tables(
    temporal_cohort: ValidationCohort,
    observation_window: ObservationWindow,
) -> None:
    """Cohort derivation is side-effect free for reproducible validation runs."""

    original_patients = temporal_cohort.patients.copy(deep=True)
    original_conditions = temporal_cohort.conditions.copy(deep=True)

    result = build_temporal_condition_cohorts(
        temporal_cohort,
        observation_window,
    )

    pdt.assert_frame_equal(temporal_cohort.patients, original_patients)
    pdt.assert_frame_equal(temporal_cohort.conditions, original_conditions)

    result.prevalent_conditions.loc[:, CONDITION_CODE_COLUMN] = "MUTATED"
    pdt.assert_frame_equal(temporal_cohort.conditions, original_conditions)