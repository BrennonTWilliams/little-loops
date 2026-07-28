---
id: ENH-2773
status: done
priority: P2
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:26+00:00
discovered_by: audit-architecture
completed_at: '2026-07-28T11:26:26Z'
focus_area: integration
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
confidence_score: 97
outcome_confidence: 76
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 20
---

# ENH-2773: Fix fsm→cli layering inversion (move resolve_loop_path out of cli/loop/_helpers)

## Summary

Architectural issue found by `/ll:audit-architecture`. The core FSM layer
imports from the CLI layer: `fsm/validation.py` reaches up into
`cli/loop/_helpers` for `resolve_loop_path`, inverting the intended dependency
direction (core → cli, never cli ← core).

## Location

- **File**: `scripts/little_loops/fsm/validation.py`
- **Line(s)**: 485, 566 (deferred `from little_loops.cli.loop._helpers import resolve_loop_path`)
- **Module**: `little_loops.fsm.validation`

## Finding

### Current State

```python
# fsm/validation.py:485 and :566 (inside functions, to dodge the cycle)
from little_loops.cli.loop._helpers import resolve_loop_path
```

- `cli/loop/_helpers.py` and `fsm/validation.py` form a module-level 2-cycle,
  currently held apart only by deferred imports on both sides.
- Loop-path resolution is core FSM behavior (static `loop:` reference
  validation depends on it), not a CLI presentation concern.
- Related fragility in the same layering pass: `subprocess_utils.py:23` imports
  `host_runner` at module level while `host_runner` defers its imports of
  `subprocess_utils` — a one-sided cycle that works only by import order and
  will break silently if the deferred imports are ever "cleaned up".

### Impact

- **Development velocity**: contributors must know the unwritten rule that
  these imports stay function-local; refactors keep re-tripping the cycle.
- **Maintainability**: the layer order (core → fsm → parallel → cli) exists by
  convention only; this edge is the clearest violation of it.
- **Risk**: import-order breakage is silent until a specific code path runs.

## Current Behavior

`fsm/validation.py` reaches up into `cli/loop/_helpers.py` for
`resolve_loop_path` via deferred (function-local) imports at lines 485 and
566, forming a bidirectional module-level 2-cycle with `cli/loop/_helpers.py`
(which itself deferred-imports `fsm.validation.load_and_validate`). The cycle
is held apart only by both sides using function-local imports instead of
top-level ones — an unwritten convention that isn't enforced anywhere.

## Expected Behavior

`resolve_loop_path` (and its dependency `get_builtin_loops_dir`) live in the
`fsm` layer (e.g. `fsm/loop_paths.py`), so `fsm/validation.py` can import it
at module level with no cycle. `cli/loop/_helpers.py` re-exports the same
names for backward compatibility, and the `core → fsm → parallel → cli`
dependency direction holds with no remaining deferred-import workaround for
this specific cycle.

## Scope Boundaries

**In scope**: relocating `resolve_loop_path`/`get_builtin_loops_dir` to
`fsm/loop_paths.py`, converting the two `fsm/validation.py` deferred imports
to top-level imports, preserving the `cli/loop/_helpers` re-export, and
updating the other deferred-import call sites (`fsm/executor.py:823`,
`fsm/fragments.py:207`) to use the new module directly. Documenting the
`host_runner`/`subprocess_utils` one-sided deferral with an explanatory
comment (no restructuring) is also in scope per the Proposed Solution.

**Out of scope**: the broader `cli/loop/_helpers.py` grab-bag split — that is
`P3-ENH-2776`, which should treat `fsm/loop_paths.py` as already extracted.
Adding the `core → fsm → parallel → cli` rule to `docs/ARCHITECTURE.md` is a
nice-to-have, not required for this fix.

## Proposed Solution

Move `resolve_loop_path` (and any helpers it depends on) into the `fsm`
layer — e.g. `fsm/loop_paths.py` — and have `cli/loop/_helpers` re-export or
import it from there, reversing the edge to the correct direction.

### Suggested Approach

1. Relocate `resolve_loop_path` to `little_loops/fsm/loop_paths.py` (or an
   existing fsm module if a better home exists); keep a re-export in
   `cli/loop/_helpers` for compatibility.
2. Convert the two deferred imports in `fsm/validation.py` to normal top-level
   imports of the new module; confirm the `cli.loop._helpers ↔ fsm.validation`
   2-cycle is gone.
