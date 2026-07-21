"""Scientific knowledge-enrichment stage.

This stage converts the functional and statistical outputs produced by the
validation stage into evidence-backed scientific interpretation.

The stage deliberately does not infer or publish causal knowledge. A detected
difference is not a demonstrated root cause. ``InvestigationCase`` and
``KnowledgeEntry`` objects belong to the downstream root-cause lifecycle and
must only be created after explicit causal verification.

Responsibilities
----------------
* Locate and verify the canonical validation-result artefact.
* Verify and reconstruct every module validation result.
* Reconstruct the normalized cohorts referenced by validation provenance.
* Execute the real ``InterpretationWorkflow`` for every configured module.
* Persist one JSON and one Markdown interpretation report per module.
* Persist one aggregate, machine-readable knowledge-stage result.
* Preserve fingerprints, evidence provenance and research-use decisions.

The stage performs no statistical recalculation, root-cause attribution or
final experiment-report composition.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import pandas as pd

from validation.comparison.module_validation import (
    ModuleValidationResult,
)
from validation.comparison.statistical_comparison import (
    ModuleStatisticalComparisonResult,
)
from validation.constants import (
    CSV_FILES,
    SOURCE_PSYNTHEA,
    SOURCE_SYNTHEA,
)
from validation.interpretation import (
    InterpretationInput,
    InterpretationWorkflow,
    InterpretationWorkflowConfig,
    InterpretationWorkflowResult,
    PipelineStage,
    render_json_report,
    render_markdown_report,
)
from validation.models import ValidationCohort
from validation.orchestration.models import (
    ArtifactKind,
    ArtifactReference,
    ExperimentStage,
    SimulatorKind,
)
from validation.orchestration.orchestrator import (
    OrchestrationContext,
    StageOutput,
)
from validation.orchestration.stage_products import (
    ScientificStageProductStore,
)

__all__ = [
    "InterpretationWorkflowFactory",
    "KnowledgeStageError",
    "KnowledgeStageHandler",
]


_KNOWLEDGE_SCHEMA_VERSION: Final = "1.0"
_SUPPORTED_VALIDATION_SCHEMA_VERSION: Final = "1.0"
_SUPPORTED_NORMALIZATION_SCHEMA_VERSION: Final = "1.0"

_KNOWLEDGE_RESULT_PATH: Final = (
    "knowledge/knowledge_result.json"
)

_KNOWLEDGE_PRODUCER: Final = "knowledge_stage"
_VALIDATION_PRODUCER: Final = "validation_stage"
_NORMALIZATION_PRODUCER: Final = (
    "cohort_normalization_stage"
)

_FUNCTIONAL_TABLES: Final[
    Mapping[str, str]
] = MappingProxyType(
    {
        "table_status": (
            "functional_table_status"
        ),
        "clinical_signal": (
            "functional_clinical_signal"
        ),
        "distributional_similarity": (
            "functional_distributional_similarity"
        ),
        "issues": "functional_issues",
        "summary": "functional_summary",
    }
)

_STATISTICAL_TABLES: Final[
    Mapping[str, str]
] = MappingProxyType(
    {
        "continuous_tests": "continuous_tests",
        "categorical_tests": "categorical_tests",
        "prevalence_tests": "prevalence_tests",
        "distribution_tests": "distribution_tests",
        "summary": "statistical_summary",
    }
)

_EXPECTED_SOURCE: Final[
    Mapping[SimulatorKind, str]
] = MappingProxyType(
    {
        SimulatorKind.SYNTHEA: SOURCE_SYNTHEA,
        SimulatorKind.PSYNTHEA: SOURCE_PSYNTHEA,
    }
)

InterpretationWorkflowFactory = Callable[
    [],
    InterpretationWorkflow,
]


class KnowledgeStageError(RuntimeError):
    """Raised when scientific interpretation cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class KnowledgeStageHandler:
    """Execute evidence-backed interpretation for every validated module."""

    workflow_factory: InterpretationWorkflowFactory = (
        InterpretationWorkflow
    )
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    product_store: ScientificStageProductStore | None = None

    stage: ExperimentStage = field(
        default=ExperimentStage.KNOWLEDGE_ENRICHMENT,
        init=False,
    )

    def __post_init__(self) -> None:
        if not callable(self.workflow_factory):
            raise TypeError(
                "workflow_factory must be callable."
            )

        if not callable(self.clock):
            raise TypeError(
                "clock must be callable."
            )
        if (
            self.product_store is not None
            and not isinstance(
                self.product_store,
                ScientificStageProductStore,
            )
        ):
            raise TypeError(
                "product_store must be a ScientificStageProductStore or None."
            )

    def execute(
        self,
        context: OrchestrationContext,
    ) -> StageOutput:
        """Interpret every canonical validation module result."""

        if not isinstance(
            context,
            OrchestrationContext,
        ):
            raise TypeError(
                "context must be an "
                "OrchestrationContext."
            )

        generated_at = _aware_datetime(
            self.clock(),
            "clock result",
        )

        validation_artifact = (
            _single_artifact(
                context.artifacts,
                kind=ArtifactKind.VALIDATION_RESULT,
                producer=_VALIDATION_PRODUCER,
                description="validation result",
            )
        )

        validation_payload = (
            _read_verified_json_artifact(
                context,
                validation_artifact,
                error_context="validation result",
            )
        )

        _validate_validation_payload(
            validation_payload,
            context=context,
        )

        normalization_artifact = (
            _normalization_artifact_from_validation(
                context,
                validation_payload,
            )
        )

        normalization_payload = (
            _read_verified_json_artifact(
                context,
                normalization_artifact,
                error_context=(
                    "normalization result"
                ),
            )
        )

        _validate_normalization_payload(
            normalization_payload,
            context=context,
        )

        cohorts = {
            simulator: _load_normalized_cohort(
                context,
                simulator=simulator,
                normalization_payload=(
                    normalization_payload
                ),
            )
            for simulator in SimulatorKind
        }

        settings = _knowledge_settings(
            context.config.metadata
        )

        module_payloads = validation_payload[
            "modules"
        ]

        generated_artifacts: list[
            ArtifactReference
        ] = []

        knowledge_modules: list[
            Mapping[str, Any]
        ] = []

        for module_payload in module_payloads:
            comparison = (
                _reconstruct_module_result(
                    context,
                    module_payload=module_payload,
                    cohorts=cohorts,
                )
            )

            workflow = self.workflow_factory()

            if not isinstance(
                workflow,
                InterpretationWorkflow,
            ):
                raise KnowledgeStageError(
                    "workflow_factory returned "
                    f"{type(workflow).__name__}; "
                    "expected InterpretationWorkflow."
                )

            workflow_result = _execute_workflow(
                workflow,
                comparison=comparison,
                context=context,
                settings=settings,
            )

            if self.product_store is not None:
                self.product_store.publish_interpretation(
                    run_id=context.run_id,
                    result=workflow_result,
                )

            (
                module_artifacts,
                serialized_module,
            ) = _persist_module_knowledge(
                context,
                workflow_result=workflow_result,
                generated_at=generated_at,
            )

            generated_artifacts.extend(
                module_artifacts
            )

            knowledge_modules.append(
                serialized_module
            )

        aggregate = _aggregate_modules(
            knowledge_modules
        )

        result_payload = {
            "schema_version": (
                _KNOWLEDGE_SCHEMA_VERSION
            ),
            "experiment_id": context.config.id,
            "run_id": context.run_id,
            "generated_at": (
                generated_at.isoformat()
            ),
            "source_validation_artifact": {
                "artifact_id": (
                    validation_artifact.id
                ),
                "path": (
                    validation_artifact.path
                    .as_posix()
                ),
                "sha256": (
                    validation_artifact.sha256
                ),
                "size_bytes": (
                    validation_artifact.size_bytes
                ),
            },
            "source_normalization_artifact": {
                "artifact_id": (
                    normalization_artifact.id
                ),
                "path": (
                    normalization_artifact.path
                    .as_posix()
                ),
                "sha256": (
                    normalization_artifact.sha256
                ),
                "size_bytes": (
                    normalization_artifact.size_bytes
                ),
            },
            "configuration": {
                "research_use": (
                    settings["research_use"]
                ),
                "strict_evidence": (
                    settings["strict_evidence"]
                ),
            },
            "aggregate": aggregate,
            "modules": knowledge_modules,
        }

        result_path = context.workspace.write_json(
            _KNOWLEDGE_RESULT_PATH,
            result_payload,
        )

        knowledge_artifact = (
            context.workspace.artifact_reference(
                artifact_id=(
                    f"{context.config.id}:"
                    f"{context.run_id}:"
                    "knowledge-result"
                ),
                kind=ArtifactKind.KNOWLEDGE_RESULT,
                path=result_path,
                media_type="application/json",
                producer=_KNOWLEDGE_PRODUCER,
                created_at=generated_at,
                metadata={
                    "schema_version": (
                        _KNOWLEDGE_SCHEMA_VERSION
                    ),
                    **aggregate,
                },
            )
        )

        return StageOutput(
            artifacts=(
                *generated_artifacts,
                knowledge_artifact,
            ),
            summary=(
                "Executed scientific interpretation "
                f"for {aggregate['module_count']} "
                "module(s); "
                f"{aggregate['research_ready_count']} "
                "are ready for research use and "
                f"{aggregate['blocking_finding_count']} "
                "blocking finding(s) were identified."
            ),
            metadata={
                "schema_version": (
                    _KNOWLEDGE_SCHEMA_VERSION
                ),
                **aggregate,
                "knowledge_result_artifact_id": (
                    knowledge_artifact.id
                ),
            },
        )

