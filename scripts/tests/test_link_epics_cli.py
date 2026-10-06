"""Tests for ll-issues link-epics sub-command (FEAT-2942)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _write_issue(issues_dir: Path, category: str, filename: str, content: str) -> Path:
    path = issues_dir / category / filename
    path.write_text(content)
    return path


@pytest.fixture
def epics_dir(issues_dir: Path) -> Path:
    d = issues_dir / "epics"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestProposeAssignments:
    """Unit tests for propose_assignments() scoring/tiering/sorting."""

    def _orphan(self, path: Path, issue_id: str, title: str):
        from little_loops.issue_parser import IssueInfo

        return IssueInfo(
            path=path, issue_type="FEAT", priority="P2", issue_id=issue_id, title=title
        )

    def _epic(self, path: Path, issue_id: str, title: str):
        from little_loops.issue_parser import IssueInfo

        return IssueInfo(
            path=path, issue_type="EPIC", priority="P2", issue_id=issue_id, title=title
        )

    def test_empty_corpus_returns_empty(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import propose_assignments

        assert propose_assignments([], [], threshold=0.0) == []

    def test_scores_and_tiers(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import propose_assignments

        orphan = self._orphan(tmp_path / "o.md", "FEAT-1", "loop automation workflow tracker")
        epic = self._epic(tmp_path / "e.md", "EPIC-1", "loop automation workflow tracker")
        proposals = propose_assignments([orphan], [epic], threshold=0.0)
        assert len(proposals) == 1
        p = proposals[0]
        assert p.orphan_id == "FEAT-1"
        assert p.epic_id == "EPIC-1"
        assert p.score == 1.0
        assert p.tier == "HIGH"

    def test_tier_boundaries(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import _tier_for_score

        assert _tier_for_score(0.7) == "HIGH"
        assert _tier_for_score(0.69) == "MEDIUM"
        assert _tier_for_score(0.4) == "MEDIUM"
        assert _tier_for_score(0.39) == "LOW"
        assert _tier_for_score(0.0) == "LOW"

    def test_threshold_excludes_low_scores(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import propose_assignments

        orphan = self._orphan(tmp_path / "o.md", "FEAT-1", "completely unrelated topic")
        epic = self._epic(tmp_path / "e.md", "EPIC-1", "loop automation workflow tracker")
        proposals = propose_assignments([orphan], [epic], threshold=0.5)
        assert proposals == []

    def test_deterministic_tiebreak_sort(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import propose_assignments

        orphan_a = self._orphan(tmp_path / "a.md", "FEAT-2", "loop automation workflow tracker")
        orphan_b = self._orphan(tmp_path / "b.md", "FEAT-1", "loop automation workflow tracker")
        epic = self._epic(tmp_path / "e.md", "EPIC-1", "loop automation workflow tracker")
        proposals = propose_assignments([orphan_a, orphan_b], [epic], threshold=0.0)
        # Equal scores -> tiebreak by orphan_id ascending
        assert [p.orphan_id for p in proposals] == ["FEAT-1", "FEAT-2"]


class TestSynthesizeClusters:
    """Unit tests for synthesize_clusters() union-find clustering."""

    def _orphan(self, tmp_path: Path, issue_id: str, title: str, priority: str = "P2"):
        from little_loops.issue_parser import IssueInfo

        return IssueInfo(
            path=tmp_path / f"{issue_id}.md",
            issue_type=issue_id.split("-")[0],
            priority=priority,
            issue_id=issue_id,
            title=title,
        )

    def test_no_edges_no_clusters(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import synthesize_clusters

        a = self._orphan(tmp_path, "FEAT-1", "alpha beta gamma")
        b = self._orphan(tmp_path, "FEAT-2", "delta epsilon zeta")
        assert synthesize_clusters([a, b], min_score=0.5) == []

    def test_chain_clusters_via_union_find(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import synthesize_clusters

        # A-B share words, B-C share words, A-C do not directly overlap enough,
        # but union-find should still merge all three transitively via B.
        a = self._orphan(tmp_path, "FEAT-1", "loop automation workflow alpha")
        b = self._orphan(tmp_path, "FEAT-2", "loop automation workflow beta")
        c = self._orphan(tmp_path, "FEAT-3", "loop automation workflow gamma")
        clusters = synthesize_clusters([a, b, c], min_score=0.4)
        assert len(clusters) == 1
        assert sorted(clusters[0].member_ids) == ["FEAT-1", "FEAT-2", "FEAT-3"]

    def test_modal_priority(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import synthesize_clusters

        a = self._orphan(tmp_path, "FEAT-1", "loop automation workflow alpha", priority="P1")
        b = self._orphan(tmp_path, "FEAT-2", "loop automation workflow beta", priority="P2")
        c = self._orphan(tmp_path, "FEAT-3", "loop automation workflow gamma", priority="P2")
        clusters = synthesize_clusters([a, b, c], min_score=0.4)
        assert clusters[0].modal_priority == "P2"

    def test_placeholder_title_frequency_derived(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import synthesize_clusters

        a = self._orphan(tmp_path, "FEAT-1", "loop automation workflow alpha")
        b = self._orphan(tmp_path, "FEAT-2", "loop automation workflow beta")
        clusters = synthesize_clusters([a, b], min_score=0.4)
        assert clusters
        title = clusters[0].placeholder_title.lower()
        assert "loop" in title
        assert "automation" in title

    def test_single_member_orphans_not_clustered(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import synthesize_clusters

        a = self._orphan(tmp_path, "FEAT-1", "loop automation workflow alpha")
        b = self._orphan(tmp_path, "FEAT-2", "completely disjoint unrelated matter")
        clusters = synthesize_clusters([a, b], min_score=0.4)
        assert clusters == []


class TestApplyAssignment:
    """Unit tests for apply_assignment()'s frontmatter + body writes."""

    def test_writes_parent_and_epic_fields(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import EpicProposal, apply_assignment

        orphan_path = tmp_path / "orphan.md"
        orphan_path.write_text("---\nid: FEAT-1\nstatus: open\n---\n\n# FEAT-1: Orphan\n")
        epic_path = tmp_path / "epic.md"
        epic_path.write_text(
            "---\nid: EPIC-1\nstatus: open\n---\n\n# EPIC-1: Container\n\n## Children\n"
        )

        proposal = EpicProposal(orphan_id="FEAT-1", epic_id="EPIC-1", score=0.9, tier="HIGH")
        apply_assignment(proposal, orphan_path=orphan_path, epic_path=epic_path)

        from little_loops.frontmatter import parse_frontmatter

        orphan_fm = parse_frontmatter(orphan_path.read_text())
        assert orphan_fm["parent"] == "EPIC-1"
        assert orphan_fm["epic"] == "EPIC-1"
        assert "FEAT-1" in epic_path.read_text()

    def test_idempotent_reapply(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import EpicProposal, apply_assignment

        orphan_path = tmp_path / "orphan.md"
        orphan_path.write_text("---\nid: FEAT-1\nstatus: open\n---\n\n# FEAT-1: Orphan\n")
        epic_path = tmp_path / "epic.md"
        epic_path.write_text(
            "---\nid: EPIC-1\nstatus: open\n---\n\n# EPIC-1: Container\n\n## Children\n"
        )

        proposal = EpicProposal(orphan_id="FEAT-1", epic_id="EPIC-1", score=0.9, tier="HIGH")
        apply_assignment(proposal, orphan_path=orphan_path, epic_path=epic_path)
        apply_assignment(proposal, orphan_path=orphan_path, epic_path=epic_path)

        body = epic_path.read_text()
        assert body.count("FEAT-1") == 1


_EPIC_TEXT = (
    "---\nid: EPIC-1\ntitle: Container\nstatus: open\n---\n\n# EPIC-1: Container\n\n"
    "## Children\n\n- **FEAT-7** — Existing (open)\n  wrapped note\n\n### Notes\n\nSee FEAT-1 here.\n\n"
    "## Status\n\n**Open**\n"
)
_ORPHAN_TEXT = (
    "---\nid: FEAT-1\ntitle: Orphan Feature\ngoals: [2]  # keep\nstatus: open\n---\n\n"
    "# FEAT-1: Orphan Feature\n"
)


def _pair(tmp_path: Path, orphan: str = _ORPHAN_TEXT, epic: str = _EPIC_TEXT) -> tuple[Path, Path]:
    orphan_path = tmp_path / "orphan.md"
    epic_path = tmp_path / "epic.md"
    orphan_path.write_bytes(orphan.encode())
    epic_path.write_bytes(epic.encode())
    return orphan_path, epic_path


def _proposal(epic_id: str = "EPIC-1"):
    from little_loops.cli.issues.link_epics import EpicProposal

    return EpicProposal(orphan_id="FEAT-1", epic_id=epic_id, score=0.9, tier="HIGH")


class TestApplyAssignmentHardening:
    """BUG-3738: precise, preserving, lock-guarded pair writes."""

    def test_title_bullet_placed_before_notes_and_orphan_churn_free(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import apply_assignment

        orphan_path, epic_path = _pair(tmp_path)
        assert apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path) is True

        assert epic_path.read_text() == _EPIC_TEXT.replace(
            "  wrapped note\n", "  wrapped note\n- **FEAT-1** — Orphan Feature (open)\n"
        )
        assert orphan_path.read_text() == _ORPHAN_TEXT.replace(
            "status: open\n---", "status: open\nparent: EPIC-1\nepic: EPIC-1\n---"
        )
        assert "added by link-epics" not in epic_path.read_text()

    def test_prose_mention_does_not_suppress_insertion(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import apply_assignment

        orphan_path, epic_path = _pair(tmp_path)
        apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path)
        assert "- **FEAT-1** —" in epic_path.read_text()

    def test_reapply_is_byte_identical_and_writes_nothing(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import apply_assignment

        orphan_path, epic_path = _pair(tmp_path)
        apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path)
        snapshot = (orphan_path.read_bytes(), epic_path.read_bytes())
        with patch("little_loops.file_utils.atomic_write") as writer:
            apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path)
        writer.assert_not_called()
        assert (orphan_path.read_bytes(), epic_path.read_bytes()) == snapshot

    def test_missing_heading_leaves_epic_untouched(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import apply_assignment

        epic = "---\nid: EPIC-1\n---\n\n# E\n\n## Child Issues\n- x\n"
        orphan_path, epic_path = _pair(tmp_path, epic=epic)
        assert apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path) is False
        assert epic_path.read_text() == epic
        assert "parent: EPIC-1" in orphan_path.read_text()

    def test_crlf_and_mode_preserved(self, tmp_path: Path) -> None:
        import os

        from little_loops.cli.issues.link_epics import apply_assignment

        orphan_path, epic_path = _pair(
            tmp_path,
            _ORPHAN_TEXT.replace("\n", "\r\n"),
            _EPIC_TEXT.replace("\n", "\r\n"),
        )
        os.chmod(orphan_path, 0o644)
        os.chmod(epic_path, 0o664)
        apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path)
        for path in (orphan_path, epic_path):
            raw = path.read_bytes()
            assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
        assert os.stat(orphan_path).st_mode & 0o777 == 0o644
        assert os.stat(epic_path).st_mode & 0o777 == 0o664

    def test_conflicting_parent_rejected_without_writes(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import ConflictingParent, apply_assignment

        orphan = _ORPHAN_TEXT.replace("status: open\n", "status: open\nparent: EPIC-2\n")
        orphan_path, epic_path = _pair(tmp_path, orphan)
        with pytest.raises(ConflictingParent, match="parent: EPIC-2"):
            apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path)
        assert orphan_path.read_text() == orphan
        assert epic_path.read_text() == _EPIC_TEXT

    def test_title_fallbacks(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import apply_assignment

        orphan_path, epic_path = _pair(tmp_path, orphan="---\nid: FEAT-1\n---\n\n# FEAT-1\n")
        apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path)
        assert "- **FEAT-1** — FEAT-1 (open)" in epic_path.read_text()

    def test_lock_timeout_leaves_files_untouched(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import apply_assignment

        orphan_path, epic_path = _pair(tmp_path)
        with patch("little_loops.file_utils.acquire_lock", side_effect=TimeoutError("busy")):
            with pytest.raises(TimeoutError):
                apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path)
        assert orphan_path.read_text() == _ORPHAN_TEXT
        assert epic_path.read_text() == _EPIC_TEXT

    def test_second_write_failure_names_remedy_and_direct_reapply_repairs(
        self, tmp_path: Path
    ) -> None:
        from little_loops.cli.issues.link_epics import apply_assignment
        from little_loops.file_utils import atomic_write

        orphan_path, epic_path = _pair(tmp_path)

        def flaky(path: Path, content: str, *a: Any, **kw: Any) -> None:
            if path == epic_path:
                raise OSError("disk full")
            atomic_write(path, content, *a, **kw)

        with patch("little_loops.file_utils.atomic_write", flaky):
            with pytest.raises(OSError, match="epic-consistency --fix EPIC-1"):
                apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path)
        assert "parent: EPIC-1" in orphan_path.read_text()
        assert epic_path.read_text() == _EPIC_TEXT

        apply_assignment(_proposal(), orphan_path=orphan_path, epic_path=epic_path)
        assert "- **FEAT-1** — Orphan Feature (open)" in epic_path.read_text()


