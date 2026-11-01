# Index Specification

The frontmatter of an index specifies its collection: how the members divide into groups, and how
each group orders, nests and displays its members. The generator renders the groups between the
markers of the region of groups, and reads no group or order from the members themselves.

This page assumes two prerequisites: a repository configured by the [configuration
guide](configuration.md), and an index holding the region of groups in its body:

```markdown
<!-- index groups -->
<!-- /index -->
```

Every link of the frontmatter names its file from the repository root.

## Declare the groups

The key `groups` lists the groups in their rendering order. The index below declares three groups,
one for each step that assigns the members:

```yaml
groups:
  - id: talks
    heading: Talks
    where: {kind: [keynote, talk]}
    sort: [kind, date]
    show: [purpose]
  - id: parts
    heading: Parts
    mode: sequence
    sequence:
      - "[Motivation](module/motivation.md)"
      - "[Model](module/model.md)"
  - id: "*"
    heading: Other notes
    show: [purpose, status]
```

Each group admits the keys below, and only its identifier `id` is required:

| Key | Value |
| --- | --- |
| `id` | the identifier of the group; `*` names the catch-all group |
| `heading` | the heading rendered above the group; a group without heading stands under the heading of the group before it, and must share its mode |
| `description` | one sentence rendered under the heading |
| `where` | a mapping from a key of the members to one value or a list of values; a key holding a list matches when the list holds an admitted value |
| `members` | a list of links to members |
| `mode` | `registry` or `sequence`; the default comes from the type of the index |
| `sort` | one sort key, or a list of sort keys |
| `order` | the list of values of the first sort key, in their order |
| `sequence` | a list of links to members, in their order |
| `nest` | the key of the members naming the parent of each member, as a dotted path |
| `show` | the keys displayed after each entry: an entry field (e.g. `purpose`, `status`) or any key of the members |

## Assign the members

The members of an index are the files of its folder whose type the configuration admits under
`indexes.members`, and the indexes of its subfolders. By default, an index lists its Markdown
notes and its YAML records, as the [configuration guide](configuration.md) states. Each member of
the folder belongs to one group. The generator assigns the members in three
steps, and an earlier step prevails over a later one:

1. A group holds the files listed in its `members`. A group whose only membership key is
   `sequence` holds the files listed in that sequence, whatever its mode. A file named by two
   groups belongs to the first.
2. A member held by no list belongs to the first group whose filter `where` selects it.
3. Any other member belongs to the catch-all group `*`, if the index declares it. Otherwise,
   the member is reported.

A filter suits a grouping by a property of the members: a new member joins its group without any
edit of the index. An explicit list suits a grouping that follows no property.

## Order a group

The mode of a group selects its source of order. A **registry** sorts its members by the keys
under `sort`:

- `title`, the default, sorts by the first alias of each member, else by its file stem, or by
  the name of its folder for a child index;
- `file` sorts by the path;
- `date` sorts by the key `date`, else by the ISO date opening the file name, and the members
  without a date follow;
- any other key sorts by the value of that key, and the members without a value follow. The
  numbers, as YAML reads them, come first and compare by value. The other values follow and
  compare as text, so `day: 2` precedes `day: 10`, and both precede `day: late`. A quoted number,
  such as `day: "10"`, is text.

Each later key of `sort` breaks the ties of the former. The title, then the path, break the
remaining ties.

A categorical key sorts in the order of its declared values. The vocabulary declares those values
under `key_values`, as the [configuration guide](configuration.md) shows. The key `order` of a
group overrides that order for the first sort key:

```yaml
groups:
  - id: "*"
    sort: kind
    order: [talk, keynote]
```

A value omitted by the `order` does not block the index. The members holding it follow the ranked
values, sorted as any other key sorts. The check command reports each of them as a warning.
A value outside the declared values of its key remains a violation.

A **sequence** follows the build manifest of its folder when the configuration declares a
manifest for that folder, and the `sequence` of the group otherwise. The members absent from that
list follow it, in the order of the sort keys, and each of them is reported as a warning.

## Nest the members

The key `nest` places each member beneath its parent within the group. Its value names a key of
the members, whose value designates the parent: a file stem, an `id`, or a link. When that key
holds a list, its first value naming a member of the group designates the parent. The entries of
the children are indented beneath the entry of their parent. Two kinds of member stand at the
first level:

- a member whose key names no parent;
- a member whose parent lies outside the group.

