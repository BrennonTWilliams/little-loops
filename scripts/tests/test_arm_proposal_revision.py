"""ll-issues arm-proposal-revision (BUG-3574)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from little_loops.cli.issues.arm_proposal_revision import cmd_arm_proposal_revision
from little_loops.issue_parser import (
    locate_enumerable_options,
    locate_unresolved_decisions,
    refuted_option_labels,
)


class _Cfg:
    def __init__(self, root: Path) -> None:
        self.root = root


@pytest.fixture
def issue_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "P3-BUG-9500-x.md"
    monkeypatch.setattr(
        "little_loops.cli.issues.show._resolve_issue_id",
        lambda _c, i: path if i == "BUG-9500" else None,
    )
    return path


def _doc(proposed: str, extra_fm: str = "", tail: str = "") -> str:
    return (
        f"---\nid: BUG-9500\ntype: BUG\nstatus: open\n{extra_fm}---\n\n# T\n\n"
        f"## Proposed Solution\n\n{proposed}\n\n{tail}## Status\n\nOpen\n"
    )


def _run(id_: str = "BUG-9500") -> int:
    return cmd_arm_proposal_revision(_Cfg(Path(".")), argparse.Namespace(issue_id=id_))  # type: ignore[arg-type]


DECIDED = (
    "### Option A: Raise through handler\n> **Selected:** Option A: Raise through handler — "
    "simplest\nstep\n\n### Option B: Alt\nbody\n\n### Decision Rationale\n\nA.\n"
)


def test_arms_with_alternative(issue_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    issue_path.write_text(_doc(DECIDED, 'verify_evidence: "handler at x.py:40 swallows it"\n'))
    assert _run() == 0
    assert "[PROPOSAL_REVISION_ARMED] BUG-9500" in capsys.readouterr().out
    text = issue_path.read_text()
    assert "decision_needed: true" in text
    assert refuted_option_labels(text) == {"option a"}
    assert "handler at x.py:40 swallows it" in text
    assert [o.eligible for o in locate_enumerable_options(text).options] == [False, True]
    assert len(locate_unresolved_decisions(text, include_approximate_tiers=True)) == 1


def test_missing_evidence_gives_wellformed_marker(issue_path: Path) -> None:
    issue_path.write_text(_doc(DECIDED))
    assert _run() == 0
    text = issue_path.read_text()
    assert "no evidence persisted" in text
    assert refuted_option_labels(text) == {"option a"}


def test_second_revision_selects_eligible_b(issue_path: Path) -> None:
    three = DECIDED.replace(
        "### Decision Rationale",
        "### Option C: Third\nbody\n\n### Decision Rationale",
    )
    issue_path.write_text(_doc(three))
    assert _run() == 0
    text = issue_path.read_text().replace(
        "body\n\n### Option C", "> **Selected:** Option B: Alt\nbody\n\n### Option C", 1
    )
    issue_path.write_text(text)
    assert _run() == 0
    assert refuted_option_labels(issue_path.read_text()) == {"option a", "option b"}


@pytest.mark.parametrize(
    "proposed",
    [
        "Just change the handler.",
        "### Option A: x\nstep\n\n### Option B: y\nbody\n",
        "### Option A: x\n> **Selected:** (x) — keep\nstep\n\n### Option B: y\nbody\n",
        "### Option A: x\n> **Selected:** Option A: x\nstep\n",
    ],
    ids=["no-options", "no-callout", "pattern-d", "only-eligible"],
)
def test_no_alternative_exits_one_without_change(issue_path: Path, proposed: str) -> None:
    doc = _doc(proposed)
    issue_path.write_text(doc)
    assert _run() == 1
    assert issue_path.read_text() == doc


def test_all_others_refuted_exits_one(issue_path: Path) -> None:
    tail = (
        "## Open Questions\n\n1. **Refuted option**: Option B — spike. Which remaining option "
        "replaces it?\n\n"
    )
    doc = _doc(DECIDED, tail=tail)
    issue_path.write_text(doc)
    assert _run() == 1
    assert issue_path.read_text() == doc


def test_unknown_id_exits_two(issue_path: Path) -> None:
    assert _run("BUG-1") == 2
