---
id: FEAT-1933
title: Create rn-implement recursive plan-and-implement FSM loop
type: FEAT
priority: P2
status: open
captured_at: '2026-06-04T05:36:57Z'
discovered_date: 2026-06-04
discovered_by: capture-issue
labels:
- loops
- fsm
- orchestration
- recursion
- planning
decision_needed: true
confidence_score: 98
outcome_confidence: 76
score_complexity: 16
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 20
---

# FEAT-1933: Create rn-implement recursive plan-and-implement FSM loop

## Summary

Create a new built-in FSM loop (`loops/rn-implement.yaml`) that combines the best patterns
from `recursive-refine` (depth tracking, cycle detection, decomposition trees), `rn-refine`
(iterative deepening, dimensional analysis, convergence detection), and `autodev` (interleaved
implementation, inflight tracking, run isolation) into a single n-depth recursive
planning-and-implementation FSM.

The loop addresses four gaps in the existing `autodev` loop:

1. **No iterative deepening** — single-pass refine→wire→confidence-check, decomposition as the only fallback
2. **No dimensional reactivity** — confidence-check produces per-dimension scores (`score_complexity`,
   `score_ambiguity`, `score_test_coverage`, `score_change_surface`, all 0–25) but only binary flags
   (`decision_needed`, `missing_artifacts`) are read
3. **No multi-pass wire↔refine feedback** — wire runs once, no loop where wiring reveals gaps needing refinement
4. **Decision may never get resolved** — edge cases where `decision_needed` surfaces but routing misses it,
   or decide runs but the issue isn't re-refined with the selected option

## Current Behavior

The `autodev` loop is structurally recursive (decomposes issues into children, re-queues depth-first)
but operationally linear — each issue gets exactly one pass through `format → refine → wire → confidence-check`
(via delegation to the `refine-to-ready-issue` sub-loop at `autodev.yaml:104-105`), with decomposition
as the only fallback when thresholds aren't met. The dimensional scores from confidence-check are
unused for routing decisions.

## Expected Behavior

A 31-state FSM loop (26 active + 2 terminal + 1 diagnostic + 2 convergence routers; includes 6 router states for multi-way token dispatch) with:

- **Iterative deepening**: `diagnose → remediate → re_assess → check_convergence` loop that re-enters
  the remediation cycle until PASS, budget exhaustion, or STALLED
- **Dimensional diagnosis**: Token-based routing (IMPLEMENT/DECIDE/WIRE/REFINE/DECOMPOSE) driven by
  all five dimensional scores from `ll-issues show --json`: `confidence_score`, `outcome_confidence`,
  `score_complexity`, `score_ambiguity`, and `score_change_surface`
- **Multi-pass wire↔refine**: Wire always chains into refine, which chains into re_assess, creating
  a closed feedback loop
- **Convergence check**: PASS/IMPROVED/STALLED routing with remediation budget gating, using a custom
  shell script (not the existing `convergence_gate` fragment from `lib/common.yaml`, which is designed
  for single-dimension numeric convergence, not multi-dimensional score comparison)
- **Depth-bounded recursion**: `max_depth` cap (default 3), depth-first child enqueuing, cycle detection
  via a visited-set file mechanism (borrowed from `recursive-refine.yaml`'s `recursive-refine-visited.txt` pattern)
- **Run isolation**: All temp files under `${context.run_dir}/` (MR-3 compliant)
- **Non-LLM gates**: `check_convergence` and `check_remediation_budget` use shell/output_numeric evaluators
  paired with LLM semantic checks (MR-1 compliant)
- **Rate-limit resilience**: All LLM-calling states (slash_command and prompt action types) wrapped with
  `with_rate_limit_handling` fragment, with `on_rate_limit_exhausted: dequeue_next` to gracefully skip
  the current issue

## Motivation

Single-pass refinement often leaves issues under-specified, and the existing confidence-check
dimensional scores are underutilized — the autodev loop reads only `decision_needed` and
`missing_artifacts` binary flags as proxies. By combining proven patterns from three existing
loops, `rn-implement` provides a measurable quality improvement over `autodev` for complex
issues that need multiple refinement passes, and gives the FSM access to the full dimensional
signal that confidence-check already produces.

This loop also serves as a reference architecture for meta-loops that need iterative deepening
with dimensional routing — a pattern that can be extracted into shared fragments later
(EPIC-1773 scope).

## Proposed Solution

### Design Decision: Sub-loop Delegation vs. Inline States

`autodev` delegates `format → refine → wire → confidence-check` to the `refine-to-ready-issue`
sub-loop via `loop: refine-to-ready-issue` with `context_passthrough: true` (`autodev.yaml:104-105`).
This sub-loop handles the single-pass linear chain and uses a `refine-broke-down → autodev-broke-down`
handshake flag pattern (`autodev.yaml:126-139`) to communicate decomposition signals back to the
outer loop.

**Decision for rn-implement**: Inline the refine/wire/confidence logic directly into the rn-implement
FSM rather than delegating to `refine-to-ready-issue`. Rationale:

1. Iterative deepening requires re-entering the remediation cycle with fresh scores, which the
   sub-loop's linear single-pass design doesn't support
2. Inlining gives the FSM direct control over the `diagnose → remediate → re_assess` loop,
   avoiding the handshake complexity that autodev needs for its outer↔inner communication
3. The sub-loop's `format` step is unnecessary — issues entering rn-implement are already
   formatted by upstream tooling (capture-issue, refine-issue)
4. Each state action (refine, wire, decide, confidence-check) becomes a direct state in the
   FSM, making routing explicit and testable

### Pattern Source: rn-refine's Iterative Deepening (Dimensions Are Different)

rn-refine's 9-dimension rubric (breadth, depth, complexity, clarity, consistency, logic_strategy,
feasibility, testability, risk_mitigation) scores **plan document quality** on a LOW→VERY-HIGH scale.
These are unrelated to issue readiness (confidence_score, outcome_confidence, score_complexity, etc.).

What IS reusable from rn-refine:
- **The convergence check pattern**: Compare pre-iteration and post-iteration scores, classify delta
  as PASS/IMPROVED/STALLED
- **The remediation budget gating**: Cap iterations at a configurable maximum, route to fallback
  (decomposition) when exhausted
- **The dimensional routing concept**: Map scores to actions, though the dimensions themselves are
  completely different

This plan borrows the **pattern** (iterative score comparison + convergence gating + budget cap)
while using **issue-readiness dimensions** from confidence-check for the actual scoring.

### Configuration: Threshold Defaults (Resolved)

The config-schema.json defines:
- `commands.confidence_gate.readiness_threshold`: default **85** (`config-schema.json:420`)
- `commands.confidence_gate.outcome_threshold`: default **70** (`config-schema.json:427`)
- `commands.recursive_refine.max_depth`: default **3** (`config-schema.json:482-486`)

However, both `autodev.yaml:25` and `recursive-refine.yaml:26` override `outcome_threshold` to **75**
in their loop-local context. rn-implement will match this convention: override `outcome_threshold` to
**75** in the loop-level context block, document the schema default (70) vs. loop default (75), and
read both thresholds from `ll-config.json` at startup with the loop-context values as fallbacks.

### Budget Interaction: max_remediation_passes vs. max_refine_count

Two separate budgets govern refinement:
1. `max_refine_count` (default 5, from `commands/refine-issue.md:473`): Limits the number of
   `--full-rewrite` passes that `/ll:refine-issue` performs internally
2. `max_remediation_passes` (default 3, loop parameter): Limits how many times the outer
   `diagnose → remediate → re_assess → check_convergence` loop iterates

These are **independent and multiplicative**: a single remediation pass that invokes refine with
`--full-rewrite` can consume up to `max_refine_count` internal rewrites within that one pass.
Total possible refine calls = `max_remediation_passes × max_refine_count`.

The plan sets `max_remediation_passes: 3` in the loop's context block. This is intentionally
lower than `max_refine_count` because each remediation pass should be a targeted response to
dimensional diagnosis, not a brute-force rewrite loop.

### State Machine: All 31 States Enumerated

The 31 states, numbered with their roles:

**Active workflow states (26):**

