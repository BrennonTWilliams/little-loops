"""BUG-3695: DIRECTIVE_DRIFT repair via ``reconcile-issue --from-verify-evidence``.

Two layers:

* **Real-child FSM tests** run the REAL builtin ``refine-to-ready-issue.yaml`` as
  the root loop (``tests.autodev_harness.run_refine_to_ready``): shell states run
  as real bash against a throwaway git project, slash commands are answered by
  scripted file effects. They prove **routing and the evidence lifecycle only** —
  scripted effects are not model behavior, so they do not prove the model repairs
  drift correctly or that a repair converges (that is the live-evaluation
  follow-up), and a green manual-phrase probe does not prove coverage or quality.
* **Prose / pin tests** slice the exact command and loop sections the contract
  lives in.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.cli.issues.check_acceptance_criteria import _find_manual_criteria
from tests.autodev_harness import (
    Effects,
    RefineResult,
    Scenario,
    SlashResponse,
    issue_path,
    read_issue_frontmatter,
    run_refine_to_ready,
)

ROOT = Path(__file__).parent.parent.parent
LOOPS = ROOT / "scripts" / "little_loops" / "loops"
RECONCILE_CMD = ROOT / "commands" / "reconcile-issue.md"
VERIFY_CMD = ROOT / "commands" / "verify-issues.md"

FLAG = "--from-verify-evidence"
AC_EVIDENCE = (
    "Acceptance Criteria: 'no AC covers the ll-doctor rebuild-pending surface' -> "
    "add an AC stating the expected notice and how it is verified"
)
FIXTURE_EVIDENCE = (
    "Implementation Steps: 'test mock returns one value for two calls' -> "
    "add a step updating the mock to a side_effect list"
)
NEW_AC = (
    "- [ ] `ll-doctor` prints a rebuild-pending notice, verified by `ll-doctor` after a reset\n"
)
NEW_STEP = "- Update the mock in the session-store test to a `side_effect` list.\n"


def _drift(evidence: str) -> SlashResponse:
    return SlashResponse(
        effects=Effects(
            frontmatter={"verify_verdict": "DIRECTIVE_DRIFT", "verify_evidence": evidence}
        )
    )


VALID = SlashResponse(effects=Effects(frontmatter={"verify_verdict": "VALID"}))
CONFIDENCE = SlashResponse(effects=Effects(scores=(95, 80)))


def _scenario(verify: tuple[SlashResponse, ...], reconcile: SlashResponse) -> Scenario:
    return Scenario(
        name="bug3695",
        context={"input": "ENH-9001"},
        slash={
            "verify-issues": verify,
            "reconcile-issue": (reconcile,),
            "confidence-check": (CONFIDENCE,),
        },
    )


class TestRealChildRepairRouting:
    """Real refine-to-ready-issue: drift -> flagged reconcile -> re-verify -> done."""

    @pytest.mark.parametrize(
        ("evidence", "effect"),
        [(AC_EVIDENCE, NEW_AC), (FIXTURE_EVIDENCE, NEW_STEP)],
        ids=["ac-only-drift", "fixture-only-drift"],
    )
    def test_drift_repaired_within_one_reconcile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, evidence: str, effect: str
    ) -> None:
        r = run_refine_to_ready(
            _scenario(
                (_drift(evidence), VALID),
                SlashResponse(effects=Effects(body_append=effect)),
            ),
            tmp_path,
            monkeypatch,
        )
        assert r.terminated_by == "terminal" and r.final_state == "done"
        p = r.path
        # exactly one reconcile attempt, with the actual dispatched state order
        assert p.count("reconcile_issue") == 1
        i = p.index("reconcile_issue")
        assert p[i - 2 : i + 6] == [
            "route_pre_score_obligation",
            "check_reconcile_limit",
            "reconcile_issue",
            "normalize_structure",
            "clear_verify_verdict",
            "verify_issue",
            "route_pre_score_obligation",
            "confidence_check",
        ]
        assert "record_gate_unmet" not in p
        # the dispatched action carries the explicit flag
        assert r.actions["reconcile_issue"] == [f"/ll:reconcile-issue ENH-9001 {FLAG}"]
        # evidence lifecycle: the normal clear removed it before the fresh verify
        fm = read_issue_frontmatter(r.project, "ENH-9001")
        assert fm["verify_verdict"] == "VALID"
        assert "verify_evidence" not in fm

    def test_repaired_checkbox_ac_passes_manual_phrase_probe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The repaired fixture's checkbox ACs clear the downstream manual-phrase
        probe (necessary compatibility only — not proof of coverage or quality)."""
        r = run_refine_to_ready(
            _scenario(
                (_drift(AC_EVIDENCE), VALID),
                SlashResponse(effects=Effects(body_append=NEW_AC)),
            ),
            tmp_path,
            monkeypatch,
        )
        body = issue_path(r.project, "ENH-9001").read_text()
        assert "rebuild-pending notice" in body
        assert _find_manual_criteria(body) == []


