from __future__ import annotations

import pytest

from validation.orchestration.scientific_pipeline import (
    ScientificPipeline,
    build_scientific_pipeline,
)
from validation.orchestration.stage_products import (
    ScientificStageProductStore,
)
from validation.orchestration.stages.root_cause_input import (
    StoredRootCauseStageInputProvider,
)


def test_build_scientific_pipeline_shares_one_product_store() -> None:
    store = ScientificStageProductStore()

    pipeline = build_scientific_pipeline(
        module_name="Hypertension",
        product_store=store,
        provider_metadata={"pilot": "hypertension"},
    )

    assert isinstance(pipeline, ScientificPipeline)
    assert pipeline.product_store is store
    assert pipeline.knowledge_handler.product_store is store

    provider = pipeline.root_cause_handler.input_provider
    assert isinstance(provider, StoredRootCauseStageInputProvider)
    assert provider.product_store is store
    assert provider.module_name == "Hypertension"
    assert provider.metadata["pilot"] == "hypertension"


def test_handlers_are_exposed_in_mandatory_scientific_order() -> None:
    pipeline = build_scientific_pipeline(
        module_name="Hypertension",
    )

    assert pipeline.handlers == (
        pipeline.knowledge_handler,
        pipeline.root_cause_handler,
    )


def test_build_scientific_pipeline_rejects_implicit_module_selection() -> None:
    with pytest.raises(
        ValueError,
        match="module_name must not be empty",
    ):
        build_scientific_pipeline(
            module_name="   ",
        )


def test_pipeline_rejects_handlers_wired_to_different_stores() -> None:
    first = build_scientific_pipeline(
        module_name="Hypertension",
    )
    second = build_scientific_pipeline(
        module_name="Hypertension",
    )

    with pytest.raises(
        ValueError,
        match="knowledge_handler must publish to product_store",
    ):
        ScientificPipeline(
            product_store=first.product_store,
            knowledge_handler=second.knowledge_handler,
            root_cause_handler=first.root_cause_handler,
        )