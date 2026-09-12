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
confidence_score: 70
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

**Tier 1 — invariants (every target, happy path only).** Hold for any host,
scripted or live, on a golden-path prompt. The stream shape is **host-specific**,
so the invariants read a per-host expectation table next to `_HOST_BINARY`:

```python
# (init event expected, terminal event kind). Codex `exec --json` emits
# thread.started/turn.started/item.*/turn.completed and no system/init;
# the consumer's turn.completed branch (subprocess_utils.py:698-717) never
# sets result_seen, so those hosts drain to EOF instead of breaking early.
_STREAM_SHAPE: dict[str, tuple[bool, TerminalKind]] = {
    "claude-code": (True, "result"), "codex": (False, "turn.completed"),
    "fake": (True, "result"), ...
}
```

- If the table says an init is expected, `on_model_detected` fires before any
  other callback. (Rejected: "if `capabilities.streaming` then init first" —
  Codex is `streaming=True` and has no init event; the flag describes argv, not
  the stream.)
- The terminal fires exactly once: `on_usage_detailed` is called once, and its
  `TokenUsage` is the last callback observed.
- For `result`-terminal hosts, `on_result_seen(True)` fires and the process exits
  within `post_stream_close_grace_seconds`. For `turn.completed` hosts,
  `on_result_seen(False)` fires (the consumer reached EOF) and `returncode == 0`.
- `CompletedProcess.returncode == 0` and `stderr == ""`.

The failure-shape and abort invariants are **not** Tier 1: a golden-path prompt
cannot make a live host fail or be aborted without spending tokens on a deliberately
broken run, so they are only inducible on the fake and belong to Tier 2. (Abort
*could* be induced live by calling `request_shutdown()` from the first callback; it
is left out of the live gate deliberately — it is one more paid run per host with no
host-identity content, and the fake covers the consumer side exactly.)

**Tier 2 — scripted-exact (fake only).** The prompt's `@@fake` block encodes the
expected sequence, and the test asserts the consumer saw exactly that. This tier
owns the scenario matrix (FEAT-3454 keeps only one end-to-end happy path, so the
seven scenarios are not duplicated across the two issues):

| Case | Script | Asserted observation |
|---|---|---|
| ordering | `init model=m session=s`, `text a`, `tool T {"k":1}`, `text b`, `result in=1 out=2` | callback kinds `[init, text, tool, text, usage]`; `stdout == "a\nb"`; `result_seen`; exit 0 |
| result error | `init …`, `result error=boom in=1 out=1` | `stderr == "[result] boom"`; `result_seen`; exit 0 |
| exit before terminal | `init …`, `text a`, `exit 3` | `returncode == 3`; `on_result_seen(False)`; `stdout == "a"` |
| failed start | `stderr no auth`, `exit 1` (no `init`) | `returncode == 1`; `stderr == "no auth"`; no `on_model_detected` |
| idle timeout | `init …`, `text working`, `sleep 5`, `result` with `automation.idle_timeout=1` | `TimeoutExpired(output="idle_timeout")`; process group gone; `stdout_lines` seen `working` via callback |
| abort | `init …`, `text working`, `sleep 5`, `result`; `stream_callback` calls `request_shutdown()` on `working` | `TimeoutExpired(output="interrupted")`; process group gone |
| wall-clock hang | `init …`, `hang` with `timeout=1` | `TimeoutExpired` with `output is None`; process group gone |
| grace kill | `init …`, `result in=1 out=1`, `hang` with `post_stream_close_grace_seconds=1` | returns normally; `result_seen`; process reaped (`returncode < 0`) |

"Process group gone" is asserted via `on_process_start`'s `Popen` handle:
`process.wait(timeout=5)` returns and `os.killpg(pgid, 0)` raises
`ProcessLookupError`. Never assert wall-clock durations; the select tick is 1s and
xdist load stretches them. Never assert `stderr` position relative to stdout —
separate pipes, nondeterministic interleaving.

