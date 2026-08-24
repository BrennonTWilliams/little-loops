---
id: FEAT-3118
title: Wire pre_done consult trigger into the Stop hook
type: FEAT
parent: FEAT-3038
priority: P3
status: open
testable: true
verify_verdict: VALID
discovered_date: 2026-08-08
depends_on:
- FEAT-3116
- FEAT-3120
labels:
- planning-hub
confidence_score: 98
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 23
---

# FEAT-3118: Wire pre_done consult trigger into the Stop hook

## Summary

Child 3 of 3 decomposed from FEAT-3038 (Advisor signal-gated auto-consults and
per-task budget). Adds the `pre_done` signal: a new `Stop` hook entry that
dispatches to a host-agnostic handler, calling `consult_for_trigger` on the
current working diff and surfacing the verdict as advisory hook feedback.
Builds on FEAT-3116 (done) for `should_consult` and `consult_for_trigger`.

Because Claude Code's `Stop` fires after *every assistant turn* rather than at
task completion, the trigger is gated by a diff-hash dedup so it consults once
per distinct diff state, not once per turn — see Expected Behavior.

## Parent Issue

Decomposed from FEAT-3038: Advisor signal-gated auto-consults and per-task
budget. See that issue's "Proposed Solution" → "Trigger dispatch" →
`pre_done` subsection and its codebase research on the contested `Stop`-hook
shape and hook-intent registration sites.

## Use Case

A developer working with `advisor.enabled: true` and `pre_done` in
`advisor.triggers` finishes a chunk of implementation work. On the turn where
the working diff first reaches a new state, the `Stop` hook ships that diff to
the advisor model (a stronger or independent model than the one that wrote the
code) and surfaces its recommendation, risks, and dissent as stderr feedback
before the developer moves on or declares the work done. The signal is
strongest exactly where self-review is weakest: the model that just wrote the
change is the worst reviewer of it.

Under automation (`ll-auto`, `ll-sprint`), the same feedback lands in the run
log keyed to `LL_ISSUE_ID`, giving a per-issue second opinion on the diff
without a human in the loop.

The trigger is off by default and bounded by `max_consults_per_task` — it is
opt-in for developers who want an independent read on their diffs and are
willing to pay the per-consult latency described under Impact → Risk.

## Current Behavior

`hooks/hooks.json:199-230` — the `Stop` event runs three shell scripts
(context-handoff-sentinel, session-cleanup, record-hook-event); none dispatch
through `python -m little_loops.hooks`. All three fire **after every assistant
turn** (`docs/guides/BUILTIN_HOOKS_GUIDE.md:407`), which is the timing any new
`Stop` entry inherits — see Expected Behavior → "`Stop` fires per turn".
<!-- ll-prose-ok: pre_done does not exist yet — this sentence documents its absence, the reason this feature is being proposed -->
No `pre_done` intent exists in
`hooks/__init__.py`'s `_INTENT_EVENT_NAME`, `_USAGE`, or `_dispatch_table()`.

**Contested convention to resolve**: existing `Stop` entries have no
`"matcher"` key and route through bash-only scripts under `hooks/scripts/`.
The only other Python-dispatched adapters (`SubagentStart`/`SubagentStop`,
`hooks/hooks.json:277-302`) use `"matcher": "*"` and route through
`hooks/adapters/claude-code/*.sh` (two-line `INPUT=$(cat) | python3 -m
little_loops.hooks <intent>` shape, e.g.
`hooks/adapters/claude-code/precompact.sh`). This issue follows the
`SubagentStart`/`SubagentStop` shape (`"matcher": "*"` +
`hooks/adapters/claude-code/`) since it is the only demonstrated pattern for a
Python-dispatched hook — the pre_done entry is the first `Stop` entry to use
it.

## Expected Behavior

The `Stop` hook auto-consults with signal `pre_done` on the current working
diff, when `pre_done` is listed in `advisor.triggers`. An unlisted trigger or
`advisor.enabled: false` fires no host call. A failed or timed-out consult
never blocks the turn — the hook completes normally (exit 0) with a logged
warning.

### `Stop` fires per turn, not per task (settled 2026-08-25)