class TestRealChildExhaustion:
    """An ineffective repair keeps the existing budget and ends GATE_UNMET."""

    def _run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RefineResult:
        return run_refine_to_ready(
            _scenario((_drift(AC_EVIDENCE),), SlashResponse()),  # sticky drift, no-op repair
            tmp_path,
            monkeypatch,
        )

    def test_no_extra_budget_and_gate_unmet(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        r = self._run(tmp_path, monkeypatch)
        assert r.path.count("reconcile_issue") == 1, "target: 2 allows ONE reconcile per run"
        assert "record_gate_unmet" in r.path
        assert r.final_state == "failed"
        # second drift fell through to the refine budget, never a second reconcile
        assert "check_gate_refine_limit" in r.path

    def test_non_convergence_is_distinguishable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        r = self._run(tmp_path, monkeypatch)
        out = r.outputs["record_gate_unmet"][-1]
        assert "[GATE_UNMET]" in out
        assert "[GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE]" in out
        record = next(r.run_dir.rglob("ENH-9001.json")).read_text()
        assert "directive_drift_nonconvergence" in record
        # no new legacy_class: the closed class set still records gate_unmet
        assert "gate_unmet" in record


class TestSharedAcceptanceCriteriaRoute:
    """``ACCEPTANCE_CRITERIA`` shares ``reconcile_issue`` (and so the flag). A stale
    leftover ``verify_evidence`` there must not be eligible: the command's gate is
    flag + ``verify_verdict == DIRECTIVE_DRIFT`` + evidence, and the verdict is not
    drift on this route (the model-side gate itself is pinned in the contract tests)."""

    def test_stale_evidence_with_valid_verdict_reaches_flagged_reconcile_ineligible(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, object] = {}

        def _capture(hctx: object, target: str) -> None:
            seen.update(read_issue_frontmatter(hctx.project, target))  # type: ignore[attr-defined]

        manual = "\n- [ ] manually verify the notice looks right\n"
        fixed = "- [ ] `ll-doctor` prints a notice, verified by `ll-doctor` after a reset\n"
        stale_valid = SlashResponse(
            effects=Effects(
                frontmatter={"verify_verdict": "VALID", "verify_evidence": "stale: 'x' -> y"},
                body_append=manual,
            )
        )
        sc = Scenario(
            name="bug3695-ac-route",
            context={"input": "ENH-9001"},
            slash={
                "verify-issues": (stale_valid,),
                "reconcile-issue": (
                    SlashResponse(effects=Effects(body_append=fixed), callback=_capture),
                ),
                "confidence-check": (CONFIDENCE,),
            },
        )
        r = run_refine_to_ready(sc, tmp_path, monkeypatch)
        assert "check_reconcile_limit" in r.path and "reconcile_issue" in r.path
        assert r.actions["reconcile_issue"] == [f"/ll:reconcile-issue ENH-9001 {FLAG}"]
        # at the moment the flagged reconcile ran, the verdict was not drift
        assert seen["verify_verdict"] == "VALID"
        assert seen["verify_evidence"] == "stale: 'x' -> y"


class TestRecordGateUnmetSignalIsScoped:
    """The non-convergence line fires only after a flagged reconcile AND a still-drift verdict."""

    @staticmethod
    def _run(tmp_path: Path, attempts: str | None, drift: bool) -> tuple[str, list[str]]:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        log = tmp_path / "calls.log"
        fake = bin_dir / "ll-issues"
        fake.write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> "{log}"\n'
            f'if [ "$1" = check-verify-verdict ]; then exit {0 if drift else 1}; fi\n'
            "exit 0\n"
        )
        fake.chmod(0o755)
        if attempts is not None:
            (tmp_path / "refine-to-ready-reconcile-attempts").write_text(attempts)
        action = yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())["states"][
            "record_gate_unmet"
        ]["action"]
        script = action.replace("${context.run_dir}", str(tmp_path)).replace(
            "${captured.issue_id.output:shell}", "ENH-9800"
        )
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
        proc = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        calls = log.read_text().splitlines() if log.exists() else []
        return proc.stdout, calls

    def test_fires_after_reconcile_with_drift(self, tmp_path: Path) -> None:
        out, calls = self._run(tmp_path, "2", drift=True)
        assert "DIRECTIVE_DRIFT_NON_CONVERGENCE" in out
        assert any("--evidence-refs directive_drift_nonconvergence" in c for c in calls)

    def test_silent_when_never_reconciled(self, tmp_path: Path) -> None:
        out, calls = self._run(tmp_path, "0", drift=True)
        assert "NON_CONVERGENCE" not in out
        assert not any("directive_drift_nonconvergence" in c for c in calls)

    def test_silent_when_verdict_not_drift(self, tmp_path: Path) -> None:
        out, calls = self._run(tmp_path, "2", drift=False)
        assert "NON_CONVERGENCE" not in out
        assert not any("directive_drift_nonconvergence" in c for c in calls)

    def test_silent_when_counter_file_missing(self, tmp_path: Path) -> None:
        out, _ = self._run(tmp_path, None, drift=True)
        assert "NON_CONVERGENCE" not in out
        assert "[GATE_UNMET]" in out


