"""Cross-loop characterization harness for ``autodev`` (ENH-3606, plan item 1C).

Runs the REAL ``autodev.yaml`` (which delegates ``refine_current`` to the real
``prepare-issue.yaml``, which delegates to ``refine-to-ready-issue``) under a
``PersistentExecutor`` against a throwaway project, with:

- a **stub** ``refine-to-ready-issue.yaml`` placed in a temporary ``loops_dir``
  (``resolve_loop_path`` prefers it over the builtin). Its one scripted state is
  executed in-process by :class:`ScriptedRunner` from the scenario's
  :class:`InnerRun` list for that issue — so a scenario can script successive
  inner runs (first pass, then a selector re-entry);
- a :class:`ScriptedRunner` that answers every ``slash_command`` action from the
  scenario's :class:`SlashResponse` queue for that skill (with file side effects:
  scores written or omitted, ``reconcile_attempted`` stamped, ``outcome_gate_waived``
  stamped, child issues created with ``parent:``), and runs every shell action as
  real bash via ``DefaultActionRunner`` against the project;
- PATH shims: ``ll-issues`` / ``ll-config`` / ``python3`` pinned to this test
  process's interpreter and ``little_loops`` source tree (the CLI shims fork from a
  preloaded server, see ``_CLI_SERVER``; ``AUTODEV_HARNESS_SLOW_CLI=1`` disables
  it), and a fake ``ll-auto`` that writes plausible output and closes the issue
  with the real ``ll-issues set-status``;
- ``context.quality_gate=false`` by default (no oracles/code-run-gate, no test
  commands); thresholds are seeded from the project config (85/65), mirroring
  ``cli/loop/run.py``'s context seeding.

Slash responses and inner runs are consumed in order per skill / per issue; the
last one is sticky. Anything unscripted runs a no-op (slash) or a ``quality``
stop (inner) and is listed in :attr:`AutodevResult.unscripted`. ``Scenario.faults``
replaces the first action of a named state with a bare exit code (on_error edges).

Everything a later spike needs to swap is a parameter of :func:`run_autodev`:
``prepare_issue_yaml=`` (a replacement wrapper, copied into the temp
``loops_dir`` as ``prepare-issue.yaml``) and ``autodev_transform=`` (a function
over the parsed ``autodev.yaml`` dict, e.g. to apply boundary-edge retargets).
Scenarios are plain dataclasses so the same table can be re-run against both.

Crash injection: ``Scenario.crash`` makes the runner raise :class:`HarnessCrash`
(a ``BaseException``, so no executor ``except Exception`` swallows it — it models
a killed process) at a runner step. The harness then builds a fresh
``PersistentExecutor`` over the same persisted state and calls ``resume()``,
exactly as ``ll-loop resume`` would.

Rate-limit waits are made instant (``FSMExecutor._interruptible_sleep`` is
patched to return the requested duration without sleeping) and every requested
wait is recorded in :attr:`AutodevResult.sleeps`, so an accidental rate-limit
classification is visible instead of hanging the test.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

import little_loops
from little_loops.frontmatter import parse_frontmatter, remove_frontmatter_keys, update_frontmatter
from little_loops.fsm.persistence import PersistentExecutor, StatePersistence
from little_loops.fsm.runners import DefaultActionRunner
from little_loops.fsm.types import ActionResult

#: Source tree the shims import ``little_loops`` from — the same tree this test
#: process imported, so worktree code is exercised even when the editable install
#: points at another checkout.
SCRIPTS_DIR = Path(little_loops.__file__).resolve().parent.parent
BUILTIN_LOOPS_DIR = SCRIPTS_DIR / "little_loops" / "loops"
AUTODEV_YAML = BUILTIN_LOOPS_DIR / "autodev.yaml"
PREPARE_ISSUE_YAML = BUILTIN_LOOPS_DIR / "prepare-issue.yaml"

#: Marker command of the stub inner loop's scripted state. Never reaches bash:
#: :class:`ScriptedRunner` executes it in-process.
INNER_MARKER = "autodev-harness-inner"

DEFAULT_CONFIG: dict[str, Any] = {
    "project": {"name": "autodev-harness-project"},
    "issues": {
        "base_dir": ".issues",
        "categories": {
            "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
            "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
            "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
            "epics": {"prefix": "EPIC", "dir": "epics", "action": "implement"},
        },
    },
    "commands": {"confidence_gate": {"readiness_threshold": 85, "outcome_threshold": 65}},
}

_TYPE_DIRS = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements", "EPIC": "epics"}

DEFAULT_BODY = """
## Summary

Make the widget faster.

## Current Behavior

The widget is slow.

## Expected Behavior

The widget is fast.

## Acceptance Criteria

