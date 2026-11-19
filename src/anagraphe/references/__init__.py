"""
The references written between the files of a repository, and the rules that they obey.

The repository declares where its references are written: the Markdown links of each layer, and
the fields of its YAML records (ADR 0003). The subpackage extracts each declared reference with
its exact place, resolves its path, and reports the references that name no file or anchor, or
break the convention of their layer. The syntaxes, the conventions and the resolution lie in the
read distribution, under :mod:`anagraphe_read._references`; this subpackage holds the check, its
rules and the rewrite of references.
"""
