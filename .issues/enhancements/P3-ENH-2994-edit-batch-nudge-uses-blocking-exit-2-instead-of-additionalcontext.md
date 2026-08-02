---
id: ENH-2994
title: edit_batch_nudge surfaces as a blocking error; use PostToolUse additionalContext
type: ENH
status: open
priority: P3
captured_at: '2026-08-02T13:44:06Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- hooks
- ux
- host-portability
confidence_score: 100
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 22
---

# edit_batch_nudge surfaces as a blocking error; use PostToolUse additionalContext

## Summary

`little_loops.hooks.edit_batch_nudge.handle` returns `LLHookResult(exit_code=2, feedback=_NUDGE)`
when its nudge fires. On Claude Code, exit 2 from a `PostToolUse` hook renders in the
transcript as **"PostToolUse:Edit hook returned blocking error"** — alarming framing for a
purely advisory token-cost reminder that blocks nothing (the edit has already applied by the
time `PostToolUse` fires).

Claude Code supports a non-error channel that still reaches the model:
`hookSpecificOutput.additionalContext` on a clean exit 0
(`docs/claude-code/hooks-reference.md` § "PostToolUse decision control", the `additionalContext`
row of the field table). Switching transport removes the scary banner while preserving the
hook's entire purpose.

## Current Behavior

- `scripts/little_loops/hooks/edit_batch_nudge.py` (`handle`) returns `exit_code=2` with
  `feedback=_NUDGE` on the single per-session fire.
- `main_hooks()` in `scripts/little_loops/hooks/__init__.py` writes `result.feedback` to stderr
  and returns `result.exit_code`.
- `hooks/adapters/claude-code/edit-batch-nudge.sh` forwards that exit code unchanged
  (its header comment documents exit 2 as deliberate).
- Claude Code renders the result as a **blocking error**, even though nothing is blocked.

The exit code is not gratuitous: the module docstring notes that `exit_code=0` feedback is
stderr-only and never reaches the model, so a naive downgrade to exit 0 + stderr would make
the hook completely invisible to its only audience.

## Expected Behavior

The nudge reaches the model's context via `hookSpecificOutput.additionalContext` with
`exit_code=0`, producing no blocking-error banner:

```json
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "<_NUDGE>"}}
```

Codex — the *only* other host that wires this intent — continues to receive the existing
exit-2 form, since `additionalContext` is a Claude Code schema and its adapter translates
exit codes. (OpenCode and Kimi do **not** wire `edit_batch_nudge` at all:
`hooks/adapters/opencode/index.ts` has no `edit_batch` entry, and
`scripts/little_loops/hooks/adapters/kimi/` wires only the generic `post_tool_use` shim. No
adapter work is needed for either.)

`feedback=_NUDGE` is retained on the Claude Code branch alongside the JSON stdout. Exit-0
stderr is verbose-mode only and never reaches the model (`docs/claude-code/hooks-reference.md`
§ "Exit code output", the **Exit 0** paragraph), so this causes no double injection and no
banner — but it keeps the fire visible in `hook_events.stderr_preview` telemetry (see
Motivation).

## Motivation

The hook is already heavily rate-limited — at most **one** fire per session, and only after a
run of 3 consecutive unbatched single edits (`_NUDGE_THRESHOLD`, `_BATCH_WINDOW_SECONDS`).
So the total cost is one misleading red banner per session. Low severity, but:

- "Blocking error" trains the user (and the model) to distrust hook output that is in fact
  advisory, eroding signal for hooks that *do* block (e.g.
  `hooks/scripts/check-duplicate-issue-id.sh`, which genuinely denies a write).
- The fix is small and the plumbing already exists — `LLHookResult.stdout` is defined
  (`scripts/little_loops/hooks/types.py`) and already written by `main_hooks()` before the
  stderr/exit-code translation, and is already used by the `session_start` intent.

**Telemetry side effect (bonus fix).** `main_hooks()` records every fire into `hook_events`
with `exit_code = result.exit_code` (`scripts/little_loops/hooks/__init__.py:217-219`), and
`history_reader.py:2800` computes each hook's failure rate as `exit_code != 0`. So today
*every* nudge fire is counted as a hook **failure** in `history.db`. Moving to exit 0 removes
that pollution. Two consequences to keep in mind:

- Historical `hook_events` rows for `edit_batch_nudge` are not comparable across the change
  (pre-change fires read as `exit_code=2` failures; post-change fires read as `exit_code=0`).