**Claude Code's `Stop` event fires after *every assistant turn*, not at task
completion or session end** — `docs/guides/BUILTIN_HOOKS_GUIDE.md:407`:
"Three hooks run after each assistant turn (Claude Code's `Stop` event)."
Earlier revisions of this issue (and of parent FEAT-3038) framed it as a
session-end / task-done event; that framing is wrong and every "session end"
phrasing below has been corrected.

The consequence is load-bearing: during any implementation session the working
diff is non-empty from turn 2 onward, so an empty-diff-only gate would consult
on **every turn** until `max_consults_per_task` (default 3) is exhausted —
three consults early in the session, then permanent silence. That is the
opposite of "consult on the final diff." The empty-diff no-op alone does not
solve this.

**Resolution — diff-hash dedup.** The handler computes a SHA-256 over the
capped diff text and skips the consult when it matches the hash recorded for
the last `pre_done` consult of the same `TaskKey`. Storage: a sibling of the
budget file, `.ll/advisor-budget/<kind>-<value>.pre_done.json`, holding
`{"last_diff_sha": "..."}`, written only after a consult that actually reached
the host. This makes the trigger fire once per *distinct* diff state rather
than once per turn, and subsumes the "nothing changed this turn" case.
(Alternative considered and rejected for v1: rebinding to `SessionEnd`. It
fires once per session, but only on session teardown — too late to be
actionable, and it does not fire at all on `/clear`-less long sessions where
the user keeps working.)

### Diff capture specification

The consult context is `git diff HEAD` (staged + unstaged changes vs `HEAD`)
plus `git status --porcelain` for untracked files, both run from
`find_project_root(Path(event.cwd or os.getcwd()))` — **not** the raw hook
CWD, which may be a subdirectory (and per the known stray-`.ll`-directory
footgun, a subdirectory `.ll/` would otherwise shadow the real root). If
`find_project_root` returns `None`, exit 0 as a no-op.

Truncation is by **both** line and byte count, whichever binds first:
`_DIFF_MAX_LINES = 400` and `_DIFF_MAX_BYTES = 96_000`, with an explicit
trailing marker (`... [truncated: N of M lines, K of L bytes]`). The byte cap
is not optional — a 400-line diff of a minified bundle or lockfile is
megabytes and would blow up the advisor prompt.

**Empty-diff no-op**: if `git diff HEAD` is empty and there are no untracked
files (or the resolved root is not a git work tree, or `git` is unavailable),
the handler exits 0 without consulting and without spending budget.

**Known scope caveat (accepted, not mitigated)**: `git diff HEAD` captures all
pre-existing dirty state in the tree, not just this session's edits, and under
`ll-parallel` worktrees it spans whatever the branch has accumulated. The
consult context is therefore "the working tree right now", not "what this task
changed". Acceptable for an advisory signal; do not let a future AC assume
otherwise.

### Verdict disposition (settled 2026-08-25)

**v1 is advisory: exit 0 + `feedback`.** The handler returns
`LLHookResult(exit_code=0, feedback=<formatted verdict>)`; `main_hooks()`
(`hooks/__init__.py:222-227`) prints `feedback` to stderr and returns the exit
code. The verdict's `recommendation`, `confidence`, and any `risks`/`dissent`
are formatted into that feedback string and also logged at warning level,
mirroring FEAT-3117's disposition of `consult_outcome.verdict`
(`issue_manager.py:838-843`). A consult whose answer is discarded is budget
spent for nothing — the verdict must reach the user somewhere.

**Blocking (exit 2) is explicitly out of scope for this issue.** Exit 2 on
`Stop` is the mechanism that forces the agent to continue, and using it
requires honoring Claude Code's `stop_hook_active` payload flag to avoid a
stop → continue → stop loop. There are currently **zero** `stop_hook_active`
references anywhere in this repo, so that guard would be new, untested
machinery on a hot path. If blocking is wanted later, it is a follow-up issue
that must land the `stop_hook_active` guard first.

### Timeout reconciliation

`AdvisorConfig.timeout_seconds` defaults to **180**
(`scripts/little_loops/config/orchestration.py:125`). Existing `Stop` entries
in `hooks/hooks.json` use `timeout` values of 5–15, and Claude Code's default
hook timeout is 60. If the host kills the hook mid-consult, **budget was
already spent** — `consult_for_trigger` reserves before calling
(`advisor.py:485`, `record_consult(task_key)` precedes `consult(...)`) — and
the verdict is lost, so every consult would burn budget and return nothing.

