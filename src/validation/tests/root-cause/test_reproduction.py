from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from validation.orchestration.models import ArtifactKind, ArtifactReference
from validation.root_cause.exceptions import ReproductionError, RootCauseInputError
from validation.root_cause.models import RootCauseRequest, VerificationOutcome, VerificationResult
from validation.root_cause.reproduction import (
    ExplicitReproductionContributor,
    ReproductionContext,
    ReproductionFragment,
    ReproductionPlanBuilder,
    ReproductionSeverity,
    VerificationReproductionContributor,
)


def artifact(identifier: str, *, digest: str | None = "a" * 64) -> ArtifactReference:
    return ArtifactReference(
        id=identifier,
        kind=ArtifactKind.OTHER,
        path=Path(f"artifacts/{identifier}.json"),
        media_type="application/json",
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
        sha256=digest,
        size_bytes=10 if digest is not None else None,
    )


def request(*, strict: bool = True, artifact_ids: tuple[str, ...] = ("input",)) -> RootCauseRequest:
    return RootCauseRequest(
        id="request-1",
        experiment_id="experiment-1",
        run_id="run-1",
        validation_result_ids=("validation-1",),
        artifact_ids=artifact_ids,
        strict_integrity=strict,
    )


def fragment(**overrides: object) -> ReproductionFragment:
    values = {
        "commands": (("python", "run.py", "--seed", "7"),),
        "working_directory": Path("workspace"),
        "seeds": (7,),
        "required_artifact_ids": ("input",),
        "software_versions": {"python": "3.12.4"},
        "expected_result": "The same discrepancy is observed.",
    }
    values.update(overrides)
    return ReproductionFragment(**values)


def test_builds_exact_plan_with_hashes() -> None:
    context = ReproductionContext(request(), {"input": artifact("input")})
    result = ReproductionPlanBuilder(
        (ExplicitReproductionContributor("explicit", fragment()),)
    ).build(context)

    assert result.plan.required_hashes == {"input": "a" * 64}
    assert result.plan.commands == (("python", "run.py", "--seed", "7"),)
    assert result.plan.expected_result == "The same discrepancy is observed."


def test_command_and_token_order_are_preserved() -> None:
    first = ExplicitReproductionContributor(
        "a", fragment(commands=(("python", "first.py", "--b", "2", "--a", "1"),))
    )
    second = ExplicitReproductionContributor(
        "b", fragment(commands=(("python", "second.py"),))
    )
    result = ReproductionPlanBuilder((second, first)).build(
        ReproductionContext(request(), {"input": artifact("input")})
    )

    assert result.plan.commands == (
        ("python", "first.py", "--b", "2", "--a", "1"),
        ("python", "second.py"),
    )


def test_strict_mode_requires_explicit_expected_result() -> None:
    contributor = ExplicitReproductionContributor(
        "explicit", fragment(expected_result=None)
    )
    with pytest.raises(ReproductionError, match="expected reproduction result"):
        ReproductionPlanBuilder((contributor,)).build(
            ReproductionContext(request(), {"input": artifact("input")})
        )


def test_permissive_mode_reports_missing_expected_result() -> None:
    contributor = ExplicitReproductionContributor(
        "explicit", fragment(expected_result=None)
    )
    result = ReproductionPlanBuilder((contributor,)).build(
        ReproductionContext(request(strict=False), {"input": artifact("input")})
    )
    assert {item.code for item in result.diagnostics} == {
        "reproduction.missing_expected_result"
    }


def test_verification_inputs_must_exist_in_context() -> None:
    verification = VerificationResult(
        id="verification-1",
        candidate_id="candidate-1",
        verifier_id="verifier-1",
        outcome=VerificationOutcome.PASSED,
        procedure="Compare outputs.",
        expected_result="Equivalent discrepancy.",
        observed_result="Equivalent discrepancy.",
        input_artifact_ids=("missing",),
        evidence_ids=("evidence-1",),
    )
    with pytest.raises(RootCauseInputError, match="unavailable input artefacts"):
        ReproductionContext(
            request(), {"input": artifact("input")}, verification_results=(verification,)
        )


def test_verification_contributor_includes_output_artifacts() -> None:
    output = artifact("output", digest="b" * 64)
    verification = VerificationResult(
        id="verification-1",
        candidate_id="candidate-1",
        verifier_id="verifier-1",
        outcome=VerificationOutcome.PASSED,
        procedure="Compare outputs.",
        expected_result="Equivalent discrepancy.",
        observed_result="Equivalent discrepancy.",
        input_artifact_ids=("input",),
        output_artifacts=(output,),
        evidence_ids=("evidence-1",),
        command=("python", "verify.py"),
    )
    explicit = ExplicitReproductionContributor(
        "explicit",
        fragment(required_artifact_ids=("input", "output")),
    )
    result = ReproductionPlanBuilder(
        (explicit, VerificationReproductionContributor())
    ).build(
        ReproductionContext(
            request(artifact_ids=("input",)),
            {"input": artifact("input"), "output": output},
            verification_results=(verification,),
        )
    )
    assert result.plan.required_artifact_ids == ("input", "output")


def test_severity_is_a_real_enum() -> None:
    assert ReproductionSeverity.WARNING.value == "warning"


def test_plan_identifier_is_order_independent_for_contributors() -> None:
    a = ExplicitReproductionContributor("a", fragment())
    b = ExplicitReproductionContributor(
        "b", ReproductionFragment(limitations=("Known limitation.",))
    )
    context = ReproductionContext(request(), {"input": artifact("input")})
    assert ReproductionPlanBuilder((a, b)).build(context).plan.id == ReproductionPlanBuilder(
        (b, a)
    ).build(context).plan.id