- Because exit code alone no longer distinguishes a fire from a no-op, `feedback` must stay
  set on the Claude Code branch so `completion.stderr_preview` still records the fire — this
  is the only remaining telemetry signal that the nudge went out.

## Proposed Solution

Branch on host inside `edit_batch_nudge.handle`'s nudge-firing return:

```python
if nudge:
    if event.host == "claude-code":
        return LLHookResult(
            exit_code=0,
            # Retained for hook_events.stderr_preview telemetry only; exit-0
            # stderr is verbose-mode only and never reaches the model, so this
            # does not double-inject the nudge.
            feedback=_NUDGE,
            stdout=json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": _NUDGE,
                    }
                }
            ),
        )
    # Other hosts translate exit codes; exit 2 stays their model-visible channel.
    return LLHookResult(exit_code=2, feedback=_NUDGE)
return LLHookResult(exit_code=0)
```

`event.host` is populated by `main_hooks()` from `LL_HOOK_HOST` and defaults to
`"claude-code"`, which is exactly the adapter contract documented in
`hooks/adapters/claude-code/edit-batch-nudge.sh`.

**Alternative considered and rejected**: plain `exit_code=0` + stderr feedback. This silences
the hook entirely — Claude Code discards exit-0 stderr rather than showing it to the model —
turning the hook into dead weight. Do not implement this variant.

**Alternative considered**: leave as-is. Defensible given the once-per-session cap; this issue
exists because the banner's framing is wrong, not because the frequency is high.

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/edit_batch_nudge.py` — the `handle` return, plus the module
  docstring paragraph that documents exit 2 as the only model-visible channel

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` registers the handler;
  `main_hooks()` already writes `result.stdout` before stderr, so no change expected. Verify
  the ordering does not interleave stdout JSON with any stderr line on the nudge path.
- `hooks/adapters/claude-code/edit-batch-nudge.sh` — forwards exit code and stdout; header
  comment states exit 2 is expected and must be updated
- `scripts/little_loops/hooks/adapters/codex/edit-batch-nudge.sh` — unchanged behavior, but
  confirm it still receives exit 2 (only when `LL_HOOK_HOST=codex` is set)

### Similar Patterns

**No Python handler in this repo emits a `hookSpecificOutput` payload today — this is the
first one.** Plan accordingly: there is no existing serializer helper to reuse, and an inline
`json.dumps` in `edit_batch_nudge.handle` is the intended shape (extracting a shared helper is
out of scope — see Scope Boundaries, which defers migrating other intents). The precedents
below are partial:

- `scripts/little_loops/hooks/session_start.py` — existing `LLHookResult.stdout` producer, but
  it writes merged config JSON, not a `hookSpecificOutput` envelope
- `scripts/little_loops/hooks/user_prompt_submit.py` — mentions `additionalContext` in its
  module docstring (line 12) only; it does **not** emit one. Not a code precedent.
- `hooks/scripts/scratch-pad-redirect.sh:123` and `hooks/scripts/check-duplicate-issue-id.sh:123`
  — the only real `hookSpecificOutput` producers, both shell-side and `PreToolUse`. Same field
  structure, different event and language.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_session_start.py:70` — `handle(LLHookEvent(host="codex", intent="session_start", payload={}))`
  is the closest precedent for constructing an inline non-default `host` in a test. [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py::test_bash_rewritten` (line ~2498-2522) —
  `json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]` is the closest
  precedent for asserting on the JSON shape this issue's fix must produce (shell-side, PreToolUse,
  but same field structure). [Agent 3 finding]

### Tests
- The existing `edit_batch_nudge` test module (find via
  `rg -l edit_batch_nudge scripts/tests/`) — assertions on `exit_code == 2` for the fire case
  must become host-parameterized: exit 0 + parseable `stdout` JSON for `claude-code`,
  exit 2 + `feedback` for a non-Claude host.

_Wiring pass added by `/ll:wire-issue`, corrected by review:_
- `scripts/tests/test_edit_batch_hook.py` — the tests that assert `exit_code == 2` on the
  firing path and need host-parameterization are **four**, not five:
  `TestStatefulNudge::test_run_of_unbatched_edits_nudges_at_threshold` (line 105),
  `test_counter_resets_after_firing` (line 113), `test_nudge_only_fires_once_per_session`
  (line 157), `test_session_change_rearms_nudge` (line 202).
  `_event()` (line 26-32) hardcodes `host="claude-code"` — needs a `host` kwarg.
  `test_nudge_only_fires_once_even_across_batched_resets` was listed here in error — it never
  asserts `exit_code == 2`; it asserts only exit-0 post-fire paths, so it needs the
  negative-assertion treatment below instead. `test_state_records_nudged_flag` needs no change
  (asserts persisted state, not `result.exit_code`).

