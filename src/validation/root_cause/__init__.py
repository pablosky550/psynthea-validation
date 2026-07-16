"""Public API for the Phase 3 Root Cause Engine.

The package transforms validated discrepancies into deterministic,
evidence-backed and reproducible causal investigations.

Only stable integration contracts are exported from this module. Internal
pipeline components such as signal extraction, candidate generation, ranking,
verification, attribution and reproduction planning remain implementation
details and must not be imported by external consumers.

Scientific boundary
-------------------
Technical execution failures are represented by ``RootCauseError`` subclasses.
Unresolved scientific investigations remain successful engine executions whose
reports contain an ``INCONCLUSIVE`` or ``NOT_APPLICABLE`` status.
"""

from __future__ import annotations

from validation.root_cause.engine import (
    EngineInputs,
    EngineServices,
    EngineStage,
    RootCauseEngine,
    RootCauseEngineResult,
    StageRecord,
    run_root_cause_analysis,
)
from validation.root_cause.exceptions import (
    RootCauseError,
    RootCauseInputError,
    RootCauseIntegrityError,
)
from validation.root_cause.models import (
    CausalConfidence,
    DifferenceClassification,
    RootCauseFinding,
    RootCauseReport,
    RootCauseRequest,
    RootCauseStatus,
)
from validation.root_cause.report import (
    ReportBundle,
    ReportConfiguration,
    ReportConsistencyError,
    RootCauseDocument,
    build_root_cause_document,
    render_json_report,
    render_markdown_report,
    write_json_report,
    write_markdown_report,
    write_report_bundle,
)



__all__ = [
    # Engine execution
    "EngineInputs",
    "EngineServices",
    "EngineStage",
    "RootCauseEngine",
    "RootCauseEngineResult",
    "StageRecord",
    "run_root_cause_analysis",
    # Scientific contracts
    "CausalConfidence",
    "DifferenceClassification",
    "RootCauseFinding",
    "RootCauseReport",
    "RootCauseRequest",
    "RootCauseStatus",
    # Reporting
    "ReportBundle",
    "ReportConfiguration",
    "ReportConsistencyError",
    "RootCauseDocument",
    "build_root_cause_document",
    "render_json_report",
    "render_markdown_report",
    "write_json_report",
    "write_markdown_report",
    "write_report_bundle",
    # Public failures
    "RootCauseError",
    "RootCauseInputError",
    "RootCauseIntegrityError",
]