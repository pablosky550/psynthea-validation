"""Tests for the production orchestration composition boundary."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from validation.orchestration.models import ExperimentStage
from validation.orchestration.orchestrator import StageOutput
from validation.orchestration.production import build_production_orchestrator


@dataclass(frozen=True, slots=True)
class _Handler:
    stage: ExperimentStage

    def execute(self, context: object) -> StageOutput:
        return StageOutput(summary=f"Executed {self.stage.value}.")


def _patch_concrete_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "validation.orchestration.production._cohort_loading_handler",
        lambda: _Handler(ExperimentStage.COHORT_LOADING),
    )
    monkeypatch.setattr(
        "validation.orchestration.production._cohort_normalization_handler",
        lambda: _Handler(ExperimentStage.COHORT_NORMALIZATION),
    )
    monkeypatch.setattr(
        "validation.orchestration.production._validation_handler",
        lambda: _Handler(ExperimentStage.VALIDATION),
    )
    monkeypatch.setattr(
        "validation.orchestration.production._report_generation_handler",
        lambda: _Handler(ExperimentStage.REPORT_GENERATION),
    )


def test_build_production_orchestrator_registers_complete_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_concrete_handlers(monkeypatch)

    orchestrator = build_production_orchestrator(
        module_name="Hypertension",
    )

    assert tuple(orchestrator.handlers) == (
        ExperimentStage.COHORT_LOADING,
        ExperimentStage.COHORT_NORMALIZATION,
        ExperimentStage.VALIDATION,
        ExperimentStage.KNOWLEDGE_ENRICHMENT,
        ExperimentStage.ROOT_CAUSE_ANALYSIS,
        ExperimentStage.REPORT_GENERATION,
    )
    assert (
        orchestrator.handlers[ExperimentStage.KNOWLEDGE_ENRICHMENT]
        is orchestrator.scientific_pipeline.knowledge_handler
    )
    assert (
        orchestrator.handlers[ExperimentStage.ROOT_CAUSE_ANALYSIS]
        is orchestrator.scientific_pipeline.root_cause_handler
    )


def test_build_production_orchestrator_propagates_scientific_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_concrete_handlers(monkeypatch)

    orchestrator = build_production_orchestrator(
        module_name="Hypertension",
        provider_metadata={"composition": "production"},
    )

    provider = (
        orchestrator.scientific_pipeline.root_cause_handler.input_provider
    )
    assert provider.module_name == "Hypertension"
    assert provider.metadata["composition"] == "production"


def test_build_production_orchestrator_rejects_empty_module_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_concrete_handlers(monkeypatch)

    with pytest.raises(ValueError, match="module_name must not be empty"):
        build_production_orchestrator(module_name="  ")


def test_concrete_handler_factory_failure_is_not_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "validation.orchestration.production._cohort_loading_handler",
        lambda: (_ for _ in ()).throw(RuntimeError("loading unavailable")),
    )

    with pytest.raises(RuntimeError, match="loading unavailable"):
        build_production_orchestrator(module_name="Hypertension")