---
id: FEAT-3455
title: Behavioral host-conformance suite runnable against a fake host in CI and live
  hosts behind an env gate
type: FEAT
priority: P2
status: open
testable: true
discovered_date: '2026-09-11'
labels:
- multi-host
- verification
depends_on:
- FEAT-3454
relates_to:
- ENH-3459
- ENH-3460
---

## Summary

Every registered host runner is currently defended by a type check.
`scripts/tests/conformance/test_host_conformance.py` parametrizes over
`_HOST_RUNNER_REGISTRY` and asserts, per host per golden path, that a
`HostInvocation` is constructable — its docstring concedes it never executes the
prompt. Nothing verifies that a runner which constructs a valid invocation actually
produces the behavior the multi-host layer promises callers.

Add a behavioral tier alongside the constructability check: one parameterized test
that actually runs the invocation through `run_claude_command` and asserts observable
outcomes. The fake host (FEAT-3454) runs it on every suite invocation; real host
binaries run the same invariants behind an explicit env gate.

## Why

The multi-host layer's premise is that a caller does not know which host is running;
this is the enforcement half of that promise. Adding another adapter becomes a day of
work against a known contract instead of a rewrite.

## Design Decision: two tiers, not one suite

A live host does not honor directives, so a scripted-exact expected sequence exists
only for the fake. The suite therefore has two tiers:

**Tier 1 — invariants (every target).** Hold for any host, scripted or live:
- If `capabilities.streaming`, the first parsed event is `system/init`.
- Exactly one terminal event (`result` or `turn.completed`) and it is the last
  JSON event on stdout.
- After the terminal event the consumer stops reading (`result_seen` break at
  `subprocess_utils.py:730-735`), the process exits within
  `post_stream_close_grace_seconds`, and `on_result_seen(True)` fires.
- A failure is reported through a stable shape: `CompletedProcess.returncode != 0`
  or `result.is_error`, with `stderr` non-empty. Same keys, same primitive types,
  regardless of host.
- Abort mid-turn: `request_shutdown()` (`subprocess_utils.py:323-335`) during a turn
  yields `TimeoutExpired(output="interrupted")` and the process group is gone.

**Tier 2 — scripted-exact (fake only).** The prompt's directive block encodes the
expected sequence, and the test asserts the consumer saw exactly that: ordered event
kinds, tool-call callbacks, usage callbacks, `stdout_lines`, exit code. Covers
ordering, `result error=`, exit-nonzero-before-terminal, failed start, idle timeout,
`hang` + grace kill. This tier is the replacement for "live-only or untested".

**Keep `test_golden_path_invocation`.** Real hosts skip the behavioral tier unless
the env gate is set, so removing the constructability test would delete the only
per-runner check the Thinky conformance job runs today. Both coexist.

**No fake-for-real substitution.** The fake is one registry entry like any other;
the parametrize picks it up automatically. Real hosts skip Tier 1 with a reason
unless `LL_HOST_CONFORMANCE_LIVE=1`. Substituting the fake for each real host would
produce eight identical runs with no host identity.

## Design Decision: capability assertions are argv facts, not event facts

`HostCapabilities` flags (`permission_skip`, `agent_select`, `tool_allowlist`,
`structured_output`, `workspace_sandboxed`, `streaming`) describe what the runner
puts in argv, not event kinds. Only `streaming` has an observable stream consequence.
So the "capability profile is a promise" rule is enforced as:

- **Negative (unconditional):** when a flag is `False`, the corresponding argv
  marker must be absent from `invocation.args` (`tool_allowlist=False` ⇒ no
  allowlist flag; `structured_output=False` ⇒ `_structured_output_args` returns
  `[]`; `agent_select=False` ⇒ `agent=` is ignored or warns `CapabilityNotSupported`).
  Under-declaring is a bug on equal footing with over-declaring.
- **Positive (gated):** when a flag is `True`, the argv marker is present. Early-
  return when the flag is `False`.