class TestLinkEpicsCLI:
    """Integration tests for the ll-issues link-epics dispatch/CLI surface."""

    def _run(self, temp_project_dir: Path, *cli_args: str) -> int:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "link-epics", *cli_args, "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            return main_issues()

    def test_assign_mode_json_no_writes_without_apply(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-1-orphan.md",
            "---\nid: FEAT-1\ntitle: loop automation workflow tracker\nstatus: open\n---\n"
            "# FEAT-1: loop automation workflow tracker\n",
        )
        _write_issue(
            issues_dir,
            "epics",
            "P2-EPIC-1-container.md",
            "---\nid: EPIC-1\ntitle: loop automation workflow tracker\nstatus: open\n---\n"
            "# EPIC-1: loop automation workflow tracker\n\n## Children\n",
        )

        exit_code = self._run(temp_project_dir, "--mode", "assign", "--threshold", "0.5", "--json")
        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["applied"] == []
        assert len(out["proposals"]) == 1
        assert out["proposals"][0]["orphan_id"] == "FEAT-1"

        # No writes happened — parent: field must still be absent
        orphan_path = issues_dir / "features" / "P2-FEAT-1-orphan.md"
        assert "parent:" not in orphan_path.read_text()

    def test_apply_writes_frontmatter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        orphan_path = _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-1-orphan.md",
            "---\nid: FEAT-1\ntitle: loop automation workflow tracker\nstatus: open\n---\n"
            "# FEAT-1: loop automation workflow tracker\n",
        )
        _write_issue(
            issues_dir,
            "epics",
            "P2-EPIC-1-container.md",
            "---\nid: EPIC-1\ntitle: loop automation workflow tracker\nstatus: open\n---\n"
            "# EPIC-1: loop automation workflow tracker\n\n## Children\n",
        )

        exit_code = self._run(
            temp_project_dir, "--mode", "assign", "--threshold", "0.5", "--apply", "--json"
        )
        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert len(out["applied"]) == 1

        from little_loops.frontmatter import parse_frontmatter

        fm = parse_frontmatter(orphan_path.read_text())
        assert fm["parent"] == "EPIC-1"
        assert fm["epic"] == "EPIC-1"

    def test_apply_synthesize_mode_errors(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        exit_code = self._run(temp_project_dir, "--mode", "synthesize", "--apply")
        assert exit_code == 1

    def test_synthesize_mode_json(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-1-a.md",
            "---\nid: FEAT-1\ntitle: loop automation workflow alpha\nstatus: open\n---\n# FEAT-1\n",
        )
        _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-2-b.md",
            "---\nid: FEAT-2\ntitle: loop automation workflow beta\nstatus: open\n---\n# FEAT-2\n",
        )

        exit_code = self._run(
            temp_project_dir, "--mode", "synthesize", "--threshold", "0.4", "--json"
        )
        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["applied"] == []
        assert len(out["clusters"]) == 1
        assert sorted(out["clusters"][0]["member_ids"]) == ["FEAT-1", "FEAT-2"]


