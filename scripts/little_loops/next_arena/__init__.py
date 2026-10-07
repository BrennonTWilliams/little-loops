"""Pure domain package for the ``ll-next`` action arena (FEAT-3561).

Importing this package performs no I/O and pulls in no config machinery, so
``little_loops.config`` can import :mod:`little_loops.next_arena.registry`
without creating an import cycle.
"""