Resolution: the new `hooks.json` entry sets `"timeout": 190` (advisor default
plus margin), **and** the handler clamps — if
`config.advisor.timeout_seconds > 190` it logs a warning and exits 0 without
consulting rather than guaranteeing a killed hook.

Note the UX cost plainly: with `pre_done` enabled, a turn that produces a new
diff state can block on a synchronous host call for up to ~180s before the
turn visibly ends. This is a stronger hazard than the parent's "Risk: Medium"
line conveys, and is the main reason the trigger stays off by default.

### Behavior under automation

The `Stop` hook also fires inside `ll-auto` / `ll-sprint` / `ll-parallel`
headless sessions, where `LL_ISSUE_ID` is set and the budget key is therefore
coherent (`kind="issue"`). **Decision: `pre_done` fires under automation.**
Budget is per-issue, dedup is per-issue, and the advisory feedback lands in
the run log. This is a stated decision, not an accident of the wiring — do not
"fix" it by suppressing on `LL_AUTOMATION`.

## Proposed Solution

- Add a `pre_done` intent across all three dispatch sites in
  `hooks/__init__.py`, kept consistent by
  `test_hook_intents.py::test_dispatch_table_intent_event_name_usage_stay_consistent`
  (`:827-855`): `_INTENT_EVENT_NAME` (`:68-80`), `_USAGE` (`:111-116`),
  `_dispatch_table()` (`:134-165`).
- New handler `scripts/little_loops/hooks/pre_done.py`, following the
  existing handler layout (`pre_compact.py`, `drift_check.py`): wraps its body
  in try/except returning exit 0 regardless of outcome (the same fail-soft
  contract documented at `hooks/__init__.py:40-43`). Control flow, in order:
  resolve the project root; assemble the capped diff per the Diff capture
  specification (empty → exit 0 no-op); compare its SHA-256 against
  `last_diff_sha` (unchanged → exit 0 no-op); clamp on
  `advisor.timeout_seconds > 190`; seed the session-ID env contract (below);
  call `consult_for_trigger("pre_done", question=..., context=<capped diff>,
  config=config)`; on a real verdict, record the new `last_diff_sha` and
  return `LLHookResult(exit_code=0, feedback=<formatted verdict>)`.
  **Do not call `should_consult` first** — `consult_for_trigger` performs that
  check internally (`advisor.py:477`), and the only other production call site
  (`issue_manager.py:834-838`) does not pre-check either.
- **Session-ID plumbing (settled 2026-08-25).** `consult_for_trigger` calls
  `resolve_task_key()` with **no arguments** (`advisor.py:475`), and
  `resolve_task_key` is a pure `os.environ` lookup with no `session_id`
  parameter (`advisor.py:338-371`). Claude Code does not export
  `CLAUDE_SESSION_ID` into hook subprocesses, so without intervention the
  budget key falls through to `session_log.get_current_session_id()` — which
  its own docstring calls "the most recently modified session JSONL —
  nondeterministic when multiple sessions run concurrently against the same
  project." The budget key would be unreliable in exactly the context this
  feature runs in. **Resolution**: `pre_done.handle()` sets
  `os.environ["CLAUDE_SESSION_ID"] = event.session_id` (from
  `main_hooks()`, `hooks/__init__.py:203`, sourced from the payload) before
  calling `consult_for_trigger`, when `event.session_id` is non-empty and the
  var is not already set. Chosen over the two alternatives: having `stop.sh`
  parse the payload would break the "adapters do no parsing" convention, and
  adding a `task_key=` parameter to `consult_for_trigger` widens FEAT-3116's
  settled API surface for a single caller.
- **Budget/dedup paths resolve from the project root, not CWD.**
  `_budget_path` is `Path.cwd() / ".ll" / "advisor-budget" / ...`
  (`advisor.py:373-374`); the hook's CWD is the session CWD, which may be a
  subdirectory. The handler `os.chdir`s to the resolved project root for the
  duration of the consult (or, preferred, the git commands and the dedup file
  both take an explicit root and the handler documents the `Path.cwd()`
  dependency it inherits from `_budget_path`). Pick the explicit-root form if
  it can be done without touching `advisor.py`.
