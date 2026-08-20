"""Tests for ENH-3259: deterministic regression protection for the § 8b caller
suitability gate (ENH-3258).

ENH-3258 landed the gate as prose in a markdown prompt and validated it with a
one-shot synthetic fixture that was deleted after use. ENH-3259's stated threat
model is *deletion* — "a companion-extraction that drops the `Inject at <path>`
clause to fit the 500-line cap" — not subtle reasoning drift.

Deletion of a clause from a markdown file is assertable here, without an LLM and
without staging a fixture into `.issues/`. These tests cover that half:

* the gate's structural doctrine survives edits to `caller-suitability-gate.md`
* `SKILL.md` § 8b keeps both halves inline and keeps linking the companion
* the worked example obeys the `Inject at <path>` rule it states 30 lines above,
  and cites the seam that is still the sole production caller in the tree

What they do NOT cover: whether an LLM running `/ll:wire-issue` actually *applies*
the rule. That residual — rule present but under-applied — is what the ENH-3259
fixture loop exists for. Presence is gated here; application is gated there.

Follows the structural-test pattern from test_enh494_skill_companions.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
GATE_DOC = PROJECT_ROOT / "skills" / "wire-issue" / "caller-suitability-gate.md"
WIRE_ISSUE_SKILL = PROJECT_ROOT / "skills" / "wire-issue" / "SKILL.md"

# ENH-3259 fixture loop artifacts.
FIXTURE_ISSUE = (
    PROJECT_ROOT
    / "scripts"
    / "tests"
    / "fixtures"
    / "issues"
    / "ENH-288-fixture-caller-suitability-gate.md"
)
FIXTURE_LOOP = (
    PROJECT_ROOT
    / "scripts"
    / "tests"
    / "fixtures"
    / "loops"
    / "caller-suitability-gate-fixture.yaml"
)

# The seam the worked example must cite: the sole production caller of
# suggest_gitignore_patterns(), which passes no untracked_files= and so always
# falls through to the unfiltered call. Asserted live against the tree below so
# the example cannot silently go stale.
WORKED_EXAMPLE_SEAM = "scripts/little_loops/cli/gitignore.py:55"
WORKED_EXAMPLE_SYMBOL = "suggest_gitignore_patterns"


@pytest.fixture(scope="module")
def gate_text() -> str:
    assert GATE_DOC.exists(), f"Gate companion missing: {GATE_DOC.relative_to(PROJECT_ROOT)}"
    return GATE_DOC.read_text()


class TestBothHalvesDoctrine:
    """The gate's defining rule is that suppression alone is not the deliverable."""

    def test_both_halves_heading_present(self, gate_text: str) -> None:
        assert "Always emit both halves:" in gate_text, (
            "The 'Always emit both halves' mandate is gone from "
            f"{GATE_DOC.relative_to(PROJECT_ROOT)}. This is the rule that keeps the gate "
            "from being purely subtractive (ENH-3258); a gate that only deletes Update "
            "bullets leaves the Wiring Phase silent about a real touchpoint."
        )

    def test_record_half_names_dependent_files_section(self, gate_text: str) -> None:
        """Half 1: record the path rather than dropping it."""
        assert "### Dependent Files (Callers/Importers)" in gate_text, (
            "The record half no longer names the section a suppressed caller must be "
            "recorded under. Without it the gate cannot say where suppressed hits go."
        )

    def test_injection_half_states_the_inject_at_path_form(self, gate_text: str) -> None:
        """Half 2: the newer, less-exercised half — the one ENH-3259 exists to protect."""
        assert "`Inject at <path>`" in gate_text, (
            "The `Inject at <path>` clause is gone from "
            f"{GATE_DOC.relative_to(PROJECT_ROOT)}. This is the exact deletion ENH-3259's "
            "threat model names: dropping it makes the gate purely subtractive again."
        )

    def test_injection_half_contrasts_with_update(self, gate_text: str) -> None:
        assert "rather than `Update <path>`" in gate_text, (
            "The gate no longer contrasts `Inject at <path>` against `Update <path>`. "
            "The contrast is the instruction — redirect the touchpoint, never drop it."
        )

    def test_skip_conditions_both_stated(self, gate_text: str) -> None:
        assert "guard branch" in gate_text, "Skip condition 1 (guard branch) is missing."
        assert "already accepts the value as a parameter" in gate_text, (
            "Skip condition 2 (parameter is the seam) is missing. Condition 2 is what "
            "triggers the injection half, so losing it disables that half indirectly."
        )


