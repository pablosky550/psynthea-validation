from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from validation.knowledge.models import EvidenceSourceKind, VerificationCheck
from validation.knowledge.protocols import (
    CANONICAL_PROTOCOLS,
    EvidenceRequirement,
    EvidenceRequirementLevel,
    InvestigationProtocol,
    ProtocolCatalog,
    ProtocolStep,
    ProtocolStepKind,
    UnknownProtocolError,
)
from validation.knowledge.taxonomy import (
    CANONICAL_TAXONOMY,
    RootCauseCategory,
    ValidationDomain,
)


def _requirement(
    requirement_id: str = "evidence.primary",
    *,
    level: EvidenceRequirementLevel = EvidenceRequirementLevel.REQUIRED,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=requirement_id,
        source_kind=EvidenceSourceKind.REPRODUCTION,
        description="A deterministic reproduction artifact.",
        acceptance_criteria="The artifact is tied to the pinned run and can be independently inspected.",
        level=level,
        suggested_locators=("outputs/run-001",),
    )


def _step(
    step_id: str = "reproduce",
    *,
    requirements: tuple[EvidenceRequirement, ...] | None = None,
    investigates: tuple[str, ...] = (RootCauseCategory.CONFIGURATION.value,),
    depends_on: tuple[str, ...] = (),
) -> ProtocolStep:
    return ProtocolStep(
        id=step_id,
        title="Reproduce the discrepancy",
        kind=ProtocolStepKind.REPRODUCE,
        procedure="Run both engines with pinned configuration and immutable input artifacts.",
        expected_result="The discrepancy is reproduced or explicitly classified as non-reproducible.",
        interpretation_boundary="Reproduction establishes existence, not cause.",
        evidence_requirements=requirements or (_requirement(),),
        investigates_category_ids=investigates,
        depends_on=depends_on,
    )


def _protocol(
    *,
    protocol_id: str = "protocol.example",
    version: str = "1.2.3",
    steps: tuple[ProtocolStep, ...] | None = None,
    candidates: tuple[str, ...] = (RootCauseCategory.CONFIGURATION.value,),
    aliases: tuple[str, ...] = ("protocol.alias",),
) -> InvestigationProtocol:
    return InvestigationProtocol(
        id=protocol_id,
        version=version,
        title="Example investigation protocol",
        objective="Determine the causal layer without converting an observed difference into a presumed cause.",
        applicability="Use for controlled validation discrepancies in the conditions domain.",
        domain_ids=(ValidationDomain.CONDITIONS.value,),
        candidate_category_ids=candidates,
        steps=steps or (_step(),),
        aliases=aliases,
        exit_criteria=(
            "The discrepancy is reproduced or classified as non-reproducible.",
            "Any supported cause has discriminating verification evidence.",
        ),
        limitations=("The protocol does not establish external clinical validity.",),
    )


def test_evidence_requirement_is_normalized_and_immutable() -> None:
    requirement = EvidenceRequirement(
        id="Evidence.Primary",
        source_kind=EvidenceSourceKind.RAW_DATA,
        description="  Raw source rows.  ",
        acceptance_criteria="  Rows originate from the pinned artifact.  ",
        suggested_locators=(" observations.csv ", "observations.csv"),
    )

    assert requirement.id == "evidence.primary"
    assert requirement.description == "Raw source rows."
    assert requirement.suggested_locators == ("observations.csv",)
    with pytest.raises(FrozenInstanceError):
        requirement.id = "changed"  # type: ignore[misc]


def test_step_requires_at_least_one_required_evidence_item() -> None:
    optional = _requirement(level=EvidenceRequirementLevel.OPTIONAL)

    with pytest.raises(ValueError, match="at least one REQUIRED"):
        _step(requirements=(optional,))


def test_step_rejects_duplicate_evidence_ids() -> None:
    requirement = _requirement()

    with pytest.raises(ValueError, match="duplicate ids"):
        _step(requirements=(requirement, requirement))


def test_step_rejects_non_root_cause_taxonomy_terms() -> None:
    with pytest.raises(ValueError):
        _step(investigates=(ValidationDomain.CONDITIONS.value,))


