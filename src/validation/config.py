"""
Validated configuration models for reproducible validation runs.

This module defines the declarative configuration consumed by the validation
orchestration layer. It centralises cohort locations, module expectations,
statistical parameters, presentation options and output paths.

It intentionally does not load cohorts, execute comparisons, create folders,
generate figures or write reports. Those responsibilities belong to loaders,
comparison modules, plotting, reporting and the CLI respectively.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from hashlib import sha256
import json
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Literal, Mapping, Sequence

from validation.constants import (
    DEFAULT_DPI,
    DEFAULT_FIGURE_FORMAT,
    DEFAULT_SIGNIFICANCE_LEVEL,
)

if TYPE_CHECKING:
    from validation.plots import PlotConfig

__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "ConfigurationError",
    "CohortInputConfig",
    "ModuleConfig",
    "StatisticalConfig",
    "PresentationConfig",
    "OutputConfig",
    "ValidationRunConfig",
]


# =============================================================================
# Supported values and schema
# =============================================================================

CONFIG_SCHEMA_VERSION = 1

_FDR_METHOD_BENJAMINI_HOCHBERG = "benjamini-hochberg"
_SUPPORTED_FDR_METHODS = frozenset({_FDR_METHOD_BENJAMINI_HOCHBERG})
_SUPPORTED_FIGURE_FORMATS = frozenset(
    {"jpeg", "jpg", "pdf", "png", "svg", "tif", "tiff"}
)
_SUPPORTED_PREVALENCE_RANKING = frozenset(
    {"prevalence", "absolute_difference", "clinical_priority"}
)


class ConfigurationError(ValueError):
    """Raised when a validation-run configuration is internally invalid."""


# =============================================================================
# Input configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class CohortInputConfig:
    """Filesystem locations of the two cohorts being compared."""

    synthea_dir: Path
    psynthea_dir: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "synthea_dir", _normalise_path(self.synthea_dir))
        object.__setattr__(self, "psynthea_dir", _normalise_path(self.psynthea_dir))

        if self.synthea_dir == self.psynthea_dir:
            raise ConfigurationError(
                "synthea_dir and psynthea_dir must identify different cohort directories."
            )

    def validate_filesystem(self, *, required_filename: str = "patients.csv") -> None:
        """Validate input directories and their mandatory cohort file.

        Filesystem validation is explicit rather than performed in ``__post_init__``
        so configuration objects remain safe to construct in tests, dry runs and
        environments where paths are mounted only at execution time.
        """

        required_filename = _validate_relative_filename(
            required_filename,
            field_name="required_filename",
        )
        _validate_cohort_directory(
            self.synthea_dir,
            source_name="Synthea",
            required_filename=required_filename,
        )
        _validate_cohort_directory(
            self.psynthea_dir,
            source_name="psynthea",
            required_filename=required_filename,
        )


# =============================================================================
# Module configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class ModuleConfig:
    """Expected clinical signals for one independently validated module."""

    name: str
    required_tables: tuple[str, ...] = ()
    required_signal_domains: tuple[str, ...] = ()
    expected_condition_terms: tuple[str, ...] = ()
    expected_medication_terms: tuple[str, ...] = ()
    expected_procedure_terms: tuple[str, ...] = ()
    expected_observation_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalise_required_text(self.name, "name"))
        object.__setattr__(
            self,
            "required_tables",
            _normalise_terms(self.required_tables),
        )
        object.__setattr__(
            self,
            "required_signal_domains",
            _normalise_terms(self.required_signal_domains),
        )
        object.__setattr__(
            self,
            "expected_condition_terms",
            _normalise_terms(self.expected_condition_terms),
        )
        object.__setattr__(
            self,
            "expected_medication_terms",
            _normalise_terms(self.expected_medication_terms),
        )
        object.__setattr__(
            self,
            "expected_procedure_terms",
            _normalise_terms(self.expected_procedure_terms),
        )
        object.__setattr__(
            self,
            "expected_observation_terms",
            _normalise_terms(self.expected_observation_terms),
        )

    @property
    def has_expected_signals(self) -> bool:
        """Return whether at least one expected clinical signal is configured."""

        return any(
            (
                self.expected_condition_terms,
                self.expected_medication_terms,
                self.expected_procedure_terms,
                self.expected_observation_terms,
            )
        )


# =============================================================================
# Scientific configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class StatisticalConfig:
    """Statistical parameters shared by module-level comparisons.

    ``confidence_level`` defaults to ``1 - alpha`` when omitted, while remaining
    independently configurable for sensitivity analyses and conservative
    interval reporting.
    """

    alpha: float = DEFAULT_SIGNIFICANCE_LEVEL
    confidence_level: float | None = None
    top_n_codes: int = 25
    fdr_method: Literal["benjamini-hochberg"] = _FDR_METHOD_BENJAMINI_HOCHBERG

    def __post_init__(self) -> None:
        alpha = _normalise_open_probability(self.alpha, "alpha")
        confidence_level = (
            1.0 - alpha
            if self.confidence_level is None
            else _normalise_open_probability(
                self.confidence_level,
                "confidence_level",
            )
        )

        object.__setattr__(self, "alpha", alpha)
        object.__setattr__(self, "confidence_level", confidence_level)
        _require_positive_integer(self.top_n_codes, "top_n_codes")

        if self.fdr_method not in _SUPPORTED_FDR_METHODS:
            supported = ", ".join(sorted(_SUPPORTED_FDR_METHODS))
            raise ConfigurationError(
                f"fdr_method must be one of: {supported}; got {self.fdr_method!r}."
            )


# =============================================================================
# Presentation configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class PresentationConfig:
    """Report and publication-figure options for a validation run."""

    top_n_prevalence_differences: int = 10
    top_n_prevalence_plots: int = 15
    top_n_effect_sizes: int = 20
    top_n_p_values: int = 25
    prevalence_rank_by: Literal[
        "prevalence", "absolute_difference", "clinical_priority"
    ] = "absolute_difference"
    clinical_priority: tuple[str, ...] = ()
    prevalence_equivalence_margin: float | None = None
    continuous_effect_margin: float | None = 0.20
    categorical_effect_margin: float | None = 0.10
    annotate_values: bool = True
    figure_format: str = DEFAULT_FIGURE_FORMAT
    dpi: int = DEFAULT_DPI

    def __post_init__(self) -> None:
        _require_positive_integer(
            self.top_n_prevalence_differences,
            "top_n_prevalence_differences",
        )
        _require_positive_integer(self.top_n_prevalence_plots, "top_n_prevalence_plots")
        _require_positive_integer(self.top_n_effect_sizes, "top_n_effect_sizes")
        _require_positive_integer(self.top_n_p_values, "top_n_p_values")

        object.__setattr__(
            self,
            "prevalence_equivalence_margin",
            _normalise_optional_non_negative(
                self.prevalence_equivalence_margin,
                "prevalence_equivalence_margin",
            ),
        )
        object.__setattr__(
            self,
            "continuous_effect_margin",
            _normalise_optional_non_negative(
                self.continuous_effect_margin,
                "continuous_effect_margin",
            ),
        )
        object.__setattr__(
            self,
            "categorical_effect_margin",
            _normalise_optional_non_negative(
                self.categorical_effect_margin,
                "categorical_effect_margin",
            ),
        )
        _require_boolean(self.annotate_values, "annotate_values")

        if self.prevalence_rank_by not in _SUPPORTED_PREVALENCE_RANKING:
            supported = ", ".join(sorted(_SUPPORTED_PREVALENCE_RANKING))
            raise ConfigurationError(
                f"prevalence_rank_by must be one of: {supported}; "
                f"got {self.prevalence_rank_by!r}."
            )

        priority = _normalise_clinical_priority(self.clinical_priority)
        object.__setattr__(self, "clinical_priority", priority)

        if self.prevalence_rank_by == "clinical_priority" and not priority:
            raise ConfigurationError(
                "clinical_priority must not be empty when "
                "prevalence_rank_by='clinical_priority'."
            )

        figure_format = str(self.figure_format).strip().lower().lstrip(".")
        if figure_format not in _SUPPORTED_FIGURE_FORMATS:
            supported = ", ".join(sorted(_SUPPORTED_FIGURE_FORMATS))
            raise ConfigurationError(
                f"figure_format must be one of: {supported}; got {self.figure_format!r}."
            )
        object.__setattr__(self, "figure_format", figure_format)

        _require_positive_integer(self.dpi, "dpi")

    def to_plot_config(
        self,
        *,
        alpha: float = DEFAULT_SIGNIFICANCE_LEVEL,
    ) -> PlotConfig:
        """Create the plotting-layer configuration without import-time coupling."""

        alpha = _normalise_open_probability(alpha, "alpha")

        from validation.plots import PlotConfig

        return PlotConfig(
            alpha=alpha,
            top_n_prevalence=self.top_n_prevalence_plots,
            top_n_effect_sizes=self.top_n_effect_sizes,
            top_n_p_values=self.top_n_p_values,
            prevalence_rank_by=self.prevalence_rank_by,
            prevalence_equivalence_margin=self.prevalence_equivalence_margin,
            continuous_effect_margin=self.continuous_effect_margin,
            categorical_effect_margin=self.categorical_effect_margin,
            clinical_priority=self.clinical_priority,
            annotate_values=self.annotate_values,
        )


# =============================================================================
# Output configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """Output layout for reports, figures and machine-readable tables."""

    root_dir: Path
    report_filename: str = "validation_report.md"
    figures_subdir: str = "figures"
    tables_subdir: str = "tables"
    overwrite: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "root_dir", _normalise_path(self.root_dir))
        object.__setattr__(
            self,
            "report_filename",
            _validate_relative_filename(
                self.report_filename,
                field_name="report_filename",
                suffix=".md",
            ),
        )
        object.__setattr__(
            self,
            "figures_subdir",
            _validate_relative_subdirectory(self.figures_subdir, "figures_subdir"),
        )
        object.__setattr__(
            self,
            "tables_subdir",
            _validate_relative_subdirectory(self.tables_subdir, "tables_subdir"),
        )
        _require_boolean(self.overwrite, "overwrite")

        if self.figures_subdir == self.tables_subdir:
            raise ConfigurationError(
                "figures_subdir and tables_subdir must identify different directories."
            )

    @property
    def report_path(self) -> Path:
        """Return the Markdown report path."""

        return self.root_dir / self.report_filename

    @property
    def figures_dir(self) -> Path:
        """Return the figure output directory."""

        return self.root_dir / self.figures_subdir

    @property
    def tables_dir(self) -> Path:
        """Return the tabular output directory."""

        return self.root_dir / self.tables_subdir

    def validate_output_state(self) -> None:
        """Reject existing output artefacts unless overwriting is explicit."""

        if self.overwrite or not self.root_dir.exists():
            return
        if not self.root_dir.is_dir():
            raise NotADirectoryError(
                f"Validation output root is not a directory: {self.root_dir}"
            )

        existing = [
            path
            for path in (self.report_path, self.figures_dir, self.tables_dir)
            if _path_contains_output(path)
        ]
        if existing:
            formatted = ", ".join(str(path) for path in existing)
            raise FileExistsError(
                "Validation output already exists and overwrite=False: "
                f"{formatted}"
            )


# =============================================================================
# Complete run configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class ValidationRunConfig:
    """Complete, immutable and serialisable validation-run specification."""

    inputs: CohortInputConfig
    output: OutputConfig
    modules: tuple[ModuleConfig, ...]
    statistics: StatisticalConfig = field(default_factory=StatisticalConfig)
    presentation: PresentationConfig = field(default_factory=PresentationConfig)
    reference_date: date | None = None
    run_name: str = "psynthea-validation"
    schema_version: int = CONFIG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.inputs, CohortInputConfig):
            raise ConfigurationError("inputs must be a CohortInputConfig instance.")
        if not isinstance(self.output, OutputConfig):
            raise ConfigurationError("output must be an OutputConfig instance.")
        if not isinstance(self.statistics, StatisticalConfig):
            raise ConfigurationError("statistics must be a StatisticalConfig instance.")
        if not isinstance(self.presentation, PresentationConfig):
            raise ConfigurationError("presentation must be a PresentationConfig instance.")

        modules = tuple(self.modules)
        if not modules:
            raise ConfigurationError("At least one module must be configured.")
        if not all(isinstance(module, ModuleConfig) for module in modules):
            raise ConfigurationError("modules must contain only ModuleConfig instances.")

        duplicate_names = _duplicate_values(module.name.casefold() for module in modules)
        if duplicate_names:
            duplicates = ", ".join(sorted(duplicate_names))
            raise ConfigurationError(f"Module names must be unique; duplicates: {duplicates}.")

        object.__setattr__(self, "modules", modules)
        object.__setattr__(
            self,
            "run_name",
            _normalise_required_text(self.run_name, "run_name"),
        )

        if self.reference_date is not None and not isinstance(self.reference_date, date):
            raise ConfigurationError("reference_date must be a datetime.date or None.")
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != CONFIG_SCHEMA_VERSION
        ):
            raise ConfigurationError(
                "Unsupported configuration schema_version "
                f"{self.schema_version!r}; expected {CONFIG_SCHEMA_VERSION}."
            )

    def validate_filesystem(self) -> None:
        """Validate input files and output overwrite constraints."""

        self.inputs.validate_filesystem()
        self.output.validate_output_state()

    def module(self, name: str) -> ModuleConfig:
        """Return one configured module using a case-insensitive name lookup."""

        target = _normalise_required_text(name, "name").casefold()
        for module in self.modules:
            if module.name.casefold() == target:
                return module
        raise KeyError(f"Unknown configured module: {name!r}.")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation suitable for audit metadata."""

        return _json_compatible(asdict(self))

    def to_plot_config(self) -> PlotConfig:
        """Create plotting configuration using this run's significance level."""

        return self.presentation.to_plot_config(alpha=self.statistics.alpha)

    def canonical_json(self) -> str:
        """Return deterministic JSON for the complete execution configuration."""

        return _canonical_json(self.to_dict())

    def scientific_dict(self) -> dict[str, Any]:
        """Return only parameters that define the scientific comparison design.

        Filesystem locations and presentation-only choices are intentionally
        excluded so equivalent analyses remain identifiable across machines and
        output formats.
        """

        return {
            "schema_version": self.schema_version,
            "modules": [_json_compatible(asdict(module)) for module in self.modules],
            "statistics": _json_compatible(asdict(self.statistics)),
            "reference_date": _json_compatible(self.reference_date),
        }

    @property
    def configuration_fingerprint(self) -> str:
        """Return SHA-256 for the complete execution configuration."""

        return _sha256_text(self.canonical_json())

    @property
    def scientific_fingerprint(self) -> str:
        """Return SHA-256 for scientific parameters independent of local paths."""

        return _sha256_text(_canonical_json(self.scientific_dict()))

    @property
    def fingerprint(self) -> str:
        """Backward-compatible alias for ``configuration_fingerprint``."""

        return self.configuration_fingerprint

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> ValidationRunConfig:
        """Build a validated configuration from a nested mapping.

        This constructor is intended for future JSON/TOML/YAML adapters while
        keeping parsing concerns outside the configuration model itself.
        """

        if not isinstance(values, Mapping):
            raise ConfigurationError("Configuration root must be a mapping.")

        input_values = _required_mapping_section(values, "inputs")
        output_values = _required_mapping_section(values, "output")
        module_values = _required_sequence_section(values, "modules")
        statistics_values = _optional_mapping_section(values, "statistics")
        presentation_values = _optional_mapping_section(values, "presentation")

        inputs = _construct_config(
            CohortInputConfig,
            input_values,
            section="inputs",
        )
        output = _construct_config(
            OutputConfig,
            output_values,
            section="output",
        )
        statistics = _construct_config(
            StatisticalConfig,
            statistics_values,
            section="statistics",
        )
        presentation = _construct_config(
            PresentationConfig,
            presentation_values,
            section="presentation",
        )

        modules: list[ModuleConfig] = []
        for index, item in enumerate(module_values):
            if not isinstance(item, Mapping):
                raise ConfigurationError(
                    f"modules[{index}] must be a mapping, got {type(item).__name__}."
                )
            modules.append(
                _construct_config(
                    ModuleConfig,
                    item,
                    section=f"modules[{index}]",
                )
            )

        reference_date = _parse_optional_date(values.get("reference_date"))

        try:
            return cls(
                inputs=inputs,
                output=output,
                modules=tuple(modules),
                statistics=statistics,
                presentation=presentation,
                reference_date=reference_date,
                run_name=values.get("run_name", "psynthea-validation"),
                schema_version=values.get("schema_version", CONFIG_SCHEMA_VERSION),
            )
        except ConfigurationError:
            raise
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                f"Invalid root configuration: {error}"
            ) from error


