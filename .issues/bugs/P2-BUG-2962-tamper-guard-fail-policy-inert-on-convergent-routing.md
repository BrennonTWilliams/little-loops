---
id: BUG-2962
title: tamper_guard fail policy is inert on convergent routing and clobbers its own evidence
type: BUG
priority: P2
status: open
discovered_date: 2026-07-31
discovered_by: manual
blocks:
- ENH-2958
relates_to:
- ENH-2934
- ENH-2958
- BUG-2954
---

# BUG-2962: tamper_guard `fail` policy is inert on convergent routing and clobbers its own evidence

## Summary

The FSM tamper guard (ENH-2934) detects tampering correctly but cannot enforce
it on any state whose `on_yes`/`on_no`/`on_error` converge to the same
successor. Its sole enforcement mechanism is a verdict flip, which is a no-op
under convergent routing. Separately, the per-state evidence key is
unconditionally overwritten, so a later guarded state erases an earlier
finding before anything can consume it.

Found while enabling `tamper_guard: fail` on `oracles/code-run-gate.yaml` — the
FSM path's actual post-implement verification step — as the prerequisite
ENH-2958 proposed.

## Current Behavior

Verified end-to-end against a scratch git repo whose `project.test_cmd`
rewrites a test file mid-run (`assert 1 == 1` → `assert 1 != 2`, a
count-preserving tamper BUG-2954's heuristic cannot catch):

```
final_state: done   failure_terminal: False
run_tamper_guard calls: 6
   policy=fail passed=True  findings=[]
   policy=fail passed=False findings=[('tests/test_x.py', 'modified')]   <-- run_test
   policy=fail passed=True  findings=[]   (x4 trailing SKIP states)
```

The guard fires and detects the mutation byte-exact. The oracle still emits
`GATE_PASS` and the loop terminates `done`.

Two independent causes:

1. **Verdict flip is a no-op under convergent routing.**
   `fsm/executor.py:1469-1474` enforces via
   `forced_verdict = "no" if state.on_no else "error"`. Every `run_*` state in
   `code-run-gate.yaml` routes `on_yes`/`on_no`/`on_error` to the *same*
   successor by design (`aggregate` is the sole arbiter, reading sidecar
   files). Flipping the verdict changes nothing. `resolve_commands` is worse —
   it uses `next:` (L184), an unconditional transition that ignores the verdict
   entirely.

2. **Evidence is clobbered.** `ctx.context["_tamper_guard"]`
   (`fsm/executor.py:1460`) is assigned unconditionally on every guarded
   state's exit. In the trace above, the 4 trailing SKIP states each overwrite
   the `run_test` finding with `passed=True`, so by the time `aggregate` runs
   the record of the tamper is gone. This also silently defeats
   `policy: allow`, whose entire purpose is to record findings.

## Expected Behavior

- A `fail`-policy tamper finding blocks the run regardless of the guarded
  state's routing shape — it must not depend on `on_no` differing from
  `on_yes`.
- Findings accumulate rather than overwrite, so a finding on one state survives
  to be consumed by a later aggregator and by run evidence under `policy:
  allow`.

## Steps to Reproduce

```bash
mkdir -p /tmp/guardrepo/tests /tmp/guardrepo/.ll && cd /tmp/guardrepo
git init -q . && git config user.email t@t.t && git config user.name t
printf 'def test_x():\n    assert 1 == 1\n' > tests/test_x.py
printf '[pytest]\n' > pytest.ini
cat > .ll/ll-config.json <<'EOF'
{"project":{"name":"guardrepo",
 "test_cmd":"printf 'def test_x():\\n    assert 1 != 2\\n' > tests/test_x.py; echo ok"}}
EOF
git add -A && git commit -qm init
ll-loop run oracles/code-run-gate --context run_dir=.loops/rd --context issue_id=TEST-1
# observed: GATE_PASS, tests/test_x.py mutated.  expected: GATE_FAILED
```

## Impact

- **Priority**: P2 — the guard is a security/integrity control that reports
  success while failing open. It is worse than dormant: `tamper_guard: fail` in
  a loop YAML reads as enforcing, so it invites false confidence. Not P1 only
  because no shipped loop depended on it until now.
- **Blast radius**: any loop adopting `tamper_guard` on a convergent-routing or
  `next:`-chained state — which is the common shape for deterministic oracle
  gates.
- **Effort**: Small-Medium — the fix is in `fsm/executor.py`, not in loop YAML.

## Proposed Solution

Two independent fixes:

1. **Enforcement that does not depend on routing shape.** Rather than flipping
   the verdict, `fail` + `not passed` should force the run toward a failure
   terminal directly (the mechanism `_check_throttle`'s `"__STOP__"` already
   uses to short-circuit), or route to the loop's declared failure terminal.
   A verdict flip is only meaningful when routes diverge.
2. **Accumulate evidence.** Make `ctx.context["_tamper_guard"]` a list, or
   merge findings into the existing entry, so later guarded states cannot erase
   an earlier finding.

Consider also a `ll-loop validate` lint (MR-family): WARN when a state carries
an effective `tamper_guard` policy of `fail` but its routing is convergent or
`next:`-based — i.e. the guard provably cannot enforce. That shifts this class
of defect left, matching the existing `diagnose-evaluators` "paired-but-
toothless" framing.

## Program Design

### Types

No new types. Change is to the shape of one existing context key:
`ctx.context["_tamper_guard"]` becomes a list of the current per-state dict
(`policy`, `passed`, `findings`, `reverted`) plus a `state` field, instead of a
single dict overwritten per state.

### Signatures

No public signature changes. The two touched internals keep their existing
signatures:

- `FSMExecutor._execute_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None`
- `_validate_tamper_guard(fsm: FSMLoop) -> list[ValidationError]`

Both edits are inside `_execute_state`'s compare-on-exit block:

- `fsm/executor.py:1460` — append to a list rather than assign.
- `fsm/executor.py:1469-1474` — replace the verdict-flip with a routing-shape-
  independent failure path, mirroring `_check_throttle`'s `"__STOP__"`
  short-circuit convention already used at `executor.py:1428-1430`.

Optional lint: `_validate_tamper_guard` (`fsm/validation/evaluator_rules.py:378`)
gains a convergent-routing check under the existing `tamper_guard_ok`
suppression flag.

### Call Path

`FSMExecutor._execute_state` → `run_tamper_guard` → (finding) → failure
terminal, bypassing `EvaluationResult` verdict routing entirely.

## Scope Boundaries

**In scope:**
- `fsm/executor.py` tamper-guard enforcement and evidence accumulation.
- Optionally, a validation lint for provably-inert tamper guards.

**Out of scope:**
- `oracles/code-run-gate.yaml`'s convergent routing — that shape is deliberate
  (`aggregate` as sole arbiter) and should not be redesigned to work around an
  executor limitation.
- BUG-2954's non-FSM weakening heuristic — a different window and mechanism.
- ENH-2958's non-FSM post-implement step — blocked on this, see below.

## Acceptance Criteria

- [ ] The reproduction above yields `GATE_FAILED` / a failure terminal.
- [ ] A `fail`-policy finding on a state whose `on_yes`/`on_no`/`on_error`
      converge still blocks the run; a test covers the convergent shape
      specifically.
- [ ] A `fail`-policy finding on a `next:`-chained state blocks the run.
- [ ] A finding on an early guarded state survives later clean guarded states
      and is present in run evidence; a test covers the clobbering case.
- [ ] `policy: allow` records all findings across states, not just the last.
- [ ] Existing `TestTamperGuardExecutorHook` tests
      (`test_fsm_executor.py:10702`) still pass unmodified.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

### Blocks ENH-2958 (active blocker)

`ENH-2958.blocked_by: [BUG-2962]` is now recorded in that issue's frontmatter.
ENH-2958 would replicate this exact bracket for the non-FSM orchestrators; the
enforcement path it copies is known-broken, so shipping it first would produce a
second guard that reports success while failing open. **This bug is the
prerequisite and should be scheduled ahead of ENH-2958.**

Note the priority inversion that follows: BUG-2962 is P2, ENH-2958 is P4. The
dependency runs from the lower-priority issue to the higher-priority one, which
is the correct direction — no reprioritization is needed, but a scheduler
selecting purely by priority will pick this up first anyway.

### How this was found

Enabling `tamper_guard: fail` on `oracles/code-run-gate.yaml` (staged alongside
this issue) was ENH-2958's proposed "far cheaper prerequisite." It is now done,
and it surfaced this defect rather than confirming the capability. The oracle
keeps the guard enabled with an inline comment marking it detect-only until
this lands — see `code-run-gate.yaml:29-58`.

The verified trace is reproduced under "Current Behavior" above: 6
`run_tamper_guard` invocations, one true positive on `run_test`
(`passed=False`, `findings=[('tests/test_x.py','modified')]`), final state
`done` / `GATE_PASS`.

### Premises this invalidates in ENH-2958

Two of that issue's stated premises are wrong and should be corrected when it
is next refined:

- `rn-implement.yaml` has no verify state — it is a queue orchestrator that
  delegates to `rn-remediate` (`loop: rn-remediate`, L755). The implement
  state is `rn-remediate.yaml:499`; the verify step is `run_code_gate`
  (L529), a `loop:` delegation to this oracle.
- `run_code_gate` cannot be guarded at all: the executor's bracket requires
  `state.action` (`executor.py:1415`), and a `loop:` delegation state has no
  `action`. So state-level `tamper_guard` on the delegating state is silently
  inert — a third variant of the same failure mode.

Both are third and fourth variants of the same failure mode this bug describes:
a `tamper_guard` declaration that reads as enforcing but provably cannot fire.
That is the strongest argument for the `ll-loop validate` lint proposed above —
four distinct inert shapes have now been found in a single sitting.

## Status

**Open** | Created: 2026-07-31 | Priority: P2
