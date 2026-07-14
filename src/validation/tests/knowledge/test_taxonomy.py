"""Tests for the canonical Phase 2A root-cause taxonomy."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from validation.knowledge.taxonomy import (
    CANONICAL_TAXONOMY,
    RootCauseCategory,
    TaxonomyAxis,
    TaxonomyCatalog,
    TaxonomyTerm,
    UnknownTaxonomyTermError,
    ValidationDomain,
)


def _term(
    id: str,
    *,
    axis: TaxonomyAxis = TaxonomyAxis.ROOT_CAUSE,
    parent_id: str | None = None,
    selectable: bool = True,
    aliases: tuple[str, ...] = (),
    deprecated: bool = False,
    replacement_id: str | None = None,
) -> TaxonomyTerm:
    return TaxonomyTerm(
        id=id,
        axis=axis,
        label=id,
        definition=f"Definition for {id}.",
        investigation_question=f"Question for {id}?",
        parent_id=parent_id,
        selectable=selectable,
        aliases=aliases,
        deprecated=deprecated,
        replacement_id=replacement_id,
    )


def test_canonical_taxonomy_contains_every_public_enum_value() -> None:
    root_ids = {
        term.id
        for term in CANONICAL_TAXONOMY.terms_for_axis(
            TaxonomyAxis.ROOT_CAUSE,
            selectable_only=True,
        )
    }
    domain_ids = {
        term.id
        for term in CANONICAL_TAXONOMY.terms_for_axis(
            TaxonomyAxis.VALIDATION_DOMAIN,
            selectable_only=True,
        )
    }

    assert root_ids == {item.value for item in RootCauseCategory}
    assert domain_ids == {item.value for item in ValidationDomain}


def test_canonical_taxonomy_keeps_cause_and_domain_orthogonal() -> None:
    export = CANONICAL_TAXONOMY.require_root_cause(RootCauseCategory.EXPORT.value)
    observations = CANONICAL_TAXONOMY.require_domain(ValidationDomain.OBSERVATIONS.value)

    assert export.axis is TaxonomyAxis.ROOT_CAUSE
    assert observations.axis is TaxonomyAxis.VALIDATION_DOMAIN
    with pytest.raises(ValueError, match="belongs to validation_domain"):
        CANONICAL_TAXONOMY.require_root_cause(observations.id)
    with pytest.raises(ValueError, match="belongs to root_cause"):
        CANONICAL_TAXONOMY.require_domain(export.id)


def test_aliases_resolve_to_canonical_identifiers() -> None:
    assert CANONICAL_TAXONOMY.resolve("exporter").id == RootCauseCategory.EXPORT.value
    assert CANONICAL_TAXONOMY.resolve("labs").id == ValidationDomain.OBSERVATIONS.value
    assert CANONICAL_TAXONOMY.resolve("ATENCION_PRIMARIA").id == ValidationDomain.PRIMARY_CARE.value


def test_unknown_lookup_fails_loudly_and_contains_is_non_throwing() -> None:
    assert not CANONICAL_TAXONOMY.contains("root_cause.imaginary")
    with pytest.raises(UnknownTaxonomyTermError, match="Unknown taxonomy term"):
        CANONICAL_TAXONOMY.resolve("root_cause.imaginary")


def test_organizational_nodes_cannot_be_persisted_as_categories() -> None:
    assert CANONICAL_TAXONOMY.resolve("root_cause.engine").selectable is False
    with pytest.raises(ValueError, match="organizational and not selectable"):
        CANONICAL_TAXONOMY.require_root_cause("root_cause.engine")


def test_unknown_root_cause_is_explicit_selectable_and_not_a_fallback() -> None:
    unknown = CANONICAL_TAXONOMY.require_root_cause(RootCauseCategory.UNKNOWN.value)

    assert unknown.id == "root_cause.unknown"
    with pytest.raises(UnknownTaxonomyTermError):
        CANONICAL_TAXONOMY.resolve("anything_else")


def test_hierarchy_queries_are_deterministic() -> None:
    engine_children = CANONICAL_TAXONOMY.children_of("root_cause.engine")
    ancestors = CANONICAL_TAXONOMY.ancestors_of(
        RootCauseCategory.TEMPORAL_SEMANTICS.value
    )
    descendants = CANONICAL_TAXONOMY.descendants_of("root_cause.compatibility")

    assert tuple(term.id for term in engine_children) == (
        RootCauseCategory.ENGINE_EXECUTION.value,
        RootCauseCategory.TEMPORAL_SEMANTICS.value,
        RootCauseCategory.PROBABILISTIC_SEMANTICS.value,
    )
    assert tuple(term.id for term in ancestors) == ("root_cause.engine", "root_cause")
    assert tuple(term.id for term in descendants) == (
        RootCauseCategory.PARSER_IMPORT.value,
        RootCauseCategory.UNSUPPORTED_GMF.value,
        RootCauseCategory.ROUND_TRIP.value,
    )


def test_canonicalize_many_resolves_aliases_deduplicates_and_preserves_order() -> None:
    result = CANONICAL_TAXONOMY.canonicalize_many(
        ["labs", ValidationDomain.CONDITIONS.value, "domain.observations"],
        axis=TaxonomyAxis.VALIDATION_DOMAIN,
    )

    assert result == (
        ValidationDomain.OBSERVATIONS.value,
        ValidationDomain.CONDITIONS.value,
    )


def test_canonicalize_many_requires_non_empty_iterable_and_rejects_string() -> None:
    with pytest.raises(ValueError, match="At least one taxonomy term"):
        CANONICAL_TAXONOMY.canonicalize_many(
            [], axis=TaxonomyAxis.VALIDATION_DOMAIN
        )
    with pytest.raises(TypeError, match="not a string"):
        CANONICAL_TAXONOMY.canonicalize_many(
            "labs", axis=TaxonomyAxis.VALIDATION_DOMAIN
        )


def test_taxonomy_term_is_immutable_and_normalizes_identifiers() -> None:
    term = _term("ROOT_CAUSE.TEST", aliases=("TEST_ALIAS",))

    assert term.id == "root_cause.test"
    assert term.aliases == ("test_alias",)
    with pytest.raises(FrozenInstanceError):
        term.label = "Changed"


def test_taxonomy_term_requires_strict_enum_and_boolean_boundaries() -> None:
    with pytest.raises(TypeError, match="TaxonomyAxis"):
        TaxonomyTerm(
            id="root_cause.test",
            axis="root_cause",
            label="Test",
            definition="Definition.",
            investigation_question="Question?",
        )
    with pytest.raises(TypeError, match="selectable must be a bool"):
        _term("root_cause.test", selectable=1)


def test_term_rejects_self_parent_self_alias_and_invalid_deprecation() -> None:
    with pytest.raises(ValueError, match="own parent"):
        _term("root_cause.test", parent_id="root_cause.test")
    with pytest.raises(ValueError, match="own id as an alias"):
        _term("root_cause.test", aliases=("root_cause.test",))
    with pytest.raises(ValueError, match="requires replacement_id"):
        _term("root_cause.old", deprecated=True, selectable=False)
    with pytest.raises(ValueError, match="only valid for deprecated"):
        _term("root_cause.current", replacement_id="root_cause.new")
    with pytest.raises(ValueError, match="cannot remain selectable"):
        _term(
            "root_cause.old",
            deprecated=True,
            selectable=True,
            replacement_id="root_cause.new",
        )


def test_catalog_rejects_duplicate_ids_and_alias_collisions() -> None:
    with pytest.raises(ValueError, match="Duplicate taxonomy term id"):
        TaxonomyCatalog(
            terms=(_term("root_cause.a"), _term("root_cause.a")),
            version="test.1",
        )
    with pytest.raises(ValueError, match="collides with canonical"):
        TaxonomyCatalog(
            terms=(
                _term("root_cause.a", aliases=("root_cause.b",)),
                _term("root_cause.b"),
            ),
            version="test.1",
        )
    with pytest.raises(ValueError, match="assigned to both"):
        TaxonomyCatalog(
            terms=(
                _term("root_cause.a", aliases=("shared",)),
                _term("root_cause.b", aliases=("shared",)),
            ),
            version="test.1",
        )


def test_catalog_rejects_unknown_parent_and_cross_axis_parent() -> None:
    with pytest.raises(ValueError, match="unknown parent"):
        TaxonomyCatalog(
            terms=(_term("root_cause.child", parent_id="root_cause.missing"),),
            version="test.1",
        )
    with pytest.raises(ValueError, match="must share an axis"):
        TaxonomyCatalog(
            terms=(
                _term("root_cause.parent", selectable=False),
                _term(
                    "domain.child",
                    axis=TaxonomyAxis.VALIDATION_DOMAIN,
                    parent_id="root_cause.parent",
                ),
            ),
            version="test.1",
        )


def test_catalog_rejects_parent_cycles() -> None:
    with pytest.raises(ValueError, match="parent cycle"):
        TaxonomyCatalog(
            terms=(
                _term("root_cause.a", parent_id="root_cause.b"),
                _term("root_cause.b", parent_id="root_cause.a"),
            ),
            version="test.1",
        )


def test_catalog_validates_deprecation_replacement_integrity() -> None:
    current = _term("root_cause.current")
    old = _term(
        "root_cause.old",
        selectable=False,
        deprecated=True,
        replacement_id=current.id,
    )
    catalog = TaxonomyCatalog(terms=(old, current), version="test.1")

    assert catalog.resolve(old.id).replacement_id == current.id
    with pytest.raises(ValueError, match="deprecated; use"):
        catalog.require_root_cause(old.id)

    with pytest.raises(ValueError, match="unknown replacement"):
        TaxonomyCatalog(
            terms=(
                _term(
                    "root_cause.old",
                    selectable=False,
                    deprecated=True,
                    replacement_id="root_cause.missing",
                ),
            ),
            version="test.1",
        )


def test_catalog_rejects_cross_axis_and_deprecated_replacements() -> None:
    with pytest.raises(ValueError, match="must share an axis"):
        TaxonomyCatalog(
            terms=(
                _term(
                    "root_cause.old",
                    selectable=False,
                    deprecated=True,
                    replacement_id="domain.current",
                ),
                _term("domain.current", axis=TaxonomyAxis.VALIDATION_DOMAIN),
            ),
            version="test.1",
        )

    old = _term(
        "root_cause.old",
        selectable=False,
        deprecated=True,
        replacement_id="root_cause.new",
    )
    new = _term(
        "root_cause.new",
        selectable=False,
        deprecated=True,
        replacement_id="root_cause.current",
    )
    current = _term("root_cause.current")
    with pytest.raises(ValueError, match="must not be deprecated"):
        TaxonomyCatalog(terms=(old, new, current), version="test.1")


def test_catalog_rejects_replacement_cycles() -> None:
    # Constructing a direct replacement cycle is prevented only after both
    # references are resolvable, which is exactly the catalogue-level invariant.
    a = TaxonomyTerm(
        id="root_cause.a",
        axis=TaxonomyAxis.ROOT_CAUSE,
        label="A",
        definition="A.",
        investigation_question="A?",
        selectable=False,
        deprecated=True,
        replacement_id="root_cause.b",
    )
    b = TaxonomyTerm(
        id="root_cause.b",
        axis=TaxonomyAxis.ROOT_CAUSE,
        label="B",
        definition="B.",
        investigation_question="B?",
        selectable=False,
        deprecated=True,
        replacement_id="root_cause.a",
    )
    with pytest.raises(ValueError, match="replacement taxonomy term must not be deprecated"):
        TaxonomyCatalog(terms=(a, b), version="test.1")


def test_catalog_storage_is_immutable() -> None:
    with pytest.raises(TypeError):
        CANONICAL_TAXONOMY._by_id["new"] = CANONICAL_TAXONOMY.terms[0]
    with pytest.raises(TypeError):
        CANONICAL_TAXONOMY._alias_to_id["new"] = "root_cause.export"


def test_every_selectable_canonical_term_is_documented_for_investigation() -> None:
    selectable = tuple(term for term in CANONICAL_TAXONOMY.terms if term.selectable)

    assert selectable
    assert all(term.definition.endswith((".", "?")) for term in selectable)
    assert all(term.investigation_question.endswith("?") for term in selectable)
    assert all(term.examples for term in selectable)


def test_root_cause_enum_values_can_be_used_directly_by_knowledge_models() -> None:
    # The models persist category_id as a stable string. This assertion protects
    # the public contract without creating an import cycle from models to taxonomy.
    category_id = RootCauseCategory.EXPORT.value

    assert CANONICAL_TAXONOMY.require_root_cause(category_id).id == category_id
    assert category_id.startswith("root_cause.")


def test_validation_framework_causes_are_distinct_from_simulator_causes() -> None:
    ingestion = CANONICAL_TAXONOMY.require_root_cause(
        RootCauseCategory.VALIDATION_INGESTION.value
    )
    metric = CANONICAL_TAXONOMY.require_root_cause(
        RootCauseCategory.VALIDATION_METRIC.value
    )
    artifact = CANONICAL_TAXONOMY.require_root_cause(
        RootCauseCategory.STATISTICAL_ARTIFACT.value
    )

    assert ingestion.parent_id == "root_cause.validation"
    assert metric.parent_id == "root_cause.validation"
    assert artifact.parent_id == "root_cause"
    assert metric.id != artifact.id


def test_validation_pipeline_domain_is_not_a_root_cause() -> None:
    domain = CANONICAL_TAXONOMY.require_domain(
        ValidationDomain.VALIDATION_PIPELINE.value
    )

    assert domain.axis is TaxonomyAxis.VALIDATION_DOMAIN
    with pytest.raises(ValueError, match="belongs to validation_domain"):
        CANONICAL_TAXONOMY.require_root_cause(domain.id)


def test_provenance_and_mortality_are_first_class_validation_domains() -> None:
    provenance = CANONICAL_TAXONOMY.require_domain(ValidationDomain.PROVENANCE.value)
    mortality = CANONICAL_TAXONOMY.require_domain(ValidationDomain.MORTALITY.value)

    assert provenance.id == "domain.provenance"
    assert mortality.id == "domain.mortality"
    assert provenance.examples
    assert mortality.examples


def test_canonical_taxonomy_version_changes_when_public_vocabulary_changes() -> None:
    assert CANONICAL_TAXONOMY.version == "phase2a.2"