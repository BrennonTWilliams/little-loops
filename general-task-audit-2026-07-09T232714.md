# `general-task` Loop Audit — run `2026-07-09T232714`

**Audited:** 2026-07-10 · **Skill:** `/ll:audit-loop-run general-task`
**Run archive:** `.loops/.history/2026-07-09T232714-general-task/` (in the `cards` consumer project)
**Run dir:** `.loops/runs/general-task-20260709T182714/`
**Task input:** `"Implement tableau-redesign.md"`
**Wall clock:** 2026-07-09 23:27:14 → 2026-07-10 04:26:43 UTC (~5h) · **206 iterations**

---

## Verdict: `partial`

The loop reached a terminal state (`failed`) after substantial, verifiable work — **26 of 38 hard DoD criteria satisfied, 61 `src/` files rewritten, build + unit suite (824 tests) green**. It did **not** launder or fabricate success: it ended honestly in `failed` and wrote an accurate, actionable diagnostic. The `failed` verdict was caused by a **loop-design flaw**, not by bad task work: `final_verify` was asked to independently re-verify ~56 criteria (including full `test:coverage` + `test:e2e` runs) inside a single 1800s prompt, timed out, and its only error exit routes straight to the `failed` terminal — discarding all partial credit.

| Dimension | Result |
|---|---|
| Terminal reached | `failed` (`terminated_by: terminal`, `iterations: 206`) |
| Contract (`min_pass_rate: 0.95`) | **Not met** — 26/38 hard criteria = 68.4% |
| Artifacts mutated | **Yes** — 61 `src/` files vs HEAD; build + `npm test` pass |
| Claimed success falsely | **No** — honest `failed` + accurate diagnose paragraph |
| Shallow iteration | `clear` (206 tool calls, 61 aux mutations) |
| Budget exhaustion | Rejected — 206/500 = 41% consumed |
| Rubric drift | N/A — no `llm_structured` evaluators |
| Sub-loop laundering | N/A — no `loop:` states |

---

## Evidence

### Terminal fault — `final_verify` 30-minute timeout

Four action timeouts (`exit_code: 124`), verbatim from `events.jsonl`:

```
{"ts":"...T01:33:01...","exit_code":124,"dur":900000}   → do_work       (15 min, self-retried, non-terminal)
{"ts":"...T02:36:44...","exit_code":124,"dur":900000}   → do_work       (15 min, self-retried, non-terminal)
{"ts":"...T02:51:45...","exit_code":124,"dur":900000}   → do_work       (15 min, self-retried, non-terminal)
{"ts":"...T04:26:00...","exit_code":124,"dur":1800000}  → final_verify  (30 min, TERMINAL)
```

Terminal trace, verbatim:

```
ENTER final_verify  03:55:59
DONE  exit=124 dur=1800000  04:26:00
ENTER diagnose      04:26:00
loop_complete  final_state="failed"  iterations=206  terminated_by="terminal"
```

`final_verify.on_error → diagnose → failed`. A single verify timeout collapses the whole run to `failed`.

### Secondary — convergence spin (03:41–03:55 UTC)

The loop cycled `continue_work → select_step → check_done → count_done(on_no) → continue_work` ~6× with **zero `do_work`** in between (`select_step` returned in ~20ms = `NO_UNCHECKED_STEPS`). Plan steps 19–23 had each hit the `max_step_attempts: 3` cap (per `step-attempts.txt`) and were abandoned. Each `continue_work` burned 50–210s of LLM time producing no new actionable plan step. `continue_work` finally returned `on_yes → final_verify` — self-assessing "done" despite 12 open hard criteria; `final_verify` was the honest gate that would have caught the overclaim, but it timed out.

### DoD state: 26/38 hard criteria verified (68.4%)

Open hard criteria at termination (from `dod.md`):

