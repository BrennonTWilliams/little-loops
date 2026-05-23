---
captured_at: "2026-05-23T16:40:11Z"
discovered_date: 2026-05-23
discovered_by: capture-issue
status: open
---

# ENH-1629: Add explicit success-threshold keys to general-task loop context

## Summary

The `general-task` loop currently treats the Definition of Done (DoD) file as an implicit contract — success is decided by LLM judgment over the DoD markdown, with no machine-readable thresholds. Adding explicit keys such as `target_pass_rate` and `min_per_category` to `context:` would make the success contract machine-auditable and would give `check_done` (and any future evaluators) a concrete target to compare against.

## Current Behavior

`scripts/little_loops/loops/general-task.yaml` `context:` block carries only the free-form `input:` value plus the DoD path. The `check_done` LLM evaluator reads the DoD markdown and renders a subjective pass/fail with no numeric bar. In the `2026-05-23T113819` run, 10/18 criteria passed (56%) and the evaluator had no defined threshold to compare against, so the loop iterated until `max_iterations` rather than terminating on a deterministic gate.

## Expected Behavior

The `general-task.yaml` `context:` block exposes explicit success thresholds (`target_pass_rate`, `min_per_category`) that:

- The `check_done` prompt interpolates so the LLM is told the exact pass bar.
- `/ll:audit-loop-run` and other tooling can read to report objective progress.
- Operators can override per run without editing the loop YAML.

A run completing 18/18 DoD criteria at `target_pass_rate: 1.0` terminates with `success`; a run that plateaus below the threshold can be flagged failure deterministically.

## Motivation

In a recent partial run (`2026-05-23T113819`, 100 iterations, terminated by `max_iterations`), 10/18 DoD criteria passed (56%) — but the loop had no machine-readable notion of what pass rate constitutes success, so the `check_done` LLM evaluator could neither confidently terminate nor confidently flag failure. Explicit thresholds would:

- Let `check_done` (or a shell sibling) compute a deterministic pass/fail against `target_pass_rate`.
- Let auditing tools (`/ll:audit-loop-run`) report objective progress against a stated bar rather than relative to LLM-rendered impressions.
- Make the contract visible to operators at loop-definition time rather than buried in DoD prose.

This complements [[BUG-1628]] (plan-exhaustion deadlock): even with the replan branch in place, the loop still needs a clear success bar to decide *when* replanning has done enough.

## Proposed Solution

Extend the `context:` block in `scripts/little_loops/loops/general-task.yaml`:

```yaml
context:
  input: "..."
  target_pass_rate: 1.0      # fraction of DoD criteria that must be [x]
  min_per_category: 1        # if DoD is grouped, minimum [x] per group
```

Then either:

1. **Phase 1 (no runtime changes)** — interpolate the thresholds into the `check_done` prompt so the LLM is told the bar explicitly (`"Pass only if ≥${context.target_pass_rate} of criteria are marked [x]."`).
2. **Phase 2 (optional, runtime-supported)** — add a shell evaluator that parses the DoD file and compares the `[x]` count against `target_pass_rate * total`, removing LLM judgment from the gate entirely (precedent: `dead-code-cleanup.yaml`'s `count_findings` state).

## Acceptance Criteria

- [ ] `general-task.yaml` `context:` block defines `target_pass_rate` and `min_per_category` (with documented defaults).
- [ ] `check_done` prompt is updated to reference `${context.target_pass_rate}` (and `${context.min_per_category}` if grouped DoDs are supported).
- [ ] `docs/guides/LOOPS_GUIDE.md` general-task section documents the new context keys and how to override them per run.
- [ ] Optional: a shell-evaluator variant of `check_done` lands behind a flag or as a second loop variant.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — add threshold keys to `context:` and reference them from the `check_done` prompt.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/` context interpolation paths — verify `${context.target_pass_rate}` resolves through the same path as existing `${context.input}`.

### Similar Patterns
- `scripts/little_loops/loops/dead-code-cleanup.yaml` — precedent for a shell evaluator state (`count_findings`) producing a deterministic gate, relevant for Phase 2.

### Tests
- TBD — add an `ll-loop validate` smoke test or fixture asserting the new keys are accepted; integration test that `check_done` receives the interpolated values.

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — document the new context keys and per-run override mechanism.

### Configuration
- N/A — no `.ll/ll-config.json` keys required; thresholds live in the loop YAML.

## Implementation Steps

1. Add `target_pass_rate` and `min_per_category` keys (with sensible defaults) to the `context:` block of `general-task.yaml`.
2. Update the `check_done` prompt template to interpolate `${context.target_pass_rate}` (and conditionally `${context.min_per_category}`).
3. Update `docs/guides/LOOPS_GUIDE.md` general-task section with key descriptions and override examples.
4. (Phase 2, optional) Prototype a shell-evaluator variant modeled on `dead-code-cleanup.yaml`'s `count_findings` and gate it behind a separate state/loop variant.
5. Verify with a short `ll-loop run general-task` invocation that the interpolated thresholds reach the evaluator prompt.

## Scope Boundaries

- **In scope**: Adding declarative threshold keys to `general-task.yaml` `context:` and wiring them into the `check_done` prompt (Phase 1).
- **Out of scope**: Replacing the LLM `check_done` evaluator with a deterministic shell evaluator (tracked as optional Phase 2 in Proposed Solution).
- **Out of scope**: Generalizing thresholds to every loop in `scripts/little_loops/loops/` — this issue is scoped to `general-task` only.
- **Out of scope**: Schema changes to the FSM runtime itself; this is a loop-YAML and prompt change only.

## Success Metrics

- A `general-task` run hitting `target_pass_rate` terminates via `check_done` rather than `max_iterations`.
- `/ll:audit-loop-run` output can quote the configured `target_pass_rate` alongside the observed pass rate.
- Operators can override the threshold for a single run without editing the loop YAML.

## Impact

- **Priority**: P3 — quality-of-life improvement to loop observability; complements but does not block [[BUG-1628]].
- **Effort**: Small — YAML key additions plus a prompt-string change; documentation update.
- **Risk**: Low — additive change with backward-compatible defaults (existing runs continue to work if thresholds default to current implicit behavior).
- **Breaking Change**: No

## Source

`general-task-audit-proposals.md` (Proposal 2) — derived from a partial run audit on 2026-05-23. The proposals file is a transient working doc; the durable record lives here and in [[BUG-1628]].

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `general-task`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-23T16:43:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7684c915-f5a2-4b68-9ba1-d56622191296.jsonl`
- `/ll:capture-issue` - 2026-05-23T16:40:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P3
