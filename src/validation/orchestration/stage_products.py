"""Run-scoped in-memory products shared between orchestration stages.

The orchestrator deliberately exposes only immutable stage metadata and persisted
artefacts through ``OrchestrationContext``. Scientific Python domain objects are
therefore exchanged through this explicit, typed store rather than serialized and
read back from disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from validation.interpretation.workflow import InterpretationWorkflowResult


@dataclass(slots=True)
class ScientificStageProductStore:
    """Thread-safe registry of immutable scientific products by run and module."""

    _interpretations: dict[
        tuple[str, str],
        InterpretationWorkflowResult,
    ] = field(default_factory=dict, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def publish_interpretation(
        self,
        *,
        run_id: str,
        result: InterpretationWorkflowResult,
    ) -> None:
        """Publish exactly one interpretation for ``run_id`` and module."""

        normalized_run_id = _require_text(run_id, "run_id")
        if not isinstance(result, InterpretationWorkflowResult):
            raise TypeError(
                "result must be an InterpretationWorkflowResult."
            )

        report = result.execution.report
        if report.pipeline_run_id != normalized_run_id:
            raise ValueError(
                "Interpretation pipeline_run_id does not match run_id."
            )

        module_name = _require_text(report.module_name, "report.module_name")
        key = (normalized_run_id, module_name)

        with self._lock:
            existing = self._interpretations.get(key)
            if existing is not None:
                if existing == result:
                    return
                raise ValueError(
                    "A different interpretation is already published for "
                    f"run {normalized_run_id!r} and module {module_name!r}."
                )
            self._interpretations[key] = result

    def interpretation(
        self,
        *,
        run_id: str,
        module_name: str | None = None,
    ) -> InterpretationWorkflowResult:
        """Return the unique interpretation selected for a run."""

        normalized_run_id = _require_text(run_id, "run_id")
        normalized_module = (
            None
            if module_name is None
            else _require_text(module_name, "module_name")
        )

        with self._lock:
            if normalized_module is not None:
                result = self._interpretations.get(
                    (normalized_run_id, normalized_module)
                )
                if result is None:
                    raise LookupError(
                        "No interpretation is published for "
                        f"run {normalized_run_id!r} and module "
                        f"{normalized_module!r}."
                    )
                return result

            matches = tuple(
                result
                for (candidate_run_id, _), result in self._interpretations.items()
                if candidate_run_id == normalized_run_id
            )

        if not matches:
            raise LookupError(
                f"No interpretation is published for run {normalized_run_id!r}."
            )
        if len(matches) != 1:
            modules = sorted(
                result.execution.report.module_name
                for result in matches
            )
            raise LookupError(
                "Root-cause input is ambiguous because multiple module "
                f"interpretations are published for run {normalized_run_id!r}: "
                + ", ".join(modules)
                + ". Configure module_name explicitly."
            )
        return matches[0]

    def clear_run(self, run_id: str) -> None:
        """Remove all products associated with one completed or failed run."""

        normalized_run_id = _require_text(run_id, "run_id")
        with self._lock:
            keys = tuple(
                key
                for key in self._interpretations
                if key[0] == normalized_run_id
            )
            for key in keys:
                del self._interpretations[key]


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized