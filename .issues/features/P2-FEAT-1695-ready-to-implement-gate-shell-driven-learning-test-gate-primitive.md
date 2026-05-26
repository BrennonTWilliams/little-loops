---
id: FEAT-1695
type: FEAT
priority: P2
status: open
captured_at: '2026-05-25T20:53:43Z'
discovered_date: '2026-05-25'
discovered_by: capture-issue
parent: EPIC-1694
relates_to: [EPIC-1694, FEAT-1283, FEAT-1287, FEAT-1285, FEAT-1286, FEAT-1696, FEAT-1692, FEAT-1697]
---

# FEAT-1695: `ready-to-implement-gate` — shell-driven Learning-Test gate primitive

## Summary

Add `scripts/little_loops/loops/ready-to-implement-gate.yaml` — a 5-state shell-driven FSM loop that mirrors `type: learning` semantics but accepts a **dynamic** comma-separated `targets` context variable. Iterates the list, checks each target via `ll-learning-tests check`, invokes `/ll:explore-api` (up to `max_retries`) when a target is missing, and routes to terminal `done` (all proven) or `blocked` (any refuted or exhausted). Designed to be called as a sub-loop from any parent that needs proof-before-codegen on a runtime-computed target list.

## Current Behavior

`type: learning` (FEAT-1283) is the canonical state for "prove a list of external-API surfaces before proceeding," but its target list is loaded once at YAML parse via `from_dict()` in `scripts/little_loops/fsm/schema.py:271–305` and is never re-interpolated against `${context.*}` or `${captured.*.output}`. This means any caller that builds a target list at runtime — extracting from an issue, scraping from docs, enumerating from code — cannot use `type: learning` directly.

Callers today either:
- Hard-code targets in the YAML (loses the dynamic case entirely), or
- Shell-drive against the registry ad-hoc, with no shared contract for `proven` / `refuted` / `exhausted` outcomes.

There is no reusable primitive that takes "a list of targets I computed at runtime" and returns a clean two-way `done` / `blocked` exit.

## Expected Behavior

Sub-loop invocation:

```yaml
my_gate_step:
  loop: ready-to-implement-gate
  with:
    targets: "${captured.computed_targets.output}"   # comma-separated string
    max_retries: "2"
  on_success: proceed_with_implementation            # all targets proven
  on_failure: block_with_diagnosis                   # at least one refuted/exhausted
```

CLI invocation (for testing / direct use):

```bash
ll-loop run ready-to-implement-gate \
  --context targets="anthropic streaming, anthropic tool_use shape" \
  --context max_retries="2"
```

Outcomes:
- **All targets `proven`** → terminal `done`
- **Any target `refuted`** → terminal `blocked` (immediate exit; no further targets checked)
- **Any target `exhausted`** (`/ll:explore-api` ran `max_retries` times without producing a `proven` or `refuted` record) → terminal `blocked`
- **Empty target list** → terminal `done` (no-op pass)

## Motivation

- **Unblocks the four-loop stack (EPIC-1694).** `assumption-firewall`, `integrate-sdk`, and `adopt-third-party-api` all need to gate a *computed* target list. Without this primitive each would reinvent the queue / check / explore / advance state machine independently.
- **One shared proof contract.** The loop's `done`/`blocked` terminals give callers a stable two-way exit via `on_success`/`on_failure`. Future loops that want a proof gate can drop this in without rebuilding the contract.
- **Discovered constraint, not a workaround.** The shell-driven design isn't a hack around `type: learning`; it's the consequence of `LearningConfig.targets` being a parse-time list. A future enhancement to `type: learning` that supports interpolation could collapse this loop into a thin wrapper, but the contract — comma-separated input, two-terminal output — is the part worth standardizing now.
- **Validates the registry's "structural gate" framing.** Today the registry is opt-in for agents. Shipping a primitive that *parents* enforce makes the gate structural rather than aspirational.

## Use Case

A parent loop has just extracted three external-API assumptions from an issue's body: `["Stripe customer.subscription.updated webhook shape", "Stripe idempotency-key header semantics", "Stripe rate-limit header parsing"]`. It needs to know — before letting any implementation code be written — whether each of these is `proven` in the registry, and if not, whether `/ll:explore-api` can prove or refute them.

