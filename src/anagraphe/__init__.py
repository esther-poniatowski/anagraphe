"""Generate repository indexes from record metadata and check their drift."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("anagraphe")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
