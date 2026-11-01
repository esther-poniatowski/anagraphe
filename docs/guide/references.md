# Reference specification

Anagraphe keeps the pointers between the files of a repository valid. The command
`anagraphe refs check` reports each pointer that names no file or anchor, or breaks a convention,
and the command `anagraphe move` moves a file or a folder while rewriting every pointer to it. This
page assumes an installed Anagraphe and an `anagraphe.yml` at `schema_version: 2`, as the
[configuration guide](configuration.md) describes.

## Kinds of pointer

A pointer is written in one **syntax**, and a syntax yields candidates that may or may not name a
file. A candidate naming a file is a pointer. A candidate naming no file is reported as `broken`
only where its syntax is **strict**, since a code span or a string of code may hold an example, a
command or no path at all. Four syntaxes are built in:

| Syntax | Notation | Files read | Omitted suffixes | Strict by default |
| --- | --- | --- | --- | --- |
| `markdown` | `[text](notes/a.md#^claim)`, embeds included | `md` | none | yes |
| `wikilink` | `[[notes/a#^claim\|text]]`, embeds included | `md` | `.md` | yes |
| `code` | a path written alone in a code span: `` `notes/a.md` `` | `md` | none | no |
| `latex` | `\input`, `\include`, `\subfile`, `\includegraphics`, `\includepdf`, `\lstinputlisting`, `\addbibresource` | `tex`, `sty`, `cls` | `.tex`, `.pdf`, `.png`, `.jpg`, `.jpeg`, `.eps`, `.svg`, `.bib` | yes |

The Markdown syntaxes skip code blocks, and a link inside a code span or a math span is not read.
The syntax `latex` skips comments. Besides the declared syntaxes, a move rewrites every **bare path**
of every text file, such as a path in a Python string or a configuration value, when the path
resolves to a moved file. A token counts as a path when it holds a slash or names a file with a
suffix, so a bare word is never rewritten.

## Declare the section

The section below admits three URL schemes, reads the Markdown links of YAML files as well, and
declares a syntax of keys for the `source` values of the glossary records:

```yaml
schema_version: 2
references:
  exclude:
    paths: [templates/]
  schemes: [https, mailto, zotero]
  syntaxes:
    markdown:
      when: {types: [md, yml]}
    glossary:
      when: {paths: ["/specs/glossary/"]}
      keys: [source]
```

Each key of the section is optional. A section written as `references: {}` reads the built-in
syntaxes under the default conventions.

| Key | Value | Default |
| --- | --- | --- |
| `exclude` | the files left unread, by pattern and by metadata, after the shared `exclude`, as the [configuration guide](configuration.md) states | none |
| `schemes` | the URL schemes resolved outside the repository, as a list or as a mapping to glosses | `https`, `http`, `mailto` |
| `fragments` | `block` admits only a block anchor `#^name`; `any` admits every fragment | `block` |
| `syntaxes` | redefinitions of the built-in syntaxes, and further syntaxes by name | the built-in syntaxes |
| `conventions` | the rules fixing the syntaxes, the path styles and the strictness admitted, by location, type, metadata, region or syntax | see below |
| `ignore` | the kinds of issue left unreported | none |

## Syntaxes

A built-in syntax is redefined under its name, with the keys `when`, `omit`, `unresolved` and
`enabled` of the table below. A further syntax is declared under a new name, either by a pattern
or by keys:

```yaml
references:
  syntaxes:
    latex:
      omit: [.tex, .pdf, .png]
    python:
      when: {types: [py]}
      pattern: "[\"'](?P<target>[\\w./-]+/[\\w.-]+)[\"']"
      comment: "#"
      unresolved: ignore
    sources:
      when: {types: [json, toml, yml]}
      keys: [source, inputs]
      form: path
```

| Key | Value | Default |
| --- | --- | --- |
| `when` | the files read, as a condition on `paths`, `types` and `where`, stated in the [configuration guide](configuration.md) | every file |
| `pattern` | a regular expression capturing the target in a group named `target` | one of `pattern` and `keys` |
| `keys` | the keys of a YAML, JSON or TOML document whose values are pointers, at any depth | one of `pattern` and `keys` |
| `form` | for `keys`: `path` for a bare path, `link` for one Markdown link or wikilink | `path` |
| `comment` | for `pattern`: a marker opening a comment to the end of its line, whose targets are not read | none |
| `omit` | the suffixes that a target may omit | none |
| `unresolved` | `report` or `ignore` a target naming no file | `report` |
| `enabled` | whether the syntax is read | `true` |

