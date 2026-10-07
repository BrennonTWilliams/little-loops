"""BUG-3763: decision-derived Program Design / Impact drift repair and exhaustion guard.

* **Real-child FSM tests** run the REAL builtin ``refine-to-ready-issue.yaml``
  (``tests.autodev_harness.run_refine_to_ready``). Scripted slash effects prove
  **routing only** — not that a model rewrites Program Design/Impact correctly
  (that is an opt-in live evaluation outside pytest).
* **Guard matrix** runs the real ``check_residual_decision_drift`` shell action
  against throwaway issue files.
* **Pin tests** slice the command contract the repair lives in.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import little_loops
from tests.autodev_harness import (
    Effects,
    RefineResult,
    Scenario,
    SlashResponse,
    read_issue_frontmatter,
    run_refine_to_ready,
)

ROOT = Path(__file__).parent.parent.parent
LOOPS = ROOT / "scripts" / "little_loops" / "loops"
RECONCILE_CMD = ROOT / "commands" / "reconcile-issue.md"
SKILL_BRIDGE = ROOT / "skills" / "ll-reconcile-issue" / "SKILL.md"

PD_EVIDENCE = (
    "Program Design: 'Signatures still describe the channel column and migration' -> "
    "rewrite to predicates on existing columns per the selected Option B"
)
IMPACT_EVIDENCE = (
    "Impact: 'Effort/Risk still prices the migration' -> reprice for Option B, no migration"
)
AC_EVIDENCE = (
    "Acceptance Criteria: 'no AC covers the notice' -> add an AC stating the expected notice"
)
PD_EDIT = "\n<!-- program design rewritten to Option B -->\n"


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
        name="bug3763",
        context={"input": "ENH-9001"},
        slash={
            "verify-issues": verify,
            "reconcile-issue": (reconcile,),
            "confidence-check": (CONFIDENCE,),
        },
    )


def _refine_count(r: RefineResult) -> str:
    f = r.run_dir / "refine-to-ready-refine-count"
    return f.read_text().strip() if f.exists() else "0"


class TestRealChildDecisionDriftRouting:
    def test_repaired_within_one_reconcile_without_additive_retry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        r = run_refine_to_ready(
            _scenario(
                (_drift(PD_EVIDENCE), VALID), SlashResponse(effects=Effects(body_append=PD_EDIT))
            ),
            tmp_path,
            monkeypatch,
        )
        assert r.terminated_by == "terminal" and r.final_state == "done"
        assert r.path.count("reconcile_issue") == 1
        assert "record_gate_unmet" not in r.path
        assert "refine_followup" not in r.path
        assert _refine_count(r) == "0", "the additive retry counter is never spent"
        fm = read_issue_frontmatter(r.project, "ENH-9001")
        assert fm["verify_verdict"] == "VALID" and "verify_evidence" not in fm

    @pytest.mark.parametrize("evidence", [PD_EVIDENCE, IMPACT_EVIDENCE], ids=["design", "impact"])
    def test_persistent_design_drift_fails_without_additive_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, evidence: str
    ) -> None:
        r = run_refine_to_ready(
            _scenario((_drift(evidence),), SlashResponse()),  # sticky drift, no-op reconcile
            tmp_path,
            monkeypatch,
        )
        assert r.final_state == "failed"
        assert r.path.count("reconcile_issue") == 1
        i = r.path.index("check_residual_decision_drift")
        assert r.path[i - 1] == "check_reconcile_limit"
        assert r.path[i + 1] == "record_gate_unmet"
        for forbidden in ("check_gate_refine_limit", "refine_followup", "breakdown_issue"):
            assert forbidden not in r.path
        assert _refine_count(r) == "0"
        out = r.outputs["record_gate_unmet"][-1]
        assert "[GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE]" in out
        record = next(r.run_dir.rglob("ENH-9001.json")).read_text()
        assert "directive_drift_nonconvergence" in record and "gate_unmet" in record

    def test_ordinary_ac_drift_keeps_additive_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        r = run_refine_to_ready(
            _scenario((_drift(AC_EVIDENCE),), SlashResponse()), tmp_path, monkeypatch
        )
        i = r.path.index("check_residual_decision_drift")
        assert r.path[i + 1] == "check_gate_refine_limit"
        assert r.path.count("reconcile_issue") == 1

    def test_spent_reconcile_budget_then_design_drift_fails_explicitly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An earlier AC-route reconcile spent the budget; design drift found later
        must not grant a second repair or reset the counter."""
        sc = Scenario(
            name="bug3763-spent",
            context={"input": "ENH-9001"},
            slash={
                "verify-issues": (VALID, _drift(PD_EVIDENCE)),
                "reconcile-issue": (SlashResponse(),),
                "confidence-check": (CONFIDENCE,),
            },
            body=(
                "\n## Summary\n\nx\n\n## Current Behavior\n\nx\n\n## Expected Behavior\n\nx\n\n"
                "## Acceptance Criteria\n\n- [ ] manually verify the notice looks right\n"
            ),
        )
        r = run_refine_to_ready(sc, tmp_path, monkeypatch)
        assert r.path.count("reconcile_issue") == 1
        if "check_residual_decision_drift" in r.path:
            assert "refine_followup" not in r.path[r.path.index("check_residual_decision_drift") :]
        counter = (r.run_dir / "refine-to-ready-reconcile-attempts").read_text().strip()
        assert counter.isdigit() and int(counter) >= 2, "counter was not reset"


