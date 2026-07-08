"""
Canonical data models used throughout the validation framework.

The framework never works directly with folders or CSV files.
Instead, every loader converts raw outputs into a ValidationCohort,
which becomes the single internal representation used by all
subsequent modules.

This design decouples data loading from analysis and allows the
framework to support multiple generators (psynthea, Synthea Java,
future simulators) without modifying the validation pipeline.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(slots=True)
class ValidationCohort:
    """
    Canonical representation of a synthetic cohort.

    Every loader must return a ValidationCohort object.

    All downstream components (metrics, statistics, plots,
    reports and comparisons) operate exclusively on this model.
    """

    # -------------------------------------------------------------------------
    # Metadata
    # -------------------------------------------------------------------------

    source: str
    output_path: Path | None = None

    # -------------------------------------------------------------------------
    # Core clinical tables
    # -------------------------------------------------------------------------

    patients: pd.DataFrame | None = None
    encounters: pd.DataFrame | None = None
    conditions: pd.DataFrame | None = None
    medications: pd.DataFrame | None = None
    procedures: pd.DataFrame | None = None
    observations: pd.DataFrame | None = None

    @property
    def n_patients(self) -> int:
        """Return the number of patients."""

        return 0 if self.patients is None else len(self.patients)

    @property
    def n_encounters(self) -> int:
        """Return the number of encounters."""

        return 0 if self.encounters is None else len(self.encounters)

    @property
    def n_conditions(self) -> int:
        """Return the number of clinical conditions."""

        return 0 if self.conditions is None else len(self.conditions)

    @property
    def n_medications(self) -> int:
        """Return the number of medication records."""

        return 0 if self.medications is None else len(self.medications)

    @property
    def n_procedures(self) -> int:
        """Return the number of procedure records."""

        return 0 if self.procedures is None else len(self.procedures)

    @property
    def n_observations(self) -> int:
        """Return the number of clinical observations."""

        return 0 if self.observations is None else len(self.observations)

    @property
    def summary(self) -> dict:
        """
        Return a compact summary of the cohort.

        Useful for quick inspection, logging and validation.
        """

        return {
            "source": self.source,
            "patients": self.n_patients,
            "encounters": self.n_encounters,
            "conditions": self.n_conditions,
            "medications": self.n_medications,
            "procedures": self.n_procedures,
            "observations": self.n_observations,
        }