A cycle of parents, such as `a` naming `b` and `b` naming `a`, leaves some members without a
chain of parents to the first level. These members belong to the cycle or stand beneath it. The
check command reports each of them as `nest-cycle`. The generator takes them in the order of
the group: each member not yet placed stands at the first level, and its descendants nest beneath
it. Therefore, the first member of a cycle, in the order of the group, stands at the first level,
and the other members of the cycle nest beneath it.

## Declare dependencies and distinctions

Three further keys complete the specification of a collection:

- The index key `external` lists the dependencies of the index outside its folder. Each entry
  states the file under `target` and its use under `for`.
- The index key `context_relations` states a distinction between two members, as a mapping
  `{source, relation, target, for}`. The vocabulary declares the admitted relations.
- The member key `superseded_by` links an archived note to the note replacing it. A note declaring
  it must hold a status declared under `archived_statuses`, as the [configuration
  guide](configuration.md) shows. This check covers every member of an index holding the region
  of groups, including a member held by no group.

The entries below declare one dependency and one distinction:

```yaml
external:
  - target: "[Kernel methods](foundations/kernel-methods.md)"
    for: the kernel used by the model of this module
context_relations:
  - source: "[Rate model](module/rate-model.md)"
    relation: contrasts
    target: "[Spiking model](module/spiking-model.md)"
    for: the time scale of the response
```

## List files that are not notes

The index key `files` lists files of the folder that cannot declare their own entry fields, such
as a PDF or a figure. Each entry declares the `file`, relative to the folder, and its `title`, and
may declare a `purpose` and a `group`. A file declared under `files` takes this entry, and is not
listed a second time as a member. An entry without `group` belongs to the group `*`. The entries of a
group follow its members, in the order of their titles:

```yaml
files:
  - file: results/summary.csv
    title: Summary of the results
    purpose: records the largest errors of each run
    group: data
```

## Read the reported issues

The check command reports each issue of a specification as a violation, unless the table marks it
as a warning. The command reports a retired key under every index, and the other issues only
under an index holding the region of groups:

| Issue | Cause |
| --- | --- |
| `invalid-link` | a link of `members`, `sequence`, `external` or `superseded_by` names no file |
| `invalid-link` | a link of `members`, or of a sequence holding the members of its group, names a file absent from the members of the index |
| `invalid-link` | the value of `superseded_by` is not a link |
| `duplicate-member` | two groups, or one group twice, name the same file |
| `unknown-filter-key` | a filter names a key absent from every member |
| `undeclared-value` | a value of a filter or of an `order` lies outside the declared values of its key |
| `undeclared-value` | a member holds, under a categorical sort key of its group, a value outside the declared values of that key |
| `unranked-value` | a member holds, under the first sort key of its group, a value omitted by the `order` of the group but admitted by the vocabulary (warning) |
| `unarchived-superseded` | a note declares `superseded_by`, and its status is absent or not declared under `archived_statuses` |
| `ignored-order` | a registry group declares a `sequence` |
| `ignored-order` | the first sort key of a group declaring `order` is `title`, `file` or `date` |
| `ignored-order` | a build manifest overrides the `sequence` of a group; the message asks to move its links under `members` when they define the members, else to remove it |
| `ignored-order` | a build manifest names a member of a registry group |
| `ignored-order` | a `sequence` names a file outside its group |
| `missing-sequence` | a sequence group lacks both a `sequence` and a build manifest |
| `nest-cycle` | a cycle of the parents named through `nest` separates the member from the first level |
| `invalid-external` | `external` names a member of the index |
| `invalid-context-relation` | a relation of `context_relations` is not declared by the vocabulary, or names a file absent from the members |
| `malformed-groups` | a key of a slot is malformed (e.g. an unknown key, a duplicate id, both `members` and `where`) |
| `malformed-groups` | no member of a group holds one of its sort keys |
| `malformed-groups` | a group declares the retired key `strategy` or the retired mode `construction`, or names a retired member key (`group`, `cites`) in `show` |
| `mixed-modes` | two groups of different modes stand under one heading |
| `unplaced-member` | a member declaring a `purpose` belongs to no group |
| `unmigrated-member` | a member lacking a `purpose` belongs to no group (warning) |
| `unsequenced-member` | a sequence does not list a member of its group (warning) |
| `retired-key` | a member or the index declares a retired key (`group`, `cites`, the index keys `sequence` and `goal`), and the message names its replacement |
| `migration-key` | a retired key lies inside a migration class declared by the configuration (warning) |

A retired construction of an index-type schema, such as `x-default-mode: construction`, or of the
vocabulary, such as its section `cites`, stops the command with a configuration error. The
[ADR 0002](../adr/0002-collection-owned-order.md) lists each retired construction with its
replacement.