| # | State | Role |
|---|-------|------|
| 1 | `init` | Parse input, seed queue, set visited-set file path, initialize depth counter, load config thresholds |
| 2 | `dequeue_next` | Pop next issue from queue; if empty → `done`; if max depth exceeded → `mark_depth_capped` |
| 3 | `assess` | Run `/ll:confidence-check <id> --auto`, write pre-scores to `${context.run_dir}/pre_scores_<id>.json` |
| 4 | `verify_scores_persisted` | Shell: parse issue frontmatter, confirm `confidence_score` and `outcome_confidence` fields exist; retry assess once on failure |
| 5 | `check_readiness` | Shell: `ll-issues check-readiness <id>` (exit-code evaluator); readiness ≥ threshold AND outcome ≥ threshold → `implement` |
| 6 | `check_outcome` | Shell: inline jq reads `outcome_confidence` from frontmatter, compares to `outcome_threshold` (note: no `--outcome-only` flag exists on `check-readiness` — `check_readiness.py:14-53` only takes `--readiness`/`--outcome` threshold overrides); outcome passes but readiness fails → `diagnose` |
| 7 | `check_decision_needed` | Shell: `ll-issues check-flag <id> decision_needed`; → `decide` if true, else → `diagnose` |
| 8 | `diagnose` | **Dimensional routing core**: Shell script reads `ll-issues show <id> --json`, extracts 5 scores, applies routing matrix, outputs token, captures as `diagnosis` |
| 8a | `route_d_implement` | Router: `output_contains` with `source: "${captured.diagnosis.output}"`, `pattern: "IMPLEMENT"` → `implement`; on_no → `route_d_decide` |
| 8b | `route_d_decide` | Router: `output_contains`, `pattern: "DECIDE"` → `decide`; on_no → `route_d_wire` |
| 8c | `route_d_wire` | Router: `output_contains`, `pattern: "WIRE"` → `wire`; on_no → `route_d_refine` |
| 8d | `route_d_refine` | Router: `output_contains`, `pattern: "REFINE"` → `refine`; on_no → `snap_for_size_review` (DECOMPOSE fallthrough) |
| 9 | `implement` | Run `/ll:manage-issue <id> --auto` (or `ll-auto --only <id>`), then → `dequeue_next` |
| 10 | `decide` | Run `/ll:decide-issue <id> --auto`, mark decision_applied, → `re_assess` (not implement — must re-check) |
| 11 | `wire` | Run `/ll:wire-issue <id> --auto`, → `refine` (always chain: wiring may reveal gaps) |
| 12 | `refine` | Run `/ll:refine-issue <id> --auto --full-rewrite`, increment refine counter, → `re_assess` |
| 13 | `re_assess` | Run `/ll:confidence-check <id> --auto`, write post-scores to `${context.run_dir}/post_scores_<id>.json`, → `verify_re_assess_scores` |
| 14 | `verify_re_assess_scores` | Shell: confirm post-scores persisted; retry re_assess once on failure; → `check_convergence` |
| 15 | `check_convergence` | Shell: diff pre/post scores, increment remediation counter, output CONVERGED_PASS/CONVERGED_IMPROVED/CONVERGED_STALLED, capture as `convergence_result` |
| 15a | `route_conv_pass` | Router: `output_contains` with `source: "${captured.convergence_result.output}"`, `pattern: "CONVERGED_PASS"` → `implement`; on_no → `route_conv_improved` |
| 15b | `route_conv_improved` | Router: `output_contains`, `pattern: "CONVERGED_IMPROVED"` → `check_remediation_budget`; on_no → `snap_for_size_review` (STALLED fallthrough) |
| 16 | `check_remediation_budget` | Shell: compare remediation counter to `max_remediation_passes` (non-LLM output_numeric evaluator) |
| 17 | `snap_for_size_review` | Shell: capture current issue state (scores + artifacts) to `${context.run_dir}/size_review_snap_<id>.json` |
| 18 | `run_size_review` | Run `/ll:issue-size-review <id> --auto`, → `detect_children` |
| 19 | `detect_children` | Shell: diff `ll-issues list --json` before/after to find new child issue IDs, write to `${context.run_dir}/children_<id>.txt` |
| 20 | `enqueue_children` | For each child: set `parent_id: <id>`, depth = parent_depth + 1, add to queue (depth-first: push front), → `dequeue_next` |
| 21 | `skip_issue` | Log skip reason (no children from detect_children), → `dequeue_next` |
| 22 | `mark_depth_capped` | Log depth-capped issue to `${context.run_dir}/depth_capped.txt`, → `dequeue_next` |

**Terminal states (2):**

| # | State | Role |
|---|-------|------|
| 23 | `done` | All issues processed; write summary to `${context.run_dir}/summary.json` |
| 24 | `failed` | Initialization or unrecoverable error; write error details to `${context.run_dir}/error.json` |

**Diagnostic state (1):**

| # | State | Role |
|---|-------|------|
| 25 | `rate_limit_diagnostic` | Log rate-limit event to `${context.run_dir}/rate_limits.txt`, → `dequeue_next` (skip current issue) |

### Routing Diagram (Full)

```
init
  → [input valid] dequeue_next
  → [no input / parse error] failed

dequeue_next
  → [queue not empty, depth ≤ max] assess
  → [queue empty] done
  → [depth > max_depth] mark_depth_capped → dequeue_next

assess → verify_scores_persisted
  → [scores persisted] check_readiness
  → [scores missing after retry] failed

check_readiness
  → [readiness ≥ threshold AND outcome ≥ threshold] implement → dequeue_next
  → [readiness < threshold OR outcome < threshold] check_outcome

check_outcome
  → [outcome passes, readiness fails] diagnose
  → [outcome fails] check_decision_needed

check_decision_needed
  → [decision_needed == true] decide → re_assess → verify_re_assess_scores → check_convergence
  → [decision_needed == false] diagnose

diagnose → route_d_implement → route_d_decide → route_d_wire → route_d_refine
  (chained binary routers; first match wins)
  → IMPLEMENT match: implement → dequeue_next
  → DECIDE match: decide → re_assess → verify_re_assess_scores → check_convergence
  → WIRE match: wire → refine → re_assess → verify_re_assess_scores → check_convergence
  → REFINE match: refine → re_assess → verify_re_assess_scores → check_convergence
  → DECOMPOSE (no match / error): snap_for_size_review → run_size_review → detect_children
       → [children found] enqueue_children → dequeue_next
       → [no children] skip_issue → dequeue_next

check_convergence → route_conv_pass → route_conv_improved
  (chained binary routers; first match wins)
  → CONVERGED_PASS: implement → dequeue_next
  → CONVERGED_IMPROVED: check_remediation_budget
       → [passes < max] diagnose (re-enter deepening loop)
       → [passes ≥ max] snap_for_size_review (budget exhausted, try decomposition)
  → CONVERGED_STALLED (no match): snap_for_size_review (no improvement, try decomposition)
```

### Dimensional Diagnosis Routing Matrix

The `diagnose` state reads scores from `ll-issues show <id> --json` and parses these fields.
**Verified against `show.py:_parse_card_fields()` (line 246–286)**: The JSON output uses
`confidence` and `outcome` as keys (not `confidence_score` / `outcome_confidence` — those
are the frontmatter field names, not the JSON serialization keys).

JSON keys from `ll-issues show <id> --json`:

- `confidence` (0–100) — serialized from frontmatter `confidence_score` at `show.py:252`
- `outcome` (0–100) — serialized from frontmatter `outcome_confidence` at `show.py:253`
- `score_complexity` (0–25)
- `score_ambiguity` (0–25)
- `score_change_surface` (0–25)
- `score_test_coverage` (0–25, informational — not used in routing but logged)
- `decision_needed` (boolean, string `"true"`/`"false"`)
- `missing_artifacts` (string `"true"`/`"false"` — boolean serialized as lowercase string)

**Important**: Frontmatter uses `confidence_score` / `outcome_confidence`; `--json` uses
`confidence` / `outcome`. The diagnostic shell script MUST use the JSON keys, not the
frontmatter names.

Routing logic (pseudocode):