# =============================================================================
# Validation helpers
# =============================================================================


def _normalise_path(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)):
        raise ConfigurationError(
            f"Path values must be str or pathlib.Path, got {type(value).__name__}."
        )

    text = str(value).strip()
    if not text:
        raise ConfigurationError("Path values must not be empty.")

    return Path(text).expanduser()


def _normalise_required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ConfigurationError(f"{field_name} must be a string.")

    normalised = " ".join(value.split())
    if not normalised:
        raise ConfigurationError(f"{field_name} must not be empty.")
    return normalised


def _normalise_terms(
    values: Sequence[str],
    *,
    case_sensitive: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ConfigurationError("Expected-term collections must be sequences, not strings.")
    if not isinstance(values, Sequence):
        raise ConfigurationError("Expected-term collections must be sequences.")

    normalised: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = _normalise_required_text(value, "expected term")
        key = term if case_sensitive else term.casefold()
        if key not in seen:
            normalised.append(term)
            seen.add(key)
    return tuple(normalised)


def _normalise_clinical_priority(values: Sequence[str]) -> tuple[str, ...]:
    priority = _normalise_terms(values, case_sensitive=True)
    for value in priority:
        domain, separator, code = value.partition(":")
        if not separator or not domain.strip() or not code.strip():
            raise ConfigurationError(
                "Each clinical_priority entry must use non-empty 'domain:code' format; "
                f"got {value!r}."
            )
    return priority


def _normalise_open_probability(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{field_name} must be numeric.")
    normalised = float(value)
    if not 0.0 < normalised < 1.0:
        raise ConfigurationError(f"{field_name} must be strictly between 0 and 1.")
    return normalised


def _normalise_optional_non_negative(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{field_name} must be numeric or None.")
    normalised = float(value)
    if normalised < 0.0:
        raise ConfigurationError(f"{field_name} must be non-negative.")
    return normalised


def _require_positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{field_name} must be a positive integer.")


def _require_boolean(value: bool, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ConfigurationError(f"{field_name} must be a boolean.")


def _validate_relative_filename(
    value: str,
    *,
    field_name: str,
    suffix: str | None = None,
) -> str:
    filename = _normalise_required_text(value, field_name)
    path = PurePath(filename)
    if path.is_absolute() or len(path.parts) != 1 or filename in {".", ".."}:
        raise ConfigurationError(f"{field_name} must be a simple relative filename.")
    if suffix is not None and path.suffix.lower() != suffix:
        raise ConfigurationError(f"{field_name} must use the {suffix} extension.")
    return filename


def _validate_relative_subdirectory(value: str, field_name: str) -> str:
    directory = _normalise_required_text(value, field_name)
    path = PurePath(directory)
    if path.is_absolute() or ".." in path.parts or path == PurePath("."):
        raise ConfigurationError(
            f"{field_name} must be a relative subdirectory contained in root_dir."
        )
    return str(path)


def _validate_cohort_directory(
    path: Path,
    *,
    source_name: str,
    required_filename: str,
) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{source_name} cohort directory not found: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"{source_name} cohort path is not a directory: {path}")

    required_path = path / required_filename
    if not required_path.is_file():
        raise FileNotFoundError(
            f"Required {source_name} cohort file not found: {required_path}"
        )


def _path_contains_output(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_file() or path.is_symlink():
        return True
    return any(path.iterdir())


def _duplicate_values(values: Sequence[str] | Any) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_compatible(item) for item in value]
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    return value


def _canonical_json(values: Mapping[str, Any]) -> str:
    return json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _required_mapping_section(
    values: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    if key not in values:
        raise ConfigurationError(f"Missing required configuration section: {key}.")
    section = values[key]
    if not isinstance(section, Mapping):
        raise ConfigurationError(f"{key} must be a mapping.")
    return section


def _optional_mapping_section(
    values: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    section = values.get(key, {})
    if not isinstance(section, Mapping):
        raise ConfigurationError(f"{key} must be a mapping.")
    return section


def _required_sequence_section(
    values: Mapping[str, Any],
    key: str,
) -> Sequence[Any]:
    if key not in values:
        raise ConfigurationError(f"Missing required configuration section: {key}.")
    section = values[key]
    if isinstance(section, (str, bytes)) or not isinstance(section, Sequence):
        raise ConfigurationError(f"{key} must be a sequence.")
    return section


def _construct_config(
    model: type[Any],
    values: Mapping[str, Any],
    *,
    section: str,
) -> Any:
    try:
        return model(**dict(values))
    except ConfigurationError as error:
        raise ConfigurationError(f"Invalid {section}: {error}") from error
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"Invalid {section}: {error}") from error


def _parse_optional_date(value: object) -> date | None:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ConfigurationError(
                "reference_date must use ISO format YYYY-MM-DD."
            ) from error
    raise ConfigurationError("reference_date must be a date, ISO date string or None.")
