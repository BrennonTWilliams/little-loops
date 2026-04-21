> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1074, FEAT-1075, FEAT-1076, FEAT-1084]
---

# ENH-1186: Parallel State v1 Scope and Limitations (Consolidated Doc)

## Summary

A single doc-consolidation issue: produce one authoritative page that enumerates what the v1 parallel-state feature does NOT do. Each limitation already appears scattered across FEAT-1075 (Known Limitations), FEAT-1084 (v1 Limitations), FEAT-1076 (Breaking Extension Assumption), and ENH-1073 (orchestrator-specific concerns); collecting them in one place prevents author confusion ("the guide mentions X but not Y; is Y supported?") and gives every follow-up issue a stable anchor to cross-reference.

This is a **docs-only** issue. It does not add or change feature behavior. It is the "read this before you write your first parallel state" page.

## Current Behavior (as of FEAT-1074 / FEAT-1075 / FEAT-1076 / FEAT-1084)

The v1 parallel-state contract has several intentional limitations, currently documented in at least four different places:

- FEAT-1084's `v1 Limitations` section (LOOPS_GUIDE.md + generalized-fsm-loop.md)
- FEAT-1075's `v1 known limitations` bullets in "Blockers & Folded Criteria"
- FEAT-1075's "Event callback worker-tagging" subsection
- FEAT-1076's "Known Limitations / Follow-ups" + "Ctrl-C latency" note
- FEAT-1074's nesting-forbidden rule (in validation rules)
- FEAT-1086's "interceptors skipped on parallel dispatch" note

A new user following `skills/create-loop/` docs plus `docs/guides/LOOPS_GUIDE.md` may or may not land on every one of these depending on entry point. A consolidated page closes that gap.

## Expected Behavior

One page — `docs/reference/parallel-state-v1-scope.md` — organized as "what v1 does" / "what v1 does not do" / "tracked follow-ups" with each "does not do" item linking to the tracking issue. Linked from:

- `docs/guides/LOOPS_GUIDE.md` — the new "Parallel Fan-Out" section's v1 Limitations subsection
- `skills/create-loop/loop-types.md` — the new `## Parallel Fan-Out` section
- `docs/generalized-fsm-loop.md` — the parallel-state chapter
- `.issues/enhancements/P2-ENH-1073-*.md` — orchestrator fan-out (already links this)

## Content Outline

### What v1 does

- Fans out N concurrent sub-loops via `ParallelRunner` (thread mode or worktree mode)
- Routes on aggregate verdict: all-yes → `on_yes`; mixed → `on_partial`; all-non-yes → `on_no`
- Captures per-worker `ParallelItemResult` dicts at `${captured.<state>.results[*]}` in item order
- Structured `ParallelItemError` on failure (`kind`, `message`, `exc_type`) — no string parsing required for downstream routing
- Per-worker timeout (`timeout_seconds`), per-worker context deepcopy when `context_passthrough: true`
- Resumes mid-fan-out when interrupted (per-worker checkpoints — FEAT-1174)
- Cleans up worker-created worktrees/branches deterministically (FEAT-1184)
- `ll-loop simulate` exercises parallel states sequentially through `SimulationActionRunner` (ENH-1164, folded into FEAT-1076)
- `Ctrl-C` cancels pending workers via `ThreadPoolExecutor.shutdown(wait=False, cancel_futures=True)` (ENH-1165 Option B, folded into FEAT-1076)

### What v1 does NOT do

Each bullet below is verbatim-aligned with the in-issue callouts so the two can't drift:

