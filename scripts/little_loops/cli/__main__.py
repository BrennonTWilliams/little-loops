"""``python -m little_loops.cli`` entry point.

The test suite's ``_cli()`` helper (see ``scripts/tests/test_ll_issues_check_*.py``)
falls back to ``python -m little_loops.cli`` when the ``ll-issues`` console
script is not on ``PATH`` (e.g. CI invokes ``.venv/bin/python -m pytest``
without activating the venv). This module makes that fallback work by routing
to ``main_issues`` — the same entry point the ``ll-issues`` script binds to
(``little_loops.cli:main_issues`` in ``pyproject.toml``).

Other top-level commands (``ll-action``, ``ll-auto``, ``ll-loop``, ...) keep
their dedicated console scripts; ``-m little_loops.cli`` intentionally mirrors
``ll-issues`` only, which is the single programmatic surface the subprocess
tests exercise.
"""

from __future__ import annotations

import sys

from little_loops.cli.issues import main_issues

if __name__ == "__main__":
    sys.exit(main_issues())
