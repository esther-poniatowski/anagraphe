"""Generate repository indexes from record metadata, and keep the pointers between files valid."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("anagraphe")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
