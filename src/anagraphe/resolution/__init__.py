"""
The record resolver of ADR 0009: it locates and reads the record of another repository named by a
logical target, verified against a selected state of that repository.

The library composes four parts:

- the section ``resolution`` of ``anagraphe.yml`` and the machine file of the local clones,
  :mod:`anagraphe.resolution.configuration`;
- the resolution context of a root, derived from its submodules and its declared repositories,
  :mod:`anagraphe.resolution.context`;
- the port of a repository-state provider, with an in-memory provider and an empty one,
  :mod:`anagraphe.resolution.provider`;
- the operations ``resolve`` and ``read``, :mod:`anagraphe.resolution.resolver`.

Examples
--------
A tool reads the record of a target into another repository::

    from anagraphe.resolution import RecordResolver, build_context, parse_section
    from anagraphe.targets.identity import repository_identity

    identity = repository_identity(root, declared)
    context = build_context(root, identity, parse_section(root, raw), provider)
    resolver = RecordResolver(context, provider, declarations)
    resolution = resolver.resolve(target)
    if resolution.outcome is Outcome.RECORD:
        read = resolver.read(resolution, contracts)
"""

# The check of the targets imports the modules of this package, so the package of the targets
# loads first, whichever of the two packages a program imports first.
import anagraphe.targets  # noqa: F401  # pylint: disable=unused-import

from anagraphe.resolution.configuration import (
    MACHINE_VARIABLE,
    DeclaredRepository,
    ResolutionConfig,
    parse_section,
    remote_problem,
)
from anagraphe.resolution.context import Entry, ResolutionContext, Unnamed, build_context
from anagraphe.resolution.provider import (
    Availability,
    Blob,
    EmptyProvider,
    Escaping,
    MemoryProvider,
    Missing,
    Mode,
    Reading,
    State,
    StateProvider,
    Unavailable,
    confined,
)
from anagraphe.resolution.resolver import (
    Outcome,
    Provenance,
    RecordRead,
    RecordResolver,
    Resolution,
)
from anagraphe.targets.verification import Finding

__all__ = [
    "MACHINE_VARIABLE",
    "Availability",
    "Blob",
    "DeclaredRepository",
    "EmptyProvider",
    "Entry",
    "Escaping",
    "Finding",
    "MemoryProvider",
    "Missing",
    "Mode",
    "Outcome",
    "Provenance",
    "Reading",
    "RecordRead",
    "RecordResolver",
    "Resolution",
    "ResolutionConfig",
    "ResolutionContext",
    "State",
    "StateProvider",
    "Unavailable",
    "Unnamed",
    "build_context",
    "confined",
    "parse_section",
    "remote_problem",
]
