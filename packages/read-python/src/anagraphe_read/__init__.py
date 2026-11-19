"""Read the addressing of Anagraphe: logical targets, repository identities, records and bindings."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("anagraphe-read")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