- New adapter `hooks/adapters/claude-code/stop.sh`, copying the two-line
  `INPUT=$(cat) | python3 -m little_loops.hooks pre_done` shape from
  `hooks/adapters/claude-code/subagent-start.sh` (the closer template —
  `precompact.sh`'s extra `timeout`/`statusMessage` wiring lives in
  `hooks.json`, not the script).
- New `Stop` entry in `hooks/hooks.json:199-230` with `"matcher": "*"` and
  `"timeout": 190`, alongside (not replacing) the existing three shell
  scripts.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- The only other production call site of `consult_for_trigger` (`issue_manager.py:820-851`, FEAT-3117's `confidence_gate` trigger) calls `consult_for_trigger` directly and does not call `should_consult` first — `consult_for_trigger` already performs that check internally (`advisor.py:477`). A separate `should_consult` pre-check is redundant with — not required by — the established call convention. **Applied 2026-08-25**: the Proposed Solution bullet above no longer instructs a `should_consult` pre-check; earlier revisions of this issue carried both instructions and contradicted themselves.

## Acceptance Criteria

1. A `Stop` event with a non-empty diff whose SHA differs from the recorded
   `last_diff_sha` triggers exactly one `pre_done` consult, when `pre_done` is
   listed in `advisor.triggers` (FEAT-3038 AC #2).
2. **Per-turn dedup**: a second `Stop` event whose capped diff is byte-identical
   to the one just consulted fires **no** host call and spends no budget. Only
   a consult that actually reached the host updates `last_diff_sha`.
3. With `pre_done` absent from `advisor.triggers`, or `advisor.enabled: false`,
   **no `consult()` host call occurs** (FEAT-3038 AC #3, pre_done half).
   Asserted against `little_loops.advisor.consult`, not against
   `consult_for_trigger` — the wrapper is always invoked and returns
   `skipped_reason="trigger_not_allowed"` / `"disabled"`, so asserting on it
   would be a vacuous test.
4. A `Stop` event with an empty `git diff HEAD` and no untracked files — or a
   root that is not a git work tree, or `find_project_root` returning `None` —
   fires no consult and spends no budget; the handler exits 0 silently.
5. A failed or timed-out consult never blocks the turn — the `Stop` hook
   completes normally (exit 0) with a logged warning whose text contains the
   `skipped_reason`/`error` substring (FEAT-3038 AC #7, pre_done half).
6. A successful consult's verdict is surfaced: `LLHookResult.feedback` is
   non-empty and contains the verdict's `recommendation`, and `exit_code` is
   **0** — the hook never returns 2 (blocking is out of scope; see Expected
   Behavior → Verdict disposition).
7. `advisor.timeout_seconds > 190` short-circuits: the handler logs a warning
   and exits 0 without consulting, rather than guaranteeing a host-killed hook
   that has already spent budget.
8. The `hooks.json` `Stop` entry for `pre_done` carries `"timeout": 190` — a
   test asserts the entry's timeout is `>= AdvisorConfig.timeout_seconds`'s
   default, so the two cannot drift apart silently.
9. `_INTENT_EVENT_NAME`, `_USAGE`, and `_dispatch_table()` stay in sync per
   `test_dispatch_table_intent_event_name_usage_stay_consistent`.
10. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
    `python -m mypy scripts/little_loops/` pass.

## Tests

- `scripts/tests/test_hook_intents.py` — `pre_done` added to
  `test_dispatch_table_intent_event_name_usage_stay_consistent`; a
  `TestHooksMainModule` happy-path subprocess smoke test (per
  `test_dispatch_subagent_start_happy_path:520-533`) and a malformed-payload
  variant (per `test_dispatch_subagent_start_malformed_payload:534-544`);
  trigger-unlisted no-host-call case (AC #3); empty-diff / non-git-root /
  `find_project_root is None` no-op cases (AC #4).
- `scripts/tests/test_advisor.py` (or a new `test_pre_done_hook.py`) — mocked
  `consult()` failure leaves the hook's exit code at 0 and logs a warning
  containing the `skipped_reason` substring (AC #5).
- **Dedup (AC #2)** — invoke `handle()` twice against an unchanged temp git
  repo with `consult` mocked; assert the mock is called exactly once and that
  `last_diff_sha` is written only on the first pass. A third invocation after
  mutating a tracked file must consult again.
- **Verdict surfacing (AC #6)** — mock `consult_for_trigger` to return a
  `ConsultOutcome` with a populated `AdvisorVerdict`; assert
  `result.exit_code == 0` and `verdict.recommendation in result.feedback`.
- **Timeout clamp (AC #7)** and **hooks.json/AdvisorConfig timeout coupling
  (AC #8)** — the latter reads `hooks/hooks.json` and
  `AdvisorConfig().timeout_seconds` and asserts the entry's `timeout` is not
  lower, so a future bump to either side fails loudly.
- **Session-ID plumbing** — assert `handle()` seeds `CLAUDE_SESSION_ID` from
  `event.session_id` when unset, leaves a pre-existing value alone, and that
  the resulting `ConsultOutcome.task_key` is `kind="session"` with the
  payload's ID (not whatever `get_current_session_id()` would have guessed).
  Use `monkeypatch.setenv`/`delenv` so the mutation cannot leak between tests.

## Documentation

- `.claude/CLAUDE.md` — hooks section.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — the new `pre_done` intent.
- `docs/reference/CLI.md`, `docs/reference/API.md` — if the new handler
  introduces any CLI-visible or importable surface beyond the dispatch table.

## Integration Map

_Populated by `/ll:refine-issue` (2026-08-24) and `/ll:wire-issue`, revised by
the 2026-08-25 pre-implementation review._

### Files to Modify
- `scripts/little_loops/hooks/__init__.py` — add `pre_done` to `_INTENT_EVENT_NAME` (:68-80), `_USAGE` (:111-116), and `_dispatch_table()`'s lazy import + `built_ins` dict (:134-165)
- `hooks/hooks.json` — new `"Stop"` block entry with `"matcher": "*"` pointing at the new adapter, added alongside (not replacing) the three existing bash-only Stop entries (:199-230)
- `scripts/little_loops/hooks/pre_done.py` — new handler module (does not exist yet); owns the diff capture + truncation, the dedup state file, the timeout clamp, and the `CLAUDE_SESSION_ID` seeding
- `hooks/adapters/claude-code/stop.sh` — new adapter script (does not exist yet)
- `.gitignore` — **confirmed gap**: `.ll/advisor-budget/` is *not* currently ignored (`git check-ignore` reports no match; `.gitignore:107-122` enumerates `.ll/` entries individually). FEAT-3116 shipped the budget files without an ignore rule; this issue's dedup file compounds it. Add `.ll/advisor-budget/` to `.gitignore` here — per-task consult counters and diff hashes are machine-local runtime state and must not be committed.
- `.ll/advisor-budget/<kind>-<value>.pre_done.json` — new runtime state file (not source), sibling of `_budget_path`'s output

### Dependent Files (Callers/Importers)
- `scripts/little_loops/advisor.py:477` — `consult_for_trigger` internally calls `should_consult`; see the Proposed Solution finding below on what this means for the new handler's call convention
- `scripts/little_loops/issue_manager.py:820-851` — the only other production call site of `consult_for_trigger` (FEAT-3117's `confidence_gate` trigger), the closest precedent for how `pre_done.py` should call it
- `scripts/tests/test_hook_intents.py:827-855` — `test_dispatch_table_intent_event_name_usage_stay_consistent` fails if `pre_done` is added to only one or two of the three `hooks/__init__.py` registration sites

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py` — asserts guide inventory/nav counts referencing `BUILTIN_HOOKS_GUIDE.md`; verify whether adding a `pre_done` section trips a count assertion [Agent 1 finding]
- `scripts/tests/test_doc_counts.py` — asserts hooks-count doc references; verify whether the new `hooks.json` `Stop` entry trips a count assertion [Agent 1 finding]
- Confirmed via `ll-code callers-of`/`importers-of` (graph, fresh): no production callers of `consult_for_trigger`/`should_consult`/`resolve_task_key` exist beyond `advisor.py`/`issue_manager.py` above, and `scripts/little_loops/hooks/__main__.py` imports `hooks/__init__.py` generically via `main_hooks()` — already-correct, intent-agnostic wiring that needs no change for `pre_done`.

### Conventions in Force
- New Python-dispatched hook intents register identically in three places in `hooks/__init__.py` (`_INTENT_EVENT_NAME`, `_USAGE`, `_dispatch_table()`) — enforced only by `test_dispatch_table_intent_event_name_usage_stay_consistent` (`test_hook_intents.py:827`), not by the language.
- Handler `handle(event: LLHookEvent) -> LLHookResult` wraps its entire body in one `try/except Exception`, converging every exception path on `LLHookResult(exit_code=0)` — evidence: `subagent_start.py` (single return outside try) and `pre_compact.py` (return inside except) — both shapes exist in this codebase.
- Claude Code adapter scripts do no parsing — they pipe stdin verbatim and propagate exit code (`echo "$INPUT" | "$PY" -m little_loops.hooks <intent>; exit $?`) — evidence: `hooks/adapters/claude-code/precompact.sh`, `subagent-start.sh`. Of the two, `subagent-start.sh` is the closer template for `stop.sh` — `precompact.sh`'s extra `timeout`/`statusMessage` wiring lives only in `hooks.json`, not the script itself [Agent 3 finding].
- No existing utility in this codebase runs `git diff HEAD` + `git status --porcelain` with truncation. The closest precedents are `worktree_utils.py:format_verify_detail` (452-478, silent tail-keep, no marker) and `work_verification.py:_prepatch_git`/`_prepatch_step_diff` (159-202, subprocess-wrapped `git diff --no-index` against a base_ref, not `HEAD`) — neither is directly reusable; this issue introduces the first `git diff HEAD`-based capture in the codebase.
- `advisor.triggers` is an unvalidated `list[str]` end-to-end (`config-schema.json` `items.type: "string"`, no `enum`; `AdvisorConfig.from_dict` does no validation) — `pre_done` is already documented as an example trigger value in `config-schema.json` and `docs/reference/CONFIGURATION.md:1417`, so no schema/config change is needed to make it a legal value [Agent 2 finding, confirmed via read].
- Fail-soft consult-failure logging follows FEAT-3117's substring-assertion convention (`test_issue_manager.py:5694-5729`: `assert "timeout" in warning_text`), not an exact-string match — `pre_done.py`'s test should assert `skipped_reason`/`error` substring containment in the logged warning, not verbatim text [Agent 2 finding].

### Tests
- `scripts/tests/test_hook_intents.py` — extend `test_dispatch_table_intent_event_name_usage_stay_consistent` (:827); mirror `test_dispatch_subagent_start_happy_path`/`test_dispatch_subagent_start_malformed_payload` (:520-544) for `pre_done`
- `scripts/tests/test_advisor.py` — `TestShouldConsult`/`TestConsultForTrigger` classes (:336, :394) show the mocking convention: mock `little_loops.advisor.consult` (innermost) to assert no-consult branches; mock `little_loops.advisor.consult_for_trigger` (wrapper) with `return_value=outcome` to assert consult-succeeds/fails branches
- `scripts/tests/test_issue_manager.py:5602-5729` — FEAT-3117's sibling wiring tests, the closest existing precedent for testing a new consult-trigger call site end to end

_Wiring pass added by `/ll:wire-issue`:_
- New `scripts/tests/test_pre_done.py` — direct unit tests for `pre_done.handle()`, mirroring `test_pre_compact.py`'s `TestHandleHappyPath` structure (call `handle()` directly, assert `LLHookResult` shape), plus a consult-failure-is-fail-soft case mocking `little_loops.advisor.consult_for_trigger` to return a `ConsultOutcome(error=...)` and asserting `exit_code == 0` [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py` — add a `TestPreDoneStop`-style class mirroring `TestPrecompactState` (:2190), invoking `hooks/adapters/claude-code/stop.sh` via `subprocess.run([str(hook_script)], ...)` [Agent 3 finding]
- `scripts/tests/test_claude_code_adapter.py` — exercises Claude Code adapter shell scripts under `hooks/adapters/claude-code/*.sh`; add `stop.sh` coverage here [Agent 1 finding]

### Documentation
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:494` — `SubagentStart`/`SubagentStop` section is the template to extend with `pre_done`; currently has zero `pre_done` references
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:69-71` — the hook summary table has **three** `Stop` rows; add a fourth for `pre_done` (Blocking column: `—`, Default: `off`). Missed by the original wiring pass, which pointed only at `:494`.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:405-407` — the `Stop` section opener says "Three hooks run after each assistant turn"; update the count and keep the per-turn wording (it is the sentence that corrects this issue's original session-end framing).
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:547` — the config-key table (`| key | events | default | purpose |`) needs an `advisor.triggers` / `advisor.enabled` row scoped to `Stop`.
- `docs/reference/API.md:9524-9541` — `main_hooks()` behavior list enumerates existing Claude Code adapters by name; `stop.sh` needs appending here

_Wiring pass added by `/ll:wire-issue` (optional/advisory — both tables are already stale on `subagent_start`/`subagent_stop`, so adding `pre_done` is precedent-following, not newly required):_
- `docs/reference/HOST_COMPATIBILITY.md` — "Hook intents" table (~line 67-76) omits `subagent_start`/`subagent_stop`; add a `pre_done` row for full-table parity if closing that debt in this pass [Agent 2 finding]
- `docs/ARCHITECTURE.md` — hooks file tree under "Repository Structure" omits `subagent-start.sh`/`subagent-stop.sh`; add `stop.sh` for consistency if closing that debt in this pass [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `scripts/tests/test_pre_done.py` — direct unit tests for `pre_done.handle()`, plus a consult-failure fail-soft case, the dedup pair (AC #2), verdict surfacing (AC #6), the timeout clamp (AC #7), and the `CLAUDE_SESSION_ID` seeding
- Add a `TestPreDoneStop`-style class to `scripts/tests/test_hooks_integration.py`, invoking `stop.sh` via subprocess
- Add `stop.sh` coverage to `scripts/tests/test_claude_code_adapter.py`
- Add the `hooks.json` `timeout` >= `AdvisorConfig().timeout_seconds` coupling assertion (AC #8) — colocate with whichever existing test already parses `hooks/hooks.json`
- Verify `scripts/tests/test_wiring_guides_and_meta.py` and `scripts/tests/test_doc_counts.py` still pass after the guide and hook-manifest edits — update their count assertions if they trip. Note the guide edits now touch **four** places in `BUILTIN_HOOKS_GUIDE.md` (summary table, `Stop` section opener and its "three hooks" count, new `pre_done` subsection, config-key table), so a count assertion tripping is likely rather than hypothetical.

## Program Design

_Populated by `/ll:refine-issue` (2026-08-24), revised by the 2026-08-25
pre-implementation review._

### Types
- `LLHookEvent` fields: `host: str`, `intent: str = ""`, `timestamp: str = ""`, `payload: dict = {}`, `session_id: str | None = None`, `cwd: str | None = None` (`scripts/little_loops/hooks/types.py`)
- `LLHookResult` fields: `exit_code: int = 0`, `feedback: str | None = None`, `decision: str | None = None`, `data: dict = {}`, `stdout: str | None = None` (same file) — `exit_code` 0 = pass, 2 = block + inject `feedback` for Claude Code
- `ConsultOutcome` (return of `consult_for_trigger`): carries `task_key`, `verdict: ... | None`, `skipped_reason: str | None`, `error: str | None` (`scripts/little_loops/advisor.py`)

### Signatures
- `consult_for_trigger(trigger: str, *, question: str, context: str = "", config: BRConfig | None = None, main_host: str | None = None, main_model: str | None = None, manual: bool = False) -> ConsultOutcome` (`advisor.py:451-522`) — internally calls `should_consult(trigger, config, task_key=task_key, manual=manual)` at `advisor.py:477`; never raises.
- `should_consult(trigger: str, config: BRConfig, *, task_key: TaskKey | None = None, manual: bool = False) -> bool` (`advisor.py:408-448`)
- `resolve_task_key(env: dict[str, str] | None = None) -> TaskKey` (`advisor.py:338-371`) — three-tier fallback: `LL_ISSUE_ID` -> `LL_LOOP_RUN_ID` -> `CLAUDE_SESSION_ID`/session_log fallback.
- `handle(event: LLHookEvent) -> LLHookResult` — the required signature for the new `scripts/little_loops/hooks/pre_done.py` module, matching every other handler in the package.

### Call Path
`Stop` event (Claude Code) -> `hooks/adapters/claude-code/stop.sh` (new) -> `python3 -m little_loops.hooks pre_done` -> `main_hooks()` (`hooks/__init__.py:168-227`, builds `LLHookEvent` from stdin JSON; `session_id` sourced from `payload["session_id"]`) -> `pre_done.handle(event)` (new) -> `consult_for_trigger("pre_done", question=..., context=<capped diff>, config=config)` (`advisor.py:451`), which internally runs the `should_consult` gate then calls `consult(...)` (the single host-calling function).

### Decision Rules

Evaluated in order; the first match short-circuits to `LLHookResult(exit_code=0)`.

1. `find_project_root(...)` returns `None`, or the root is not a git work tree, or `git` is unavailable -> no-op.
2. `git diff HEAD` empty AND `git status --porcelain` shows no untracked files -> no-op.
3. `sha256(capped_diff) == last_diff_sha` for this `TaskKey` -> no-op (per-turn dedup; AC #2).
4. `config.advisor.timeout_seconds > 190` -> log warning, no-op (AC #7) — consulting would guarantee a host-killed hook that has already spent budget.
5. Otherwise: seed `CLAUDE_SESSION_ID` if unset, call `consult_for_trigger`, and on a real verdict record `last_diff_sha` and return `feedback` with `exit_code=0`.

Supporting constants and shapes:

- Diff cap: `_DIFF_MAX_LINES = 400` **and** `_DIFF_MAX_BYTES = 96_000`, whichever binds first, with an explicit truncation marker. No existing truncation utility in this codebase produces that shape (see Integration Map -> Conventions in Force); this issue introduces it fresh, there is nothing to reuse. The byte cap is mandatory — 400 lines of a minified bundle or lockfile is megabytes into the advisor prompt.
- Dedup state file: `.ll/advisor-budget/<kind>-<value>.pre_done.json`, `{"last_diff_sha": "<hex>"}`, a sibling of `_budget_path`'s output (`advisor.py:373-374`). Written only after a consult that reached the host — a skipped or failed consult must not poison the dedup, or one transient failure silences the trigger for that diff state permanently.
- `resolve_task_key()` is a pure `os.environ` read with no `session_id` parameter (`advisor.py:338-371`), and `consult_for_trigger` calls it with no arguments (`advisor.py:475`) — the env-seeding step in Proposed Solution is the only way `event.session_id` can reach the budget key without changing FEAT-3116's API.
- `exit_code` is always 0. `LLHookResult.exit_code = 2` (block + inject `feedback`) is deliberately unused here; see Expected Behavior -> Verdict disposition for why, and what a future blocking variant would have to land first (`stop_hook_active`).

## Impact

- **Priority**: P3 — matches parent FEAT-3038.
- **Effort**: Medium — hook intent plumbing across three dispatch sites is
  small, but the diff-capture utility, the dedup state file, and the
  session-ID env contract are all new code with no existing analogue in this
  codebase. Revised up from Small-Medium after the 2026-08-25 review.
- **Risk**: Medium-High — adds a synchronous host call of up to
  `advisor.timeout_seconds` (default **180s**) to `Stop`, which fires after
  *every assistant turn*. A turn producing a new diff state can visibly hang
  for minutes. Mitigations: off by default (`advisor.enabled: false` and
  `pre_done` absent from `advisor.triggers`), fail-soft on every path,
  per-diff-hash dedup so it fires once per distinct diff rather than per turn,
  and the `>190s` clamp. Revised up from Medium — the parent's assessment
  predated the discovery that `Stop` is a per-turn event.
- **Breaking Change**: No — inert unless `advisor.triggers` lists `pre_done`.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1 (pair LLM judgment with a
  non-LLM signal).

## Status

**Open** | Created: 2026-08-08 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-24T01:04:54 - `b39154ec-0980-409b-84ab-ed4ad74fd627.jsonl`
- `/ll:verify-issues` - 2026-08-24T01:01:13 - `cc9bd000-037b-4a44-932a-dc4ed454ef42.jsonl`
- `/ll:confidence-check` - 2026-08-24T00:47:22 - `ac4ebe86-c119-4653-93c7-fc3fe0b64d39.jsonl`
- `/ll:wire-issue` - 2026-08-24T00:29:05 - `b22f0975-b1f0-4ce9-8e05-a02e4f199c80.jsonl`
- `/ll:refine-issue` - 2026-08-24T00:20:49 - `68b44843-12dc-4a31-a007-13664d319cc4.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:56 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:51:42 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:issue-size-review` - 2026-08-08T21:18:50 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`