A value of a key may be one string or a list of strings, and a bare path is read as written,
without percent-decoding. When a key holds values of several kinds across the repository, only the
files holding paths are named under `when`. For example, a `source` key may hold a path in the
glossary records and the name of a website in an asset registry.

## Conventions

A convention fixes how the pointers of a file are written: in which **syntaxes**, in which **path
styles**, and which syntaxes are **strict**. The path styles are the starting points of a path:

| Style | Starting point | Example from `notes/sub/a.md` to `docs/b.md` |
| --- | --- | --- |
| `relative` | the folder of the holding file | `../../docs/b.md` |
| `root` | the repository root | `docs/b.md` |
| `absolute` | the repository root, after a slash | `/docs/b.md` |
| `shortest` | the shortest end of the path naming one file, as Obsidian writes wikilinks | `b` |
| `{base: folder}` | a declared folder, such as the root of a project inside a vault | `b.md`, under `{base: docs}` |

The section `conventions` lists rules. Each rule holds an optional condition under `when`, and sets
`format`, `path` or `strict`, each as one value or as a list of admitted values:

```yaml
references:
  conventions:
    - format: [markdown, code]
      path: relative
    - when: {regions: [metadata]}
      path: root
    - when: {paths: ["/journal/"]}
      format: wikilink
      path: shortest
    - when: {paths: ["/docs/"]}
      strict: [markdown, wikilink, code]
    - when: {syntaxes: [latex]}
      path: [relative, {base: manuscript}]
```

A condition admits five parts, and a rule applies to a pointer meeting every part stated by the
rule:

| Part | Value |
| --- | --- |
| `paths` | patterns in the syntax of `.gitignore`, matched against the path of the holding file |
| `types` | file suffixes, such as `md` or `tex` |
| `where` | metadata filters of the form of the `where` of a group; one matching filter suffices |
| `regions` | `metadata`, the span holding the fields read by the metadata source of the file, or `content` |
| `syntaxes` | the syntaxes of the pointers governed by the rule |

The rules cascade. The built-in rules come first:

- every syntax is admitted, and each syntax keeps its default strictness;
- a pointer of the content is `relative`, and a pointer of the metadata is `root`;
- a backticked path admits both `relative` and `root`, as backticked paths are customarily written.

Each declared rule follows in its order, and a matching rule overrides only the keys set by that
rule. A rule setting a format alone therefore keeps the path style of an earlier rule. The keys of
an index that name files, such as `members` and `external`, are links in the metadata of the index,
and are checked as such.

## Move a file or a folder

The command `anagraphe move OLD NEW` moves one file or one folder, and rewrites every pointer to it
in the files left unexcluded by the section. A rewritten pointer keeps its syntax, its path style,
its fragment, a suffix omitted by its syntax and, in a Markdown link, its percent-encoding. A
wikilink written by its shortest end takes the shortest end naming the moved file alone. A
file-relative pointer held by a moved file is recomputed from its new folder. When the
configuration declares the section `indexes`, the move also updates the indexes, as the [usage
guide](usage.md) describes. The option `--dry-run` prints every planned rename and edit, and
changes no file.

## Read the reported issues

Each issue is printed as `path:line: kind: target: detail`. For each kind of issue, the cause and
the repair are as follows:

| Kind | Cause | Repair |
| --- | --- | --- |
| `broken` | the path of a strict syntax names no file, from the folder of the file nor from the root | correct the path, or restore the file |
| `ambiguous-link` | the end of a path names several files, and no other style names one | write a longer end, or a path from the root |
| `link-format` | the pointer is written in a syntax left out by its convention | rewrite the pointer in an admitted syntax |
| `outside-repository` | the path names a file outside the repository, so it resolves on one machine only | move the file into the repository, or cite it by a URL |
| `convention` | the path names a file only under a path style left out by its convention | rewrite the path in an admitted style |
| `broken-anchor` | the fragment `#^name` names no block anchor of the cited file | add the anchor `^name` at the end of the cited line, or correct the fragment |
| `heading-fragment` | under `fragments: block`, a fragment opens on no caret, as the slug of a heading does | cite a block anchor `#^name`, since a slug changes with the heading |
| `foreign-scheme` | the target carries a URL scheme outside `schemes`, such as an address written by an editor | replace the address by a path, or declare the scheme |
| `unreadable-file` | a document read by a syntax of keys cannot be parsed | correct the syntax of the document |

A kind listed under `ignore` is not reported. The kind `unreadable-file` cannot be ignored, since a
file left unparsed hides all its pointers. The command exits with `1` when an issue is reported,
and with `2` when the configuration or a named target is invalid.