def test_step_rejects_self_dependency() -> None:
    with pytest.raises(ValueError, match="depend on itself"):
        _step(step_id="reproduce", depends_on=("reproduce",))


def test_required_evidence_filters_nonmandatory_requirements() -> None:
    step = _step(
        requirements=(
            _requirement("evidence.required"),
            _requirement(
                "evidence.context",
                level=EvidenceRequirementLevel.CORROBORATING,
            ),
        )
    )

    assert tuple(item.id for item in step.required_evidence) == ("evidence.required",)


def test_verification_check_created_from_step_is_unexecuted() -> None:
    check = _step().to_verification_check("hypothesis.export", id_prefix="protocol.example:v1.0.0")

    assert isinstance(check, VerificationCheck)
    assert check.id == "protocol.example:v1.0.0.reproduce"
    assert check.hypothesis_id == "hypothesis.export"
    assert check.evidence_ids == ()
    assert check.actual_result is None


def test_protocol_rejects_unknown_step_dependency() -> None:
    step = _step(depends_on=("missing",))

    with pytest.raises(ValueError, match="unknown dependencies"):
        _protocol(steps=(step,))


def test_protocol_rejects_dependency_cycles() -> None:
    first = _step("first", depends_on=("second",))
    second = _step(
        "second",
        requirements=(_requirement("evidence.second"),),
        depends_on=("first",),
    )

    with pytest.raises(ValueError, match="dependency cycle"):
        _protocol(steps=(first, second))


def test_protocol_rejects_duplicate_evidence_ids_across_steps() -> None:
    first = _step("first")
    second = _step("second")

    with pytest.raises(ValueError, match="unique across the entire protocol"):
        _protocol(steps=(first, second))


def test_protocol_rejects_candidate_category_not_investigated_by_any_step() -> None:
    with pytest.raises(ValueError, match="not investigated by any step"):
        _protocol(
            candidates=(
                RootCauseCategory.CONFIGURATION.value,
                RootCauseCategory.EXPORT.value,
            )
        )


def test_protocol_rejects_step_category_outside_candidate_scope() -> None:
    step = _step(investigates=(RootCauseCategory.EXPORT.value,))

    with pytest.raises(ValueError, match="outside the protocol scope"):
        _protocol(steps=(step,))


def test_qualified_id_is_identifier_safe_and_versioned() -> None:
    protocol = _protocol(version="1.2.3+build.7")

    assert protocol.qualified_id == "protocol.example:v1.2.3_build.7"


def test_default_verification_ids_are_versioned_to_prevent_collisions() -> None:
    first = _protocol(version="1.0.0", aliases=()).instantiate_checks("hypothesis.one")
    second = _protocol(version="2.0.0", aliases=()).instantiate_checks("hypothesis.one")

    assert first[0].id == "protocol.example:v1.0.0.reproduce"
    assert second[0].id == "protocol.example:v2.0.0.reproduce"
    assert first[0].id != second[0].id


def test_protocol_step_lookup_is_strict() -> None:
    protocol = _protocol()

    assert protocol.step("REPRODUCE").id == "reproduce"
    with pytest.raises(KeyError, match="Unknown step"):
        protocol.step("missing")


def test_protocol_evidence_lookup_is_protocol_wide_and_strict() -> None:
    protocol = _protocol()

    assert protocol.evidence_requirement("EVIDENCE.PRIMARY").id == "evidence.primary"
    with pytest.raises(KeyError, match="Unknown evidence requirement"):
        protocol.evidence_requirement("evidence.missing")


def test_execution_layers_are_deterministic_and_dependency_safe() -> None:
    first = _step("first", requirements=(_requirement("evidence.first"),))
    second = _step(
        "second",
        requirements=(_requirement("evidence.second"),),
        depends_on=("first",),
    )
    parallel = _step(
        "parallel",
        requirements=(_requirement("evidence.parallel"),),
        depends_on=("first",),
    )
    final = _step(
        "final",
        requirements=(_requirement("evidence.final"),),
        depends_on=("second", "parallel"),
    )
    protocol = _protocol(steps=(first, second, parallel, final))

    assert tuple(tuple(step.id for step in layer) for layer in protocol.execution_layers()) == (
        ("first",),
        ("second", "parallel"),
        ("final",),
    )


