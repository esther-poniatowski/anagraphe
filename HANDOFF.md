# Handoff: order and grouping owned by collections

This handoff directs the agent that implements the decision of Geonexus on order and grouping in Anagraphe, then migrates its consumers. The decision is stated in `/Users/eresther/Documents/research/geonexus/docs/_decisions/collections-own-order-and-grouping.md`. That record is the single source of the design: this handoff carries only the order of work, the constraints and the state.

## Task state

Nothing is implemented. The decision record is in status `wip`, and its text awaits the acceptance of the researcher. Start only once the record is accepted.

The work proceeds in this order:

1. **Record the change in Anagraphe.** Write the ADR `docs/adr/0002-collection-owned-order.md`, stating the retirement and the new model of a group, with a pointer to the decision of Geonexus.
2. **Implement in Anagraphe**, following the tasks of the [task list](TODO.md):
   - membership by a filter `where` or by an explicit list `members` of links, the list prevailing, and the retirement of the member key `group`;
   - the modes `registry` and `sequence` only. A registry sorts by a key and by secondary keys, and a categorical key sorts in the order of its declared values, unless an `order` overrides it. A sequence holds its own list of links per group, and a build manifest prevails;
   - the retirement of `construction`, of the strategy tokens, order rules, grades and contributing ends, of the goal test, of the check of mirrored citations, and of the parsing of typed citations;
   - the resolution of the index key `external`, of the optional note key `superseded_by`, and the table `context_relations` kept as it stands;
   - every check listed by the decision, each with a planted case among the tests.
3. **Release a breaking version.** A leftover `construction`, a member key `group`, or a key `cites` outside a declared migration class fails with a message naming its replacement.
4. **Migrate the two consumers before the release:** `/Users/eresther/Documents/projects/mixture-input-encoding` and `/Users/eresther/Documents/projects/symmetry-lens-on-representations`. Each migration covers:
   - its `anagraphe.yml`;
   - its index-type schemas, whose type `module` defaults to `construction`;
   - its vocabulary;
   - its indexes.

   In the Mixture repository, its research notes keep their typed citations as a non-blocking migration class, declared in its own configuration. Its index `settings/_index.md` declares a `sequence` that the default mode ignores; the migration must restore that order.
5. **Move the vault to Anagraphe** under the task `index-collection-ownership` of the [Geonexus task list](/Users/eresther/Documents/research/geonexus/TODO.md). The vault replaces its fork `utils/scripts/index_entries/` by Anagraphe, adds its `anagraphe.yml`, and migrates its notes and indexes, as the implications of the decision count them.

## Active constraints

- **Repository boundary.** Following [ADR 0001](docs/adr/0001-repository-boundary.md), the core holds no vocabulary, path or task syntax of a consumer, and each consumer supplies its policy.
- **No silent ordering.** A source of order that the mode of its group ignores is reported, never dropped.
- **A plugin will edit the same specification.** Anagraphe will also provide an Obsidian plugin that renders indexes and lets the author manipulate their groups, membership, order and nesting. The specification of a collection therefore stays in the frontmatter of its index, in a form that the plugin can read and write, and the command line and the plugin share one core.
- **Consumers first.** Run `anagraphe check` in every consumer at the new version before the release, and confirm that no `x-default-mode: construction` remains.
- **Cutover gate.** Before editing the configuration of the Mixture or Symmetry repository, confirm with the researcher whether such an edit is admitted before the cutover of that repository.
- **No change to Gnomon.** The order strategies of expositions belong to Gnomon, under its task `exposition-family`, and are not part of this work.
- **Commits.** Commit on the current branch, and only when the researcher asks.
- **Checks.** Run the tests with `conda run -n anagraphe python -m pytest`, and the prose linter on every changed document with `conda run -n hermeneia hermeneia lint --format text <path>`.

## Open questions

- Do decision records need an untyped list of the decisions on which they rest? No check consumes such a list today, so the decision defers the question.
- Is the configuration of indexes an edit admitted before the cutover of a project repository?

## Provenance

- The design follows an adversarial review of an earlier proposal. That proposal placed order in the notes through the keys `parent` and `follows`. The review found that `nest` already provides nesting, that `follows` costs more edits than a sequence held by the index, and that the vault runs a fork of the generator rather than Anagraphe.
- The counts of the decision were measured on 2026-10-29:
  - 218 notes declare `group`;
  - 53 files outside the Mixture project declare `cites`;
  - 9 indexes declare `sequence`;
  - 10 indexes have the type `module` or `project`.

## Decision log

- 2026-10-29: the researcher assigned order, nesting and grouping to the index of a collection, and the intrinsic properties to the notes.
- 2026-10-29: the researcher retired the dependency key, kept the index key `external`, and reserved `superseded_by` for archived notes.
- 2026-10-29: the researcher assigned the implementation to Anagraphe, in a versioned release, before the vault replaces its fork.
