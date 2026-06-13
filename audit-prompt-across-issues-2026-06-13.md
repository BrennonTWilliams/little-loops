# Loop Audit: `prompt-across-issues`

**Run**: `2026-06-13T140549`  
**Audit date**: 2026-06-13  
**Invocation**: `ll-loop run prompt-across-issues "/ll:format-issue {issue_id}"`  

---

## Goal-vs-Outcome Scorecard

**Goal**: "Run an arbitrary prompt against every open/active issue, one at a time. No quality gates — use harness-multi-item if you need evaluation phases."

**Contract**: None detected — the loop explicitly disclaims quality gates in its description. Success is defined implicitly as "process all items in the pending list until exhaustion."

**Artifacts checked**:

| Artifact | Status |
|----------|--------|
| `.loops/tmp/prompt-across-issues-pending.txt` | Temp file — created, consumed, empty at termination |
| `.issues/*.md` (17 target files) | 5 fully formatted, 12 analyzed-only (interactive questions unanswered) |
| `.ll/lloops-parity.json` | Pre-existing modification, not loop-caused |

**Phase 1 signals**: None — zero action failures, zero evaluate failures, zero retries, zero throttle events. All 36 evaluate verdicts were `yes` except the final `discover → done` route (exit_code 1 on empty pending file, which is the intended termination signal).

**Shallow-iteration check**: `warning` (70 tool calls, 0 auxiliary mutations outside primary artifact paths). The loop burned 70 iterations across 17 issues (~4.1 shell actions per issue) without producing any helper/intermediate artifacts. While the primary artifacts (`.issues/` files) were mutated, only 5 of 17 prompt actions produced write-side-effects; the other 12 were read-analysis-only.

**Verdict**: **`partial`**

**Rationale**: The loop reached its terminal state cleanly and processed all 17 issues in the pending list. However, only 5 of 17 issues (~29%) were actually formatted — the other 12 received gap analysis but no changes were applied because `/ll:format-issue` is an interactive skill that asks the user questions (e.g., "Which gaps would you like to address?", "Which approach would you prefer?"). The loop's `execute` state has no evaluation step — it uses `next: "advance"` unconditionally, so it cannot distinguish between "prompt completed successfully with changes" and "prompt analyzed but couldn't apply changes without user input." This is a structural defect: the loop treats all `exit_code: 0` prompt completions as equivalent, but `/ll:format-issue` exits 0 even when it only performs analysis and waits for interactive input.

---

## Run Statistics

| Metric | Value |
|--------|-------|
| Duration | 35 min 33 sec (2,132,654 ms accumulated) |
| Iterations | 70 |
| Issues processed | 17 |
| Issues formatted | 5 (29%) |
| Issues analyzed-only | 12 (71%) |
| Prompt action exits (all code 0) | 17 |
| Shell action exits (all code 0 except final) | 53 |
| Evaluate events (all `yes` except final `no`) | 36 |
| Retry events | 0 |
| Error events | 0 |
| Avg prompt action duration | ~104 sec |
| Total tokens consumed | ~1.1M input, ~93K output, ~4.7M cache read |

---

## Issues Processed — Detail

| # | Issue ID | Formatted? | Notes |
|---|----------|------------|-------|
| 1 | ENH-1736 | ✅ Yes | Autonomous — all gaps high-confidence |
| 2 | ENH-1737 | ❌ No | HIGH confidence gaps but only analysis produced |
| 3 | ENH-1738 | ❌ No | Asked interactive questions — unanswered |
| 4 | ENH-1740 | ❌ No | Asked interactive questions — unanswered |
| 5 | ENH-1743 | ❌ No | Asked interactive questions — unanswered |
| 6 | ENH-1744 | ❌ No | Analysis only, no changes applied |
| 7 | ENH-1748 | ❌ No | Asked interactive questions — unanswered |
| 8 | ENH-1749 | ❌ No | Asked interactive questions — unanswered |
| 9 | ENH-1752 | ❌ No | Asked interactive questions — unanswered |
| 10 | FEAT-1739 | ❌ No | Asked interactive questions — unanswered |
| 11 | FEAT-1741 | ✅ Yes | 7 gaps filled autonomously |
| 12 | FEAT-1742 | ✅ Yes | 8 gaps resolved autonomously |
| 13 | FEAT-1745 | ❌ No | Asked "Which approach would you prefer?" — unanswered |
| 14 | FEAT-1746 | ✅ Yes | 8 sections added |
| 15 | FEAT-1747 | ❌ No | Asked for Impact + Acceptance Criteria input — unanswered |
| 16 | FEAT-1750 | ✅ Yes | ISSUE FORMATTED — all gaps resolved |
| 17 | FEAT-1751 | ❌ No | Asked for Use Case + Impact input — unanswered |

---

## Root Cause: Why `ll-issues rs` Shows Unformatted Issues

The `/ll:format-issue` skill has two execution modes:

1. **Autonomous mode**: When all gaps can be resolved with high confidence from existing content, it applies changes directly and reports "ISSUE FORMATTED."
2. **Interactive mode**: When gaps require user judgment (Impact priority, Acceptance Criteria specifics, etc.), it presents `AskUserQuestion` prompts and waits for answers.

When invoked non-interactively via the `prompt-across-issues` loop, mode 2 stalls — the skill asks questions that nobody answers. The loop then unconditionally advances to the next issue (`next: "advance"`), treating the analysis as "done."

The 12 unformatted issues all hit mode 2. Their output previews show variations of:
- *"Please select which gaps you'd like to address"*
- *"Which approach would you prefer? A) Let me resolve everything... B) Address the 3 judgment items..."*
- *"I've presented two questions — one for Use Case and one for Impact"*

