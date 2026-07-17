"""Tests for the in-memory root-cause stage input provider."""

from __future__ import annotations

from validation.interpretation.workflow import InterpretationWorkflowResult
from validation.orchestration.stages.root_cause_input import (
    InMemoryRootCauseStageInputProvider,
)
from validation.tests.orchestrations.test_root_cause_analysis_stage import _context


def _interpretation_from_payload(payload) -> InterpretationWorkflowResult:
    result = object.__new__(InterpretationWorkflowResult)
    execution = type(
        "Execution",
        (),
        {"report": payload.request_source.interpretation_report},
    )()
    object.__setattr__(result, "execution", execution)
    object.__setattr__(result, "workflow_fingerprint", "workflow-fingerprint")
    object.__setattr__(
        result,
        "evidence_catalog_fingerprint",
        "evidence-fingerprint",
    )
    return result


def test_provider_builds_request_source_and_engine_inputs(tmp_path) -> None:
    _, context, existing_payload = _context(tmp_path)
    interpretation = _interpretation_from_payload(existing_payload)

    provider = InMemoryRootCauseStageInputProvider(
        interpretation=interpretation,
        evidence_sources=(),
        metadata={"test_case": "provider"},
    )

    payload = provider.load(context)

    source = payload.request_source
    inputs = payload.engine_inputs

    assert source.experiment_result.run_id == context.run_id
    assert source.experiment_result.status.value == "running"
    assert source.interpretation_report is interpretation.execution.report
    assert source.metadata["interpretation_workflow_fingerprint"] == (
        "workflow-fingerprint"
    )
    assert {item.id for item in inputs.artifacts} == {
        item.id for item in context.artifacts
    }
    assert inputs.metadata["experiment_id"] == context.config.id
    assert inputs.metadata["orchestrator_run_id"] == context.run_id


def test_provider_rejects_interpretation_from_another_run(tmp_path) -> None:
    _, context, existing_payload = _context(tmp_path)
    interpretation = _interpretation_from_payload(existing_payload)
    report = interpretation.execution.report
    object.__setattr__(report, "pipeline_run_id", "another-run")

    provider = InMemoryRootCauseStageInputProvider(
        interpretation=interpretation,
        evidence_sources=(),
    )

    try:
        provider.load(context)
    except ValueError as exc:
        assert "pipeline_run_id" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected provider to reject a mismatched run id.")