def test_catalog_rejects_taxonomy_version_drift() -> None:
    with pytest.raises(ValueError, match="does not match"):
        ProtocolCatalog(
            protocols=(_protocol(),),
            version="phase2a.99",
            taxonomy_version="phase2a.999",
        )


def test_catalog_rejects_alias_collisions() -> None:
    first = _protocol(protocol_id="protocol.first", aliases=("protocol.shared",))
    second = _protocol(protocol_id="protocol.second", aliases=("protocol.shared",))

    with pytest.raises(ValueError, match="assigned to both"):
        ProtocolCatalog(
            protocols=(first, second),
            version="phase2a.2",
            taxonomy_version=CANONICAL_TAXONOMY.version,
        )


def test_catalog_resolves_id_alias_and_qualified_id() -> None:
    protocol = _protocol()
    catalog = ProtocolCatalog(
        protocols=(protocol,),
        version="phase2a.2",
        taxonomy_version=CANONICAL_TAXONOMY.version,
    )

    assert catalog.resolve(protocol.id) is protocol
    assert catalog.resolve("protocol.alias") is protocol
    assert catalog.resolve(protocol.qualified_id) is protocol


def test_catalog_unknown_lookup_fails_loudly() -> None:
    with pytest.raises(UnknownProtocolError, match="Unknown investigation protocol"):
        CANONICAL_PROTOCOLS.resolve("protocol.does_not_exist")


def test_catalog_domain_filter_only_narrows_candidates() -> None:
    protocols = CANONICAL_PROTOCOLS.for_domain(ValidationDomain.OBSERVATIONS.value)

    assert protocols
    assert any(item.id == "protocol.missing_or_empty_output" for item in protocols)
    assert any(item.id == "protocol.generic_root_cause" for item in protocols)


def test_catalog_category_filter_returns_capable_protocols() -> None:
    protocols = CANONICAL_PROTOCOLS.investigating(RootCauseCategory.EXPORT.value)

    assert protocols
    assert all(
        RootCauseCategory.EXPORT.value in protocol.candidate_category_ids
        for protocol in protocols
    )


def test_canonical_catalog_is_bound_to_latest_taxonomy_and_protocol_version() -> None:
    assert CANONICAL_PROTOCOLS.version == "phase2a.2"
    assert CANONICAL_PROTOCOLS.taxonomy_version == CANONICAL_TAXONOMY.version
    assert len(CANONICAL_PROTOCOLS.protocols) == 6


def test_canonical_protocols_have_complete_scientific_contracts() -> None:
    for protocol in CANONICAL_PROTOCOLS.protocols:
        assert protocol.exit_criteria
        assert protocol.steps
        assert protocol.domain_ids
        assert protocol.candidate_category_ids
        assert all(step.required_evidence for step in protocol.steps)
        assert {
            category_id
            for step in protocol.steps
            for category_id in step.investigates_category_ids
        } >= set(protocol.candidate_category_ids)


def test_canonical_evidence_ids_are_unique_within_each_protocol() -> None:
    for protocol in CANONICAL_PROTOCOLS.protocols:
        evidence_ids = [
            requirement.id
            for step in protocol.steps
            for requirement in step.evidence_requirements
        ]
        assert len(evidence_ids) == len(set(evidence_ids))


def test_canonical_check_ids_are_unique_across_protocols_and_steps() -> None:
    check_ids = [
        check.id
        for protocol in CANONICAL_PROTOCOLS.protocols
        for check in protocol.instantiate_checks("hypothesis.canonical")
    ]

    assert len(check_ids) == len(set(check_ids))


def test_protocol_models_are_immutable() -> None:
    protocol = _protocol()

    with pytest.raises(FrozenInstanceError):
        protocol.version = "9.9.9"  # type: ignore[misc]