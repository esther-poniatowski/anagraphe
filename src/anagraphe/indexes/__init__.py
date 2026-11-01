"""
Generation of the indexes of a repository from the metadata of their members.

An index declares its collection in its frontmatter: the groups, their membership, their order
and their nesting (ADR 0002). The subpackage renders the generated regions of each index, reports
their drift and the defects of the declaration, and writes the regions on request.
"""
