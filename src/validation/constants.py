"""
Global constants used throughout the validation framework.

This module centralises all reusable constant values to avoid hard-coded
strings across the project and to simplify future maintenance.

No validation logic should be implemented here.
"""

from pathlib import Path

# =============================================================================
# Supported cohort sources
# =============================================================================

SOURCE_PSYNTHEA = "psynthea"
SOURCE_SYNTHEA = "synthea-java"


# =============================================================================
# Standard CSV filenames
# =============================================================================

CSV_FILES = {
    "patients": "patients.csv",
    "encounters": "encounters.csv",
    "conditions": "conditions.csv",
    "medications": "medications.csv",
    "observations": "observations.csv",
}


# =============================================================================
# Standard folder names
# =============================================================================

RAW_DATA_FOLDER = Path("data/raw")
PROCESSED_DATA_FOLDER = Path("data/processed")
REPORTS_FOLDER = Path("reports")
FIGURES_FOLDER = Path("figures")


# =============================================================================
# Default statistical configuration
# =============================================================================

DEFAULT_SIGNIFICANCE_LEVEL = 0.05
DEFAULT_CONFIDENCE_LEVEL = 0.95


# =============================================================================
# Default plotting configuration
# =============================================================================

DEFAULT_DPI = 300
DEFAULT_FIGURE_FORMAT = "png"

# =============================================================================
# Demographic constants
# =============================================================================

AGE_BANDS = [
    0,
    5,
    15,
    25,
    35,
    45,
    55,
    65,
    75,
    85,
    200,
]

AGE_LABELS = [
    "0–4",
    "5–14",
    "15–24",
    "25–34",
    "35–44",
    "45–54",
    "55–64",
    "65–74",
    "75–84",
    "85+",
]