def _make_deep_runner():
    """Fake HostRunner exposing only build_blocking_json, matching test_artifact_discover.py."""
    from little_loops.host_runner import HostInvocation

    return type(
        "FakeRunner",
        (),
        {
            "name": "claude-code",
            "build_blocking_json": lambda self, *, prompt, model=None, json_schema=None: (
                HostInvocation(binary="claude", args=["-p", prompt])
            ),
        },
    )()


class TestDeepSynthesizeClusters:
    """Unit tests for --deep's LLM-adjudicated clustering (ENH-2979)."""

    def _orphan(
        self, tmp_path: Path, issue_id: str, title: str, summary: str, priority: str = "P2"
    ):
        from little_loops.issue_parser import IssueInfo

        path = tmp_path / f"{issue_id}.md"
        path.write_text(
            f"---\nid: {issue_id}\ntitle: {title}\nstatus: open\n---\n\n"
            f"# {issue_id}: {title}\n\n## Summary\n\n{summary}\n"
        )
        return IssueInfo(
            path=path,
            issue_type=issue_id.split("-")[0],
            priority=priority,
            issue_id=issue_id,
            title=title,
        )

    def test_deep_omitted_leaves_to_dict_unchanged(self) -> None:
        from little_loops.cli.issues.link_epics import ClusterProposal

        c = ClusterProposal(
            member_ids=["FEAT-1", "FEAT-2"],
            placeholder_title="Title",
            modal_priority="P2",
            pairwise_min_score=0.5,
        )
        assert c.to_dict() == {
            "member_ids": ["FEAT-1", "FEAT-2"],
            "placeholder_title": "Title",
            "modal_priority": "P2",
            "pairwise_min_score": 0.5,
        }

    def test_deep_merges_jaccard_and_llm_cluster(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import deep_synthesize_clusters, synthesize_clusters

        a = self._orphan(tmp_path, "FEAT-1", "loop automation workflow alpha", "alpha details")
        b = self._orphan(tmp_path, "FEAT-2", "loop automation workflow beta", "beta details")
        c = self._orphan(tmp_path, "FEAT-3", "completely different topic gamma", "gamma details")

        jaccard_clusters = synthesize_clusters([a, b, c], min_score=0.4)
        assert sorted(jaccard_clusters[0].member_ids) == ["FEAT-1", "FEAT-2"]

        raw = {
            "clusters": [
                {
                    "member_ids": ["FEAT-2", "FEAT-3"],
                    "placeholder_title": "Shared Theme",
                    "evidence": ["loop automation workflow beta", "gamma details"],
                }
            ]
        }
        with (
            patch(
                "little_loops.cli.issues.link_epics.resolve_host",
                return_value=_make_deep_runner(),
            ),
            patch(
                "little_loops.cli.issues.link_epics.run_blocking_json",
                return_value=raw,
            ),
        ):
            merged, skip_info = deep_synthesize_clusters([a, b, c], jaccard_clusters)

        assert skip_info is None
        assert len(merged) == 1
        cluster = merged[0]
        assert sorted(cluster.member_ids) == ["FEAT-1", "FEAT-2", "FEAT-3"]
        assert cluster.source == "merged"
        assert cluster.evidence == ["loop automation workflow beta", "gamma details"]
        assert cluster.modal_priority == "P2"

    def test_deep_schema_passed_to_both_calls(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import _DEEP_CLUSTER_SCHEMA, _deep_cluster_call

        a = self._orphan(tmp_path, "FEAT-1", "alpha", "alpha summary")
        b = self._orphan(tmp_path, "FEAT-2", "beta", "beta summary")
        raw = {"clusters": []}

        runner = _make_deep_runner()
        with (
            patch(
                "little_loops.cli.issues.link_epics.resolve_host",
                return_value=runner,
            ) as mock_resolve,
            patch(
                "little_loops.cli.issues.link_epics.run_blocking_json",
                return_value=raw,
            ) as mock_run,
        ):
            with patch.object(
                runner, "build_blocking_json", wraps=runner.build_blocking_json
            ) as mock_build:
                result = _deep_cluster_call([(a, "alpha summary"), (b, "beta summary")])

        assert result == []
        assert mock_resolve.called
        _, build_kwargs = mock_build.call_args
        assert build_kwargs["json_schema"] is _DEEP_CLUSTER_SCHEMA
        _, run_kwargs = mock_run.call_args
        assert run_kwargs["schema"] is _DEEP_CLUSTER_SCHEMA
        assert run_kwargs["schema"] is not None

    def test_deep_over_cap_skips_llm_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import little_loops.cli.issues.link_epics as link_epics_module

        monkeypatch.setattr(link_epics_module, "_DEEP_CANDIDATE_CAP", 1)

        a = self._orphan(tmp_path, "FEAT-1", "alpha", "alpha summary")
        b = self._orphan(tmp_path, "FEAT-2", "beta", "beta summary")

        with (
            patch("little_loops.cli.issues.link_epics.resolve_host") as mock_resolve,
            patch("little_loops.cli.issues.link_epics.run_blocking_json") as mock_run,
        ):
            merged, skip_info = link_epics_module.deep_synthesize_clusters([a, b], [])

        assert merged == []
        assert skip_info == {"skipped": "too_many_orphans", "count": 2}
        mock_resolve.assert_not_called()
        mock_run.assert_not_called()

    def test_deep_drops_unknown_id_and_unverifiable_evidence(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.cli.issues.link_epics import deep_synthesize_clusters

        a = self._orphan(tmp_path, "FEAT-10", "alpha topic", "alpha summary text")
        b = self._orphan(tmp_path, "FEAT-11", "beta topic", "beta summary text")
        c = self._orphan(tmp_path, "FEAT-12", "gamma topic", "gamma summary text")

        raw = {
            "clusters": [
                {
                    "member_ids": ["FEAT-10", "FEAT-99"],
                    "placeholder_title": "x",
                    "evidence": ["alpha topic"],
                },
                {
                    "member_ids": ["FEAT-11", "FEAT-12"],
                    "placeholder_title": "y",
                    "evidence": ["this text was never in any orphan"],
                },
            ]
        }
        with (
            patch(
                "little_loops.cli.issues.link_epics.resolve_host",
                return_value=_make_deep_runner(),
            ),
            patch("little_loops.cli.issues.link_epics.run_blocking_json", return_value=raw),
        ):
            merged, skip_info = deep_synthesize_clusters([a, b, c], [])

        assert skip_info is None
        assert merged == []
        stderr = capsys.readouterr().err
        assert "dropped unknown member id FEAT-99" in stderr
        assert "no verifiable evidence" in stderr

    def test_deep_key_check_failure_raises(self, tmp_path: Path) -> None:
        from little_loops.cli.issues.link_epics import _deep_cluster_call

        a = self._orphan(tmp_path, "FEAT-1", "alpha", "alpha summary")
        with (
            patch(
                "little_loops.cli.issues.link_epics.resolve_host",
                return_value=_make_deep_runner(),
            ),
            patch(
                "little_loops.cli.issues.link_epics.run_blocking_json",
                return_value={"unexpected": []},
            ),
        ):
            with pytest.raises(ValueError, match="missing expected keys"):
                _deep_cluster_call([(a, "alpha summary")])


class TestDeepSynthesizeCLI:
    """CLI-level tests for `ll-issues link-epics --mode synthesize --deep` (ENH-2979)."""

    def _run(self, temp_project_dir: Path, *cli_args: str) -> int:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "link-epics", *cli_args, "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            return main_issues()

    def test_deep_with_default_mode_errors(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        exit_code = self._run(temp_project_dir, "--deep")
        assert exit_code == 1
        assert "--deep is only supported for --mode synthesize" in capsys.readouterr().err

    def test_deep_call_failure_prints_error_and_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from little_loops.host_runner import BlockingJsonError

        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-1-a.md",
            "---\nid: FEAT-1\ntitle: loop automation workflow alpha\nstatus: open\n---\n"
            "# FEAT-1\n\n## Summary\n\nalpha\n",
        )
        _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-2-b.md",
            "---\nid: FEAT-2\ntitle: loop automation workflow beta\nstatus: open\n---\n"
            "# FEAT-2\n\n## Summary\n\nbeta\n",
        )

        with (
            patch(
                "little_loops.cli.issues.link_epics.resolve_host",
                return_value=_make_deep_runner(),
            ),
            patch(
                "little_loops.cli.issues.link_epics.run_blocking_json",
                side_effect=BlockingJsonError("boom", {"error": "boom"}),
            ),
        ):
            exit_code = self._run(
                temp_project_dir, "--mode", "synthesize", "--threshold", "0.4", "--deep"
            )
        assert exit_code == 1
        assert "Error: --deep cluster call failed" in capsys.readouterr().err

    def test_deep_end_to_end_json_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-1-a.md",
            "---\nid: FEAT-1\ntitle: predicate duplication in autodev\nstatus: open\n---\n"
            "# FEAT-1\n\n## Summary\n\npredicate duplication details\n",
        )
        _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-2-b.md",
            "---\nid: FEAT-2\ntitle: heuristic duplication in refine-issue\nstatus: open\n---\n"
            "# FEAT-2\n\n## Summary\n\nheuristic duplication details\n",
        )

        raw = {
            "clusters": [
                {
                    "member_ids": ["FEAT-1", "FEAT-2"],
                    "placeholder_title": "Duplication Cleanup",
                    "evidence": [
                        "predicate duplication in autodev",
                        "heuristic duplication in refine-issue",
                    ],
                }
            ]
        }
        with (
            patch(
                "little_loops.cli.issues.link_epics.resolve_host",
                return_value=_make_deep_runner(),
            ),
            patch("little_loops.cli.issues.link_epics.run_blocking_json", return_value=raw),
        ):
            exit_code = self._run(
                temp_project_dir, "--mode", "synthesize", "--threshold", "0.9", "--deep", "--json"
            )
        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert "deep" not in out
        assert len(out["clusters"]) == 1
        cluster = out["clusters"][0]
        assert sorted(cluster["member_ids"]) == ["FEAT-1", "FEAT-2"]
        assert cluster["source"] == "deep"
        assert cluster["evidence"]

    def test_deep_over_cap_json_reports_skip(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import little_loops.cli.issues.link_epics as link_epics_module

        monkeypatch.setattr(link_epics_module, "_DEEP_CANDIDATE_CAP", 1)

        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-1-a.md",
            "---\nid: FEAT-1\ntitle: loop automation workflow alpha\nstatus: open\n---\n"
            "# FEAT-1\n\n## Summary\n\nalpha\n",
        )
        _write_issue(
            issues_dir,
            "features",
            "P2-FEAT-2-b.md",
            "---\nid: FEAT-2\ntitle: loop automation workflow beta\nstatus: open\n---\n"
            "# FEAT-2\n\n## Summary\n\nbeta\n",
        )

        with (
            patch("little_loops.cli.issues.link_epics.resolve_host") as mock_resolve,
            patch("little_loops.cli.issues.link_epics.run_blocking_json") as mock_run,
        ):
            exit_code = self._run(
                temp_project_dir, "--mode", "synthesize", "--threshold", "0.4", "--deep", "--json"
            )
        assert exit_code == 0
        mock_resolve.assert_not_called()
        mock_run.assert_not_called()
        stderr = capsys.readouterr()
        out = json.loads(stderr.out)
        assert out["deep"]["skipped"] == "too_many_orphans"
        assert out["deep"]["count"] > 1
        assert "exceeds the 1-orphan cap" in stderr.err


