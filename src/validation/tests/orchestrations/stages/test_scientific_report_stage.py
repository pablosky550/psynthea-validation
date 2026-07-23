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
