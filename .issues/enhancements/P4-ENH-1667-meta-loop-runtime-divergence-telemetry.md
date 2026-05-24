---
id: ENH-1667
type: ENH
status: open
priority: P4
discovered_date: 2026-05-23
discovered_by: manual
labels: [telemetry, loops, meta-loop, harness, shor, observability, follow-up]
parent: EPIC-1663
relates_to: [ENH-1665, ENH-1670]
depends_on: [ENH-1665]
---

# ENH-1667: Meta-loop runtime divergence telemetry (follow-up)

## Summary

Add runtime telemetry to the FSM executor so that when a meta-loop runs an
`llm_structured` evaluator paired with a non-LLM evaluator (per ENH-1665
MR-1), both verdicts and the iteration's diff stats are logged to
`.loops/runs/<name>/meta-eval.jsonl`. This data lets `loop-specialist` audit
for systematic LLM-vs-deterministic divergence over time — the runtime
analog of SHOR §3 Analysis III.

This is the **follow-up** layer of EPIC-1663, explicitly out of scope for
the first three children. Decoupled because it requires touching the
executor (more risk) and the value is observational, not preventative.

## Motivation

ENH-1665's MR-1 catches *absence* of a non-LLM gate. It does NOT catch the
adjacent failure mode: a non-LLM gate that's tuned so loosely it never
fires (e.g., `diff_stall` with `max_stall: 50` in a 30-iteration loop).
The validator can't tell whether a gate is meaningfully gating without
runtime data.

SHOR Analysis III shows optimizers self-evaluate at 33–55% accuracy. If
the LLM judge says YES on every iteration while the non-LLM gate also
trivially passes, the loop will commit drift indistinguishable from
progress. Logging both verdicts per iteration gives `loop-specialist`
the evidence to flag this pattern.

## Telemetry Schema

For meta-loops (as detected by the ENH-1665 heuristic), append one JSONL
entry per iteration to `.loops/runs/<name>/meta-eval.jsonl`:

```json
{
  "iteration": 7,
  "ts": "2026-05-24T03:14:15Z",
  "loop": "harness-optimize",
  "state": "check_semantic",
  "llm_verdict": "yes",
  "llm_rationale": "<truncated to 200 chars>",
  "external_verdict": "no",
  "external_state": "gate",
  "external_evaluator": "convergence",
  "external_value": "0.82",
  "external_target": "0.85",
  "diff_stats": {
    "files_changed": 1,
    "insertions": 4,
    "deletions": 2
  },
  "agreed": false
}
```

`agreed` is the boolean LLM-and-external-agree signal. The
`loop-specialist` agent can grep this file for long streaks of
`agreed: false` (LLM optimistic while scorer says no progress) or
`agreed: true` with `diff_stats.files_changed == 0` (both passing
trivially — possible self-eval drift).

## Implementation Steps

1. **`scripts/little_loops/fsm/executor.py`**: When transitioning out of an
   `llm_structured` state in a loop where `_is_meta_loop()` returns true,
   capture (a) the LLM verdict + rationale, (b) the next non-LLM
   evaluator's verdict + value (look ahead one transition), (c) `git diff
   --stat HEAD` output. Write the JSONL entry to
   `.loops/runs/<run-id>/meta-eval.jsonl`.
2. **`agents/loop-specialist.md`**: Add a new section "Auditing meta-loop
   telemetry" describing how to read `meta-eval.jsonl` and the two
   divergence patterns to look for (LLM optimistic vs trivial agreement).
   Add new failure-mode entry `evaluator-trivial` for the "both pass but
   nothing changed" pattern.
3. **`scripts/little_loops/cli/loop/__init__.py`**: Add subcommand
   `ll-loop audit-meta <name>` that reads the JSONL and prints a summary
   table: total iterations, agreement rate, mean diff size per verdict,
   and a flag if any divergence pattern crosses a threshold.
4. **Tests**: Smoke test that running `harness-optimize` on a tiny scorer
   produces the expected JSONL entries with the right fields.

## Verification

- Running any meta-loop produces `.loops/runs/<run-id>/meta-eval.jsonl`
  with one entry per iteration that hits an `llm_structured` state.
- `ll-loop audit-meta <name>` summarizes the file correctly.
- Non-meta loops do NOT produce the file (no overhead for
  data-operating loops).

## Scope Boundaries

**In scope:**
- Executor instrumentation gated on meta-loop detection
- JSONL schema and writer
- `loop-specialist` agent doc update + new failure-mode entry
- New `ll-loop audit-meta` summary subcommand

**Out of scope:**
- Automatic enforcement (e.g., killing a loop when divergence is detected)
  — telemetry only; humans / `loop-specialist` interpret it.
- Multi-judge ensembling, second-opinion LLMs, or any change to which
  evaluators run.
- Backfilling telemetry for past runs.

## Impact

- **Priority**: P4 — follow-up; ENH-1665 captures the primary value.
  Useful once meta-loops are widespread enough that divergence data
  becomes worth auditing.
- **Effort**: Medium — executor changes carry more risk than validator/wizard work.
- **Risk**: Medium — touches the hot path of the FSM executor; gated on the
  meta-loop detector to avoid overhead on normal loops.
- **Breaking Change**: No — purely additive observability.
- **Depends on**: ENH-1665 (uses the same `_is_meta_loop()` detector;
  no point logging until the design rule is enforced).

## Open Questions

- Should `meta_self_eval_ok: true` loops still produce telemetry? Lean YES
  — the flag suppresses the *validator*, but observability is still useful.
- What's the retention policy for `meta-eval.jsonl`? Likely defer to the
  same retention as `.loops/runs/` itself; document in `cleanup-loops`.
- Is the diff capture per state worth the `git diff` cost on every
  meta-loop iteration? Possibly cache last `git rev-parse HEAD` and only
  diff when it has changed.

## Related Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/fsm/executor.py` | Instrumentation site |
| `agents/loop-specialist.md:52–63` | Failure-mode taxonomy — add `evaluator-trivial` |
| `docs/research/Towards-Direct-Evaluation-of-Harness-Optimizers.md` | SHOR §3 Analysis III — accuracy gap |

## Labels

- telemetry
- loops
- meta-loop
- harness
- shor
- observability
- follow-up

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The artifact path `.loops/runs/<name>/meta-eval.jsonl` used here should be confirmed against ENH-1670's artifact convention (`.loops/.running/{instance_id}.log`). Both issues define per-run observability artifact conventions independently — align on a shared directory policy before both land to prevent convention drift.


## Verification Notes

_Verified 2026-05-24 by `/ll:verify-issues`:_ Soft-blocked on ENH-1665. The
proposed instrumentation gates on `_is_meta_loop()` in
`scripts/little_loops/fsm/executor.py`, which does not yet exist (grep found
zero matches). This is consistent with the declared `depends_on: [ENH-1665]`
— the detector is owned by ENH-1665 and must land first. Once it exists,
re-verify the exact detector signature and the executor instrumentation
site (currently described conceptually, not anchored to a line).

## Session Log
- `/ll:verify-issues` - 2026-05-24T07:01:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08ba673b-967b-4af4-a548-692288b5485d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
