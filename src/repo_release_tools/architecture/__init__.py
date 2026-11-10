"""Architecture skeleton checks and templates behind ``rrt arch``.

``core`` computes findings (units, files, layers, imports, import-linter
sync); ``templates`` renders ``.rrt/templates/<kind>/`` for ``rrt arch new``.
Both are pure library code; ``commands/arch_cmd.py`` owns all output.
"""
