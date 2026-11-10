# Handoff: order and grouping owned by collections

This handoff directs the agent that implements the decision of Geonexus on order and grouping in Anagraphe, then migrates its consumers. The decision is stated in `/Users/eresther/Documents/research/geonexus/docs/_decisions/collections-own-order-and-grouping.md`. That record is the single source of the design: this handoff carries only the order of work, the constraints and the state.

## Task state

Steps 1, 2, 3 and 6 are complete. The current release is `v0.2.2` (2026-11-10). Step 4 waits for the cutover gate. Step 5 comes next, since step 6 showed that the vault can replace its fork. That move needs the migration of the policy and of the content of the vault, and a decision on one point of Anagraphe.

1. **Done: record the change.** [ADR 0002](docs/adr/0002-collection-owned-order.md) states the model of a group and the retired constructions, with a pointer to the decision of Geonexus. The [index specification](docs/guide/index-specification.md) is the user reference of the model.
2. **Done: implement in Anagraphe.** Every check of the decision and every retired construction has a planted case in [the collection tests](tests/test_collections.py). The defects found by the independent review are fixed, each with a planted case, and so is the rule that a note declaring `superseded_by` holds a status listed under the vocabulary section `archived_statuses`. Two of these fixes enlarge the edits measured in step 4: a retired key is now reported under an index without a region of groups, and each consumer declaring `superseded_by` must declare `archived_statuses`. Measure the consumers again before migrating them.
3. **Done: release.** The researcher released `v0.1.0` on 2026-11-01, before migrating the consumers, so that Geonexus could pin it while refactoring. The releases `v0.2.0` and `v0.2.1` followed on 2026-11-04, and `v0.2.2` on 2026-11-10, each described by its section of the [changelog](CHANGELOG.md). The Release workflow tagged `v0.1.0` from the commit `7ba8c15` and created the [GitHub release](https://github.com/esther-poniatowski/anagraphe/releases/tag/v0.1.0), whose notes are the section 0.1.0 of the changelog. Before 1.0.0, a breaking change bumps the minor version (`major_on_zero = false`), and the changelog stays hand-written, the workflow running with `--no-changelog`. The release `v0.1.0` holds no distribution: the workflow failed after the tag, since the configuration staged `dist/*` files that no step built. The configuration now builds them with `build_command`, and the workflow attaches them with `semantic-release publish`, a step that the release `v0.2.0` showed missing; the wheel and the sdist of `v0.2.0` were attached by hand. The workflow attached those of `v0.2.1`. The Geonexus record linked by ADR 0002 is pushed, with `status: stable`.
4. **Migrate the two consumers to `v0.2.2`**, once the researcher admits the edits (see the cutover gate); on 2026-11-01 the researcher deferred both. A pin moved alone fails: the release stops on the configuration of each consumer with status 2. Therefore, each migration lands in one commit with its pin, from `@1db2c46` to `@v0.2.2` in `environment.yml`; the pip pin of Anagraphe brings its dependency Merismos. A check of a local clone of each `HEAD` at `v0.2.1`, on 2026-11-05, measured the edits.
   - **Both consumers**:
     - `anagraphe.yml` takes `schema_version: 2`, with its index keys under `indexes`. Each entry of `directories` becomes the pattern `name/`, each entry of `files` the pattern `/path`, and each entry of `basenames` the pattern `name`, all under `exclude.paths`;
     - the vocabulary drops its retired section `cites`;
     - `config/anagraphe/index-types/module.schema.yaml` replaces `x-default-mode: construction` by `registry`;
     - the adapter test calls `indexes write` instead of `write`, and moves the index key `sequence` that it writes into a group.
   - **Symmetry** (`/Users/eresther/Documents/projects/symmetry-lens-on-representations`): after the configuration, 5 `retired-key` remain, all `cites`. Two artifact indexes move it to `external`, and three notes drop it: two decision records and one audit.
   - **Mixture** (`/Users/eresther/Documents/projects/mixture-input-encoding`): the vocabulary declares `context_relations: [visualizes]`. After the configuration, 160 issues remain:
     - 27 members drop `group`, and their parent indexes declare `where` or `members` instead; placing these members also clears the 24 `unplaced-member`;
     - 5 indexes move their key `sequence` into a group of mode `sequence`. This move also clears the 4 `missing-sequence`. Two of these indexes, in `artifacts/mixture-input-encoding_abstract_2026-08_ccn/`, keep their order in a `loretex.yml` build manifest. Written as links, that order would be stated twice, so these two indexes wait for step 7;
     - 8 files outside `models/` drop `cites`, as the researcher decided on 2026-10-29, and `anagraphe.yml` declares a migration class for `models/*`, which holds the other 26;
     - 12 YAML files that hold no record are excluded by pattern: `_audits/notation-migration/*.yml`, the two `loretex.yml` of the CCN abstract and the `argument.yml` of the PINTS poster;
     - finally, `anagraphe indexes write` regenerates the 30 stale regions.
   - **Concurrent work**: on 2026-11-05, Mixture held 6 uncommitted changes of another session, among them its root `_index.md`, `TODO.md` and an untracked `HANDOFF.md`. Its migration waits for that work to land.
5. **Move the indexes of the vault to Anagraphe** under the task `index-collection-ownership` of the [Geonexus task list](/Users/eresther/Documents/research/geonexus/TODO.md). The vault already checks its references with Anagraphe: its `config/anagraphe.yml` declares the section `references`, its gate Elenchos runs `anagraphe refs check`, and its checker `check_links.py` is retired. The vault pins `v0.1.0`, at the commit `7ba8c15`. Its indexes are still generated by its fork, `utils/scripts/build_indexes.py` with `utils/scripts/index_entries/`. The move replaces that fork, declares the section `indexes` in `config/anagraphe.yml`, raises the pin to the current release, and migrates the notes and indexes counted by the implications of the decision. Two edits of the vault policy are already known. First, the vocabulary folder `specs/vocabulary/` declares the retired section `cites` in `relations.yml`; Anagraphe merges that folder into one vocabulary. Second, the index types `module` and `project` declare `x-default-mode: construction`. Once the move is done, the [designation handoff](/Users/eresther/Documents/research/geonexus/designation-handoff.md) declares the section `bindings` in the same file.
   **State on 2026-11-10.** The switch is prepared in `.agent-work/index-parity/` and waits for two conditions: the release `v0.3.0`, after the session writing the conventions of the command line commits its work in Anagraphe, and the commit of the uncommitted edits of another session to the indexes of the vault (`_index.md`, `conferences/_index.md`, `contacts/_index.md`, the PINTS conference). The researcher admitted installing the release into the environment `geonexus` at the switch. On a clone of the vault, `policy.py`, then `decisions.py`, then `migrate.py` leave `anagraphe indexes check` with no violation but two links into a submodule that the clone leaves empty, and every index renders as the fork renders it. The vault declares no `task_states`, since no note declares `blocked_by`. The researcher decided on 2026-11-10:
   - the Mind Matching registration note of CCN 2026 takes the role `networking`, with the `event` and the `day` of `networking_mind-matching.md`, so the group `networking` keeps its filter;
   - the catch-all group of `docs/_audits/architecture-autonomous-projects-shared-assets/_index.md` becomes a sequence, in the order that the fork renders.

   The switch lands in one commit of the vault, since its pre-commit hook runs the fork on every commit. Beyond the configuration and the content, the gate of the vault reports what the commit must also change:
   - `utils/schemas/index-types/part-base.schema.yaml` admits the keys of a group: `members`, `sequence`, `mode`, `where`, `sort`, `order`, `nest` and `show`;
   - the vocabulary declares `external` for the role `index`, and drops `group` and `cites` from `specs/vocabulary/keys.yml`;
   - `utils/scripts/build_metadata_options.py` no longer reads the retired `cites.relations`;
   - `config/elenchos.toml` runs `anagraphe indexes check` as a SARIF check, and `utils/hooks/pre-commit` drops the fork;
   - the fork `utils/scripts/build_indexes.py`, its package `index_entries/` and its tests retire, with the rules, the templates and the decision records that name `group`, `cites` or the fork;
   - `environment.yml` raises the pin of Anagraphe from `7ba8c15` to `v0.3.0`.

6. **Done: show that the index generator reproduces the fork of the vault.** The comparison ran on a shallow clone of the vault at `5a6cc0c`, in the ignored workspace `.agent-work/index-parity/` of this repository. Four scripts of that workspace serve step 5:
   - `policy.py` converts the policy of the clone, as step 5 states;
   - `finish_policy.py` writes `build/task-states.yml` with the reader of the fork;
   - `migrate.py` moves `group`, `sequence` and `cites` into the indexes;
   - `render.py` writes the rendering of Anagraphe, even when the check reports violations.

   After the conversion and the migration, 65 of the 67 indexes holding blocks render as the fork renders them, and 6 violations remain:
   - 2 `invalid-link` name files of project submodules. The clone leaves these submodules empty, and the fork reports the same targets;
   - the group `networking` of `conferences/2026-08_ccn/_index.md` united a filter and the notes declaring `group: networking`, whereas the Geonexus decision admits at most one of `members` and `where` in a group. The vault lists every member of that group, or gives the registration note the role `networking`;
   - `docs/_audits/architecture-autonomous-projects-shared-assets/_index.md` swaps two entries, since the retired mode `construction` ordered them by citation; the vault declares a sequence if that order matters.

   Two defects of Anagraphe were found and repaired. First, an empty group was reported for its sort key (`fb60bb4`). Second, the configuration guide stated one vocabulary file, whereas the code merges a folder (`db7fb88`). The fork lists a YAML file only when it holds a block `metadata`. As the researcher decided on 2026-11-10, a rule of `indexes.members` may name such keys under `keys`, so the vault declares `{types: [yml, yaml], keys: [metadata]}`; on the clone, this rule leaves out `environment.yml`, `obsidian-plugins.yml` and `utils/schemas/constraints.schema.yaml` without any exclusion, with the same findings.
7. **Then: read the build manifests of a consumer.** ADR 0001 leaves the derivation of a sequence to the consumer, but a consumer running the command line can supply a sequence only through `indexes.sequences`, written in `anagraphe.yml`. When a consumer derives a sequence from a build manifest, such as the order of the inclusions of a Loretex document, that order is stated twice. The step lets `indexes.sequences` name a file generated by the consumer, as `indexes.task_states` does, so that Mixture keeps `loretex.yml` as the single source of its order.
8. **Blocked: further work assigned by Geonexus.** The task `record-state-provider` of Geonexus waits for `record-resolver`, `record-registry` and `record-reference-schema`, none done. The conda package of Anagraphe cannot build while its recipe holds the Git pin of Merismos, so it waits for Merismos on the conda channel.

## Active constraints

- **Repository boundary.** Following [ADR 0001](docs/adr/0001-repository-boundary.md), the core holds no vocabulary, path or task syntax of a consumer, and each consumer supplies its policy.
- **No silent ordering.** A source of order that the mode of its group ignores is reported, never dropped.
- **A plugin will edit the same specification.** Anagraphe will also provide an Obsidian plugin that renders indexes and lets the author manipulate their groups, membership, order and nesting. The specification of a collection therefore stays in the frontmatter of its index, in a form that the plugin can read and write, and the command line and the plugin share one core.
- **Consumers first.** Run `anagraphe check` in every consumer at the target release before moving its pin, and confirm that no `x-default-mode: construction` remains.
- **Cutover gate.** Before editing the configuration of the Mixture or Symmetry repository, confirm with the researcher whether such an edit is admitted before the cutover of that repository.
- **No order strategy in Anagraphe.** The order strategies of expositions belong to Ekthesis, under the task `exposition-order-strategy` of the [Geonexus task list](/Users/eresther/Documents/research/geonexus/TODO.md), and are not part of this work.
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