The parent flattens the list to a comma-separated string, calls `ready-to-implement-gate` as a sub-loop with `targets: "Stripe ...webhook shape, Stripe idempotency-key..., Stripe rate-limit..."` and `max_retries: "2"`. The gate:

1. Parses the list (`parse_targets` state) → 3 items queued.
2. Pops the head, runs `ll-learning-tests check "Stripe customer.subscription.updated webhook shape"` (`check_next` state).
3. If `proven` → advances queue. If `refuted` → terminal `blocked`. If missing/`stale` → routes to `explore`.
4. `explore` state runs `/ll:explore-api "<target>"` up to `max_retries` times, re-checks status between attempts; first `proven`/`refuted` resolves the target. Exhaustion → terminal `blocked`.
5. Loops until queue empty → terminal `done`.

The parent receives a clean `on_success` (proceed to scaffold) or `on_failure` (block with diagnosis). It never has to reimplement the queue management or the retry semantics.

## Proposed Solution

Five states + two terminals; uses captured-variable interpolation and `output_json` evaluators throughout. Source:`~/.claude/plans/proceed-with-creating-all-indexed-bumblebee.md` (full YAML reproduced below).

```yaml
name: ready-to-implement-gate
category: gate
description: Sub-loop that proves a list of external-API targets via ll-learning-tests; routes done if all proven, blocked if any refuted.
initial: parse_targets
max_iterations: 50          # generous for many-target lists with re-exploration
timeout: 3600
on_handoff: spawn

context:
  targets: ""               # comma-separated; required
  max_retries: "2"          # per-target /ll:explore-api retries

states:
  parse_targets:
    action: |
      python3 - <<'PY'
      import json, os
      raw = os.environ.get("LL_CONTEXT_TARGETS","").strip()
      items = [t.strip() for t in raw.split(",") if t.strip()]
      print(json.dumps({"queue": items, "remaining": len(items), "refuted": []}))
      PY
    action_type: shell
    capture: state
    evaluate:
      type: output_json
      path: ".remaining"
      operator: gt
      target: 0
    on_yes: check_next
    on_no: done              # empty target list is a no-op pass

  check_next:
    # Pop the head of the queue, query the registry, decide what to do.
    action: |
      python3 - <<'PY'
      import json, subprocess, sys
      state = json.loads("""${captured.state.output}""")
      target = state["queue"][0]
      r = subprocess.run(["ll-learning-tests","check",target], capture_output=True, text=True)
      record = json.loads(r.stdout) if r.returncode == 0 else None
      status = (record or {}).get("status")  # proven|refuted|stale|None
      verdict = "proven" if status == "proven" else ("refuted" if status == "refuted" else "needs_explore")
      print(json.dumps({"target": target, "verdict": verdict, "queue": state["queue"], "refuted": state["refuted"]}))
      PY
    action_type: shell
    capture: probe
    evaluate:
      type: output_json
      path: ".verdict"
      operator: eq
      target: "proven"
    on_yes: advance_queue
    on_no: branch_on_verdict

  branch_on_verdict:
    action: echo "${captured.probe.output}"
    action_type: shell
    evaluate:
      type: output_json
      path: ".verdict"
      operator: eq
      target: "refuted"
    on_yes: blocked          # refuted → terminal
    on_no: explore           # needs_explore → run /ll:explore-api with retries

  explore:
    # Up to context.max_retries attempts of /ll:explore-api, re-check between.
    action: |
      TARGET=$(echo '${captured.probe.output}' | python3 -c "import sys,json;print(json.load(sys.stdin)['target'])")
      MAX=${context.max_retries}
      for i in $(seq 1 $MAX); do
        /ll:explore-api "$TARGET" || true
        STATUS=$(ll-learning-tests check "$TARGET" 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('status',''))" 2>/dev/null || echo "")
        if [ "$STATUS" = "proven" ]; then echo "RESULT=proven"; exit 0; fi
        if [ "$STATUS" = "refuted" ]; then echo "RESULT=refuted"; exit 0; fi
      done
      echo "RESULT=exhausted"
    action_type: shell
    capture: explore_result
    evaluate:
      type: output_contains
      pattern: "RESULT=proven"
    on_yes: advance_queue
    on_no: blocked            # refuted or exhausted both → blocked

  advance_queue:
    action: |
      python3 - <<'PY'
      import json
      probe = json.loads("""${captured.probe.output}""")
      queue = probe["queue"][1:]
      print(json.dumps({"queue": queue, "remaining": len(queue), "refuted": probe["refuted"]}))
      PY
    action_type: shell
    capture: state
    evaluate:
      type: output_json
      path: ".remaining"
      operator: gt
      target: 0
    on_yes: check_next         # more targets → loop
    on_no: done

  done:
    terminal: true

  blocked:
    terminal: true
```

