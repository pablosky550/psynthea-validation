"""Deterministic construction of exact, non-executing reproduction plans.

This module converts already validated Phase 2B provenance and Phase 3 causal
outputs into a :class:`~validation.root_cause.models.ReproductionPlan`.  It
never executes commands, reads artefact contents, resolves software versions
from the environment, or invents missing scientific provenance.

Scientific boundary
-------------------
A reproduction plan is a protocol, not evidence that a discrepancy has been
reproduced.  Successful reproduction can only be asserted by a completed
verification result.  Missing seeds, hashes, versions, commands or artefacts
are therefore surfaced explicitly instead of being guessed.

Design guarantees
-----------------
* Exact commands are supplied by trusted contributors and remain tokenised.
* Artefact references are resolved by stable ID and, in strict mode, require a
  SHA-256 digest.
* Conflicting contributors fail loudly; equivalent contributions are merged.
* Input ordering cannot affect the generated plan or its identifier.
* The resulting plan is immutable, deterministic and safe to serialise.
* No subprocess, filesystem, network or shell access exists in this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from pathlib import Path
from re import compile as compile_pattern
from types import MappingProxyType
from enum import Enum
from typing import Any, Final, Protocol, runtime_checkable

from validation.orchestration.models import ArtifactReference
from validation.root_cause.exceptions import (
    ReproductionError,
    RootCauseInputError,
    RootCauseIntegrityError,
)
from validation.root_cause.models import (
    ReproductionPlan,
    RootCauseRequest,
    SourceAttribution,
    VerificationOutcome,
    VerificationResult,
)

__all__ = [
    "ExplicitReproductionContributor",
    "ReproductionContext",
    "ReproductionContributor",
    "ReproductionDiagnostic",
    "ReproductionFragment",
    "ReproductionPlanBuilder",
    "ReproductionSeverity",
    "VerificationReproductionContributor",
    "build_reproduction_plan",
]


_IDENTIFIER_PATTERN: Final = compile_pattern(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SHA256_PATTERN: Final = compile_pattern(r"^[0-9a-f]{64}$")


class ReproductionSeverity(str, Enum):
    """Stable diagnostic severity values without introducing causal semantics."""

    INFO = "info"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ReproductionDiagnostic:
    """One deterministic, non-fatal planning diagnostic."""

    code: str
    message: str
    severity: ReproductionSeverity = ReproductionSeverity.WARNING
    contributor_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_identifier(self.code, "code"))
        object.__setattr__(self, "message", _require_text(self.message, "message"))
        if not isinstance(self.severity, ReproductionSeverity):
            try:
                object.__setattr__(self, 'severity', ReproductionSeverity(self.severity))
            except (TypeError, ValueError) as exc:
                raise ValueError("severity must be a ReproductionSeverity.") from exc
        object.__setattr__(
            self,
            "contributor_id",
            _optional_identifier(self.contributor_id, "contributor_id"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class ReproductionFragment:
    """Immutable contribution to one reproduction protocol.

    Contributors may provide any subset of the plan.  The builder performs a
    deterministic merge and rejects contradictory values.
    """

    commands: tuple[tuple[str, ...], ...] = ()
    working_directory: Path | None = None
    seeds: tuple[int, ...] = ()
    module_paths: tuple[str, ...] = ()
    patient_ids: tuple[str, ...] = ()
    cohort_ids: tuple[str, ...] = ()
    required_artifact_ids: tuple[str, ...] = ()
    configuration: Mapping[str, Any] = field(default_factory=dict)
    software_versions: Mapping[str, str] = field(default_factory=dict)
    verification_steps: tuple[str, ...] = ()
    expected_result: str | None = None
    limitations: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "commands", _normalize_commands(self.commands, "commands"))
        if self.working_directory is not None:
            object.__setattr__(
                self,
                "working_directory",
                _normalize_path(self.working_directory, "working_directory"),
            )
        object.__setattr__(self, "seeds", _normalize_seeds(self.seeds, "seeds"))
        object.__setattr__(
            self, "module_paths", _normalize_text_tuple(self.module_paths, "module_paths")
        )
        for field_name in ("patient_ids", "cohort_ids", "required_artifact_ids"):
            object.__setattr__(
                self,
                field_name,
                _normalize_identifier_tuple(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "configuration",
            _freeze_mapping(self.configuration, "configuration"),
        )
        object.__setattr__(
            self,
            "software_versions",
            _normalize_text_mapping(self.software_versions, "software_versions"),
        )
        object.__setattr__(
            self,
            "verification_steps",
            _normalize_text_tuple(self.verification_steps, "verification_steps"),
        )
        object.__setattr__(
            self,
            "expected_result",
            _optional_text(self.expected_result, "expected_result"),
        )
        object.__setattr__(
            self, "limitations", _normalize_text_tuple(self.limitations, "limitations")
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class ReproductionContext:
    """Complete validated input available to reproduction contributors."""

    request: RootCauseRequest
    artifacts: Mapping[str, ArtifactReference]
    verification_results: tuple[VerificationResult, ...] = ()
    attribution: SourceAttribution | None = None
    title: str = "Reproduce root-cause discrepancy"
    objective: str = "Reproduce the observed discrepancy with the recorded experiment inputs."
    strict_integrity: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, RootCauseRequest):
            raise TypeError("request must be a RootCauseRequest.")
        artifacts = _normalize_model_mapping(
            self.artifacts, ArtifactReference, "artifacts"
        )
        object.__setattr__(self, "artifacts", artifacts)
        results = _normalize_model_tuple(
            self.verification_results, VerificationResult, "verification_results"
        )
        _require_unique_ids(results, "verification_results")
        object.__setattr__(
            self,
            "verification_results",
            tuple(sorted(results, key=lambda item: item.id)),
        )
        if self.attribution is not None and not isinstance(self.attribution, SourceAttribution):
            raise TypeError("attribution must be a SourceAttribution or None.")
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "objective", _require_text(self.objective, "objective"))
        strict = self.request.strict_integrity if self.strict_integrity is None else self.strict_integrity
        if not isinstance(strict, bool):
            raise TypeError("strict_integrity must be a bool or None.")
        object.__setattr__(self, "strict_integrity", strict)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

        referenced_input_artifacts = {
            artifact_id
            for result in results
            for artifact_id in result.input_artifact_ids
        }
        missing_verification_inputs = sorted(referenced_input_artifacts - set(artifacts))
        if missing_verification_inputs:
            raise RootCauseInputError(
                "Verification results reference unavailable input artefacts.",
                context={"missing_artifact_ids": missing_verification_inputs},
            )

        output_ids: set[str] = set()
        for result in results:
            for artifact in result.output_artifacts:
                if artifact.id in output_ids:
                    raise RootCauseIntegrityError(
                        "Verification results contain duplicate output artefact identifiers.",
                        context={"artifact_id": artifact.id},
                    )
                output_ids.add(artifact.id)
                existing = artifacts.get(artifact.id)
                if existing is not None and existing != artifact:
                    raise RootCauseIntegrityError(
                        "A verification output artefact conflicts with the registered artefact.",
                        context={"artifact_id": artifact.id},
                    )

        unknown_requested = sorted(set(self.request.artifact_ids) - set(artifacts))
        if unknown_requested:
            raise RootCauseInputError(
                "The reproduction context is missing artefacts declared by the request.",
                context={"missing_artifact_ids": unknown_requested},
            )


@runtime_checkable
class ReproductionContributor(Protocol):
    """Injected source of exact reproduction-plan fragments."""

    @property
    def id(self) -> str:
        """Stable contributor identifier."""

    def contribute(self, context: ReproductionContext) -> ReproductionFragment | None:
        """Return an exact fragment, or ``None`` when not applicable."""


@dataclass(frozen=True, slots=True)
class ExplicitReproductionContributor:
    """Contributor backed by an explicitly supplied immutable fragment."""

    id: str
    fragment: ReproductionFragment

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        if not isinstance(self.fragment, ReproductionFragment):
            raise TypeError("fragment must be a ReproductionFragment.")

    def contribute(self, context: ReproductionContext) -> ReproductionFragment:
        del context
        return self.fragment


@dataclass(frozen=True, slots=True)
class VerificationReproductionContributor:
    """Derive protocol steps from already recorded verification results.

    Commands are reused only when they were explicitly recorded by the
    verification stage.  Results with technical ``ERROR`` outcomes are retained
    as limitations, not represented as scientific reproduction steps.
    """

    id: str = "verification_results"
    include_not_run: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_identifier(self.id, "id"))
        if not isinstance(self.include_not_run, bool):
            raise TypeError("include_not_run must be a bool.")

    def contribute(self, context: ReproductionContext) -> ReproductionFragment | None:
        commands: list[tuple[str, ...]] = []
        artefact_ids: list[str] = []
        steps: list[str] = []
        limitations: list[str] = []

        for result in context.verification_results:
            if result.outcome is VerificationOutcome.ERROR:
                limitations.append(
                    f"Verification {result.id} ended in a technical error and is not a "
                    "scientific reproduction step."
                )
                continue
            if result.outcome is VerificationOutcome.NOT_RUN and not self.include_not_run:
                limitations.append(
                    f"Verification {result.id} was not run and must be executed separately."
                )
                continue
            if result.command:
                commands.append(result.command)
            artefact_ids.extend(result.input_artifact_ids)
            artefact_ids.extend(artifact.id for artifact in result.output_artifacts)
            steps.append(
                f"Run verifier {result.verifier_id}: {result.procedure} "
                f"Expected: {result.expected_result}"
            )

        if not any((commands, artefact_ids, steps, limitations)):
            return None
        return ReproductionFragment(
            commands=tuple(commands),
            required_artifact_ids=tuple(artefact_ids),
            verification_steps=tuple(steps),
            limitations=tuple(limitations),
        )


@dataclass(frozen=True, slots=True)
class ReproductionBuild:
    """Plan plus non-fatal diagnostics generated during construction."""

    plan: ReproductionPlan
    diagnostics: tuple[ReproductionDiagnostic, ...] = ()
    contributor_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.plan, ReproductionPlan):
            raise TypeError("plan must be a ReproductionPlan.")
        diagnostics = _normalize_model_tuple(
            self.diagnostics, ReproductionDiagnostic, "diagnostics"
        )
        object.__setattr__(
            self,
            "diagnostics",
            tuple(sorted(diagnostics, key=lambda item: (item.code, item.message))),
        )
        object.__setattr__(
            self,
            "contributor_ids",
            _normalize_identifier_tuple(self.contributor_ids, "contributor_ids"),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


class ReproductionPlanBuilder:
    """Merge trusted fragments into one exact, deterministic reproduction plan."""

    def __init__(self, contributors: Sequence[ReproductionContributor]) -> None:
        if isinstance(contributors, (str, bytes)) or not isinstance(contributors, Sequence):
            raise TypeError("contributors must be a sequence.")
        normalized: list[ReproductionContributor] = []
        ids: set[str] = set()
        for index, contributor in enumerate(contributors):
            if not isinstance(contributor, ReproductionContributor):
                raise TypeError(
                    f"contributors[{index}] must implement ReproductionContributor."
                )
            contributor_id = _require_identifier(contributor.id, f"contributors[{index}].id")
            if contributor_id in ids:
                raise ValueError(f"Duplicate contributor id: {contributor_id!r}.")
            ids.add(contributor_id)
            normalized.append(contributor)
        self._contributors = tuple(sorted(normalized, key=lambda item: item.id))

    def build(self, context: ReproductionContext) -> ReproductionBuild:
        if not isinstance(context, ReproductionContext):
            raise TypeError("context must be a ReproductionContext.")

        fragments: list[tuple[str, ReproductionFragment]] = []
        diagnostics: list[ReproductionDiagnostic] = []
        for contributor in self._contributors:
            try:
                fragment = contributor.contribute(context)
            except (RootCauseInputError, RootCauseIntegrityError, ReproductionError):
                raise
            except Exception as exc:  # pragma: no cover - collaborator isolation
                raise ReproductionError(
                    "A reproduction contributor failed unexpectedly.",
                    context={
                        "contributor_id": contributor.id,
                        "error_type": type(exc).__name__,
                    },
                ) from exc
            if fragment is None:
                continue
            if not isinstance(fragment, ReproductionFragment):
                raise RootCauseIntegrityError(
                    "A reproduction contributor returned an invalid fragment type.",
                    context={
                        "contributor_id": contributor.id,
                        "returned_type": type(fragment).__name__,
                    },
                )
            fragments.append((contributor.id, fragment))

        if not fragments:
            raise ReproductionError(
                "No contributor supplied enough information to construct a reproduction plan.",
                context={"request_id": context.request.id},
            )

        merged = _merge_fragments(fragments)
        required_ids = tuple(
            sorted(set(context.request.artifact_ids) | set(merged.required_artifact_ids))
        )
        missing = sorted(set(required_ids) - set(context.artifacts))
        if missing:
            raise ReproductionError(
                "Required reproduction artefacts are unavailable.",
                context={"missing_artifact_ids": missing},
            )

        hashes: dict[str, str] = {}
        unhashed: list[str] = []
        for artifact_id in required_ids:
            digest = context.artifacts[artifact_id].sha256
            if digest is None:
                unhashed.append(artifact_id)
            else:
                hashes[artifact_id] = _normalize_sha256(digest, f"artifact[{artifact_id}].sha256")

        if unhashed and context.strict_integrity:
            raise ReproductionError(
                "Strict reproduction requires SHA-256 hashes for every required artefact.",
                context={"unhashed_artifact_ids": unhashed},
            )
        if unhashed:
            diagnostics.append(
                ReproductionDiagnostic(
                    code="reproduction.unhashed_artifacts",
                    message="Some required artefacts do not have a recorded SHA-256 digest.",
                    metadata={"artifact_ids": tuple(unhashed)},
                )
            )

        if not merged.commands:
            raise ReproductionError(
                "An exact reproduction plan requires at least one tokenised command.",
                context={"request_id": context.request.id},
            )
        if merged.working_directory is None:
            raise ReproductionError(
                "An exact reproduction plan requires an explicit working directory.",
                context={"request_id": context.request.id},
            )
        if not merged.seeds:
            message = "No random seeds were supplied; deterministic reproduction is not guaranteed."
            if context.strict_integrity:
                raise ReproductionError(message, context={"request_id": context.request.id})
            diagnostics.append(
                ReproductionDiagnostic(
                    code="reproduction.missing_seeds",
                    message=message,
                )
            )
        if not merged.software_versions:
            message = "No software versions were supplied; environment equivalence is not guaranteed."
            if context.strict_integrity:
                raise ReproductionError(message, context={"request_id": context.request.id})
            diagnostics.append(
                ReproductionDiagnostic(
                    code="reproduction.missing_versions",
                    message=message,
                )
            )

        expected_result = merged.expected_result
        if expected_result is None:
            message = (
                "No explicit expected reproduction result was supplied; the plan cannot "
                "claim a scientifically testable endpoint."
            )
            if context.strict_integrity:
                raise ReproductionError(message, context={"request_id": context.request.id})
            diagnostics.append(
                ReproductionDiagnostic(
                    code="reproduction.missing_expected_result",
                    message=message,
                )
            )
            expected_result = "Re-execute the recorded experiment and compare the discrepancy."
        plan_id = _stable_plan_id(context, merged, required_ids, hashes, expected_result)
        plan = ReproductionPlan(
            id=plan_id,
            experiment_id=context.request.experiment_id,
            run_id=context.request.run_id,
            title=context.title,
            objective=context.objective,
            commands=merged.commands,
            working_directory=merged.working_directory,
            seeds=merged.seeds,
            module_paths=merged.module_paths,
            patient_ids=merged.patient_ids,
            cohort_ids=merged.cohort_ids,
            required_artifact_ids=required_ids,
            required_hashes=hashes,
            configuration=merged.configuration,
            software_versions=merged.software_versions,
            verification_steps=merged.verification_steps,
            expected_result=expected_result,
            limitations=merged.limitations,
        )
        return ReproductionBuild(
            plan=plan,
            diagnostics=tuple(diagnostics),
            contributor_ids=tuple(contributor_id for contributor_id, _ in fragments),
            metadata={
                "request_id": context.request.id,
                "attribution_level": (
                    context.attribution.level.value if context.attribution is not None else None
                ),
            },
        )


def build_reproduction_plan(
    context: ReproductionContext,
    contributors: Sequence[ReproductionContributor],
) -> ReproductionBuild:
    """Functional façade for deterministic plan construction."""

    return ReproductionPlanBuilder(contributors).build(context)


def _merge_fragments(
    fragments: Sequence[tuple[str, ReproductionFragment]],
) -> ReproductionFragment:
    commands: list[tuple[str, ...]] = []
    seen_commands: set[tuple[str, ...]] = set()
    working_directory: Path | None = None
    seeds: set[int] = set()
    module_paths: set[str] = set()
    patient_ids: set[str] = set()
    cohort_ids: set[str] = set()
    artifact_ids: set[str] = set()
    configuration: dict[str, Any] = {}
    versions: dict[str, str] = {}
    steps: set[str] = set()
    expected_result: str | None = None
    limitations: set[str] = set()
    metadata: dict[str, Any] = {}

    for contributor_id, fragment in fragments:
        for command in fragment.commands:
            if command not in seen_commands:
                seen_commands.add(command)
                commands.append(command)
        seeds.update(fragment.seeds)
        module_paths.update(fragment.module_paths)
        patient_ids.update(fragment.patient_ids)
        cohort_ids.update(fragment.cohort_ids)
        artifact_ids.update(fragment.required_artifact_ids)
        steps.update(fragment.verification_steps)
        limitations.update(fragment.limitations)

        if fragment.working_directory is not None:
            if working_directory is None:
                working_directory = fragment.working_directory
            elif working_directory != fragment.working_directory:
                raise RootCauseIntegrityError(
                    "Reproduction contributors disagree on the working directory.",
                    context={
                        "contributor_id": contributor_id,
                        "existing": str(working_directory),
                        "received": str(fragment.working_directory),
                    },
                )
        expected_result = _merge_scalar(
            expected_result,
            fragment.expected_result,
            "expected_result",
            contributor_id,
        )
        _merge_mapping(configuration, fragment.configuration, "configuration", contributor_id)
        _merge_mapping(versions, fragment.software_versions, "software_versions", contributor_id)
        _merge_mapping(metadata, fragment.metadata, "metadata", contributor_id)

    return ReproductionFragment(
        commands=tuple(commands),
        working_directory=working_directory,
        seeds=tuple(sorted(seeds)),
        module_paths=tuple(sorted(module_paths)),
        patient_ids=tuple(sorted(patient_ids)),
        cohort_ids=tuple(sorted(cohort_ids)),
        required_artifact_ids=tuple(sorted(artifact_ids)),
        configuration=configuration,
        software_versions=versions,
        verification_steps=tuple(sorted(steps)),
        expected_result=expected_result,
        limitations=tuple(sorted(limitations)),
        metadata=metadata,
    )


def _merge_scalar(
    current: str | None,
    incoming: str | None,
    field_name: str,
    contributor_id: str,
) -> str | None:
    if incoming is None:
        return current
    if current is None:
        return incoming
    if current != incoming:
        raise RootCauseIntegrityError(
            f"Reproduction contributors disagree on {field_name}.",
            context={
                "contributor_id": contributor_id,
                "existing": current,
                "received": incoming,
            },
        )
    return current


def _merge_mapping(
    target: dict[str, Any],
    incoming: Mapping[str, Any],
    field_name: str,
    contributor_id: str,
) -> None:
    for key, value in incoming.items():
        if key in target and _canonical(target[key]) != _canonical(value):
            raise RootCauseIntegrityError(
                f"Reproduction contributors disagree on {field_name}[{key!r}].",
                context={"contributor_id": contributor_id, "key": key},
            )
        target[key] = value


def _stable_plan_id(
    context: ReproductionContext,
    fragment: ReproductionFragment,
    required_ids: tuple[str, ...],
    hashes: Mapping[str, str],
    expected_result: str,
) -> str:
    payload = {
        "request_id": context.request.id,
        "experiment_id": context.request.experiment_id,
        "run_id": context.request.run_id,
        "title": context.title,
        "objective": context.objective,
        "commands": fragment.commands,
        "working_directory": str(fragment.working_directory),
        "seeds": fragment.seeds,
        "module_paths": fragment.module_paths,
        "patient_ids": fragment.patient_ids,
        "cohort_ids": fragment.cohort_ids,
        "required_artifact_ids": required_ids,
        "required_hashes": dict(sorted(hashes.items())),
        "configuration": fragment.configuration,
        "software_versions": fragment.software_versions,
        "verification_steps": fragment.verification_steps,
        "expected_result": expected_result,
        "limitations": fragment.limitations,
    }
    digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]
    return f"reproduction:{digest}"


def _canonical_json(value: Any) -> str:
    return dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        items = [_canonical(item) for item in value]
        return sorted(items, key=lambda item: dumps(item, sort_keys=True, default=str)) if isinstance(value, (set, frozenset)) else items
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def _normalize_commands(value: Any, field_name: str) -> tuple[tuple[str, ...], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of token sequences.")
    commands: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for index, command in enumerate(value):
        normalized = _normalize_text_tuple(
            command, f"{field_name}[{index}]", allow_empty=False, preserve_order=True
        )
        if normalized not in seen:
            seen.add(normalized)
            commands.append(normalized)
    return tuple(commands)


def _normalize_seeds(value: Any, field_name: str) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of integers.")
    seeds: set[int] = set()
    for index, seed in enumerate(value):
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError(f"{field_name}[{index}] must be an integer.")
        seeds.add(seed)
    return tuple(sorted(seeds))


def _normalize_path(value: Any, field_name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{field_name} must be a string or Path.")
    path = Path(value)
    if not str(path).strip():
        raise ValueError(f"{field_name} cannot be empty.")
    return path


def _normalize_text_mapping(value: Any, field_name: str) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized = {
        _require_identifier(key, f"{field_name} key"): _require_text(item, f"{field_name}[{key!r}]")
        for key, item in value.items()
    }
    return MappingProxyType(dict(sorted(normalized.items())))


def _normalize_model_mapping(value: Any, cls: type[Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        identifier = _require_identifier(key, f"{field_name} key")
        if not isinstance(item, cls):
            raise TypeError(f"{field_name}[{identifier!r}] must be a {cls.__name__}.")
        if item.id != identifier:
            raise ValueError(f"{field_name}[{identifier!r}] key must match item.id.")
        normalized[identifier] = item
    return MappingProxyType(dict(sorted(normalized.items())))


def _normalize_model_tuple(value: Any, cls: type[Any], field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence.")
    result: list[Any] = []
    for index, item in enumerate(value):
        if not isinstance(item, cls):
            raise TypeError(f"{field_name}[{index}] must be a {cls.__name__}.")
        result.append(item)
    return tuple(result)


def _require_unique_ids(items: Sequence[Any], field_name: str) -> None:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{field_name} contains duplicate ids.")


def _normalize_identifier_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of identifiers.")
    return tuple(sorted({_require_identifier(item, f"{field_name} item") for item in value}))


def _normalize_text_tuple(
    value: Any,
    field_name: str,
    *,
    allow_empty: bool = True,
    preserve_order: bool = False,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    normalized = [_require_text(item, f"{field_name} item") for item in value]
    if preserve_order:
        result = tuple(dict.fromkeys(normalized))
    else:
        result = tuple(sorted(set(normalized)))
    if not allow_empty and not result:
        raise ValueError(f"{field_name} cannot be empty.")
    return result


def _require_identifier(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        raise ValueError(f"{field_name} is not a valid identifier: {text!r}.")
    return text


def _optional_identifier(value: Any, field_name: str) -> str | None:
    return None if value is None else _require_identifier(value, field_name)


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


def _optional_text(value: Any, field_name: str) -> str | None:
    return None if value is None else _require_text(value, field_name)


def _normalize_sha256(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name).lower()
    if not _SHA256_PATTERN.fullmatch(text):
        raise ValueError(f"{field_name} must be a 64-character lowercase SHA-256 digest.")
    return text


def _freeze_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return MappingProxyType(
        {
            _require_text(str(key), f"{field_name} key"): _deep_freeze(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    )


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _deep_freeze(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_deep_freeze(item) for item in value), key=repr))
    return value