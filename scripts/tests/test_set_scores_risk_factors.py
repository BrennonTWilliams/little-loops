"""Tests for ll-issues set-scores risk-factor persistence and comparison (ENH-3742)."""

from __future__ import annotations

import io
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from little_loops.cli.issues.set_scores import (
    RiskFactor,
    RiskFactorError,
    clear_scores,
    diff_risk_factors,
    parse_risk_factors,
)
from little_loops.frontmatter import parse_frontmatter, update_frontmatter

SCORES = [
    "--confidence",
    "90",
    "--outcome",
    "70",
    "--score-complexity",
    "10",
    "--score-test-coverage",
    "18",
    "--score-ambiguity",
    "20",
    "--score-change-surface",
    "22",
]


def _factor(fid: str, domain: str = "outcome", criterion: str = "test_coverage", desc: str = "d"):
    return {"id": fid, "domain": domain, "criterion": criterion, "description": desc}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text(
        json.dumps(
            {
                "project": {"name": "t"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                        "enhancements": {
                            "prefix": "ENH",
                            "dir": "enhancements",
                            "action": "improve",
                        },
                    },
                },
            }
        )
    )
    (tmp_path / ".issues" / "bugs").mkdir(parents=True)
    (tmp_path / ".issues" / "enhancements").mkdir(parents=True)
    return tmp_path


def _issue(project: Path, text: str, name: str = "P2-BUG-001-x.md") -> Path:
    path = project / ".issues" / "bugs" / name
    path.write_bytes(text.encode("utf-8"))
    return path


BASIC = "---\nid: BUG-001\nstatus: open\n---\n# BUG-001: X\n\n## Summary\nbody\n"


def _run(
    project: Path,
    *argv: str,
    stdin: str | None = None,
    capsys: pytest.CaptureFixture[str],
    issue: str = "BUG-001",
) -> tuple[int, str, str]:
    from little_loops.cli import main_issues

    args = ["ll-issues", "set-scores", issue, *argv, "--config", str(project)]
    with patch.object(sys, "argv", args):
        if stdin is not None:
            with patch.object(sys, "stdin", io.StringIO(stdin)):
                rc = main_issues()
        else:
            rc = main_issues()
    out = capsys.readouterr()
    return rc, out.out, out.err


def _factors_file(project: Path, factors: Any, name: str = "f.json") -> str:
    p = project / name
    p.write_text(json.dumps(factors))
    return str(p)


class TestParseAndDiff:
    def test_parse_sorts_by_id(self) -> None:
        out = parse_risk_factors(json.dumps([_factor("b-two"), _factor("a-one")]))
        assert [f.id for f in out] == ["a-one", "b-two"]

    def test_empty_array_is_valid(self) -> None:
        assert parse_risk_factors("[]") == []

    @pytest.mark.parametrize(
        "payload",
        [
            "not json",
            "{}",
            json.dumps([_factor("A")]),
            json.dumps([_factor("a_b")]),
            json.dumps([_factor("a.b")]),
            json.dumps([_factor("-a")]),
            json.dumps([_factor("a" * 49)]),
            json.dumps([_factor("a", domain="other")]),
            json.dumps([_factor("a", criterion="Test")]),
            json.dumps([_factor("a", desc="")]),
            json.dumps([_factor("a", desc="   ")]),
            json.dumps([_factor("a", desc="two\nlines")]),
            json.dumps([_factor("a", desc="cr\rhere")]),
            json.dumps([_factor("a", desc="x" * 201)]),
            json.dumps([_factor("a"), _factor("a")]),
            json.dumps([{**_factor("a"), "extra": "x"}]),
            json.dumps([{"id": "a", "domain": "outcome", "criterion": "c"}]),
            json.dumps([{**_factor("a"), "description": 5}]),
            json.dumps([{**_factor("a"), "id": 123}]),
            json.dumps(["a"]),
        ],
    )
    def test_rejects_invalid(self, payload: str) -> None:
        with pytest.raises(RiskFactorError):
            parse_risk_factors(payload)

    def test_accepts_unicode_and_boundary_lengths(self) -> None:
        out = parse_risk_factors(json.dumps([_factor("a" * 48, desc="é" * 200)]))
        assert out[0].description == "é" * 200

    def test_id_with_trailing_newline_rejected(self) -> None:
        with pytest.raises(RiskFactorError):
            parse_risk_factors(json.dumps([_factor("abc\n")]))

    def test_diff_membership_and_changed_fields(self) -> None:
        prev = [
            RiskFactor("keep", "outcome", "c", "same"),
            RiskFactor("gone", "outcome", "c", "g"),
            RiskFactor("edit", "outcome", "c", "old"),
        ]
        cur = [
            RiskFactor("keep", "outcome", "c", "same"),
            RiskFactor("new", "readiness", "c", "n"),
            RiskFactor("edit", "readiness", "c2", "old"),
        ]
        d = diff_risk_factors(prev, cur)
        assert [f.id for f in d.added] == ["new"]
        assert [f.id for f in d.removed] == ["gone"]
        assert d.removed[0].description == "g"  # prior record
        assert [(r.factor.id, r.changed_fields) for r in d.retained] == [
            ("edit", ("domain", "criterion")),
            ("keep", ()),
        ]

    def test_diff_empty_previous_is_not_absent(self) -> None:
        d = diff_risk_factors([], [RiskFactor("a", "outcome", "c", "d")])
        assert [f.id for f in d.added] == ["a"] and not d.removed and not d.retained


