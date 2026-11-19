"""
The logical targets of a repository: the addresses by which a record refers to a record of another
tool, or to a unit inside it, possibly in another repository.

A target is the mapping ``{repository, id, unit}``, published as the definition ``target`` of the
resource ``addressing.v1``. A repository derives its identifier from the override of the section
``repository`` of ``anagraphe.yml``, its remote or its folder, a record type declares the field of
its identifier by ``x-identifier``, and a consumer types a target field
by ``x-target-contract``. The section ``targets`` of ``anagraphe.yml`` enables the check, which
resolves the targets within one repository. A field path names one node of a document, and
converts to and from a JSON Pointer.

Examples
--------
A tool reads and compares two targets written in one repository::

    from anagraphe.targets import Target, repository_identity

    repository = repository_identity(root, config.repository).id
    same = Target.parse(a).normalized(repository) == Target.parse(b).normalized(repository)
"""

from anagraphe.targets.configuration import ReadSide, TargetConfig
from anagraphe.targets.field_paths import (
    ANY_ITEM,
    ANY_KEY,
    FieldPath,
    FieldPathError,
    FieldPathReason,
    PointerError,
    PointerReason,
    expand,
    from_pointer,
    is_field_path,
    is_field_path_pattern,
    match_nodes,
    parse_field_path,
    parse_field_path_pattern,
    pointer_tokens,
    print_field_path,
    to_pointer,
)
from anagraphe.targets.identity import (
    DeclaredIdentity,
    Identity,
    IdentityProblem,
    IdentitySource,
    derive_identity,
    repository_identity,
)
from anagraphe.targets.model import InvalidTarget, Reason, Target, admits, parse_contracts
from anagraphe.targets.resource import ADDRESSING_ID, REPOSITORY_CONTRACT, TARGET_REFERENCE
from anagraphe.targets.service import TargetChecker
from anagraphe.targets.specification import IMPLEMENTED_SPECIFICATION

__all__ = [
    "ADDRESSING_ID",
    "ANY_ITEM",
    "ANY_KEY",
    "IMPLEMENTED_SPECIFICATION",
    "REPOSITORY_CONTRACT",
    "TARGET_REFERENCE",
    "FieldPath",
    "FieldPathError",
    "FieldPathReason",
    "DeclaredIdentity",
    "Identity",
    "IdentityProblem",
    "IdentitySource",
    "InvalidTarget",
    "PointerError",
    "PointerReason",
    "ReadSide",
    "Reason",
    "Target",
    "TargetChecker",
    "TargetConfig",
    "admits",
    "derive_identity",
    "expand",
    "from_pointer",
    "is_field_path",
    "is_field_path_pattern",
    "match_nodes",
    "parse_contracts",
    "parse_field_path",
    "parse_field_path_pattern",
    "pointer_tokens",
    "print_field_path",
    "repository_identity",
    "to_pointer",
]