class TestSkillInlineGate:
    """SKILL.md § 8b carries the gate inline and links the companion (ENH-494 budget)."""

    @pytest.fixture(scope="class")
    def skill_text(self) -> str:
        return WIRE_ISSUE_SKILL.read_text()

    def test_section_8b_names_the_gate(self, skill_text: str) -> None:
        assert "Caller suitability gate" in skill_text, (
            "§ 8b's caller suitability gate heading is gone from "
            f"{WIRE_ISSUE_SKILL.relative_to(PROJECT_ROOT)}."
        )

    def test_inline_text_keeps_the_injection_half(self, skill_text: str) -> None:
        """The 500-line cap makes § 8b the likeliest place for the clause to be trimmed."""
        assert "`Inject at <path>`" in skill_text, (
            "§ 8b's inline text no longer mentions `Inject at <path>`. A companion "
            "extraction that trims the inline summary to fit the 500-line cap can drop "
            "this half while leaving the companion intact — the model reads SKILL.md first."
        )

    def test_links_companion(self, skill_text: str) -> None:
        assert GATE_DOC.name in skill_text, (
            f"{WIRE_ISSUE_SKILL.relative_to(PROJECT_ROOT)} no longer links "
            f"{GATE_DOC.name}; the companion is unreachable from the prompt."
        )


class TestWorkedExampleObeysItsOwnRule:
    """The worked example emits the form the doctrine mandates.

    ENH-3259 found the original bullet in breach: it read `Inject at
    suggest_gitignore_patterns()'s existing untracked_files= parameter` — naming no
    path at all, violating the `Inject at <path>` rule stated 30 lines above it.
    """

    def test_example_cites_a_path(self, gate_text: str) -> None:
        assert f"Inject at `{WORKED_EXAMPLE_SEAM}`" in gate_text, (
            "The worked example's `Inject at` bullet does not name "
            f"`{WORKED_EXAMPLE_SEAM}`. The example is the doctrine the gate's own prompt "
            "cites as correct behavior — a bullet that names no path teaches the "
            "violation it warns against."
        )

    def test_cited_seam_is_still_the_sole_production_caller(self) -> None:
        """Guard the example against tree drift, not just deletion.

        If someone adds a second production caller of suggest_gitignore_patterns(),
        or moves the existing one, the worked example's "sole production caller"
        claim becomes false and the example must be re-derived.
        """
        path_part, _, line_part = WORKED_EXAMPLE_SEAM.rpartition(":")
        cited = PROJECT_ROOT / path_part
        assert cited.exists(), f"Worked example cites a file that no longer exists: {path_part}"

        lines = cited.read_text().splitlines()
        cited_line_no = int(line_part)
        assert cited_line_no <= len(lines), (
            f"{path_part} has {len(lines)} lines; worked example cites :{cited_line_no}."
        )
        assert WORKED_EXAMPLE_SYMBOL in lines[cited_line_no - 1], (
            f"{WORKED_EXAMPLE_SEAM} no longer calls {WORKED_EXAMPLE_SYMBOL}(). "
            f"Found instead: {lines[cited_line_no - 1].strip()!r}. Re-derive the worked "
            "example's injection seam and update the citation."
        )

    def test_example_records_the_suppressed_call_site(self, gate_text: str) -> None:
        """The record half of the example — also the loop's liveness precondition."""
        assert "`scripts/little_loops/git_operations.py:413`" in gate_text, (
            "The worked example no longer records the suppressed call site under "
            "Dependent Files. That entry is the positive half the gate mandates."
        )


