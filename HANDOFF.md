# Handoff: order and grouping owned by collections

This handoff directs the agent that implements the decision of Geonexus on order and grouping in Anagraphe, then migrates its consumers. The decision is stated in `/Users/eresther/Documents/research/geonexus/docs/_decisions/collections-own-order-and-grouping.md`. That record is the single source of the design: this handoff carries only the order of work, the constraints and the state.

## Task state

Steps 1, 2 and 3 are complete: the researcher released `v0.1.0` on 2026-11-01, ahead of the consumer migration, so that the refactoring of Geonexus can pin it. Step 4 waits for the cutover gate, and step 5 follows the pin of the release in Geonexus.

1. **Done: record the change.** [ADR 0002](docs/adr/0002-collection-owned-order.md) states the model of a group and the retired constructions, with a pointer to the decision of Geonexus. The [index specification](docs/guide/index-specification.md) is the user reference of the model.
2. **Done: implement in Anagraphe.** Every check of the decision and every retired construction has a planted case in [the collection tests](tests/test_collections.py). The defects found by the independent review are fixed, each with a planted case, and so is the rule that a note declaring `superseded_by` holds a status listed under the vocabulary section `archived_statuses`. Two of these fixes enlarge the edits measured in step 4: a retired key is now reported under an index without a region of groups, and each consumer declaring `superseded_by` must declare `archived_statuses`. Measure the consumers again before migrating them.
3. **Done: release `v0.1.0`.** The Release workflow tagged `v0.1.0` from the commit `7ba8c15` and created the [GitHub release](https://github.com/esther-poniatowski/anagraphe/releases/tag/v0.1.0), whose notes are the section 0.1.0 of the [changelog](CHANGELOG.md). Before 1.0.0, a breaking change bumps the minor version (`major_on_zero = false`), and the changelog stays hand-written, the workflow running with `--no-changelog`. The release holds no distribution: the workflow failed after the tag, since the configuration staged `dist/*` files that no step built. The configuration now builds them with `build_command`, so the next release attaches its wheel and its sdist. One point remains:
   - ADR 0002 links the Geonexus record on GitHub, and the Geonexus commit adding that record is not pushed. The record also still reads `status: wip`, although the researcher accepted it on 2026-10-29.
4. **Migrate the two consumers to `v0.1.0`**, once the researcher admits the edits (see the cutover gate). Each migration covers the policy of the repository (`anagraphe.yml`, the index-type schemas, the vocabulary), its indexes, and its pin of Anagraphe in `environment.yml`, from the commit `1db2c46` to the tag `v0.1.0`. The release also carries the layout of [ADR 0003](docs/adr/0003-pointers-across-moves.md), so each consumer moves its `anagraphe.yml` to `schema_version: 2`, with its index keys under the section `indexes`, and its adapter test replaces the command `write` by `indexes write`. Since an index now lists YAML records by default, each consumer also excludes its YAML files that hold no record, such as `anagraphe.yml` and `environment.yml` (19 files in Mixture, 9 in Symmetry). A check of a scratch copy at the new version, after the configuration migration, measured the remaining edits:
   - **Symmetry** (`/Users/eresther/Documents/projects/symmetry-lens-on-representations`): two artifact indexes move their `cites` to `external`, and two decision records drop `cites`. Its root index was already stale at the pinned version.
   - **Mixture** (`/Users/eresther/Documents/projects/mixture-input-encoding`):
     - 25 members drop `group`, and their 23 parent indexes declare `where` or `members` instead;
     - 3 indexes move their `sequence` into a group of mode `sequence`, written as links. This move restores the order of `settings/_index.md`;
     - 7 files outside `models/` drop `cites`, as the researcher decided on 2026-10-29, and `anagraphe.yml` declares a migration class for `models/*`;
     - the vocabulary declares `context_relations: [visualizes]`;
     - the adapter test `tests/test_mixture_anagraphe_adapter.py` writes an index key `sequence`, and must move it into a group.
5. **Move the vault to Anagraphe** under the task `index-collection-ownership` of the [Geonexus task list](/Users/eresther/Documents/research/geonexus/TODO.md). The move also retires the vault checker `utils/scripts/check_links.py`, as the [handoff on pointers](HANDOFF_references.md) states. The decision orders this move after the breaking release, and its prerequisite `index-tool-adapters` is already complete. The vault replaces its fork `utils/scripts/index_entries/` by Anagraphe, adds its `anagraphe.yml`, and migrates the notes and indexes counted by the implications of the decision. Its closed value sets already sit under `key_values`, the section read by Anagraphe.

## Active constraints

- **Repository boundary.** Following [ADR 0001](docs/adr/0001-repository-boundary.md), the core holds no vocabulary, path or task syntax of a consumer, and each consumer supplies its policy.
- **No silent ordering.** A source of order that the mode of its group ignores is reported, never dropped.
- **A plugin will edit the same specification.** Anagraphe will also provide an Obsidian plugin that renders indexes and lets the author manipulate their groups, membership, order and nesting. The specification of a collection therefore stays in the frontmatter of its index, in a form that the plugin can read and write, and the command line and the plugin share one core.
- **Consumers first.** Run `anagraphe check` in every consumer at `v0.1.0` before moving its pin, and confirm that no `x-default-mode: construction` remains.
- **Cutover gate.** Before editing the configuration of the Mixture or Symmetry repository, confirm with the researcher whether such an edit is admitted before the cutover of that repository.
- **No change to Gnomon.** The order strategies of expositions belong to Gnomon, under its task `exposition-family`, and are not part of this work.
- **Commits.** Commit on the current branch, and only when the researcher asks.
- **Checks.** Run three commands, each on the changed files:
  - the tests: `conda run -n anagraphe python -m pytest`;
  - the doctests: `conda run -n anagraphe python -m pytest --doctest-modules src/anagraphe`;
  - the prose linter: `conda run -n hermeneia hermeneia lint --changed --format text <path>`.
- **Dirty consumer tree.** The Mixture repository holds uncommitted work of another task, and its baseline check at the pinned version already reports 135 violations `index-location`. A migration must touch only the files required by the migration.

## Open questions

- Do decision records need an untyped list of the decisions on which they rest? No check consumes such a list today, so the decision defers the question.

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
- 2026-10-29: the researcher accepted the decision record, admitted no consumer edit in the implementation session, and chose that the `sequence` of a group without `members` or `where` defines its members.
