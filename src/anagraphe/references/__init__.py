"""
The references written between the files of a repository, and the rules that they obey.

The repository declares where its references are written: the Markdown links of each layer, and
the fields of its YAML records (ADR 0003). The subpackage extracts each declared reference with
its exact place, resolves its path, and reports the references that name no file or anchor, or
break the convention of their layer.
"""