3. In the same pass, make `host_runner`/`subprocess_utils` symmetric (extract
   the shared piece or document why the one-sided deferral is required).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`resolve_loop_path` implementation** (`cli/loop/_helpers.py:1407-1428`) is
  self-contained apart from stdlib `Path`: it tries the literal path, then
  `<loops_dir>/<name>.fsm.yaml`, then `<loops_dir>/<name>.yaml`, then falls
  back to `get_builtin_loops_dir() / f"{name}.yaml"` (`_helpers.py:1217-1219`,
  `Path(__file__).parent.parent.parent / "loops"`), raising `FileNotFoundError`
  if nothing matches. Both functions have no other module-level dependencies,
  confirming they can move cleanly without dragging in `_helpers.py`'s
  terminal-rendering/signal-handling machinery (imports at `_helpers.py:19-28`:
  `cli.output`, `cli.loop.diagram_modes`, `fsm.concurrency`, `fsm.types`,
  `logger.Logger` — none needed by `resolve_loop_path` itself).
- **This is a true bidirectional 2-cycle**, not one-sided: `_helpers.py`'s own
  `load_loop()` (`:1431-1442`) and `load_loop_with_spec()` (`:1445-1466`) do a
  deferred `from little_loops.fsm.validation import load_and_validate` (line
  1438 / 1458) to call `resolve_loop_path()` then `load_and_validate()` in
  sequence — the correct-direction half of the cycle. The inverted half is in
  `fsm/validation.py`: `_validate_with_bindings()` (`:479-553`, deferred import
  at line 500, wrapped in `try/except Exception`) and
  `_validate_loop_references()` (`:556-592`, deferred import at line 581,
  wrapped in `try/except FileNotFoundError`). The latter's docstring
  (`:562-571`) notes it deliberately calls the *same* `resolve_loop_path` the
  runtime executor uses, so validate-time and run-time resolution can't drift
  — a constraint the relocation must preserve (single source of truth, not a
  duplicated copy in `fsm`).
- **Additional callers beyond the two validation.py sites** that also use
  deferred imports of `resolve_loop_path` and would benefit from the fix:
  `fsm/executor.py:823` (`_execute_sub_loop()`) and `fsm/fragments.py:207`
  (`resolve_inheritance()`, parent-loop lookup). CLI-layer callers already use
  top-level imports safely: `cli/loop/run.py`, `cli/loop/info.py`,
  `cli/loop/edit_routes.py:8`, `cli/loop/lifecycle.py`,
  `cli/loop/config_cmds.py:8` (also imports `get_builtin_loops_dir`);
  `cli/queue.py:44` still defers.
- **`get_builtin_loops_dir()` is a shared dependency** referenced from 5
  CLI-layer files (`cli/doctor.py`, `cli/loop/run.py`, `cli/loop/_helpers.py`,
  `cli/loop/info.py`, `cli/loop/config_cmds.py`) in addition to
  `resolve_loop_path`. Decide during implementation whether it moves alongside
  `resolve_loop_path` into `fsm/loop_paths.py` or stays in `_helpers.py` with
  `fsm/loop_paths.py` importing it back up (which would reintroduce the
  inversion) — moving both together is the cleaner option since neither has
  CLI-specific behavior (pure `Path` arithmetic).
- **Existing precedent for the re-export shim shape**: `fsm/__init__.py:1-168`
  already re-exports every public name from its concern-split submodules
  (`schema.py`, `validation.py`, `persistence.py`, etc.) through a single
  `__all__`, grouped by concern with comment headers. A new
  `fsm/loop_paths.py` should follow the same intra-`fsm` top-level import
  style used elsewhere (e.g. `fsm/persistence.py:37-41`), and
  `cli/loop/_helpers.py` should keep `resolve_loop_path`/`get_builtin_loops_dir`
  importable by name (`from little_loops.cli.loop._helpers import
  resolve_loop_path` must keep working) since `cli/loop/edit_routes.py` and
  others import it directly from `_helpers`.
- **No existing layering/import-cycle regression test** exists in
  `scripts/tests/` (searched "import cycle" / "layering" / "circular import" —
  no hits beyond unrelated incidental matches). Any test asserting the cycle
  is gone (e.g. importing `fsm.validation` standalone and checking
  `sys.modules` for `cli.loop._helpers`, or a static AST check for
  module-level imports) would be net-new.