- [ ] widget renders in under 100ms
"""

#: Stub ``refine-to-ready-issue.yaml``. ``resolve_issue`` mirrors the real loop's
#: resets (terminal-class sentinel, broke-down flag, own record); the scripted
#: state then prints DONE / FAILED / ERROR. ERROR reaches ``die``, whose
#: undefined context reference raises ``InterpolationError`` so the child
#: finishes ``terminated_by: error`` (prepare-issue's ``mark_inner_error`` edge).
STUB_REFINE_TO_READY = """\
name: refine-to-ready-issue
description: "autodev characterization harness stub (scripted by ScriptedRunner)"
category: issue-management
visibility: internal
initial: resolve_issue
max_steps: 20
states:
  resolve_issue:
    action: >-
      mkdir -p ${context.run_dir} &&
      rm -f ${context.run_dir}/refine-terminal-class &&
      printf '0' > ${context.run_dir}/refine-broke-down &&
      ID=$(printf '%s' ${context.input:shell} | tr -d '\\n\\r ') &&
      { ll-issues run-record clear "$${ID}" --run-dir ${context.run_dir} --writer refine-to-ready-issue || true; } &&
      printf '%s' "$${ID}"
    action_type: shell
    capture: issue_id
    next: scripted_run
    on_error: scripted_run
  scripted_run:
    action: "autodev-harness-inner ${context.run_dir} ${captured.issue_id.output:shell} ${context.readiness_threshold} ${context.outcome_threshold}"
    action_type: shell
    evaluate:
      type: classify
    route:
      DONE: done
      FAILED: failed
      ERROR: die
      _: die
      _error: die
  die:
    action: "echo ${context.autodev_harness_undefined_key}"
    action_type: shell
    next: failed
  done:
    terminal: true
  failed:
    terminal: true
    failure: true