def _fixture_loop_is_running() -> bool:
    """Skip-condition for the residue guard: is the fixture loop mid-run right now?

    Locks live at .loops/.running/<instance_id>.lock (fsm/concurrency.py), named by
    instance_id rather than loop name, with loop_name carried inside the JSON payload —
    so this must glob-and-parse rather than check a fixed path. An env-var check
    (LL_AUTOMATION) does not work here: conftest.py's autouse _restore_cmd_run_env_vars
    fixture delenvs it for every test, so it always reads unset (ENH-3259 seventh
    review round).
    """
    running_dir = PROJECT_ROOT / ".loops" / ".running"
    if not running_dir.is_dir():
        return False
    for lock_file in running_dir.glob("*.lock"):
        try:
            payload = json.loads(lock_file.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("loop_name") == "caller-suitability-gate-fixture":
            return True
    return False


class TestFixtureLoopResidue:
    """ENH-3259: the staged fixture must leave no residue in `.issues/`.

    The staged copy is gitignored (see .gitignore), which blinds `git status` to
    residue by construction — this filesystem-level glob is the only mechanism that
    can see it once that ignore entry exists. It doubles as the ID-reservation guard:
    the same assertion proves nobody has hand-allocated 288 to real work.
    """

    def test_no_staged_fixture_residue(self) -> None:
        if _fixture_loop_is_running():
            pytest.skip("caller-suitability-gate-fixture loop is currently running")
        residue = list((PROJECT_ROOT / ".issues").glob("*/*-288-*.md"))
        assert not residue, (
            f"Staged ENH-288 fixture residue found: {residue}. Either a fixture loop "
            "run was interrupted before its unstage-fixture state, or ID 288 has been "
            "hand-allocated to real work — both are invalid states."
        )


class TestFixtureNonVacuity:
    """ENH-3259 seventh review round: gate-record must not be satisfiable by the
    pristine (unmodified) fixture body.

    All three gates `grep` the archived file, which is the fixture body plus
    whatever wire-issue appended — `grep` cannot tell the two apart. If the
    checked-in fixture body happened to already contain one of the gate substrings,
    a dead run (wire-issue never wrote) could pass that gate anyway, defeating the
    RUN_INVALID liveness design. This converts "the gates are non-vacuous" from an
    authoring convention into a suite-enforced invariant.
    """

    def test_fixture_body_carries_none_of_the_gate_substrings(self) -> None:
        assert FIXTURE_ISSUE.exists(), (
            f"Fixture issue missing: {FIXTURE_ISSUE.relative_to(PROJECT_ROOT)}"
        )
        body = FIXTURE_ISSUE.read_text()
        forbidden = [
            "git_operations.py:413",
            "Update `scripts/little_loops/git_operations.py",
            "Inject at `scripts/little_loops/cli/gitignore.py:55`",
        ]
        for substring in forbidden:
            assert substring not in body, (
                f"Fixture body already contains gate substring {substring!r} before "
                "wire-issue ever runs — this would let the gate pass vacuously on a "
                "dead run, defeating the RUN_INVALID liveness check."
            )


class TestFixtureLoopValidates:
    """ENH-3259 sixth review round: the loop under scripts/tests/fixtures/loops/ sits
    outside every BUILTIN_LOOPS_DIR sweep, so nothing else in the suite validates its
    schema. Wrapped as a subprocess-shelling pytest per the repo's Testing & CI Policy
    (precedent: test_policy_builder_node_gate.py).
    """

    def test_ll_loop_validate_exits_zero(self) -> None:
        assert FIXTURE_LOOP.exists(), (
            f"Fixture loop missing: {FIXTURE_LOOP.relative_to(PROJECT_ROOT)}"
        )
        result = subprocess.run(
            ["ll-loop", "validate", str(FIXTURE_LOOP)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"ll-loop validate failed on {FIXTURE_LOOP.relative_to(PROJECT_ROOT)}:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