class TestResidualGuardMatrix:
    """Run the real guard action: exit 0 match, 1 no-match, 2+ diagnostic."""

    @staticmethod
    def _run(
        tmp_path: Path,
        evidence_line: str | None,
        probe_rc: int = 0,
        path_rc: int = 0,
    ) -> tuple[int, str, Path]:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        issue = tmp_path / "ENH-9800.md"
        fm = "---\nid: ENH-9800\nverify_verdict: DIRECTIVE_DRIFT\n"
        if evidence_line is not None:
            fm += evidence_line + "\n"
        issue.write_text(fm + "---\n\nbody\n")
        fake = bin_dir / "ll-issues"
        fake.write_text(
            "#!/bin/sh\n"
            f'if [ "$1" = check-verify-verdict ]; then exit {probe_rc}; fi\n'
            f'if [ "$1" = path ]; then [ {path_rc} -eq 0 ] && echo "{issue}"; exit {path_rc}; fi\n'
            "exit 0\n"
        )
        fake.chmod(0o755)
        py = bin_dir / "python3"
        py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        py.chmod(0o755)
        action = yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())["states"][
            "check_residual_decision_drift"
        ]["action"]
        script = action.replace("${context.run_dir}", str(tmp_path)).replace(
            "${captured.issue_id.output:shell}", "ENH-9800"
        )
        src = str(Path(little_loops.__file__).resolve().parent.parent)
        env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "PYTHONPATH": src,
        }
        proc = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
        return proc.returncode, proc.stderr, tmp_path / "residual-decision-drift-diagnostic"

    @staticmethod
    def _ev(value: str) -> str:
        return 'verify_evidence: "' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (PD_EVIDENCE, 0),
            (IMPACT_EVIDENCE, 0),
            (f"{AC_EVIDENCE}; {PD_EVIDENCE}", 0),
            (AC_EVIDENCE, 1),
            ("Program Design: -> only a correction", 2),
            ("Impact: 'drift' ->", 2),
            ("Acceptance Criteria: 'x' -> update the Program Design: step", 1),
            ("Integration Map: 'Impact: stays' -> keep", 1),
        ],
        ids=[
            "design",
            "impact",
            "mixed",
            "ac-only",
            "empty-drift",
            "empty-correction",
            "prefix-in-correction-tail",
            "prefix-in-drift-tail",
        ],
    )
    def test_item_shapes(self, tmp_path: Path, value: str, expected: int) -> None:
        rc, _, _ = self._run(tmp_path, self._ev(value))
        assert rc == expected

    def test_non_string_and_absent_evidence_are_ordinary_no_match(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, "verify_evidence: [Program Design, Impact]")[0] == 1

    def test_absent_evidence_is_no_match(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, None)[0] == 1

    def test_ambiguous_quoted_delimiter_is_a_diagnostic(self, tmp_path: Path) -> None:
        rc, err, diag = self._run(
            tmp_path, self._ev("Program Design: 'drift; Impact: foo -> bar' -> fix")
        )
        assert rc == 2
        assert "ambiguous item boundary" in err
        assert diag.exists() and "ambiguous item boundary" in diag.read_text()

    @pytest.mark.parametrize(
        "value",
        [
            "Impact: it's priced for the old migration -> reprice for Option B, it's cheaper",
            "Impact: 'Effort says \\migration\\' -> reprice",
            "Program Design: 'a \"quoted\" step' -> rewrite",
            "Program Design: Call Path a \u2192 b \u2192 c -> rewrite the Call Path",
            "Impact: 'drift' -> fix, with one comma",
            f"{PD_EVIDENCE}; Acceptance Criteria: 'don't skip' -> add an AC",
        ],
        ids=["apostrophes", "backslashes", "double-quotes", "normalized-arrows", "comma", "mixed"],
    )
    def test_legal_punctuation_is_not_ambiguous(self, tmp_path: Path, value: str) -> None:
        assert self._run(tmp_path, self._ev(value))[0] == 0

    @pytest.mark.parametrize(
        "value",
        [
            "Program Design: a single item with no arrow",
            "Program Design:'no space' -> fix",
            "Program Design",
            "Impact:",
            "Impact: '' -> fix",
            "Program Design: 'drift' -> a -> b",
            f"{PD_EVIDENCE}; Impact: malformed later item",
            f"Impact: 'x' -> y; {PD_EVIDENCE}; Program Design:'bad' -> z",
            "Acceptance Criteria: ordinary fragment; Impact: 'x' -> y",
            "Impact: 'x' -> y; Acceptance Criteria: ",
        ],
        ids=[
            "no-arrow",
            "missing-space",
            "section-only",
            "section-colon-only",
            "empty-drift-quotes",
            "extra-arrow",
            "valid-first-malformed-later",
            "valid-first-malformed-last",
            "ordinary-fragment-beside-reserved",
            "empty-ordinary-item",
        ],
    )
    def test_malformed_reserved_lists_are_diagnostics(self, tmp_path: Path, value: str) -> None:
        rc, err, diag = self._run(tmp_path, self._ev(value))
        assert rc == 2
        assert "ambiguous item boundary" in err
        assert diag.exists()

    @pytest.mark.parametrize(
        "value",
        [
            "Acceptance Criteria: it's quoted; and a legacy fragment",
            "Acceptance Criteria: 'x' -> a -> b",
            "Integration Map: 'Impact: stays' -> keep; loose fragment",
        ],
        ids=["apostrophe-fragment", "ordinary-extra-arrow", "reserved-name-in-tail"],
    )
    def test_prefix_free_evidence_keeps_ordinary_fallback(self, tmp_path: Path, value: str) -> None:
        assert self._run(tmp_path, self._ev(value))[0] == 1

    def test_not_drift_verdict_is_no_match(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, self._ev(PD_EVIDENCE), probe_rc=1)[0] == 1

    @pytest.mark.parametrize("probe_rc", [2, 3])
    def test_probe_failure_is_a_diagnostic(self, tmp_path: Path, probe_rc: int) -> None:
        rc, _, diag = self._run(tmp_path, self._ev(PD_EVIDENCE), probe_rc=probe_rc)
        assert rc == 2 and diag.exists() and "probe failed" in diag.read_text()

    def test_path_failure_is_a_diagnostic(self, tmp_path: Path) -> None:
        rc, _, diag = self._run(tmp_path, self._ev(PD_EVIDENCE), path_rc=1)
        assert rc == 2 and diag.exists()


