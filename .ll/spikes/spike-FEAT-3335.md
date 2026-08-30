# Spike Plan: FEAT-3335 — rolling-baseline containment gate

## Context

FEAT-3335 selected Option B (per-pass gates at six window boundaries, one
factored fragment, **rolling baseline**) over Option A (single re-check,
init-anchored baseline). The Decision Rationale and both refine passes flag
the same unproven mechanism:

> "Reconfirmed (2026-08-30, independent repo-wide search): no loop or Python
> module anywhere in the tree implements a per-pass rolling-baseline diff
> pattern... ⚠ Unproven mechanism — rolling baseline has no in-repo
> precedent." (issue body, Proposed Solution → Codebase Research Findings)

Concrete failure the spike must rule out: the landed FEAT-3332
`check_intent_scope` script only ever diffs against `init`'s **one baseline,
never rewritten**. Option B requires each of the six new gates to (a) diff
against the *previous* gate's snapshot, not `init`'s, and (b) on pass,
rewrite the baseline to the current snapshot so the next gate's window starts
clean. If advancing the baseline on pass silently swallows a real violation
(because it got folded into the "already accounted for" set), or if it fails
to isolate which window a violation belongs to, Option B's core attribution
claim — "each diff window names the states between gates" — is false and the
selected option should have been Option A.

Both canonical low-confidence drivers apply: **(a)** zero precedent for the
rolling-baseline pattern; **(b)** no existing test exercises multi-window
sequential gating with baseline advancement.

## Approach

Reimplement the FEAT-3332 changed-set algorithm (tracked ∪ untracked,
path → sha256, symmetric diff, `run_dir`-prefix allow-list) as a small
importable Python library instead of embedded shell, add one new capability
absent from the landed script — **advance the baseline file to the current
snapshot when the gate passes** — and drive it against real temporary git
repos through a simulated 3-gate pipeline (`init` → `gate1` → `gate2`). Real
`git` subprocess calls and a real filesystem are used (the same primitives
the production shell body uses); only the harness (Python functions instead
of `python3 -c` + bash plumbing) is faked, and that substitution doesn't
touch the risky core — the diff/advance/attribution logic runs identically
either way.

## Critical files

Read-only references:
- `scripts/little_loops/loops/workflow-generator.yaml:248-363` — the landed
  `check_intent_scope` gate body this spike extends (comparison-only, single
  baseline, never advances).
- `scripts/little_loops/loops/workflow-generator.yaml:44-187` — `init`'s
  baseline capture (dump mode of the same embedded script).
- `scripts/tests/test_builtin_loops.py::TestCheckIntentScopeShellAction`
  (`:18544`) — existing regression suite for the landed gate; the spike must
  not contradict its assumptions about the comparison script's behavior.

New spike paths:
- `scripts/tests/spike/rolling_scope_gate/__init__.py`
- `scripts/tests/spike/rolling_scope_gate/rolling_gate.py`
- `scripts/tests/spike/rolling_scope_gate/test_rolling_gate.py`

## Implementation

```
scripts/tests/spike/rolling_scope_gate/
├── __init__.py
├── rolling_gate.py          # changed_set() + run_gate() with advance-on-pass
└── test_rolling_gate.py     # AC test class + isolation guard
```

API sketch (`rolling_gate.py`):

```python
def changed_set(root: str, ref: str) -> dict[str, str]:
    """tracked-diff-vs-ref ∪ untracked, path -> sha256 (or "DELETED")."""

@dataclass
class GateResult:
    passed: bool
    violations: list[str]
    snapshot: dict[str, str]

def run_gate(
    root: str, ref: str, run_dir: str, baseline_path: str, *, advance: bool = True
) -> GateResult:
    """Load baseline_path, diff against changed_set(root, ref), filter
    violations to paths outside run_dir. On pass (no violations) and
    advance=True, overwrite baseline_path with the current snapshot so the
    NEXT call's window starts here. On failure, baseline_path is left
    untouched."""
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_gate_passes_and_advances_baseline` | Risk (a)/(b): baseline-advance-on-pass has no precedent and is untested | behavior |
| `test_gate_fails_and_leaves_baseline_untouched` | Risk (b): failure path must not corrupt the rolling baseline | behavior |
| `test_sequential_windows_attribute_violation_to_correct_gate` | Risk (a): the core Option B claim — per-window attribution across a 3-gate chain | behavior |
| `test_advance_does_not_mask_a_violation_in_the_same_pass` | Risk (a): advancing must be gated on zero violations, never partial/best-effort | behavior |
| `test_rolling_gate_module_has_no_production_imports` | isolation guard | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/rolling_scope_gate/ -v
python -m pytest scripts/tests/test_builtin_loops.py -k TestCheckIntentScopeShellAction -v
```

## Out of Scope

- The actual FSM YAML wiring (six insertion edges, fragment factoring,
  `${context.loops_dir}` allow-list addition, `diagnose`/
  `finalize_await_confirmation` routing) — that is FEAT-3335's real
  integration point, done after this spike, not by it.
- Placement-count and late-violation-routing design questions (Expected
  Behavior questions 1–2) — those are `/ll:decide-issue` territory, not
  retired by proving the mechanism works.
- Any change to the landed `check_intent_scope` shell body itself (read-only
  in this skill).

## Promotion

On acceptance, promote `rolling_gate.py`'s `run_gate`/`changed_set` shape
into the actual fragment body embedded in
`scripts/little_loops/loops/workflow-generator.yaml` (or
`scripts/little_loops/loops/lib/common.yaml`, per the fragment-location
decision) in a **separate PR** — this spike proves the algorithm, it does not
ship it as embedded shell.