### Structural Defect in the FSM

The `execute` state has no post-action evaluation:

```yaml
# Current (defect):
execute:
  action: "${captured.final_prompt.output}"
  action_type: "prompt"
  next: "advance"            # ← unconditional — can't detect partial success
  max_retries: 3
  on_retry_exhausted: "advance"
```

Because `next: "advance"` is unconditional, the loop cannot distinguish between:
- A prompt that applied concrete file mutations (formatting completed)
- A prompt that only performed analysis and is waiting for interactive input

Both produce `exit_code: 0`, and the loop treats them identically.

---

## Rubric-vs-Description Audit

**Skipped** — no `llm_structured` evaluators exist in this FSM. All evaluators use `exit_code` type. 0 evaluators checked, 0 flagged.

---

## Sub-Loop Verdict Laundering Check

**No sub-loop states** — no `loop:` keys in any state. 0 checked, 0 flagged.

---

## Existing Issues (Deduplication)

Existing issues referencing `prompt-across-issues`:

| Issue | Relevance |
|-------|-----------|
| BUG-617 | Template error with unescaped variable — different defect class |
| BUG-1675 | Bash variable interpolation conflict — different defect class |
| BUG-671 | Double-dollar shell escape — different defect class |
| ENH-629 | Stale counter clearing — different concern |
| ENH-761 | Plan-contract degenerate gate — related (evaluator gap) but different scope |
| FEAT-004, FEAT-033, FEAT-097 | Feature requests, not bug reports |

**All three proposals below are NEW** — no existing issue covers the fire-and-forget prompt defect.

---

## Improvement Proposals

### 1. [structural] Add post-execute evaluation to detect interactive-stall

**Rationale**: The `execute` state unconditionally routes to `advance` with no quality check. A post-execute evaluator should detect when the prompt only analyzed without applying changes.

**Severity**: High — causes silent partial completion (29% success rate in observed run)

**YAML diff**:

```yaml
# Current (defect):
execute:
  action: "${captured.final_prompt.output}"
  action_type: "prompt"
  next: "advance"
  max_retries: 3
  on_retry_exhausted: "advance"

# Proposed fix:
execute:
  action: "${captured.final_prompt.output}"
  action_type: "prompt"
  evaluate:
    type: "llm_structured"
    prompt: >
      Did the prompt action apply concrete changes (write/edit file mutations)?
      Answer YES if the output indicates sections were added, files were written,
      or formatting was applied. Answer NO if the output is only analysis/gap-identification
      or ends with interactive questions waiting for user input.
    schema:
      type: object
      properties:
        changes_applied:
          type: boolean
          description: Whether concrete file mutations occurred
    on_yes: "advance"
    on_no: "log_skip"
  max_retries: 3
  on_retry_exhausted: "advance"
```

---

### 2. [contract] Add a skip-tracking state for transparency

**Rationale**: When the evaluator determines no changes were applied, route to a `log_skip` state that records the issue ID and reason before advancing. This gives operators a post-run summary of which issues were skipped and why.

**Severity**: Medium — operators currently have no visibility into which issues were silently skipped

**YAML diff**:

```yaml
# New state to add after execute:
log_skip:
  action: >
    echo "SKIPPED: ${captured.current_item.output} — prompt completed without file mutations"
    echo "${captured.current_item.output}" >> .loops/tmp/prompt-across-issues-skipped.txt
  action_type: "shell"
  next: "advance"
```

---

### 3. [state] Document the interactive-mode limitation in the loop description

**Rationale**: The current description says "No quality gates" but doesn't warn operators that interactive skills will stall when run non-interactively. Adding this caveat prevents misuse.

**Severity**: Low — documentation-only; operators can work around by choosing non-interactive skills

**YAML diff**:

```yaml
description: >
  Run an arbitrary prompt against every open/active issue, one at a time.
  Pass the prompt via the input parameter; use {issue_id} as a placeholder
  to inject each issue's ID. Issues are processed in priority order using a
  temp-file pending list to avoid infinite loops. No quality gates — use
  harness-multi-item if you need evaluation phases.
  Optionally constrain the sweep to a single issue type with --context type=<TYPE>
  (one of BUG, FEAT, ENH, EPIC). When omitted, all open issues are processed.
  Optionally scope the sweep to children of an epic with --context parent=EPIC-NNN.
  Both filters may be combined: --context type=ENH --context parent=EPIC-1773.

  WARNING: Skills that use AskUserQuestion (interactive mode) will analyze but
  not apply changes when run non-interactively. Prefer skills with --auto or
  --batch flags, or use harness-multi-item for evaluation-gated multi-pass
  workflows.

  Usage:
    ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}"
    ll-loop run prompt-across-issues "/ll:normalize-issues {issue_id} --quick"
    ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}" --context type=BUG
    ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}" --context parent=EPIC-1773
```

---

## Final Report

```
Assessment complete for loop: prompt-across-issues

Verdict: partial
Rubric audit: skipped (no llm_structured evaluators)
Laundering check: no sub-loop states
Shallow-iteration check: warning (70 tool calls, 0 auxiliary mutations)
Issues created: 0 (written to audit file instead)

Root cause: /ll:format-issue is interactive; 12/17 issues hit AskUserQuestion
prompts that were never answered. The execute state's unconditional next: advance
prevents the loop from detecting this failure mode.

Key metric: 29% formatting success rate (5/17). The other 12 issues received
gap analysis only — the skill asked questions the loop couldn't answer.
```
