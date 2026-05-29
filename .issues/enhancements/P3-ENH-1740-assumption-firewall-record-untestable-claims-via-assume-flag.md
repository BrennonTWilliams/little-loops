---
id: ENH-1740
type: ENH
priority: P3
status: open
captured_at: '2026-05-27T18:08:06Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
relates_to:
- FEAT-1696
- FEAT-1695
- EPIC-1694
parent: EPIC-1694
depends_on: [FEAT-1743]
---

# ENH-1740: `assumption-firewall` — record untestable claims via `--assume` flag

## Summary

Extend `assumption-firewall` so that after extracting API assumptions from an issue file, it classifies each assumption as *testable* (can run a local proof script) or *untestable* (requires live credentials, rate-limited endpoints, long-running behavior, or vendor-only environments), and records untestable ones as structured `untested` TODOs via `/ll:explore-api --assume "<claim>"` rather than silently discarding them.

## Current Behavior

`assumption-firewall` (FEAT-1696) extracts up to 7 external-API assumptions from an issue file via LLM, passes all of them to `ready-to-implement-gate`, which in turn calls `/ll:explore-api` to run a proof script. When an assumption can't be proven — because it requires live API credentials, is rate-limited, or depends on long-running behavior — the proof script fails, the record ends up `refuted`, and the gate blocks the implementation.

This is a false block: the assumption may well be correct, just impossible to prove cheaply in this environment. Today there is no way to record "I believe this is true but can't test it" as a structured TODO that persists with the LT record and gets upgraded later.

The `--assume` flag in `/ll:explore-api` exists precisely for this use case — it adds a claim with `result: untested` to the record — but `assumption-firewall` never invokes it.

## Expected Behavior

After assumption extraction, the firewall classifies each assumption before routing:

- **Testable**: passes to `ready-to-implement-gate` as before.
- **Untestable**: routed to a new `record_untestable` state that calls `/ll:explore-api <target> --assume "<claim>"` for each, creating an LT record with `result: untested` assertions.

The gate then only blocks on *testable* assumptions that are refuted. Untestable assumptions are recorded and pass through.

Downstream, `ll-learning-tests check "<target>"` will show the `untested` assertions, and `learning-tests-audit` (FEAT-1739) will surface them in its "Open TODOs" section, prompting a future developer to resolve them when the environment allows.

## Motivation

- **Eliminates false blocks.** Today a single assumption that requires a live API key blocks the entire gate. After this change, untestable claims are recorded as structured TODOs and the gate passes.
- **Closes the `--assume` loop gap.** The `--assume` flag is documented and implemented, but no built-in loop uses it. This is the natural integration point.
- **Structured TODOs that travel with the record.** An `untested` claim in a LT record is more durable than a comment or a TODO in issue prose — it's machine-readable, survives copy-paste, and gets automatically surfaced by `ll-learning-tests check`.

## Proposed Solution

### New state: `classify_assumptions`

After `parse_assumptions` (which produces `extracted.targets`), add a `classify_assumptions` prompt state that asks the LLM to classify each target as `testable` or `untestable`, emitting:

```json
{
  "testable": ["Stripe webhook signature (Stripe-Signature header)"],
  "untestable": ["Stripe rate limit: 100 req/s per webhook endpoint"],
  "rationale": "Rate-limit claims require a live Stripe account and sustained load."
}
```

Evaluate with `output_json .testable | length >= 0` (always passes — classification itself can't fail).

### New state: `record_untestable`

Shell state that iterates `captured.classified.untestable`:

```bash
python3 << 'PYEOF'
import json, subprocess
classified = json.loads("""${captured.classified.output}""")
for claim in classified.get("untestable", []):
    subprocess.run(["ll-action", "invoke", "explore-api",
                    "--args", f"{claim} --assume {claim!r}"], check=False)
PYEOF
```

Routes unconditionally to `flatten_testable` (even if list is empty).

### Modified `flatten_targets`

Change to read from `classified.testable` instead of `extracted.targets`. If `testable` is empty, route directly to `no_external_deps` (all assumptions were untestable — gate passes trivially).

### Modified routing

```
parse_assumptions → classify_assumptions → record_untestable → flatten_testable → run_gate
                                         ↘ (if testable empty) → no_external_deps
```

### State count delta

+2 states (`classify_assumptions`, `record_untestable`), 1 state renamed (`flatten_targets` → `flatten_testable`). Total: ~9 states.

## Implementation Steps

1. Read `scripts/little_loops/loops/assumption-firewall.yaml` in full.
2. Add `classify_assumptions` prompt state after `parse_assumptions`. Prompt must emit JSON with `testable`, `untestable`, and `rationale` keys. Evaluate `output_json` on `.testable` to confirm structure.
3. Add `record_untestable` shell state: inline Python iterates `classified.untestable`, calls `ll-action invoke explore-api --args "<target> --assume <claim>"` for each.
4. Rename `flatten_targets` to `flatten_testable` and change it to read from `classified.testable`.
5. Add empty-testable branch: if `classified.testable` is empty, route to `no_external_deps`.
6. Update `run_gate` to receive `flatten_testable`'s output.
7. Run `ll-loop validate assumption-firewall` until no ERRORs.
8. Update `scripts/tests/test_builtin_loops.py::TestAssumptionFirewallLoop` — add assertions for the new states.
9. Update `docs/guides/LEARNING_TESTS_GUIDE.md` — note in "Pre-Seeding Assumptions" section that `assumption-firewall` now records untestable claims automatically.

## Acceptance Criteria

- `ll-loop validate assumption-firewall` reports no ERRORs after the change.
- When issue has only untestable assumptions: gate routes `no_external_deps` and each assumption appears as `result: untested` in the corresponding LT record.
- When issue has both testable and untestable assumptions: testable ones go through `ready-to-implement-gate`; untestable ones are recorded as `untested` and do not block.
- When issue has only testable assumptions: behavior is unchanged from FEAT-1696 baseline.
- `TestAssumptionFirewallLoop` passes with updated state assertions.

## Labels

`enh`, `loop`, `learning-tests`, `assumption-firewall`, `assume-flag`, `false-block-fix`

---

**Open** | Created: 2026-05-27 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-27T18:08:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55979bca-15d7-443c-b4d3-a76d29148106.jsonl`