class TestLinkEpicsConfigSchema:
    """Tests for the issues.link_epics.min_score config key."""

    def test_config_default(self) -> None:
        from little_loops.config.features import IssuesConfig

        cfg = IssuesConfig.from_dict({})
        assert cfg.link_epics.min_score == 0.0

    def test_config_override(self) -> None:
        from little_loops.config.features import IssuesConfig

        cfg = IssuesConfig.from_dict({"link_epics": {"min_score": 0.6}})
        assert cfg.link_epics.min_score == 0.6


class TestApplyOneWinnerAndRejections:
    """BUG-3738: one EPIC per orphan, continue-and-report on rejections."""

    def _run(self, temp_project_dir: Path, *cli_args: str) -> int:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "link-epics", *cli_args, "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            return main_issues()

    def _setup(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))

    def _epic(self, issues_dir: Path, num: int, title: str) -> Path:
        return _write_issue(
            issues_dir,
            "epics",
            f"P2-EPIC-{num}-e.md",
            f"---\nid: EPIC-{num}\ntitle: {title}\nstatus: open\n---\n# EPIC-{num}: {title}\n\n"
            "## Children\n\n",
        )

    def _orphan(self, issues_dir: Path, num: int, title: str) -> Path:
        return _write_issue(
            issues_dir,
            "features",
            f"P2-FEAT-{num}-o.md",
            f"---\nid: FEAT-{num}\ntitle: {title}\nstatus: open\n---\n# FEAT-{num}: {title}\n",
        )

    def test_only_top_ranked_epic_applied_but_all_proposals_listed(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._setup(temp_project_dir, sample_config)
        orphan = self._orphan(issues_dir, 1, "loop automation")
        strong = self._epic(issues_dir, 1, "loop automation")
        weak = self._epic(issues_dir, 2, "loop automation workflow tracker")

        code = self._run(temp_project_dir, "--threshold", "0.4", "--apply", "--json")
        out = json.loads(capsys.readouterr().out)

        assert code == 0
        assert len(out["proposals"]) == 2
        assert [a["epic_id"] for a in out["applied"]] == ["EPIC-1"]
        assert out["rejected"] == []
        assert "- **FEAT-1** — loop automation (open)" in strong.read_text()
        assert "FEAT-1" not in weak.read_text()
        assert "parent: EPIC-1" in orphan.read_text()

    def test_missing_children_heading_flagged_in_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._setup(temp_project_dir, sample_config)
        self._orphan(issues_dir, 1, "loop automation")
        epic = _write_issue(
            issues_dir,
            "epics",
            "P2-EPIC-1-e.md",
            "---\nid: EPIC-1\ntitle: loop automation\nstatus: open\n---\n# EPIC-1: x\n",
        )
        before = epic.read_text()
        self._run(temp_project_dir, "--threshold", "0.4", "--apply", "--json")
        out = json.loads(capsys.readouterr().out)
        assert out["applied"][0]["children_wired"] is False
        assert epic.read_text() == before

    def test_rejected_pair_does_not_stop_later_orphans(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._setup(temp_project_dir, sample_config)
        bad = self._orphan(issues_dir, 1, "loop automation")
        good = self._orphan(issues_dir, 2, "loop automation")
        epic = self._epic(issues_dir, 1, "loop automation")
        epic.write_text(
            epic.read_text().replace("## Children\n\n", "## Children\n- **FEAT-7** — a\nlazy\n")
        )
        # Make FEAT-1 hit a conflicting parent discovered under the lock.
        real = __import__("little_loops.cli.issues.link_epics", fromlist=["x"]).apply_assignment

        def racing(proposal, **kw):  # type: ignore[no-untyped-def]
            if proposal.orphan_id == "FEAT-1":
                bad.write_text(
                    bad.read_text().replace("status: open", "status: open\nparent: EPIC-9")
                )
            return real(proposal, **kw)

        with patch("little_loops.cli.issues.link_epics.apply_assignment", racing):
            code = self._run(temp_project_dir, "--threshold", "0.4", "--apply", "--json")
        out = json.loads(capsys.readouterr().out)

        assert code == 1
        reasons = {r["orphan_id"]: r["reason"] for r in out["rejected"]}
        assert reasons["FEAT-1"] == "conflicting_parent"
        # FEAT-2 hits the lazy-continuation EPIC section and is rejected too, but was still attempted.
        assert reasons["FEAT-2"] == "ambiguous_children_section"
        assert out["applied"] == []
        assert "parent: EPIC-1" not in good.read_text()

    def test_partial_write_orphan_not_reproposed_and_fixer_repairs(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        epics_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._setup(temp_project_dir, sample_config)
        orphan = self._orphan(issues_dir, 1, "loop automation")
        epic = self._epic(issues_dir, 1, "loop automation")
        from little_loops.file_utils import atomic_write

        def flaky(path: Path, content: str, *a: Any, **kw: Any) -> None:
            if path.resolve() == epic.resolve():
                raise OSError("disk full")
            atomic_write(path, content, *a, **kw)

        with patch("little_loops.file_utils.atomic_write", flaky):
            code = self._run(temp_project_dir, "--threshold", "0.4", "--apply", "--json")
        out = json.loads(capsys.readouterr().out)
        assert code == 1 and out["rejected"][0]["reason"] == "write_failed"
        assert "parent: EPIC-1" in orphan.read_text()

        self._run(temp_project_dir, "--threshold", "0.4", "--json")
        assert json.loads(capsys.readouterr().out)["proposals"] == []

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-1", "--fix", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            main_issues()
        capsys.readouterr()
        assert "FEAT-1" in epic.read_text()


class TestOrphanExclusions:
    """BUG-3739: malformed metadata, intentional markers and Children-listed orphans."""

    _SAME = "loop automation workflow tracker"

    def _run(self, temp_project_dir: Path, *cli_args: str) -> int:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "link-epics", *cli_args, "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            return main_issues()

    def _setup(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        orphans: dict[str, str],
        epics: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        """*orphans*: ``FEAT-n`` -> text after the opening fence; *epics*: id -> (status, body)."""
        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        for seeded in [
            *(issues_dir / "bugs").glob("*.md"),
            *(issues_dir / "features").glob("*.md"),
        ]:
            seeded.unlink()  # drop the fixture's sample issues; they are orphans too
        for issue_id, text in orphans.items():
            _write_issue(issues_dir, "features", f"P2-{issue_id}-o.md", text)
        for epic_id, (status, body) in (epics or {}).items():
            _write_issue(
                issues_dir,
                "epics",
                f"P2-{epic_id}-e.md",
                f"---\nid: {epic_id}\ntitle: {self._SAME}\nstatus: {status}\n---\n"
                f"# {epic_id}: {self._SAME}\n\n{body}",
            )

    def _orphan(self, issue_id: str, extra_fm: str = "", after_fence: str = "") -> str:
        return (
            f"---\nid: {issue_id}\ntitle: {self._SAME}\nstatus: open\n{extra_fm}---\n"
            f"{after_fence}# {issue_id}: {self._SAME}\n"
        )

    def _json(self, temp_project_dir: Path, capsys: pytest.CaptureFixture[str], *args: str):
        code = self._run(temp_project_dir, "--threshold", "0", "--json", *args)
        captured = capsys.readouterr()
        return code, json.loads(captured.out), captured.err

    def test_control_orphan_still_proposed_with_zeroed_report(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys
    ) -> None:
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {"FEAT-1": self._orphan("FEAT-1")},
            {"EPIC-1": ("open", "## Children\n")},
        )
        code, out, _ = self._json(temp_project_dir, capsys)
        assert code == 0
        assert [p["orphan_id"] for p in out["proposals"]] == ["FEAT-1"]
        assert out["skipped_malformed_metadata"] == out["skipped_intentional"] == 0
        assert out["skipped_children_listed"] == 0
        assert out["malformed_metadata"] == [] and out["children_listed_drift"] == []

    def test_misplaced_metadata_excluded_without_any_epic_claim_and_never_applied(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys
    ) -> None:
        text = self._orphan("FEAT-1", after_fence="parentless_reason: private text\n\n")
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {"FEAT-1": text},
            {"EPIC-1": ("open", "## Children\n")},
        )
        orphan_path = issues_dir / "features" / "P2-FEAT-1-o.md"
        code, out, _ = self._json(temp_project_dir, capsys, "--apply")
        assert code == 0
        assert out["proposals"] == [] and out["applied"] == []
        assert out["skipped_malformed_metadata"] == 1
        assert out["malformed_metadata"] == [{"orphan_id": "FEAT-1", "keys": ["parentless_reason"]}]
        assert "private text" not in json.dumps(out)
        assert orphan_path.read_text() == text

    @pytest.mark.parametrize(
        ("value", "opts_out"),
        [
            ("Deliberately standalone", True),
            ("'  padded reason  '", True),
            ("''", False),
            ("null", False),
            ("~", False),
            ('"   "', False),
            ("[a, b]", False),
            ("{a: b}", False),
        ],
    )
    def test_parentless_reason_values(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys, value, opts_out
    ) -> None:
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {"FEAT-1": self._orphan("FEAT-1", extra_fm=f"parentless_reason: {value}\n")},
            {"EPIC-1": ("open", "## Children\n")},
        )
        code, out, err = self._json(temp_project_dir, capsys)
        assert code == 0
        assert (out["skipped_intentional"] == 1) is opts_out
        assert (out["proposals"] == []) is opts_out
        warned = "parentless_reason must be a non-empty string" in err
        assert warned is (value in ("[a, b]", "{a: b}"))

    @pytest.mark.parametrize("style", ["- **FEAT-1** — t (open)", "- FEAT-1", "### FEAT-1 — t"])
    def test_non_terminal_epic_claim_excludes_and_reports(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys, style
    ) -> None:
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {"FEAT-1": self._orphan("FEAT-1")},
            {"EPIC-1": ("open", f"## Children\n\n{style}\n")},
        )
        code, out, _ = self._json(temp_project_dir, capsys)
        assert code == 0
        assert out["proposals"] == []
        assert out["skipped_children_listed"] == 1
        assert out["children_listed_drift"] == [
            {
                "orphan_id": "FEAT-1",
                "excluded_reason": "children_listed",
                "epics": [{"epic_id": "EPIC-1", "status": "open", "blocks_proposal": True}],
            }
        ]

    @pytest.mark.parametrize("status", ["done", "cancelled"])
    def test_terminal_epic_claim_reports_but_stays_proposable(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys, status
    ) -> None:
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {"FEAT-1": self._orphan("FEAT-1")},
            {
                "EPIC-1": ("open", "## Children\n"),
                "EPIC-2": (status, "## Children\n\n- **FEAT-1** — t\n"),
            },
        )
        _, out, _ = self._json(temp_project_dir, capsys)
        assert [(p["orphan_id"], p["epic_id"]) for p in out["proposals"]] == [("FEAT-1", "EPIC-1")]
        assert out["skipped_children_listed"] == 0
        assert out["children_listed_drift"] == [
            {
                "orphan_id": "FEAT-1",
                "excluded_reason": None,
                "epics": [{"epic_id": "EPIC-2", "status": status, "blocks_proposal": False}],
            }
        ]

    def test_terminal_claim_stays_proposable_in_synthesize_mode(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys
    ) -> None:
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {"FEAT-1": self._orphan("FEAT-1"), "FEAT-2": self._orphan("FEAT-2")},
            {"EPIC-9": ("cancelled", "## Children\n\n- **FEAT-1** — t\n")},
        )
        code = self._run(temp_project_dir, "--mode", "synthesize", "--threshold", "0.5", "--json")
        out = json.loads(capsys.readouterr().out)
        assert code == 0
        assert out["clusters"][0]["member_ids"] == ["FEAT-1", "FEAT-2"]
        assert out["children_listed_drift"][0]["epics"][0]["blocks_proposal"] is False

    @pytest.mark.parametrize(
        "body",
        [
            "## Children\n\n```markdown\n- **FEAT-1** — fenced example\n```\n",
            "## Children\n\n- **FEAT-1suffix** — prefix token\n",
            "## Children\n\nSee FEAT-1 for background.\n",
            "## Notes\n\n- **FEAT-1** — other section\n",
        ],
    )
    def test_fenced_prose_and_partial_ids_do_not_count(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys, body
    ) -> None:
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {"FEAT-1": self._orphan("FEAT-1")},
            {"EPIC-1": ("open", body)},
        )
        _, out, _ = self._json(temp_project_dir, capsys)
        assert [p["orphan_id"] for p in out["proposals"]] == ["FEAT-1"]
        assert out["children_listed_drift"] == []

    def test_primary_reason_precedence_keeps_secondary_claims(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys
    ) -> None:
        listing = "## Children\n\n- **FEAT-1** — t\n- **FEAT-2** — t\n- **FEAT-3** — t\n"
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {
                "FEAT-1": self._orphan("FEAT-1", after_fence="parent: EPIC-2\n\n"),
                "FEAT-2": self._orphan("FEAT-2", extra_fm="parentless_reason: alone\n"),
                "FEAT-3": self._orphan("FEAT-3"),
            },
            {"EPIC-1": ("open", listing), "EPIC-2": ("done", listing)},
        )
        _, out, _ = self._json(temp_project_dir, capsys)
        assert out["proposals"] == []
        assert (
            out["skipped_malformed_metadata"],
            out["skipped_intentional"],
            out["skipped_children_listed"],
        ) == (1, 1, 1)
        drift = {d["orphan_id"]: d for d in out["children_listed_drift"]}
        assert drift["FEAT-1"]["excluded_reason"] == "malformed_metadata"
        assert drift["FEAT-2"]["excluded_reason"] == "intentional"
        assert drift["FEAT-3"]["excluded_reason"] == "children_listed"
        assert [e["epic_id"] for e in drift["FEAT-3"]["epics"]] == ["EPIC-1", "EPIC-2"]
        assert [d["orphan_id"] for d in out["children_listed_drift"]] == sorted(drift)

    def test_exclusion_runs_before_deep_model_call(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys
    ) -> None:
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {
                "FEAT-1": self._orphan("FEAT-1", extra_fm="parentless_reason: alone\n"),
                "FEAT-2": self._orphan("FEAT-2"),
            },
        )
        with patch("little_loops.cli.issues.link_epics._deep_cluster_call") as call:
            call.return_value = []
            self._run(temp_project_dir, "--mode", "synthesize", "--deep", "--json")
        capsys.readouterr()
        sent = [info.issue_id for info, _ in call.call_args.args[0]]
        assert sent == ["FEAT-2"]

    def test_text_mode_reports_counts_and_claimants(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys
    ) -> None:
        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {"FEAT-1": self._orphan("FEAT-1")},
            {"EPIC-1": ("blocked", "## Children\n\n- **FEAT-1** — t\n")},
        )
        assert self._run(temp_project_dir, "--threshold", "0") == 0
        out = capsys.readouterr().out
        assert (
            "Skipped 1 orphan(s): 0 malformed metadata, 0 intentionally parentless, 1 already"
            in out
        )
        assert "FEAT-1: listed in EPIC-1 (blocked); children_listed" in out
        assert "epic-consistency" in out

    def test_unreadable_epic_is_a_path_specific_error_and_blocks_apply(
        self, temp_project_dir, sample_config, issues_dir, epics_dir, capsys
    ) -> None:
        from pathlib import Path as _P

        self._setup(
            temp_project_dir,
            sample_config,
            issues_dir,
            {"FEAT-1": self._orphan("FEAT-1")},
            {"EPIC-1": ("open", "## Children\n")},
        )
        orphan = issues_dir / "features" / "P2-FEAT-1-o.md"
        real = _P.read_text

        def flaky(self: _P, *a: Any, **k: Any) -> str:
            if self.name == "P2-EPIC-1-e.md":
                raise PermissionError("denied")
            return real(self, *a, **k)

        before = orphan.read_text()
        with patch.object(_P, "read_text", flaky):
            code = self._run(temp_project_dir, "--apply", "--json")
        captured = capsys.readouterr()
        assert code == 1
        assert "P2-EPIC-1-e.md" in captured.err and captured.out == ""
        assert orphan.read_text() == before


class TestClassifyHelpers:
    """BUG-3739: pure helpers."""

    def test_intentional_parentless_values(self) -> None:
        from little_loops.cli.issues.link_epics import intentional_parentless

        assert intentional_parentless({"parentless_reason": "x"})
        for bad in (None, "", "  ", [], ["a"], {}, {"a": 1}, 3):
            assert not intentional_parentless({"parentless_reason": bad})
        assert not intentional_parentless({})