**Observation model.** The consumer exposes no event list; everything is seen
through callbacks, so `Observed.kinds` is the callback-derived sequence:
`on_model_detected`/`on_session_id_detected` ⇒ `init`, `on_tool_call` ⇒ `tool`,
`stream_callback(is_stderr=False)` ⇒ `text`, `on_usage_detailed` ⇒ `usage`.
Events with no callback-triggering field are invisible (`init` without `model`
or `session_id`, `result` without `usage`, `assistant` with empty text), and
`raw` is indistinguishable from `text`. Every Tier 2 script therefore carries the
triggering fields, and FEAT-3454's default emission does too.

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
- **`streaming`:** argv-only like the others (the fake asserts nothing for it beyond
  the flag round-tripping into `invocation.capabilities`). No stream-level
  assertion: the fake executable never sees capabilities — what it emits is decided
  by the script, so "`streaming=False` ⇒ no init parsed" would test the script, not
  the flag. Init expectations are host facts in `_STREAM_SHAPE` (Tier 1).

The fake's per-test capability override (FEAT-3454) makes both directions testable
without a real host — **by direct construction only**: `resolve_host()` calls
`runner_cls()` with no arguments (`host_runner.py:2323, :2334`), so the override
can never reach `run_claude_command`. The capability tests build
`FakeHostRunner(capabilities=…).build_streaming(...)` and assert on `invocation.args`;
they do not spawn.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- Stale anchor: `resolve_host()` calls `runner_cls()` with no arguments at `host_runner.py:2488` and `:2499`, not `:2323, :2334` as cited above (FakeHostRunner's registration pushed line numbers down since this issue was last refined).
- Confirmed mechanism defect: `FakeHostRunner.build_streaming()` (`host_runner.py:2082-2104`) always returns `args=[prompt]` — it never threads `agent`, `tools`, or `workspace_root` into argv regardless of the `capabilities` override passed to its constructor. This means the positive-direction argv-facts check ("when a flag is True, the argv marker is present") cannot be observed through `FakeHostRunner(capabilities=...).build_streaming(...)` for `permission_skip`, `agent_select`, `tool_allowlist`, or `workspace_sandboxed` — those flags' argv-injection logic lives only inside each *real* runner's own `build_streaming` (e.g. `ClaudeCodeRunner` lines 926-1013, `CodexRunner` lines 1180-1253), which `FakeHostRunner` does not share or delegate to.
- `structured_output` is the one flag with an independent, spawn-free test path: `_structured_output_args(invocation, schema)` (`host_runner.py:2530`) is a standalone module-level function that reads `invocation.capabilities.structured_output` directly and returns `[]` when `False` — it does not depend on `build_streaming()`'s own `args` list, so it can be exercised on any manually-constructed `HostInvocation` (fake or otherwise) without spawning.
- `streaming` has no argv consumption anywhere (confirmed) — consistent with the issue's own note that it round-trips into `invocation.capabilities` only.
- Net effect: "assert on `invocation.args`" only works for a flag whose real-runner injection logic is itself reproduced somewhere reachable without a real host. As written, no such path exists for `permission_skip`/`agent_select`/`tool_allowlist`/`workspace_sandboxed` via the fake. The route to satisfy the Acceptance Criteria's "positive direction gated" requirement for those four flags is an implementation decision (e.g., test each real runner's own `build_streaming` directly for the positive case, as `test_host_runner.py` already does per-runner at `:761-786`/`:823-882` — see Integration Map findings below).

## Current Behavior

`test_golden_path_invocation` (`test_host_conformance.py:64-112`) skips on binary
missing or `HostNotConfigured`, then asserts `invocation.binary` and
`invocation.args` are non-empty. A runner that constructs a syntactically valid
invocation but emits a terminal mid-stream, leaks events after it, or mis-shapes a
failure passes this gate.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- FEAT-3454 (this issue's stated dependency) is now **done**. The fake host executable exists at `scripts/little_loops/fake_host.py`. Its runner, `FakeHostRunner` (defined in `host_runner.py`, line 2053), is registered as the `"fake"` entry (`host_runner.py`, line 2157), alongside `TEST_ONLY_HOSTS`/`TEST_ONLY_BINARIES` (`host_runner.py`, lines 2142/2193), the `_match_host_binary` fake-binary carve-out (`conftest.py`, lines 255-278), and the `pytest_sessionstart` PATH prepend (`conftest.py`, lines 103-117) — all exist in the codebase today. This issue's premise that "the fake host runs it on every suite invocation" is now buildable against real, landed infrastructure rather than a planned dependency — the prior verification note's "FEAT-3454 genuinely still open and unimplemented" is stale. The Tier 1/Tier 2 machinery this issue itself proposes (the root-conftest hook pair, its module global, `LL_HOST_CONFORMANCE_LIVE`) is separate, still-unbuilt work — see Integration Map.

## Expected Behavior

- `test_golden_path_behavior(host, golden_path)` runs Tier 1 for every registered
  host: unconditionally for `fake`, behind `LL_HOST_CONFORMANCE_LIVE=1` for the rest.
  For the fake the golden-path prompts carry no `@@fake` block, so the four cases
  exercise FEAT-3454's default emission (identical runs, ~150ms each — accepted for
  parametrize symmetry with the constructability test).
- `test_scripted_*` cases run Tier 2 against the fake only, on every
  `python -m pytest scripts/tests/` invocation. They never skip: FEAT-3454's
  session-start PATH prepend makes `ll-fake-host` resolvable in every job, and a
  missing binary is a failure.
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
  and asserts every Tier 1 invariant against `_STREAM_SHAPE[host]`. `_STREAM_SHAPE`
  has a row for every registry key (gate-tested, like `_HOST_BINARY`). For
  `host == "fake"` it runs unconditionally; for other hosts it skips with reason
  unless `LL_HOST_CONFORMANCE_LIVE=1`, and the existing skips (binary missing,
  `HostNotConfigured`) still apply.
- Tier 2 scripted cases exist for all eight rows of the Tier 2 table: ordering,
  `result error=`, exit-nonzero before terminal, failed start, idle timeout, abort
  via `request_shutdown()` fired from `stream_callback`, wall-clock `hang`, and
  `result` + `hang` grace kill. Each asserts the exact callback-derived observation,
  asserts no durations, and runs in the default suite without skipping.
- Capability assertions per the argv-facts rule above: negative direction fires
  unconditionally; positive direction gated. Tested in both directions via the fake's
  capability override on directly-constructed invocations; no stream-level
  capability assertion exists.
  > ⚠ Superseded — mechanism broken for 5/6 flags; see Codebase Research Findings
- The live-spawn guard (`scripts/tests/conftest.py:_match_host_binary` `:237-255`)
  > ⚠ Superseded — actual span is conftest.py:255-278
  gains a carve-out that lets a real host spawn proceed only when
  `LL_HOST_CONFORMANCE_LIVE=1` **and** the running test carries the `conformance`
  marker. The opt-in is a **module-level flag in the root conftest**, set by a
  `pytest_runtest_setup` hook (marker present and env var set) and cleared in
  `pytest_runtest_teardown`; four-shape regression tests in
  `test_conftest_cap.py::TestNoLiveHostCLIGuard` cover it (flag set ⇒ None;
  flag clear ⇒ tuple; `--version` carve-out preserved; non-host basename unaffected).
- Failure diagnostics include runner name, golden path, expected vs actual kinds,
  first-divergence index.
- `docs/development/CONFORMANCE.md` rewritten for the two tiers, the env gate and
  its cost, the timeout policy, and the capability rule.
- `python -m pytest scripts/tests/` exits 0 with no env vars set; `-m "not
  conformance"` deselects the behavioral tier; `ll-verify-host-map` stays clean.

## Integration Map

### Files to Modify
- `scripts/tests/conformance/test_host_conformance.py` — add `_STREAM_SHAPE`, `test_golden_path_behavior`, Tier 2 `test_scripted_*` cases, helpers (`_run_and_capture`, `assert_terminal_once`, `assert_event_kinds`, `assert_capability_argv`, `assert_group_gone`).
- `scripts/tests/conformance/conftest.py` — `live_conformance` fixture reading `LL_HOST_CONFORMANCE_LIVE` at fixture time (so `monkeypatch.setenv` in a test body wins; `conftest.py:1095-1096` precedent) and deciding the skip for non-fake hosts; `isolated_env` stays.
- `scripts/tests/conftest.py` — `_live_spawn_allowed: bool` module global; `pytest_runtest_setup` sets it when `item.get_closest_marker("conformance")` and `LL_HOST_CONFORMANCE_LIVE=1`, `pytest_runtest_teardown` clears it; `_match_host_binary` returns `None` when it is set. A module global rather than a contextvar because FSM-level runs spawn from worker threads, where a contextvar set in the test thread does not propagate; a hook in the root conftest rather than a fixture in `conformance/conftest.py` because the sub-conftest has no clean way to import the root conftest module to set its state (`test_conftest_cap.py` loads it via `importlib` precisely because it is not importable by name).
- `scripts/tests/test_conftest_cap.py::TestNoLiveHostCLIGuard` (`:281-300`) — four-shape carve-out tests; `_reset_collector` autouse (`:232-238`) still clears `_host_cli_hits`/`_reported_upto`.
  > ⚠ Superseded — class now at test_conftest_cap.py:223-321