- **`streaming`:** `True` ⇒ Tier 1 init-first assertion applies; `False` ⇒ assert
  no `system/init` event was parsed.

The fake's per-test capability override (FEAT-3454) makes both directions testable
without a real host.

## Current Behavior

`test_golden_path_invocation` (`test_host_conformance.py:64-112`) skips on binary
missing or `HostNotConfigured`, then asserts `invocation.binary` and
`invocation.args` are non-empty. A runner that constructs a syntactically valid
invocation but emits a terminal mid-stream, leaks events after it, or mis-shapes a
failure passes this gate.

## Expected Behavior

- `test_golden_path_behavior(host, golden_path)` runs Tier 1 for every registered
  host: unconditionally for `fake`, behind `LL_HOST_CONFORMANCE_LIVE=1` for the rest.
- `test_scripted_*` cases run Tier 2 against the fake only, on every
  `python -m pytest scripts/tests/` invocation.
- Live runs use a per-target timeout via `run_claude_command(timeout=…)` (the
  production site, `subprocess_utils.py:424`), tighter than the suite's
  `--timeout=120` watchdog. Live runs spend real model tokens and require host
  auth; the docs say so.
- Assertion failures print runner name, golden path, expected kinds, actual kinds,
  and the index of first divergence (shape: `test_streaming_cache_parity.py:182-186`).

## Use Case

A maintainer ports a new CLI host. They wire the five `build_*` methods, then run
`LL_HOST_CONFORMANCE_LIVE=1 pytest -m conformance --conformance-host <name>
scripts/tests/conformance/`. A terminal that is not last, an init that never
arrives, or a failure with no stderr fails loudly with the event-kind diff. The day
it goes green, the host satisfies the multi-host promise.

## Acceptance Criteria

- `test_golden_path_invocation` is retained unchanged in behavior.
- `test_golden_path_behavior(host, golden_path)` exists, parametrized over
  `_HOST_RUNNER_REGISTRY` × `_GOLDEN_PATHS`, drives `run_claude_command` unpatched,
  and asserts every Tier 1 invariant. For `host == "fake"` it runs unconditionally;
  for other hosts it skips with reason unless `LL_HOST_CONFORMANCE_LIVE=1`, and the
  existing skips (binary missing, `HostNotConfigured`) still apply.
- Tier 2 scripted cases exist for: ordered happy path, `result error=`, exit-nonzero
  before terminal, failed start (`stderr` + `exit 1`, no `init`), idle timeout, abort
  via `request_shutdown()`, `hang` + grace kill. Each asserts the exact consumer
  observation and runs in the default suite.
- Capability assertions per the argv-facts rule above: negative direction fires
  unconditionally; positive direction gated. Tested in both directions via the fake's
  capability override.
- The live-spawn guard (`scripts/tests/conftest.py:_match_host_binary` `:237-255`)
  gains a carve-out that lets a real host spawn proceed only when
  `LL_HOST_CONFORMANCE_LIVE=1` **and** the running test carries the `conformance`
  marker; four-shape regression tests in
  `test_conftest_cap.py::TestNoLiveHostCLIGuard` cover it (env set + marker ⇒ None;
  env unset ⇒ tuple; `--version` carve-out preserved; non-host basename unaffected).
- Failure diagnostics include runner name, golden path, expected vs actual kinds,
  first-divergence index.
- `docs/development/CONFORMANCE.md` rewritten for the two tiers, the env gate and
  its cost, the timeout policy, and the capability rule.
- `python -m pytest scripts/tests/` exits 0 with no env vars set; `-m "not
  conformance"` deselects the behavioral tier; `ll-verify-host-map` stays clean.

## Integration Map