class TestWriter:
    def test_records_factors_with_scores_and_json(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, BASIC)
        f = _factors_file(project, [_factor("b-two"), _factor("a-one")])
        rc, out, err = _run(project, *SCORES, "--risk-factors-file", f, "--json", capsys=capsys)
        assert rc == 0 and err == ""
        data = json.loads(out)
        assert data["issue_id"] == "BUG-001"
        rf = data["risk_factors"]
        assert rf["recorded"] is True and rf["baseline"] == "absent"
        assert [x["id"] for x in rf["factors"]] == ["a-one", "b-two"]
        assert rf["added"] is None and rf["removed"] is None and rf["retained"] is None
        fm = yaml.safe_load(issue.read_text().split("---\n")[1])
        assert fm["confidence_score"] == 90
        assert [x["id"] for x in fm["risk_factors"]] == ["a-one", "b-two"]
        assert fm["status"] == "open"
        assert issue.read_text().endswith("# BUG-001: X\n\n## Summary\nbody\n")

    def test_quiet_without_json(self, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _issue(project, BASIC)
        f = _factors_file(project, [])
        rc, out, err = _run(project, *SCORES, "--risk-factors-file", f, capsys=capsys)
        assert (rc, out, err) == (0, "", "")

    def test_stdin_and_alias_and_factor_only(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, BASIC)
        rc, out, _ = _run(
            project,
            "--risk-factors-file",
            "-",
            "-j",
            stdin=json.dumps([_factor("a")]),
            capsys=capsys,
        )
        assert rc == 0
        assert json.loads(out)["risk_factors"]["recorded"] is True
        assert "confidence_score" not in issue.read_text()
        assert "risk_factors:" in issue.read_text()

    def test_rescore_reports_delta_at_fixed_totals(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, BASIC)
        first = _factors_file(
            project, [_factor("page-tests"), _factor("transport"), _factor("submit", desc="s")]
        )
        assert _run(project, *SCORES, "--risk-factors-file", first, capsys=capsys)[0] == 0
        second = _factors_file(
            project,
            [
                _factor("submit", criterion="change_surface", desc="s"),
                _factor("transport"),
                _factor("fresh"),
            ],
            "g.json",
        )
        rc, out, _ = _run(project, *SCORES, "--risk-factors-file", second, "--json", capsys=capsys)
        assert rc == 0
        rf = json.loads(out)["risk_factors"]
        assert rf["baseline"] == "present"
        assert [x["id"] for x in rf["added"]] == ["fresh"]
        assert [x["id"] for x in rf["removed"]] == ["page-tests"]
        assert [(x["id"], x["changed_fields"]) for x in rf["retained"]] == [
            ("submit", ["criterion"]),
            ("transport", []),
        ]
        assert "confidence_score: 90" in issue.read_text()

    def test_identical_assessment_has_no_membership_delta(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _issue(project, BASIC)
        f = _factors_file(project, [_factor("a")])
        _run(project, "--risk-factors-file", f, capsys=capsys)
        rc, out, _ = _run(project, "--risk-factors-file", f, "--json", capsys=capsys)
        rf = json.loads(out)["risk_factors"]
        assert (
            rf["added"] == [] and rf["removed"] == [] and rf["retained"][0]["changed_fields"] == []
        )

    def test_empty_list_is_known_empty_baseline(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _issue(project, BASIC)
        empty = _factors_file(project, [])
        _run(project, "--risk-factors-file", empty, capsys=capsys)
        f = _factors_file(project, [_factor("a")], "g.json")
        rc, out, _ = _run(project, "--risk-factors-file", f, "--json", capsys=capsys)
        rf = json.loads(out)["risk_factors"]
        assert rf["baseline"] == "present"
        assert [x["id"] for x in rf["added"]] == ["a"] and rf["removed"] == []
        # all removed -> empty list persists and reports removal
        rc, out, _ = _run(project, "--risk-factors-file", empty, "--json", capsys=capsys)
        rf = json.loads(out)["risk_factors"]
        assert rf["factors"] == [] and [x["id"] for x in rf["removed"]] == ["a"]

    def test_removed_then_reintroduced_is_added(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _issue(project, BASIC)
        a = _factors_file(project, [_factor("a")])
        empty = _factors_file(project, [], "e.json")
        _run(project, "--risk-factors-file", a, capsys=capsys)
        _run(project, "--risk-factors-file", empty, capsys=capsys)
        rc, out, _ = _run(project, "--risk-factors-file", a, "--json", capsys=capsys)
        assert [x["id"] for x in json.loads(out)["risk_factors"]["added"]] == ["a"]

    def test_omitted_option_preserves_factors_and_reports_presence(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, BASIC)
        rc, out, _ = _run(project, "--outcome", "50", "--json", capsys=capsys)
        assert json.loads(out)["risk_factors"] == {"recorded": False, "baseline": "absent"}
        f = _factors_file(project, [_factor("a")])
        _run(project, "--risk-factors-file", f, capsys=capsys)
        rc, out, _ = _run(project, "--outcome", "51", "--json", capsys=capsys)
        assert json.loads(out)["risk_factors"] == {"recorded": False, "baseline": "present"}
        assert "id: a" in issue.read_text() and "outcome_confidence: 51" in issue.read_text()

    def test_no_update_json_warns_and_writes_nothing(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, BASIC)
        before = issue.read_bytes()
        rc, out, err = _run(project, "--json", capsys=capsys)
        assert rc == 0 and "nothing to write" in err
        assert json.loads(out)["risk_factors"] == {"recorded": False, "baseline": "absent"}
        assert issue.read_bytes() == before

    def test_malformed_baseline_replaced_with_warning(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(
            project, "---\nid: BUG-001\nrisk_factors:\n- id: 123\n  domain: outcome\n---\n# X\n"
        )
        f = _factors_file(project, [_factor("a")])
        rc, out, err = _run(project, "--risk-factors-file", f, "--json", capsys=capsys)
        assert rc == 0
        assert err.strip() == "Warning: stored risk_factors baseline malformed; replaced"
        rf = json.loads(out)["risk_factors"]
        assert rf["baseline"] == "malformed" and rf["added"] is None
        assert "id: a" in issue.read_text()

    @pytest.mark.parametrize("bad_id", ["123", "yes", "null"])
    def test_unquoted_nonstring_ids_are_malformed(
        self, project: Path, capsys: pytest.CaptureFixture[str], bad_id: str
    ) -> None:
        _issue(
            project,
            "---\nid: BUG-001\nrisk_factors:\n"
            f"- id: {bad_id}\n  domain: outcome\n  criterion: c\n  description: d\n---\n# X\n",
        )
        f = _factors_file(project, [])
        _, out, _ = _run(project, "--risk-factors-file", f, "--json", capsys=capsys)
        assert json.loads(out)["risk_factors"]["baseline"] == "malformed"

    @pytest.mark.parametrize("fid", ["123", "yes", "null", "true"])
    def test_writer_created_slug_ids_stay_strings(
        self, project: Path, capsys: pytest.CaptureFixture[str], fid: str
    ) -> None:
        issue = _issue(project, BASIC)
        f = _factors_file(project, [_factor(fid)])
        assert _run(project, "--risk-factors-file", f, capsys=capsys)[0] == 0
        # later ordinary frontmatter update must keep the string
        issue.write_text(update_frontmatter(issue.read_text(), {"status": "in_progress"}))
        g = _factors_file(project, [_factor(fid)], "g.json")
        _, out, _ = _run(project, "--risk-factors-file", g, "--json", capsys=capsys)
        rf = json.loads(out)["risk_factors"]
        assert rf["baseline"] == "present" and rf["added"] == [] and rf["removed"] == []

    def test_unicode_description_round_trips(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _issue(project, BASIC)
        desc = "Ünïcode — résumé 日本語 " + "w" * 150
        f = _factors_file(project, [_factor("a", desc=desc)])
        _run(project, "--risk-factors-file", f, capsys=capsys)
        _, out, _ = _run(project, "--risk-factors-file", f, "--json", capsys=capsys)
        rf = json.loads(out)["risk_factors"]
        assert (
            rf["retained"][0]["description"] == desc and rf["retained"][0]["changed_fields"] == []
        )

    def test_description_with_yaml_specials_round_trips(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _issue(project, BASIC)
        desc = ": # - 'quoted' \"double\"  trailing  "
        f = _factors_file(project, [_factor("a", desc=desc)])
        _run(project, "--risk-factors-file", f, capsys=capsys)
        _, out, _ = _run(project, "--risk-factors-file", f, "--json", capsys=capsys)
        assert json.loads(out)["risk_factors"]["retained"][0]["changed_fields"] == []

    def test_file_mode_preserved(self, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        issue = _issue(project, BASIC)
        os.chmod(issue, 0o664)
        f = _factors_file(project, [_factor("a")])
        _run(project, *SCORES, "--risk-factors-file", f, capsys=capsys)
        assert stat.S_IMODE(issue.stat().st_mode) == 0o664

    def test_first_mapping_without_id_supported(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, "---\nstatus: open\n---\n# BUG-001: X\n")
        f = _factors_file(project, [_factor("a")])
        rc, out, _ = _run(project, "--risk-factors-file", f, "--json", capsys=capsys)
        assert rc == 0 and json.loads(out)["issue_id"] == "BUG-001"
        assert parse_frontmatter(issue.read_text())["status"] == "open"

    def test_no_frontmatter_prepends_and_baseline_absent(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, "# BUG-001: X\n\nbody\n")
        f = _factors_file(project, [_factor("a")])
        rc, out, _ = _run(project, *SCORES, "--risk-factors-file", f, "--json", capsys=capsys)
        assert rc == 0 and json.loads(out)["risk_factors"]["baseline"] == "absent"
        assert issue.read_text().startswith("---\n")

    def test_canonical_block_behind_score_block(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(
            project,
            "---\nconfidence_score: 5\n---\n---\nid: BUG-001\nstatus: open\n---\n# BUG-001: X\n",
        )
        f = _factors_file(project, [_factor("a")])
        rc, _, _ = _run(project, "--risk-factors-file", f, capsys=capsys)
        assert rc == 0
        text = issue.read_text()
        assert text.index("risk_factors:") > text.index("id: BUG-001")

    @pytest.mark.parametrize("ident", ["001", "P2-BUG-001", "BUG-001", "ENH-001"])
    def test_resolved_identity_is_full_id(
        self, project: Path, capsys: pytest.CaptureFixture[str], ident: str
    ) -> None:
        _issue(project, "---\nstatus: open\n---\n# BUG-001: X\n")
        rc, out, _ = _run(project, "--outcome", "1", "--json", capsys=capsys, issue=ident)
        # A stale type prefix resolves by numeric ID; the JSON echoes the resolved file's ID.
        assert rc == 0 and json.loads(out)["issue_id"] == "BUG-001"


class TestFailures:
    @pytest.mark.parametrize(
        "payload",
        ["{", '{"a":1}', json.dumps([_factor("A")]), json.dumps([_factor("a"), _factor("a")])],
    )
    def test_invalid_input_writes_nothing(
        self, project: Path, capsys: pytest.CaptureFixture[str], payload: str
    ) -> None:
        issue = _issue(project, BASIC.replace("\n", "\r\n"))
        before = issue.read_bytes()
        p = project / "bad.json"
        p.write_text(payload)
        rc, out, err = _run(
            project, *SCORES, "--risk-factors-file", str(p), "--json", capsys=capsys
        )
        assert rc == 1 and out == ""
        assert err.startswith("Error: invalid risk factors:")
        assert issue.read_bytes() == before

    def test_missing_file_uses_input_prefix(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, BASIC)
        before = issue.read_bytes()
        rc, out, err = _run(
            project, *SCORES, "--risk-factors-file", str(project / "nope.json"), capsys=capsys
        )
        assert rc == 1 and err.startswith("Error: invalid risk factors:")
        assert issue.read_bytes() == before

    def test_stdin_invalid_utf8_free_empty_input_rejected(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _issue(project, BASIC)
        rc, _, err = _run(project, "--risk-factors-file", "-", stdin="", capsys=capsys)
        assert rc == 1 and err.startswith("Error: invalid risk factors:")

    def test_clear_with_factor_option_does_not_read_stdin(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, BASIC)
        before = issue.read_bytes()
        sentinel = io.StringIO("[]")
        with patch.object(sys, "stdin", sentinel):
            from little_loops.cli import main_issues

            with patch.object(
                sys,
                "argv",
                [
                    "ll-issues",
                    "set-scores",
                    "BUG-001",
                    "--clear",
                    "--risk-factors-file",
                    "-",
                    "--config",
                    str(project),
                ],
            ):
                rc = main_issues()
        err = capsys.readouterr().err
        assert rc == 1 and "invalid risk factors" not in err and "--clear" in err
        assert sentinel.tell() == 0
        assert issue.read_bytes() == before

    @pytest.mark.parametrize(
        "text",
        [
            "---\nid: BUG-001\nstatus: [unclosed\n---\n# X\n",
            "---\n- a\n- b\n---\n# X\n",
            "---\nid: BUG-001\nstatus: open\n# never closed\n",
        ],
    )
    def test_unsafe_target_is_operational_error(
        self, project: Path, capsys: pytest.CaptureFixture[str], text: str
    ) -> None:
        issue = _issue(project, text.replace("\n", "\r\n"))
        before = issue.read_bytes()
        f = _factors_file(project, [_factor("a")])
        rc, out, err = _run(project, *SCORES, "--risk-factors-file", f, "--json", capsys=capsys)
        assert rc == 1 and out == ""
        assert "invalid risk factors" not in err and "replaced" not in err
        assert issue.read_bytes() == before

    def test_failed_write_does_not_claim_replacement(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, "---\nid: BUG-001\nrisk_factors: nonsense\n---\n# X\n")
        before = issue.read_bytes()
        f = _factors_file(project, [_factor("a")])
        with patch("little_loops.file_utils.atomic_write", side_effect=OSError("disk full")):
            rc, out, err = _run(project, *SCORES, "--risk-factors-file", f, "--json", capsys=capsys)
        assert rc == 1 and out == "" and "malformed" not in err and "disk full" in err
        assert issue.read_bytes() == before

    def test_lock_timeout_is_operational_error(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, BASIC)
        before = issue.read_bytes()
        f = _factors_file(project, [_factor("a")])
        with patch("little_loops.file_utils.acquire_lock", side_effect=TimeoutError("busy")):
            rc, out, err = _run(project, *SCORES, "--risk-factors-file", f, capsys=capsys)
        assert rc == 1 and "busy" in err and "invalid risk factors" not in err
        assert issue.read_bytes() == before

    def test_unresolvable_issue(self, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = _factors_file(project, [])
        rc, out, err = _run(project, "--risk-factors-file", f, capsys=capsys, issue="BUG-999")
        assert rc == 1 and "not found" in err and "invalid risk factors" not in err

    def test_argparse_usage_error_keeps_exit_2(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _issue(project, BASIC)
        with pytest.raises(SystemExit) as exc:
            _run(project, "--confidence", "x", capsys=capsys)
        assert exc.value.code == 2


class TestClearPreservesFactors:
    def test_clear_keeps_valid_and_invalid_baselines(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(project, BASIC)
        f = _factors_file(project, [_factor("a")])
        _run(project, *SCORES, "--risk-factors-file", f, capsys=capsys)
        rc, out, _ = _run(project, "--clear", "--json", capsys=capsys)
        assert rc == 0
        data = json.loads(out)
        assert data["cleared"] is True and data["risk_factors"]["baseline"] == "present"
        text = issue.read_text()
        assert "confidence_score" not in text and "id: a" in text
        # re-score after clear still compares against the retained baseline
        _, out, _ = _run(project, "--risk-factors-file", f, "--json", capsys=capsys)
        assert json.loads(out)["risk_factors"]["baseline"] == "present"

    def test_clear_keeps_malformed_baseline(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issue = _issue(
            project,
            "---\nid: BUG-001\nconfidence_score: 5\nrisk_factors:\n- just a string\n---\n# X\n",
        )
        assert _run(project, "--clear", capsys=capsys)[0] == 0
        assert "just a string" in issue.read_text()
        assert "confidence_score" not in issue.read_text()

    def test_helper_clear_uses_configured_base_dir_lock(self, tmp_path: Path) -> None:
        from little_loops.file_utils import issue_lock_path

        issue = tmp_path / "tickets" / "bugs" / "P2-BUG-001-x.md"
        issue.parent.mkdir(parents=True)
        issue.write_text("---\nid: BUG-001\nconfidence_score: 5\n---\n# X\n")
        seen: list[Path] = []
        from little_loops import file_utils

        original = file_utils.acquire_lock

        def spy(path, timeout=10.0):  # noqa: ANN001
            seen.append(Path(path))
            return original(path, timeout)

        with patch("little_loops.file_utils.acquire_lock", side_effect=spy):
            assert clear_scores(issue, base_dir="tickets") is True
        assert seen == [issue_lock_path(issue, "tickets")]
        assert seen[0].parent.name == "tickets"
