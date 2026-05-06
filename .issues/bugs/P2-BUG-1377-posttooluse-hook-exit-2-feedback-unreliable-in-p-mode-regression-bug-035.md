---
id: BUG-1377
type: BUG
priority: P2
status: open
captured_at: 2026-05-06T20:59:54Z
discovered_date: 2026-05-06
discovered_by: capture-issue
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

### Option G: Stop-hook + parent resume ⭐ PREFERRED (combine with E)
Use the `Stop` hook (fires when Claude finishes a turn — Claude is idle, no pending tool-use) instead of PostToolUse. Stop-hook checks the threshold and writes a sentinel file. `run_with_continuation` reads the sentinel between sessions and decides whether to resume with an explicit handoff instruction.

- Avoids the "feedback turn doesn't fit in remaining context" failure entirely — the decision is made *between* sessions, not inside one
- No mid-turn injection, no risk that the feedback message itself overflows
- PostToolUse remains as a coarse early-warning (logging only), Stop as the trigger
- Cleaner control flow than E alone: parent-side decision, parent-side resume

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

### Option J: Parent-side guillotine (explicit backstop)
If ENH-1376 reports context > 90% and Claude has not called `/ll:handoff`, parent SIGINTs after the current turn and starts a fresh `--resume` session with an assembled "previous session ran out of context, here's where we were" prompt built from the transcript. This is Option C reframed: not the primary mechanism, but the *backstop* that guarantees no silent work loss when E/G fail.