### Files to Modify
- `scripts/tests/conformance/test_host_conformance.py` — add `test_golden_path_behavior`, Tier 2 `test_scripted_*` cases, helpers (`_run_and_capture`, `assert_terminal_is_last`, `assert_event_kinds`, `assert_capability_argv`).
- `scripts/tests/conformance/conftest.py` — `live_conformance` fixture reading `LL_HOST_CONFORMANCE_LIVE` at fixture time (so `monkeypatch.setenv` in a test body wins; `conftest.py:1095-1096` precedent); `isolated_env` stays.
- `scripts/tests/conftest.py:_match_host_binary` — env+marker carve-out. The marker check needs the current item; use the same `_current_test_id()` plumbing the collector uses (`:258-270`) or a contextvar set by the `live_conformance` fixture. Prefer the fixture-set flag: it is explicit and needs no item lookup.
- `scripts/tests/test_conftest_cap.py::TestNoLiveHostCLIGuard` (`:281-300`) — four-shape carve-out tests; `_reset_collector` autouse (`:232-238`) still clears `_host_cli_hits`/`_reported_upto`.
- `docs/development/CONFORMANCE.md` — rewrite (currently constructability-only; "Reading the Results" table and baseline board need the new rows).
- `docs/development/TESTING.md:121` (tree line) and `:1048` (markers table) — describe the behavioral tier and env gate.
- `docs/kimi/automation.md:71-82` — optional one-sentence note; the `4 passed` invocation stays valid.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:422-771` — `run_claude_command`, the consumer under test. Callback surface used by the helpers: `on_model_detected`, `on_session_id_detected`, `on_tool_call`, `on_usage_detailed`, `on_result_seen`, `stream_callback`, `on_process_start/end`. Not modified.
- `scripts/little_loops/host_runner.py` — `_HOST_RUNNER_REGISTRY`, `resolve_host_named`, `HostCapabilities`, `CapabilityReport`, `_structured_output_args`. Not modified.
- `scripts/little_loops/fake_host.py` + `FakeHostRunner` (FEAT-3454) — the CI target; directive vocabulary is defined there and consumed here.
- `.github/workflows/ci.yml` — the GitHub-hosted `unit-tests` job runs `-m "not integration and not conformance"`, so the behavioral tier reaches CI only via the Thinky `conformance` job (`:149-207`), which does not set `LL_HOST_CONFORMANCE_LIVE`. Fake-only cases run there; real hosts skip. No workflow change.
- `scripts/tests/test_conftest_cap.py` — loads `conftest.py` via `importlib`; must keep passing after the guard edit.

### Out of scope (owned elsewhere)
- Second divergent fake, composition tests, `TestRegressionGuard` promotion — ENH-3459.
- Drift-gate sync for the second registry entry — ENH-3460. The first entry's drift sync is FEAT-3454's.
- Any change to the runner Protocol or the consumer.

### Conventions in Force
- Parametrize over registry keys with descriptive `ids=` (`test_host_conformance.py:64-71`; `test_host_runner.py:64-74`).
- SKIP-not-FAIL with a concrete `reason=` for environmental gates; FAIL only for observable-behavior deviations (`test_host_conformance.py:96-109`).
- Capability assertions test both directions (`test_host_runner.py:2047-2055`).
- Negative assertions use `not in` with a repr diagnostic (`test_autodev_decision_gate.py:653`).
- Per-target timeout at the production `subprocess` site, suite watchdog `--timeout=120 --timeout-method=thread` (`scripts/pyproject.toml:266-267`).
- `conformance` marker registered identically in `pytest.ini:24` and `scripts/pyproject.toml:280-285`; `--strict-markers` on both.
- Guard carve-out precedent: the `--version` case in `_match_host_binary`; test precedent `test_conftest_cap.py:292-300`.
- `clear_shutdown()` at test start and in teardown whenever a test calls `request_shutdown()` — the event is module-global.

### Tests
- `test_golden_path_behavior[<path>-<host>]` — Tier 1.
- `test_scripted_ordering`, `test_scripted_result_error`, `test_scripted_exit_before_terminal`, `test_scripted_failed_start`, `test_scripted_idle_timeout`, `test_scripted_abort_request_shutdown`, `test_scripted_hang_grace_kill` — Tier 2, fake only.
- `test_capability_argv_negative[<flag>]` / `test_capability_argv_positive[<flag>]` — fake with override, both directions.
- `TestNoLiveHostCLIGuard` four-shape carve-out tests.

## Program Design

### Types
- `Observed`: `(kinds: list[str], init: dict | None, tool_calls: list[ToolCall], usage: TokenUsage | None, result_seen: bool, completed: CompletedProcess | None, error: BaseException | None)` — everything the consumer surfaced, collected via callbacks.
- `TerminalKind = Literal["result", "turn.completed"]`.

### Signatures
- `_run_and_capture(host: str, prompt: str, *, timeout: int, automation: AutomationContext | None = None, tmp_path: Path) -> Observed` — sets `LL_HOST_CLI=host`, wires every callback, calls `run_claude_command` unpatched, catches `TimeoutExpired` into `Observed.error`.
- `assert_terminal_is_last(obs: Observed, *, host: str, golden_path: str) -> None`.
- `assert_event_kinds(obs: Observed, expected: list[str], *, host: str, golden_path: str) -> None` — diff with first-divergence index.
- `assert_capability_argv(invocation: HostInvocation, flag: str) -> None` — negative when `False`, positive when `True`.
- `live_conformance` fixture → `bool`; also sets the guard's opt-in flag for the test's duration.

### Call Path
`pytest` → parametrize over `_HOST_RUNNER_REGISTRY` → `live_conformance` decides skip for non-fake → `_run_and_capture` → `resolve_host()` (via `LL_HOST_CLI`) → `build_streaming` → `subprocess.Popen` (guard: fake basename carved out always; real basename carved out only under live flag) → `ll-fake-host` or real CLI → consumer callbacks → `Observed` → assertions.

## Implementation Steps

1. Land FEAT-3454 (fake executable, runner, its guard carve-out, first-entry drift sync).
2. `live_conformance` fixture + guard opt-in flag + four-shape regression tests.
3. `_run_and_capture` and `Observed`; prove it against the fake's happy path.
4. `test_golden_path_behavior` with Tier 1 invariants; verify fake passes, real hosts skip without the env var, and one real host passes locally with it.
5. Tier 2 scripted cases, one per AC row; each uses a directive block and asserts the exact observation.
6. Capability argv assertions, both directions, via the fake override.
7. Docs: `CONFORMANCE.md` rewrite, `TESTING.md` two lines, optional kimi note.
8. Verify: default suite green with no env vars; `-m "not conformance"` deselects; `ll-verify-host-map` clean; mypy/ruff clean.

## Impact

- **Priority (P2)**: defensive infrastructure for a latent rewrite risk; the first behavioral coverage of the real spawn path in the default suite.
- **Effort**: medium — one test module rewrite, one fixture, one guard carve-out, one doc rewrite. Depends on FEAT-3454.
- **Risk**: low — additive; the constructability test stays; no runner or consumer change. Tier 1 against a real host may surface a genuine contract deviation on first run — that is the point, treat it as a bug not a baseline.
- **Breaking Change**: no.

## Status

**Open** | Created: 2026-09-11 | Priority: P2

## Dependencies

- **Depends on FEAT-3454** for the CI target and the directive vocabulary.
- **Blocks ENH-3459** (composition suite builds on the behavioral tier).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/development/CONFORMANCE.md` | The harness doc this issue rewrites |
| `docs/reference/API.md#little_loopshost_runner` | `HostRunner` + `CapabilityReport` surface asserted against |
| `docs/development/TESTING.md` § live-spawn guard | The guard the env gate must cooperate with |
| `.claude/CLAUDE.md` § Host CLI Abstraction, § Testing & CI Policy | `resolve_host()` seam; no paid CI, gates live in the local suite |