- **Ctrl-C does not stop in-flight workers** — running workers finish their current state before the pool shuts down. A worker running a 20-minute state means ~20-minute Ctrl-C. Full per-worker cancellation via a shared `threading.Event` checked between state transitions is deferred post-v1 (ENH-1165 Option A).
- **No per-worker retries** — `fail_mode` supports `collect` and `fail_fast`; retry-transient and skip-permanent modes are not available. Author-level workaround: route `on_partial` / `on_no` back to the parallel state for a full re-run.
- **No resource-limit enforcement** — no hard cap on `items` count, no cumulative-timeout budget, no worktree-count cap. Tracked in **ENH-1176** (now P2). Soft warning only when running under `ll-parallel` or `ll-sprint --parallel` (FEAT-1080).
- **`context_passthrough` is binary-only** — `true` copies everything, `false` copies nothing. Finer-grained include/exclude filtering and secret-masking are post-v1.
- **Worker events merge without per-worker tag in the programmatic callback stream** — the parent's `event_callback` sees 4×-interleaved events with no worker attribution field. The live CLI display ships a per-worker label for log-tail debuggability (FEAT-1081); structured event tagging for programmatic consumers is tracked in **ENH-1177** (now P2).
- **Thread-mode sub-loop write-safety is not validated** — `isolation: thread` is the default and is fast. Sub-loops that write to shared files in thread mode can corrupt state. Validation-time heuristic warning is tracked in **ENH-1178** (now P2).
- **Nested `parallel:` states are forbidden** — a sub-loop invoked by a `parallel:` state cannot itself contain a `parallel:` state. Authors must decompose or flatten. Enforced at validation time (FEAT-1074).
- **Interceptors are skipped on the parallel dispatch path** — third-party extension interceptors registered via `extension.py:wire_extensions()` do NOT fire around `_execute_parallel_state()`. This mirrors the existing `_execute_sub_loop` early-return behavior but is a silent behavior change for extension authors.
- **Singleton-safety audit ships with v1** but any new module-level singleton added after v1 ships must be re-audited against the FEAT-1075 thread-safety contract. Tracked in **ENH-1185**.

### Tracked follow-ups (one-line pointer per item)

Link each "does not do" bullet to its tracking issue:

- Ctrl-C in-flight cancellation → **.issues/enhancements/P2-ENH-1165-...** (Option A, un-deferred 2026-04-20)
- Per-worker retries → *(no issue yet — create if demand materializes)*
- Resource limits → **.issues/enhancements/P2-ENH-1176-parallel-state-resource-limits.md**
- Fine-grained context passthrough → *(no issue yet)*
- Per-worker event tagging → **.issues/enhancements/P2-ENH-1177-worker-tagged-observability-for-parallel-states.md**
- Thread-mode safety detection → **.issues/enhancements/P2-ENH-1178-thread-mode-isolation-safety-detection.md**
- Singleton-safety audit → **.issues/enhancements/P2-ENH-1185-parallel-state-singleton-thread-safety.md**

## Files to Modify

- `docs/reference/parallel-state-v1-scope.md` — **new file** (this is the consolidated doc)
- `docs/guides/LOOPS_GUIDE.md` — link from the "Parallel Fan-Out" / "v1 Limitations" subsection
- `skills/create-loop/loop-types.md` — link from the `## Parallel Fan-Out` section
- `docs/generalized-fsm-loop.md` — link from the parallel-state chapter's v1 limitations subsection

## Acceptance Criteria

- `docs/reference/parallel-state-v1-scope.md` exists and enumerates every bullet above
- Each "does not do" bullet links to the tracking issue (or says "no issue yet — create if demand materializes")
- LOOPS_GUIDE, create-loop loop-types, and generalized-fsm-loop each have a one-line link to the consolidated doc
- A CI check (or `ll-verify-docs` extension) asserts the link targets exist — broken links fail the docs CI
- Content parity check: the same limitation bullets appear in the consolidated doc AND in the in-issue callouts (grep-based verification OK)

## Impact

- **Priority**: P2 — Source-of-truth scope doc for v1. Must ship in the same release as FEAT-1074/1075/1076, otherwise users land on contradictory limitation callouts scattered across FEAT-1084, FEAT-1075, and loop YAML examples. Re-prioritized 2026-04-20 during parallel-FSM issue-set review.
- **Effort**: Small — writing is straightforward; the bullets already exist verbatim in the other issues.
- **Risk**: Low — additive doc page; no code or behavior change
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `docs`, `scope`, `v1`

## Related / See Also

- **FEAT-1084** — LOOPS_GUIDE v1 Limitations subsection (the canonical source of bullet wording — this doc mirrors, does not paraphrase)
- **FEAT-1075** — runner-module known limitations (structured error, thread-safety contract, event callback tagging)
- **FEAT-1076** — dispatch known limitations (Ctrl-C latency, interceptors skipped)
- **ENH-1073** — orchestrator-level concerns that surface because of v1 limitations
- **ENH-1176 / 1177 / 1178 / 1185** — tracked follow-up issues linked from this doc

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - issue created during parallel-family review to consolidate the v1 "does not do" list into one authoritative doc page. Prevents author confusion from bullet-drift across FEAT-1075/1076/1084/1086 and gives follow-up issues a stable anchor to cross-reference. Docs-only; P3 because it's not a correctness blocker.

---

**Open** | Created: 2026-04-20 | Priority: P2