### Design notes

- The `explore` step replaces what `type: learning` does internally — same retry contract (`max_retries`), same outcomes (`proven`/`refuted`/`exhausted`), but the target is read from captured state instead of a static YAML list.
- Captured-variable interpolation pattern (`${captured.<state>.output}`) is established; reference: `scripts/little_loops/loops/eval-driven-development.yaml:49`.
- Two terminal states give the parent loop a clean two-way exit via `on_success` (mapped from `done`) and `on_failure` (mapped from `blocked`) when called as a sub-loop.

### Meta-loop compliance (CLAUDE.md § Loop Authoring)

This loop **does not modify harness artifacts** — it queries the registry and runs `/ll:explore-api`, which writes `.ll/learning-tests/*.md` (data, not harness config). It is not a meta-loop; rule MR-1 does not apply. All evaluators are non-LLM (`output_json`, `output_contains`) by construction.

## API/Interface

**Context variables (sub-loop inputs):**

| Variable | Type | Required | Description |
|---|---|---|---|
| `targets` | string | yes | Comma-separated list of target descriptions; whitespace around commas is trimmed |
| `max_retries` | string (int-coerced) | no (default `"2"`) | Per-target `/ll:explore-api` retry budget |

**Terminal states:**

- `done` — every target in `targets` resolved to `proven`; parent should route via `on_success`
- `blocked` — at least one target resolved to `refuted` or exhausted `max_retries`; parent should route via `on_failure`

**Sub-loop binding (caller side):**

```yaml
my_gate_step:
  loop: ready-to-implement-gate
  with:
    targets: "${captured.computed_targets.output}"
    max_retries: "2"
  on_success: <next-state>
  on_failure: <block-state>
```

