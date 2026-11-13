"""
The logical target: its written form, its normalization, and the contracts that it admits.

A target is the mapping ``{repository, id, unit}``, read by the YAML reader alone. An absent
``repository`` names the repository holding the citing file, so the normalization fills it, and two
targets are equal when their normalized mappings are equal. A target with ``repository`` and
without ``id`` names the repository itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable

from anagraphe.targets.resource import CONTRACT_ENTRY, matches

#: The keys of a target, each with the identifier definition of its value.
COMPONENTS = {"repository": "repository-id", "id": "record-id", "unit": "unit-id"}


class Reason(StrEnum):
    """Why a value is not a logical target, in the order of the checks."""

    NOT_A_MAPPING = "not-a-mapping"
    UNKNOWN_KEY = "unknown-key"
    NOTHING_NAMED = "no-record-or-repository"
    UNIT_WITHOUT_RECORD = "unit-without-record"
    INVALID_COMPONENT = "invalid-component"


class InvalidTarget(ValueError):
    """Report a value that is not a logical target, with the reason of the first failed check."""

    def __init__(self, reason: Reason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


@dataclass(frozen=True)
class Target:
    """A logical target: a record, a unit inside it, or a repository.

    Examples
    --------
    >>> target = Target.parse({"id": "kriegeskorte_nikolaus"})
    >>> target.normalized("geonexus").as_mapping()
    {'repository': 'geonexus', 'id': 'kriegeskorte_nikolaus'}
    >>> target.normalized("geonexus") == Target.parse(
    ...     {"repository": "geonexus", "id": "kriegeskorte_nikolaus"})
    True
    >>> Target.parse({"unit": "eta_rep"})
    Traceback (most recent call last):
    ...
    anagraphe.targets.model.InvalidTarget: a target names a record under id, or a repository under repository
    """

    repository: str | None = None
    id: str | None = None
    unit: str | None = None

    @classmethod
    def parse(cls, value: Any) -> Target:
        """Read a target from its written form.

        Raises
        ------
        InvalidTarget
            If the value is not a mapping, holds another key, names neither a record nor a
            repository, holds a unit without a record, or holds a component outside its pattern.
        """
        if not isinstance(value, dict):
            raise InvalidTarget(
                Reason.NOT_A_MAPPING, "a target is a mapping {repository, id, unit}"
            )
        unknown = sorted(str(key) for key in value if key not in COMPONENTS)
        if unknown:
            raise InvalidTarget(
                Reason.UNKNOWN_KEY,
                f"a target holds only repository, id and unit, not {', '.join(unknown)}",
            )
        if "id" not in value and "repository" not in value:
            raise InvalidTarget(
                Reason.NOTHING_NAMED,
                "a target names a record under id, or a repository under repository",
            )
        if "unit" in value and "id" not in value:
            raise InvalidTarget(
                Reason.UNIT_WITHOUT_RECORD, "a target holding a unit names its record under id"
            )
        for key, definition in COMPONENTS.items():
            if key in value and not matches(definition, value[key]):
                raise InvalidTarget(
                    Reason.INVALID_COMPONENT,
                    f"{key} {value[key]!r} lies outside the pattern of {definition}",
                )
        return cls(value.get("repository"), value.get("id"), value.get("unit"))

    @property
    def names_repository(self) -> bool:
        """Whether the target names a repository itself, rather than a record of it."""
        return self.id is None

    def normalized(self, repository: str | None) -> Target:
        """Return the target with its repository filled by the repository holding the citing file;
        unchanged when that repository declares no identifier."""
        if self.repository is not None or repository is None:
            return self
        return Target(repository, self.id, self.unit)

    def __str__(self) -> str:
        """Return the target in the flow form of its mapping, as a record writes it.

        Examples
        --------
        >>> str(Target("geonexus", "smith2024"))
        '{repository: geonexus, id: smith2024}'
        """
        return "{" + ", ".join(f"{key}: {value}" for key, value in self.as_mapping().items()) + "}"

    def as_mapping(self) -> dict[str, str]:
        """Return the written form of the target, without its absent keys."""
        return {
            key: value
            for key, value in (
                ("repository", self.repository),
                ("id", self.id),
                ("unit", self.unit),
            )
            if value is not None
        }


def parse_contracts(value: Any) -> tuple[str, ...]:
    """Read the value of ``x-target-contract``: a non-empty list of contract identifiers.

    Raises
    ------
    ValueError
        If the value is not a non-empty list, or holds an entry that is no contract identifier.

    Examples
    --------
    >>> parse_contracts(["geonexus:contact", "homilia:contact@1"])
    ('geonexus:contact', 'homilia:contact@1')
    >>> parse_contracts("geonexus:contact")
    Traceback (most recent call last):
    ...
    ValueError: x-target-contract holds a non-empty list of contract identifiers
    """
    if not isinstance(value, list) or not value:
        raise ValueError("x-target-contract holds a non-empty list of contract identifiers")
    for entry in value:
        if not isinstance(entry, str) or not CONTRACT_ENTRY.fullmatch(entry):
            raise ValueError(
                f"x-target-contract holds {entry!r}, which is no contract identifier "
                "namespace:name or namespace:name@version"
            )
    return tuple(value)


def admits(entries: Iterable[str], contracts: Iterable[str]) -> bool:
    """Whether an entry of ``x-target-contract`` admits one of the contracts of a record: its
    ``_schema``, or a contract that its root schema declares under ``x-implements``.

    An entry ``namespace:name`` admits every version of that contract, and an entry
    ``namespace:name@n`` admits that version only.

    Examples
    --------
    >>> admits(["geonexus:contact"], ["geonexus:contact@16"])
    True
    >>> admits(["geonexus:contact@15"], ["geonexus:contact@16"])
    False
    >>> admits(["ekthesis:audience"], ["geonexus:audience@1", "ekthesis:audience@2"])
    True
    """
    named = tuple(contracts)
    return any(
        entry == contract or ("@" not in entry and contract.partition("@")[0] == entry)
        for entry in entries
        for contract in named
    )
