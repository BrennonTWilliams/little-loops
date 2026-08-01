"""Tests for cli/doctor.py's --full ll-verify-* aggregation (FEAT-2795)."""

from __future__ import annotations

import json
from unittest.mock import patch

from little_loops.cli.doctor import (
    CheckResult,
    _full_check_links_check,
    _full_check_links_data,
    _full_decisions_data,
    _full_des_audit_data,
    _full_design_tokens_data,
    _full_docs_check,
    _full_docs_data,
    _full_kinds_data,
    _full_package_data_data,
    _full_section_data,
    _full_skill_budget_data,
    _full_skill_prose_data,
    _full_skills_data,
    _full_triggers_data,
    _run_full_checks,
)


class TestFullAdapters:
    """Each `_full_*_data()` adapter mocks its underlying verifier callable to fail."""

    def test_docs_reports_full_on_match(self) -> None:
        from little_loops import doc_counts

        with patch.object(
            doc_counts, "verify_documentation", return_value=doc_counts.VerificationResult()
        ):
            data = _full_docs_data()
        assert data["status"] == "full"

    def test_docs_reports_unsupported_on_mismatch(self) -> None:
        from little_loops import doc_counts

        result = doc_counts.VerificationResult()
        result.add_result(
            doc_counts.CountResult(category="skills", actual=1, documented=2, matches=False)
        )
        with patch.object(doc_counts, "verify_documentation", return_value=result):
            data = _full_docs_data()
        assert data["status"] == "unsupported"
        assert "skills" in data["note"]

    def test_docs_surfaces_action_severity_findings(self) -> None:
        from little_loops import doc_counts

        result = doc_counts.VerificationResult()
        result.add_result(
            doc_counts.CountResult(
                category="skills",
                actual=1,
                documented=2,
                matches=False,
                action_severity="route",
                route_owner="ll-verify-docs",
            )
        )
        with patch.object(doc_counts, "verify_documentation", return_value=result):
            data = _full_docs_data()
            findings = _full_docs_check()[0].findings
        assert len(data["findings"]) == 1
        assert data["findings"][0].label == "skills"
        assert data["findings"][0].action_severity == "route"
        assert data["findings"][0].route_owner == "ll-verify-docs"
        assert findings == tuple(data["findings"])

    def test_skill_budget_reports_unsupported_over_budget(self) -> None:
        from little_loops import doc_counts

        result = doc_counts.SkillBudgetResult(
            total_tokens=5000,
            threshold_tokens=2000,
            under_budget=False,
            skill_breakdown=[],
            violations=[],
        )
        with patch.object(doc_counts, "check_skill_budget", return_value=result):
            data = _full_skill_budget_data()
        assert data["status"] == "unsupported"

    def test_skills_reports_unsupported_on_violation(self, tmp_path) -> None:
        from little_loops import doc_counts

        violations = [(tmp_path / "skills" / "big" / "SKILL.md", 600)]
        with patch.object(doc_counts, "check_skill_sizes", return_value=violations):
            data = _full_skills_data()
        assert data["status"] == "unsupported"
        assert "big" in data["note"]

    def test_triggers_reports_informational_when_no_skills_dir(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = _full_triggers_data()
        assert data["status"] == "unsupported"
        assert data["severity"] == "informational"

    def test_triggers_reports_unsupported_on_failure(self, monkeypatch, tmp_path) -> None:
        import little_loops.cli.verify_triggers as verify_triggers_mod

        monkeypatch.chdir(tmp_path)
        (tmp_path / "skills").mkdir()
        with (
            patch.object(
                verify_triggers_mod,
                "_run_validation",
                return_value=(
                    {},
                    [],
                    {
                        "precision_threshold": 0.5,
                        "recall_threshold": 0.5,
                    },
                ),
            ),
            patch.object(verify_triggers_mod, "_any_failures", return_value=True),
        ):
            data = _full_triggers_data()
        assert data["status"] == "unsupported"
        assert data["severity"] == "error"

    def test_triggers_passes_on_fixture_less_tree(self, monkeypatch, tmp_path) -> None:
        """A populated but fixture-less skills tree no longer fails --full (BUG-2879)."""
        monkeypatch.chdir(tmp_path)
        skill = tmp_path / "skills" / "ll-alpha"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: ll-alpha\ndescription: Does something useful\n---\n\n# Alpha\n"
        )
        data = _full_triggers_data()
        assert data["status"] == "full"
        assert data["note"] == "0/1 skill(s) measured"

    def test_decisions_reports_unsupported_on_error(self) -> None:
        import little_loops.cli.verify_decisions as verify_decisions_mod

        with patch.object(verify_decisions_mod, "_run", return_value=(1, "ERROR: boom")):
            data = _full_decisions_data()
        assert data["status"] == "unsupported"
        assert data["note"] == "ERROR: boom"

    def test_package_data_reports_unsupported_on_missing_root(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = _full_package_data_data()
        assert data["status"] == "unsupported"

    def test_package_data_reports_full_when_clean(self) -> None:
        import little_loops.cli.verify_package_data as verify_package_data_mod

        with (
            patch.object(verify_package_data_mod, "run_escape_lint", return_value=[]),
            patch.object(verify_package_data_mod, "run_manifest_check", return_value=[]),
        ):
            data = _full_package_data_data()
        assert data["status"] == "full"

    def test_skill_prose_reports_full_when_clean(self) -> None:
        import little_loops.cli.verify_skill_prose as verify_skill_prose_mod

        with patch.object(verify_skill_prose_mod, "scan_prose", return_value=[]):
            data = _full_skill_prose_data()
        assert data["status"] == "full"

    def test_skill_prose_reports_unsupported_on_findings(self) -> None:
        import little_loops.cli.verify_skill_prose as verify_skill_prose_mod
        from little_loops.cli.verify_skill_prose import ProseFinding

        finding = ProseFinding(
            path=None, line=1, marker="union_find_cluster_merge", owner_cli="ll-issues link-epics"
        )
        with patch.object(verify_skill_prose_mod, "scan_prose", return_value=[finding]):
            data = _full_skill_prose_data()
        assert data["status"] == "unsupported"
        assert "1" in data["note"]

    def test_kinds_reports_unsupported_on_unregistered(self) -> None:
        import little_loops.cli.verify_kinds as verify_kinds_mod

        with patch.object(verify_kinds_mod, "_run", return_value=(1, ["mystery_table"])):
            data = _full_kinds_data()
        assert data["status"] == "unsupported"
        assert "mystery_table" in data["note"]

    def test_design_tokens_reports_informational_when_missing(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = _full_design_tokens_data()
        assert data["status"] == "unsupported"
        assert data["severity"] == "informational"

    def test_des_audit_reports_informational_when_missing(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = _full_des_audit_data()
        assert data["status"] == "unsupported"
        assert data["severity"] == "informational"

    def test_check_links_reports_unsupported_on_broken(self) -> None:
        from little_loops import link_checker

        result = link_checker.LinkCheckResult(broken_links=2)
        with patch.object(link_checker, "check_markdown_links", return_value=result):
            data = _full_check_links_data()
        assert data["status"] == "unsupported"
        assert data["severity"] == "error"
        assert "2" in data["note"]

    def test_check_links_reports_informational_on_unreachable_only(self) -> None:
        """Unreachable (network) links are warn-tier, not error-tier (ENH-2836)."""
        from little_loops import link_checker

        result = link_checker.LinkCheckResult(unreachable_links=3)
        with patch.object(link_checker, "check_markdown_links", return_value=result):
            data = _full_check_links_data()
        assert data["status"] == "unsupported"
        assert data["severity"] == "informational"
        assert "3" in data["note"]

    def test_check_links_reports_informational_on_indeterminate_only(self) -> None:
        """INDETERMINATE (429/401/403/5xx) is warn-tier, not error-tier (ENH-2920)."""
        from little_loops import link_checker

        result = link_checker.LinkCheckResult(indeterminate_links=4)
        with patch.object(link_checker, "check_markdown_links", return_value=result):
            data = _full_check_links_data()
        assert data["status"] == "unsupported"
        assert data["severity"] == "informational"
        assert "4" in data["note"]

    def test_check_links_broken_and_indeterminate_reports_error(self) -> None:
        """Broken links take priority over co-occurring indeterminate ones (ENH-2920)."""
        from little_loops import link_checker

        result = link_checker.LinkCheckResult(broken_links=1, indeterminate_links=4)
        with patch.object(link_checker, "check_markdown_links", return_value=result):
            data = _full_check_links_data()
        assert data["status"] == "unsupported"
        assert data["severity"] == "error"
        assert "1" in data["note"]

    def test_check_links_surfaces_action_severity_findings(self) -> None:
        from little_loops import link_checker

        broken = link_checker.LinkResult(
            url="https://example.com/broken",
            file="README.md",
            line=1,
            status="broken",
            action_severity="mention",
        )
        result = link_checker.LinkCheckResult(broken_links=1, results=[broken])
        with patch.object(link_checker, "check_markdown_links", return_value=result):
            data = _full_check_links_data()
            findings = _full_check_links_check()[0].findings
        assert len(data["findings"]) == 1
        assert data["findings"][0].label == "https://example.com/broken"
        assert data["findings"][0].action_severity == "mention"
        assert findings == tuple(data["findings"])


class TestFullSection:
    """Aggregation and JSON-section behavior."""

    def _patch_check_links(self):
        from little_loops import link_checker

        return patch.object(
            link_checker, "check_markdown_links", return_value=link_checker.LinkCheckResult()
        )

    def test_run_full_checks_returns_check_result_per_verifier(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        with self._patch_check_links():
            results = _run_full_checks()
        assert all(isinstance(r, CheckResult) for r in results)
        names = {r.name for r in results}
        assert names == {
            "full:docs",
            "full:skill_budget",
            "full:skill_prose",
            "full:skills",
            "full:triggers",
            "full:decisions",
            "full:package_data",
            "full:kinds",
            "full:design_tokens",
            "full:des_audit",
            "full:check_links",
            "full:host_map",
        }

    def test_full_section_data_keyed_by_verifier_name(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        with self._patch_check_links():
            section = _full_section_data()
        assert "docs" in section
        assert set(section["docs"]) == {"status", "note", "findings"}


class TestMainDoctorFull:
    """End-to-end `--full` behavior through main_doctor()."""

    def test_full_flag_absent_by_default(self, tmp_path, monkeypatch) -> None:
        from little_loops.cli import doctor
        from little_loops.host_runner import CapabilityReport
        from tests.test_cli_doctor import _capture_print, _json_safe_config, _make_runner

        monkeypatch.chdir(tmp_path)
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
            patch("builtins.print", side_effect=side_effect),
        ):
            doctor.main_doctor()

        data = json.loads("\n".join(lines))
        assert "full" not in data

    def test_full_flag_adds_json_section_with_mocked_failure(self, tmp_path, monkeypatch) -> None:
        from little_loops import link_checker
        from little_loops.cli import doctor
        from little_loops.host_runner import CapabilityReport
        from tests.test_cli_doctor import _capture_print, _json_safe_config, _make_runner

        monkeypatch.chdir(tmp_path)
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-doctor", "--json", "--full"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
            patch.object(
                link_checker, "check_markdown_links", return_value=link_checker.LinkCheckResult()
            ),
            patch.object(
                doctor,
                "_full_kinds_data",
                return_value={"status": "unsupported", "note": "mystery_table"},
            ),
            patch("builtins.print", side_effect=side_effect),
        ):
            exit_code = doctor.main_doctor()

        data = json.loads("\n".join(lines))
        assert "full" in data
        assert data["full"]["kinds"]["status"] == "unsupported"
        assert exit_code == 1