Reference pattern: `scripts/little_loops/loops/outer-loop-eval.yaml:55–63` (explicit `with:` binding to a *captured* value).

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — **new** (the loop)
- `scripts/tests/test_builtin_loops.py` — add `"ready-to-implement-gate"` to the `expected` set in `test_expected_loops_exist` (lines ~66–80)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/learning_tests.py:44–92` — `ll-learning-tests check <target>` (exit 0 + JSON when proven/refuted/stale exists, exit 1 when missing); the gate depends on this exact contract
- `skills/explore-api/SKILL.md` — `/ll:explore-api <target>`; the gate depends on this writing a `.ll/learning-tests/*.md` record on success
- `scripts/little_loops/fsm/evaluators.py:217–271` — `output_json` evaluator (dot-path + `eq|ne|lt|le|gt|ge` operators)
- `scripts/little_loops/fsm/schema.py` — captured-variable interpolation (`${captured.<state>.output}`) and `output_contains` evaluator

### Similar Patterns

- `scripts/little_loops/loops/eval-driven-development.yaml:49` — `${captured.<state>.output}` interpolation
- `scripts/little_loops/loops/outer-loop-eval.yaml:55–63` — sub-loop with explicit `with:` binding to a captured value
- `scripts/tests/fixtures/fsm/learning-state-loop.yaml` — `type: learning` reference (the semantics this loop reproduces dynamically)

### Tests

- `scripts/tests/test_builtin_loops.py` — update `test_expected_loops_exist` to include `"ready-to-implement-gate"`
- Manual smoke: `ll-loop test ready-to-implement-gate --context targets="nonexistent-target-xyz" --context max_retries="0"` should advance from `parse_targets` to `check_next` to `branch_on_verdict` to `explore` to `blocked`
- End-to-end (proven target): `ll-learning-tests list | jq -r '.[0].target' | xargs -I{} ll-loop run ready-to-implement-gate --context targets="{}"` must reach `done` in one iteration without invoking `/ll:explore-api` (verifiable via `ll-loop history`)
- End-to-end (missing target): `ll-loop run ready-to-implement-gate --context targets="Python json.dumps default" --context max_retries="1"` must invoke `/ll:explore-api` once and route to `done` or `blocked` based on outcome

### Documentation

- `LOOPS_GUIDE.md` — follow-up doc pass after the four loops have shipped (out of scope for this issue per EPIC-1694)
- `LEARNING_TESTS_GUIDE.md` — same

### Configuration

- N/A — no new config keys

## Implementation Steps

1. **Draft `scripts/little_loops/loops/ready-to-implement-gate.yaml`** using the YAML above verbatim as the starting point.
2. **Run `ll-loop validate ready-to-implement-gate`** and iterate until no ERRORs. Meta-loop rule MR-1 does not apply (no LLM evaluators); other validation should pass cleanly.
3. **Update `scripts/tests/test_builtin_loops.py`** to add `"ready-to-implement-gate"` to the `expected` set in `test_expected_loops_exist`.
4. **Run the test:** `python -m pytest scripts/tests/test_builtin_loops.py::test_expected_loops_exist -v`.
5. **Smoke test the empty-list pass:** `ll-loop run ready-to-implement-gate --context targets=""` — should reach `done` immediately.
6. **Smoke test the proven path:** pick an existing proven LT record (`ll-learning-tests list | jq -r '.[0].target'`) and run the gate against it. Verify via `ll-loop history` that no `/ll:explore-api` invocation occurred.
7. **Smoke test the explore path:** pick a deliberately-missing target and run with `max_retries=1`. Verify `/ll:explore-api` was invoked once and the loop routed to either `done` or `blocked`.
8. **Smoke test the refute path:** if a refuted LT record exists, run the gate against it. Should reach `blocked` without invoking `/ll:explore-api`.
9. **Smoke test the multi-target path:** comma-separated list mixing proven, missing, and (if available) refuted targets. Verify iteration order and early-exit on refute.
10. **Confirm discovery:** `ll-loop list | grep ready-to-implement-gate` returns one match.

## Acceptance Criteria

- `scripts/little_loops/loops/ready-to-implement-gate.yaml` exists and `ll-loop validate ready-to-implement-gate` reports no ERRORs.
- `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` passes with the new loop name in the `expected` set.
- `ll-loop list` surfaces `ready-to-implement-gate`.
- Empty target list (`targets=""`) reaches terminal `done` in one iteration.
- Already-proven target reaches terminal `done` in one iteration without invoking `/ll:explore-api` (verifiable via `ll-loop history`).
- Missing target with `max_retries=1` invokes `/ll:explore-api` exactly once and routes to `done` or `blocked` based on the resulting registry status.
- Refuted target reaches terminal `blocked` without invoking `/ll:explore-api`.
- Multi-target list with a `refuted` target early-exits to `blocked` without checking subsequent targets.
- Sub-loop invocation from a parent (smoke-tested via `assumption-firewall` once FEAT-1696 ships) routes cleanly through `on_success` / `on_failure`.

## Impact

- **Priority**: P2 — Blocks the other three loops in EPIC-1694. The gate is the load-bearing primitive; FEAT-1696, FEAT-1692, FEAT-1697 all consume it. Higher than the children's P3 because of the dependency.
- **Effort**: Small-Medium — One YAML, one test edit, no Python code. The hard parts are the embedded `python3 - <<'PY'` blocks (queue state management) and the `explore` shell loop (retry semantics). Both are mechanical translations of the design above.
- **Risk**: Low — New isolated loop; touches no existing automation. The `output_json` evaluator and `${captured.*.output}` interpolation are well-exercised patterns. The only novelty is shell-driving the explore loop, which is bounded by `max_retries`.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loop`, `learning-tests`, `fsm`, `gate-primitive`, `sub-loop`, `captured`

---

**Open** | Created: 2026-05-25 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-05-25T20:53:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/810cf8d1-477c-42da-bb20-b577b2ee3ad9.jsonl`