- **Phase 3 CSS** — `global.css` still carries ~114 legacy class hits (`#hand`, `.shelf-row`, `.ghost-slot`, etc.); BEM rename incomplete.
- **Phase 6 E2E** — `e2e/fixtures/forty-card-tableau.json` never created; `legibility-budget.spec.ts` + `density-visual.spec.ts` blocked by the fixture bug below.
- **Phase 7 gates** — `test:coverage` 61.44/49.43/67.8/63.3 vs 70/55/75/70 (all four missed); `test:e2e` exits 1 before any test runs (`gate-1-deal-test.spec.ts` imports non-existent `src/data/verbs`).
- **Phase 8 closeout** — all 7 criteria untouched (Table/Garden deletion, CardView scrub, slice-export verification, `depcheck`, tsconfig/CLAUDE.md/MEMORY.md updates, phased PR).

The loop's own `diagnose` output named every one of these accurately, including the fixture bug: *"`buildFortyCardFixture()` produces 44 landed cards (1 center + 4 strand heads + 24 around + 8 for + 8 against) but asserts `landedCount === 40` at `src/canvas/fortyCardFixture.ts:149`."*

---

## Recommendations (ranked) — target the `general-task` FSM

> These are loop-definition fixes for the `general-task` FSM YAML in this repo, **not** the cards consumer project.

### 1. [structural] `final_verify` timeout must not forfeit partial progress
`final_verify.on_error → diagnose → failed` discards a run that had 26/38 hard criteria done. Route to the already-existing but never-reached `summarize_partial`:

```yaml
states:
  final_verify:
-   on_error: diagnose
+   on_error: summarize_partial   # preserve partial credit instead of collapsing to failed
```

### 2. [state] Decompose `final_verify` — one 30-min prompt cannot re-verify ~56 criteria + run coverage + e2e
Split verification per-phase (or per-criterion), each with its own bounded timeout, so one slow gate cannot forfeit the run. This is the root cause of *this* run's `failed` verdict: the verification surface (38 hard criteria + full `test:coverage` + full `test:e2e`) is far larger than one 1800s prompt can complete.

### 3. [state] Guard the `continue_work` convergence spin
When `select_step` returns `NO_UNCHECKED_STEPS` **and** `continue_work` emits no new `- [ ]` step, it re-deliberates for minutes with no progress. Add a stall counter: after N no-progress `continue_work` cycles, route to `summarize_partial` (a `diff_stall`-style guard) rather than looping until abandoned steps pile up and `final_verify` fires.

### 4. [state] Cap `do_work` timeout self-retries
`do_work.on_error → do_work` self-retried 3 × 15 min (~45 min) on timeout, with no attempt cap on the *timeout* path (distinct from `max_step_attempts`, which only governs the verify path). Add a timeout-retry budget that routes to `diagnose` / `summarize_partial` after K timeouts.

### Task-level (not loop) — operator must fix on the `refactor/tableau-third-revision` branch
These were correctly reported by the loop and are not FSM defects:
- `buildFortyCardFixture()` yields 44 landed cards but asserts 40 (`src/canvas/fortyCardFixture.ts:149`) — trim to 40 or update the assertion / restore the JSON fixture.
- `e2e/gate-1-deal-test.spec.ts` (and gate-2) import non-existent `src/data/verbs` — point at a real module or stub it.
- Coverage top-ups needed for `DragContext.tsx`, `llm/play.ts`, `tableGeometry.ts`, `useDensity.ts`, `ResolutionDialog.tsx`, `SettingsSheet.tsx`.
- Entire Phase 8 closeout is unstarted — on re-run, narrow the task description (e.g. "finish Step 23 + Step 28" or "execute Phase 8 closeout") rather than re-issuing the full plan.

---

## Method notes
- Pre-flight gate passed: `events.jsonl` (4181 lines) + `state.json` present and non-empty.
- FSM: 20 states, `max_steps: 500`, evaluators all mechanical (`output_contains`/`output_json`/`exit_code`).
- No `summary.json` written by this run (loop has no summary emitter on the `failed` path — see Recommendation 1).
- Dedup: `grep -rl "general-task" .issues/**` in the cards project → no existing issues reference this loop.