```bash
# Read scores from JSON (NOTE: JSON keys differ from frontmatter names)
SCORES=$(ll-issues show "$ISSUE_ID" --json)
CONFIDENCE=$(echo "$SCORES" | jq -r '.confidence // 0')           # JSON key: confidence
OUTCOME=$(echo "$SCORES" | jq -r '.outcome // 0')                 # JSON key: outcome
COMPLEXITY=$(echo "$SCORES" | jq -r '.score_complexity // 0')
AMBIGUITY=$(echo "$SCORES" | jq -r '.score_ambiguity // 0')
CHANGE_SURFACE=$(echo "$SCORES" | jq -r '.score_change_surface // 0')
DECISION_NEEDED=$(echo "$SCORES" | jq -r '.decision_needed // false')
MISSING_ARTIFACTS=$(echo "$SCORES" | jq -r '.missing_artifacts // false')

# Priority-ordered routing (first match wins)
if [ "$CONFIDENCE" -ge "$READINESS_THRESHOLD" ] && [ "$OUTCOME" -ge "$OUTCOME_THRESHOLD" ]; then
  echo "IMPLEMENT"
elif [ "$DECISION_NEEDED" = "true" ]; then
  echo "DECIDE"
elif [ "$AMBIGUITY" -ge 15 ]; then
  echo "WIRE"          # High ambiguity → needs integration wiring
elif [ "$COMPLEXITY" -ge 15 ] || [ "$CONFIDENCE" -lt 50 ]; then
  echo "REFINE"        # High complexity or very low confidence → needs deeper refinement
elif [ "$CHANGE_SURFACE" -ge 15 ]; then
  echo "DECOMPOSE"     # Large change surface → break down into smaller pieces
else
  # Default: attempt refinement first, decompose if already refined
  echo "REFINE"
fi
```

The threshold values (15 for ambiguity/complexity/change_surface, 50 for confidence fallback)
are initial defaults defined in the loop's context block. They should be tunable via
`ll-config.json` under a new `commands.rn_implement` section for post-MVP calibration.

### Convergence Check Shell Script

The `check_convergence` state runs a shell script that:

1. Reads pre-scores from `${context.run_dir}/pre_scores_<id>.json`
2. Reads post-scores from `${context.run_dir}/post_scores_<id>.json`
3. Computes the delta for each dimension:
   - `delta_confidence = post.confidence_score - pre.confidence_score`
   - `delta_outcome = post.outcome_confidence - pre.outcome_confidence`
   - `delta_complexity = post.score_complexity - pre.score_complexity` (lower is better, so invert)
   - `delta_ambiguity = post.score_ambiguity - pre.score_ambiguity` (lower is better, so invert)
4. Applies convergence rules (first match wins):

```bash
# Total improvement: sum of deltas where improvement is positive
# For complexity/ambiguity, improvement means score went DOWN
TOTAL_DELTA=$((delta_confidence + delta_outcome - delta_complexity - delta_ambiguity))

# PASS: confidence and outcome both meet thresholds
if [ "$post_confidence" -ge "$READINESS_THRESHOLD" ] && [ "$post_outcome" -ge "$OUTCOME_THRESHOLD" ]; then
  echo "CONVERGED_PASS"
# STALLED: no meaningful improvement (total delta ≤ 2)
elif [ "$TOTAL_DELTA" -le 2 ]; then
  echo "CONVERGED_STALLED"
# IMPROVED: meaningful progress but thresholds not yet met
else
  echo "CONVERGED_IMPROVED"
fi
```

**Token naming**: Uses `CONVERGED_PASS` / `CONVERGED_IMPROVED` / `CONVERGED_STALLED`
compound tokens instead of bare `PASS` / `IMPROVED` / `STALLED`. The
`test_no_bare_pass_token_in_output_contains` regression guard
(`test_builtin_loops.py:145-163`) forbids bare `"PASS"` as an `output_contains`
pattern because scoring annotations (e.g., `"design_quality: 8/10 — PASS"`)
contain the substring "PASS" and would produce false-positive matches.

**Multi-way routing**: `output_contains` is a binary evaluator — it supports only
`on_yes`/`on_no`. Three-way convergence routing therefore requires TWO chained
router states (following the `rn-refine.yaml` pattern at lines 129-148):

1. `check_convergence` — shell script outputs token, captured as
   `convergence_result`
2. `route_conv_pass` — `output_contains` with `source:
   "${captured.convergence_result.output}"`, `pattern: "CONVERGED_PASS"`;
   on_yes → `implement`, on_no → `route_conv_improved`
3. `route_conv_improved` — `output_contains` with `pattern:
   "CONVERGED_IMPROVED"`; on_yes → `check_remediation_budget`, on_no →
   `snap_for_size_review` (STALLED fallthrough)

Similarly, the `diagnose` state's 5-way routing requires four chained router
states (`route_d_implement`, `route_d_decide`, `route_d_wire`,
`route_d_refine`) with DECOMPOSE as the terminal fallthrough. Each catches
one token and passes unmatched output to the next.

**Revised state count**: 31 states (26 active + 2 terminal + 1 diagnostic +
2 convergence routers). The original 25-state count treated multi-way routing
as a single `output_contains` state, but `output_contains` is binary — each
extra route branch adds a router state.

### Edge Case Handling (Complete)

| Edge Case | Detection | Response |
|-----------|-----------|----------|
| Empty input (no issue ID) | `init` state: `context.input` is empty or whitespace | Route to `failed`, exit code 1 |
| Empty queue | `dequeue_next`: queue file has no remaining lines | Route to `done`, write summary |
| Max depth reached | `dequeue_next`: `current_depth > max_depth` | Route to `mark_depth_capped`, log to `${context.run_dir}/depth_capped.txt`, advance queue |
| All remediation exhausted | `check_remediation_budget`: `pass_count >= max_remediation_passes` | Route to `snap_for_size_review` → decomposition path |
| Diagnose outputs no token | `diagnose`: shell script produces empty/whitespace output | Fallthrough route to `snap_for_size_review` (decomposition as safe default) |
| Rate limit exhausted | On any LLM state: `with_rate_limit_handling` fragment triggers | Route to `rate_limit_diagnostic` → `dequeue_next` (skip current issue) |
| Skill invocation fails | State action returns non-zero exit code | Log failure to `${context.run_dir}/failures.txt`, route to `skip_issue` → `dequeue_next` |
| Skill invocation times out | FSM executor timeout (default 300s per state) | Log timeout to `${context.run_dir}/timeouts.txt`, route to `skip_issue` → `dequeue_next` |
| Confidence-check scores not persisted | `verify_scores_persisted` / `verify_re_assess_scores`: scores absent from frontmatter | Retry once; on second failure, log and route to `failed` |
| Child detection finds no children | `detect_children`: diff produces empty output | Route to `skip_issue` (not an error — issue may be atomic) |
| Cycle detected | `enqueue_children`: child ID already in visited-set file | Skip that child, log to `${context.run_dir}/cycles.txt`, continue with remaining children |
| Config file missing thresholds | `init`: `ll-config.json` key not found | Use loop-context defaults (readiness=85, outcome=75, max_depth=3) |
| `ll-issues show --json` parse failure | `diagnose`: jq parse error | Log raw output to `${context.run_dir}/parse_errors.txt`, fallthrough to DECOMPOSE |

### Operational Concerns

**Mid-loop failure recovery**: On any state failure (non-zero exit, timeout), the loop writes
the current queue state, visited set, and remediation counters to `${context.run_dir}/checkpoint.json`
before transitioning to `failed`. A subsequent run with the same `run_dir` can resume by
reading the checkpoint.

**Phased rollout plan**:
1. **Phase 1 — Dry runs**: Run `rn-implement` against 5–10 closed issues from `.issues/`
   that have known confidence-check scores. Compare rn-implement's routing decisions against
   what autodev did. Validate that dimensional routing produces sensible tokens.
2. **Phase 2 — Shadow mode**: Run rn-implement in parallel with autodev on new issues,
   comparing outcomes (implemented vs. decomposed vs. skipped). Do not merge rn-implement's
   changes; only observe.
3. **Phase 3 — Opt-in**: Announce rn-implement as available opt-in for developers who want
   iterative deepening. Gather feedback for 1–2 weeks.
4. **Phase 4 — Default for complex issues**: Wire rn-implement as the default loop for issues
   flagged with `complexity: high` or `ambiguity: high`.