- `docs/development/CONFORMANCE.md` — rewrite (currently constructability-only; "Reading the Results" table and baseline board need the new rows).
- `docs/development/TESTING.md:121` (tree line) and `:1048` (markers table) — describe the behavioral tier and env gate.
- `docs/kimi/automation.md:71-82` — optional one-sentence note; the `4 passed` invocation stays valid.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:422-771` — `run_claude_command`, the consumer under test. Callback surface used by the helpers: `on_model_detected`, `on_session_id_detected`, `on_tool_call`, `on_usage_detailed`, `on_result_seen`, `stream_callback`, `on_process_start/end`. Not modified.
- `scripts/little_loops/host_runner.py` — `_HOST_RUNNER_REGISTRY`, `resolve_host_named`, `HostCapabilities`, `CapabilityReport`, `_structured_output_args`. Not modified.
- `scripts/little_loops/fake_host.py` (directive vocabulary/parser/executable) and `FakeHostRunner` (defined in `scripts/little_loops/host_runner.py`, line 2053) (FEAT-3454) — the CI target; directive vocabulary is defined in `fake_host.py` and consumed here.
- `.github/workflows/ci.yml` — the `unit-tests` job runs `-m "not integration and not conformance"`, so the behavioral tier reaches CI only via the Thinky `conformance` job (`:149-207`), which does not set `LL_HOST_CONFORMANCE_LIVE`. Fake-only cases run there; real hosts skip. **That job never puts `.venv/bin` on PATH** (only the unit job does, `:110`) — without FEAT-3454's `pytest_sessionstart` PATH prepend every test in this issue would skip there. No workflow change; the prepend is the fix.
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
- Trigger `request_shutdown()` from `stream_callback`, not a timer thread: the loop checks `_shutdown_event` at the top of each iteration (`subprocess_utils.py:581`), so a callback-fired shutdown is deterministic.
- Timeouts passed to `run_claude_command` are small integers (`timeout=1`, `automation.idle_timeout=1`, `post_stream_close_grace_seconds=1`); the fake's `sleep` is longer than the timeout it is meant to trip (`sleep 5`), and no test asserts elapsed time.

### Tests
- `test_golden_path_behavior[<path>-<host>]` — Tier 1.
- `test_stream_shape_covers_registry` — `_STREAM_SHAPE.keys() == _HOST_RUNNER_REGISTRY.keys()`.
- `test_scripted_ordering`, `test_scripted_result_error`, `test_scripted_exit_before_terminal`, `test_scripted_failed_start`, `test_scripted_idle_timeout`, `test_scripted_abort_request_shutdown`, `test_scripted_hang_wall_clock`, `test_scripted_result_then_hang_grace_kill` — Tier 2, fake only.
- `test_capability_argv_negative[<flag>]` / `test_capability_argv_positive[<flag>]` — fake with override, both directions.
- `TestNoLiveHostCLIGuard` four-shape carve-out tests.

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `docs/development/CONFORMANCE.md` "Reading the Results" table (`:26-38`) | Documents 4 outcomes for `test_golden_path_invocation` only: `PASSED`/`SKIPPED` (binary absent)/`SKIPPED` (stub)/`FAILED` | PRESERVED, extended | Existing 4 outcomes still describe the constructability test unchanged; the rewrite adds a parallel row set for `test_golden_path_behavior` (Tier 1) and the `test_scripted_*` cases (Tier 2), which have their own skip/fail semantics (env-gated skip for non-fake hosts; scripted cases never skip). |
| `docs/development/CONFORMANCE.md` "Running the Harness" commands (`:13-24`) | `pytest -m conformance`, `--conformance-host`, `-m "not conformance"` | PRESERVED unchanged | These invocations are unaffected by adding a behavioral tier — the same marker and CLI option select both tiers together. |
| `docs/development/CONFORMANCE.md` "Baseline Pass/Fail Board" (`:40-52`) | Snapshot table of 4 hosts (`claude-code`, `codex`, `opencode`, `pi`) as of 2026-06-26 | CHANGED | Already stale independent of this issue — `_HOST_RUNNER_REGISTRY` now has 9 entries (adds `fake`, `gemini`, `omp`, `kimi-code`, `qwen`); the rewrite should refresh this board and, if it keeps the single-table shape, add a column set for the new behavioral-tier results. |
| `docs/development/CONFORMANCE.md` "Adding a New Host" (`:54-59`) | 3-step guide: implement `HostRunner`, register it, update the baseline board | PRESERVED, extended | Still accurate for Tier 1 (auto-picked-up via the registry parametrize); step 3 should note a new real host stays skipped on Tier 1 until `LL_HOST_CONFORMANCE_LIVE=1` is set for it. |
| `docs/development/CONFORMANCE.md` "Closing Superseded Issues" (`:61-68`) | FEAT-1721/FEAT-2192 closure criteria reference `test_golden_path_invocation` only | PRESERVED unchanged | This issue keeps `test_golden_path_invocation` unchanged in behavior (Acceptance Criteria), so these closure criteria are unaffected. |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- Stale anchors corrected (all confirmed against current code, post-FEAT-3454):
  - `test_host_conformance.py`: `test_golden_path_invocation` is defined at line 72 (not part of a "64-112" span) and its body runs to line 114, the file's actual last line (114 lines total, not 112). The `@pytest.mark.conformance`/`@pytest.mark.parametrize` decorator stack cited as `:64-71` actually spans lines 65-71 (line 64 is blank).
  - `scripts/pyproject.toml`: the watchdog timeout args are at lines 267-268 (`"--timeout=120"`, `"--timeout-method=thread"`), not `:266-267`.
  - `.github/workflows/ci.yml`: the `conformance:` job spans lines 149-211 (including its final "Snapshot .ll/history.db" step), not `:149-207`.
  - `scripts/tests/conftest.py`: the "monkeypatch.setenv in a test body wins" precedent is the comment at line 1119 ("Tests that *want* the gate monkeypatch.setenv() it in the test body, which still wins over this."), not `:1095-1096` (that range is inside an unrelated fixture's docstring about `Path.home`).
  - `scripts/tests/test_conftest_cap.py`: confirmed via direct grep — `class TestNoLiveHostCLIGuard` at line 223, `_reset_collector` at line 235 (issue's existing `:232-238` citation is close enough, off by ~3 lines, not corrected further).
- `fake_host.py` directive vocabulary is larger than described: `_KNOWN_KINDS` (`fake_host.py:33-46`) is `{init, text, tool, result, turn_completed, raw, stderr, sleep, exit, hang}` — this issue's Tier 2 table and Design Decision prose only enumerate 8 of these 10 (omitting `turn_completed` and `raw`). `turn_completed` lets the fake emit a Codex-shaped terminal event if a future test ever needs to script that shape; `raw` emits a stream-JSON line indistinguishable from `text` per this issue's own Observation Model note.
- Convention correction: `test_host_runner.py` does **not** contain `@pytest.mark.parametrize("host", list(_HOST_RUNNER_REGISTRY.keys()))` anywhere — that sweep-style parametrize exists only in `test_host_conformance.py:66`. `test_host_runner.py` instead repeats individual `assert "<host>" in hr._HOST_RUNNER_REGISTRY` / `assert hr._HOST_RUNNER_REGISTRY["<host>"] is <RunnerCls>` pairs per host (e.g. `:718-719` for codex, `:1120-1121` for fake), and its one registry-adjacent parametrize is over a hand-picked runner-class list (`:2021-2024`), not the full registry.
- Convention correction: the "capability flags tested in both directions" precedent is not at `test_host_runner.py:2047-2055` (that range is `TestCapabilityWarning`, a generic warning-mechanics check unrelated to any specific flag). The real both-directions precedent is the paired negative/positive tests per flag, e.g. `test_build_streaming_emits_warning_for_agent_when_toml_absent` (`:761-767`, negative) / `test_build_streaming_injects_persona_when_toml_present` (`:769-786`, positive) for `agent_select`, and the tools/`structured_output` equivalents at `:823-827` / `:872-882`.
- No existing precedent anywhere in the repo for a module-level bool toggled by `pytest_runtest_setup`/`pytest_runtest_teardown` (repo-wide grep: zero hits outside this issue's own prose). The closest existing shape in `scripts/tests/conftest.py` is the lock-guarded module-level collector `_host_cli_hits`/`_host_cli_lock`/`_reported_upto` (used by the live-spawn-guard's autouse-fixture-based enforcement, not a runtest hook pair) — the same "module global, not contextvar, because FSM worker threads don't share test-thread contextvars" reasoning already applies there.

## Program Design

### Types
- `Observed`: `(kinds: list[str], model: str | None, session_id: str | None, tool_calls: list[ToolCall], usage: list[TokenUsage], result_seen: bool | None, process: Popen | None, completed: CompletedProcess | None, error: BaseException | None)` — everything the consumer surfaced, collected via callbacks; `kinds` is the callback-derived sequence defined in the Observation model above; `usage` is a list so "terminal fired exactly once" is `len(usage) == 1`; `process` is the handle from `on_process_start`, kept for the process-group assertion.
- `TerminalKind = Literal["result", "turn.completed"]`; `_STREAM_SHAPE: dict[str, tuple[bool, TerminalKind]]`.

### Signatures
- `_run_and_capture(host: str, prompt: str, *, timeout: int, automation: AutomationContext | None = None, post_stream_close_grace_seconds: int = 5, on_text: Callable[[str], None] | None = None, tmp_path: Path) -> Observed` — sets `LL_HOST_CLI=host`, wires every callback, calls `run_claude_command` unpatched, catches `TimeoutExpired` into `Observed.error`; `on_text` is the hook the abort case uses to call `request_shutdown()` from inside `stream_callback`.
- `assert_terminal_once(obs: Observed, *, host: str, golden_path: str) -> None` — one `usage`, last in `kinds`; `result_seen` per `_STREAM_SHAPE[host]`.
- `assert_group_gone(obs: Observed) -> None` — `process.wait(timeout=5)`; `os.killpg(pgid, 0)` raises `ProcessLookupError`.
- `assert_event_kinds(obs: Observed, expected: list[str], *, host: str, golden_path: str) -> None` — diff with first-divergence index.
- `assert_capability_argv(invocation: HostInvocation, flag: str) -> None` — negative when `False`, positive when `True`.
- `live_conformance` fixture → `bool` (skip decision only; the guard flag is set by the root-conftest hook, not the fixture).

### Call Path
`pytest` → `pytest_runtest_setup` sets `_live_spawn_allowed` when marker + env → parametrize over `_HOST_RUNNER_REGISTRY` → `live_conformance` decides skip for non-fake → `_run_and_capture` → `resolve_host()` (via `LL_HOST_CLI`) → `build_streaming` → `subprocess.Popen` (guard: fake basename carved out always; real basename carved out only while `_live_spawn_allowed`) → `ll-fake-host` or real CLI → consumer callbacks → `Observed` → assertions.

## Implementation Steps

1. Land FEAT-3454 (fake executable, runner, its guard carve-out, PATH prepend, first-entry drift sync).
   > ⚠ Superseded — already done; FEAT-3454 landed

2. Root-conftest `_live_spawn_allowed` flag + setup/teardown hooks + `live_conformance` fixture + four-shape regression tests.
3. `_run_and_capture` and `Observed`; prove it against the fake's default emission.
4. `_STREAM_SHAPE` + coverage gate; `test_golden_path_behavior` with Tier 1 invariants; verify fake passes, real hosts skip without the env var, and one `result`-terminal host plus Codex pass locally with it (Codex is the row that proves the per-host shape table earns its keep).
5. Tier 2 scripted cases, one per table row; each uses a `@@fake` block and asserts the exact callback-derived observation and, where applicable, `assert_group_gone`.
6. Capability argv assertions, both directions, on directly-constructed fake invocations.
7. Docs: `CONFORMANCE.md` rewrite, `TESTING.md` two lines, optional kimi note.
8. Verify: default suite green with no env vars; `-m "not conformance"` deselects; `ll-verify-host-map` clean; mypy/ruff clean.

## Impact

- **Priority (P2)**: defensive infrastructure for a latent rewrite risk; the first behavioral coverage of the real spawn path in the default suite.
- **Effort**: medium — one test module rewrite, one fixture, one guard carve-out, one doc rewrite. Built on FEAT-3454, now `done`.
- **Risk**: low — additive; the constructability test stays; no runner or consumer change. Tier 1 against a real host may surface a genuine contract deviation on first run — that is the point, treat it as a bug not a baseline.
- **Breaking Change**: no.

## Status

**Open** | Created: 2026-09-11 | Priority: P2

## Dependencies

- FEAT-3454 supplied the CI target and the directive vocabulary this issue builds on; its status is now `done`, so this issue is unblocked (see Current Behavior).
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
- `FEAT-3454` (the stated dependency) was open and unimplemented at the time of
  this verification pass. It has since landed (confirmed 2026-09-12, this
  refine pass). `scripts/little_loops/fake_host.py` now exists.
  `FakeHostRunner` (in `host_runner.py`) is now registered in
  `_HOST_RUNNER_REGISTRY`. The "no fake exists yet" premise no longer holds —
  see Current Behavior for what changed.
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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-12_

**Readiness Score**: 70/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 89/100 → HIGH CONFIDENCE

### Concerns
- Criterion 5 scored 0: the hard dependency `FEAT-3454` is `depends_on` (soft), not `blocked_by`, so it doesn't trigger the Dependencies Hard Override — but `format-check`'s `soft_dep_hard_edge: [FEAT-3454]` confirms it functions as a hard edge in practice, and `scripts/little_loops/fake_host.py` genuinely does not exist yet. This issue cannot be started until FEAT-3454 lands; consider whether `depends_on` should be `blocked_by`.
- Criterion 4 capped at 10/20 by `missing_behavior_parity: [docs/development/CONFORMANCE.md]` — the issue rewrites this doc but has no `### Behavior Parity` subsection describing what the rewrite replaces.

