"""
The logical targets of a repository: the addresses by which a record refers to a record of another
tool, or to a unit inside it, possibly in another repository.

A target is the mapping ``{repository, id, unit}``, published as the definition ``target`` of the
resource ``addressing.v1``. A repository declares its identifier in ``repository.yml``, a record
type declares the field of its identifier by ``x-identifier``, and a consumer types a target field
by ``x-target-contract``. The section ``targets`` of ``anagraphe.yml`` enables the check, which
resolves the targets within one repository. A field path names one node of a document, and
converts to and from a JSON Pointer.

Examples
--------
A tool reads and compares two targets written in one repository::

    from anagraphe.targets import Target, read_manifest

    manifest = read_manifest(root).manifest
    repository = manifest.id if manifest is not None else None
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
from anagraphe.targets.manifest import Manifest, ManifestReading, check_manifest, read_manifest
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
    "InvalidTarget",
    "Manifest",
    "ManifestReading",
    "PointerError",
    "PointerReason",
    "ReadSide",
    "Reason",
    "Target",
    "TargetChecker",
    "TargetConfig",
    "admits",
    "check_manifest",
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
    "read_manifest",
    "to_pointer",
]
