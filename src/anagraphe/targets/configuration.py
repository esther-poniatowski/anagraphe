"""
The section ``targets`` of ``anagraphe.yml``, which enables the check of the logical targets.

The section declares two optional keys:

- ``records``, the schema registry through which a record reaches the schema of its contract, and
  the key of a record naming its contract, ``_schema`` by default, as the section ``bindings``
  declares them. Without it, the check reads the identifiers of the records and the manifest, and
  finds no target field;
- ``exclude``, the files left unread by the check, after the shared exclusions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from anagraphe.core.configuration import known_keys
from anagraphe.core.exclusions import Exemptions, exemptions
from anagraphe.core.metadata import MetadataReader
from anagraphe.core.schemas import RecordSchemas, parse_records

#: The keys of the section ``targets``.
SECTION_KEYS = frozenset({"records", "exclude"})


@dataclass(frozen=True)
class TargetConfig:
    """The resolved declaration of the check of the targets of one repository."""

    records: RecordSchemas | None = None
    exemptions: Exemptions = Exemptions()


def parse_section(
    root: Path,
    raw: Mapping[str, Any],
    shared: Exemptions,
    metadata: MetadataReader | None = None,
    field_name: str = "targets",
) -> TargetConfig:
    """Validate and resolve the section ``targets``, its exemptions added to the shared ones."""
    known_keys(raw, SECTION_KEYS, field_name)
    return TargetConfig(
        records=parse_records(root, raw.get("records"), f"{field_name}.records"),
        exemptions=shared.union(
            exemptions(raw.get("exclude"), f"{field_name}.exclude", root, metadata)
        ),
    )
