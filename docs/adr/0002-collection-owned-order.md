# ADR 0002: Collection-owned order

**Status**: Accepted

---

## Problem Statement

Before this decision, Anagraphe read three facts of a collection outside the groups declared by
its index:

- **the group of a member**: each member names its group in its key `group`;
- **the order of a construction**: a group of mode `construction` derives its order from the typed
  citations of its members. The attributes of their relations (e.g. grades, order rules) and the
  strategy tokens of the group fix that order;
- **the sequence of an index**: an index states one `sequence` for all its groups, and the default
  mode of its type can ignore that sequence without reporting it.

The [Geonexus decision on collection-owned order](https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/collections-own-order-and-grouping.md)
assigns the order, the nesting and the grouping of the members to the frontmatter of their index.
That record compares the possible locations of the three facts. The present record fixes two
points: how Anagraphe reads these facts from the index, and how one release retires the former
constructions.

**Questions to be addressed**:

1. Which keys of a group specify its membership and its order, and which key prevails over
   another?
2. How does a release retire the former constructions without changing an order silently?

---

## Decision Drivers

- **Single specification**: the frontmatter of an index is the only input that fixes the
  membership, the order and the nesting of its groups. The Obsidian plugin writes the same keys.
- **No silent ordering**: every source of order ignored by the mode of its group is reported.
- **Safe migration**: a repository learns each edit owed by its files from the report of
  `anagraphe check`.
- **Repository boundary**: following [ADR 0001](0001-repository-boundary.md), the core names no
  vocabulary, path or migration of a consumer.

---

## Considered Options

1. **Compatibility layer**
   The new keys of a group are added, and the former constructions keep working beside them.
   - The member key `group`, the mode `construction` and the index key `sequence` are still read.
   - Each former construction emits a deprecation warning.
   - The core still parses typed citations.

2. **Breaking release**
   The new keys of a group replace the former constructions in one versioned release.
   - Each former construction fails with a message naming the construction that replaces it.
   - A repository may tolerate the retired key `cites` in a declared migration class, whose
     instances are reported as warnings.
   - The core no longer parses typed citations.

---

## Analysis of Options

### Individual Assessment

1. **Compatibility layer**
   - Pros:
     - Safe migration: a repository can upgrade before editing any file.
   - Cons:
     - Single specification: a group could take its members from the notes and from the index at
       once, so two sources of membership coexist until every consumer migrates.
     - No silent ordering: an index `sequence` and the default mode `construction` of its type
       would keep conflicting without a report, as in the index of `settings/` in the Mixture
       repository.
     - Additional disadvantage: the vocabulary of relations, retired by the decision, stays in the
       core.

2. **Breaking release**
   - Pros:
     - Single specification: only the keys of the index are read.
     - Safe migration: each failure names its replacement, and the consumers migrate before the
       release.
     - Repository boundary: each consumer declares its own migration classes in `anagraphe.yml`.
   - Cons:
     - A repository cannot upgrade before it edits its configuration, its schemas, its vocabulary
       and its indexes.

### Summary: Comparison by Criteria

- **Single specification**
  - **Compatibility layer**: LOW (two sources of membership)
  - **Breaking release**: HIGH (index frontmatter only)
- **No silent ordering**
  - **Compatibility layer**: LOW (mixed sources of order)
  - **Breaking release**: HIGH (one source of order per group, report `ignored-order`)
- **Safe migration**
  - **Compatibility layer**: HIGH (deprecation warnings)
  - **Breaking release**: MEDIUM (failures naming replacements, migration classes)
- **Repository boundary**
  - **Compatibility layer**: MEDIUM (relation vocabulary kept in the core)
  - **Breaking release**: HIGH (migration classes owned by the consumer)

---

## Conclusions

### Decision

**Chosen option**: Breaking release.

**Justification**: A compatibility layer would keep two sources of membership and two sources of
order until every consumer migrates. The decision exists to remove that duplication. In a breaking
release, each failure names the edit owed.

#### Choices beyond the Geonexus record

The [index specification](../guide/index-specification.md) is the reference of the keys of a group.
The rules below are choices of Anagraphe. The Geonexus record, amended on 2026-10-29 after a review
of this implementation, adopts the first four, and the last four stay choices of Anagraphe:

1. A group whose only membership key is `sequence` takes its members from that sequence, so that
   one list fixes both the members and their order.
2. The `order` of a group overrides the declared values of its first sort key. A value absent
   from `order` is a warning and sorts after the ranked values.
3. The declared values come from the vocabulary section `key_values` alone. Reading them from the
   schema of a member is deferred.
4. A member matching no group belongs to the group `*` only when the index declares that group.
   Otherwise, the member is reported, since an undeclared group has no place in the rendering.
5. Each entry of `external` is a mapping `{target, for}`.
6. In every mode, the title of a member breaks the ties left by the sort keys, and its path breaks
   the ties between equal titles.
7. A key of the members compares its numbers, as YAML reads them, by value. Its other values
   follow the numbers and compare as text. Therefore, one rule orders a key holding values of
   mixed types.
8. The statuses of an archived note are declared in the vocabulary section `archived_statuses`,
   beside the closed value sets of `key_values`. A status is a value of the vocabulary, so the
   vocabulary can check that each archived status is a declared status.

#### Retired constructions

| Construction | Replacement |
| --- | --- |
| member key `group` | the `where` or the `members` of a group |
| key `cites` of a note | the links of its body |
| key `cites` of an index | `external` for outside files, `context_relations` for distinctions |
| index key `sequence` | the `sequence` of a group |
| index key `goal`, warning `off-goal` | the expositions of Gnomon |
| group key `strategy` | a sort key or a sequence |
| mode `construction`, in a group or in `x-default-mode` | the modes `registry` and `sequence` |
| vocabulary section `cites` | the vocabulary section `context_relations` |

### Final Answers

1. The explicit list of a group prevails over every filter, and a file named by two groups
   belongs to the first. Among filters, the first matching group wins. In a sequence group, the
   build manifest of the folder prevails over the `sequence` of the group.
2. Each retired construction fails with a message naming its replacement. A retired key of a
   member or of an index is a violation, and a retired construction of a type schema or of the
   vocabulary stops the command. A retired key is reported under every index, whether or not it
   holds its region of groups, so a repository learns each edit owed before its indexes migrate.
   Each source of order ignored by its group is reported as `ignored-order`. Only the key `cites`
   admits a migration class, whose instances are reported as warnings.

---

## Implications

- **Modules**: the module `retired` holds every retired construction and its replacement, the
  module `membership` assigns the members, and the module `order` holds the collation of a
  group. The typed citations, the goal test and the ordering by constraints leave the core.
- **Checks**: each check listed by the decision of Geonexus reports a violation, under the issue
  kinds tabulated by the [index specification](../guide/index-specification.md).
- **Consumers**: each consuming repository migrates its `anagraphe.yml`, its index-type schemas,
  its vocabulary and its indexes before it pins the release. The research notes of the Mixture
  repository keep their typed citations in a migration class.
- **Plugin**: the Obsidian plugin will read and write the same keys of `groups`.

---

## See Also

### Related Decisions

- [ADR 0001](0001-repository-boundary.md): Relates to. The migration classes and the categorical
  values are supplied by each consumer, as the repository boundary requires.

### References and Resources

- [Geonexus decision on collection-owned order](https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/collections-own-order-and-grouping.md)