**Monitoring hooks**: Add state-transition logging to `${context.run_dir}/transitions.jsonl`
(every state entry/exit with timestamp and context snapshot) for post-run diagnostics. This
is standard in autodev and recursive-refine and should be carried forward.

**Backward compatibility**: rn-implement is a new loop — no existing callers to break.
The only integration point is `test_builtin_loops.py` where the expected-set addition is
additive. Autodev continues to work unchanged.

### Codebase Research Verification

_Added by `/ll:refine-issue --full-rewrite` — verified against actual code on 2026-06-04:_

#### Verified Claims

| Claim | Verification | Source |
|-------|-------------|--------|
| `ll-issues show --json` field names | JSON keys are `confidence` and `outcome` (NOT `confidence_score` / `outcome_confidence`) | `show.py:252-253` — `_parse_card_fields()` serializes frontmatter `confidence_score` → JSON key `confidence` |
| `output_contains` is binary | Supports only `on_yes`/`on_no`; multi-way routing needs chained router states | `validation.py:68` — evaluator schema; `rn-refine.yaml:129-148` — chained router pattern |
| Bare `PASS` token forbidden | `test_no_bare_pass_token_in_output_contains` (`test_builtin_loops.py:145-163`) asserts pattern ≠ `"PASS"` | Compound tokens (`CONVERGED_PASS`) avoid substring collisions with scoring annotations |
| `check-readiness` flags | Takes `--readiness` and `--outcome` as threshold overrides; no `--outcome-only` flag exists | `check_readiness.py:14-53` |
| `check-flag` behavior | Exit 0 if frontmatter field equals `"true"` (case-insensitive); exit 1 otherwise | `check_flag.py:13-33` |
| `ll-issues list --json` format | Standard JSON array; used by autodev for child detection via `comm -13` pre/post diff | `autodev.yaml:77,331` |
| Frontmatter field names | `confidence_score` and `outcome_confidence` in `.md` frontmatter (these differ from JSON keys) | `check_readiness.py:50-51`; `show.py:252-253` |
| `convergence_gate` fragment | Single-dimension numeric convergence with `direction: maximize`; inappropriate for multi-dim comparison | `lib/common.yaml:118-129` |
| `queue_pop` fragment | Adds `evaluate: {type: exit_code}`; caller must supply the `head -1`/`tail -n +2`/`mv` shell script | `lib/common.yaml:131-139` |
| `with_rate_limit_handling` fragment | Two-tier (short 3-retry + long 6hr ladder); requires `on_rate_limit_exhausted` from caller | `lib/common.yaml:61-74` |
| `retry_counter` fragment | `output_numeric` evaluator with `operator: lt` against `param.max_retries` | `lib/common.yaml:23-45` |
| MR-1 compliance | Non-LLM evaluator (`exit_code`, `output_contains`, `output_numeric`) must pair with `check_semantic` (`llm_structured`) for meta-loops | `validation.py:1034` — `_validate_meta_loop_evaluation` |
| MR-3 compliance | Temp files under `${context.run_dir}/` only; `.loops/tmp/` writes flagged as WARNING | `validation.py:103-105` — `_SHARED_TMP_PATH_RE` |
| Sub-loop context passthrough | `context_passthrough: true` forwards `captured.input.output` as sub-loop's `context.input` | `autodev.yaml:104-105` |

#### Corrections Applied

1. **JSON field names**: Fixed `.confidence_score` → `.confidence`, `.outcome_confidence` → `.outcome` in diagnose pseudocode
2. **Convergence tokens**: Changed bare `PASS`/`IMPROVED`/`STALLED` → `CONVERGED_PASS`/`CONVERGED_IMPROVED`/`CONVERGED_STALLED`
3. **Multi-way routing**: Documented that `output_contains` is binary; 3-way convergence needs 2 chained router states; 5-way diagnose needs 4 chained router states; revised state count 25 → 31
4. **`--outcome-only` flag**: Confirmed nonexistent — Step 4's `check_outcome` state must use inline `jq` frontmatter check instead
5. **`missing_artifacts` in JSON**: Field is serialized as lowercase string `"true"`/`"false"` (not a list), per `show.py:277-279`

#### Pattern Confirmations

- **Chained router pattern** (`rn-refine.yaml:105-148`): `classify_research` captures output → `route_files` checks NEEDS_FILES → `route_web` checks NEEDS_WEB → fallthrough. This is the pattern rn-implement uses for both the diagnose (5 tokens) and convergence (3 tokens) routing chains.
- **Queue pop + inflight sentinel** (`autodev.yaml:56-92`): `head -1`/`tail -n +2`/`mv` idiom, captured as `input` for downstream states. Also writes current ID to inflight sentinel for crash recovery.
- **Child detection via `ll-issues list --json` diff** (`autodev.yaml:324-361`): `comm -13` pre/post snapshots, `grep "Decomposed from $PARENT"` filter for parent reference validation.
- **Depth-first enqueuing** (`recursive-refine.yaml:261-324`): `{ echo "$CHILDREN"; echo "$EXISTING"; }` prepend pattern, with cycle detection via visited-set file.

## Use Case

**Who**: A developer or CI automation running `ll-loop run rn-implement "EPIC-1811"`
to process a complex epic with issues that need multi-pass refinement before they're
ready to implement.

**Context**: The developer has a set of issues that `autodev` keeps skipping or
decomposing because confidence-check scores are below threshold. Single-pass refinement
isn't enough — these issues need iterative deepening.

**Goal**: Run `rn-implement` which diagnoses each issue dimensionally, applies targeted
remediation (refine, wire, decide), re-assesses, and converges only when scores cross
thresholds — implementing immediately when ready, decomposing only when remediation
is exhausted.

**Outcome**: More issues reach IMPLEMENT-ready state without unnecessary decomposition,
and those that truly need decomposition are correctly identified after systematic
remediation attempts.

## Acceptance Criteria

- [ ] `loops/rn-implement.yaml` passes `ll-loop validate` (MR-1 and MR-3 clean)
- [ ] All 31 states have correct routing (verified by `TestRoutingStructure` — test parses
  every `route:` and `next:` key, confirms no dead-end states, no unreachable states)
- [ ] `diagnose` state correctly outputs all 5 tokens for their respective score combinations,
  and the 4 chained router states (8a–8d) dispatch correctly: IMPLEMENT (both thresholds met),
  DECIDE (decision_needed=true), WIRE (ambiguity≥15), REFINE (complexity≥15 or confidence<50),
  DECOMPOSE (change_surface≥15 or fallthrough)
- [ ] `check_convergence` correctly outputs CONVERGED_PASS/CONVERGED_IMPROVED/CONVERGED_STALLED
  for known pre/post score deltas, and the 2 chained router states (15a–15b) dispatch correctly:
  - CONVERGED_PASS: both scores at/above thresholds
  - CONVERGED_IMPROVED: total_delta > 2, thresholds not yet met
  - CONVERGED_STALLED: total_delta ≤ 2, thresholds not yet met
- [ ] `check_remediation_budget` gates at `max_remediation_passes` → route to decomposition;
  under budget → route back to `diagnose`
- [ ] Depth tracking: child depth = parent+1 written to queue entries; enqueuing skipped
  when `current_depth + 1 > max_depth`
- [ ] Cycle detection: visited-set file (`${context.run_dir}/visited.txt`) checked before
  each enqueue; duplicate issue IDs logged to `${context.run_dir}/cycles.txt` and skipped
- [ ] All temp files written under `${context.run_dir}/`; no writes to `.loops/tmp/` (MR-3)
- [ ] `test_rn_implement.py` passes with ≥90% coverage on loop-specific logic
- [ ] `test_builtin_loops.py` parametrized sweep passes with `rn-implement` in the expected set
- [ ] Dry run `ll-loop run rn-implement "FEAT-9999"` loads FSM, executes init, detects
  nonexistent issue, routes to `failed` (graceful)
- [ ] Full test suite passes with no regressions (`python -m pytest scripts/tests/ -x`)

## API/Interface