def _execute_workflow(
    workflow: InterpretationWorkflow,
    *,
    comparison: ModuleStatisticalComparisonResult,
    context: OrchestrationContext,
    settings: Mapping[str, Any],
) -> InterpretationWorkflowResult:
    module_name = comparison.module_name

    functional_result = comparison.validation

    if not isinstance(
        functional_result,
        ModuleValidationResult,
    ):
        raise KnowledgeStageError(
            "Scientific interpretation requires "
            "the functional validation result for "
            f"module {module_name!r}."
        )

    config = InterpretationWorkflowConfig(
        validation_id=(
            f"{context.config.id}."
            f"{module_name}"
        ),
        pipeline_run_id=context.run_id,
        module_name=module_name,
        report_id=(
            f"{context.config.id}."
            f"{context.run_id}."
            f"{module_name}."
            "interpretation"
        ),
        research_use=settings[
            "research_use"
        ],
        strict_evidence=settings[
            "strict_evidence"
        ],
        metadata={
            "experiment_id": (
                context.config.id
            ),
            "orchestrator_run_id": (
                context.run_id
            ),
            "source_stage": (
                ExperimentStage.VALIDATION.value
            ),
        },
    )

    try:
        return workflow.run(
            (
                InterpretationInput(
                    stage=(
                        PipelineStage
                        .FUNCTIONAL_VALIDATION
                    ),
                    source=functional_result,
                    label=(
                        f"{module_name}."
                        "functional"
                    ),
                ),
                InterpretationInput(
                    stage=(
                        PipelineStage
                        .STATISTICAL_VALIDATION
                    ),
                    source=comparison,
                    label=(
                        f"{module_name}."
                        "statistical"
                    ),
                ),
            ),
            config=config,
        )
    except Exception as exc:
        raise KnowledgeStageError(
            "Scientific interpretation failed "
            f"for module {module_name!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

def _reconstruct_module_result(
    context: OrchestrationContext,
    *,
    module_payload: Mapping[str, Any],
    cohorts: Mapping[
        SimulatorKind,
        ValidationCohort,
    ],
) -> ModuleStatisticalComparisonResult:
    if not isinstance(
        module_payload,
        Mapping,
    ):
        raise KnowledgeStageError(
            "Validation module payload must be "
            "an object."
        )

    module_name = module_payload.get(
        "module_name"
    )

    if (
        not isinstance(module_name, str)
        or not module_name.strip()
    ):
        raise KnowledgeStageError(
            "Validation module payload has no "
            "valid module_name."
        )

    module_name = module_name.strip()

    tables = module_payload.get(
        "tables"
    )

    if not isinstance(tables, Mapping):
        raise KnowledgeStageError(
            f"Validation module {module_name!r} "
            "has no table catalogue."
        )

    functional_frames = {
        attribute: _load_validation_table(
            context,
            tables=tables,
            table_key=table_key,
            module_name=module_name,
        )
        for attribute, table_key
        in _FUNCTIONAL_TABLES.items()
    }

    statistical_frames = {
        attribute: _load_validation_table(
            context,
            tables=tables,
            table_key=table_key,
            module_name=module_name,
        )
        for attribute, table_key
        in _STATISTICAL_TABLES.items()
    }

    functional_result = ModuleValidationResult(
        module_name=module_name,
        synthea_cohort=cohorts[
            SimulatorKind.SYNTHEA
        ],
        psynthea_cohort=cohorts[
            SimulatorKind.PSYNTHEA
        ],
        table_status=functional_frames[
            "table_status"
        ],
        clinical_signal=functional_frames[
            "clinical_signal"
        ],
        distributional_similarity=(
            functional_frames[
                "distributional_similarity"
            ]
        ),
        issues=functional_frames["issues"],
        summary=functional_frames["summary"],
    )

    return ModuleStatisticalComparisonResult(
        module_name=module_name,
        validation=functional_result,
        continuous_tests=statistical_frames[
            "continuous_tests"
        ],
        categorical_tests=statistical_frames[
            "categorical_tests"
        ],
        prevalence_tests=statistical_frames[
            "prevalence_tests"
        ],
        distribution_tests=statistical_frames[
            "distribution_tests"
        ],
        summary=statistical_frames["summary"],
    )


def _load_validation_table(
    context: OrchestrationContext,
    *,
    tables: Mapping[str, Any],
    table_key: str,
    module_name: str,
) -> pd.DataFrame:
    table_payload = tables.get(
        table_key
    )

    if not isinstance(
        table_payload,
        Mapping,
    ):
        raise KnowledgeStageError(
            f"Validation module {module_name!r} "
            f"is missing table {table_key!r}."
        )

    relative_path = table_payload.get(
        "path"
    )

    if not isinstance(
        relative_path,
        str,
    ):
        raise KnowledgeStageError(
            f"Validation table "
            f"{module_name}.{table_key} "
            "has no valid path."
        )

    path = context.workspace.resolve(
        relative_path
    )

    _verify_file_identity(
        path,
        expected_sha256=(
            table_payload.get("sha256")
        ),
        expected_size=(
            table_payload.get("size_bytes")
        ),
        description=(
            f"{module_name}.{table_key}"
        ),
    )

    dataframe = _read_csv(
        path,
        description=(
            f"{module_name}.{table_key}"
        ),
    )

    expected_rows = table_payload.get(
        "rows"
    )

    if (
        isinstance(expected_rows, int)
        and len(dataframe) != expected_rows
    ):
        raise KnowledgeStageError(
            "Validation evidence row count "
            "changed after validation for "
            f"{module_name}.{table_key}."
        )

    expected_columns = table_payload.get(
        "columns"
    )

    if isinstance(
        expected_columns,
        Sequence,
    ) and not isinstance(
        expected_columns,
        (str, bytes),
    ):
        observed_columns = [
            str(column)
            for column in dataframe.columns
        ]

        if observed_columns != list(
            expected_columns
        ):
            raise KnowledgeStageError(
                "Validation evidence columns "
                "changed after validation for "
                f"{module_name}.{table_key}."
            )

    return dataframe


def _normalization_artifact_from_validation(
    context: OrchestrationContext,
    validation_payload: Mapping[str, Any],
) -> ArtifactReference:
    source = validation_payload.get(
        "source_normalization_artifact"
    )

    if not isinstance(source, Mapping):
        raise KnowledgeStageError(
            "Validation result does not declare "
            "its normalization provenance."
        )

    artifact_id = source.get(
        "artifact_id"
    )

    path = source.get("path")
    digest = source.get("sha256")
    size_bytes = source.get(
        "size_bytes"
    )

    candidates = [
        artifact
        for artifact in context.artifacts
        if (
            artifact.kind
            is ArtifactKind.COHORT_NORMALIZATION_RESULT
            and artifact.producer
            == _NORMALIZATION_PRODUCER
        )
    ]

    if len(candidates) != 1:
        raise KnowledgeStageError(
            "Knowledge enrichment requires "
            "exactly one normalization-result "
            f"artifact; found {len(candidates)}."
        )

    artifact = candidates[0]

    if artifact.id != artifact_id:
        raise KnowledgeStageError(
            "Validation normalization artifact_id "
            "does not match the orchestration "
            "artifact catalogue."
        )

    if artifact.path.as_posix() != path:
        raise KnowledgeStageError(
            "Validation normalization path does "
            "not match the orchestration artifact "
            "catalogue."
        )

    if artifact.sha256 != digest:
        raise KnowledgeStageError(
            "Validation normalization hash does "
            "not match the orchestration artifact "
            "catalogue."
        )

    if artifact.size_bytes != size_bytes:
        raise KnowledgeStageError(
            "Validation normalization size does "
            "not match the orchestration artifact "
            "catalogue."
        )

    return artifact


def _load_normalized_cohort(
    context: OrchestrationContext,
    *,
    simulator: SimulatorKind,
    normalization_payload: Mapping[
        str,
        Any,
    ],
) -> ValidationCohort:
    cohort_payload = normalization_payload[
        "cohorts"
    ][simulator.value]

    if not isinstance(
        cohort_payload,
        Mapping,
    ):
        raise KnowledgeStageError(
            "Invalid normalization payload for "
            f"{simulator.value}."
        )

    expected_source = _EXPECTED_SOURCE[
        simulator
    ]

    if (
        cohort_payload.get("source")
        != expected_source
    ):
        raise KnowledgeStageError(
            "Unexpected normalized cohort source "
            f"for {simulator.value}."
        )

    table_catalogue = cohort_payload.get(
        "tables"
    )

    if not isinstance(
        table_catalogue,
        Mapping,
    ):
        raise KnowledgeStageError(
            "Missing normalized table catalogue "
            f"for {simulator.value}."
        )

    tables: dict[str, pd.DataFrame] = {}

    for table_name in CSV_FILES:
        table_payload = table_catalogue.get(
            table_name
        )

        if not isinstance(
            table_payload,
            Mapping,
        ):
            raise KnowledgeStageError(
                "Missing normalized table "
                f"{simulator.value}."
                f"{table_name}."
            )

        relative_path = table_payload.get(
            "path"
        )

        if not isinstance(
            relative_path,
            str,
        ):
            raise KnowledgeStageError(
                "Missing normalized path for "
                f"{simulator.value}."
                f"{table_name}."
            )

        path = context.workspace.resolve(
            relative_path
        )

        _verify_file_identity(
            path,
            expected_sha256=(
                table_payload.get("sha256")
            ),
            expected_size=(
                table_payload.get(
                    "size_bytes"
                )
            ),
            description=(
                f"{simulator.value}."
                f"{table_name}"
            ),
        )

        tables[table_name] = _read_csv(
            path,
            description=(
                f"{simulator.value}."
                f"{table_name}"
            ),
        )

    cohort = ValidationCohort(
        source=expected_source,
        output_path=(
            context.workspace.resolve(
                Path("normalized")
                / simulator.value
            )
        ),
        patients=tables["patients"],
        encounters=tables["encounters"],
        conditions=tables["conditions"],
        medications=tables["medications"],
        procedures=tables["procedures"],
        observations=tables["observations"],
    )

    if (
        cohort.patients is None
        or cohort.patients.empty
    ):
        raise KnowledgeStageError(
            f"Normalized {simulator.value} "
            "cohort contains no patients."
        )

    return cohort


def _persist_module_knowledge(
    context: OrchestrationContext,
    *,
    workflow_result: InterpretationWorkflowResult,
    generated_at: datetime,
) -> tuple[
    tuple[ArtifactReference, ...],
    Mapping[str, Any],
]:
    module_name = (
        workflow_result.execution.report
        .module_name
    )

    if module_name is None:
        raise KnowledgeStageError(
            "Interpretation workflow result has "
            "no module_name."
        )

    module_directory = (
        Path("knowledge")
        / "modules"
        / module_name
    )

    json_path = context.workspace.write_text(
        module_directory
        / "interpretation_report.json",
        render_json_report(
            workflow_result.document
        ),
    )

    markdown_path = (
        context.workspace.write_text(
            module_directory
            / "interpretation_report.md",
            render_markdown_report(
                workflow_result.document
            ),
        )
    )

    json_artifact = (
        context.workspace.artifact_reference(
            artifact_id=(
                f"{context.config.id}:"
                f"{context.run_id}:"
                f"knowledge:{module_name}:json"
            ),
            kind=ArtifactKind.EVIDENCE,
            path=json_path,
            media_type="application/json",
            producer=_KNOWLEDGE_PRODUCER,
            created_at=generated_at,
            metadata={
                "module": module_name,
                "report_id": (
                    workflow_result.execution
                    .report.report_id
                ),
                "workflow_fingerprint": (
                    workflow_result
                    .workflow_fingerprint
                ),
                "document_fingerprint": (
                    workflow_result.document
                    .to_dict()[
                        "document_fingerprint"
                    ]
                ),
                "research_use_ready": (
                    workflow_result.summary
                    .research_use_ready
                ),
            },
        )
    )

    markdown_artifact = (
        context.workspace.artifact_reference(
            artifact_id=(
                f"{context.config.id}:"
                f"{context.run_id}:"
                f"knowledge:{module_name}:markdown"
            ),
            kind=ArtifactKind.REPORT,
            path=markdown_path,
            media_type=(
                "text/markdown; charset=utf-8"
            ),
            producer=_KNOWLEDGE_PRODUCER,
            created_at=generated_at,
            metadata={
                "report_type": (
                    "scientific_interpretation"
                ),
                "module": module_name,
                "report_id": (
                    workflow_result.execution
                    .report.report_id
                ),
                "workflow_fingerprint": (
                    workflow_result
                    .workflow_fingerprint
                ),
                "research_use_ready": (
                    workflow_result.summary
                    .research_use_ready
                ),
            },
        )
    )

    report = (
        workflow_result.execution.report
    )

    serialized = {
        "module_name": module_name,
        "report_id": report.report_id,
        "overall_status": (
            workflow_result.summary
            .overall_status.value
        ),
        "research_use_ready": (
            workflow_result.summary
            .research_use_ready
        ),
        "finding_count": len(
            report.findings
        ),
        "blocking_finding_count": len(
            report.blocking_findings
        ),
        "evidence_count": len(
            workflow_result.evidence
        ),
        "recommendation_count": len(
            workflow_result
            .recommendation_plan.items
        ),
        "incomplete_rule_count": (
            workflow_result.summary
            .incomplete_rule_count
        ),
        "workflow_fingerprint": (
            workflow_result
            .workflow_fingerprint
        ),
        "evidence_catalog_fingerprint": (
            workflow_result
            .evidence_catalog_fingerprint
        ),
        "document_fingerprint": (
            workflow_result.document
            .to_dict()[
                "document_fingerprint"
            ]
        ),
        "interpretation_report": (
            report.to_dict()
        ),
        "summary": (
            workflow_result.summary.to_dict()
        ),
        "recommendation_plan": (
            workflow_result
            .recommendation_plan.to_dict()
        ),
        "input_manifest": [
            _plain_value(item)
            for item
            in workflow_result.input_manifest
        ],
        "stage_statuses": {
            stage.value: status.value
            for stage, status
            in workflow_result
            .stage_statuses.items()
        },
        "artifacts": {
            "json": {
                "artifact_id": (
                    json_artifact.id
                ),
                "path": (
                    json_artifact.path
                    .as_posix()
                ),
                "sha256": (
                    json_artifact.sha256
                ),
                "size_bytes": (
                    json_artifact.size_bytes
                ),
            },
            "markdown": {
                "artifact_id": (
                    markdown_artifact.id
                ),
                "path": (
                    markdown_artifact.path
                    .as_posix()
                ),
                "sha256": (
                    markdown_artifact.sha256
                ),
                "size_bytes": (
                    markdown_artifact
                    .size_bytes
                ),
            },
        },
    }

    return (
        (
            json_artifact,
            markdown_artifact,
        ),
        serialized,
    )


def _aggregate_modules(
    modules: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "module_count": len(modules),
        "research_ready_count": sum(
            bool(
                module[
                    "research_use_ready"
                ]
            )
            for module in modules
        ),
        "finding_count": sum(
            int(module["finding_count"])
            for module in modules
        ),
        "blocking_finding_count": sum(
            int(
                module[
                    "blocking_finding_count"
                ]
            )
            for module in modules
        ),
        "recommendation_count": sum(
            int(
                module[
                    "recommendation_count"
                ]
            )
            for module in modules
        ),
        "incomplete_rule_count": sum(
            int(
                module[
                    "incomplete_rule_count"
                ]
            )
            for module in modules
        ),
    }


def _knowledge_settings(
    metadata: Mapping[str, Any],
) -> Mapping[str, bool]:
    if not isinstance(metadata, Mapping):
        raise TypeError(
            "experiment metadata must be a "
            "mapping."
        )

    raw = metadata.get(
        "knowledge",
        {},
    )

    if raw is None:
        raw = {}

    if not isinstance(raw, Mapping):
        raise KnowledgeStageError(
            "metadata.knowledge must be an "
            "object."
        )

    allowed = {
        "research_use",
        "strict_evidence",
    }

    unknown = sorted(
        set(raw) - allowed
    )

    if unknown:
        raise KnowledgeStageError(
            "metadata.knowledge contains unknown "
            "field(s): "
            + ", ".join(unknown)
            + "."
        )

    research_use = raw.get(
        "research_use",
        True,
    )

    strict_evidence = raw.get(
        "strict_evidence",
        True,
    )

    if not isinstance(
        research_use,
        bool,
    ):
        raise KnowledgeStageError(
            "metadata.knowledge.research_use "
            "must be a boolean."
        )

    if not isinstance(
        strict_evidence,
        bool,
    ):
        raise KnowledgeStageError(
            "metadata.knowledge.strict_evidence "
            "must be a boolean."
        )

    return MappingProxyType(
        {
            "research_use": research_use,
            "strict_evidence": (
                strict_evidence
            ),
        }
    )


def _validate_validation_payload(
    payload: Mapping[str, Any],
    *,
    context: OrchestrationContext,
) -> None:
    if (
        payload.get("schema_version")
        != _SUPPORTED_VALIDATION_SCHEMA_VERSION
    ):
        raise KnowledgeStageError(
            "Unsupported validation-result "
            f"schema: "
            f"{payload.get('schema_version')!r}."
        )

    if (
        payload.get("experiment_id")
        != context.config.id
    ):
        raise KnowledgeStageError(
            "Validation-result experiment_id "
            "does not match the active "
            "experiment."
        )

    if payload.get("run_id") != context.run_id:
        raise KnowledgeStageError(
            "Validation-result run_id does not "
            "match the active run."
        )

    modules = payload.get("modules")

    if (
        isinstance(modules, (str, bytes))
        or not isinstance(
            modules,
            Sequence,
        )
        or not modules
    ):
        raise KnowledgeStageError(
            "Validation result must contain at "
            "least one module result."
        )

    configured_modules = tuple(
        dict.fromkeys(
            (
                *context.config.cohort.modules,
                *(
                    module_file.stem
                    for module_file
                    in context.config.cohort.module_files
                ),
            )
        )
    )

    if not configured_modules:
        raise KnowledgeStageError(
            "ExperimentConfig must define at least "
            "one module through 'modules' or "
            "'module_files'."
        )

    observed_modules = tuple(
        module.get("module_name")
        if isinstance(module, Mapping)
        else None
        for module in modules
    )

    if observed_modules != configured_modules:
        raise KnowledgeStageError(
            "Validation-result module order does "
            "not match ExperimentConfig: "
            f"expected {configured_modules!r}, "
            f"observed {observed_modules!r}."
        )


def _validate_normalization_payload(
    payload: Mapping[str, Any],
    *,
    context: OrchestrationContext,
) -> None:
    if (
        payload.get("schema_version")
        != _SUPPORTED_NORMALIZATION_SCHEMA_VERSION
    ):
        raise KnowledgeStageError(
            "Unsupported normalization-result "
            f"schema: "
            f"{payload.get('schema_version')!r}."
        )

    if (
        payload.get("experiment_id")
        != context.config.id
    ):
        raise KnowledgeStageError(
            "Normalization experiment_id does "
            "not match the active experiment."
        )

    if payload.get("run_id") != context.run_id:
        raise KnowledgeStageError(
            "Normalization run_id does not match "
            "the active run."
        )

    cohorts = payload.get("cohorts")

    if not isinstance(cohorts, Mapping):
        raise KnowledgeStageError(
            "Normalization result must contain "
            "a cohorts object."
        )

    expected = {
        simulator.value
        for simulator in SimulatorKind
    }

    if set(cohorts) != expected:
        raise KnowledgeStageError(
            "Normalization result must contain "
            "exactly Synthea and psynthea."
        )


def _single_artifact(
    artifacts: Sequence[ArtifactReference],
    *,
    kind: ArtifactKind,
    producer: str,
    description: str,
) -> ArtifactReference:
    if isinstance(
        artifacts,
        (str, bytes),
    ):
        raise TypeError(
            "artifacts must be a sequence."
        )

    candidates = [
        artifact
        for artifact in artifacts
        if (
            artifact.kind is kind
            and artifact.producer == producer
        )
    ]

    if len(candidates) != 1:
        raise KnowledgeStageError(
            f"Knowledge enrichment requires "
            f"exactly one {description} artifact; "
            f"found {len(candidates)}."
        )

    return candidates[0]


def _read_verified_json_artifact(
    context: OrchestrationContext,
    artifact: ArtifactReference,
    *,
    error_context: str,
) -> Mapping[str, Any]:
    path = context.workspace.resolve(
        artifact.path
    )

    _verify_file_identity(
        path,
        expected_sha256=artifact.sha256,
        expected_size=artifact.size_bytes,
        description=artifact.id,
    )

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise KnowledgeStageError(
            f"Unable to read {error_context} "
            f"{artifact.path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise KnowledgeStageError(
            f"{error_context} root must be a "
            "JSON object."
        )

    return payload


def _read_csv(
    path: Path,
    *,
    description: str,
) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            keep_default_na=True,
            na_values=[""],
        )
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except (
        OSError,
        UnicodeError,
        pd.errors.ParserError,
        ValueError,
    ) as exc:
        raise KnowledgeStageError(
            f"Unable to read {description}: "
            f"{exc}"
        ) from exc


