from __future__ import annotations

from dataclasses import dataclass

import pytest

from validation.orchestration import (
    ExperimentOrchestrator,
    ExperimentStage,
    StageOutput,
    build_experiment_orchestrator,
)
from validation.orchestration.scientific_pipeline import (
    build_scientific_pipeline,
)


@dataclass(frozen=True, slots=True)
class _Handler:
    stage: ExperimentStage

    def execute(self, context: object) -> StageOutput:
        return StageOutput(summary=f"Executed {self.stage.value}.")


def _handler(stage: ExperimentStage) -> _Handler:
    return _Handler(stage=stage)


def test_build_experiment_orchestrator_registers_canonical_stage_order() -> None:
    scientific = build_scientific_pipeline(
        module_name="Hypertension",
    )

    orchestrator = build_experiment_orchestrator(
        cohort_loading_handler=_handler(
            ExperimentStage.COHORT_LOADING
        ),
        cohort_normalization_handler=_handler(
            ExperimentStage.COHORT_NORMALIZATION
        ),
        validation_handler=_handler(
            ExperimentStage.VALIDATION
        ),
        scientific_pipeline=scientific,
        report_generation_handler=_handler(
            ExperimentStage.REPORT_GENERATION
        ),
    )

    assert isinstance(orchestrator, ExperimentOrchestrator)
    assert tuple(orchestrator.handlers) == (
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
        ExperimentStage.KNOWLEDGE_ENRICHMENT,
        ExperimentStage.ROOT_CAUSE_ANALYSIS,
        ExperimentStage.REPORT_GENERATION,
    )
    assert (
        orchestrator.handlers[
            ExperimentStage.KNOWLEDGE_ENRICHMENT
        ]
        is scientific.knowledge_handler
    )
    assert (
        orchestrator.handlers[
            ExperimentStage.ROOT_CAUSE_ANALYSIS
        ]
        is scientific.root_cause_handler
    )


def test_build_experiment_orchestrator_rejects_wrong_stage_role() -> None:
    scientific = build_scientific_pipeline(
        module_name="Hypertension",
    )

    with pytest.raises(
        ValueError,
        match="cohort_loading_handler.stage must be 'cohort_loading'",
    ):
        build_experiment_orchestrator(
            cohort_loading_handler=_handler(
                ExperimentStage.VALIDATION
            ),
            cohort_normalization_handler=_handler(
                ExperimentStage.COHORT_NORMALIZATION
            ),
            validation_handler=_handler(
                ExperimentStage.VALIDATION
            ),
            scientific_pipeline=scientific,
            report_generation_handler=_handler(
                ExperimentStage.REPORT_GENERATION
            ),
        )


def test_build_experiment_orchestrator_requires_scientific_pipeline() -> None:
    with pytest.raises(
        TypeError,
        match="scientific_pipeline must be a ScientificPipeline",
    ):
        build_experiment_orchestrator(
            cohort_loading_handler=_handler(
                ExperimentStage.COHORT_LOADING
            ),
            cohort_normalization_handler=_handler(
                ExperimentStage.COHORT_NORMALIZATION
            ),
            validation_handler=_handler(
                ExperimentStage.VALIDATION
            ),
            scientific_pipeline=object(),  # type: ignore[arg-type]
            report_generation_handler=_handler(
                ExperimentStage.REPORT_GENERATION
            ),
        )



def test_scientific_orchestrator_clears_run_when_execution_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scientific = build_scientific_pipeline(
        module_name="Hypertension",
    )
    cleared: list[str] = []

    from validation.orchestration.stage_products import (
        ScientificStageProductStore,
    )

    real_clear_run = ScientificStageProductStore.clear_run

    def clear_and_capture(self, run_id):
        cleared.append(run_id)
        real_clear_run(self, run_id)

    monkeypatch.setattr(
        ScientificStageProductStore,
        "clear_run",
        clear_and_capture,
    )

    def fail_execute(self, config, *, run_id=None):
        raise RuntimeError("forced orchestration failure")

    monkeypatch.setattr(
        ExperimentOrchestrator,
        "execute",
        fail_execute,
    )

    orchestrator = build_experiment_orchestrator(
        cohort_loading_handler=_handler(
            ExperimentStage.COHORT_LOADING
        ),
        cohort_normalization_handler=_handler(
            ExperimentStage.COHORT_NORMALIZATION
        ),
        validation_handler=_handler(
            ExperimentStage.VALIDATION
        ),
        scientific_pipeline=scientific,
        report_generation_handler=_handler(
            ExperimentStage.REPORT_GENERATION
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="forced orchestration failure",
    ):
        orchestrator.execute(
            object(),  # type: ignore[arg-type]
            run_id="failed-scientific-run",
        )

    assert cleared == ["failed-scientific-run"]