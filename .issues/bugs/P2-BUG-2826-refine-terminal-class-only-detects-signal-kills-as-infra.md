---
id: BUG-2826
type: BUG
priority: P2
status: open
captured_at: '2026-07-26T06:40:00Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
labels:
- fsm
- loops
- autodev
- error-classification
relates_to:
- ENH-2727
- BUG-2611
---

# BUG-2826: `classify_terminal` only recognizes signal kills as infra, so API/config failures are ledgered as refine-quality failures

## Summary

`refine-to-ready-issue.yaml`'s `classify_terminal` state decides whether a failed
refine run was *infra-class* (transient, re-runnable) or *quality-class* (the
issue genuinely could not be refined) by inspecting **exit codes only**, and its
infra set is `143 | 137 | 124` — SIGTERM, OOM-kill, and `timeout(1)`. Every other
failure mode is classified `quality` by default.

An API-layer failure — 404 on an unresolvable model, 401 on bad credentials, 429
after retry exhaustion, a network error — surfaces as **exit 1**, not a signal.
It is therefore written to `${context.run_dir}/refine-terminal-class` as
`quality`, and `autodev.yaml`'s `skip_inflight` ledgers the issue as
`refine_failed` in `autodev-skipped.txt`.

The consequence is a false accusation against the issue: the run summary reports
the issue as skipped for quality reasons, and ENH-2727's whole point — separating
"just re-run this" from "this issue needs human attention" — is inverted for the
most common non-signal failure class.

## Current Behavior

Observed in run `.loops/runs/autodev-20260726T011116/` (`ll-loop run autodev
FEAT-2123`), which completed in 7.1 seconds without touching the issue:

```
refine_issue   action: /ll:refine-issue FEAT-2123 --auto   exit 1 after 200ms
  stderr: Error code: 404 - {'type':'error','error':
          {'type':'not_found_error','message':'model: sonnet'}}
diagnose       exit 1 after 210ms, SAME 404
classify_terminal → wrote 'quality'
failed
```

Ledgered result: `FEAT-2123  refine_failed`, reported under `Skipped (1)`.

The classifier itself:

```bash
CLASS=quality
for c in 1      0 0; do
  case "$c" in
    143|137|124) CLASS=infra ;;
    -*) CLASS=infra ;;
  esac
done
printf '%s' "$CLASS" > ${context.run_dir}/refine-terminal-class
```

Two compounding problems in the same run:

1. **The classifier has no signal to work with.** Exit 1 is the universal
   catch-all; it carries no information about *why*. The classifier cannot
   distinguish "the LLM read the issue and concluded it is unrefinable" from
   "the request never reached a model."
2. **`diagnose` cannot compensate.** The `diagnose` state exists precisely to
   explain an unrecoverable failure, but it is itself a prompt state — so it
   died on the *same* 404, wrote nothing, and the run produced no diagnosis
   artifact. Whenever the failure is at the model-invocation layer, the
   diagnostic path fails in exactly the same way as the thing it is diagnosing.

## Steps to Reproduce

Any failure that makes prompt states fail at the API layer reproduces it. The
observed instance:

1. Set `orchestration.request_path: "sdk"` in `.ll/ll-config.json`.
2. Ensure the FSM resolves a model the Messages API rejects (before the alias
   fix, `fsm.schema.DEFAULT_LLM_MODEL = "sonnet"` did this on its own).
3. `ll-loop run autodev <ISSUE-ID>`.
4. Inspect `${run_dir}/refine-terminal-class` → `quality`, and
   `${run_dir}/autodev-skipped.txt` → `<ISSUE-ID>  refine_failed`.

A synthetic reproduction needs no API at all: make `refine_issue`'s action exit 1
by any means and observe that the class is always `quality`.

## Expected Behavior

1. A failure that never reached a model verdict is classified `infra` and
   ledgered `refine_failed_infra` — re-runnable, surfaced in the separate
   "just re-run" bucket, not counted against the issue.
2. `refine_failed` means what ENH-2727 intended: an evidenced quality verdict.
3. When the failure is at the model-invocation layer, the run still produces a
   usable diagnosis — the operator should not have to read the events JSONL to
   discover that a 404 killed the run.

## Impact

Any autodev run whose prompt states fail at the API layer blames the dequeued
issue for an infrastructure fault: it is ledgered `refine_failed`, reported under
`Skipped`, and excluded from the "just re-run" bucket ENH-2727 created for
exactly this case. Because `diagnose` fails the same way, the run leaves no
artifact explaining itself — the operator has to read the events JSONL to find
the real cause. Severity is bounded (nothing is corrupted and a re-run recovers)
but the misreport is silent, which is what makes it costly.

## Status

Open — not started. Reproduction and root cause established from run
`.loops/runs/autodev-20260726T011116/`; no fix attempted.

## Motivation

ENH-2727 introduced the infra/quality split so operators could tell re-runnable
failures apart from ones needing attention. Signal kills are the *rare* case;
API-layer failures (auth, model resolution, rate limits, network) are the common
one, and they all land on the wrong side of the split. Worse, they are silent: a
run that touched nothing reports `done` with a clean-looking summary, so the
failure reads as an issue-quality problem rather than a configuration problem.
The FEAT-2123 run is the concrete instance — 7 seconds, zero work, and an issue
blamed for it.

