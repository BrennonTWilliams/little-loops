"""Drift guard for repo-root files duplicated into scripts/ for packaging.

hatchling's build root is scripts/, so README.md and LICENSE are duplicated
there rather than referenced with an escaping ../ path (BUG-3179). Nothing
enforced that the duplicates stay in sync with their repo-root originals
before this test — this closes that gap for both files.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


class TestPackagingDuplicateFiles:
    def test_readme_matches_repo_root(self) -> None:
        original = (REPO_ROOT / "README.md").read_bytes()
        duplicate = (SCRIPTS_DIR / "README.md").read_bytes()
        assert original == duplicate, (
            "scripts/README.md has drifted from the repo-root README.md — "
            "re-copy it (see BUG-3179)."
        )

    def test_license_matches_repo_root(self) -> None:
        original = (REPO_ROOT / "LICENSE").read_bytes()
        duplicate = (SCRIPTS_DIR / "LICENSE").read_bytes()
        assert original == duplicate, (
            "scripts/LICENSE has drifted from the repo-root LICENSE — re-copy it."
        )