```yaml
# Loop invocation
ll-loop run rn-implement "<issue-id-or-epic-id>"

# Context variables injected by runner
# NOTE: rn-implement uses the default input_key ("input"), matching autodev.
# The positional CLI arg is accessible as context.input (NOT context.issue_id).
context.run_dir              # .loops/runs/rn-implement-<timestamp>/
context.input                # Seed issue ID(s) — e.g., "FEAT-1933" or "EPIC-1811"
context.max_depth            # From ll-config.json → commands.recursive_refine.max_depth (default 3)
context.max_remediation_passes  # Loop parameter (default 3)
context.readiness_threshold  # From ll-config.json → commands.confidence_gate.readiness_threshold (default 85)
context.outcome_threshold    # Loop-context default 75 (overrides config-schema default of 70, matching autodev convention)

# Config reads (from ll-config.json, with loop-context fallbacks)
# commands.confidence_gate.readiness_threshold → context.readiness_threshold (schema default: 85)
# commands.confidence_gate.outcome_threshold → context.outcome_threshold (schema default: 70, loop overrides to 75)
# commands.recursive_refine.max_depth → context.max_depth (schema default: 3)

# No new config keys required for MVP. A commands.rn_implement section can be added
# post-MVP to tune the diagnose routing matrix thresholds without editing the YAML.

# JSON field name mapping (verified against show.py:246-286):
# ┌──────────────────────────┬─────────────────────────┐
# │ Frontmatter field         │ JSON key (--json)       │
# ├──────────────────────────┼─────────────────────────┤
# │ confidence_score          │ confidence              │
# │ outcome_confidence        │ outcome                 │
# │ score_complexity          │ score_complexity        │
# │ score_ambiguity           │ score_ambiguity         │
# │ score_change_surface      │ score_change_surface    │
# │ score_test_coverage       │ score_test_coverage     │
# │ decision_needed           │ decision_needed         │
# │ missing_artifacts         │ missing_artifacts       │
# └──────────────────────────┴─────────────────────────┘
# Note: confidence_score and outcome_confidence are the ONLY fields where
# the JSON key differs from the frontmatter name. The diagnose shell script
# must use .confidence and .outcome (not .confidence_score / .outcome_confidence).
```

### State Actions — Corrected Skill/Command Classification

Each action below includes whether it's a **skill** (invoked as `/ll:<name>`) or a
**command** (invoked as `<name>`), and whether `--auto` is supported:

| State | Action | Type | --auto? | Notes |
|-------|--------|------|---------|-------|
| `assess`, `re_assess` | `/ll:confidence-check <id>` | **Skill** (`skills/confidence-check/SKILL.md:46`) | Yes | Writes `confidence_score`, `outcome_confidence`, and dimensional scores to issue frontmatter |
| `implement` | `ll-auto --only <id>` | **CLI command** (`scripts/little_loops/cli/auto.py:43`) | N/A | Direct process invocation, not a slash command |
| `decide` | `/ll:decide-issue <id>` | **Skill** (`skills/decide-issue/SKILL.md:36`) | Yes | Resolves `decision_needed` options; use `--auto` for non-interactive runs |
| `wire` | `/ll:wire-issue <id>` | **Skill** (`skills/wire-issue/SKILL.md`) | Yes | Adds integration wiring to implementation plan |
| `refine` | `/ll:refine-issue <id>` | **Command** (`commands/refine-issue.md:40,43`) | Yes (`--auto` + `--full-rewrite`) | `--full-rewrite` passes count against `max_refine_count` (default 5) |
| `run_size_review` | `/ll:issue-size-review <id>` | **Skill** (`skills/issue-size-review/SKILL.md`) | Yes | Reviews issue size, may trigger decomposition |

All skill invocations use `action_type: slash_command` in the YAML, which is the same mechanism
autodev uses successfully (e.g., `autodev.yaml:216` for confidence-check).

## Integration Map

### Files to Modify
- **CREATE** `scripts/little_loops/loops/rn-implement.yaml` — ~550 lines, imports `lib/common.yaml`
  (specifically: `queue_pop`, `queue_track`, `with_rate_limit_handling`, `retry_counter`,
  `shell_exit`, `numeric_gate`; does NOT use `convergence_gate` — that fragment is for
  single-dimension numeric convergence and is inappropriate for multi-dimensional score comparison)
- **CREATE** `scripts/tests/test_rn_implement.py` — ~700 lines, 12 test classes (see Test Strategy below)
- **EDIT** `scripts/tests/test_builtin_loops.py` — add `"rn-implement"` to the expected set
  (insert alphabetically among the ~65 existing entries around line 74–141)
- **EDIT** `docs/guides/LOOPS_GUIDE.md` — add row to Planning table (~line 441), full section
  after autodev section (~line 1450)

### Dependent Files (Callers/Importers)
- N/A (new loop, no existing callers)

