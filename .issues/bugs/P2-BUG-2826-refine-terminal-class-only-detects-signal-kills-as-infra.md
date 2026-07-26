---
id: BUG-2826
type: BUG
priority: P2
status: done
captured_at: '2026-07-26T06:40:00Z'
completed_at: '2026-07-26T16:20:16Z'
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
confidence_score: 96
outcome_confidence: 78
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 18
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

Done — fixed via Proposed Solution items 1-alternative (reuse the existing
`classify_failure` verdict rather than duplicating stderr regexes in bash), 3,
and 4. See Resolution.

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
| `scripts/little_loops/fsm/executor.py` | expose `classify_failure()`'s verdict (already computed at ~line 1458 for retry/defer routing) into `self.captured[state_name]["failure_type"]` at the shell-capture site (~line 1746) so `classify_terminal` can read `${captured.<state>.failure_type}`; other `self.captured[...]` construction sites (~1011, ~1312, ~1365, ~1401/1432, ~1693) are candidates to audit for consistency but are not required to carry the new key |

Check whether other loops replicate the same three-exit-code classifier before
fixing this one in isolation.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation.py` — `_SUB_LOOP_CAPTURE_OWN_FIELDS` (line ~172) is the enumerated allow-list of nested-path suffixes (`{"output", "exit_code"}`) valid on a sub-loop-delegating state's own `capture:` name (BUG-2812 shape). If `failure_type` is exposed on the sub-loop capture path (executor.py ~line 1011-1012) too, this frozenset needs `"failure_type"` added or `${captured.<subloop_state>.failure_type}` references will be flagged as validation errors [Agent 1/2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (~line 1032) — the `autodev` "Notes" paragraph states today's exact (now-incorrect) rule: "`infra` when the failing state's captured exit code is 143/137/124 (SIGTERM/SIGKILL/timeout) or a signal, else `quality`" — must be rewritten to describe `FailureType`-based classification [Agent 2 finding]
- `skills/audit-loop-run/SKILL.md` (~line 295, ENH-2404 section) — documents `refine_failed_infra` as meaning only "SIGTERM/OOM/timeout — exit 143/137/124"; same stale exit-code framing needs updating to reflect the broader classification [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` `action_complete` event table (lines 200-217) — only needs a new row if `failure_type` is also surfaced on the event stream (not just the in-memory `captured` dict) for `audit-loop-run`/`ll-logs` observability; advisory, confirm scope during implementation [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — new test in the `TestCapture`/`TestCaptureWorkflow` classes asserting `result.captured["<state>"]["failure_type"]` is populated for a shell action that fails with API/config-error-shaped output (no existing test does this — the plumbing from `classify_failure()` into `self.captured[...]` doesn't exist yet). Also re-check `test_sub_loop_capture_shape_has_no_stderr_key` (~line 5724) if `failure_type` is added to the sub-loop capture shape at executor.py ~line 1011 — it currently documents that dict's exact key set (`{"output", "exit_code"}`) [Agent 1/3 finding]
- `scripts/tests/test_builtin_loops.py` — `test_classify_terminal_classifies_by_exit_code` (~1497-1533) will need new parametrize rows/logic once `classify_terminal` also branches on `failure_type`, not just raw exit codes [Agent 3 finding]

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


## Resolution

Fixed by exposing the executor's already-computed `classify_failure()` verdict to
loop YAML and consuming it in `classify_terminal`, plus a non-LLM diagnosis
backstop. No new classifier was written — the tested
`issue_lifecycle.classify_failure()` logic is reused, per the second Codebase
Research Findings block.

1. **`fsm/executor.py`** (shell/action capture site, "Capture if requested"):
   `self.captured[state.capture]` now carries a `failure_type` key — the
   `FailureType.value` string from `classify_failure(output + stderr, exit_code,
   result_seen=...)` when `exit_code != 0`, else `""` (always present, so a
   nullable `${captured.x.failure_type?}` ref word-splits away in bash). The
   sub-loop capture site (~line 1011) was deliberately left unchanged, so
   `validation.py`'s `_SUB_LOOP_CAPTURE_OWN_FIELDS` needed no edit and
   `test_sub_loop_capture_shape_has_no_stderr_key` still holds.
2. **`loops/refine-to-ready-issue.yaml`** — `classify_terminal` gained a second
   pass over the same 8 states' `failure_type`, mapping `transient` /
   `non_recoverable` / `infra_retry` → `infra`. The exit-code pass is unchanged;
   only `real` (an evidenced quality verdict) now stays `quality`.
3. **`loops/refine-to-ready-issue.yaml`** — new `write_failure_evidence` shell
   state between `diagnose` and `classify_terminal`. `diagnose.next` *and* the new
   `diagnose.on_error` both route to it, so a model-layer failure that kills the
   prompt-based diagnosis still yields
   `${context.run_dir}/refine-failure-evidence.txt` (failing state, all captured
   exit codes, all `failure_type` verdicts, stderr tails). Stderr prose is emitted
   inside quoted heredocs so arbitrary error text can't be re-tokenized as bash.
   `on_error: classify_terminal` keeps a diagnostics failure from swallowing the
   termination class.
4. **`autodev.yaml` unchanged** — `skip_inflight` consumes the sentinel as-is;
   BUG-2611's route constraint (Proposed Solution item 4) holds.
5. **Docs** — `docs/guides/LOOPS_REFERENCE.md` (autodev Notes) and
   `skills/audit-loop-run/SKILL.md` (ENH-2404 section) rewritten off the stale
   exit-code-only rule. `docs/reference/EVENT-SCHEMA.md` was left alone:
   `failure_type` lives only in the in-memory `captured` dict, not on the event
   stream, so its `action_complete` table needs no row.

Option 2 (a structural transport-failure exit code threaded through
`host_runner.py`) was not pursued — reusing `classify_failure` achieves the same
discrimination without a new `ActionResult` field.

### Verification

- `scripts/tests/test_fsm_executor.py` — 2 new tests: a 429-shaped stderr with
  exit 1 captures `failure_type == "transient"`; a successful action captures `""`.
- `scripts/tests/test_builtin_loops.py` — new `_run_classify_terminal` helper
  (regex-substitutes any `${captured.*}` ref, and asserts no interpolation token
  is left unsubstituted) backs both the existing exit-code test and a new
  parametrized `failure_type` test (`transient`/`non_recoverable`/`infra_retry` →
  `infra`; `real`/`""` → `quality`), plus a test asserting every state inspected
  for `exit_code` is also inspected for `failure_type`, and tests for the
  `diagnose` → `write_failure_evidence` → `classify_terminal` routing and the
  evidence artifact's content.
- `ll-loop validate refine-to-ready-issue` — valid, 24 states.
- Full suite: 16405 passed, 42 skipped. `ruff check scripts/` clean. `mypy` shows
  only the pre-existing unrelated `issue_parser.py:350` error (confirmed present
  on the stashed tree).

## Session Log
- `/ll:manage-issue` - 2026-07-26T16:19:31 - `da324ba0-fa3b-47d4-9721-f97b1900609c.jsonl`
- `/ll:ready-issue` - 2026-07-26T16:09:51 - `02c03dd5-5f8d-42fc-ad27-b9f94bbbd79e.jsonl`
- `/ll:confidence-check` - 2026-07-26T16:15:00 - `02c03dd5-5f8d-42fc-ad27-b9f94bbbd79e.jsonl`
- `/ll:wire-issue` - 2026-07-26T16:00:45 - `31974136-16cc-44e0-be8f-8ec79fa16ac6.jsonl`
- `/ll:refine-issue` - 2026-07-26T15:55:19 - `6bef5b5d-7593-42f3-ac27-a41db893916f.jsonl`
- `/ll:refine-issue` - 2026-07-26T15:54:16 - `1ce1fe65-85b4-46d0-8a32-e06d2cab4f5b.jsonl`
