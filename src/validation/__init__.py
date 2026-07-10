"""Scientific validation framework for Psynthea versus Synthea.

The package provides reproducible tooling for cohort loading, metric
computation, statistical comparison, reporting and visualisation used in the
scientific validation of Psynthea against Synthea.

Importing :mod:`validation` has no side effects and performs no expensive
initialisation.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__author__ = "IRYCIS"
__license__ = "Apache-2.0"

_PACKAGE_NAME = "psynthea-validation"


def _get_version() -> str:
    """Return the installed package version.

    Falls back to a development version when the package metadata is not yet
    available (for example when running directly from the source tree).
    """
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.0.0"


__version__: str = _get_version()

__all__ = ["__version__"]