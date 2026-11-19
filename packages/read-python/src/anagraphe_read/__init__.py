"""
Read the addressing of Anagraphe: logical targets, repository identities, records and bindings.

The distribution ``anagraphe-read`` is the Python read side of Anagraphe. A consumer opens a
repository with :func:`open_repository`, which locates and loads its ``anagraphe.yml``, derives its
identity and builds its resolution context, then resolves the logical targets of its records and
reads the bindings of its texts through the returned :class:`Repository`.

This module is the interface of the distribution, and every name of ``__all__`` is part of it. The
subpackages and modules whose names open on an underscore are private: their names and their
contents change without a change of the version of the distribution.

Examples
--------
A tool reads the record that a target names in another repository::

    from anagraphe_read import Outcome, Target, open_repository

    repository = open_repository(root)
    resolution = repository.resolve(Target.parse({"repository": "lab", "id": "ada"}))
    if resolution.outcome is Outcome.RECORD:
        read = repository.read(resolution, (("test:person",),))
"""

from importlib.metadata import PackageNotFoundError, version

from anagraphe_read._bindings.model import Binding, Merge, Role
from anagraphe_read._configuration import Configuration
from anagraphe_read._core.configuration import ConfigurationError
from anagraphe_read._repository import Repository, addressing_schema, git_provider, open_repository
from anagraphe_read._resolution.provider import (
    Availability,
    Blob,
    Escaping,
    MemoryProvider,
    Missing,
    Mode,
    Reading,
    State,
    StateProvider,
    Unavailable,
)
from anagraphe_read._resolution.resolver import Outcome, Provenance, RecordRead, Resolution
from anagraphe_read._targets.identity import Identity
from anagraphe_read._targets.kinds import (
    AMBIGUOUS_UNIT,
    ESCAPING_TARGET_PATH,
    IDENTITY_DISAGREEMENT,
    INVALID_RECORD_REGISTRY,
    INVALID_TARGET_REPOSITORY,
    INVALID_TARGET_STATE,
    LINKED_TARGET_PATH,
    RENAMED_REPOSITORY,
    RENAMED_TARGET,
    RETIRED_REPOSITORY_MANIFEST,
    RETIRED_TARGET,
    STALE_TARGET_REGISTRY,
    TARGET_CONTRACT_MISMATCH,
    UNBOUND_TARGET,
    UNKNOWN_RECORD,
    UNKNOWN_REPOSITORY,
    UNKNOWN_UNIT,
    UNREADABLE_RECORD,
    UNREADABLE_TARGET_STATE,
    UNVERIFIED_TARGET,
)
from anagraphe_read._targets.model import InvalidTarget, Target
from anagraphe_read._targets.resource import ADDRESSING_ID
from anagraphe_read._targets.specification import IMPLEMENTED_SPECIFICATION
from anagraphe_read._targets.verification import Finding

try:
    __version__ = version("anagraphe-read")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    # The entry point and the repository it opens.
    "Configuration",
    "ConfigurationError",
    "Repository",
    "open_repository",
    # The logical targets and their resolution.
    "Finding",
    "Identity",
    "InvalidTarget",
    "Outcome",
    "Provenance",
    "RecordRead",
    "Resolution",
    "Target",
    # The bindings of texts.
    "Binding",
    "Merge",
    "Role",
    # The port of a repository-state provider, its readings and its providers.
    "Availability",
    "Blob",
    "Escaping",
    "MemoryProvider",
    "Missing",
    "Mode",
    "Reading",
    "State",
    "StateProvider",
    "Unavailable",
    "git_provider",
    # The kinds of the findings of a resolution, a read and an identity.
    "AMBIGUOUS_UNIT",
    "ESCAPING_TARGET_PATH",
    "IDENTITY_DISAGREEMENT",
    "INVALID_RECORD_REGISTRY",
    "INVALID_TARGET_REPOSITORY",
    "INVALID_TARGET_STATE",
    "LINKED_TARGET_PATH",
    "RENAMED_REPOSITORY",
    "RENAMED_TARGET",
    "RETIRED_REPOSITORY_MANIFEST",
    "RETIRED_TARGET",
    "STALE_TARGET_REGISTRY",
    "TARGET_CONTRACT_MISMATCH",
    "UNBOUND_TARGET",
    "UNKNOWN_RECORD",
    "UNKNOWN_REPOSITORY",
    "UNKNOWN_UNIT",
    "UNREADABLE_RECORD",
    "UNREADABLE_TARGET_STATE",
    "UNVERIFIED_TARGET",
    # The published specification.
    "ADDRESSING_ID",
    "IMPLEMENTED_SPECIFICATION",
    "addressing_schema",
    # The version of the distribution.
    "__version__",
]