## Session Log
- `/ll:refine-issue` - 2026-09-12T21:53:24 - `d550be67-8e77-4467-ae5a-f361c5b766bf.jsonl`
- `/ll:confidence-check` - 2026-09-12T18:35:12 - `a9b86d47-3a71-4e77-ab37-f0478a56bd37.jsonl`
- Manual pre-implementation review - 2026-09-12 - Tier 1 rewritten around a per-host `_STREAM_SHAPE` table (Codex has no `system/init` and `turn.completed` never sets `result_seen`, so "streaming ⇒ init first" and "consumer stops after terminal" were false for a real host); failure/abort invariants moved out of the live tier; callback-derived observation model made explicit; `streaming` stream-assertion dropped (fake executable never sees capabilities; override is direct-construction-only); `hang` split into wall-clock vs `result`+`hang` grace kill; Tier 2 made the sole owner of the scenario matrix (was duplicated in FEAT-3454); guard opt-in moved to a root-conftest hook + module global; CI PATH gap noted
- `/ll:verify-issues` - 2026-09-12T17:10:03 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- `/ll:verify-issues` - 2026-09-12T17:06:35 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- Manual review rewrite - 2026-09-12 - folded two-tier split (invariants vs scripted-exact), keep constructability test, capability-as-argv rule, guard env+marker carve-out, corrected `_check_emitter_agreement` claim, moved spike promotion to ENH-3459
- `/ll:confidence-check` - 2026-09-12T07:08:51 - `cd97a6a9-4e4b-4de2-8681-0b936dccac65.jsonl`
- `/ll:wire-issue` - 2026-09-12T07:05:00 - `6acb6589-d0ad-4f08-a678-5d9b934fde54.jsonl`
- `/ll:refine-issue` - 2026-09-12T06:50:19 - `3c577ef9-4e12-4545-bd70-260fee13d04b.jsonl`
- `/ll:wire-issue` - 2026-09-12T04:48:54 - `f8f5f90a-7e37-48e9-8cab-bcbd9492818f.jsonl`
- `/ll:refine-issue` - 2026-09-12T04:00:52 - `e6d1e59e-6622-4d79-806e-0adbe063751c.jsonl`
- `/ll:format-issue` - 2026-09-12T03:50:16 - `b5367032-da18-428d-be91-16777a0b7408.jsonl`