def _verify_file_identity(
    path: Path,
    *,
    expected_sha256: str | None,
    expected_size: int | None,
    description: str,
) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
    ):
        raise KnowledgeStageError(
            "Verified scientific artefact is "
            f"missing or unsafe: {description}."
        )

    try:
        content = path.read_bytes()
    except OSError as exc:
        raise KnowledgeStageError(
            "Unable to read scientific artefact "
            f"{description}: {exc}"
        ) from exc

    actual_size = len(content)

    actual_sha256 = sha256(
        content
    ).hexdigest()

    if (
        expected_size is not None
        and actual_size != expected_size
    ):
        raise KnowledgeStageError(
            "Scientific artefact size changed: "
            f"{description}."
        )

    if (
        expected_sha256 is not None
        and actual_sha256 != expected_sha256
    ):
        raise KnowledgeStageError(
            "Scientific artefact hash changed: "
            f"{description}."
        )


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _plain_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [
            _plain_value(item)
            for item in value
        ]

    if isinstance(value, list):
        return [
            _plain_value(item)
            for item in value
        ]

    if isinstance(value, (set, frozenset)):
        return sorted(
            _plain_value(item)
            for item in value
        )

    if isinstance(value, datetime):
        return value.astimezone(
            UTC
        ).isoformat()

    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "value"):
        enum_value = getattr(
            value,
            "value",
        )

        if isinstance(enum_value, str):
            return enum_value

    return value


def _aware_datetime(
    value: datetime,
    field_name: str,
) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(
            f"{field_name} must be a datetime."
        )

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{field_name} must be "
            "timezone-aware."
        )

    return value.astimezone(UTC)