## Proposed Solution

The classifier needs a richer signal than an exit code; consider in this order:

1. **Classify on captured stderr, not just exit status.** `classify_terminal`
   already runs after the failing state; the failing state's stderr is available
   via `${captured...}`. Pattern-match the API-error shapes (`Error code: 4xx`,
   `not_found_error`, `authentication_error`, `rate_limit_error`,
   `APIConnectionError`) into `infra`. Keep the existing exit-code cases.
2. **Prefer a structural signal where one exists.** An exit code emitted by the
   executor specifically for "the request never reached a model" would be more
   robust than stderr regexes; check whether the SDK/CLI dispatch path in
   `host_runner.py` / `fsm/executor.py` can distinguish transport failure from
   a completed-but-unsuccessful run, and thread that through rather than parsing
   prose.
3. **Make `diagnose` survivable.** If the failing state's failure was at the
   model layer, a prompt-based diagnosis cannot run — route to a non-LLM
   fallback that writes the failing state name, exit code, and stderr tail to
   the run dir, so the run is always self-describing.
4. **Do not change `refine_current`'s routes.** BUG-2611's constraint stands:
   `on_failure`/`on_error` stay `skip_inflight`/`skip_inflight_infra` and no
   `on_no` is added. The classification belongs inside the skip path, where
   ENH-2727 correctly put it.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/loops/refine-to-ready-issue.yaml` | `classify_terminal` classification logic; `diagnose` fallback |
| `scripts/little_loops/loops/autodev.yaml` | `skip_inflight` consumes the sentinel unchanged — verify no route change needed |
| `scripts/tests/test_builtin_loops.py` | assert an API-error stderr classifies `infra`; assert a genuine quality failure still classifies `quality` |

Check whether other loops replicate the same three-exit-code classifier before
fixing this one in isolation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stderr is already captured and available**: `fsm/executor.py:1746` (shell
  action capture path) writes `{"output", "stderr", "exit_code", "duration_ms"}`
  per captured state — `${captured.refine_issue.stderr?}` etc. are already
  valid references, so option 1 in Proposed Solution (pattern-match stderr) is
  a same-file change to `classify_terminal`'s existing `for c in ...` loop —
  add a parallel loop (or single combined pass) over
  `${captured.<state>.stderr?}` for each of the same 8 states already
  enumerated at `refine-to-ready-issue.yaml:475`, matching `Error code: 4[0-9][0-9]`,
  `not_found_error`, `authentication_error`, `rate_limit_error`,
  `APIConnectionError` into `CLASS=infra`.
- **No structural exit-code signal exists yet** (option 2): grepped
  `fsm/executor.py` and `host_runner.py` for a distinct transport-failure exit
  code — none found; `ActionResult.exit_code` is the raw subprocess/SDK exit
  code with no dedicated "never reached a model" sentinel. Option 1 (stderr
  pattern-match) is therefore the only viable near-term fix; option 2 would
  require a new `ActionResult` field threaded through `host_runner.py`'s SDK
  dispatch path, a materially larger change.
- **Only one other loop shares the shape**: `grep -l "143|137|124"` across
  `scripts/little_loops/loops/*.yaml` returns only
  `refine-to-ready-issue.yaml` (the classifier) and `autodev.yaml` (the
  consumer at `skip_inflight`, which reads the sentinel file — it does not
  duplicate the classification logic itself). No other loop needs a parallel
  fix.
- **Existing test coverage is structural, not behavioral**: `test_builtin_loops.py`'s
  ENH-2727 tests (`test_classify_terminal_state_exists`,
  `test_diagnose_routes_to_classify_terminal`, near line 1442-1465) assert
  YAML shape (state exists, routes correctly) — none execute the shell
  classifier logic. A new test for this fix should follow the same
  static-assertion style: parse `classify_terminal`'s `action` string and
  assert it contains the new stderr-pattern branches, consistent with how
  `test_diagnose_routes_to_classify_terminal` asserts on `state.get("next")`
  rather than simulating execution.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **A ready-made classifier already exists and is unused by `classify_terminal`.**
  `scripts/little_loops/issue_lifecycle.py:105` defines `classify_failure(output, exit_code, result_seen=...)`,
  returning a `(FailureType, reason)` tuple. `FailureType` (line 87) already
  distinguishes `TRANSIENT` (rate limit/quota, network/connectivity, API server
  error 5xx, context exhausted, CLI session error, OOM/SIGKILL, timeout),
  `NON_RECOVERABLE` (auth/credentials failure — 401/403), `INFRA_RETRY` (SIGTERM
  after a result event, BUG-2731), and `REAL` (genuine bug). It already
  pattern-matches the exact error shapes item 1 of Proposed Solution asks for
  (rate-limit/429, auth/401/403, network errors, API 5xx) — this is proven,
  tested logic (`scripts/tests/test_issue_lifecycle.py:681-827`), not something
  to write fresh.
- **It is already wired into the FSM executor, but only for in-process routing,
  not exposed to loop YAML.** `fsm/executor.py:1458` calls
  `classify_failure(_combined, action_result.exit_code, result_seen=...)`
  immediately after every action to drive rate-limit/API-error retry handling
  (`_handle_rate_limit`, `_handle_api_error`) — but the resulting
  `FailureType`/reason is not written into `self.captured[...]` or otherwise
  exposed as a `${captured.<state>.*}` field, so `classify_terminal`'s bash
  state has no way to read it today. Closing this gap (exposing
  `classify_failure`'s verdict per captured state, e.g.
  `${captured.<state>.failure_type}`) is a smaller, more targeted change than
  either duplicating stderr-regex logic in bash (Proposed Solution item 1) or
  inventing a new executor-level exit-code convention (item 2) — it reuses
  existing, tested classification instead of adding a second one.
- **`classify_terminal`'s exact current logic** (refine-to-ready-issue.yaml
  lines 454-485): iterates 8 fixed `${captured.<state>.exit_code?}` refs
  (`refine_issue`, `refine_followup`, `breakdown_issue`, `check_outcome`,
  `check_refine_limit`, `check_scores_from_file`, `issue_id`,
  `check_lifetime_limit`) through `case "$c" in 143|137|124) CLASS=infra ;; -*)
  CLASS=infra ;; esac`, then `printf '%s' "$CLASS" >
  ${context.run_dir}/refine-terminal-class`. `next: failed` unconditionally —
  the state's classification never changes the routing target, only the
  sentinel file content.
- **`diagnose` (lines 407-452) is `action_type: prompt`**, routed to
  unconditionally by other states' `on_error`/`on_failure`/
  `circuit.repeated_failure`, with `next: classify_terminal`. Because both
  `refine_issue` (a `slash_command` state going through the CLI subprocess
  path) and `diagnose` (a `prompt` state eligible for the SDK/batch dispatch
  path per `fsm/executor.py:1652`) run under the same broken host/API
  configuration, a model-invocation-layer failure kills both identically —
  `diagnose` produces no evidence-bearing output to classify.
- **Where the collapsed `exit_code=1` comes from for SDK-path errors**:
  `host_runner.py:1556-1613` `dispatch_anthropic_request()` catches
  `anthropic.APIError` broadly and returns `ActionResult(output="",
  stderr=str(exc), exit_code=1, ...)` — every `APIError` subclass (404
  model-not-found, 401 auth, 429 rate limit) collapses to the same exit code;
  only `stderr` differs. CLI-path failures (the `slash_command` states) go
  through the host binary subprocess instead and can carry other nonzero exit
  codes depending on the host CLI's own behavior — not guaranteed to be `1`,
  nor one of `143|137|124`.
- **`autodev.yaml` consumption confirmed unaffected by a fix here**:
  `skip_inflight` (lines 193-226) reads `${context.run_dir}/refine-terminal-class`
  (default `quality` if absent); `CLASS=infra` routes via `on_no:
  skip_inflight_infra` to append `"<id>  refine_failed_infra"` to
  `autodev-skipped.txt`; otherwise `skip_inflight` appends `"<id>
  refine_failed"` directly. No route changes needed in `autodev.yaml` — only
  the sentinel's classification logic in `refine-to-ready-issue.yaml` needs to
  change, confirming Proposed Solution item 4's constraint holds.
- **No other loop replicates this classifier.** A repo-wide search for the
  `143|137|124` / `CLASS=infra`/`CLASS=quality` shape found only this one
  instance in `refine-to-ready-issue.yaml`; no duplication to fix elsewhere.
  A structurally similar (but semantically distinct) `classify_failure` state
  exists in `scripts/little_loops/loops/interactive-component-generator.yaml`
  (line 341) — it is a different, unrelated classifier (planning vs. build
  failure) despite the name collision; not applicable here.
- **Existing test scaffold to extend**:
  `scripts/tests/test_builtin_loops.py:1489-1530`
  (`test_classify_terminal_classifies_by_exit_code`) already substitutes each
  `${captured.<state>.exit_code?}` token with literal test values and executes
  the extracted bash `action:` string via `subprocess.run(["bash", "-c",
  script], ...)`, then asserts on the written sentinel file. A new stderr-based
  test case (or a rewritten test if the classifier moves to consuming
  `${captured.<state>.stderr?}`/a new `failure_type` field) should follow the
  same harness shape. Companion sentinel-consumption tests already exist at
  `test_builtin_loops.py:4302-4402` (`test_skip_inflight_infra_*` family) that
  hand-write a `refine-terminal-class` file and assert on
  `autodev-skipped.txt` — reuse for an end-to-end check.


## Session Log
- `/ll:refine-issue` - 2026-07-26T15:55:19 - `6bef5b5d-7593-42f3-ac27-a41db893916f.jsonl`
- `/ll:refine-issue` - 2026-07-26T15:54:16 - `1ce1fe65-85b4-46d0-8a32-e06d2cab4f5b.jsonl`