_Wiring pass added by `/ll:wire-issue`:_
- Auto-discovery confirmed: loops are loaded via `rglob("*.yaml")` filtered by `is_runnable_loop()`
  in `scripts/little_loops/fsm/validation.py:1525`. No explicit registration site exists — creating
  the YAML file is sufficient for runtime discovery. All loop resolution paths (`resolve_loop_path()`
  in `cli/loop/_helpers.py:840`, `cmd_list()` in `cli/loop/info.py:53`, `cmd_install()` in
  `cli/loop/config_cmds.py:43`, `load_loop()` in `cli/loop/_helpers.py:864`) use glob-based
  discovery. [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/loop/next_loop.py` line 152-153 — `_PARAM_RESOLVERS` dict currently
  only contains `"autodev"`. Adding `"rn-implement"` with a resolver for auto-resolving open issue
  IDs would enable `ll-loop next-loop` to suggest rn-implement with pre-filled inputs. Optional
  for MVP, but should be added before Phase 3 (opt-in) rollout. [Agent 2 finding]

### Similar Patterns (Source Material)
- `scripts/little_loops/loops/recursive-refine.yaml` — Depth tracking (`max_depth: 3` at line 28),
  visited-set file pattern (`recursive-refine-visited.txt`), queue-based processing
- `scripts/little_loops/loops/rn-refine.yaml` — Iterative deepening loop structure, convergence
  check pattern (pre/post score comparison), remediation budget gating. Note: `rn-refine.yaml:3`
  uses `input_key: plan_file` — rn-implement uses the default `input_key: input`, matching
  autodev, not rn-refine's custom key
- `scripts/little_loops/loops/autodev.yaml` — Inflight tracking (`autodev.yaml:72`),
  `ll-auto --only` integration (`autodev.yaml:318`), child enqueuing depth-first
  (`autodev.yaml:363-388`), `ll-issues list --json` diff pattern for child detection
  (`autodev.yaml:77,247,331,499`), `with_rate_limit_handling` on all LLM states
- `scripts/little_loops/loops/lib/common.yaml` — Shared fragments: `shell_exit` (line 15),
  `retry_counter` (line 23), `llm_gate` (line 47), `with_rate_limit_handling` (line 62),
  `numeric_gate` (line 108), `convergence_gate` (line 118), `diff_stall_gate` (line 148),
  `queue_pop` (line 131), `queue_track` (line 141)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — NOT used (inlined instead), but
  studied for the refine→wire→confidence-check chain pattern and broke-down handshake mechanism

### Tests
- **CREATE** `scripts/tests/test_rn_implement.py` — 12 test classes (see Implementation Steps
  for per-class scope)
- **EDIT** `scripts/tests/test_builtin_loops.py` — register `"rn-implement"` in
  `test_expected_loops_exist` expected set

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py` — `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration`
  (line 999-1023) has a hardcoded `migration_targets` list of built-in loops that use the `shell_exit`
  fragment. Since rn-implement imports `shell_exit` from `lib/common.yaml`, `"rn-implement.yaml"` must be
  added to this list or the test will fail when it validates all migration-target loops [Agent 1 finding]
- Auto-cover confirmation: the `builtin_loops` fixture in `test_builtin_loops.py` (line 28) uses
  `rglob("*.yaml")` filtered by `is_runnable_loop()`, so all 6 parametrized structural tests
  (`test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, `test_all_have_description_field`,
  `test_no_bare_pass_token_in_output_contains`, `test_no_bare_bash_variable_in_shell_actions`,
  `test_all_failure_terminals_have_diagnostic_action`) will automatically exercise rn-implement
  once the YAML is created. No additional registration in these tests is needed [Agent 3 finding]
- `scripts/tests/test_fsm_flow.py::TestBuiltinLoopRegression.test_all_builtin_loops_still_load`
  (line 325) also auto-covers via `glob("*.yaml")` [Agent 3 finding]

### Documentation
- **EDIT** `docs/guides/LOOPS_GUIDE.md` — add rn-implement entry to Planning table and full
  section after autodev
- **EDIT** `scripts/little_loops/loops/README.md` — add rn-implement row to Planning category
  table (authoritative built-in loops catalog)

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — update "71 FSM loops" to "72 FSM loops" (line 163); `ll-verify-docs` checks
  this count against actual runnable loops and will flag a mismatch [Agent 2 finding]
- `CONTRIBUTING.md` — update "61 YAML files" to "62 YAML files" (line 122); `ll-verify-docs`
  checks this count and will flag a mismatch [Agent 2 finding]
- `CHANGELOG.md` — record new loop addition (convention for all prior loop additions,
  e.g., rn-refine at line 270, rn-plan at line 331) [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — add rn-implement entry to Planning table (line 46-52);
  this is the authoritative catalog of built-in loops [Agent 1 finding]

### Configuration
- Reads existing config keys: `commands.confidence_gate.readiness_threshold`,
  `commands.confidence_gate.outcome_threshold`, `commands.recursive_refine.max_depth`
- No new config keys required for MVP
- Post-MVP: add `commands.rn_implement` section for tuning the diagnose routing matrix thresholds

## Implementation Steps

### Phase 1: Foundation (States 1–7, Terminal States)

**Step 1: Create loop YAML skeleton with context and imports**
- Create `scripts/little_loops/loops/rn-implement.yaml`
- Define top-level metadata: `name: rn-implement`, `description`, `input_key: input` (default),
  `meta_self_eval_ok: false` (MR-1 enforced), `shared_state_ok: false` (MR-3 enforced)
- Set loop-level context defaults:
  ```yaml
  context:
    readiness_threshold: 85
    outcome_threshold: 75    # Override config-schema default of 70, match autodev
    max_depth: 3
    max_remediation_passes: 3
    run_dir: "${context.run_dir}"
  ```
- Import fragments from `lib/common.yaml`: `shell_exit`, `queue_pop`, `queue_track`,
  `with_rate_limit_handling`, `retry_counter`, `numeric_gate`, `llm_gate`, `diff_stall_gate`
- Define all 25 state stubs with placeholder `next:` routing (validated that every state
  has at least one outgoing edge)
- Dependencies: none (greenfield file)

**Step 2: Implement `init` state (state 1)**
- Action: shell script that:
  - Validates `context.input` is non-empty
  - Creates `${context.run_dir}/` directory
  - Seeds queue file at `${context.run_dir}/queue.txt` with `context.input`
  - Initializes `${context.run_dir}/visited.txt` (empty)
  - Initializes `${context.run_dir}/depth.txt` with `0`
  - Writes config snapshot to `${context.run_dir}/config.json` (thresholds, max_depth, max_remediation_passes)
- Routing: queue seeded → `dequeue_next`; empty input → `failed`
- Dependencies: step 1

**Step 3: Implement `dequeue_next` state (state 2)**
- Action: shell script using `queue_pop` fragment that:
  - Pops first line from `${context.run_dir}/queue.txt`
  - Reads current depth from `${context.run_dir}/depth.txt`
  - Compares depth to `context.max_depth`
- Routing: issue available + depth ≤ max → `assess`; empty queue → `done`;
  depth > max → `mark_depth_capped`
- Dependencies: step 2

**Step 4: Implement `assess` → `verify_scores_persisted` → `check_readiness` → `check_outcome` → `check_decision_needed` chain (states 3–7)**
- `assess` (state 3): `action_type: slash_command`, command: `/ll:confidence-check <id> --auto`.
  Wrap with `with_rate_limit_handling` (on_exhausted: `rate_limit_diagnostic`). On success,
  write pre-scores: shell parses `ll-issues show <id> --json` and writes to
  `${context.run_dir}/pre_scores_<id>.json`. → `verify_scores_persisted`
- `verify_scores_persisted` (state 4): Shell checks that `confidence_score` and `outcome_confidence`
  exist in issue frontmatter. On failure, retry once (using `retry_counter` fragment). On second
  failure → `failed`. On success → `check_readiness`
- `check_readiness` (state 5): Shell: `ll-issues check-readiness <id>`. Exit-code evaluator:
  exit 0 → `implement`; exit 1 → `check_outcome`
- `check_outcome` (state 6): Shell: `ll-issues check-readiness <id> --outcome-only` (hypothetical
  flag — check if supported; if not, inline jq check: `outcome_confidence >= outcome_threshold`).
  Exit 0 → `diagnose`; exit 1 → `check_decision_needed`
- `check_decision_needed` (state 7): Shell: `ll-issues check-flag <id> decision_needed`.
  Exit 0 → `decide`; exit 1 → `diagnose`
- Dependencies: step 3

**Step 5: Implement terminal states `done` (23) and `failed` (24)**
- `done`: Shell writes summary JSON to `${context.run_dir}/summary.json`:
  `{total_processed, implemented, decomposed, skipped, depth_capped, failed, run_duration_seconds}`.
  No outgoing edge (terminal).
- `failed`: Shell writes error JSON to `${context.run_dir}/error.json`:
  `{error, failed_state, issue_id, timestamp}`. Also writes checkpoint (queue, visited, counters).
  No outgoing edge (terminal).
- Dependencies: step 2 (both states are routed to from dequeue_next)

### Phase 2: Remediation Core (States 8–16)

**Step 6: Implement `diagnose` state (state 8) — the dimensional routing core**
- Action: shell script (embedded inline in YAML) that:
  1. Calls `ll-issues show <id> --json` and parses with `jq`
  2. Extracts: `confidence_score`, `outcome_confidence`, `score_complexity`,
     `score_ambiguity`, `score_change_surface`, `decision_needed`
  3. Applies the routing matrix from §Dimensional Diagnosis Routing Matrix above
  4. Outputs exactly one token: IMPLEMENT, DECIDE, WIRE, REFINE, or DECOMPOSE
  5. Logs scores and selected token to `${context.run_dir}/diagnosis_<id>.json`
- Routing: 5-way `output_contains` evaluator (one route per token) + fallthrough → `snap_for_size_review`
- Pair with `check_semantic` (llm_structured) for MR-1 compliance
- Wrap with `with_rate_limit_handling` (the `ll-issues show` may involve an LLM under the hood — if
  it doesn't, the wrap is harmless)
- Dependencies: step 4 (diagnose is the convergence point for check_outcome and check_decision_needed)

**Step 7: Implement remediation action states (states 9–12)**
- `implement` (state 9): `action_type: shell`, command: `ll-auto --only <id>`.
  On exit 0 → `dequeue_next`; on failure → `skip_issue`
- `decide` (state 10): `action_type: slash_command`, command: `/ll:decide-issue <id> --auto`.
  Wrap with `with_rate_limit_handling`. On success → `re_assess` (always re-check after decide).
  Write `decision_applied: true` marker to `${context.run_dir}/decisions_<id>.txt`
- `wire` (state 11): `action_type: slash_command`, command: `/ll:wire-issue <id> --auto`.
  Wrap with `with_rate_limit_handling`. On success → `refine` (always chain: wiring may reveal gaps).
  On failure → `refine` anyway (refine can still improve the issue without wiring)
- `refine` (state 12): `action_type: slash_command`, command: `/ll:refine-issue <id> --auto --full-rewrite`.
  Wrap with `with_rate_limit_handling`. Increment refine counter in
  `${context.run_dir}/refine_count_<id>.txt`. On success → `re_assess`; on failure → `skip_issue`
- Dependencies: step 6 (these are the targets of diagnose's routing tokens)

**Step 8: Implement `re_assess` → `verify_re_assess_scores` chain (states 13–14)**
- `re_assess` (state 13): Identical to `assess` (state 3) but writes post-scores to
  `${context.run_dir}/post_scores_<id>.json` instead of pre-scores. Reuse the same
  `action_type: slash_command` with `/ll:confidence-check <id> --auto`.
  Wrap with `with_rate_limit_handling`. → `verify_re_assess_scores`
- `verify_re_assess_scores` (state 14): Identical pattern to `verify_scores_persisted` (state 4).
  On success → `check_convergence`; on failure → retry once, then → `failed`
- Dependencies: step 7 (re_assess is the target after decide, wire→refine, and refine)

**Step 9: Implement `check_convergence` state (state 15)**
- Action: shell script that:
  1. Reads `${context.run_dir}/pre_scores_<id>.json` and `${context.run_dir}/post_scores_<id>.json`
  2. Computes delta for each dimension (confidence, outcome: higher is better;
     complexity, ambiguity: lower is better, so invert delta sign)
  3. Computes `total_delta = delta_confidence + delta_outcome - delta_complexity - delta_ambiguity`
  4. Applies convergence rules from §Convergence Check Shell Script above
  5. Outputs PASS, IMPROVED, or STALLED
  6. Increments remediation counter in `${context.run_dir}/remediation_count_<id>.txt`
  7. Logs pre/post/delta to `${context.run_dir}/convergence_<id>.json`
- Evaluator: `output_contains` (non-LLM, 3-way routing) paired with `check_semantic` (llm_structured)
  for MR-1 compliance
- Routing: PASS → `implement`; IMPROVED → `check_remediation_budget`; STALLED → `snap_for_size_review`
- Dependencies: step 8

**Step 10: Implement `check_remediation_budget` state (state 16)**
- Action: shell script that reads `${context.run_dir}/remediation_count_<id>.txt` and compares
  to `context.max_remediation_passes`
- Evaluator: `output_numeric` (non-LLM) — outputs current count, compared against threshold
  in the `numeric_gate` fragment. Paired with `check_semantic` for MR-1 compliance
- Routing: count < max → `diagnose` (re-enter deepening loop); count ≥ max → `snap_for_size_review`
  (budget exhausted, escalate to decomposition)
- Dependencies: step 9

### Phase 3: Decomposition Path (States 17–22)

**Step 11: Implement decomposition chain (states 17–21)**
- `snap_for_size_review` (state 17): Shell writes current issue state snapshot to
  `${context.run_dir}/size_review_snap_<id>.json` (scores, depth, remediation count, timestamp).
  → `run_size_review`
- `run_size_review` (state 18): `action_type: slash_command`, command: `/ll:issue-size-review <id> --auto`.
  Wrap with `with_rate_limit_handling`. On success → `detect_children`; on failure → `skip_issue`
- `detect_children` (state 19): Shell script that:
  1. Captures current issue list: `ll-issues list --json` → `${context.run_dir}/issues_before_<id>.json`
  2. (size_review already ran; new issues created by it)
  3. Captures new issue list: `ll-issues list --json` → `${context.run_dir}/issues_after_<id>.json`
  4. Diffs: `jq` filter to find IDs in "after" but not in "before"
  5. Writes child IDs (one per line) to `${context.run_dir}/children_<id>.txt`
  6. Outputs count of children found
- Routing: children found → `enqueue_children`; no children → `skip_issue`
- `enqueue_children` (state 20): Shell script that:
  1. Reads `${context.run_dir}/children_<id>.txt`
  2. For each child: checks `${context.run_dir}/visited.txt` — if already visited → log to
     `${context.run_dir}/cycles.txt` and skip
  3. For new children: computes `child_depth = parent_depth + 1`, appends to
     `${context.run_dir}/visited.txt`, inserts at FRONT of `${context.run_dir}/queue.txt`
     (depth-first: newest children processed first)
  4. Writes `parent_id: <current_id>` to each child's queue entry metadata
  → `dequeue_next`
- `skip_issue` (state 21): Shell logs skip reason to `${context.run_dir}/skipped.txt`.
  → `dequeue_next`
- Dependencies: step 10 (snap_for_size_review is the convergence point for STALLED, budget exhausted,
  and diagnose fallthrough)

**Step 12: Implement `mark_depth_capped` state (state 22) and `rate_limit_diagnostic` state (state 25)**
- `mark_depth_capped` (state 22): Shell logs issue ID and current depth to
  `${context.run_dir}/depth_capped.txt`. → `dequeue_next`
- `rate_limit_diagnostic` (state 25): Shell logs timestamp and triggering state to
  `${context.run_dir}/rate_limits.txt`. → `dequeue_next` (skip current issue, process queue)
- Dependencies: step 3 (mark_depth_capped is routed from dequeue_next);
  step 4+ (rate_limit_diagnostic is routed from with_rate_limit_handling on all LLM states)

### Phase 4: Tests

**Step 13: Create test file `scripts/tests/test_rn_implement.py` with 12 test classes**

Test class scopes:

| # | Test Class | Covers | Key Assertions |
|---|-----------|--------|----------------|
| 1 | `TestInitAndInputValidation` | States 1, 24 | Non-empty input seeds queue; empty input → failed; run_dir created |
| 2 | `TestDequeueAndDepthTracking` | States 2, 22 | Queue FIFO order; depth cap enforced at max_depth=3; depth-capped logged |
| 3 | `TestAssessAndScorePersistence` | States 3, 4 | Confidence-check invoked; pre_scores written; verification retries once |
| 4 | `TestReadinessAndDecisionGates` | States 5, 6, 7 | check-readiness exit codes; check-flag routing; decision_needed → decide |
| 5 | `TestDiagnoseRouting` | State 8 | All 5 tokens for known score combinations; fallthrough on empty output; MR-1 pairing present |
| 6 | `TestRemediationActions` | States 9, 10, 11, 12 | Implement → dequeue_next; decide → re_assess; wire → refine; refine → re_assess; failure → skip |
| 7 | `TestReassessAndConvergence` | States 13, 14, 15 | Post-scores written; PASS/IMPROVED/STALLED for known deltas; remediation counter incremented; MR-1 pairing present |
| 8 | `TestRemediationBudget` | State 16 | Under budget → diagnose; at limit → snap_for_size_review; MR-1 pairing present |
| 9 | `TestDecompositionChain` | States 17, 18, 19, 20, 21 | Size review invoked; child detection via diff; depth-first enqueuing; visited-set filtering; no-children → skip |
| 10 | `TestCycleDetection` | State 20 | Duplicate child ID skipped; logged to cycles.txt; visited.txt updated |
| 11 | `TestRateLimitAndErrorHandling` | State 25, all wrappers | Rate limit → skip current; skill failure → skip; timeout → skip; checkpoint written on failed |
| 12 | `TestRoutingStructure` | All 25 states | Every state has ≥1 outgoing edge; no dead-end states (except terminal done/failed); every state reachable from init; verify 25-state count |

- Dependencies: steps 1–12 (tests exercise the complete FSM)

**Step 14: Register in `test_builtin_loops.py`**
- Edit `scripts/tests/test_builtin_loops.py`:
  - Find the expected set literal in `test_expected_loops_exist` (around line 74–141)
  - Insert `"rn-implement"` alphabetically among the ~65 existing entries
  - Verify the set count matches: `len(expected) == 66` (65 existing + 1 new)
- Dependencies: step 13 (the YAML file must exist for the glob to find it)

### Phase 5: Documentation and Validation

**Step 15: Update `docs/guides/LOOPS_GUIDE.md`**
- Add `rn-implement` row to the Planning loops table (~line 441):
  `| rn-implement | Recursive plan-and-implement with iterative deepening, dimensional routing, and convergence detection |`
- Add a full section after the autodev section (~line 1450) covering:
  - What it does and when to use it (vs. autodev)
  - The four-gap motivation
  - The 25-state architecture with the routing diagram
  - Configuration: thresholds, max_depth, max_remediation_passes
  - Invocation examples: `ll-loop run rn-implement "FEAT-1933"`, `ll-loop run rn-implement "EPIC-1811"`
  - Differences from autodev: dimensional routing, iterative deepening, inlined vs. delegated refine
- Dependencies: step 1 (loop name and architecture are defined)

**Step 16: Validate and dry-run**
- Run `ll-loop validate rn-implement` — must pass with MR-1 and MR-3 clean
- Run `python -m pytest scripts/tests/test_rn_implement.py -v` — all 12 test classes pass
- Run `python -m pytest scripts/tests/test_builtin_loops.py::test_expected_loops_exist -v` —
  rn-implement found in expected set
- Run `ll-loop run rn-implement "FEAT-9999"` — dry run against nonexistent issue: loads FSM,
  executes init, detects missing issue, routes to `failed` gracefully (exit code 1, error.json written)
- Run full test suite: `python -m pytest scripts/tests/ -x` — no regressions
- Dependencies: steps 1–15

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

17. Update `scripts/little_loops/loops/README.md` — add `| rn-implement | Recursive plan-and-implement with iterative deepening, dimensional routing, and convergence detection | <inputs> |` row to the Planning category table (lines 46-52). This is the authoritative built-in loops catalog. [Agent 1 finding]
18. Update `README.md` line 163 — increment "71 FSM loops" to "72 FSM loops". `ll-verify-docs` checks this count against actual runnable loops and will fail on mismatch. [Agent 2 finding]
19. Update `CONTRIBUTING.md` line 122 — increment "61 YAML files" to "62 YAML files" (or whatever the actual count becomes after creation). `ll-verify-docs` checks this count and will fail on mismatch. [Agent 2 finding]
20. Update `scripts/tests/test_fsm_fragments.py` line 999-1023 — add `"rn-implement.yaml"` to the `migration_targets` list in `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration`. rn-implement imports `shell_exit` from `lib/common.yaml`, so it must be in this list. [Agent 1 + Agent 3 finding]
21. Add CHANGELOG entry — record the new loop addition following convention (see prior loop additions: rn-refine at ~line 270, rn-plan at ~line 331). [Agent 2 finding]

### Dependency Graph (updated)

```
Step 1 (skeleton)
├─ Step 2 (init) ── depends on: 1
├─ Step 3 (dequeue_next) ── depends on: 2
├─ Step 4 (assess chain) ── depends on: 3
├─ Step 5 (done/failed) ── depends on: 2
├─ Step 6 (diagnose) ── depends on: 4
├─ Step 7 (remediation actions) ── depends on: 6
├─ Step 8 (re_assess chain) ── depends on: 7
├─ Step 9 (check_convergence) ── depends on: 8
├─ Step 10 (check_remediation_budget) ── depends on: 9
├─ Step 11 (decomposition chain) ── depends on: 10
├─ Step 12 (depth_capped / rate_limit) ── depends on: 3, 4+
├─ Step 13 (test_rn_implement.py) ── depends on: 1-12
├─ Step 14 (test_builtin_loops.py) ── depends on: 13
├─ Step 15 (LOOPS_GUIDE.md) ── depends on: 1
├─ Step 17 (loops/README.md) ── depends on: 1
├─ Step 18 (README.md count) ── depends on: 1
├─ Step 19 (CONTRIBUTING.md count) ── depends on: 1
├─ Step 20 (test_fsm_fragments.py) ── depends on: 1, 7
├─ Step 21 (CHANGELOG.md) ── depends on: 1
└─ Step 16 (validate + dry-run) ── depends on: 13, 14, 17, 18, 19, 20
```

Steps 15, 17-21 and 13/14 can be done in parallel. Step 16 is the final gate.

## Impact

- **Priority**: P2 — Significant new capability filling a proven gap in the loop catalog; the
  four gaps are well-documented from extensive use of autodev
- **Effort**: Large — ~1,250 lines of new code across YAML (~550 lines), test file (~700 lines,
  12 test classes), plus docs; however, it composes proven patterns from three existing loops
  rather than inventing new primitives
- **Risk**: Medium — New loop, no existing callers to break; risk is in getting the routing logic
  correct (25 states with dimensional token routing). Mitigated by: (a) comprehensive 12-class
  test coverage, (b) dry-run validation, (c) phased rollout plan (dry runs → shadow mode →
  opt-in → default), (d) checkpoint-based failure recovery, (e) non-LLM evaluators paired
  with LLM checks (MR-1) to prevent hallucinated routing
- **Breaking Change**: No — entirely new artifact, no existing APIs modified

## Related Key Documentation

| Document | Relevance | Key Topics |
|---|---|---|
| `docs/ARCHITECTURE.md` | HIGH — Covers loop system design and FSM architecture | Loop catalog structure, FSM execution model, built-in loop conventions |
| `.claude/CLAUDE.md` § Loop Authoring | HIGH — Meta-loop rules govern this implementation | MR-1 (non-LLM evaluator pairing), MR-3 (run_dir isolation), meta-loop design patterns |
| `docs/reference/API.md` | MEDIUM — Loop infrastructure and CLI reference | `ll-loop` CLI, FSM schema, evaluator types, context variable injection |
| `scripts/little_loops/loops/autodev.yaml` | HIGH — Primary reference loop | Queue-driven processing, confidence-check chain, child enqueuing, rate-limit handling, inflight tracking |
| `scripts/little_loops/loops/recursive-refine.yaml` | HIGH — Depth tracking + visited set | Depth-bounded recursion, visited-set file pattern, cycle detection |
| `scripts/little_loops/loops/rn-refine.yaml` | MEDIUM — Convergence pattern | Iterative score comparison, convergence gating, remediation budget (pattern only — dimensions differ) |
| `scripts/little_loops/loops/refine-to-ready-issue.yaml` | MEDIUM — Studied, not used | Refine→wire→confidence linear chain, handshake flag pattern (decided against delegation) |
| `scripts/little_loops/loops/lib/common.yaml` | HIGH — Shared fragments | queue_pop, queue_track, with_rate_limit_handling, retry_counter, numeric_gate, llm_gate, shell_exit |
| `config-schema.json` § commands.confidence_gate | MEDIUM — Config defaults | readiness_threshold (85), outcome_threshold (70 schema / 75 loop override) |
| `docs/guides/LOOPS_GUIDE.md` | LOW — Documentation target | Planning table and autodev section for new rn-implement entry |

## Labels

`loops`, `fsm`, `orchestration`, `recursion`, `planning`

## Session Log
- `/ll:refine-issue` - 2026-06-04T13:29:48 - `76d43d09-72c5-49f1-8090-a12a00a33d40.jsonl`
- `/ll:format-issue` - 2026-06-04T13:15:38 - `bd7f5333-de62-45ce-8686-dca087a872b2.jsonl`
- `/ll:capture-issue` - 2026-06-04T05:36:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e0ae204-dee8-4424-b3cd-529179a61766.jsonl`
- `rn-refine` iteration - 2026-06-04T01:26:14Z - plan improved: added 25-state enumeration, dimensional diagnosis pseudocode, convergence shell script, edge case handling table, operational concerns (phased rollout, failure recovery, monitoring), 16 granular implementation steps with dependency graph, corrected skill/command classification, fixed score field names and threshold defaults, resolved sub-loop delegation decision, clarified rn-refine pattern vs. dimensions distinction
- `/ll:refine-issue --full-rewrite --auto` - 2026-06-04 - codebase research verification: fixed JSON field names (confidence_score→confidence, outcome_confidence→outcome) per show.py:252-253; renamed convergence tokens to compound forms (CONVERGED_PASS/IMPROVED/STALLED) to avoid test_no_bare_pass_token_in_output_contains collision; documented chained-router approach for multi-way output_contains routing (3-way→2 router states, 5-way→4 router states); revised state count 25→31; added Codebase Research Verification subsection with 14 verified claims table, 5 corrections, 3 pattern confirmations; confirmed no --outcome-only flag on check-readiness; set decision_needed: true (2+ implementation options)
- `/ll:wire-issue --auto` - 2026-06-04 - 3-agent wiring research: confirmed auto-discovery (no explicit registration needed); found 5 missing files: loops/README.md (Planning table entry), README.md (loop count 71→72), CONTRIBUTING.md (YAML count 61→62), CHANGELOG.md (new loop entry), test_fsm_fragments.py (migration targets list); added 5 Wiring Phase implementation steps (17-21); confirmed 6 auto-cover tests in test_builtin_loops.py will validate rn-implement automatically
- `/ll:confidence-check` - 2026-06-04T13:45:00Z - `1a8126ae-a53d-43ef-8d42-82478292edad.jsonl`

---

## Status

**Open** | Created: 2026-06-04 | Priority: P2
