"""Regression tests for BUG-3216: broken `ll-logs` invocations in the telemetry digest loop.

Five states in `.loops/ll-logs-telemetry-digest.yaml` invoked corpus-scoped
`ll-logs` subcommands without the required `--project`/`--all` target (each exits
2 at argparse), and `refresh_corpus` additionally passed an unregistered
`--quiet`. Downstream, a failed call was indistinguishable from an empty result,
so the digest could report a clean corpus off argparse usage text.

Follows the content-assertion idiom of `test_bug_2816_cli_invocations.py` (same
defect class), but targets the repo-root `.loops/` directory, which
`TestBuiltinLoopFiles` does not walk — it covers `BUILTIN_LOOPS_DIR` only.

The parse check drives `_build_parser()` rather than the usual
`main_logs()`-under-patched-`sys.argv` convention on purpose: `main_logs()` would
*execute* the commands, and `extract --all` writes into `logs/`. Parser-level
validation proves the argument surface without side effects.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import shlex
from pathlib import Path

import pytest
import yaml

from little_loops.cli.logs import _build_parser

# scripts/tests/ -> scripts/ -> repo root. Resolved from __file__ rather than
# find_project_root() so a stray .ll/ directory cannot shadow the lookup.
REPO_ROOT = Path(__file__).parents[2]
LOOP_REL_PATH = ".loops/ll-logs-telemetry-digest.yaml"

# States that invoke a corpus-scoped ll-logs subcommand, and the target each must
# supply. scan_failures/check_dead_skills stay project-scoped because they feed
# prompt states that file issues into *this* repo's .issues/.
EXPECTED_TARGETS = {
    "refresh_corpus": "--all",
    "run_stats": "--all",
    "scan_failures": "--project",
    "run_sequences": "--all",
    "check_dead_skills": "--project",
}

# Tokens that end a simple command inside a shell action.
_STOP_TOKENS = {"|", "||", "&&", ";", "&", ">", ">>", "<"}


def _loop_text() -> str:
    path = REPO_ROOT / LOOP_REL_PATH
    if not path.exists():
        pytest.skip(f"{LOOP_REL_PATH} not present (source-repo-only artifact)")
    return path.read_text()


def _join_continuations(action: str) -> str:
    """Fold `\\`-continued shell lines into one physical line.

    Without this, `shlex.split` raises ValueError("No escaped character") on the
    trailing backslash and the invocation is silently dropped — which would make
    the sweep below cover only part of the file while still passing.
    """
    return re.sub(r"\\\n\s*", " ", action)


def _extract_ll_logs_invocations() -> list[tuple[str, list[str]]]:
    """Return (state_name, argv) for every `ll-logs ...` call in a shell action."""
    loop = yaml.safe_load(_loop_text())
    found: list[tuple[str, list[str]]] = []

    for state_name, state in loop["states"].items():
        if state.get("action_type") != "shell":
            continue
        for line in _join_continuations(state["action"]).splitlines():
            for match in re.finditer(r"\bll-logs\b", line):
                try:
                    tokens = shlex.split(line[match.start() :], posix=True)
                except ValueError:  # pragma: no cover - guarded by _join_continuations
                    pytest.fail(f"{state_name}: could not tokenize shell line: {line!r}")
                argv: list[str] = []
                for token in tokens[1:]:
                    if token in _STOP_TOKENS or re.match(r"^\d*[<>]", token):
                        break
                    argv.append(token)
                found.append((state_name, argv))
    return found


class TestExtractorSanity:
    """The sweep must not pass vacuously: an extractor that finds nothing would
    satisfy every 'all invocations parse' assertion below."""

    def test_finds_invocations_in_every_corpus_state(self) -> None:
        states = {state for state, _ in _extract_ll_logs_invocations()}
        missing = set(EXPECTED_TARGETS) - states
        assert not missing, f"extractor found no ll-logs invocation in: {sorted(missing)}"

    def test_finds_the_line_continued_invocation(self) -> None:
        """run_sequences' call historically wrapped with a trailing backslash."""
        calls = [
            argv
            for state, argv in _extract_ll_logs_invocations()
            if state == "run_sequences" and argv[:1] == ["sequences"]
        ]
        assert calls, "no real `ll-logs sequences` invocation extracted from run_sequences"


class TestInvocationsParse:
    """Every invocation must satisfy the real argument surface."""

    def test_all_invocations_parse(self) -> None:
        parser = _build_parser()
        failures = []
        for state, argv in _extract_ll_logs_invocations():
            if "--help" in argv or "-h" in argv:
                continue
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    parser.parse_args(argv)
            except SystemExit as exc:
                failures.append(f"{state}: `ll-logs {' '.join(argv)}` exits {exc.code}")
        assert not failures, "invocations rejected by argparse:\n" + "\n".join(failures)

    def test_every_corpus_state_supplies_a_target(self) -> None:
        by_state: dict[str, list[list[str]]] = {}
        for state, argv in _extract_ll_logs_invocations():
            by_state.setdefault(state, []).append(argv)

        for state, expected in EXPECTED_TARGETS.items():
            targeted = [
                argv
                for argv in by_state.get(state, [])
                if argv and argv[0] != "discover" and expected in argv
            ]
            assert targeted, f"{state}: no ll-logs call carrying {expected}"

    def test_no_unregistered_quiet_flag(self) -> None:
        """`--quiet` is not registered anywhere on ll-logs (Part 4 not shipped)."""
        assert "--quiet" not in _loop_text()

    def test_discover_takes_no_target(self) -> None:
        """discover_parser has no corpus-target group; passing one would exit 2."""
        for state, argv in _extract_ll_logs_invocations():
            if argv[:1] == ["discover"]:
                assert "--all" not in argv and "--project" not in argv, (
                    f"{state}: ll-logs discover accepts no --project/--all target"
                )