class TestFlagReachesOnlyReconcileIssue:
    def _data(self) -> dict:
        return yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())

    def test_reconcile_issue_alone_has_flag(self) -> None:
        states = self._data()["states"]
        assert states["reconcile_issue"]["action"].endswith(f" {FLAG}")
        flagged = [n for n, s in states.items() if FLAG in str(s.get("action", ""))]
        assert flagged == ["reconcile_issue"]
        assert FLAG not in states["reconcile_revision"]["action"]

    def test_prepare_issue_run_reconcile_has_no_flag(self) -> None:
        text = (LOOPS / "prepare-issue.yaml").read_text()
        assert FLAG not in yaml.safe_load(text)["states"]["run_reconcile"]["action"]
        assert FLAG not in text

    def test_route_table_budget_and_step_cap_unchanged(self) -> None:
        data = self._data()
        st = data["states"]
        route = st["route_pre_score_obligation"]["route"]
        assert route["VERIFY:DIRECTIVE_DRIFT"] == "check_reconcile_limit"
        assert route["ACCEPTANCE_CRITERIA"] == "check_reconcile_limit"
        limit = st["check_reconcile_limit"]
        assert limit["evaluate"]["target"] == 2
        assert limit["on_yes"] == "reconcile_issue"
        assert limit["on_no"] == "check_gate_refine_limit"
        assert st["reconcile_issue"]["next"] == "normalize_structure"
        assert data["max_steps"] == 113


def _slice(text: str, start: str, end: str) -> str:
    a = text.index(start)
    return text[a : text.index(end, a)]


class TestReconcileFlagContract:
    def _contract(self) -> str:
        text = RECONCILE_CMD.read_text()
        return " ".join(_slice(text, "## Contract (read this first", "\n## Process").split())

    def test_flag_documented_and_parsed(self) -> None:
        text = RECONCILE_CMD.read_text()
        parse = _slice(text, "### 0. Parse Flags", "### 1. Find Issue File")
        assert "FROM_VERIFY_EVIDENCE=false" in parse and FLAG in parse
        assert FLAG in text.split("---", 2)[1], "flag must be in the frontmatter argument docs"
        assert FLAG in _slice(text, "## Arguments", "## Examples")

    def test_eligibility_requires_flag_verdict_and_evidence(self) -> None:
        c = self._contract()
        assert "ALL of" in c
        assert "the flag is passed" in c
        assert "`verify_verdict` is `DIRECTIVE_DRIFT`" in c
        assert "`verify_evidence` is nonempty" in c
        assert "never inferred from frontmatter" in c
        assert "`--check` stays read-only" in c

    def test_additions_scope_and_boundaries(self) -> None:
        c = self._contract()
        assert "MAY add or rewrite Acceptance Criteria and Implementation Steps" in c
        assert "Never add new Integration Map entries" in c
        assert "entailed by the selected mechanism" in c
        assert "PROPOSAL_UNSOUND" in c
        assert "Fixture/mock invalidation drift → a concrete Implementation Step" in c
        # the ordinary rule still binds outside the extension
        assert "do not invent new requirements" in " ".join(RECONCILE_CMD.read_text().split())

    def test_output_reports_additions(self) -> None:
        out = _slice(RECONCILE_CMD.read_text(), "## Output Format", "**Correction category**")
        assert "Implementation Steps: [rewritten | added | unchanged]" in out
        assert "Acceptance Criteria: [rewritten | added | unchanged]" in out


class TestVerifyIssuesB6AndPersistence:
    def _text(self) -> str:
        return " ".join(VERIFY_CMD.read_text().split())

    def test_b6_role_table_and_complete_enumeration(self) -> None:
        t = self._text()
        assert "walk **every actual Integration Map entry**" in t
        for role in (
            "Observable behavior, public API or compatibility contract change",
            "Required test/mock/fixture update or fixture invalidation",
            "Context-only existing caller, unchanged helper, Similar Pattern",
        ):
            assert role in t
        assert "`covered`, `uncovered` or `not applicable`" in t
        assert "coverage is not one AC per filename" in t
        assert "Collect **all** uncovered applicable points" in t

    def test_drift_branch_persists_verdict_and_evidence_together(self) -> None:
        """Slice the DIRECTIVE_DRIFT bullet itself — a generic ``verify_evidence:``
        substring from another verdict branch must not satisfy this."""
        body = VERIFY_CMD.read_text()
        start = body.index("- `DIRECTIVE_DRIFT` verdict (BUG-3574, check B6)")
        end = body.index("- `CLAIMS_OUTDATED` verdict (BUG-3637)", start)
        branch = " ".join(body[start:end].split())
        assert "verify_verdict: DIRECTIVE_DRIFT" in branch
        assert "same frontmatter update" in branch
        assert "complete current" in branch
        assert "replace any prior value, never append" in branch
        assert "double-quoted YAML scalar" in branch
        assert "Do not truncate" in branch
        assert "Frontmatter only under `--check`" in branch

    def test_remedy_row_names_flagged_reconcile(self) -> None:
        row = next(
            ln for ln in VERIFY_CMD.read_text().splitlines() if ln.startswith("| DIRECTIVE_DRIFT |")
        )
        assert f"reconcile-issue {FLAG}" in row
