"""Tests for run-scoped scientific stage product exchange."""

from __future__ import annotations

import pytest

from validation.orchestration.stage_products import ScientificStageProductStore
from validation.orchestration.stages.root_cause_input import (
    StoredRootCauseStageInputProvider,
)
from validation.tests.orchestrations.test_root_cause_input_provider import (
    _interpretation_from_payload,
)
from validation.tests.orchestrations.test_root_cause_analysis_stage import _context


def test_store_publishes_and_resolves_interpretation_by_run_and_module(
    tmp_path,
) -> None:
    _, context, existing_payload = _context(tmp_path)
    interpretation = _interpretation_from_payload(existing_payload)
    module_name = interpretation.execution.report.module_name
    store = ScientificStageProductStore()

    store.publish_interpretation(
        run_id=context.run_id,
        result=interpretation,
    )

    assert store.interpretation(run_id=context.run_id) is interpretation
    assert (
        store.interpretation(
            run_id=context.run_id,
            module_name=module_name,
        )
        is interpretation
    )


def test_store_rejects_cross_run_interpretation(tmp_path) -> None:
    _, context, existing_payload = _context(tmp_path)
    interpretation = _interpretation_from_payload(existing_payload)
    store = ScientificStageProductStore()

    with pytest.raises(ValueError, match="pipeline_run_id"):
        store.publish_interpretation(
            run_id="another-run",
            result=interpretation,
        )


def test_stored_provider_resolves_current_run_at_execution_time(tmp_path) -> None:
    _, context, existing_payload = _context(tmp_path)
    interpretation = _interpretation_from_payload(existing_payload)
    store = ScientificStageProductStore()
    provider = StoredRootCauseStageInputProvider(
        product_store=store,
        module_name=interpretation.execution.report.module_name,
        metadata={"integration": "knowledge-to-root-cause"},
    )

    with pytest.raises(LookupError, match="No interpretation"):
        provider.load(context)

    store.publish_interpretation(
        run_id=context.run_id,
        result=interpretation,
    )
    payload = provider.load(context)

    assert payload.request_source.interpretation_report is (
        interpretation.execution.report
    )
    assert payload.request_source.experiment_result.run_id == context.run_id
    assert payload.engine_inputs.metadata["integration"] == (
        "knowledge-to-root-cause"
    )
    assert {artifact.id for artifact in payload.engine_inputs.artifacts} == {
        artifact.id for artifact in context.artifacts
    }


def test_store_clear_run_removes_published_products(tmp_path) -> None:
    _, context, existing_payload = _context(tmp_path)
    interpretation = _interpretation_from_payload(existing_payload)
    store = ScientificStageProductStore()
    store.publish_interpretation(
        run_id=context.run_id,
        result=interpretation,
    )

    store.clear_run(context.run_id)

    with pytest.raises(LookupError, match="No interpretation"):
        store.interpretation(run_id=context.run_id)