from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from validation.comparison.module_validation import ModuleValidationResult
from validation.comparison.statistical_comparison import ModuleStatisticalComparisonResult
from validation.interpretation.evidence import (
    DuplicateEvidenceError,
    EvidenceCatalog,
    EvidenceExtractionError,
    FrameExtractionSpec,
    collect_evidence,
    extract_dataframe_cell,
    extract_dataframe_rows,
    extract_scalar,
    normalize_scalar,
)
from validation.interpretation.models import EvidenceAvailability
from validation.models import ValidationCohort


def _cohort(source: str) -> ValidationCohort:
    return ValidationCohort(source=source, patients=pd.DataFrame([{"Id": "p1"}]))


def _functional_result() -> ModuleValidationResult:
    return ModuleValidationResult(
        module_name="hypertension",
        synthea_cohort=_cohort("synthea"),
        psynthea_cohort=_cohort("psynthea"),
        table_status=pd.DataFrame(
            [{
                "module_name": "hypertension",
                "table": "observations",
                "synthea_available": True,
                "psynthea_available": True,
                "synthea_rows": 10,
                "psynthea_rows": 0,
                "synthea_empty": False,
                "psynthea_empty": True,
                "row_difference": -10,
                "relative_row_difference": -1.0,
                "required": False,
                "blocking_issue": False,
            }]
        ),
        clinical_signal=pd.DataFrame(),
        distributional_similarity=pd.DataFrame(),
        issues=pd.DataFrame(),
        summary=pd.DataFrame(
            [{
                "module_name": "hypertension",
                "status": "warning",
                "status_reason": "Output differs",
                "synthea_functional": True,
                "psynthea_functional": True,
                "valid_for_comparison": True,
                "blocking_issue_count": 0,
                "warning_count": 1,
                "synthea_condition_count": 10,
                "psynthea_condition_count": 12,
                "synthea_observation_count": 10,
                "psynthea_observation_count": 0,
                "mean_distributional_similarity": 0.8,
                "mean_jensen_shannon_divergence": 0.1,
            }]
        ),
    )


def test_zero_is_available_evidence() -> None:
    evidence = extract_scalar(0, metric_id="count.zero", name="Zero count")
    assert evidence.availability is EvidenceAvailability.AVAILABLE
    assert evidence.value == 0
    assert evidence.is_zero


def test_missing_and_non_finite_values_are_not_zero() -> None:
    assert normalize_scalar(None).availability is EvidenceAvailability.NOT_COMPUTED
    assert normalize_scalar(np.nan).availability is EvidenceAvailability.NOT_COMPUTED
    assert normalize_scalar(np.inf).availability is EvidenceAvailability.INVALID


def test_dataframe_states_are_distinct() -> None:
    missing = extract_dataframe_cell(None, column="value", metric_id="x.missing", name="Missing")
    empty = extract_dataframe_cell(
        pd.DataFrame(columns=["value"]), column="value", metric_id="x.empty", name="Empty"
    )
    field_missing = extract_dataframe_cell(
        pd.DataFrame([{"other": 1}]), column="value", metric_id="x.field", name="Field"
    )
    assert missing.availability is EvidenceAvailability.SOURCE_MISSING
    assert empty.availability is EvidenceAvailability.EMPTY
    assert field_missing.availability is EvidenceAvailability.FIELD_MISSING


def test_callable_selector_must_be_index_aligned() -> None:
    frame = pd.DataFrame([{"value": 1}, {"value": 2}], index=[10, 20])
    with pytest.raises(EvidenceExtractionError, match="index-aligned"):
        extract_dataframe_cell(
            frame,
            column="value",
            metric_id="selector.misaligned",
            name="Misaligned selector",
            row=lambda _: pd.Series([True, False]),
        )


