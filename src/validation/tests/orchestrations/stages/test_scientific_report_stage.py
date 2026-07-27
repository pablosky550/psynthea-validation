from __future__ import annotations

from validation.orchestration.stages.report import (
    _age_range_label,
    _module_scope_label,
    _module_selection_details,
    _render_html,
    _statistical_evidence_v13,
)


def _minimal_payload(*, modules: list[str]) -> dict[str, object]:
    return {
        "experiment_id": "multi-module-equivalence",
        "experiment_name": "Multi-module equivalence",
        "decision": "PASS",
        "cohort": {
            "population_size": 100,
            "seed": 7,
            "modules": modules,
            "module_count": len(modules),
            "module_selection": "single_module" if len(modules) == 1 else "explicit_multi_module",
            "reference_date": "2026-06-30",
            "min_age": 18,
            "max_age": 90,
        },
        "executive_summary": {
            "validation": {
                "module_count": len(modules),
                "comparable_module_count": len(modules),
                "significant_after_fdr_count": 0,
            },
            "root_cause": {},
        },
        "scientific_results": {
            "validation": {
                "aggregate": {
                    "module_count": len(modules),
                    "comparable_module_count": len(modules),
                    "significant_test_count": 0,
                    "significant_after_fdr_count": 0,
                    "warning_count": 0,
                },
                "modules": [],
            },
            "knowledge": {"modules": []},
            "root_cause": {},
        },
        "scientific_analysis": {},
        "source_artifacts": {},
        "stage_summary": [],
    }


def test_module_scope_label_keeps_single_module_name() -> None:
    cohort = {"modules": ["hypertension"], "module_count": 1}

    assert _module_scope_label(cohort) == "hypertension"
    assert _module_selection_details(cohort) == ""


def test_module_scope_label_compacts_multi_module_selection() -> None:
    cohort = {
        "modules": ["hypertension", "diabetes", "covid19"],
        "module_count": 3,
    }

    assert _module_scope_label(cohort) == "3 explicitly selected modules"
    details = _module_selection_details(cohort)
    assert "Show complete module selection (3)" in details
    assert "hypertension" in details
    assert "diabetes" in details
    assert "covid19" in details


def test_age_range_label_formats_inclusive_range() -> None:
    assert _age_range_label({"min_age": 18, "max_age": 90}) == "18–90 years"


def test_render_html_uses_compact_multimodule_overview() -> None:
    modules = ["hypertension", "diabetes", "covid19"]

    html = _render_html(_minimal_payload(modules=modules))

    assert "Experiment overview" in html
    assert "3 explicitly selected modules" in html
    assert "Show complete module selection (3)" in html
    assert "2026-06-30" in html
    assert "18–90 years" in html
    assert "Synthea / Psynthea" in html
    assert "hypertension, diabetes, covid19" not in html


def test_statistical_module_table_is_collapsed_for_multimodule_runs() -> None:
    validation = {
        "aggregate": {
            "module_count": 2,
            "significant_test_count": 0,
            "significant_after_fdr_count": 0,
            "warning_count": 0,
        },
        "modules": [
            {
                "module_name": "hypertension",
                "statistical_summary": {
                    "validation_status": "comparable",
                    "significant_test_count": 0,
                    "significant_after_fdr_count": 0,
                    "valid_for_statistical_comparison": True,
                },
            },
            {
                "module_name": "diabetes",
                "statistical_summary": {
                    "validation_status": "comparable",
                    "significant_test_count": 0,
                    "significant_after_fdr_count": 0,
                    "valid_for_statistical_comparison": True,
                },
            },
        ],
    }

    html = _statistical_evidence_v13(validation, ())

    assert "Module-level statistical summary (2 modules)" in html
    assert html.count("<details>") == 1

from __future__ import annotations

from validation.orchestration.stages.report import (
    _observation_window_label,
    _render_demographic_comparability,
    _render_temporal_epidemiology,
)


def test_observation_window_label_is_explicit() -> None:
    assert _observation_window_label({
        "observation_start_date": "2020-01-01",
        "observation_end_date": "2024-12-31",
    }) == "2020-01-01 – 2024-12-31"


def test_demographic_section_renders_age_and_sex_with_differences() -> None:
    validation = {
        "demographics": {
            "age_summary": {
                "synthea": {"mean": 55.0, "median": 56.0},
                "psynthea": {"mean": 57.0, "median": 58.0},
            },
            "age_groups": [
                {
                    "label": "50–59",
                    "synthea_count": 30,
                    "psynthea_count": 35,
                    "synthea_proportion": 0.30,
                    "psynthea_proportion": 0.35,
                }
            ],
            "sex_distribution": [
                {
                    "sex": "F",
                    "synthea_count": 52,
                    "psynthea_count": 49,
                    "synthea_proportion": 0.52,
                    "psynthea_proportion": 0.49,
                }
            ],
        }
    }
    html = _render_demographic_comparability(validation)
    assert "Age summary" in html
    assert "Age-group distribution" in html
    assert "Sex distribution" in html
    assert "+5.0 pp" in html
    assert "baseline comparability checks" in html


def test_epidemiology_section_renders_denominators_and_collapsed_detail() -> None:
    validation = {
        "epidemiology": {
            "aggregate": {
                "synthea": {"eligible_patients": 100, "prevalent_patients": 29, "incident_patients": 10},
                "psynthea": {"eligible_patients": 100, "prevalent_patients": 38, "incident_patients": 14},
            },
            "diseases": [
                {
                    "code": "38341003",
                    "description": "Hypertension",
                    "synthea_period_prevalence": 0.29,
                    "psynthea_period_prevalence": 0.38,
                    "synthea_cumulative_incidence": 0.12,
                    "psynthea_cumulative_incidence": 0.18,
                    "synthea_at_risk_patients": 83,
                    "psynthea_at_risk_patients": 79,
                }
            ],
        }
    }
    cohort = {
        "observation_start_date": "2020-01-01",
        "observation_end_date": "2024-12-31",
    }
    html = _render_temporal_epidemiology(validation, cohort)
    assert "2020-01-01" in html
    assert "Disease-specific epidemiology" in html
    assert "Hypertension" in html
    assert "denominators and onset age" in html
    assert "population at risk" in html


def test_missing_demographics_is_reported_without_fabrication() -> None:
    html = _render_demographic_comparability({})
    assert "was not persisted" in html
    assert "cannot be assessed" in html