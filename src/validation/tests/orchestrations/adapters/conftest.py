"""Shared fixtures for Root Cause orchestration adapter tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from validation.interpretation.models import InterpretationReport
from validation.knowledge.models import (
    CausalCertainty,
    DetectionSignal,
    InvestigationCase,
    InvestigationStatus,
    KnowledgeEntry,
    KnowledgeEntryStatus,
)
from validation.orchestration.models import (
    CohortConfig,
    ExperimentConfig,
    ReportFormat,
    SimulatorConfig,
    SimulatorKind,
)


NOW = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)


@pytest.fixture
def experiment_config(
    tmp_path: Path,
) -> ExperimentConfig:
    """Return a complete deterministic experiment configuration."""

    synthea_directory = tmp_path / "synthea"
    psynthea_directory = tmp_path / "psynthea"

    synthea_directory.mkdir()
    psynthea_directory.mkdir()

    return ExperimentConfig(
        id="hypertension-validation",
        name="Hypertension equivalence validation",
        cohort=CohortConfig(
            population=100,
            seed=42,
            modules=("hypertension",),
            reference_date=date(2026, 1, 1),
        ),
        simulators=(
            SimulatorConfig(
                kind=SimulatorKind.SYNTHEA,
                command=("synthea",),
                working_directory=synthea_directory,
                output_subdirectory="cohort",
            ),
            SimulatorConfig(
                kind=SimulatorKind.PSYNTHEA,
                command=("psynthea",),
                working_directory=psynthea_directory,
                output_subdirectory="cohort",
            ),
        ),
        output_root=tmp_path / "runs",
        report_formats=(ReportFormat.HTML,),
        description=(
            "Deterministic Synthea versus Psynthea validation experiment."
        ),
        tags=("hypertension", "root-cause"),
    )


@pytest.fixture
def interpretation_report() -> InterpretationReport:
    """Return an empty but valid interpretation report.

    Individual tests may replace ``pipeline_run_id`` and findings as needed.
    """

    return InterpretationReport(
        report_id="interpretation.report",
        pipeline_run_id="run-001",
        findings=(),
        evidence=(),
        generated_at=NOW,
        engine_version="test-engine",
        module_name="hypertension",
    )


@pytest.fixture
def investigation_case() -> InvestigationCase:
    """Return a minimal valid open investigation case."""

    signal = DetectionSignal(
        id="signal.prevalence",
        domain="epidemiological",
        summary="Hypertension prevalence differs between simulators.",
        finding_id="finding.prevalence",
        metric_id="hypertension.prevalence",
        observed_value={
            "synthea": 0.31,
            "psynthea": 0.27,
        },
        source="interpretation_engine",
    )

    return InvestigationCase(
        id="investigation.hypertension-prevalence",
        title="Hypertension prevalence divergence",
        status=InvestigationStatus.OPEN,
        signals=(signal,),
        opened_at=NOW,
        updated_at=NOW,
        owner="IRYCIS-validation",
    )


@pytest.fixture
def knowledge_entry() -> KnowledgeEntry:
    """Return a minimal draft knowledge entry.

    Draft status deliberately avoids requiring confirmed evidence,
    verification and recommended actions.
    """

    return KnowledgeEntry(
        id="knowledge.hypertension-prevalence",
        title="Potential prevalence calibration divergence",
        status=KnowledgeEntryStatus.DRAFT,
        category_id="calibration.prevalence",
        detection_pattern=(
            "The two simulators produce different hypertension prevalence "
            "under an equivalent deterministic configuration."
        ),
        root_cause=(
            "A difference in module probability interpretation or population "
            "calibration may explain the observed divergence."
        ),
        causal_certainty=CausalCertainty.HYPOTHETICAL,
        source_investigation_id="investigation.hypertension-prevalence",
        source_hypothesis_id="hypothesis.calibration-difference",
        evidence=(),
        verifications=(),
        recommended_actions=(),
        applicability=(
            "Deterministic hypertension equivalence experiments",
        ),
        limitations=(
            "The hypothesis has not yet been verified.",
        ),
        created_at=NOW,
        updated_at=NOW,
    )