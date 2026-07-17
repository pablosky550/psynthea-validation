"""
Normalization and collection of validation evidence.

The interpretation engine never consumes arbitrary pipeline objects directly.
This module converts scalar values, mappings, dataclasses and pandas tables into
immutable :class:`~validation.interpretation.models.EvidenceValue` objects.

Scientific safety rules
-----------------------

* An observed zero is represented as ``AVAILABLE`` with ``value=0``.
* A missing source, missing field, empty table and failed computation are never
  collapsed into zero.
* Non-finite numeric values are not exposed as available evidence.
* Duplicate metric identifiers are rejected.
* Structural corruption can fail loudly in strict mode or be represented as
  ``INVALID`` evidence in permissive mode.
* Every extracted value preserves source, row identity and column provenance.

This module normalizes evidence only. It does not assign validation decisions,
clinical meaning, severity, confidence or recommendations.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from math import isfinite
from pathlib import Path
from re import sub
from types import MappingProxyType
from typing import Any, Protocol, TypeAlias

import numpy as np
import pandas as pd

from validation.comparison.module_validation import ModuleValidationResult
from validation.comparison.spanish_validation import SpanishAdaptationValidation
from validation.comparison.statistical_comparison import ModuleStatisticalComparisonResult
from validation.interpretation.models import EvidenceAvailability, EvidenceValue

__all__ = [
    "DEFAULT_EVIDENCE_REGISTRY",
    "DuplicateEvidenceError",
    "EvidenceAdapter",
    "EvidenceBuilder",
    "EvidenceCatalog",
    "EvidenceExtractionError",
    "EvidenceRegistry",
    "FrameExtractionSpec",
    "ScalarNormalization",
    "collect_evidence",
    "extract_dataframe_cell",
    "extract_dataframe_rows",
    "extract_scalar",
    "normalize_scalar",
]


# =============================================================================
# Exceptions
# =============================================================================


class EvidenceExtractionError(ValueError):
    """Raised when pipeline output cannot be normalized without ambiguity."""


class DuplicateEvidenceError(EvidenceExtractionError):
    """Raised when two evidence items use the same stable metric identifier."""


# =============================================================================
# Internal helpers
# =============================================================================


ScalarValue: TypeAlias = str | int | float | bool | date | datetime
RowSelector: TypeAlias = int | str | Callable[[pd.DataFrame], pd.Series]

_IDENTIFIER_REPLACEMENT_PATTERN = r"[^A-Za-z0-9._:-]+"


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _metric_token(value: Any) -> str:
    """Return a deterministic identifier-safe token for row identities."""

    if value is None or _is_missing(value):
        return "missing"
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, datetime):
        value = value.astimezone(UTC).isoformat() if value.tzinfo else value.isoformat()
    elif isinstance(value, date):
        value = value.isoformat()

    token = sub(_IDENTIFIER_REPLACEMENT_PATTERN, "-", str(value).strip()).strip("-._:")
    return token[:120] or "empty"


def _is_missing(value: Any) -> bool:
    """Safely detect scalar missing values without evaluating arrays as booleans."""

    if value is None:
        return True
    if isinstance(value, (pd.DataFrame, pd.Series, np.ndarray, Mapping, list, tuple, set)):
        return False
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result) if isinstance(result, (bool, np.bool_)) else False


def _safe_metadata(metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if metadata is None:
        return MappingProxyType({})
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping or None.")
    return metadata


def _source_name(source: Any, fallback: str | None = None) -> str | None:
    """Derive a readable source label from a pipeline object."""

    if fallback is not None:
        return _text(fallback, "source")
    if source is None:
        return None
    for attribute in ("source", "module_name", "name"):
        value = getattr(source, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return type(source).__name__


def _invalid_evidence(
    *,
    metric_id: str,
    name: str,
    source: str | None,
    description: str | None,
    metadata: Mapping[str, Any] | None,
    reason: str,
) -> EvidenceValue:
    merged = dict(metadata or {})
    merged["normalization_error"] = reason
    return EvidenceValue(
        metric_id=metric_id,
        name=name,
        availability=EvidenceAvailability.INVALID,
        value=None,
        source=source,
        description=description,
        metadata=merged,
    )


# =============================================================================
# Scalar normalization
# =============================================================================


@dataclass(frozen=True, slots=True)
class ScalarNormalization:
    """Result of converting one arbitrary scalar into canonical evidence data."""

    availability: EvidenceAvailability
    value: ScalarValue | None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.availability, EvidenceAvailability):
            raise TypeError("availability must be an EvidenceAvailability member.")
        if self.availability is EvidenceAvailability.AVAILABLE and self.value is None:
            raise ValueError("Available scalar normalization must contain a value.")
        if self.availability is not EvidenceAvailability.AVAILABLE and self.value is not None:
            raise ValueError("Unavailable scalar normalization must use value=None.")


def normalize_scalar(value: Any) -> ScalarNormalization:
    """Normalize one scalar while preserving zero and rejecting ambiguous values.

    Supported values are strings, booleans, finite numbers, dates, datetimes,
    enums, NumPy scalar values and pathlib paths. Missing values become
    ``NOT_COMPUTED``. Infinite numbers and non-scalar containers become
    ``INVALID``.
    """

    if _is_missing(value):
        return ScalarNormalization(
            EvidenceAvailability.NOT_COMPUTED,
            None,
            "The value is missing or was not computed.",
        )

    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, Path):
        value = str(value)

    if isinstance(value, bool):
        return ScalarNormalization(EvidenceAvailability.AVAILABLE, value)
    if isinstance(value, int):
        return ScalarNormalization(EvidenceAvailability.AVAILABLE, value)
    if isinstance(value, float):
        if not isfinite(value):
            return ScalarNormalization(
                EvidenceAvailability.INVALID,
                None,
                "Numeric evidence must be finite.",
            )
        return ScalarNormalization(EvidenceAvailability.AVAILABLE, value)
    if isinstance(value, datetime):
        normalized = value.astimezone(UTC) if value.tzinfo else value
        return ScalarNormalization(EvidenceAvailability.AVAILABLE, normalized)
    if isinstance(value, date):
        return ScalarNormalization(EvidenceAvailability.AVAILABLE, value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return ScalarNormalization(
                EvidenceAvailability.EMPTY,
                None,
                "Text evidence is empty.",
            )
        return ScalarNormalization(EvidenceAvailability.AVAILABLE, normalized)

    return ScalarNormalization(
        EvidenceAvailability.INVALID,
        None,
        f"Unsupported non-scalar evidence type: {type(value).__name__}.",
    )


def extract_scalar(
    value: Any,
    *,
    metric_id: str,
    name: str,
    source: str | None = None,
    unit: str | None = None,
    sample_size: int | None = None,
    denominator: int | None = None,
    observed_at: datetime | None = None,
    description: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    availability: EvidenceAvailability | None = None,
) -> EvidenceValue:
    """Create one :class:`EvidenceValue` from an arbitrary scalar.

    ``availability`` may be provided only to represent known external states
    such as a missing source or non-applicable metric. It cannot be used to mark
    a concrete non-null value as unavailable.
    """

    if availability is not None:
        if not isinstance(availability, EvidenceAvailability):
            raise TypeError("availability must be an EvidenceAvailability member or None.")
        if availability is not EvidenceAvailability.AVAILABLE:
            if value is not None and not _is_missing(value):
                raise ValueError("Unavailable evidence cannot contain a concrete value.")
            return EvidenceValue(
                metric_id=metric_id,
                name=name,
                availability=availability,
                value=None,
                source=source,
                unit=unit,
                sample_size=sample_size,
                denominator=denominator,
                observed_at=observed_at,
                description=description,
                metadata=_safe_metadata(metadata),
            )

    normalized = normalize_scalar(value)
    normalized_metadata = dict(metadata or {})
    if normalized.reason:
        normalized_metadata["normalization_reason"] = normalized.reason

    return EvidenceValue(
        metric_id=metric_id,
        name=name,
        availability=normalized.availability,
        value=normalized.value,
        source=source,
        unit=unit,
        sample_size=sample_size,
        denominator=denominator,
        observed_at=observed_at,
        description=description,
        metadata=normalized_metadata,
    )


# =============================================================================
# DataFrame extraction
# =============================================================================


@dataclass(frozen=True, slots=True)
class FrameExtractionSpec:
    """Declarative definition for extracting evidence rows from a DataFrame."""

    namespace: str
    value_columns: tuple[str, ...]
    identity_columns: tuple[str, ...] = ()
    name_columns: tuple[str, ...] = ()
    unit_by_column: Mapping[str, str] = field(default_factory=dict)
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "namespace", _text(self.namespace, "namespace"))
        object.__setattr__(self, "value_columns", tuple(self.value_columns))
        object.__setattr__(self, "identity_columns", tuple(self.identity_columns))
        object.__setattr__(self, "name_columns", tuple(self.name_columns))
        if not self.value_columns:
            raise ValueError("value_columns must contain at least one column.")
        for field_name, values in (
            ("value_columns", self.value_columns),
            ("identity_columns", self.identity_columns),
            ("name_columns", self.name_columns),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicate columns.")
            for value in values:
                _text(value, field_name)
        object.__setattr__(self, "unit_by_column", MappingProxyType(dict(self.unit_by_column)))


def _select_row(frame: pd.DataFrame, selector: RowSelector) -> tuple[pd.Series | None, str | None]:
    if isinstance(selector, int):
        if selector < 0 or selector >= len(frame):
            return None, f"Row position {selector} is outside the table bounds."
        return frame.iloc[selector], None
    if isinstance(selector, str):
        if selector not in frame.index:
            return None, f"Row label {selector!r} is not present in the table index."
        selected = frame.loc[selector]
        if isinstance(selected, pd.DataFrame):
            return None, f"Row label {selector!r} is not unique."
        return selected, None
    if callable(selector):
        try:
            mask = selector(frame)
        except Exception as exc:  # noqa: BLE001 - converted to evidence in permissive mode
            return None, f"Row selector raised {type(exc).__name__}: {exc}"
        if not isinstance(mask, pd.Series) or not pd.api.types.is_bool_dtype(mask.dtype):
            return None, "Callable row selector must return a boolean pandas Series."
        if len(mask) != len(frame) or not mask.index.equals(frame.index):
            return None, "Callable row selector must be index-aligned to the table."
        if mask.isna().any():
            return None, "Callable row selector must not contain missing boolean values."
        selected = frame.loc[mask.astype(bool)]
        if len(selected) != 1:
            return None, f"Callable row selector matched {len(selected)} rows; exactly one is required."
        return selected.iloc[0], None
    return None, f"Unsupported row selector type: {type(selector).__name__}."


def extract_dataframe_cell(
    frame: pd.DataFrame | None,
    *,
    column: str,
    metric_id: str,
    name: str,
    row: RowSelector = 0,
    source: str | None = None,
    unit: str | None = None,
    sample_size: int | None = None,
    denominator: int | None = None,
    observed_at: datetime | None = None,
    description: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    strict: bool = True,
) -> EvidenceValue:
    """Extract one traceable cell from a DataFrame.

    A missing table, empty table and missing column receive different
    availability states. Invalid selectors raise in strict mode and produce
    ``INVALID`` evidence in permissive mode.
    """

    column = _text(column, "column")
    base_metadata = dict(metadata or {})
    base_metadata.update({"column": column, "row_selector": repr(row)})

    if frame is None:
        return extract_scalar(
            None,
            metric_id=metric_id,
            name=name,
            source=source,
            unit=unit,
            sample_size=sample_size,
            denominator=denominator,
            observed_at=observed_at,
            description=description,
            metadata=base_metadata,
            availability=EvidenceAvailability.SOURCE_MISSING,
        )
    if not isinstance(frame, pd.DataFrame):
        message = f"Expected pandas DataFrame, got {type(frame).__name__}."
        if strict:
            raise EvidenceExtractionError(message)
        return _invalid_evidence(
            metric_id=metric_id,
            name=name,
            source=source,
            description=description,
            metadata=base_metadata,
            reason=message,
        )
    if frame.empty:
        return extract_scalar(
            None,
            metric_id=metric_id,
            name=name,
            source=source,
            unit=unit,
            sample_size=sample_size,
            denominator=denominator,
            observed_at=observed_at,
            description=description,
            metadata=base_metadata,
            availability=EvidenceAvailability.EMPTY,
        )
    if column not in frame.columns:
        return extract_scalar(
            None,
            metric_id=metric_id,
            name=name,
            source=source,
            unit=unit,
            sample_size=sample_size,
            denominator=denominator,
            observed_at=observed_at,
            description=description,
            metadata=base_metadata,
            availability=EvidenceAvailability.FIELD_MISSING,
        )

    selected, error = _select_row(frame, row)
    if error is not None or selected is None:
        if strict:
            raise EvidenceExtractionError(error or "Unable to select a table row.")
        return _invalid_evidence(
            metric_id=metric_id,
            name=name,
            source=source,
            description=description,
            metadata=base_metadata,
            reason=error or "Unable to select a table row.",
        )

    base_metadata["row_index"] = _metric_token(selected.name)
    return extract_scalar(
        selected[column],
        metric_id=metric_id,
        name=name,
        source=source,
        unit=unit,
        sample_size=sample_size,
        denominator=denominator,
        observed_at=observed_at,
        description=description,
        metadata=base_metadata,
    )


def extract_dataframe_rows(
    frame: pd.DataFrame | None,
    *,
    spec: FrameExtractionSpec,
    source: str | None = None,
    strict: bool = True,
) -> tuple[EvidenceValue, ...]:
    """Expand selected DataFrame columns into stable row-level evidence values."""

    if frame is None:
        return tuple(
            extract_scalar(
                None,
                metric_id=f"{spec.namespace}.source.{_metric_token(column)}",
                name=f"{spec.namespace} {column}",
                source=source,
                description=spec.description,
                metadata={"column": column},
                availability=EvidenceAvailability.SOURCE_MISSING,
            )
            for column in spec.value_columns
        )
    if not isinstance(frame, pd.DataFrame):
        message = f"Expected pandas DataFrame, got {type(frame).__name__}."
        if strict:
            raise EvidenceExtractionError(message)
        return tuple(
            _invalid_evidence(
                metric_id=f"{spec.namespace}.source.{_metric_token(column)}",
                name=f"{spec.namespace} {column}",
                source=source,
                description=spec.description,
                metadata={"column": column},
                reason=message,
            )
            for column in spec.value_columns
        )
    if frame.empty:
        return tuple(
            extract_scalar(
                None,
                metric_id=f"{spec.namespace}.empty.{_metric_token(column)}",
                name=f"{spec.namespace} {column}",
                source=source,
                description=spec.description,
                metadata={"column": column},
                availability=EvidenceAvailability.EMPTY,
            )
            for column in spec.value_columns
        )

    missing_columns = [
        column
        for column in (*spec.identity_columns, *spec.name_columns, *spec.value_columns)
        if column not in frame.columns
    ]
    if missing_columns and strict:
        raise EvidenceExtractionError(
            f"Table for namespace {spec.namespace!r} is missing columns: {missing_columns}."
        )

    values: list[EvidenceValue] = []
    seen_identities: set[str] = set()
    for position, (_, row) in enumerate(frame.iterrows()):
        identity_parts = [
            _metric_token(row[column]) if column in frame.columns else f"missing-{column}"
            for column in spec.identity_columns
        ]
        if not identity_parts:
            identity_parts = [str(position)]
        identity = ".".join(identity_parts)
        if identity in seen_identities:
            message = (
                f"Duplicate row identity {identity!r} in namespace {spec.namespace!r}; "
                "identity_columns do not uniquely identify rows."
            )
            if strict:
                raise EvidenceExtractionError(message)
            identity = f"{identity}.duplicate-{position}"
        seen_identities.add(identity)

        display_parts = [
            str(row[column]).strip()
            for column in spec.name_columns
            if column in frame.columns and not _is_missing(row[column]) and str(row[column]).strip()
        ]
        display = " / ".join(display_parts) or identity

        row_metadata = {
            "row_position": position,
            "row_identity": identity,
            "identity_columns": list(spec.identity_columns),
        }

        for column in spec.value_columns:
            metric_id = f"{spec.namespace}.{identity}.{_metric_token(column)}"
            metric_name = f"{display}: {column}"
            if column not in frame.columns:
                values.append(
                    extract_scalar(
                        None,
                        metric_id=metric_id,
                        name=metric_name,
                        source=source,
                        unit=spec.unit_by_column.get(column),
                        description=spec.description,
                        metadata={**row_metadata, "column": column},
                        availability=EvidenceAvailability.FIELD_MISSING,
                    )
                )
                continue

            values.append(
                extract_scalar(
                    row[column],
                    metric_id=metric_id,
                    name=metric_name,
                    source=source,
                    unit=spec.unit_by_column.get(column),
                    description=spec.description,
                    metadata={**row_metadata, "column": column},
                )
            )

    return tuple(values)


# =============================================================================
# Immutable catalog and builder
# =============================================================================


@dataclass(frozen=True, slots=True)
class EvidenceCatalog:
    """Immutable, indexed collection of unique normalized evidence values."""

    values: tuple[EvidenceValue, ...] = ()
    _index: Mapping[str, EvidenceValue] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        normalized = tuple(self.values)
        for position, value in enumerate(normalized):
            if not isinstance(value, EvidenceValue):
                raise TypeError(
                    f"values[{position}] must be EvidenceValue, got {type(value).__name__}."
                )
        index: dict[str, EvidenceValue] = {}
        for value in normalized:
            if value.metric_id in index:
                raise DuplicateEvidenceError(
                    f"Duplicate evidence metric_id: {value.metric_id!r}."
                )
            index[value.metric_id] = value
        object.__setattr__(self, "values", normalized)
        object.__setattr__(self, "_index", MappingProxyType(index))

    def __iter__(self) -> Iterator[EvidenceValue]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def __contains__(self, metric_id: object) -> bool:
        return isinstance(metric_id, str) and metric_id in self._index

    def get(self, metric_id: str) -> EvidenceValue | None:
        """Return one metric or ``None`` when it is absent from the catalog."""

        return self._index.get(metric_id)

    def require(self, metric_id: str) -> EvidenceValue:
        """Return one metric or raise a descriptive lookup error."""

        try:
            return self._index[metric_id]
        except KeyError as exc:
            raise KeyError(f"Evidence metric {metric_id!r} is not present.") from exc

    @property
    def available(self) -> tuple[EvidenceValue, ...]:
        return tuple(value for value in self.values if value.is_available)

    @property
    def unavailable(self) -> tuple[EvidenceValue, ...]:
        return tuple(value for value in self.values if not value.is_available)

    def merge(self, *others: EvidenceCatalog) -> EvidenceCatalog:
        """Return a new catalog and reject duplicate identifiers across inputs."""

        merged = list(self.values)
        for other in others:
            if not isinstance(other, EvidenceCatalog):
                raise TypeError("merge accepts EvidenceCatalog instances only.")
            merged.extend(other.values)
        return EvidenceCatalog(tuple(merged))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_count": len(self.values),
            "available_count": len(self.available),
            "unavailable_count": len(self.unavailable),
            "values": [value.to_dict() for value in self.values],
        }


class EvidenceBuilder:
    """Mutable construction helper that enforces metric uniqueness eagerly."""

    __slots__ = ("_values", "_metric_ids")

    def __init__(self) -> None:
        self._values: list[EvidenceValue] = []
        self._metric_ids: set[str] = set()

    def add(self, value: EvidenceValue) -> EvidenceBuilder:
        if not isinstance(value, EvidenceValue):
            raise TypeError(f"value must be EvidenceValue, got {type(value).__name__}.")
        if value.metric_id in self._metric_ids:
            raise DuplicateEvidenceError(f"Duplicate evidence metric_id: {value.metric_id!r}.")
        self._values.append(value)
        self._metric_ids.add(value.metric_id)
        return self

    def extend(self, values: Iterable[EvidenceValue]) -> EvidenceBuilder:
        for value in values:
            self.add(value)
        return self

    def scalar(self, value: Any, **kwargs: Any) -> EvidenceBuilder:
        return self.add(extract_scalar(value, **kwargs))

    def dataframe_cell(self, frame: pd.DataFrame | None, **kwargs: Any) -> EvidenceBuilder:
        return self.add(extract_dataframe_cell(frame, **kwargs))

    def dataframe_rows(
        self,
        frame: pd.DataFrame | None,
        *,
        spec: FrameExtractionSpec,
        source: str | None = None,
        strict: bool = True,
    ) -> EvidenceBuilder:
        return self.extend(
            extract_dataframe_rows(frame, spec=spec, source=source, strict=strict)
        )

    def build(self) -> EvidenceCatalog:
        return EvidenceCatalog(tuple(self._values))


# =============================================================================
# Adapter registry
# =============================================================================


class EvidenceAdapter(Protocol):
    """Protocol implemented by adapters from pipeline outputs to evidence."""

    def supports(self, source: Any) -> bool:
        """Return whether this adapter can normalize ``source``."""

    def extract(self, source: Any, *, strict: bool = True) -> EvidenceCatalog:
        """Normalize ``source`` into an immutable evidence catalog."""


@dataclass(frozen=True, slots=True)
class _AttributeFrameAdapter:
    """Adapter for current pipeline dataclasses containing canonical DataFrames."""

    target_types: tuple[type[Any], ...]
    frame_specs: Mapping[str, FrameExtractionSpec]
    scalar_attributes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.target_types or not all(isinstance(item, type) for item in self.target_types):
            raise TypeError("target_types must contain at least one concrete class.")
        object.__setattr__(self, "frame_specs", MappingProxyType(dict(self.frame_specs)))
        object.__setattr__(self, "scalar_attributes", tuple(self.scalar_attributes))

    def supports(self, source: Any) -> bool:
        return isinstance(source, self.target_types)

    def extract(self, source: Any, *, strict: bool = True) -> EvidenceCatalog:
        builder = EvidenceBuilder()
        source_name = _source_name(source)
        namespace = _metric_token(getattr(source, "module_name", type(source).__name__))

        for attribute in self.scalar_attributes:
            if not hasattr(source, attribute):
                builder.scalar(
                    None,
                    metric_id=f"{namespace}.attribute.{_metric_token(attribute)}",
                    name=f"{source_name} {attribute}",
                    source=source_name,
                    metadata={"attribute": attribute},
                    availability=EvidenceAvailability.FIELD_MISSING,
                )
                continue
            builder.scalar(
                getattr(source, attribute),
                metric_id=f"{namespace}.attribute.{_metric_token(attribute)}",
                name=f"{source_name} {attribute}",
                source=source_name,
                metadata={"attribute": attribute},
            )

        for attribute, spec in self.frame_specs.items():
            if not hasattr(source, attribute):
                for column in spec.value_columns:
                    builder.scalar(
                        None,
                        metric_id=(
                            f"{namespace}.{spec.namespace}.attribute-missing."
                            f"{_metric_token(column)}"
                        ),
                        name=f"{source_name} {attribute} {column}",
                        source=source_name,
                        metadata={"attribute": attribute, "column": column},
                        availability=EvidenceAvailability.FIELD_MISSING,
                    )
                continue
            frame = getattr(source, attribute)
            contextual_spec = FrameExtractionSpec(
                namespace=f"{namespace}.{spec.namespace}",
                value_columns=spec.value_columns,
                identity_columns=spec.identity_columns,
                name_columns=spec.name_columns,
                unit_by_column=spec.unit_by_column,
                description=spec.description,
            )
            builder.dataframe_rows(
                frame,
                spec=contextual_spec,
                source=f"{source_name}.{attribute}",
                strict=strict,
            )
        return builder.build()


class EvidenceRegistry:
    """Ordered adapter registry with explicit ambiguity detection."""

    __slots__ = ("_adapters",)

    def __init__(self, adapters: Sequence[EvidenceAdapter] = ()) -> None:
        self._adapters = tuple(adapters)
        for position, adapter in enumerate(self._adapters):
            if not callable(getattr(adapter, "supports", None)) or not callable(
                getattr(adapter, "extract", None)
            ):
                raise TypeError(f"adapters[{position}] does not satisfy EvidenceAdapter.")

    @property
    def adapters(self) -> tuple[EvidenceAdapter, ...]:
        return self._adapters

    def register(self, adapter: EvidenceAdapter) -> EvidenceRegistry:
        """Return a new registry with one adapter appended."""

        return EvidenceRegistry((*self._adapters, adapter))

    def extract(self, source: Any, *, strict: bool = True) -> EvidenceCatalog:
        matches = [adapter for adapter in self._adapters if adapter.supports(source)]
        if not matches:
            raise EvidenceExtractionError(
                f"No evidence adapter is registered for {type(source).__name__}."
            )
        if len(matches) > 1:
            raise EvidenceExtractionError(
                f"Multiple evidence adapters matched {type(source).__name__}; "
                "adapter selection must be unambiguous."
            )
        return matches[0].extract(source, strict=strict)


# =============================================================================
# Current pipeline adapter specifications
# =============================================================================


_MODULE_VALIDATION_ADAPTER = _AttributeFrameAdapter(
    target_types=(ModuleValidationResult,),
    frame_specs={
        "table_status": FrameExtractionSpec(
            namespace="functional.table_status",
            identity_columns=("table",),
            name_columns=("table",),
            value_columns=(
                "synthea_available",
                "psynthea_available",
                "synthea_rows",
                "psynthea_rows",
                "synthea_empty",
                "psynthea_empty",
                "row_difference",
                "relative_row_difference",
                "required",
                "blocking_issue",
            ),
        ),
        "clinical_signal": FrameExtractionSpec(
            namespace="functional.clinical_signal",
            identity_columns=("domain",),
            name_columns=("domain",),
            value_columns=(
                "synthea_signal_count",
                "psynthea_signal_count",
                "shared_code_count",
                "synthea_only_code_count",
                "psynthea_only_code_count",
                "expected_signal_detected_synthea",
                "expected_signal_detected_psynthea",
                "expected_terms",
                "blocking_issue",
            ),
        ),
        "distributional_similarity": FrameExtractionSpec(
            namespace="functional.distributional_similarity",
            identity_columns=("domain",),
            name_columns=("domain",),
            value_columns=(
                "synthea_total",
                "psynthea_total",
                "shared_code_count",
                "synthea_only_code_count",
                "psynthea_only_code_count",
                "jaccard_similarity",
                "overlap_coefficient",
                "jensen_shannon_divergence",
                "valid_for_distributional_comparison",
                "blocking_issue",
            ),
        ),
        "issues": FrameExtractionSpec(
            namespace="functional.issues",
            identity_columns=("domain", "issue"),
            name_columns=("domain", "issue"),
            value_columns=("severity", "details"),
        ),
        "summary": FrameExtractionSpec(
            namespace="functional.summary",
            identity_columns=("module_name",),
            name_columns=("module_name",),
            value_columns=(
                "status",
                "status_reason",
                "synthea_functional",
                "psynthea_functional",
                "valid_for_comparison",
                "blocking_issue_count",
                "warning_count",
                "synthea_condition_count",
                "psynthea_condition_count",
                "synthea_observation_count",
                "psynthea_observation_count",
                "mean_distributional_similarity",
                "mean_jensen_shannon_divergence",
            ),
        ),
    },
    scalar_attributes=("module_name",),
)


_MODULE_STATISTICAL_ADAPTER = _AttributeFrameAdapter(
    target_types=(ModuleStatisticalComparisonResult,),
    frame_specs={
        "continuous_tests": FrameExtractionSpec(
            namespace="statistics.continuous",
            identity_columns=("metric", "test_name"),
            name_columns=("metric", "test_name"),
            value_columns=(
                "statistic",
                "p_value",
                "effect_size",
                "significant",
                "n_synthea",
                "n_psynthea",
                "notes",
            ),
        ),
        "categorical_tests": FrameExtractionSpec(
            namespace="statistics.categorical",
            identity_columns=("domain", "test_name"),
            name_columns=("domain", "test_name"),
            value_columns=(
                "statistic",
                "p_value",
                "effect_size",
                "significant",
                "n_synthea",
                "n_psynthea",
                "notes",
            ),
        ),
        "prevalence_tests": FrameExtractionSpec(
            namespace="statistics.prevalence",
            identity_columns=("domain", "code"),
            name_columns=("domain", "code"),
            value_columns=(
                "synthea_events",
                "synthea_total",
                "psynthea_events",
                "psynthea_total",
                "synthea_prevalence",
                "psynthea_prevalence",
                "absolute_difference",
                "relative_difference",
                "risk_ratio",
                "risk_ratio_ci_lower",
                "risk_ratio_ci_upper",
                "odds_ratio",
                "odds_ratio_ci_lower",
                "odds_ratio_ci_upper",
                "test_name",
                "statistic",
                "p_value",
                "adjusted_p_value",
                "significant",
                "significant_after_fdr",
                "notes",
            ),
        ),
        "distribution_tests": FrameExtractionSpec(
            namespace="statistics.distribution",
            identity_columns=("domain", "test_name"),
            name_columns=("domain", "test_name"),
            value_columns=(
                "statistic",
                "p_value",
                "effect_size",
                "jensen_shannon_divergence",
                "significant",
                "n_synthea",
                "n_psynthea",
                "notes",
            ),
        ),
        "summary": FrameExtractionSpec(
            namespace="statistics.summary",
            identity_columns=("module_name",),
            name_columns=("module_name",),
            value_columns=(
                "validation_status",
                "valid_for_statistical_comparison",
                "skipped",
                "skip_reason",
                "continuous_test_count",
                "categorical_test_count",
                "prevalence_test_count",
                "distribution_test_count",
                "significant_test_count",
                "significant_after_fdr_count",
                "mean_jensen_shannon_divergence",
            ),
        ),
    },
    scalar_attributes=(),
)


_SPANISH_ADAPTATION_ADAPTER = _AttributeFrameAdapter(
    target_types=(SpanishAdaptationValidation,),
    frame_specs={
        attribute: FrameExtractionSpec(
            namespace=f"spanish.{attribute}",
            identity_columns=("domain", "indicator"),
            name_columns=("domain", "indicator"),
            value_columns=(
                "value",
                "numerator",
                "denominator",
                "fraction",
                "available",
                "evidence",
            ),
        )
        for attribute in (
            "primary_care",
            "referrals",
            "healthcare_flow",
            "clinical_context",
            "summary",
        )
    },
)


DEFAULT_EVIDENCE_REGISTRY = EvidenceRegistry(
    (
        _MODULE_STATISTICAL_ADAPTER,
        _MODULE_VALIDATION_ADAPTER,
        _SPANISH_ADAPTATION_ADAPTER,
    )
)


def collect_evidence(
    source: Any,
    *,
    strict: bool = True,
    registry: EvidenceRegistry = DEFAULT_EVIDENCE_REGISTRY,
) -> EvidenceCatalog:
    """Normalize one supported pipeline result using the configured registry."""

    if source is None:
        raise EvidenceExtractionError("Cannot collect evidence from None without a source schema.")
    if not isinstance(registry, EvidenceRegistry):
        raise TypeError("registry must be an EvidenceRegistry instance.")
    return registry.extract(source, strict=strict)