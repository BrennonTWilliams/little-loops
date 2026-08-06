---
id: BUG-3085
type: BUG
title: Learning gate's 900s subprocess timeout preempts the configured 86400s queue-wait
  budget
priority: P3
status: done
captured_at: '2026-08-06T16:17:02Z'
completed_at: '2026-08-06T18:06:27Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
verify_verdict: VALID
labels:
- learning-gate
- fsm-concurrency
- config
relates_to:
- BUG-3083
- ENH-3073
confidence_score: 98
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
---

# BUG-3085: Learning gate's 900s subprocess timeout preempts the configured 86400s queue-wait budget

## Summary

The ENH-3073 follow-up in `learning_tests/gate.py` (now committed as
`98789489`) adds `--queue` to the `ll-loop run ready-to-implement-gate`
invocation, plus `_QUEUE_WAIT_TIMEOUT_SECONDS = 900` as a
`subprocess.run(timeout=...)` bound.

The child's own queue-wait budget is `loops.queue_wait_timeout_seconds`, which
defaults to **86400** (`config-schema.json:969-973`) and is read at
`cli/loop/run.py:401`. The outer 900s bound therefore always wins by nearly two
orders of magnitude: the configured value can never take effect, and the child
is SIGKILLed mid-queue rather than timing out cleanly on its own terms.

Because this repo is `local-editable` for every little-loops project on this
machine, the fix (or its absence) is immediately live everywhere.

## Steps to Reproduce

1. Hold a repo-root scope lock for >15 minutes (e.g. a long
   `refine-to-ready-issue` run — see BUG-3083).
2. Run `ll-auto --only <ID>` on an issue with `learning_tests_required`.
3. The gate subprocess queues, waits 900s, and is killed by
   `subprocess.run`'s timeout — never reaching its own 86400s budget.
   `ll-auto` reports `impl_failed`.

## Root Cause

Two independent timeout budgets govern the same wait, and the caller's is
unconditionally the smaller:

- `scripts/little_loops/learning_tests/gate.py` — `_QUEUE_WAIT_TIMEOUT_SECONDS = 900`,
  passed as `subprocess.run(..., timeout=...)`.
- `scripts/little_loops/cli/loop/run.py:401` — `_budget = _config.loops.queue_wait_timeout_seconds`,
  default 86400.

`subprocess.run`'s timeout path calls `Popen.kill()` (SIGKILL on POSIX), so the
child's `atexit` cleanup for its `.queue` entry and `.pid` file does not run.

## Current Behavior

- `loops.queue_wait_timeout_seconds` is dead config for this call path.
- The queued child dies by SIGKILL, orphaning its `.loops/.queue/<uuid>.json`
  entry and `.loops/.running/<instance>.pid`.

## Expected Behavior

One authoritative budget for the queue wait. The caller either adopts the
configured value or explicitly passes its own bound down to the child so both
layers agree, and the child exits its wait gracefully.

## Proposed Solution

Preferred: pass the intent down rather than racing it from outside.

1. If `ll-loop run` accepts a queue-timeout flag, pass it explicitly so the
   child's budget *is* the caller's budget. Grep the current `ll-loop run`
   argument surface before adding one — the flag may already exist.
2. If it does not, add `--queue-timeout SECONDS` to `ll-loop run` overriding
   `_budget` at run.py:401.
3. Keep an outer `subprocess.run(timeout=...)` only as a backstop, set
   comfortably *above* the child's budget (e.g. child budget + slack), so it
   fires only when the child is genuinely wedged — not as the normal exit path.
4. Decide the right default wait for the ll-auto call path deliberately. 900s is
   defensible for a foreground `ll-auto`; 86400s clearly is not. If 900s is the
   intended policy, set it as the child's budget rather than as an external kill.