**CRITICAL — negative assertions go silent without this.** Today `exit_code == 0` *means*
"did not nudge", so every pass-through assertion is load-bearing. After this change a
claude-code fire *also* returns exit 0, so each of these keeps passing even if the nudge
wrongly fires — silently gutting the regression coverage for the threshold, the batch window,
and the once-per-session latch. Every "did not nudge" assertion must gain
`assert result.stdout is None` alongside its `exit_code == 0`:

`scripts/tests/test_edit_batch_hook.py` lines 69, 74, 79, 94, 104, 117, 124, 134, 137, 147,
163, 177, 187, 201, 247, 265, 285 — covering `test_non_edit_tool_passes_through`,
`test_empty_payload_passes_through`, `test_read_tool_passes_through`,
`test_single_edit_does_not_nudge`, `test_batched_edits_never_nudge`,
`test_multiedit_never_nudges_and_resets_run`, `test_session_change_resets_run`, the post-fire
loops in `test_nudge_only_fires_once_per_session` and
`test_nudge_only_fires_once_even_across_batched_resets`, the non-firing prefixes of
`test_run_of_unbatched_edits_nudges_at_threshold` / `test_counter_resets_after_firing` /
`test_session_change_rearms_nudge`, and the no-op/write-failure tests
(`test_no_project_and_no_claude_project_dir_is_noop`,
`test_claude_project_dir_anchors_state_there`, `test_state_write_failure_passes_through`).
- `scripts/tests/test_hook_intents.py::TestDispatchEditBatchNudge::test_dispatch_edit_batch_nudge_happy_path`
  (line ~380-407) — a **second, previously-unlisted breakage site**: a subprocess-level CLI
  dispatch test (`python -m little_loops.hooks edit_batch_nudge`) that sets no `LL_HOOK_HOST`
  (defaults to `claude-code`) and asserts `returncode == 2` / `"batch" in result.stderr.lower()`.
  Will break identically to the `handle()`-level tests once the claude-code branch routes
  through stdout/exit 0. [Agent 3 finding]
- No existing Python test constructs/asserts a `hookSpecificOutput.additionalContext` JSON
  shape from a `handle()` return — model new assertions after
  `test_hooks_integration.py::test_bash_rewritten` (line ~2498-2522, `json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]`
  pattern) combined with the `host=` construction style at `test_hook_session_start.py:70`
  (`LLHookEvent(host="codex", ...)`). [Agent 3 finding]

### Documentation
- `hooks/adapters/codex/README.md` — the stdout channel table lists `session_start` as the only
  stdout producer; add `edit_batch_nudge` (Claude Code only)
- `docs/reference/API.md` — if it documents the handler's return contract

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — the hooks summary table row for `edit-batch-nudge`
  states the mechanism as unconditionally `exit 2`, and the "Edit-batch nudge" prose section
  says "Returns exit 2 so the reminder reaches the model's context." Both need updating to
  describe the host-conditional behavior. [Agent 2 finding]
- `CHANGELOG.md` (historical Tier-0 quick-wins entry) also states the mechanism as "exit 2" —
  informational only per this repo's changelog convention (no `[Unreleased]` section, don't
  amend old entries); no edit required, noted so the discrepancy isn't mistaken for a bug
  later. [Agent 2 finding]

### Configuration
- N/A

## Program Design

### Types

- No new types. Reuses `LLHookResult(exit_code: int, feedback: str | None, stdout: str | None)`
  from `little_loops.hooks.types`.

### Signatures

- `handle(event: LLHookEvent) -> LLHookResult` — unchanged signature; return value varies by
  `event.host` on the nudge path only.

### Call Path

`hooks/adapters/claude-code/edit-batch-nudge.sh` -> `little_loops.hooks.main_hooks` ->
`edit_batch_nudge.handle` -> (`result.stdout` written by `main_hooks`) -> Claude Code
`PostToolUse` JSON parser

## Implementation Steps