## Verification Notes

Verdict at time of check: **OUTDATED** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

- Three stale anchor citations corrected in the Integration Map / Conventions
  in Force: `_reset_collector` autouse fixture is at
  `test_conftest_cap.py:232-238`, not `:222-228` (the fixture body sits inside
  the `TestNoLiveHostCLIGuard` class docstring block, ~10 lines below the
  cited range); the watchdog-timeout citation was missing its directory —
  `scripts/pyproject.toml:266-267`, not bare `pyproject.toml` (no root
  `pyproject.toml` exists in this repo); and the "negative assertions use
  `not in` with a repr diagnostic" precedent cited `test_fsm_signal_integration.py:211`,
  a file that contains no `not in` assertion anywhere — retargeted to the
  actual matching pattern at `test_autodev_decision_gate.py:653`
  (`assert "reconcile_current" not in visited, f"visited={visited!r}"`).
- Every other file/line citation checked (30+ across `subprocess_utils.py`,
  `host_runner.py`, `test_host_conformance.py`, `test_host_runner.py`,
  `conftest.py` ×2, `test_conftest_cap.py`, `test_streaming_cache_parity.py`,
  `pytest.ini`, `.github/workflows/ci.yml`, `docs/development/TESTING.md`,
  `docs/kimi/automation.md`) matches current code exactly, including the
  `run_claude_command` span (`subprocess_utils.py` 422-771, confirmed as the
  file's last line) and the CI conformance job (confirmed it does not set
  `LL_HOST_CONFORMANCE_LIVE`).