Note: the orphaned `.queue` entry is self-healing — `read_queue_entries()`
prunes dead-PID entries (`cli/loop/_helpers.py:206-217`, BUG-1360) — so orphan
starvation is not a live risk. Do not over-engineer that part.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- Confirmed: no `--queue-timeout` (or similarly named) flag exists on `ll-loop run` — every `add_argument` call in `cli/loop/__init__.py`'s `run_parser` registration was checked; only `--queue`/`-q` (`cli/loop/__init__.py:281-283`) and `--no-lock` (`:284-286`) exist. Proposed Solution step 1 ("grep the arg surface") is answered: a new flag must be added, not reused.
- Two established "flag overrides config" mechanisms exist elsewhere in this codebase and disagree on carrier. `--handoff-threshold` (`cli_args.py:139`) threads through as an env var (`cli/loop/run.py:216-223`) and is separately re-emitted onto a *child* `ll-loop run` invocation's argv by a parent-process subprocess builder (`cli/loop/_helpers.py:1637-1639` — the closest existing precedent for a parent reading its own `args.<flag>` and re-appending `--flag value` to a child `ll-loop run` call, the exact shape this issue's fix needs). `--idle-timeout` (`cli_args.py:125`) instead mutates the already-loaded config object directly (`cli/auto.py:80-81`: `config.automation.idle_timeout_seconds = args.idle_timeout`). Both share a `default=None` + `if value is not None: override` idiom.
- No existing precedent in this codebase for computing an outer `subprocess.run(timeout=...)` as inner-budget-plus-slack; the one adjacent example (`fsm/host_guard.py:284`, `self._thread.join(timeout=self.interval + 1.0)`) adds slack to a thread join, not a subprocess timeout.
- `_config.loops.queue_wait_timeout_seconds` has no dedicated getter anywhere in `scripts/little_loops/config/` — every call site, including `cli/loop/run.py:401`, reads it as a direct attribute chain off `_config.loops`; this is the established convention for the whole `_config.loops.*` field family, not a gap to fix.

## Program Design

### Types

N/A — no new data type or shape is introduced; this is a budget-reconciliation
fix over existing `int` values (`_QUEUE_WAIT_TIMEOUT_SECONDS`,
`loops.queue_wait_timeout_seconds`).

- `run_learning_gate_for_issue(issue_id, targets, working_dir)` — builds the child `cmd` and calls `subprocess.run(cmd, timeout=_QUEUE_WAIT_TIMEOUT_SECONDS)`, `scripts/little_loops/learning_tests/gate.py:65-142`
- `cmd_run(loop_name, args, loops_dir, logger)` — reads `_budget` at `scripts/little_loops/cli/loop/run.py:92-401`; no parameter or `args.*` flag lets a caller override `_budget` today

Full context: `run_learning_gate_for_issue()` (`gate.py:65`) builds
`cmd = ["ll-loop", "run", "ready-to-implement-gate", "--context",
f"targets={...}", "--queue"]` (lines 121-134) and calls
`subprocess.run(cmd, capture_output=True, text=True, cwd=working_dir,
timeout=_QUEUE_WAIT_TIMEOUT_SECONDS)` (lines 136-142), where
`_QUEUE_WAIT_TIMEOUT_SECONDS = 900` (line 27) is a hard-coded module
constant, not derived from config. `cmd_run()` reads
`_budget = _config.loops.queue_wait_timeout_seconds` (line 401) inside the
`--queue` retry loop (lines 377-424).

### Call Path

`run_learning_gate_for_issue()` (`gate.py:65`) → spawns child process
`ll-loop run ready-to-implement-gate --context targets=... --queue`, bounded
by the parent's `subprocess.run(timeout=900)` (`gate.py:136-142`) → child
process enters `cmd_run()` (`cli/loop/run.py:92`) → `--queue` conflict-wait
retry loop (`run.py:377-424`) polls `lock_manager.wait_for_scope(...)` against
`_budget = _config.loops.queue_wait_timeout_seconds` (`run.py:401`, default
86400) → on the parent's 900s expiry, `subprocess.run` calls `Popen.kill()`
(SIGKILL), bypassing the child's `atexit.register(_cleanup_pid)` (`run.py:359`),
`atexit.register(_cleanup_queue_entry)` (`run.py:394`), and the
`lock_manager.release(...)` in a `finally:` (`run.py:610`) — none of which run
on SIGKILL, since `register_loop_signal_handlers()` (`cli/loop/_helpers.py:220-244`)
only installs SIGINT/SIGTERM handlers and SIGKILL is uncatchable.

### Decision Rules

