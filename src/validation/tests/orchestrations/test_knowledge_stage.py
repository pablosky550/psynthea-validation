from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from validation.orchestration.models import (
    ArtifactKind,
)
from validation.orchestration.orchestrator import (
    OrchestrationContext,
)
from validation.orchestration.stages.knowledge import (
    KnowledgeStageError,
    KnowledgeStageHandler,
)
from validation.orchestration.stages.validation import (
    ValidationStageHandler,
)

from validation.tests.orchestrations.test_validation_stage import (
    _context as _validation_context,
)


_FIXED_TIME = datetime(
    2026,
    7,
    16,
    8,
    0,
    tzinfo=UTC,
)


def _context(
    tmp_path: Path,
):
    workspace, validation_context = (
        _validation_context(tmp_path)
    )

    validation_output = (
        ValidationStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(validation_context)
    )

    context = OrchestrationContext(
        config=validation_context.config,
        workspace=workspace,
        run_id=validation_context.run_id,
        simulator_runs=(
            validation_context.simulator_runs
        ),
        stage_results=(
            validation_context.stage_results
        ),
        artifacts=(
            *validation_context.artifacts,
            *validation_output.artifacts,
        ),
    )

    return workspace, context


def test_stage_executes_real_interpretation_and_persists_outputs(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    output = KnowledgeStageHandler(
        clock=lambda: _FIXED_TIME
    ).execute(context)

    knowledge_results = [
        artifact
        for artifact in output.artifacts
        if artifact.kind
        is ArtifactKind.KNOWLEDGE_RESULT
    ]

    reports = [
        artifact
        for artifact in output.artifacts
        if artifact.kind
        is ArtifactKind.REPORT
    ]

    evidence = [
        artifact
        for artifact in output.artifacts
        if artifact.kind
        is ArtifactKind.EVIDENCE
    ]

    assert len(knowledge_results) == 1
    assert len(reports) == 1
    assert len(evidence) == 1

    payload = json.loads(
        workspace.resolve(
            knowledge_results[0].path
        ).read_text()
    )

    assert payload["schema_version"] == "1.0"

    assert (
        payload["experiment_id"]
        == context.config.id
    )

    assert payload["run_id"] == (
        context.run_id
    )

    assert (
        payload["aggregate"]["module_count"]
        == 1
    )

    module = payload["modules"][0]

    assert module["module_name"] == (
        "hypertension"
    )

    assert isinstance(
        module["interpretation_report"][
            "findings"
        ],
        list,
    )

    assert len(
        module["workflow_fingerprint"]
    ) == 64

    assert len(
        module[
            "evidence_catalog_fingerprint"
        ]
    ) == 64

    assert len(
        module["document_fingerprint"]
    ) == 64

    assert output.metadata[
        "module_count"
    ] == 1


def test_stage_preserves_validation_and_normalization_provenance(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    output = KnowledgeStageHandler(
        clock=lambda: _FIXED_TIME
    ).execute(context)

    knowledge_artifact = next(
        artifact
        for artifact in output.artifacts
        if artifact.kind
        is ArtifactKind.KNOWLEDGE_RESULT
    )

    payload = json.loads(
        workspace.resolve(
            knowledge_artifact.path
        ).read_text()
    )

    assert (
        payload[
            "source_validation_artifact"
        ]["artifact_id"]
    )

    assert (
        payload[
            "source_normalization_artifact"
        ]["artifact_id"]
    )

    assert len(
        payload[
            "source_validation_artifact"
        ]["sha256"]
    ) == 64

    assert len(
        payload[
            "source_normalization_artifact"
        ]["sha256"]
    ) == 64


def test_stage_rejects_missing_validation_result(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    invalid_context = OrchestrationContext(
        config=context.config,
        workspace=workspace,
        run_id=context.run_id,
        simulator_runs=(
            context.simulator_runs
        ),
        stage_results=(
            context.stage_results
        ),
        artifacts=tuple(
            artifact
            for artifact in context.artifacts
            if artifact.kind
            is not ArtifactKind.VALIDATION_RESULT
        ),
    )

    with pytest.raises(
        KnowledgeStageError,
        match="exactly one validation result",
    ):
        KnowledgeStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(invalid_context)


def test_stage_rejects_modified_validation_evidence(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    evidence_artifact = next(
        artifact
        for artifact in context.artifacts
        if (
            artifact.kind
            is ArtifactKind.EVIDENCE
            and artifact.producer
            == "validation_stage"
        )
    )

    workspace.resolve(
        evidence_artifact.path
    ).write_text(
        "tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(
        KnowledgeStageError,
        match="changed",
    ):
        KnowledgeStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(context)


def test_stage_rejects_unknown_knowledge_configuration(
    tmp_path: Path,
) -> None:
    workspace, context = _context(
        tmp_path
    )

    config_type = type(context.config)

    invalid_config = config_type(
        id=context.config.id,
        name=context.config.name,
        cohort=context.config.cohort,
        simulators=context.config.simulators,
        output_root=context.config.output_root,
        report_formats=(
            context.config.report_formats
        ),
        metadata={
            **dict(context.config.metadata),
            "knowledge": {
                "unknown": True
            },
        },
    )

    invalid_context = OrchestrationContext(
        config=invalid_config,
        workspace=workspace,
        run_id=context.run_id,
        simulator_runs=(
            context.simulator_runs
        ),
        stage_results=(
            context.stage_results
        ),
        artifacts=context.artifacts,
    )

    with pytest.raises(
        KnowledgeStageError,
        match="unknown field",
    ):
        KnowledgeStageHandler(
            clock=lambda: _FIXED_TIME
        ).execute(invalid_context)


def test_stage_requires_timezone_aware_clock(
    tmp_path: Path,
) -> None:
    _, context = _context(
        tmp_path
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        KnowledgeStageHandler(
            clock=lambda: datetime(
                2026,
                7,
                16,
                8,
                0,
            )
        ).execute(context)