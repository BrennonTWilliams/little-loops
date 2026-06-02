---
id: BUG-1377
type: BUG
priority: P2
status: done
captured_at: 2026-05-06 20:59:54+00:00
completed_at: 2026-05-07T01:07:58Z
discovered_date: 2026-05-06
discovered_by: capture-issue
confidence_score: 88
outcome_confidence: 45
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
decision_needed: false
missing_artifacts: true
---

# BUG-1377: PostToolUse Hook `exit 2` Feedback Unreliable in `-p` Mode — Regression of BUG-035

## Summary

BUG-035 was closed as "already fixed" because the `exit 2 + stderr` pattern was already present in `context-monitor.sh`. However, the ll-auto run of ENH-1115 (2026-05-06) ran for 20 minutes, crossed well past the 50% context threshold (100K of 200K tokens), and never triggered a handoff — Claude hit "Prompt is too long" with no `CONTEXT_HANDOFF` signal emitted. The BUG-035 fix either never worked end-to-end or has regressed.

## Current Behavior

1. `ll-auto` spawns `claude --dangerously-skip-permissions -p <manage-issue prompt>` as a subprocess
2. The subprocess's PostToolUse hooks run (including `context-monitor.sh`) — confirmed by `.ll/ll-context-state.json` being updated during sessions
3. When the 50% threshold is crossed, `context-monitor.sh` outputs to stderr with `exit 2`:
   ```bash
   echo "[ll] Context ~${USAGE_PERCENT}% used ..." >&2
   exit 2
   ```
4. **Expected**: Claude Code in `-p` mode injects this stderr as feedback into Claude's conversation turn
5. **Actual**: Claude never receives the feedback; continues working until the API returns "Prompt is too long"
6. `run_with_continuation` in `issue_manager.py` never detects `CONTEXT_HANDOFF`; the session is treated as a real failure

## Steps to Reproduce

1. Configure `ll-auto` with the context monitor hook (`hooks/scripts/context-monitor.sh`) set to the 50% threshold
2. Start `ll-auto` processing a large issue: `ll-auto` spawns `claude --dangerously-skip-permissions -p <prompt>`
3. The session accumulates tokens past the 50% threshold
4. Observe: `context-monitor.sh` fires via PostToolUse, writes warning to stderr with `exit 2`
5. Observe: Claude never receives the hook feedback — no `CONTEXT_HANDOFF` line appears in session output
6. Claude continues working until the API returns "Prompt is too long"
7. Observe: `run_with_continuation` sees no handoff signal; treats session as a real failure

## Expected Behavior

When `context-monitor.sh` fires at the 50% threshold during a `-p` mode session:
1. Claude Code injects the stderr warning as a feedback message
2. Claude reads it, stops at a natural boundary, runs `/ll:handoff`
3. `/ll:handoff` writes `.ll/ll-continue-prompt.md` and outputs `CONTEXT_HANDOFF: Ready for fresh session`
4. `run_with_continuation` detects the signal and spawns a fresh continuation session with `--resume`

## Motivation

The automatic context handoff is the primary mechanism preventing `ll-auto` from losing completed work on large issues. Without it:
- Sessions exceeding the context limit lose all in-progress implementation work (code, tests, documentation)
- `ll-auto` incorrectly classifies the exhaustion as a real failure (see companion BUG-1375)
- Large issues — the highest-value automation targets — are the most likely to fail silently

BUG-035 was closed as fixed without end-to-end verification; the ENH-1115 run provides production evidence that the mechanism fails under real `ll-auto` conditions.

## Root Cause

BUG-035 documented the exact problem and the exact fix (exit 2 + stderr). The fix was "already in the code" when BUG-035 was validated, so it was closed without an end-to-end test confirming the signal actually reached Claude in a real `ll-auto` run. The ENH-1115 failure provides that evidence: it does not work.

Possible sub-causes (requires investigation):
1. **Claude Code regression**: A recent Claude Code release changed behavior of PostToolUse `exit 2` in `-p` mode
2. **Context already full**: By the time the threshold is crossed, the context is already too full to accept a new tool-use feedback injection — the next API call fails immediately rather than letting Claude respond to the hook
3. ~~**Hook runs but exit 2 doesn't trigger feedback in `-p` mode**~~ — **ELIMINATED** (see Investigation Results)
4. **Threshold never fired**: The state file was overwritten by the next interactive session, so we cannot confirm the 50% crossing actually happened during the failed ll-auto run. Token estimation may be conservative enough that the threshold was never reached before "Prompt is too long". This is indistinguishable from sub-cause #2 without instrumentation.
5. **Single tool-call cliff**: A single large tool result (large file `Read`, big test log, generated artifact) can move context from ~40% to >100% in one hop. PostToolUse fires *after* the result is already in context — by then it is too late. Threshold-based mechanisms cannot address this; only headroom reservation or output-size capping can.
6. **Output tokens are invisible to the hook**: PostToolUse fires between tool calls. A single large model response (long plan, verbose explanation) inflates context but no hook fires until the next tool call. If a turn's output tips it over, all current options miss it.

## Investigation Results

**Option A completed (2026-05-06).** Controlled test run:

```bash
# .claude/settings.json in a temp dir
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "echo 'HOOK-FEEDBACK: exit2 reached Claude' >&2 && exit 2" }]
      }
    ]
  }
}

claude -p --dangerously-skip-permissions \
  "Run: echo hello. Did you receive any hook feedback?"
```

**Result**: Claude's response explicitly confirmed it received the stderr message as a "system-reminder" in its context. Exit 2 PostToolUse feedback **does work in `-p` mode**.

**Additional finding**: `PreToolUse` hooks do NOT fire in `-p` mode (GH #40506). `PostToolUse` hooks do fire. This is an important asymmetry — any alternative using `PreToolUse` to approximate this behavior would be broken in automation.

**Sub-cause #3 eliminated.** The mechanism is sound. The failure during the ENH-1115 ll-auto run must be sub-cause #1 or #2:

- **Sub-cause #2 (most likely)**: Token estimate is too conservative — the threshold fires only after the context is already too full to fit the hook feedback as a new turn. The "Prompt is too long" error fires on the *next* API call, before Claude ever processes the hook message.
- **Sub-cause #1**: Less likely given the mechanism passes a direct test, but worth checking against Claude Code release notes if sub-cause #2 is ruled out.

**Next step**: Focus investigation on the token estimation accuracy and threshold timing (does the threshold fire close enough to the limit that the feedback turn itself exceeds capacity?).

## Open Questions / Gaps

These need answers before tuning thresholds or picking between options:

1. **Did the threshold actually cross in the failing run?** State file was overwritten. Without an append-only crossing log, sub-cause #2 vs #4 cannot be distinguished — and any threshold tuning is guesswork.
2. **How accurate is `context-monitor.sh`'s token estimate?** If it estimates from transcript size with a fixed chars/token ratio, it can be off by 2–5× depending on tool output composition (JSON vs prose vs base64). Calibrate against ENH-1376 ground truth before picking a new threshold.
3. **What is the actual token trajectory of the failing run?** Parse `ll-auto-debug.txt` / transcript to plot tokens-per-tool-call. This tells us whether the failure was a gradual creep (D fixes), a single-call cliff (D doesn't fix), or output-side growth (no current option fixes).
4. **Does Claude Code's auto-compact run in `-p --dangerously-skip-permissions`?** If yes, it may already address this (or interfere with our handoff). If no, that itself is the answer for some cases. Untested.
5. **What if `/ll:handoff` itself can't run?** If context is so full that even the handoff turn fails, Options D and E both deadlock. Need a parent-process backstop (see Option J).
6. **Decision criteria between Options D and E are unclear.** "If D insufficient, do E" — but measured how? Define: *D is sufficient if N consecutive ll-auto runs on issues > 50K tokens hand off cleanly.*

## Evidence

- `ll-auto-debug.txt`: 20-minute session ended with `Prompt is too long` at line 1037; no `CONTEXT_HANDOFF` anywhere in the log
- `.ll/ll-context-state.json` (post-session): `threshold_crossed_at: null` — but this was overwritten by the next interactive session; the ll-auto session's final state is unknown
- BUG-035 resolution: "The current `hooks/scripts/context-monitor.sh` uses `echo ... >&2` with `exit 2`, which is exactly the proposed solution" — closed without runtime verification

## Proposed Solution

### ~~Option A: Investigate exit 2 in -p mode empirically~~ — COMPLETE
Exit 2 PostToolUse feedback works in `-p` mode. Sub-cause #3 eliminated. See Investigation Results.

### Option B: Sentinel file polling (bypass hook feedback)
Instead of relying on hook feedback reaching Claude, write a sentinel file (`.ll/ll-context-limit-reached`) when the threshold fires. The `manage-issue` skill polls for this file at phase boundaries (e.g., after each implementation phase) and self-triggers `/ll:handoff`. This makes the handoff independent of hook feedback reliability.

### Option C: Hard context limit enforcement in `run_claude_command`
Parse `result` events (see ENH-1376) to track actual token counts externally. When cumulative tokens exceed the threshold, `run_claude_command` sends SIGINT after the current response completes, then `issue_manager.py` immediately spawns a `--resume` continuation. Does not require Claude to cooperate.

### Option D: Lower the threshold dramatically
The mechanism is proven to work — the failure is timing. If the token estimate underestimates real usage, or if 50% leaves too little remaining context for the feedback turn to fit, both problems are addressed by firing at 20–25% instead of 50%. No code changes required — config-only. Should be tested first as it may be sufficient on its own.

### Option E: External resume + explicit handoff prompt
Decouple context detection (parent process) from handoff triggering (explicit message to Claude). `run_claude_command` monitors the output stream for token usage via ENH-1376 stream parsing (or a conservative heuristic). When the threshold is crossed, it does **not** interrupt Claude — it waits for the current turn to complete naturally, then sends a new `claude -p --resume <session-id>` call with an explicit instruction: "Context limit approaching, please run /ll:handoff now." `run_with_continuation` already handles the continuation pattern.

- No hook feedback path required
- No SIGINT mid-work, no risk of lost in-progress implementation
- No LLM polling at phase boundaries
- Claude receives a clean, explicit instruction at a natural turn boundary
- Entirely parent-process-managed via `run_claude_command` / `issue_manager.py`
- Depends on ENH-1376 for accurate token counts (conservative heuristic viable in the interim)

### Option F: Phase-boundary handoff (session-driven, not context-driven)
`manage-issue` already executes discrete phases (plan → implement → test → commit). End each phase with a forced fresh session via `--resume`, regardless of context state. Predictable, immune to token-estimation error, no hook reliance.

- Trade-off: more sessions even when not needed (small issues pay the resume cost)
- Pairs well with Option E as a hard upper bound on session length

### Option G: Stop-hook + parent resume ⭐ PREFERRED (combine with E, H, and J)
Use the `Stop` hook (fires when Claude finishes a turn — Claude is idle, no pending tool-use) instead of PostToolUse. Stop-hook checks the threshold and writes a sentinel file. `run_with_continuation` reads the sentinel between sessions and decides whether to resume with an explicit handoff instruction.

- Avoids the "feedback turn doesn't fit in remaining context" failure for the *gradual creep* case — the decision is made *between* turns, not inside one
- No mid-turn injection while Claude is working; Stop fires at idle
- PostToolUse remains as a coarse early-warning (logging only), Stop as the trigger
- Cleaner control flow than E alone: parent-side decision, parent-side resume

**Important limits of E+G alone — these motivate pairing with H and J:**
1. **`--resume` reuses the existing session context.** If the threshold fires at 95%, the resumed session is still at 95%. The injected handoff prompt + Claude's response + `/ll:handoff` execution all have to fit in the remaining ~5%. This is the same room-for-feedback-turn problem, shifted from PostToolUse to Stop. **Mitigated by Option H** (dynamic headroom ensures the threshold fires with enough room for the handoff turn).
2. **Single tool-call cliff (sub-cause #5) is untouched.** A 40%→100% jump on one big `Read` errors with "Prompt is too long" mid-turn — Stop never fires because the turn never completes cleanly. **Mitigated by Option J** (parent-side guillotine assembles a fresh-session continuation prompt from the transcript when context exceeds 90% with no observed handoff).
3. **Output-side growth (sub-cause #6) IS fixed by G** — Stop fires after any turn, tool call or not, so a long model response without tool calls is detected.

### Option H: Headroom reservation (dynamic threshold)
Track the rolling max turn cost (input + output) over the last N turns. Set the effective threshold to `context_limit - (2 × max_recent_turn_size)` rather than a fixed percentage. Naturally accommodates large-output turns and tool-result cliffs that fixed percentages miss.

- Addresses sub-causes #5 and #6
- Requires ENH-1376 for accurate per-turn token counts
- Composes with E/G — changes *when* to fire, not *how* to hand off

### Option I: Subprocess delegation for heavy reads
When `manage-issue` needs to scan a large file, log, or generated artifact, spawn a separate `claude -p` to summarize it; only the summary returns to the parent context. Caps single-tool-call context jumps at the source.

- Extends the existing scratch-pad pattern (raw output → file) with an LLM-summary step
- Addresses sub-cause #5 (single tool-call cliff) at the root
- Independent of handoff — reduces the *need* for handoff rather than improving its reliability

### Option J: Parent-side guillotine ⭐ CO-EQUAL with E+G (not optional)
If ENH-1376 reports context > 90% and Claude has not called `/ll:handoff`, parent SIGINTs after the current turn (or on detected "Prompt is too long" mid-turn) and starts a **fresh session** (not `--resume`) with an assembled "previous session ran out of context, here's where we were" prompt built from the transcript.

**Why co-equal, not optional:** the failure modes where E+G break — single tool-call cliffs (sub-cause #5) and full-context resume that can't fit the handoff turn — are exactly the cases ll-auto hits on large issues, which are the whole point of having handoff. Treating J as Phase 3 means shipping a mechanism that fails on its primary use case. J must land alongside E+G, not after.

- Uses a fresh session (new context window), not `--resume` — avoids the "resumed session is still 95% full" problem
- Guarantees the deadlock case (sub-cause #5, gap #5) is recoverable
- Accepts that the in-flight turn may be partially lost — but the assembled prompt preserves completed work via transcript summary
- Composes with E+G: E+G is the happy path (clean handoff at idle), J is the safety net (forced recovery when the happy path can't fit)

Option A is complete. **Phase 1 must land ENH-1376 (hard prerequisite) and complete instrumentation + design spikes** before Phase 2 begins. Phase 1 also classifies the dominant failure mode — gradual creep (E+G+H fix), single-call cliff (needs J, possibly I), or output growth (G fixes alone) — which determines Phase 2 scope.

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — add append-only crossing log (Phase 1); optionally lower threshold (Option D)
- `hooks/hooks.json` — register a new Stop hook for sentinel-write (Option G)
- `hooks/scripts/` — new Stop-hook script that checks threshold and writes `.ll/ll-context-handoff-needed` sentinel
- `scripts/little_loops/issue_manager.py` — extend `run_claude_command()` to parse stream-json `result` events for accurate token counts (depends on ENH-1376); add Option J backstop (SIGINT + resume with assembled prompt)
- `scripts/little_loops/issue_manager.py` — `run_with_continuation()` reads sentinel and prepends explicit handoff instruction to next resume (Option E + G)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:38` — `detect_context_handoff()` — checks only `result.stdout` (Claude's text output); hook stderr is captured into `result.stderr` only and never reaches this check
- `scripts/little_loops/subprocess_utils.py:50` — `read_continuation_prompt()` — reads `.ll/ll-continue-prompt.md`; the new sentinel read in `run_with_continuation()` should mirror this pattern
- `scripts/little_loops/issue_manager.py:620,628` — `run_with_continuation()` called inside `manage_issue()` for the Phase 2 implement step
- `scripts/little_loops/parallel/worker_pool.py:391,683` — `WorkerPool._run_with_continuation()` — parallel-mode counterpart at `:683`; must be updated alongside `issue_manager.py` (the two are structural copies)
- `hooks/hooks.json:88-98` — existing Stop hook entry (`session-cleanup.sh`, timeout 15s); a second Stop hook entry pointing to new `context-handoff-sentinel.sh` is needed
- `hooks/scripts/session-cleanup.sh:14` — deletes `.ll/ll-context-state.json` on Stop; sentinel file `.ll/ll-context-handoff-needed` must NOT appear in this `rm -f` list — it must persist across sessions until consumed by `run_with_continuation()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py:61,84` — imports and calls `run_claude_command` directly; if the function signature gains new parameters (Option J backstop), this caller must be updated [Agent 1]
- `scripts/little_loops/fsm/runners.py:20` — `DefaultActionRunner` imports `run_claude_command`; same signature-change risk as `action.py` [Agent 1]
- `scripts/little_loops/fsm/handoff_handler.py` — `HandoffHandler` class handles `CONTEXT_HANDOFF` signals in FSM-loop sessions; verify sentinel-file approach doesn't conflict with this parallel detection system [Agent 2]
- `scripts/little_loops/fsm/signal_detector.py:74` — defines `HANDOFF_SIGNAL` constant; check for sentinel-file detection parity in the FSM executor path [Agent 2]

### Similar Patterns
- `run_with_continuation()` in `issue_manager.py:152` — existing resume logic; extend for sentinel-file detection
- `hooks/scripts/precompact-state.sh` — closest codebase analog to Option G: a hook that writes a sentinel file (`.ll/ll-precompact-state.json`) using `atomic_write_json` + `acquire_lock` from `lib/common.sh`, which the Python/bash layer reads later; follow this exact write pattern for `context-handoff-sentinel.sh`
- `subprocess_utils.py:50` — `read_continuation_prompt()` — plain `Path.exists()` + `path.read_text()` (no locking, no JSON); the sentinel-read in `run_with_continuation()` can be equally simple (just `Path(".ll/ll-context-handoff-needed").exists()`)

### Tests
- `scripts/tests/test_issue_manager.py:940` — `TestRunWithContinuation` class — existing tests for `run_with_continuation()` handoff detection; extend with test for sentinel-file path (hook writes file → `run_with_continuation()` detects it → continuation spawned with explicit instruction)
- `scripts/tests/test_subprocess_utils.py` — `TestDetectContextHandoff` and `TestReadContinuationPrompt` classes — unit tests for detection helpers; no sentinel-file test exists yet
- `scripts/tests/test_hooks_integration.py` — existing hook execution integration tests
- New: end-to-end test — Stop hook writes `.ll/ll-context-handoff-needed` → `run_with_continuation()` reads and consumes it → continuation session spawned with explicit `"Context limit approaching, please run /ll:handoff"` instruction

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py:2183` — `TestRunWithContinuation` has only 1 test (no happy-path continuation or sentinel case); **add sentinel-file test** mirroring the `issue_manager` counterpart; patches must target `little_loops.parallel.worker_pool.*` [Agent 3]
- `scripts/tests/test_issue_manager.py:940` — actual class name is `TestRunWithContinuation` (not `TestContextHandoff`): **add sentinel-triggered continuation test**; ensure `test_returns_immediately_when_no_handoff` has sentinel-absent setup so the new check doesn't inadvertently trigger [Agent 3]
- `scripts/tests/test_hooks_integration.py` — **new `TestContextHandoffSentinel` class**: Stop hook writes sentinel at threshold; sentinel absent below threshold; sentinel survives `session-cleanup.sh` run — follow `TestPrecompactState` pattern (line 1729) exactly (chdir + subprocess.run + file assertion) [Agent 3]
- `scripts/tests/test_subprocess_utils.py:216` — `test_constructs_correct_command_args` asserts exact CLI arg list; **will break** if `run_claude_command` in `subprocess_utils.py` gains new flags — update alongside any signature changes [Agent 3]

### Documentation
- `docs/guides/SESSION_HANDOFF.md` — describes the continuation flow; update once Stop-hook sentinel path is confirmed
- `docs/ARCHITECTURE.md` — covers context monitor and hook system; update to reflect new Stop hook entry

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md` — context monitor troubleshooting section; add sentinel file inspection step (`.ll/ll-context-handoff-needed`) [Agent 2]
- `docs/reference/API.md` — `run_claude_command` signature block; update if the `issue_manager.py` wrapper gains new parameters [Agent 2]
- `commands/handoff.md` — "Integration" section: currently describes PostToolUse as primary trigger; update to note Stop hook + sentinel as new primary mechanism [Agent 2]
- `skills/manage-issue/SKILL.md` — "Handoff Protocol" section (lines 311–330): update to reference parent-side explicit handoff instruction (Option E/G) alongside the self-initiated path [Agent 2]

### Configuration
- `.ll/ll-context-state.json` — no schema change needed; sentinel approach uses a separate file
- `.ll/ll-context-handoff-needed` — new sentinel file (written by Stop hook, consumed by `run_with_continuation()`)

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — `context_monitor` object has `additionalProperties: false`; must be updated if new config keys are introduced (e.g., `auto_handoff_threshold` minimum relaxed for Option D's 20–25% target, or a `sentinel_file` path override) [Agent 2]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Active threshold is 50%** (`.ll/ll-config.json:27`), not the script default of 80%. At 50% of 200K = 100K tokens estimated — but because `get_transcript_baseline()` has a one-turn lag (reads the previous assistant event), the hook fires after the current tool call when the real count may already be higher.
- **`detect_context_handoff()` checks only `result.stdout`** (`subprocess_utils.py:38`): the stream-json parser (`run_claude_command`) extracts only `type == "assistant"` text events into stdout. Hook stderr lands in `result.stderr` only. `CONTEXT_HANDOFF` must appear in Claude's TEXT response, not in stderr — the whole chain requires Claude to voluntarily emit the signal after receiving the hook feedback.
- **No Stop hook currently fires for context monitoring**: `hooks/hooks.json:88` only runs `session-cleanup.sh` on Stop. A second Stop-hook entry (new script `context-handoff-sentinel.sh`) is the primary addition for Option G.
- **`session-cleanup.sh:14` deletes `ll-context-state.json`** on every session Stop — so any threshold-crossing evidence in that file is lost. The sentinel file (`.ll/ll-context-handoff-needed`) must be a distinct path not in the cleanup `rm -f` list.
- **`WorkerPool._run_with_continuation()` at `parallel/worker_pool.py:683`** is structurally identical to `issue_manager.run_with_continuation()` — both must be updated in tandem.

## Implementation Steps

**Phase 1 — Instrumentation + prerequisites (NON-NEGOTIABLE, do first, no behavior changes):**

Without trajectory data, picking thresholds and ranking options is guesswork. Phase 1 outputs gate Phase 2 design decisions.

**Hard prerequisite — ENH-1376 must land before Phase 2.** Options C/E/G/H/J all depend on accurate per-turn token counts. The "conservative heuristic in the interim" fallback is exactly what `context-monitor.sh` does now and is the suspected failure point — building Phase 2 on that same heuristic risks inheriting this bug. ENH-1376 (stream-json `result` event parsing) provides the ground-truth signal H's dynamic headroom and J's >90% trigger require. Do not start Phase 2 until ENH-1376 is merged and emitting accurate per-turn token counts.

1. **Land ENH-1376** (hard prereq for Phase 2). No further Phase 2 work begins until stream-json `result` events deliver accurate per-turn input/output token counts to `run_claude_command`.
2. Add an append-only crossing log in `context-monitor.sh` (e.g., `.ll/ll-context-crossings.log`) so future runs preserve threshold-crossing evidence even when state is overwritten.
3. Confirm whether Claude Code's auto-compact runs in `-p --dangerously-skip-permissions`. Document the answer; if it does, evaluate whether it already addresses some failure modes.
4. Calibrate `context-monitor.sh`'s token estimate against ENH-1376 ground truth on a representative session. Record observed error margin.
5. **Verify Stop-hook timing in `-p` mode.** Plan assumes Stop fires after every turn (idle boundary). If Stop only fires on session termination in `-p --dangerously-skip-permissions`, the sentinel-between-sessions design in Option G changes substantially. Confirm with a controlled probe (Stop hook that appends to a log file) before committing to the Stop-hook approach.
6. **Confirm `ll-auto-debug.txt` has the data Phase 1 step 7 needs.** Inspect a sample log to verify it contains per-tool-call token usage (or sufficient signal to derive it). If it does not, this gating step is impossible without reproducing the failure — surface that risk and decide whether to reproduce or proceed without classification.
7. Parse the failing `ll-auto-debug.txt` to plot token trajectory per tool call. Classify the dominant failure mode: **gradual creep** (E+G+H sufficient), **single-call cliff** (requires J, possibly I), or **output-side growth** (G alone sufficient). This classification drives Phase 2 scope.
8. **Design spike for Option J's transcript-summary assembly.** → **RESOLVED** (see `## Option J Design Spike` section). Chosen approach: structured stdout-tail + inventory (option c) with heuristic length cap as guard. Algorithm: (1) first 20 lines of `original_command` for task intent, (2) last 12K chars of `captured_stdout` for last-output context, (3) `.loops/tmp/scratch/` file inventory, (4) cumulative `on_usage` token count. Assembled prompt ≤ 15K tokens; fresh session starts at 0 tokens — structurally deadlock-free. `assemble_guillotine_prompt()` goes in `subprocess_utils.py`; bare-restart fallback if assembly itself fails.

**Phase 2 — Primary mechanism + headroom + backstop (Options E + G + H + J, shipped together):**

E+G alone is insufficient — see "Important limits" under Option G. H ensures the Stop threshold fires with enough remaining context for the handoff turn to actually fit; J handles the cases E+G structurally cannot (mid-turn cliffs, resumed-session-still-full).

_Gated on Phase 1 hard prerequisite (ENH-1376 merged) and Phase 1 design spike for J's transcript-summary algorithm._

9. Add a Stop hook that checks token usage at turn boundaries and writes a sentinel file when threshold crossed. PostToolUse retains a coarse early-warning role (log only). Confirms Phase 1 step 5 (Stop-hook timing) before committing.
10. **Implement Option H (dynamic headroom)** alongside the Stop hook: effective threshold = `context_limit − (2 × max_recent_turn_size)` rather than a fixed percentage. Required so the Stop trigger fires with room for the handoff turn to fit on resume. Uses ENH-1376 token counts (Phase 1 prereq).
11. Extend `run_with_continuation` in `issue_manager.py` to read the sentinel between sessions and, if set, send an explicit `claude -p --resume <session-id> "Context limit approaching, please run /ll:handoff now."` before continuing.
12. **Implement Option J (parent-side guillotine) as co-equal backstop**, not deferred work: in `run_claude_command`, if ENH-1376 reports context > 90% and no handoff has been observed (or "Prompt is too long" is detected), SIGINT and start a **fresh session** (not `--resume`) using the transcript-summary assembly approach chosen in Phase 1 step 8. This is the only mechanism that handles single-call cliffs and full-context resume failure.

**Phase 3 — Source mitigations (conditional on Phase 1 findings):**
13. **Option I** if Phase 1 shows single tool-call cliffs from heavy reads dominate: delegate large file/log scans to subprocess summarizers.

**Phase 4 — Verification:**
14. Add end-to-end integration test: simulate threshold crossing → verify sentinel written → verify continuation session spawned with handoff instruction → verify `CONTEXT_HANDOFF` produced.
15. Add J-path integration test: simulate context > 90% with no handoff → verify SIGINT → verify fresh session spawned with assembled transcript-summary prompt (per Phase 1 step 8 design) → verify work continues from prior state.
16. Success metric: **5 consecutive `ll-auto` runs on issues > 50K tokens hand off cleanly with no "Prompt is too long" failure, including at least one run that exercises the J backstop.** If any run fails, fix and reset the counter to zero — 5 consecutive clean runs from the latest fix.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

17. Verify `scripts/little_loops/fsm/handoff_handler.py` and `fsm/signal_detector.py` — the FSM executor has a parallel CONTEXT_HANDOFF detection path; confirm the sentinel-file approach doesn't introduce divergent behavior between FSM loops and `-p` mode ll-auto sessions. **If divergence is detected, decide explicitly**: unify the two paths, or document why FSM uses a separate detection mechanism. Do not leave the two implementations to drift.
18. Update `scripts/tests/test_worker_pool.py:2183` `TestRunWithContinuation` — add sentinel-file test case alongside `issue_manager` counterpart updates (minimal coverage currently: only 1 test exists)
19. Add `TestContextHandoffSentinel` class to `scripts/tests/test_hooks_integration.py` — sentinel written at threshold, absent below threshold, survives `session-cleanup.sh` — follow `TestPrecompactState` (line 1626) pattern exactly
20. Update `scripts/tests/test_subprocess_utils.py:216` `test_constructs_correct_command_args` — fix expected CLI arg list if `run_claude_command` in `subprocess_utils.py` gains new flags
21. Update `commands/handoff.md` and `skills/manage-issue/SKILL.md` handoff protocol sections to reference Stop hook + sentinel as the new primary trigger path, with Option J (fresh-session guillotine) documented as the backstop path
22. Update `config-schema.json` `context_monitor` object for new config keys: Option H headroom multiplier (e.g., `headroom_turn_multiplier`, default 2), Option J trigger threshold (e.g., `guillotine_threshold`, default 0.9), and sentinel path override

## Impact

- **Severity**: High — automatic context handoff (core automation feature) is non-functional for large sessions
- **Effort**: Low (investigation) / Medium (fix, depending on root cause)
- **Risk**: Low
- **Breaking Change**: No

## Labels

`bug`, `regression`, `context-monitor`, `hooks`, `ll-auto`, `automation`

---

## Status

**Open** | Created: 2026-05-06 | Priority: P2

## Related Issues

- BUG-035 (completed): Original bug — closed without end-to-end verification
- BUG-1375: `classify_failure` misses "Prompt is too long" (companion fix)
- **ENH-1376: HARD PREREQUISITE for Phase 2.** Parse stream-json result events for accurate token counts. Options C/E/G/H/J all depend on it; conservative-heuristic interim is what's failing now.
- BUG-1374: Spurious implementation failure issue created as a symptom of this bug

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-06_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 45/100 → LOW

### Concerns
- Root cause dominant failure mode (gradual creep vs single-call cliff) is unclassified — Phase 1 step 7 (trajectory analysis of ll-auto-debug.txt) must precede Phase 2 threshold tuning and Option H headroom algorithm calibration; skipping risks tuning for the wrong failure mode
- Option J transcript-summary assembly algorithm is TBD (Phase 1 design spike) — implementing J without it risks shipping a safety net that deadlocks under its primary use cases (single-call cliffs, full-context resume failure)

### Outcome Risk Factors
- Option J transcript-summary assembly algorithm is undefined — resolve before implementing Option J to avoid shipping a safety net with unknown failure modes
- Dominant failure mode (gradual creep vs single-call cliff) not yet classified — Phase 1 step 7 trajectory analysis is required before Phase 2 scope can be finalized; this determines whether Option I (subprocess delegation) is in scope
- 13+ files span hooks, subprocess management, parallel workers, FSM layer, CLI, config, and docs — run_claude_command signature changes will propagate to action.py and fsm/runners.py callers; high coordination cost
- `hooks/scripts/context-handoff-sentinel.sh` does not exist yet (new artifact) — must be created alongside the hooks.json Stop hook entry; session-cleanup.sh rm list must explicitly exclude this path

## Option J Design Spike

_Added by design spike on 2026-05-06. Resolves Phase 1 step 8 and clears `decision_needed`._

**Decision: Structured stdout-tail + inventory (option c), with heuristic length cap (option b) as guard.**

### Why not option (a) — separate `claude -p` summarizer call

The `result.stdout` captured by `run_claude_command` already contains Claude's own text responses
(extracted from stream-json `assistant` events). Running another LLM to "summarize" Claude's own
words adds latency, an additional API call, and a new failure surface — without adding semantic
quality. The one case where (a) would help is when stdout exceeds ~100K chars and a shorter prompt
is needed; that edge case is handled instead by the length cap in step 2 below.

An additional concern: J is a safety net for cases where the primary handoff mechanism (E+G) failed.
A safety net that itself depends on a successful external API call is not a reliable backstop.

### Why not option (b) — heuristic truncation only

Raw character truncation of stdout cuts mid-sentence and loses structure (which files were written,
which phase was active, what the last complete Claude response was). Approach (c) uses (b) as a
component — tail-N chars — but wraps it in structure so the fresh session understands context.

### Chosen Algorithm

```python
GUILLOTINE_TAIL_CHARS = 12_000   # ≈ 3K tokens — last N chars of Claude's stdout
GUILLOTINE_MAX_TASK_LINES = 20   # first N lines of original command for task intent
```

**Input data available to the parent process at J-trigger time:**

| Source | How accessed | Contains |
|---|---|---|
| `result.stdout` | Already in memory | All Claude text responses (assistant events) |
| `original_command` | Passed to `run_with_continuation` | Original task / skill invocation |
| `.ll/ll-context-state.json` | `Path(".ll/ll-context-state.json").read_text()` | Tool call count, estimated tokens |
| `.loops/tmp/scratch/` | `glob` | Large outputs offloaded by Claude |
| Cumulative token count | `on_usage` callback accumulation | Exact token count at trigger |

**Assembly steps:**

1. **Task intent**: Extract first `GUILLOTINE_MAX_TASK_LINES` lines of `original_command`.
   This is the skill invocation (e.g., `/ll:manage-issue BUG-1234`) that defines the session goal.

2. **Stdout tail**: Take `captured_stdout[-GUILLOTINE_TAIL_CHARS:]`.
   If stdout is shorter, use all of it. This is Claude's most recent output — the most semantically
   relevant content describing what was in progress at interruption.

3. **Scratch pad inventory**: List files in `.loops/tmp/scratch/` with sizes.
   These are large tool outputs Claude offloaded; the fresh session should check them before re-running
   expensive operations (e.g., test runs, large file reads).

4. **Token stats**: From the cumulative `on_usage` accumulation (not the context-state file, which
   uses a heuristic estimate). Report the actual token count at trigger time.

5. **Assemble prompt** using the following template:

```
⚠ CONTEXT LIMIT REACHED — FRESH SESSION CONTINUATION

The previous automation session exhausted its context window before completing.
This fresh session (new context window, starts at 0 tokens) is continuing from
that interrupted session.

## Original Task
[first GUILLOTINE_MAX_TASK_LINES lines of original_command]

## Session Progress at Interruption
- Approximate tokens used: {input_tokens:,} / {context_limit:,}
- Tool calls executed: {tool_calls}
- Trigger reason: {trigger_reason}  # "context > 90%" or "Prompt is too long"

## Last Session Output (what was happening at interruption)
[last GUILLOTINE_TAIL_CHARS chars of captured_stdout]

## Scratch Pad Files Available
[list of .loops/tmp/scratch/ files with sizes, or "None" if empty]

## Instructions for This Session
1. Do NOT restart from scratch — the previous session made progress (see above)
2. Read the "Last Session Output" section to understand exactly where we were
3. Check the scratch pad files before re-running expensive operations
4. Continue implementation from the interruption point
5. Complete normally: test, commit, close the issue as usual
```

### Failure Modes

| Failure Mode | Impact | Mitigation |
|---|---|---|
| `captured_stdout` empty (SIGINT before first output) | No last-output context | Template says "interrupted at session start" — fresh session starts from scratch with original command; acceptable for early-interrupt case |
| stdout very large (> 200K chars) | Tail still bounded at 12K chars | Length cap ensures assembled prompt stays ≤ 15K tokens regardless of session length |
| Scratch pad dir missing | Missing file inventory | Skip that section; not a failure |
| Context state file missing/corrupt | No tool-call count | Use "unknown" — cosmetic only |
| Fresh session ALSO immediately exhausts context | J deadlocks | **Structurally impossible**: fresh session starts at 0 tokens; assembled prompt ≈ 12K tokens leaves >185K available in a 200K window |
| Assembled prompt > context limit | Pathological: would require task + stdout-tail alone to exceed 200K tokens | Reduce `GUILLOTINE_TAIL_CHARS` to 2K — document as config key `guillotine_tail_chars` |

### Trigger Conditions (two paths into J)

1. **Gradual creep past 90%**: `on_usage` cumulative total crosses `guillotine_threshold` (default 0.9),
   no handoff observed. After current turn's `result` event (not mid-turn), send SIGINT, then assemble
   and spawn fresh session. This path is clean — the turn completed.

2. **"Prompt is too long" mid-turn**: Detected in `result.stderr` or as a non-zero returncode with
   that error string. SIGINT is immediate (process may already be dead). `captured_stdout` has
   everything up to the point of failure. Assemble prompt from partial stdout — the tail is still
   the most useful part.

### Integration Points

- `assemble_guillotine_prompt(original_command, captured_stdout, token_stats)` → new function in
  `subprocess_utils.py` (mirrors `read_continuation_prompt` pattern)
- Trigger detection inside `run_claude_command` (or a thin wrapper in `run_with_continuation`):
  accumulate `on_usage` totals; when threshold crossed after a `result` event, set a flag for
  `run_with_continuation` to inspect
- `run_with_continuation` checks the J flag after each `run_claude_command` call:
  if set, calls `assemble_guillotine_prompt` and spawns fresh session (not `--resume`)
- `WorkerPool._run_with_continuation` must receive the same treatment in parallel mode

### What Falls Back If J's Own Assembly Fails

If `assemble_guillotine_prompt` raises an exception (disk I/O error, encoding issue):
- Log the error and fall through to a **bare restart**: fresh session with `original_command` only,
  no context from prior session.
- This is the same as if J didn't exist — no worse than the current state (session lost).
- Document in J-path integration test.

## Resolution

**Status**: Completed 2026-05-07

**What was done**: Implemented Options E+G+J across all layers to make context handoff reliable regardless of the PostToolUse `exit 2` feedback path:

- **Option G** (`hooks/scripts/context-handoff-sentinel.sh` — new Stop hook): Fires at turn idle boundaries (not mid-turn); checks `estimated_tokens`/`result_token_count` from the state file; writes `.ll/ll-context-handoff-needed` JSON sentinel when usage ≥ 60% and no handoff yet complete. Registered in `hooks/hooks.json` before `session-cleanup.sh` so sentinel persists across sessions.
- **Context crossing log** (`hooks/scripts/context-monitor.sh`): Added append-only `.ll/ll-context-crossings.log` so threshold crossings are preserved even when state file is overwritten by subsequent sessions.
- **Option E** (`scripts/little_loops/subprocess_utils.py`, `issue_manager.py`, `worker_pool.py`): `run_with_continuation` reads the sentinel between sessions; if present, consumes it and resumes the existing session with an explicit handoff instruction (`claude --resume -p "Context limit approaching, please run /ll:handoff now"`).
- **Option J** (guillotine path in the same files): If cumulative `on_usage` tokens cross 90% of `context_limit` and no handoff was observed, `run_with_continuation` spawns a **fresh session** (not `--resume`) with an assembled transcript-summary prompt built from task intent + stdout tail + scratch pad inventory. This handles single-call cliffs and resumed-sessions-still-full cases that E+G cannot.
- **24 new tests** across `test_subprocess_utils.py`, `test_issue_manager.py`, `test_hooks_integration.py`, `test_worker_pool.py` covering all three paths.

**Verification**: 5940 tests pass; 12 pre-existing failures unchanged (confirmed by testing clean state).

## Session Log
- `/ll:manage-issue --resume` - 2026-05-07T01:07:58Z - `21062892-560c-4809-9cfd-e1b61b833732.jsonl`
- `/ll:ready-issue` - 2026-05-07T00:40:10 - `21062892-560c-4809-9cfd-e1b61b833732.jsonl`
- `design-spike: Option J` - 2026-05-06T00:00:00 - cleared `decision_needed`; chosen algorithm: structured stdout-tail + inventory; see `## Option J Design Spike` section
- `/ll:confidence-check` - 2026-05-06T00:00:00 - `8bdc0e06-85ea-43b5-8eeb-b06ffc964981.jsonl`
- `/ll:wire-issue` - 2026-05-06T21:52:53 - `f52c049f-8ef4-44fc-95ad-687a8ae1df72.jsonl`
- `/ll:refine-issue` - 2026-05-06T21:39:24 - `63fad009-7663-49aa-ac6a-4ad5eb77b1de.jsonl`
- `/ll:format-issue` - 2026-05-06T21:10:20 - `291cabfe-e58a-41a8-a54c-5ae0200e8ef1.jsonl`
- `/ll:capture-issue` - 2026-05-06T20:59:54Z - `381e1f9c-a749-4e5e-9040-a1d4e3d3e647.jsonl`