- **Tests exercising `resolve_loop_path` indirectly**: `test_fsm_validation.py`
  covers `_validate_with_bindings`/`_validate_loop_references`;
  `test_deep_research.py:194,221`, `test_deep_research_arxiv.py:221`, and
  `test_rn_plan.py:308` also use deferred imports of `resolve_loop_path` in
  test setup and should keep passing unchanged post-move if the
  `cli/loop/_helpers` re-export is preserved.
- **`docs/ARCHITECTURE.md`'s "Orchestration Layers" section (`:348-391`)
  documents a different layering axis** (L0 shared core → L1 `ll-auto` → L2
  `ll-sprint` → L3 `ll-parallel`, entry points) — it does not currently state
  the `core → fsm → parallel → cli` module-dependency-direction rule this
  issue's Impact section asserts; that rule exists today only in this issue
  and in the parent epic (`EPIC-2789:24-26,34`). Consider adding a short note
  to `ARCHITECTURE.md` once the cycle is fixed, so the rule has one canonical
  home.
- **Overlapping-scope sibling issue**: `P3-ENH-2776` ("Dissolve
  cli/loop/_helpers.py grab-bag into named modules") targets the same file
  more broadly and explicitly cites this issue's line numbers as one of its
  motivating examples. Implement ENH-2773 first (narrower, higher severity)
  — ENH-2776's later split should treat `fsm/loop_paths.py` as already
  extracted rather than re-deciding its home.
- **`host_runner`/`subprocess_utils` is a one-sided cycle, not symmetric**:
  `subprocess_utils.py:23` imports `resolve_host` from `host_runner` at module
  level. `host_runner.py`'s only reference back is inside `if TYPE_CHECKING:`
  (`:40-42`, erased at runtime, type-only) plus one deferred import inside
  `_usage_from_response()` (`:1580-1582`) to construct a `TokenUsage`. Because
  `host_runner.py` never needs `subprocess_utils` at module-load time, there is
  no live circular-import hazard today — the risk is that a future "cleanup"
  moves the `TokenUsage` import out of `TYPE_CHECKING`/deferred position into
  a plain top-level import, which would then cycle. Suggested fix: leave the
  runtime deferred import as-is (it's correct), but add a one-line comment at
  `host_runner.py:1580` explaining why it must stay deferred, rather than
  restructuring — there is no shared-piece extraction needed here since the
  only runtime coupling is a single dataclass construction.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

4. Shorten `get_builtin_loops_dir()`'s `Path(__file__).parent` chain by one
   hop when it moves from `cli/loop/_helpers.py` to `fsm/loop_paths.py` (3
   parents → 2 parents) — a known gotcha per BUG-1008/FEAT-2274.
5. Verify `cli/loop/testing.py:8` and `analytics/variance.py:224` (both
   import `load_loop`) still resolve correctly through the `_helpers`
   re-export after the move.
6. Confirm `test_cli_doctor_install_checks.py:211,233,252`'s
   `monkeypatch.setattr("little_loops.cli.loop._helpers.get_builtin_loops_dir", ...)`
   still works — requires the re-export to bind a real name in `_helpers`,
   not just a pass-through reference.
7. Add `scripts/tests/test_fsm_loop_paths.py` covering the new
   `fsm/loop_paths.py` module directly.
8. Decide whether `resolve_loop_path`/`get_builtin_loops_dir` join
   `fsm/__init__.py`'s public `__all__` re-exports (matching sibling
   submodules) or stay `fsm.loop_paths`-only.

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/testing.py:8` — imports `load_loop` from
  `cli/loop/_helpers`; unaffected if the re-export is preserved, but confirm
  after the move [Agent 1 finding]
- `scripts/little_loops/analytics/variance.py:224` — imports `load_loop`
  (deferred, inside a function body); same re-export dependency [Agent 1
  finding]

### Files to Modify

- `scripts/little_loops/fsm/loop_paths.py:1428` (new file) — when relocating
  `get_builtin_loops_dir()`, the `Path(__file__).parent...` chain must drop
  from 3 parents (in `cli/loop/_helpers.py`) to 2 parents (in `fsm/`) to keep
  resolving to `scripts/little_loops/loops/`; this exact gotcha is documented
  in BUG-1008 and FEAT-2274 [Agent 2 finding]
- `scripts/little_loops/fsm/__init__.py` — currently does NOT export
  `resolve_loop_path`/`get_builtin_loops_dir`. Decide during implementation
  whether to add them to the top-level import block and `__all__` (matching
  the pattern used for `persistence.py`'s exports) for consistency with
  sibling `fsm` submodules, or deliberately leave them CLI-facing-only and
  accessible solely via `fsm.loop_paths` [Agent 1 + Agent 2 finding, framed as
  a decision point rather than a required change]

### Tests

- `scripts/tests/test_cli_doctor_install_checks.py:211,233,252` — monkeypatches
  `"little_loops.cli.loop._helpers.get_builtin_loops_dir"` directly; this only
  keeps working if the compat re-export leaves `get_builtin_loops_dir` as a
  real bound name in `_helpers`'s namespace (not just referenced through it)
  [Agent 3 finding]
- `scripts/tests/test_cli_loop_testing.py:271` — imports `load_loop`; verify
  unaffected by the relocation [Agent 1 finding]
- New test file needed: `scripts/tests/test_fsm_loop_paths.py` for the new
  `fsm/loop_paths.py` module directly [Agent 3 finding]
- Optional new layering-regression test (no cycle-detection test exists today
  — confirmed by search) — closest structural template in this repo is
  `scripts/little_loops/cli/verify_cli_allowlist.py` +
  `scripts/tests/test_verify_cli_allowlist.py` (static-parse-and-assert shape,
  called directly rather than via runtime `sys.modules` introspection) [Agent
  3 finding]
- Tests unaffected because their patches target the CLI-layer re-export one
  hop downstream (`cli.loop.info`, `cli.loop.config_cmds`), not `_helpers`
  itself — no action needed: `test_ll_loop_commands.py` (~40 sites),
  `test_cli_loop_next.py:368-436`, `test_json_output_contracts.py:69` [Agent 3
  finding, informational]

### Documentation

- `docs/development/TROUBLESHOOTING.md:828` — names `get_builtin_loops_dir()`
  by bare name (no module path) in the BUG-885 postmortem; stays accurate
  post-move but is a candidate to annotate with the new location [Agent 2
  finding]
- No doc file states the `core → fsm → parallel → cli` module-dependency rule
  anywhere outside this issue and `EPIC-2789:24-26,34` — confirmed by search;
  `docs/ARCHITECTURE.md`'s "Orchestration Layers" section documents a
  different (execution-lifecycle) axis and has no natural section to extend,
  so documenting the rule would be new content, not an edit [Agent 2 finding]

## Impact Assessment

- **Severity**: High
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Impact

- **Priority**: P2 - core-layer import cycle held apart only by an unwritten
  deferred-import convention; low blast radius but clearest violation of the
  intended `core → fsm → parallel → cli` layering.
- **Effort**: Small - two call sites in `fsm/validation.py` plus a handful of
  other deferred-import call sites to update; the moved functions have no
  other module-level dependencies.
- **Risk**: Low - re-export shim in `cli/loop/_helpers` preserves all existing
  import paths; no behavior change, only import location.
- **Breaking Change**: No

## Resolution

Relocated `resolve_loop_path`/`get_builtin_loops_dir` to new
`fsm/loop_paths.py`. Converted the two `fsm/validation.py` deferred imports
plus `fsm/executor.py:823` and `fsm/fragments.py:207` to top-level imports of
the new module. `cli/loop/_helpers.py` now re-exports both names via a
top-level import for backward compatibility. Added an explanatory comment at
`host_runner.py:_usage_from_response` documenting why its deferred import of
`subprocess_utils.TokenUsage` must stay deferred. Added
`scripts/tests/test_fsm_loop_paths.py` covering the new module directly plus
a regression test asserting the `cli/loop/_helpers` re-export binds the same
objects. Full test suite passes (7 pre-existing unrelated failures confirmed
present without this change).

## Session Log
- `/ll:manage-issue` - 2026-07-28T11:25:53 - `215318c4-a0a4-4690-9987-071d48d51b46.jsonl`
- `/ll:ready-issue` - 2026-07-28T11:17:20 - `c5bdffd7-8d96-447f-8376-171af765cfd6.jsonl`
- `/ll:wire-issue` - 2026-07-28T11:14:28 - `2f6e4b92-887d-46c7-9188-fcf41563fdc2.jsonl`
- `/ll:refine-issue` - 2026-07-28T11:10:12 - `84562207-dc59-4fac-b11b-397ac5512573.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2