class TestRecordGateUnmetDiagnosticSurface:
    def test_diagnostic_and_capture_reach_terminal_reporting(self) -> None:
        text = (LOOPS / "refine-to-ready-issue.yaml").read_text()
        data = yaml.safe_load(text)
        action = data["states"]["record_gate_unmet"]["action"]
        assert "residual-decision-drift-diagnostic" in action
        assert "repair budget" in action and "not decomposing" in action
        assert data["states"]["check_residual_decision_drift"]["capture"] == (
            "check_residual_decision_drift"
        )
        assert "${captured.check_residual_decision_drift.stderr?}" in text

    def test_step_cap_and_closed_class_unchanged(self) -> None:
        data = yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())
        assert data["max_steps"] == 113
        assert "--legacy-class gate_unmet" in data["states"]["record_gate_unmet"]["action"]

    def test_guard_prefixes_pinned(self) -> None:
        action = yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())["states"][
            "check_residual_decision_drift"
        ]["action"]
        assert '("Program Design: ", "Impact: ")' in action
        assert 'split("; ")' in action and 'partition(" -> ")' in action
        assert 'count("\'")' not in action, "no quote-count rule (BUG-3764)"


def _slice(text: str, start: str, end: str) -> str:
    a = text.index(start)
    return text[a : text.index(end, a)]