class TestFailureIsDistinguishableFromEmpty:
    """A failed or no-data call must not be reported as a clean corpus."""

    @pytest.mark.parametrize(
        ("state", "tokens"),
        [
            ("scan_failures", ("FAILURES_ERROR", "FAILURES_NO_DATA", "NO_FAILURES")),
            ("check_dead_skills", ("DEAD_SKILLS_ERROR", "DEAD_SKILLS_NO_DATA", "NO_DEAD_SKILLS")),
            ("run_stats", ("STATS_ERROR", "STATS_NO_DATA", "STATS_OK")),
            ("run_sequences", ("SEQUENCES_ERROR", "SEQUENCES_OK")),
        ],
    )
    def test_state_emits_distinct_outcome_tokens(self, state: str, tokens: tuple[str, ...]) -> None:
        action = yaml.safe_load(_loop_text())["states"][state]["action"]
        for token in tokens:
            assert token in action, f"{state}: missing outcome token {token}"

    @pytest.mark.parametrize("state", ["scan_failures", "check_dead_skills", "run_stats"])
    def test_state_checks_exit_status_separately(self, state: str) -> None:
        action = yaml.safe_load(_loop_text())["states"][state]["action"]
        assert "RC=$?" in action, f"{state}: does not capture the invocation's exit status"
        assert 'if [ "$RC" -ne 0 ]' in action, f"{state}: does not branch on exit status"

    @pytest.mark.parametrize("state", ["scan_failures", "check_dead_skills"])
    def test_unparseable_artifact_is_not_zero(self, state: str) -> None:
        """The old `except: print(0)` made usage text look like an empty result."""
        action = yaml.safe_load(_loop_text())["states"][state]["action"]
        assert "print(-1)" in action, f"{state}: unparseable output must not read as a count of 0"
        assert "except Exception:\n    print(0)" not in action

    @pytest.mark.parametrize("state", ["scan_failures", "check_dead_skills"])
    def test_json_array_shape_is_preserved(self, state: str) -> None:
        """Both subcommands emit a bare top-level array; the dict-key branch is
        dead code that must stay dead rather than become a required key."""
        action = yaml.safe_load(_loop_text())["states"][state]["action"]
        assert "isinstance(d, dict)" in action
        assert "isinstance(items, list)" in action

    @pytest.mark.parametrize(
        ("state", "pattern", "triage_state"),
        [
            ("scan_failures", "FAILURES_FOUND", "triage_failures"),
            ("check_dead_skills", "DEAD_SKILLS_FOUND", "file_dead_skill_issues"),
        ],
    )
    def test_only_a_positive_finding_reaches_triage(
        self, state: str, pattern: str, triage_state: str
    ) -> None:
        """Gate on the positive token so _ERROR/_NO_DATA cannot file issues from
        garbage — the old `NO_FAILURES` polarity routed errors into triage."""
        node = yaml.safe_load(_loop_text())["states"][state]
        assert node["evaluate"]["pattern"] == pattern
        assert node["on_yes"] == triage_state
        for outcome in (
            f"{pattern.rsplit('_', 1)[0]}_ERROR",
            f"{pattern.rsplit('_', 1)[0]}_NO_DATA",
        ):
            assert not re.search(pattern, outcome), f"{outcome} must not match the triage gate"


class TestRefreshCorpusDoesNotGate:
    """`extract --all` has no failure path (cli/logs.py:796) and nothing
    downstream reads what it writes, so the state has no honest signal to gate on."""

    def test_no_vacuous_evaluate_block(self) -> None:
        node = yaml.safe_load(_loop_text())["states"]["refresh_corpus"]
        assert "evaluate" not in node, "refresh_corpus gate is always true — use `next:` instead"
        assert node.get("next") == "run_stats"

    def test_no_refreshed_gate_token(self) -> None:
        assert "REFRESHED" not in _loop_text()


class TestLoopDeclaresScope:
    """Without `scope:`, ll-loop run takes a repo-root lock that false-conflicts
    with every other concurrently running loop."""

    def test_scope_declared(self) -> None:
        loop = yaml.safe_load(_loop_text())
        scope = loop.get("scope")
        assert scope, "loop declares no scope:"
        assert ".issues/" in scope, "loop files issues but does not scope .issues/"


class TestHelpProbeAntiPattern:
    """argparse services -h and exits 0 *before* validating required groups, so a
    `--help` probe cannot detect a missing required argument."""

    def test_help_probes_removed(self) -> None:
        loop = yaml.safe_load(_loop_text())
        offenders = [
            name
            for name, state in loop["states"].items()
            if state.get("action_type") == "shell"
            and "--help >/dev/null" in state.get("action", "")
        ]
        assert not offenders, f"--help capability probes remain in: {offenders}"


class TestParserSurfaceUnchanged:
    """Guards the assumptions the loop now encodes, so a CLI change breaks here
    rather than silently disabling the loop."""

    @pytest.mark.parametrize(
        ("argv", "expect_exit"),
        [
            (["extract", "--all"], False),
            (["extract"], True),  # required target group
            (["extract", "--all", "--quiet"], True),  # --quiet still unregistered
            (["stats", "--all"], False),
            (["sequences", "--all", "--top", "20", "--min-count", "3"], False),
            (["scan-failures", "--project", ".", "--json"], False),
            (["dead-skills", "--project", ".", "--json"], False),
            (["discover"], False),
        ],
    )
    def test_argument_surface(self, argv: list[str], expect_exit: bool) -> None:
        parser = _build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            if expect_exit:
                with pytest.raises(SystemExit):
                    parser.parse_args(argv)
            else:
                assert isinstance(parser.parse_args(argv), argparse.Namespace)