- `FEAT-3454` (the stated dependency) is genuinely still open and unimplemented
  — `scripts/little_loops/fake_host.py` does not exist yet — so the "depends
  on FEAT-3454" framing and the "no fake exists yet" premise both hold.
- Dependency refs: `depends_on: FEAT-3454` and `relates_to: [ENH-3459,
  ENH-3460]` all resolve to existing, open issues; `ENH-3459`'s
  `blocked_by` correctly lists `FEAT-3455` back. Note: this project's issue
  schema has no `blocks`/`## Blocks` backlink field on the blocker side
  (`dependency_mapper` only validates `blocked_by`/`depends_on`/`relates_to`
  targets exist, not a mirrored "blocks" list) — so `FEAT-3454` not declaring
  "blocks FEAT-3455" is expected, not a MISSING_BACKLINK defect.
- Evidence-quote check (`ll-verify-evidence --json`): clean, 0 findings.
- No completed issue matches this one closely enough for regression analysis.
- Graph tools: `ll-code` (provider=codegraph, freshness=fresh) available but
  not needed — all checks resolved via direct file/line inspection.

## Session Log
- `/ll:verify-issues` - 2026-09-12T17:10:03 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- `/ll:verify-issues` - 2026-09-12T17:06:35 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- Manual review rewrite - 2026-09-12 - folded two-tier split (invariants vs scripted-exact), keep constructability test, capability-as-argv rule, guard env+marker carve-out, corrected `_check_emitter_agreement` claim, moved spike promotion to ENH-3459
- `/ll:confidence-check` - 2026-09-12T07:08:51 - `cd97a6a9-4e4b-4de2-8681-0b936dccac65.jsonl`
- `/ll:wire-issue` - 2026-09-12T07:05:00 - `6acb6589-d0ad-4f08-a678-5d9b934fde54.jsonl`
- `/ll:refine-issue` - 2026-09-12T06:50:19 - `3c577ef9-4e12-4545-bd70-260fee13d04b.jsonl`
- `/ll:wire-issue` - 2026-09-12T04:48:54 - `f8f5f90a-7e37-48e9-8cab-bcbd9492818f.jsonl`
- `/ll:refine-issue` - 2026-09-12T04:00:52 - `e6d1e59e-6622-4d79-806e-0adbe063751c.jsonl`
- `/ll:format-issue` - 2026-09-12T03:50:16 - `b5367032-da18-428d-be91-16777a0b7408.jsonl`