- Guarantees the deadlock case (sub-cause #5, gap #5) is recoverable
- Last-resort only — accepts that the in-flight turn may be partially lost

Option A should be done first to establish whether Option B or C is needed.

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — add append-only crossing log (Phase 1); optionally lower threshold (Option D)
- `hooks/hooks.json` — register a new Stop hook for sentinel-write (Option G)
- `hooks/scripts/` — new Stop-hook script that checks threshold and writes `.ll/ll-context-handoff-needed` sentinel
- `scripts/little_loops/issue_manager.py` — extend `run_claude_command()` to parse stream-json `result` events for accurate token counts (depends on ENH-1376); add Option J backstop (SIGINT + resume with assembled prompt)
- `scripts/little_loops/issue_manager.py` — `run_with_continuation()` reads sentinel and prepends explicit handoff instruction to next resume (Option E + G)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:35` — `detect_context_handoff()` — checks only `result.stdout` (Claude's text output); hook stderr is captured into `result.stderr` only and never reaches this check
- `scripts/little_loops/subprocess_utils.py:47` — `read_continuation_prompt()` — reads `.ll/ll-continue-prompt.md`; the new sentinel read in `run_with_continuation()` should mirror this pattern
- `scripts/little_loops/issue_manager.py:597,605` — `run_with_continuation()` called inside `manage_issue()` for the Phase 2 implement step
- `scripts/little_loops/parallel/worker_pool.py:391,683` — `WorkerPool._run_with_continuation()` — parallel-mode counterpart at `:683`; must be updated alongside `issue_manager.py` (the two are structural copies)
- `hooks/hooks.json:88-98` — existing Stop hook entry (`session-cleanup.sh`, timeout 15s); a second Stop hook entry pointing to new `context-handoff-sentinel.sh` is needed
- `hooks/scripts/session-cleanup.sh:14` — deletes `.ll/ll-context-state.json` on Stop; sentinel file `.ll/ll-context-handoff-needed` must NOT appear in this `rm -f` list — it must persist across sessions until consumed by `run_with_continuation()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py:61,84` — imports and calls `run_claude_command` directly; if the function signature gains new parameters (Option J backstop), this caller must be updated [Agent 1]
- `scripts/little_loops/fsm/runners.py:20` — `DefaultActionRunner` imports `run_claude_command`; same signature-change risk as `action.py` [Agent 1]
- `scripts/little_loops/fsm/handoff_handler.py` — `HandoffHandler` class handles `CONTEXT_HANDOFF` signals in FSM-loop sessions; verify sentinel-file approach doesn't conflict with this parallel detection system [Agent 2]
- `scripts/little_loops/fsm/signal_detector.py:74` — defines `HANDOFF_SIGNAL` constant; check for sentinel-file detection parity in the FSM executor path [Agent 2]

### Similar Patterns
- `run_with_continuation()` in `issue_manager.py:149` — existing resume logic; extend for sentinel-file detection
- `hooks/scripts/precompact-state.sh` — closest codebase analog to Option G: a hook that writes a sentinel file (`.ll/ll-precompact-state.json`) using `atomic_write_json` + `acquire_lock` from `lib/common.sh`, which the Python/bash layer reads later; follow this exact write pattern for `context-handoff-sentinel.sh`
- `subprocess_utils.py:47` — `read_continuation_prompt()` — plain `Path.exists()` + `path.read_text()` (no locking, no JSON); the sentinel-read in `run_with_continuation()` can be equally simple (just `Path(".ll/ll-context-handoff-needed").exists()`)

### Tests
- `scripts/tests/test_issue_manager.py:941` — `TestContextHandoff` class — existing tests for `run_with_continuation()` handoff detection; extend with test for sentinel-file path (hook writes file → `run_with_continuation()` detects it → continuation spawned with explicit instruction)
- `scripts/tests/test_subprocess_utils.py` — `TestDetectContextHandoff` and `TestReadContinuationPrompt` classes — unit tests for detection helpers; no sentinel-file test exists yet
- `scripts/tests/test_hooks_integration.py` — existing hook execution integration tests
- New: end-to-end test — Stop hook writes `.ll/ll-context-handoff-needed` → `run_with_continuation()` reads and consumes it → continuation session spawned with explicit `"Context limit approaching, please run /ll:handoff"` instruction

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py:2183` — `TestRunWithContinuation` has only 1 test (no happy-path continuation or sentinel case); **add sentinel-file test** mirroring the `issue_manager` counterpart; patches must target `little_loops.parallel.worker_pool.*` [Agent 3]
- `scripts/tests/test_issue_manager.py:940` — actual class name is `TestRunWithContinuation` (not `TestContextHandoff`): **add sentinel-triggered continuation test**; ensure `test_returns_immediately_when_no_handoff` has sentinel-absent setup so the new check doesn't inadvertently trigger [Agent 3]
- `scripts/tests/test_hooks_integration.py` — **new `TestContextHandoffSentinel` class**: Stop hook writes sentinel at threshold; sentinel absent below threshold; sentinel survives `session-cleanup.sh` run — follow `TestPrecompactState` pattern (line 1626) exactly (chdir + subprocess.run + file assertion) [Agent 3]
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
- **`detect_context_handoff()` checks only `result.stdout`** (`subprocess_utils.py:35`): the stream-json parser (`run_claude_command`) extracts only `type == "assistant"` text events into stdout. Hook stderr lands in `result.stderr` only. `CONTEXT_HANDOFF` must appear in Claude's TEXT response, not in stderr — the whole chain requires Claude to voluntarily emit the signal after receiving the hook feedback.
- **No Stop hook currently fires for context monitoring**: `hooks/hooks.json:88` only runs `session-cleanup.sh` on Stop. A second Stop-hook entry (new script `context-handoff-sentinel.sh`) is the primary addition for Option G.
- **`session-cleanup.sh:14` deletes `ll-context-state.json`** on every session Stop — so any threshold-crossing evidence in that file is lost. The sentinel file (`.ll/ll-context-handoff-needed`) must be a distinct path not in the cleanup `rm -f` list.
- **`WorkerPool._run_with_continuation()` at `parallel/worker_pool.py:683`** is structurally identical to `issue_manager.run_with_continuation()` — both must be updated in tandem.

## Implementation Steps

**Phase 1 — Instrumentation (do first, no behavior changes):**
1. Add an append-only crossing log in `context-monitor.sh` (e.g., `.ll/ll-context-crossings.log`) so future runs preserve threshold-crossing evidence even when state is overwritten.
2. Confirm whether Claude Code's auto-compact runs in `-p --dangerously-skip-permissions`. Document the answer; if it does, evaluate whether it already addresses some failure modes.
3. Calibrate `context-monitor.sh`'s token estimate against ENH-1376 ground truth on a representative session. Record observed error margin.
4. Parse the failing `ll-auto-debug.txt` to plot token trajectory per tool call. Determine: gradual creep, single-call cliff, or output-side growth. This drives which option(s) actually apply.

**Phase 2 — Primary mechanism (Stop-hook + external resume, Options G + E combined):**
5. Add a Stop hook that checks token usage at turn boundaries and writes a sentinel file when threshold crossed. PostToolUse retains a coarse early-warning role (log only).
6. Extend `run_with_continuation` in `issue_manager.py` to read the sentinel between sessions and, if set, send an explicit `claude -p --resume <session-id> "Context limit approaching, please run /ll:handoff now."` before continuing.
7. Implement ENH-1376 stream-json `result` event parsing for accurate token counts (or use a conservative heuristic in the interim).

**Phase 3 — Backstop (Option J):**
8. In `run_claude_command`, if ENH-1376 reports context > 90% and no handoff has been observed, SIGINT after current turn and resume with an assembled context-summary prompt built from the transcript. Guarantees no silent work loss in the deadlock case.

**Phase 4 — Source mitigations (optional, if Phase 1 trajectory shows cliff/output growth dominates):**
9. **Option H** if cliffs/output growth dominate: replace fixed threshold with dynamic `limit − 2 × max_recent_turn_size`.
10. **Option I** if single tool-call cliffs from heavy reads dominate: delegate large file/log scans to subprocess summarizers.

**Phase 5 — Verification:**
11. Add end-to-end integration test: simulate threshold crossing → verify sentinel written → verify continuation session spawned with handoff instruction → verify `CONTEXT_HANDOFF` produced.
12. Define success metric and re-run: *N consecutive ll-auto runs on issues > 50K tokens hand off cleanly with no "Prompt is too long" failure.*

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

13. Verify `scripts/little_loops/fsm/handoff_handler.py` and `fsm/signal_detector.py` — the FSM executor has a parallel CONTEXT_HANDOFF detection path; confirm the sentinel-file approach doesn't introduce divergent behavior between FSM loops and `-p` mode ll-auto sessions
14. Update `scripts/tests/test_worker_pool.py:2183` `TestRunWithContinuation` — add sentinel-file test case alongside `issue_manager` counterpart updates (minimal coverage currently: only 1 test exists)
15. Add `TestContextHandoffSentinel` class to `scripts/tests/test_hooks_integration.py` — sentinel written at threshold, absent below threshold, survives `session-cleanup.sh` — follow `TestPrecompactState` (line 1626) pattern exactly
16. Update `scripts/tests/test_subprocess_utils.py:216` `test_constructs_correct_command_args` — fix expected CLI arg list if `run_claude_command` in `subprocess_utils.py` gains new flags
17. Update `commands/handoff.md` and `skills/manage-issue/SKILL.md` handoff protocol sections to reference Stop hook + sentinel as the new primary trigger path
18. Update `config-schema.json` `context_monitor` object if new config keys are introduced (Option D threshold relaxation or sentinel path override)

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
- ENH-1376: Parse stream-json result events for accurate token counts (Option C enabler)
- BUG-1374: Spurious implementation failure issue created as a symptom of this bug

## Session Log
- `/ll:wire-issue` - 2026-05-06T21:52:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f52c049f-8ef4-44fc-95ad-687a8ae1df72.jsonl`
- `/ll:refine-issue` - 2026-05-06T21:39:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/63fad009-7663-49aa-ac6a-4ad5eb77b1de.jsonl`
- `/ll:format-issue` - 2026-05-06T21:10:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/291cabfe-e58a-41a8-a54c-5ae0200e8ef1.jsonl`
- `/ll:capture-issue` - 2026-05-06T20:59:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/381e1f9c-a749-4e5e-9040-a1d4e3d3e647.jsonl`
