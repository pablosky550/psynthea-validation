"""Contract tests for the public scientific-interpretation API."""

from __future__ import annotations

import importlib
from collections import Counter

import pytest

import validation.interpretation as interpretation
import validation.interpretation.rules as rules
from validation.interpretation.engine import DEFAULT_INTERPRETATION_RULES, ENGINE_VERSION
from validation.interpretation.rules import (
    DEFAULT_CLINICAL_RULES,
    DEFAULT_EPIDEMIOLOGICAL_RULES,
    DEFAULT_SPANISH_ADAPTATION_RULES,
    DEFAULT_STATISTICAL_RULES,
    DEFAULT_STRUCTURAL_RULES,
)


EXPECTED_RULE_REGISTRY = (
    *DEFAULT_STRUCTURAL_RULES,
    *DEFAULT_STATISTICAL_RULES,
    *DEFAULT_CLINICAL_RULES,
    *DEFAULT_EPIDEMIOLOGICAL_RULES,
    *DEFAULT_SPANISH_ADAPTATION_RULES,
)


@pytest.mark.parametrize("module", [interpretation, rules])
def test_public_api_contains_no_duplicate_names(module: object) -> None:
    exported = tuple(module.__all__)
    duplicates = sorted(name for name, count in Counter(exported).items() if count > 1)

    assert duplicates == []
    assert exported == tuple(sorted(exported))


@pytest.mark.parametrize("module", [interpretation, rules])
def test_every_declared_public_symbol_is_bound(module: object) -> None:
    missing = [name for name in module.__all__ if not hasattr(module, name)]

    assert missing == []


@pytest.mark.parametrize("module", [interpretation, rules])
def test_star_import_matches_declared_public_api(module: object) -> None:
    namespace: dict[str, object] = {}
    exec(f"from {module.__name__} import *", {}, namespace)

    assert set(namespace) == set(module.__all__)


def test_interpretation_version_has_single_engine_source_of_truth() -> None:
    assert interpretation.__version__ == ENGINE_VERSION
    assert interpretation.ENGINE_VERSION == ENGINE_VERSION


def test_default_registry_exposes_all_rule_families_in_scientific_order() -> None:
    assert DEFAULT_INTERPRETATION_RULES == EXPECTED_RULE_REGISTRY
    assert interpretation.DEFAULT_INTERPRETATION_RULES == EXPECTED_RULE_REGISTRY

    rule_ids = tuple(rule.rule_id for rule in EXPECTED_RULE_REGISTRY)
    assert len(rule_ids) == len(set(rule_ids))

    dimensions = tuple(rule.dimension.value for rule in EXPECTED_RULE_REGISTRY)
    first_epidemiological = dimensions.index("epidemiological")
    last_statistical = max(index for index, value in enumerate(dimensions) if value == "statistical")
    last_clinical = max(index for index, value in enumerate(dimensions) if value == "clinical")
    first_spanish = dimensions.index("spanish_adaptation")

    assert last_statistical < first_epidemiological
    assert last_clinical < first_epidemiological
    assert first_epidemiological < first_spanish


def test_epidemiological_public_symbols_are_identity_preserving_reexports() -> None:
    epidemiological = importlib.import_module(
        "validation.interpretation.rules.epidemiological"
    )

    for name in epidemiological.__all__:
        assert getattr(rules, name) is getattr(epidemiological, name)


def test_core_public_symbols_are_identity_preserving_reexports() -> None:
    provenance = {
        "InterpretationEngine": "validation.interpretation.engine",
        "EvidenceCatalog": "validation.interpretation.evidence",
        "InterpretationReport": "validation.interpretation.models",
        "RecommendationPlan": "validation.interpretation.recommendations",
        "InterpretationDocument": "validation.interpretation.report",
        "InterpretationSummary": "validation.interpretation.summary",
        "InterpretationWorkflow": "validation.interpretation.workflow",
    }

    for name, module_name in provenance.items():
        source = importlib.import_module(module_name)
        assert getattr(interpretation, name) is getattr(source, name)


def test_public_modules_reload_without_circular_import_failure() -> None:
    reloaded_rules = importlib.reload(rules)
    reloaded_interpretation = importlib.reload(interpretation)

    assert reloaded_rules.DEFAULT_EPIDEMIOLOGICAL_RULES
    assert reloaded_interpretation.InterpretationEngine is not None
    assert reloaded_interpretation.__version__ == ENGINE_VERSION