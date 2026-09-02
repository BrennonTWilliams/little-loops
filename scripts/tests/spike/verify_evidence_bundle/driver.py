"""Render a sample bundle from a fixture verify-issue-loop run for manual inspection.

Answers FEAT-3182's empirical question -- run this and read the printed JSON:
is the resulting (deliberately weaker) Option A bundle still useful to a
reviewer, or does it read as "a check was attempted" with no real content?
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .bundle import assemble_bundle
from .test_bundle import build_fixture_run_dir, FIXTURE_LOOP_RUNS_ROW


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = build_fixture_run_dir(Path(tmp))
        bundle = assemble_bundle(
            loop_runs_row=FIXTURE_LOOP_RUNS_ROW,
            run_dir=run_dir,
            git_facts={"head_sha": "abc1234", "branch": "main"},
        )
        print(json.dumps(bundle.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