class TestReconcileDecisionCarveOutContract:
    def _contract(self) -> str:
        return " ".join(
            _slice(
                RECONCILE_CMD.read_text(), "## Contract (read this first", "\n## Process"
            ).split()
        )

    def test_conditional_and_bounded(self) -> None:
        c = self._contract()
        assert "Decision-derived design/estimate propagation (BUG-3763)" in c
        assert "unambiguous selected option and its Decision Rationale" in c
        assert "`PROPOSAL_UNSOUND`" in c
        assert "re-reading the current issue" in c
        assert "never replace the whole H2" in c
        assert "Severity, Affected populations" in c
        assert "Ordinary reconciliation, unflagged callers" in c

    def test_process_clauses_extended(self) -> None:
        text = RECONCILE_CMD.read_text()
        triage = " ".join(_slice(text, "### 3b.", "### 4. Detect").split())
        assert "Design/estimate propagation target (BUG-3763)" in triage
        assert "fourth role" in triage
        step5b = " ".join(_slice(text, "### 5b.", "### 6. Append").split())
        assert "design-only or Impact-only" in step5b
        assert "never clear scores" in step5b
        check = " ".join(_slice(text, "### 7. Check Mode", "## Output Format").split())
        assert "design-only/Impact-only plateau" in check
        out = _slice(text, "## SECTIONS_REWRITTEN", "## CORRECTIONS_MADE")
        assert "- Program Design:" in out and "- Impact:" in out

    def test_bridge_and_flag_docs_mention_extension(self) -> None:
        assert "Program Design" in SKILL_BRIDGE.read_text()
        assert "BUG-3763" in RECONCILE_CMD.read_text().split("---", 2)[1]


class TestProducerSerializationRoundtrip:
    """BUG-3764: produced evidence survives strict YAML, the real parser and the guard."""

    @pytest.mark.parametrize(
        "payload",
        [
            "Impact: 'Effort/Risk: it's priced for the migration' -> reprice, it needs none",
            "Program Design: 'Call Path \"a\" \u2192 b' -> rewrite C:\\path\\step",
            "Impact: 'x: y' -> z; Program Design: 'q' -> r",
        ],
        ids=["apostrophe-colon", "quote-backslash-arrow", "mixed"],
    )
    def test_roundtrip(self, tmp_path: Path, payload: str) -> None:
        from little_loops.frontmatter import parse_frontmatter

        line = TestResidualGuardMatrix._ev(payload)
        text = f"---\nid: ENH-9800\n{line}\n---\n\nbody\n"
        assert yaml.safe_load(text.split("---")[1])["verify_evidence"] == payload
        assert parse_frontmatter(text)["verify_evidence"] == payload
        assert TestResidualGuardMatrix._run(tmp_path, line)[0] == 0