1. Add the host-branched return to `edit_batch_nudge.handle`; import `json` (already imported).
   Keep `feedback=_NUDGE` set on the Claude Code branch (telemetry; see Motivation).
2. Update the module docstring's exit-2 rationale paragraph and the Claude Code adapter's
   header comment to describe both channels.
3. Parameterize the existing nudge-fires test over `host` (`claude-code` -> exit 0 + JSON stdout;
   `codex` -> exit 2 + feedback); assert the stdout parses and carries
   `hookSpecificOutput.hookEventName == "PostToolUse"`.
4. Update `hooks/adapters/codex/README.md`'s stdout-channel table.
5. Verify manually: trigger 3 unbatched single edits in a fresh Claude Code session and confirm
   the nudge lands with no blocking-error banner.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Host-parameterize the four firing-path `TestStatefulNudge` tests in
   `scripts/tests/test_edit_batch_hook.py` listed above (add a `host` kwarg to `_event()`);
   `test_state_records_nudged_flag` needs no change.
6a. **Strengthen every negative assertion** in `scripts/tests/test_edit_batch_hook.py` with
   `assert result.stdout is None` next to its `exit_code == 0` (full line list in Tests above).
   Without this the change silently removes the coverage that the nudge does *not* fire.
   Sanity check: temporarily force `handle` to always nudge and confirm the pass-through tests
   fail; they pass today under that mutation only because exit 0 is no longer discriminating.
7. Update `scripts/tests/test_hook_intents.py::TestDispatchEditBatchNudge::test_dispatch_edit_batch_nudge_happy_path`
   — the subprocess-dispatch companion test that also hard-codes exit-code-2 semantics.
8. Update `docs/guides/BUILTIN_HOOKS_GUIDE.md`'s hooks summary table row and "Edit-batch nudge"
   prose section to describe the host-conditional behavior instead of unconditional `exit 2`.

## Impact

- **Priority**: P3 - Cosmetic/trust issue on an advisory hook that is already capped at one fire
  per session. No functional breakage.
- **Effort**: Small - One branched return, one docstring, one adapter comment, one
  parameterized test, one README table row. All plumbing (`LLHookResult.stdout`,
  `main_hooks()` stdout write) already exists.
- **Risk**: Low - The behavior change is confined to the single nudge-firing branch; every
  non-fire path already returns exit 0. Main risk is a Claude Code version that ignores
  `PostToolUse.additionalContext`, which would silently drop the nudge — hence the manual
  verification step. Guard by keeping exit 2 for non-Claude hosts.
- **Breaking Change**: No

## Backwards Compatibility

Non-Claude hosts see byte-identical behavior. On Claude Code the hook's exit code changes
2 -> 0 for the fire case, which no automation consumes (the adapter is the only caller and it
forwards the code to the host).

## Success Metrics

- Nudge fires in a Claude Code session with no "hook returned blocking error" banner in the
  transcript.
- Model context contains the nudge text (confirm via the injected-context reminder or a
  follow-up batched edit).
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

**In scope**: the transport of the existing nudge message.

**Out of scope**: changing `_NUDGE_THRESHOLD`, `_BATCH_WINDOW_SECONDS`, the once-per-session
latch, the nudge text itself, or migrating other hook intents off exit 2. Auditing the rest of
the `LLHookResult` exit-2 users for the same framing problem is a separate issue if wanted.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/claude-code/hooks-reference.md` § PostToolUse decision control | Defines the `additionalContext` field and JSON shape this issue adopts |
| `docs/reference/HOST_COMPATIBILITY.md` | Host-capability differences that motivate the `event.host` branch |
| `hooks/adapters/codex/README.md` | Documents the stdout channel per intent; needs a new row |

## Session Log
- `/ll:confidence-check` - 2026-08-02T23:00:40 - `d76746ac-4ba6-4c06-9cbe-c32a23962287.jsonl`
- `/ll:confidence-check` - 2026-08-02T22:07:38 - `d288e8d9-e72d-4fc5-a110-cda8245ba0ef.jsonl`
- `/ll:wire-issue` - 2026-08-02T17:09:15 - `d7f5411e-7a9d-4bf5-bae1-030f4a53dae3.jsonl`
- `/ll:refine-issue` - 2026-08-02T16:53:50 - `971b00cc-0a51-43c1-8fd9-6f984aead353.jsonl`
- `/ll:capture-issue` - 2026-08-02T13:45:10 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

---

## Status

**open** - Captured 2026-08-02
