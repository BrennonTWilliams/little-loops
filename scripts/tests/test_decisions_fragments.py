"""Fragment-storage tests for little_loops.decisions (BUG-2644).

Covers the append-only fragment write + directory-union read layer that removes
the id / merge collisions reported in BUG-2642. Union-reader cases mirror
``test_cli_loop_queue.py::TestReadQueueEntries``; the dual-branch merge repro
mirrors ``test_merge_coordinator.py``'s ``temp_git_repo`` diverge-then-merge idiom.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.decisions import (
    DecisionEntry,
    RuleEntry,
    add_entry,
    load_decisions,
    save_decisions,
    set_outcome,
    update_entry,
)


@pytest.fixture
def decisions_path(tmp_path: Path) -> Path:
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    return ll_dir / "decisions.yaml"


def _frag_dir(decisions_path: Path) -> Path:
    return decisions_path.with_suffix(".d")


def _write_fragment(frag_dir: Path, name: str, payload: dict | str) -> Path:
    """Write a raw fragment, decoupled from add_entry() (mirrors queue tests)."""
    frag_dir.mkdir(parents=True, exist_ok=True)
    p = frag_dir / name
    text = payload if isinstance(payload, str) else json.dumps(payload)
    p.write_text(text, encoding="utf-8")
    return p


class TestFragmentWrite:
    def test_add_entry_writes_fragment_not_flat_file(self, decisions_path: Path) -> None:
        add_entry(RuleEntry(id="NAMING-001", rule="r"), decisions_path)
        assert not decisions_path.exists()
        frags = list(_frag_dir(decisions_path).glob("*.json"))
        assert len(frags) == 1

    def test_two_appends_do_not_share_a_file(self, decisions_path: Path) -> None:
        add_entry(RuleEntry(id="A-001", rule="a"), decisions_path)
        add_entry(RuleEntry(id="B-001", rule="b"), decisions_path)
        assert len(list(_frag_dir(decisions_path).glob("*.json"))) == 2
        assert {e.id for e in load_decisions(decisions_path)} == {"A-001", "B-001"}


class TestDirectoryUnionRead:
    def test_missing_dir_returns_empty(self, decisions_path: Path) -> None:
        assert load_decisions(decisions_path) == []

    def test_empty_dir_returns_empty(self, decisions_path: Path) -> None:
        _frag_dir(decisions_path).mkdir(parents=True, exist_ok=True)
        assert load_decisions(decisions_path) == []

    def test_multi_fragment_merge_sorted_by_timestamp(self, decisions_path: Path) -> None:
        frag_dir = _frag_dir(decisions_path)
        _write_fragment(frag_dir, "b.json", {"id": "B", "type": "rule", "timestamp": "2026-02"})
        _write_fragment(frag_dir, "a.json", {"id": "A", "type": "rule", "timestamp": "2026-01"})
        loaded = load_decisions(decisions_path)
        assert [e.id for e in loaded] == ["A", "B"]

    def test_malformed_fragment_skipped(self, decisions_path: Path) -> None:
        frag_dir = _frag_dir(decisions_path)
        _write_fragment(frag_dir, "good.json", {"id": "OK", "type": "rule"})
        _write_fragment(frag_dir, "bad.json", "{not json")
        _write_fragment(frag_dir, "noid.json", {"type": "rule"})  # missing id → skip
        _write_fragment(frag_dir, "badtype.json", {"id": "X", "type": "nope"})  # unknown → skip
        loaded = load_decisions(decisions_path)
        assert [e.id for e in loaded] == ["OK"]

    def test_colliding_ids_both_preserved(self, decisions_path: Path) -> None:
        """BUG-2642: two fragments with the same id must not silently overwrite."""
        frag_dir = _frag_dir(decisions_path)
        _write_fragment(frag_dir, "1.json", {"id": "DUP", "type": "rule", "timestamp": "2026-01"})
        _write_fragment(frag_dir, "2.json", {"id": "DUP", "type": "rule", "timestamp": "2026-02"})
        loaded = load_decisions(decisions_path)
        assert [e.id for e in loaded] == ["DUP", "DUP"]

    def test_unions_legacy_flat_file_with_fragments(self, decisions_path: Path) -> None:
        decisions_path.write_text(
            "entries:\n  - id: LEGACY-001\n    type: rule\n", encoding="utf-8"
        )
        add_entry(RuleEntry(id="FRAG-001", rule="r"), decisions_path)
        assert {e.id for e in load_decisions(decisions_path)} == {"LEGACY-001", "FRAG-001"}


class TestSaveCompactsFragments:
    def test_save_folds_fragments_and_clears_dir(self, decisions_path: Path) -> None:
        add_entry(RuleEntry(id="F-001", rule="r"), decisions_path)
        entries = load_decisions(decisions_path)
        save_decisions(entries, decisions_path)
        # Flat file now holds the entry; fragment dir emptied → no double count.
        assert not list(_frag_dir(decisions_path).glob("*.json"))
        data = yaml.safe_load(decisions_path.read_text())
        assert [e["id"] for e in data] == ["F-001"]
        assert [e.id for e in load_decisions(decisions_path)] == ["F-001"]


class TestUpdateEntry:
    """BUG-2645: fragment-targeted in-place mutation must not clear siblings."""

    def test_updates_only_the_backing_fragment(self, decisions_path: Path) -> None:
        add_entry(DecisionEntry(id="D-001", rationale="d"), decisions_path)
        add_entry(RuleEntry(id="R-002", rule="r"), decisions_path)
        frag_dir = _frag_dir(decisions_path)
        # Snapshot the sibling fragment (the one we are NOT mutating).
        sibling = next(
            f for f in frag_dir.glob("*.json") if json.loads(f.read_text())["id"] == "R-002"
        )
        sibling_before = sibling.read_bytes()

        def mutate(entry):
            entry.rationale = "changed"
            return entry

        update_entry("D-001", mutate, decisions_path)

        # Sibling fragment byte-identical; no compaction, flat file never created.
        assert sibling.read_bytes() == sibling_before
        assert not decisions_path.exists()
        assert len(list(frag_dir.glob("*.json"))) == 2
        loaded = {e.id: e for e in load_decisions(decisions_path)}
        assert loaded["D-001"].rationale == "changed"

    def test_flat_file_only_entry_rewrites_flat_without_clearing_fragments(
        self, decisions_path: Path
    ) -> None:
        decisions_path.write_text(
            "entries:\n  - id: FLAT-001\n    type: rule\n    rule: old\n", encoding="utf-8"
        )
        add_entry(RuleEntry(id="FRAG-001", rule="pending"), decisions_path)

        update_entry("FLAT-001", lambda e: RuleEntry(id="FLAT-001", rule="new"), decisions_path)

        # Flat entry updated; the pending fragment survives (not compacted away).
        data = yaml.safe_load(decisions_path.read_text())
        assert [e["id"] for e in data] == ["FLAT-001"]
        assert data[0]["rule"] == "new"
        assert len(list(_frag_dir(decisions_path).glob("*.json"))) == 1
        assert {e.id for e in load_decisions(decisions_path)} == {"FLAT-001", "FRAG-001"}

    def test_missing_id_raises_keyerror(self, decisions_path: Path) -> None:
        add_entry(RuleEntry(id="R-001", rule="r"), decisions_path)
        with pytest.raises(KeyError):
            update_entry("NOPE", lambda e: e, decisions_path)

    def test_mutate_exception_writes_nothing(self, decisions_path: Path) -> None:
        add_entry(RuleEntry(id="R-001", rule="orig"), decisions_path)
        frag = next(_frag_dir(decisions_path).glob("*.json"))
        before = frag.read_bytes()

        def boom(entry):
            raise TypeError("nope")

        with pytest.raises(TypeError):
            update_entry("R-001", boom, decisions_path)
        assert frag.read_bytes() == before


class TestSetOutcomeFragmentIsolation:
    """BUG-2645: set_outcome mutates a single fragment, leaving siblings intact."""

    def test_set_outcome_isolates_fragment(self, decisions_path: Path) -> None:
        add_entry(DecisionEntry(id="DEC-001", rationale="try X"), decisions_path)
        add_entry(RuleEntry(id="SIB-002", rule="r"), decisions_path)
        frag_dir = _frag_dir(decisions_path)
        sibling = next(
            f for f in frag_dir.glob("*.json") if json.loads(f.read_text())["id"] == "SIB-002"
        )
        sibling_before = sibling.read_bytes()

        set_outcome("DEC-001", "success", "2026-07-15", path=decisions_path)

        assert sibling.read_bytes() == sibling_before
        assert not decisions_path.exists()  # no compaction to the flat file
        assert len(list(frag_dir.glob("*.json"))) == 2
        loaded = {e.id: e for e in load_decisions(decisions_path)}
        assert loaded["DEC-001"].outcome is not None
        assert loaded["DEC-001"].outcome.result == "success"

    def test_set_outcome_missing_id_raises_keyerror(self, decisions_path: Path) -> None:
        with pytest.raises(KeyError):
            set_outcome("GONE", "success", "2026-07-15", path=decisions_path)

    def test_set_outcome_refuses_overwrite_without_force(self, decisions_path: Path) -> None:
        add_entry(DecisionEntry(id="DEC-001", rationale="d"), decisions_path)
        set_outcome("DEC-001", "success", "2026-07-15", path=decisions_path)
        with pytest.raises(ValueError):
            set_outcome("DEC-001", "failure", "2026-07-16", path=decisions_path)
        set_outcome("DEC-001", "failure", "2026-07-16", path=decisions_path, force=True)
        loaded = {e.id: e for e in load_decisions(decisions_path)}
        assert loaded["DEC-001"].outcome.result == "failure"

    def test_set_outcome_non_decision_raises_typeerror(self, decisions_path: Path) -> None:
        add_entry(RuleEntry(id="RULE-001", rule="r"), decisions_path)
        with pytest.raises(TypeError):
            set_outcome("RULE-001", "success", "2026-07-15", path=decisions_path)


@pytest.mark.integration
class TestDualBranchMergeNoConflict:
    def test_divergent_appends_merge_cleanly(self, tmp_path: Path) -> None:
        """Two branches each append a decision; merge must not conflict (BUG-2642)."""
        repo = tmp_path / "repo"
        repo.mkdir()

        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

        git("init")
        git("config", "user.email", "t@t.t")
        git("config", "user.name", "t")
        ll = repo / ".ll"
        ll.mkdir()
        decisions_path = ll / "decisions.yaml"
        decisions_path.write_text("entries: []\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-m", "seed")

        git("checkout", "-b", "branch-a")
        add_entry(RuleEntry(id="X", rule="from-a"), decisions_path)
        git("add", "-A")
        git("commit", "-m", "a")

        git("checkout", "main" if _has_main(repo) else "master")
        add_entry(RuleEntry(id="X", rule="from-b"), decisions_path)
        git("add", "-A")
        git("commit", "-m", "b")

        # No conflict: fragment files have distinct uuid names.
        merge = subprocess.run(
            ["git", "merge", "branch-a", "--no-edit"],
            cwd=repo,
            capture_output=True,
        )
        assert merge.returncode == 0, merge.stdout + merge.stderr

        loaded = load_decisions(decisions_path)
        rules = sorted(e.rule for e in loaded)
        assert rules == ["from-a", "from-b"]


def _has_main(repo: Path) -> bool:
    out = subprocess.run(
        ["git", "branch", "--list", "main"], cwd=repo, capture_output=True, text=True
    )
    return "main" in out.stdout
