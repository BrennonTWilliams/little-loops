"""CI checkout policy pins for history-dependent gates (BUG-3442).

``ll-verify-evidence`` builds its path -> blob-OID index from one
``git log --all --raw`` pass, so the gate needs full repository history.
``actions/checkout`` defaults to ``fetch-depth: 1``, which collapses that
index to the tip commit and makes the evidence gate structurally always-red
(~155 unverifiable-span findings on CI regardless of corpus state).

Fail, don't skip: the checkout depth is repo policy we control, not an
external tool a contributor might lack (contrast the skip-when-missing
idiom in ``test_decisions_yaml_gate.py``).
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_unit_tests_checkout_fetches_full_history() -> None:
    """The unit-tests job must check out with ``fetch-depth: 0`` (BUG-3442)."""
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["unit-tests"]["steps"]
    checkouts = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout")]
    assert checkouts, "unit-tests job has no actions/checkout step to pin"
    for step in checkouts:
        with_block = step.get("with") or {}
        assert with_block.get("fetch-depth") == 0, (
            f"{step.get('uses')} in unit-tests lacks `with: fetch-depth: 0` — "
            "the default depth-1 checkout collapses HistoryIndex's "
            "`git log --all --raw` pass to the tip commit and the evidence "
            "gate is structurally always-red (BUG-3442)"
        )