No existing `--queue-timeout` (or similarly named) flag exists on `ll-loop run`
today (confirmed by grepping every `add_argument` call in
`cli/loop/__init__.py`'s `run_parser` registration — only `--queue`/`-q` and
`--no-lock` exist). Two established "flag overrides config" mechanisms exist
elsewhere in this codebase for this exact shape and disagree on carrier:
`--handoff-threshold` threads through as an env var
(`cli/loop/run.py:216-223`) and is separately re-emitted onto a *child*
`ll-loop run` invocation's argv by a parent-process subprocess builder
(`cli/loop/_helpers.py:1637-1639` — the closest existing precedent for what
this fix needs: a parent reading its own flag and re-appending it to a child
`ll-loop run` call); `--idle-timeout` instead mutates the already-loaded
config object directly (`cli/auto.py:80-81`). Both share a `default=None` +
`if value is not None: override` idiom. Which of the two carriers to use for
a new `--queue-timeout`-style flag, and the exact numeric relationship between
the outer `subprocess.run` backstop and the inner budget it should exceed, is
not resolved by existing convention — no precedent for the backstop's slack
computation exists in this codebase (see Proposed Solution → Codebase
Research Findings) — and is left to the implementer to decide.

## Impact

Low severity but it makes a documented config knob inert and hides the real
tuning surface. Worth fixing before the ENH-3073 work is committed, since the
current shape bakes in a hardcoded constant that silently overrides user config.

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/learning_tests/gate.py` | `run_learning_gate_for_issue`, targets branch | Reconcile the two budgets |
| `scripts/little_loops/cli/loop/run.py` | `cmd_run`, ~line 401 | Optional `--queue-timeout` |
| `scripts/little_loops/config-schema.json` | `loops.queue_wait_timeout_seconds` | Reconsider the 86400 default |
| `scripts/tests/test_learning_tests_gate.py` | — | Assert the effective budget |

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:46,~1110-1147` — production caller of `run_learning_gate_for_issue()`; the `impl_failed` branch observes any verdict-timing change from this fix, and is the only in-repo call site to update if the function's signature grows a new override parameter [Agent 1/2 finding]
- `scripts/little_loops/cli/loop/__init__.py:281-286,314,1022` — `--queue`/`-q` inline registration, `add_handoff_threshold_arg(run_parser)` precedent wiring call, and the `cmd_run()` call site (`main_loop`) [Agent 1/2 finding]
- `scripts/little_loops/cli/queue.py:880` — calls `cmd_run()` (`main_queue`) [Agent 1 finding]
- `scripts/little_loops/cli/loop/_helpers.py:1637-1639` — `--handoff-threshold` argv re-emit precedent (parent reads `args.handoff_threshold`, re-appends `--handoff-threshold value` to a child `ll-loop run` invocation); a new `--queue-timeout` flag needs its own emission logic in `gate.py`, this is not shared code [Agent 1/2 finding]
- `scripts/little_loops/cli_args.py:125-150` — `add_idle_timeout_arg()`/`add_handoff_threshold_arg()`; a new `add_queue_timeout_arg()` would follow this shape [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:570,~6743-6760` — `loops.queue_wait_timeout_seconds` config field doc and `run_learning_gate_for_issue()` signature/behavior doc; both need updating if a parameter is added [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md:305` — mentions `queue_wait_timeout_seconds` [Agent 1 finding]
- `docs/guides/LOOPS_GUIDE.md:796,848,1285` — the known `queue_wait_timeout_seconds` mention plus two more `--queue` UX mentions that would read confusingly if a new `--queue-timeout` flag changes the effective wait without being documented alongside them [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:933` — mentions `queue_wait_timeout_seconds` [Agent 1 finding]
- `docs/reference/CLI.md` — `ll-loop run` flag table (`~572-608`): `--queue` row `~594`, `--handoff-threshold` row `~606`, `--no-lock` row `~608`; a new `--queue-timeout` row is needed if that flag is added [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_worktree.py:924-936` — `_mock_br_config()`, the existing convention for exercising `cmd_run`'s queue-wait budget with a concrete `loops.queue_wait_timeout_seconds` value [Agent 3 finding]
- `scripts/tests/test_ll_loop_parsing.py:310-403` — `--handoff-threshold` parsing precedent tests (isolated + real-parser wiring); model a new `--queue-timeout` flag test after this shape [Agent 3 finding]
- `scripts/tests/test_cli_args.py:404-442,749-786` — argparse helper unit-test precedent for `add_handoff_threshold_arg()` [Agent 3 finding]
- `scripts/tests/test_cli_loop_queue.py` (`TestQueueRetryOnRace`, `_make_args()` helper `:12-41`) — closest existing coverage of `cmd_run`'s `--queue` retry loop (`run.py:377-424`); the `_make_args()` fixture needs a new default key if `--queue-timeout` is added, mirroring the existing `"handoff_threshold": None` entry [Agent 3 finding]
- `scripts/tests/test_config.py:648-660,840` — `LoopsConfig` default/round-trip assertions; `test_from_dict_with_defaults` breaks if the 86400 default changes [Agent 1/2 finding]
- `scripts/tests/test_config_properties.py:44` — Hypothesis strategy currently bounds `queue_wait_timeout_seconds` to `1..600`, which does not reach the 900s boundary this issue fixes [Agent 2/3 finding]
- `scripts/tests/test_feat3033_idle_timeout.py` — precedent test shape for a similar timeout-override mechanism (FEAT-3033): schema round-trip, kwarg forwarding, end-to-end routing [Agent 1 finding]
- `scripts/tests/test_learning_tests_gate.py:280-294` (`test_scope_conflict_never_clearing_yields_impl_failed`) — hard-codes `subprocess.TimeoutExpired(cmd="ll-loop", timeout=900)` in its mock; won't fail mechanically (fully mocked) but the literal becomes stale once `_QUEUE_WAIT_TIMEOUT_SECONDS` is no longer the operative bound — update alongside the fix [Agent 3 finding, likely to break]
- Coverage gap: no existing test asserts the actual `timeout=` kwarg value passed to `subprocess.run` in `gate.py:136-142` — `test_invocation_passes_queue_flag` only checks `cmd`, never `mock_sub.call_args.kwargs["timeout"]` [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- `scripts/little_loops/cli/loop/__init__.py:281-286` — `--queue`/`-q` and `--no-lock` argparse registration; no queue-timeout flag exists here today
- `scripts/little_loops/config/features.py:748,757` — `queue_wait_timeout_seconds: int = 86400` dataclass field and its loader default, mirroring `config-schema.json`'s default
- `scripts/little_loops/cli/loop/run.py:356-359,366-394,606-610` — cleanup registration skipped by SIGKILL: `atexit.register(_cleanup_pid)` (line 359), `atexit.register(_cleanup_queue_entry)` (line 394), and `lock_manager.release(...)` inside a `finally:` (line 610) — none of these run when the parent's `subprocess.run(timeout=900)` SIGKILLs a still-queued child
- `scripts/little_loops/cli/loop/_helpers.py:220-244` — `register_loop_signal_handlers()` installs SIGINT/SIGTERM handlers only; SIGKILL is uncatchable, confirming the atexit/finally skip above is unavoidable via signal handling
- `scripts/tests/test_cli_loop_worktree.py:924-936` — `_mock_br_config()` is the existing convention for exercising `cli/loop/run.py`'s queue-wait budget in a test: mocks the whole `BRConfig` return value and sets `loops.queue_wait_timeout_seconds` directly, rather than monkeypatching a module constant
- `scripts/tests/test_learning_tests_gate.py:263-278,280-294` — existing tests assert `"--queue" in cmd` and that a `TimeoutExpired` (with `timeout=900` hard-coded into the mock's constructor, not read from `_QUEUE_WAIT_TIMEOUT_SECONDS`) yields `impl_failed`; neither asserts the actual `timeout=` kwarg value passed to `subprocess.run`, nor any relationship to `loops.queue_wait_timeout_seconds`

## Implementation Steps

1. Grep the `ll-loop run` arg surface for an existing queue-timeout flag.
2. Wire the caller's intended budget into the child.
3. Reduce the outer `subprocess.run` timeout to a backstop above that budget.
4. Test that the configured value is what actually governs the wait.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- If a `--queue-timeout` flag is added: register it via a new `add_queue_timeout_arg()` in `cli_args.py` (following `add_handoff_threshold_arg()`), wire it onto `run_parser` in `cli/loop/__init__.py`, and forward it from `gate.py`'s child-`cmd` build (parallel to, but not shared with, the `--handoff-threshold` argv re-emit at `cli/loop/_helpers.py:1637-1639`)
- Add a test asserting the actual `timeout=` kwarg value passed to `subprocess.run` in `gate.py` — no existing test covers this
- Update `scripts/tests/test_learning_tests_gate.py:280-294`'s hard-coded `TimeoutExpired(timeout=900)` mock to match the new effective bound
- If a `--queue-timeout` flag is added, add parsing tests following `scripts/tests/test_ll_loop_parsing.py:310-403`'s `--handoff-threshold` precedent, and a fixture key in `scripts/tests/test_cli_loop_queue.py`'s `_make_args()` helper
- Update `docs/reference/CLI.md`'s `ll-loop run` flag table if a new flag is added; review `docs/guides/LOOPS_GUIDE.md:796,848,1285`, `docs/reference/API.md:570,~6743-6760`, `docs/development/TROUBLESHOOTING.md:305`, and `docs/reference/CONFIGURATION.md:933` for consistency with the new behavior
- Note (no action required by this issue): `ENH-3084` touches the same `impl_failed` verdict boundary in `gate.py`/`issue_manager.py` — if it lands first and widens the verdict `Literal`, this fix's `TimeoutExpired` branch may need to return a different verdict string; check sequencing before implementing

## Resolution

Added a `--queue-timeout` flag (`add_queue_timeout_arg()` in `cli_args.py`,
following `add_handoff_threshold_arg()`) wired onto `ll-loop run`'s
`run_parser`. `cmd_run()` (`cli/loop/run.py:401-403`) now overrides its
`_budget` with `args.queue_timeout` when set, otherwise falling back to the
existing `loops.queue_wait_timeout_seconds` config default (86400).

`run_learning_gate_for_issue()` (`gate.py`) reads that same configured budget
via `BRConfig(working_dir).loops.queue_wait_timeout_seconds`, forwards it
explicitly to the child as `--queue-timeout <budget>`, and sets its own outer
`subprocess.run(timeout=...)` to `budget + 60s` slack — a pure backstop
against a genuinely wedged child rather than the normal exit path. The
hard-coded `_QUEUE_WAIT_TIMEOUT_SECONDS = 900` module constant was removed.

ENH-3084 is still `open` (unimplemented), so there was no verdict-`Literal`
sequencing conflict to resolve.

Tests: added coverage in `test_cli_args.py` (flag defaults/parsing),
`test_ll_loop_parsing.py` (real-parser wiring), `test_cli_loop_queue.py`
(the override actually shrinks the retry-loop budget), and
`test_learning_tests_gate.py` (default and custom-config budget forwarding to
`--queue-timeout` and the outer `timeout=` kwarg; updated the stale
`TimeoutExpired(timeout=900)` mock). Docs updated: `CLI.md` flag table,
`LOOPS_GUIDE.md`, `API.md`.

## Status

open


## Session Log
- `/ll:manage-issue` - 2026-08-06T18:05:31 - `10a4dda7-3bc6-4a1f-94ff-501ee053ac5f.jsonl`
- `/ll:ready-issue` - 2026-08-06T17:41:11 - `bf1b7c6a-6d5b-4c22-84fe-40280423c7d4.jsonl`
- `/ll:confidence-check` - 2026-08-06T17:38:52 - `71a5b5c8-8b5f-4779-9a91-00cc882432b5.jsonl`
- `/ll:verify-issues` - 2026-08-06T17:36:28 - `f48b7155-003a-4588-960d-c18302f9b44d.jsonl`
- `/ll:wire-issue` - 2026-08-06T17:34:47 - `38f97e92-ebff-4e04-8108-4ccac1c4b973.jsonl`
- `/ll:refine-issue` - 2026-08-06T17:26:40 - `c2f2d034-a95d-46be-8c19-33b0c6322dd0.jsonl`
- `/ll:capture-issue` - 2026-08-06T16:20:22 - `ee676905-966c-42aa-ac9d-d7d4aaeea91d.jsonl`