"""


# ---------------------------------------------------------------------------
# Scenario data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChildSpec:
    """An issue file created as a side effect (a decomposition child)."""

    issue_id: str
    parent: str | None
    status: str = "open"
    frontmatter: Mapping[str, Any] = field(default_factory=dict)
    title: str = "Child issue"


@dataclass(frozen=True)
class Effects:
    """File side effects shared by inner runs and slash responses.

    ``frontmatter`` updates the target issue (a ``None`` value removes the key);
    ``scores=(readiness, outcome)`` is shorthand for ``confidence_score`` /
    ``outcome_confidence``; ``clear_scores`` removes both. ``status`` rewrites
    the frontmatter ``status`` directly. ``body_append`` is appended to the issue
    body; ``children`` are created as new issue files; ``run_dir_appends`` are
    ``(filename, line)`` pairs appended under ``run_dir``.
    """

    frontmatter: Mapping[str, Any] = field(default_factory=dict)
    scores: tuple[int, int] | None = None
    clear_scores: bool = False
    status: str | None = None
    body_append: str = ""
    children: tuple[ChildSpec, ...] = ()
    run_dir_appends: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class InnerRun:
    """One scripted run of the stub ``refine-to-ready-issue`` for one issue.

    ``terminal``: ``done`` / ``failed`` end in the matching stub terminal;
    ``error`` makes the child die (``terminated_by: error``). ``legacy_class``
    is written to ``refine-terminal-class`` and passed as ``--legacy-class``
    (the real loop's stop states do both). ``broke_down`` writes ``1`` to
    ``refine-broke-down`` before the record write (``write_broke_down``).
    ``write_record=False`` models a failed ``|| true`` record write.
    """

    terminal: Literal["done", "failed", "error"] = "done"
    effects: Effects = field(default_factory=Effects)
    legacy_class: str | None = None
    broke_down: bool = False
    write_record: bool = True
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlashResponse:
    """Canned result of one slash-command call, plus its side effects on the issue."""

    output: str = ""
    exit_code: int = 0
    effects: Effects = field(default_factory=Effects)
    callback: Callable[[HarnessContext, str], None] | None = None


@dataclass(frozen=True)
class LlAutoSpec:
    """Behavior of the fake ``ll-auto --only <ID>``."""

    exit_code: int = 0
    output: str = "Processing issue {id}\nIssues processed: 1\n"
    close: bool = True


@dataclass(frozen=True)
class Crash:
    """Kill the run at one runner step, then resume via ``PersistentExecutor``.

    Exactly one of ``step`` (1-based index over every ``ActionRunner.run`` call,
    shell and slash, parent and child) or ``state`` (the ``occurrence``-th runner
    call made while that state is current) selects the step. ``when="before"``
    crashes before the action runs; ``"after"`` runs it (side effects land) and
    crashes before its result is returned.
    """

    step: int | None = None
    state: str | None = None
    occurrence: int = 1
    when: Literal["before", "after"] = "before"
    #: ENH-3630: roll back the last scripted command's consumption (slash
    #: response / inner run) at the crash, so a resumed replay of that command gets
    #: the same scripted result (models a deterministic replay of the killed command).
    replay_same: bool = False


@dataclass(frozen=True)
class Scenario:
    """One characterization scenario. Pure data (plus optional callbacks)."""

    name: str
    issue_id: str = "ENH-9001"
    frontmatter: Mapping[str, Any] = field(default_factory=dict)
    body: str = DEFAULT_BODY
    queue: str | None = None
    extra_issues: tuple[ChildSpec, ...] = ()
    inner_runs: Mapping[str, tuple[InnerRun, ...]] = field(default_factory=dict)
    slash: Mapping[str, tuple[SlashResponse, ...]] = field(default_factory=dict)
    #: ``{state_name: exit_code}``: the first runner call made in that state
    #: returns this exit code without running the action (fault injection).
    faults: Mapping[str, int] = field(default_factory=dict)
    context: Mapping[str, Any] = field(default_factory=dict)
    ll_auto: LlAutoSpec = field(default_factory=LlAutoSpec)
    project_files: Mapping[str, str] = field(default_factory=dict)
    config_overrides: Mapping[str, Any] = field(default_factory=dict)
    crash: Crash | None = None


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class AutodevResult:
    """What one harness run produced (all lists are file lines, blanks dropped)."""

    terminated_by: str
    final_state: str
    path: list[str]
    wrapper_path: list[str]
    full_path: list[str]
    skipped: list[str]
    queue: list[str]
    staged: list[str]
    passed: list[str]
    unverified: list[str]
    dequeued: list[str]
    record_token: str
    inner_record_token: str
    records: dict[str, str]
    inner_records: dict[str, str]
    status: str | None
    deferred_reason: str | None
    issues: dict[str, tuple[str | None, str | None]]
    loop_yaml_paths: dict[str, list[str]]
    summary: dict[str, Any] | None
    slash_commands: list[str]
    repair_cycle_count: str | None
    ll_auto_calls: list[str]
    ledgers: dict[str, list[str]]
    sleeps: list[float]
    unscripted: list[str]
    cli_calls: list[str]
    cli_failures: list[str]
    steps: int
    crashed_at: dict[str, Any] | None
    resumed_terminated_by: str | None
    run_dir: Path
    project: Path
    #: Issue id of every stub inner run actually executed (ENH-3630).
    inner_calls: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Issue-file helpers
# ---------------------------------------------------------------------------


def issue_path(project: Path, issue_id: str) -> Path:
    """Return the path of an issue created by this harness (``P3-<ID>-...md``)."""
    prefix = issue_id.split("-", 1)[0]
    d = project / ".issues" / _TYPE_DIRS[prefix]
    matches = sorted(d.glob(f"P*-{issue_id}-*.md"))
    if not matches:
        raise FileNotFoundError(f"harness: no issue file for {issue_id} in {d}")
    return matches[0]


def write_issue(
    project: Path,
    issue_id: str,
    *,
    frontmatter: Mapping[str, Any],
    body: str,
    title: str = "Sample enhancement",
) -> Path:
    """Create ``P3-<ID>-harness.md`` with ``id``/``status`` plus *frontmatter*."""
    prefix = issue_id.split("-", 1)[0]
    d = project / ".issues" / _TYPE_DIRS[prefix]
    d.mkdir(parents=True, exist_ok=True)
    fm: dict[str, Any] = {"id": issue_id, "status": "open"}
    fm.update(frontmatter)
    fm_text = yaml.safe_dump(fm, default_flow_style=False, sort_keys=False).strip()
    path = d / f"P3-{issue_id}-harness.md"
    path.write_text(f"---\n{fm_text}\n---\n\n# {issue_id}: {title}\n{body}")
    return path


def read_issue_frontmatter(project: Path, issue_id: str) -> dict[str, Any]:
    """Parse the issue's frontmatter (coerced types)."""
    return parse_frontmatter(issue_path(project, issue_id).read_text(), coerce_types=True)


@dataclass
class HarnessContext:
    """Handed to side-effect callbacks: where things are, plus the effect applier."""

    project: Path
    run_dir: Path
    harness_dir: Path

    def apply(self, issue_id: str, effects: Effects) -> None:
        """Apply *effects* to *issue_id* (see :class:`Effects`)."""
        path = issue_path(self.project, issue_id)
        content = path.read_text()
        updates = dict(effects.frontmatter)
        removals = [k for k, v in updates.items() if v is None]
        updates = {k: v for k, v in updates.items() if v is not None}
        if effects.scores is not None:
            updates["confidence_score"], updates["outcome_confidence"] = effects.scores
        if effects.status is not None:
            updates["status"] = effects.status
        if effects.clear_scores:
            removals += ["confidence_score", "outcome_confidence"]
        if updates:
            content = update_frontmatter(content, updates)
        if removals:
            content = remove_frontmatter_keys(content, removals)
        if effects.body_append:
            content = content.rstrip("\n") + "\n" + effects.body_append
        path.write_text(content)
        for child in effects.children:
            fm: dict[str, Any] = {"status": child.status}
            if child.parent is not None:
                fm["parent"] = child.parent
            fm.update(child.frontmatter)
            write_issue(self.project, child.issue_id, frontmatter=fm, body=DEFAULT_BODY)
        for name, line in effects.run_dir_appends:
            with (self.run_dir / name).open("a") as f:
                f.write(line + "\n")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class HarnessCrash(BaseException):  # noqa: N818 - models a process kill, not an error
    """Raised by :class:`ScriptedRunner` to model a killed process mid-run."""


class _Tracker:
    """Current (loop, state) from ``state_enter`` events, plus the event log."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.loop = ""
        self.state = ""

    def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        if event.get("event") == "state_enter":
            self.loop = str(event.get("loop") or "")
            self.state = str(event.get("state") or "")


_SLASH_RE = re.compile(r"^/(?:[\w-]+:)?([\w-]+)\s*(\S*)")


class ScriptedRunner:
    """``ActionRunner`` for the harness (see module docstring)."""

    def __init__(
        self,
        scenario: Scenario,
        hctx: HarnessContext,
        tracker: _Tracker,
        *,
        inner_counts: dict[str, int],
        slash_counts: dict[str, int],
    ) -> None:
        self.scenario = scenario
        self.hctx = hctx
        self.tracker = tracker
        self.inner_counts = inner_counts
        self.slash_counts = slash_counts
        self.default = DefaultActionRunner()
        self.step = 0
        self.state_calls: dict[str, int] = {}
        self.faults_fired: set[str] = set()
        self.slash_log: list[str] = []
        self.inner_log: list[str] = []
        self.unscripted: list[str] = []
        self.crash: Crash | None = scenario.crash
        self.crashed_at: dict[str, Any] | None = None
        #: (counter dict, key) of the last scripted command consumed (Crash.replay_same).
        self._consumed: tuple[dict[str, int], str] | None = None

    # -- crash -------------------------------------------------------------

    def _crash_due(self, state: str) -> bool:
        c = self.crash
        if c is None:
            return False
        if c.step is not None:
            return self.step == c.step
        return c.state == state and self.state_calls.get(state, 0) == c.occurrence

    def _maybe_crash(self, when: str, action: str) -> None:
        if (
            self.crash is not None
            and self.crash.when == when
            and self._crash_due(self.tracker.state)
        ):
            self.crashed_at = {
                "step": self.step,
                "loop": self.tracker.loop,
                "state": self.tracker.state,
                "when": when,
                "action": action.splitlines()[0][:120] if action else "",
            }
            replay_same = self.crash.replay_same
            self.crash = None  # one crash per run
            if replay_same and self._consumed is not None:
                counts, key = self._consumed
                counts[key] -= 1
            raise HarnessCrash(f"harness crash at step {self.step} ({self.tracker.state})")

    # -- ActionRunner protocol ----------------------------------------------

    def run(self, action: str, timeout: int, is_slash_command: bool, **kwargs: Any) -> ActionResult:
        self.step += 1
        state = self.tracker.state
        self.state_calls[state] = self.state_calls.get(state, 0) + 1
        self._maybe_crash("before", action)
        # ENH-3630: "state#N" faults the N-th runner call made in that state.
        fault_key = next(
            (
                k
                for k in (state, f"{state}#{self.state_calls[state]}")
                if k in self.scenario.faults and k not in self.faults_fired
            ),
            None,
        )
        if fault_key is not None:
            self.faults_fired.add(fault_key)
            result = ActionResult(
                output=f"[HARNESS-FAULT] {state}",
                stderr="",
                exit_code=self.scenario.faults[fault_key],
                duration_ms=1,
            )
        elif is_slash_command:
            result = self._run_slash(action)
        elif action.startswith(INNER_MARKER + " "):
            result = self._run_inner(action)
        else:
            result = self.default.run(action, timeout, is_slash_command, **kwargs)
        self._maybe_crash("after", action)
        return result

    # -- slash commands -----------------------------------------------------

    def _run_slash(self, action: str) -> ActionResult:
        m = _SLASH_RE.match(action.strip())
        skill = m.group(1) if m else action.strip().split()[0]
        target = m.group(2) if m else ""
        self.slash_log.append(f"{skill} {target}".strip())
        n = self.slash_counts.get(skill, 0)
        self.slash_counts[skill] = n + 1
        self._consumed = (self.slash_counts, skill)
        responses = self.scenario.slash.get(skill, ())
        if not responses:
            self.unscripted.append(f"slash:{skill}")
            resp = SlashResponse()
        else:
            resp = responses[min(n, len(responses) - 1)]  # last response is sticky
        if target:
            self.hctx.apply(target, resp.effects)
        if resp.callback is not None:
            resp.callback(self.hctx, target)
        return ActionResult(
            output=resp.output.format(id=target),
            stderr="",
            exit_code=resp.exit_code,
            duration_ms=1,
        )

    # -- stub inner loop ----------------------------------------------------

    def _run_inner(self, action: str) -> ActionResult:
        parts = shlex.split(action)
        _, run_dir, issue_id, readiness, outcome = parts[:5]
        n = self.inner_counts.get(issue_id, 0)
        self.inner_counts[issue_id] = n + 1
        self._consumed = (self.inner_counts, issue_id)
        self.inner_log.append(issue_id)
        runs = self.scenario.inner_runs.get(issue_id, ())
        if not runs:
            self.unscripted.append(f"inner:{issue_id}")
            spec = InnerRun(terminal="failed", legacy_class="quality")
        else:
            spec = runs[min(n, len(runs) - 1)]  # last run is sticky
        rd = Path(run_dir)
        self.hctx.apply(issue_id, spec.effects)
        if spec.broke_down:
            (rd / "refine-broke-down").write_text("1")
        if spec.legacy_class is not None:
            (rd / "refine-terminal-class").write_text(spec.legacy_class)
        out = ""
        if spec.write_record:
            cmd = [
                "ll-issues",
                "run-record",
                "write",
                issue_id,
                "--run-dir",
                run_dir,
                "--writer",
                "refine-to-ready-issue",
            ]
            if spec.legacy_class is not None:
                cmd += ["--legacy-class", spec.legacy_class]
            else:  # done paths pass the context thresholds (write_done_record)
                cmd += ["--readiness-threshold", readiness, "--outcome-threshold", outcome]
            if spec.evidence_refs:
                cmd += ["--evidence-refs", *spec.evidence_refs]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            out = proc.stdout
        token = {"done": "DONE", "failed": "FAILED", "error": "ERROR"}[spec.terminal]
        return ActionResult(output=f"{out}{token}\n", stderr="", exit_code=0, duration_ms=1)


# ---------------------------------------------------------------------------
# Project / environment setup
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, Mapping) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


#: Fork server for the ``ll-issues`` / ``ll-config`` shims. A fresh ``ll-issues``
#: process spends ~200ms importing ``little_loops`` and autodev makes ~35 calls per
#: issue pass, so a scenario is dominated by interpreter start-up. The server
#: imports ``little_loops.cli`` once, then forks a pristine copy per call; the
#: child adopts the client's stdin/stdout/stderr (passed over the socket), cwd,
#: environment and argv, runs the real ``main_*`` and reports the exit code. Each
#: call still runs in its own process from the same import-time state, so no
#: cache or global survives from one call to the next. Set
#: ``AUTODEV_HARNESS_SLOW_CLI=1`` to bypass it (plain ``python -c`` per call).
_CLI_SERVER = r"""
import json, os, socket, struct, sys, traceback
from little_loops.cli import main_config, main_issues

MAINS = {"ll-issues": main_issues, "ll-config": main_config}


def _recv_exact(conn, n, head=b""):
    buf = head
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise EOFError("client closed")
        buf += chunk
    return buf


def _child(conn):
    code = 1
    try:
        head, fds, _flags, _addr = socket.recv_fds(conn, 4, 3)
        (size,) = struct.unpack("!I", _recv_exact(conn, 4, head))
        req = json.loads(_recv_exact(conn, size))
        for target, fd in zip((0, 1, 2), fds):
            os.dup2(fd, target)
            os.close(fd)
        os.chdir(req["cwd"])
        os.environ.clear()
        os.environ.update(req["env"])
        sys.argv = [req["prog"], *req["args"]]
        try:
            rc = MAINS[req["prog"]]()
            code = rc if isinstance(rc, int) else 0
        except SystemExit as exc:
            if exc.code is None:
                code = 0
            elif isinstance(exc.code, int):
                code = exc.code
            else:
                print(exc.code, file=sys.stderr)
                code = 1
        except BaseException:
            traceback.print_exc()
            code = 1
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        try:
            conn.sendall(struct.pack("!i", code))
        except Exception:
            pass
        os._exit(0)


def main(name):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(name)
    srv.listen(64)
    open("cli.ready", "w").close()
    while True:
        conn, _ = srv.accept()
        if os.fork() == 0:
            srv.close()
            _child(conn)
        conn.close()
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            pass


main(sys.argv[1])
"""

#: Client shim (``ll-issues`` / ``ll-config``). ``-SE``: stdlib only, fast start.
#: Falls back to a plain interpreter per call when the server is absent, the
#: switch is set, or the fds cannot be passed; a call whose server child never
#: reported an exit code is logged to ``cli-failures.log`` (surfaced in results).
_CLI_CLIENT = r"""#!{py} -SE
import json, os, socket, struct, sys
NAME, FN, H, PY = {name!r}, {fn!r}, {hdir!r}, {py!r}
with open(os.path.join(H, "cli-calls.log"), "a") as f:
    f.write(NAME + " " + " ".join(sys.argv[1:]) + "\n")


def slow():
    code = "import sys; from little_loops.cli import %s; sys.exit(%s())" % (FN, FN)
    os.execv(PY, [PY, "-c", code, *sys.argv[1:]])


if os.environ.get("AUTODEV_HARNESS_SLOW_CLI") or not os.path.exists(os.path.join(H, "cli.ready")):
    slow()
cwd = os.getcwd()
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    os.chdir(H)  # relative connect: AF_UNIX paths are capped near 104 bytes
    try:
        s.connect("cli.sock")
    finally:
        os.chdir(cwd)
    req = json.dumps(
        {{"prog": NAME, "args": sys.argv[1:], "cwd": cwd, "env": dict(os.environ)}}
    ).encode()
    socket.send_fds(s, [struct.pack("!I", len(req))], [0, 1, 2])
    s.sendall(req)
except OSError:
    slow()
data = b""
while len(data) < 4:
    chunk = s.recv(4 - len(data))
    if not chunk:
        break
    data += chunk
if len(data) != 4:
    with open(os.path.join(H, "cli-failures.log"), "a") as f:
        f.write(NAME + " " + " ".join(sys.argv[1:]) + "\n")
    sys.exit(70)
sys.exit(struct.unpack("!i", data)[0])
"""


def _write_shims(bin_dir: Path, harness_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    (harness_dir / "cli_server.py").write_text(_CLI_SERVER)
    for name, fn in (("ll-issues", "main_issues"), ("ll-config", "main_config")):
        shim = bin_dir / name
        shim.write_text(_CLI_CLIENT.format(py=py, name=name, fn=fn, hdir=str(harness_dir)))
        shim.chmod(0o755)
    (bin_dir / "python3").write_text(f'#!/bin/sh\nexec "{py}" "$@"\n')
    (bin_dir / "python3").chmod(0o755)
    (bin_dir / "ll-auto").write_text(
        "#!/bin/sh\n"
        'ID=""\n'
        'while [ $# -gt 0 ]; do case "$1" in --only) ID="$2"; shift 2;; *) shift;; esac; done\n'
        f'H="{harness_dir}"\n'
        'printf \'%s\\n\' "$ID" >> "$H/ll-auto-calls.txt"\n'
        'sed "s/{id}/$ID/g" "$H/ll-auto-output" 2>/dev/null\n'
        'if [ -f "$H/ll-auto-close" ]; then\n'
        '  ll-issues set-status "$ID" done >/dev/null 2>&1 || true\n'
        "fi\n"
        'exit "$(cat "$H/ll-auto-exit" 2>/dev/null || echo 0)"\n'
    )
    (bin_dir / "ll-auto").chmod(0o755)


def _start_cli_server(harness_dir: Path) -> subprocess.Popen[bytes] | None:
    """Start the ``ll-issues`` fork server (``None``: shims use the slow path)."""
    if os.environ.get("AUTODEV_HARNESS_SLOW_CLI"):
        return None
    ready = harness_dir / "cli.ready"
    with (harness_dir / "cli-server.log").open("wb") as log:
        server = subprocess.Popen(
            [sys.executable, str(harness_dir / "cli_server.py"), "cli.sock"],
            cwd=harness_dir,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            # macOS: the ObjC runtime reads this at process start; forked children
            # replace os.environ with the caller's, so it never reaches ll-issues.
            env={**os.environ, "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES"},
        )
    deadline = time.monotonic() + 15
    while not ready.exists():
        if server.poll() is not None or time.monotonic() > deadline:
            server.kill()
            server.wait()
            return None
        time.sleep(0.02)
    return server


def _git(project: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )


def _setup_project(root: Path, scenario: Scenario) -> Path:
    project = root / "project"
    (project / ".ll").mkdir(parents=True)
    for d in _TYPE_DIRS.values():
        (project / ".issues" / d).mkdir(parents=True)
    cfg = _deep_merge(DEFAULT_CONFIG, scenario.config_overrides)
    (project / ".ll" / "ll-config.json").write_text(json.dumps(cfg, indent=2))
    write_issue(project, scenario.issue_id, frontmatter=scenario.frontmatter, body=scenario.body)
    for extra in scenario.extra_issues:
        fm: dict[str, Any] = {"status": extra.status}
        if extra.parent is not None:
            fm["parent"] = extra.parent
        fm.update(extra.frontmatter)
        write_issue(project, extra.issue_id, frontmatter=fm, body=DEFAULT_BODY, title=extra.title)
    for rel, text in scenario.project_files.items():
        p = project / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    (project / ".gitignore").write_text(".loops/\n")
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "harness@example.invalid")
    _git(project, "config", "user.name", "harness")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")
    return project


def _lines(path: Path) -> list[str]:
    try:
        return [ln for ln in path.read_text().splitlines() if ln.strip()]
    except OSError:
        return []


def _read_token(run_dir: Path, issue_id: str, writer: str) -> str:
    """``ll-issues run-record read --format token``, in-process.

    Harness issues carry ``id: <issue_id>`` in frontmatter, so the canonical
    record id the CLI would resolve is *issue_id* itself.
    """
    from little_loops.run_record import read_run_record, record_token

    return record_token(read_run_record(run_dir, writer, issue_id))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _load_fsm(
    loops_dir: Path,
    autodev_transform: Callable[[dict[str, Any]], dict[str, Any]] | None,
) -> tuple[Any, Path]:
    from little_loops.fsm.validation import load_and_validate

    path = AUTODEV_YAML
    if autodev_transform is not None:
        data = yaml.safe_load(AUTODEV_YAML.read_text())
        path = loops_dir / "autodev.yaml"
        path.write_text(yaml.safe_dump(autodev_transform(data), sort_keys=False))
    fsm, _ = load_and_validate(path, raise_on_error=False)
    return fsm, path


def _seed_context(fsm: Any, scenario: Scenario, run_dir: Path) -> None:
    from little_loops.fsm.context_seed import (
        derive_input_hash,
        seed_confidence_thresholds,
        seed_parameter_defaults,
    )

    # Mirrors cli/loop/run.py's order: parameter defaults, positional input,
    # --context overrides, run_dir, input_hash, config thresholds.
    seed_parameter_defaults(fsm.context, fsm.parameters)
    fsm.context["input"] = scenario.queue if scenario.queue is not None else scenario.issue_id
    fsm.context["quality_gate"] = "false"
    fsm.context.update(scenario.context)
    fsm.context["run_dir"] = str(run_dir) + "/"
    derive_input_hash(fsm.context)
    seed_confidence_thresholds(fsm.context)


def run_autodev(
    scenario: Scenario,
    tmp_path: Path,
    monkeypatch: Any,
    *,
    prepare_issue_yaml: Path | None = None,
    autodev_transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> AutodevResult:
    """Run ``autodev`` on *scenario* and collect its artifacts.

    Args:
        scenario: What to run (see :class:`Scenario`).
        tmp_path: A fresh directory (pytest's ``tmp_path``).
        monkeypatch: pytest's ``monkeypatch`` (cwd, PATH, PYTHONPATH, sleep patch).
        prepare_issue_yaml: Replacement wrapper loop, copied into the temporary
            ``loops_dir`` as ``prepare-issue.yaml`` (default: the builtin one).
        autodev_transform: Function over the parsed ``autodev.yaml`` mapping; its
            result is written into the temporary ``loops_dir`` and run instead.
    """
    from little_loops.fsm.executor import FSMExecutor

    root = tmp_path
    project = _setup_project(root, scenario)
    harness_dir = root / "harness"
    loops_dir = harness_dir / "loops"
    loops_dir.mkdir(parents=True)
    (loops_dir / "refine-to-ready-issue.yaml").write_text(STUB_REFINE_TO_READY)
    if prepare_issue_yaml is not None:
        (loops_dir / "prepare-issue.yaml").write_text(Path(prepare_issue_yaml).read_text())
    bin_dir = harness_dir / "bin"
    _write_shims(bin_dir, harness_dir)
    (harness_dir / "ll-auto-output").write_text(scenario.ll_auto.output)
    (harness_dir / "ll-auto-exit").write_text(str(scenario.ll_auto.exit_code))
    if scenario.ll_auto.close:
        (harness_dir / "ll-auto-close").write_text("1")

    run_dir = project / ".loops" / "runs" / "autodev-harness"
    run_dir.mkdir(parents=True)

    monkeypatch.chdir(project)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    pythonpath = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH", f"{SCRIPTS_DIR}{os.pathsep}{pythonpath}" if pythonpath else str(SCRIPTS_DIR)
    )
    # Ambient automation env leaks into every descendant (see MEMORY: LL_AUTOMATION).
    for var in ("LL_AUTOMATION", "LL_HOST_CLI", "LL_HOOK_HOST"):
        monkeypatch.delenv(var, raising=False)

    sleeps: list[float] = []

    def _instant_sleep(self: Any, duration: float, on_heartbeat: Any = None) -> float:
        sleeps.append(float(duration))
        return float(duration)

    monkeypatch.setattr(FSMExecutor, "_interruptible_sleep", _instant_sleep)

    hctx = HarnessContext(project=project, run_dir=run_dir, harness_dir=harness_dir)
    tracker = _Tracker()
    inner_counts: dict[str, int] = {}
    slash_counts: dict[str, int] = {}
    runner = ScriptedRunner(
        scenario, hctx, tracker, inner_counts=inner_counts, slash_counts=slash_counts
    )
    persistence = StatePersistence("autodev", harness_dir / "state", instance_id="autodev-harness")

    def _executor() -> PersistentExecutor:
        fsm, fsm_path = _load_fsm(loops_dir, autodev_transform)
        _seed_context(fsm, scenario, run_dir)
        ex = PersistentExecutor(
            fsm,
            persistence=persistence,
            loops_dir=loops_dir,
            action_runner=runner,
            working_dir=project,
            loop_yaml_path=fsm_path,
        )
        ex.event_bus.register(tracker)
        return ex

    crashed_at: dict[str, Any] | None = None
    resumed_terminated_by: str | None = None
    server = _start_cli_server(harness_dir)
    try:
        try:
            result = _executor().run()
        except HarnessCrash:
            crashed_at = runner.crashed_at
            resumed = _executor().resume()
            assert resumed is not None, "harness: persisted state was not resumable"
            result = resumed
            resumed_terminated_by = result.terminated_by
    finally:
        if server is not None:
            server.kill()
            server.wait()

    events = tracker.events
    enters = [e for e in events if e.get("event") == "state_enter"]
    path = [str(e["state"]) for e in enters if not e.get("depth")]
    wrapper_path = [str(e["state"]) for e in enters if e.get("loop") == "prepare-issue"]
    full_path = [f"{e.get('loop')}:{e['state']}" for e in enters]
    dequeued = []
    for e in events:
        if (
            e.get("event") == "action_complete"
            and e.get("state") == "dequeue_next"
            and not e.get("depth")
            and e.get("exit_code") == 0
        ):
            out = (e.get("output_preview") or "").strip().splitlines()
            if out:
                dequeued.append(out[-1].strip())

    issues: dict[str, tuple[str | None, str | None]] = {}
    for p in sorted((project / ".issues").rglob("*.md")):
        fm = parse_frontmatter(p.read_text(), coerce_types=True)
        iid = str(fm.get("id") or p.stem)
        issues[iid] = (
            str(fm["status"]) if fm.get("status") is not None else None,
            str(fm["deferred_reason"]) if fm.get("deferred_reason") is not None else None,
        )
    main = issues.get(scenario.issue_id, (None, None))
    loop_yaml_paths: dict[str, list[str]] = {}
    for e in events:
        if e.get("event") == "loop_start" and e.get("loop_yaml_path"):
            paths = loop_yaml_paths.setdefault(str(e.get("loop")), [])
            if e["loop_yaml_path"] not in paths:
                paths.append(str(e["loop_yaml_path"]))

    summary: dict[str, Any] | None = None
    if (run_dir / "summary.json").exists():
        summary = json.loads((run_dir / "summary.json").read_text())
    rc_file = run_dir / "autodev-repair-cycle-count.txt"
    ledger_names = (
        "autodev-scores-absent.txt",
        "autodev-decision-unresolved.txt",
        "autodev-gate-blocked.txt",
        "autodev-proof-gate-infra.txt",
        "autodev-not-started.txt",
        "autodev-new-children.txt",
    )
    return AutodevResult(
        terminated_by=result.terminated_by,
        final_state=result.final_state,
        path=path,
        wrapper_path=wrapper_path,
        full_path=full_path,
        skipped=_lines(run_dir / "autodev-skipped.txt"),
        queue=_lines(run_dir / "autodev-queue.txt"),
        staged=_lines(run_dir / "autodev-staged.txt"),
        passed=_lines(run_dir / "autodev-passed.txt"),
        unverified=_lines(run_dir / "autodev-unverified.txt"),
        dequeued=dequeued,
        record_token=_read_token(run_dir, scenario.issue_id, "prepare-issue"),
        inner_record_token=_read_token(run_dir, scenario.issue_id, "refine-to-ready-issue"),
        records={i: _read_token(run_dir, i, "prepare-issue") for i in issues},
        inner_records={i: _read_token(run_dir, i, "refine-to-ready-issue") for i in issues},
        status=main[0],
        deferred_reason=main[1],
        issues=issues,
        loop_yaml_paths=loop_yaml_paths,
        summary=summary,
        slash_commands=list(runner.slash_log),
        repair_cycle_count=rc_file.read_text().strip() if rc_file.exists() else None,
        ll_auto_calls=_lines(harness_dir / "ll-auto-calls.txt"),
        ledgers={n: lines for n in ledger_names if (lines := _lines(run_dir / n))},
        sleeps=sleeps,
        unscripted=list(runner.unscripted),
        cli_calls=_lines(harness_dir / "cli-calls.log"),
        cli_failures=_lines(harness_dir / "cli-failures.log"),
        steps=runner.step,
        crashed_at=crashed_at,
        resumed_terminated_by=resumed_terminated_by,
        run_dir=run_dir,
        project=project,
        inner_calls=list(runner.inner_log),
    )