def test_invalid_selector_can_fail_loudly_or_degrade() -> None:
    frame = pd.DataFrame([{"value": 1}])
    with pytest.raises(EvidenceExtractionError):
        extract_dataframe_cell(
            frame, column="value", metric_id="selector.strict", name="Strict", row=5
        )

    evidence = extract_dataframe_cell(
        frame,
        column="value",
        metric_id="selector.permissive",
        name="Permissive",
        row=5,
        strict=False,
    )
    assert evidence.availability is EvidenceAvailability.INVALID


def test_row_extraction_has_stable_ids_and_provenance() -> None:
    frame = pd.DataFrame(
        [
            {"domain": "conditions", "code": "A 1", "p_value": 0.01},
            {"domain": "conditions", "code": "B/2", "p_value": 0.20},
        ]
    )
    values = extract_dataframe_rows(
        frame,
        spec=FrameExtractionSpec(
            namespace="stats.prevalence",
            identity_columns=("domain", "code"),
            name_columns=("domain", "code"),
            value_columns=("p_value",),
        ),
    )
    assert [value.metric_id for value in values] == [
        "stats.prevalence.conditions.A-1.p_value",
        "stats.prevalence.conditions.B-2.p_value",
    ]
    assert values[0].metadata["column"] == "p_value"
    assert values[0].metadata["row_position"] == 0


def test_duplicate_row_identity_fails_in_strict_mode() -> None:
    frame = pd.DataFrame(
        [
            {"domain": "conditions", "code": "A", "p_value": 0.01},
            {"domain": "conditions", "code": "A", "p_value": 0.02},
        ]
    )
    with pytest.raises(EvidenceExtractionError, match="Duplicate row identity"):
        extract_dataframe_rows(
            frame,
            spec=FrameExtractionSpec(
                namespace="stats.prevalence",
                identity_columns=("domain", "code"),
                value_columns=("p_value",),
            ),
        )


def test_catalog_rejects_duplicates() -> None:
    evidence = extract_scalar(1, metric_id="duplicate.metric", name="Metric")
    with pytest.raises(DuplicateEvidenceError):
        EvidenceCatalog((evidence, evidence))


def test_functional_adapter_matches_current_summary_schema() -> None:
    catalog = collect_evidence(_functional_result())
    assert catalog.require("hypertension.functional.summary.hypertension.status").value == "warning"
    assert catalog.require(
        "hypertension.functional.summary.hypertension.psynthea_observation_count"
    ).value == 0


def test_current_statistical_result_adapter_uses_real_result_type() -> None:
    validation = _functional_result()
    result = ModuleStatisticalComparisonResult(
        module_name="hypertension",
        validation=validation,
        continuous_tests=pd.DataFrame(
            [{
                "module_name": "hypertension",
                "scope": "continuous",
                "metric": "age",
                "test_name": "ks",
                "statistic": 0.1,
                "p_value": 0.5,
                "effect_size": 0.02,
                "significant": False,
                "n_synthea": 100,
                "n_psynthea": 100,
                "notes": None,
            }]
        ),
        categorical_tests=pd.DataFrame(),
        prevalence_tests=pd.DataFrame(),
        distribution_tests=pd.DataFrame(),
        summary=pd.DataFrame(
            [{
                "module_name": "hypertension",
                "validation_status": "valid",
                "valid_for_statistical_comparison": True,
                "skipped": False,
                "skip_reason": None,
                "continuous_test_count": 1,
                "categorical_test_count": 0,
                "prevalence_test_count": 0,
                "distribution_test_count": 0,
                "significant_test_count": 0,
                "significant_after_fdr_count": 0,
                "mean_jensen_shannon_divergence": None,
            }]
        ),
    )

    catalog = collect_evidence(result)
    assert catalog.require("hypertension.statistics.continuous.age.ks.p_value").value == 0.5
    assert any(value.availability is EvidenceAvailability.EMPTY for value in catalog)


def test_same_class_name_from_unrelated_type_is_not_accepted() -> None:
    unrelated = type("ModuleStatisticalComparisonResult", (), {})()
    with pytest.raises(EvidenceExtractionError, match="No evidence adapter"):
        collect_evidence(unrelated)