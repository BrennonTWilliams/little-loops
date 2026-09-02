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
