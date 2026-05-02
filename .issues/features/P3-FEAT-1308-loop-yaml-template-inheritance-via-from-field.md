---
captured_at: "2026-05-01T17:30:19Z"
discovered_date: "2026-05-01"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 81
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 18
---

# FEAT-1308: Loop YAML Template Inheritance via `from:` Field

## Summary

Add a `from:` top-level field to loop YAML files that lets a child loop inherit another loop's state graph and override only the deltas, replacing copy-paste of full ~100-line loop skeletons with ~15-line variants.

## Current Behavior

Each loop YAML in `scripts/little_loops/loops/` declares its full state graph from scratch. There is no inheritance mechanism — `lib/` fragments only cover prompt/snippet reuse, not loop skeletons. Adding a new variant requires duplicating ~100 lines of boilerplate even when only a few states differ.

## Expected Behavior

Loop YAML accepts an optional `from: <loop-name>` top-level field. The loader resolves the parent loop, deep-merges child state overrides on top, and feeds the materialized loop into validation. Circular `from:` chains raise a clear error. Transition merge defaults to replace, with `append_transitions: true` opt-in per state. Existing loops without `from:` behave identically.

## Motivation

Most loops in `scripts/little_loops/loops/` share the same skeleton (plan → execute → check → loop). Today, every loop YAML repeats the full state graph even when it differs from a sibling by only a handful of states or transitions. This makes the catalog harder to scan, harder to keep consistent, and discourages introducing new variants since each one starts at ~100 lines of boilerplate.

Existing `lib/` fragments cover prompt and snippet reuse, but there is no mechanism for loop-level skeleton reuse — i.e., "this loop is like X but with these deltas." A one-line `from:` declaration that inherits another loop's states and lets the child override only what changes would turn many 100-line loops into ~15 lines.

## Use Case

Author wants a new "scan + refine" loop that is identical to `issue-refinement.yaml` except the `execute` state runs a different skill and the `check` state has an extra exit transition. Instead of copy-pasting the entire YAML, they write:

```yaml
name: my-scan-refine
from: issue-refinement
states:
  execute:
    prompt: "/ll:scan-codebase"
  check:
    transitions:
      - if: needs_decision
        to: decide
```

Loader merges the parent's states with these overrides at load time, producing the full FSM.

## API/Interface

**New top-level YAML field:**

- `from: <loop-name>` — references a loop by name, resolved via the existing `resolve_loop_path()` (in `scripts/little_loops/cli/loop/_helpers.py:93`) which already searches `<loops_dir>/<name>.fsm.yaml`, `<loops_dir>/<name>.yaml`, and the built-in `scripts/little_loops/loops/` directory. Must point to a loop without circular `from:` chains.

**Merge semantics (canonical schema confirmed; routing terminology corrected):**

- Child `states.<name>` deep-merges into parent `states.<name>` (child wins on scalar conflicts). The `states` field is a **mapping** (`dict[str, StateConfig]` per `scripts/little_loops/fsm/schema.py:546`), not a list — confirmed by reading `FSMLoop` and all 45 built-in YAMLs. Cross-issue note: this resolves the FEAT-1283 schema ambiguity in favor of the mapping form (already canonical, not a new decision).
- The schema does **not** use a `transitions:` list — that section of the original Open Questions was based on an incorrect mental model. State routing is expressed via:
  - **Shorthand fields**: `on_yes`, `on_no`, `on_error`, `on_partial`, `on_blocked`, `on_maintain`, `on_retry_exhausted`, `on_rate_limit_exhausted`, `next` (each is a single string — the target state name), declared on `StateConfig` at `scripts/little_loops/fsm/schema.py:230-256`.
  - **Full routing table**: an optional `route:` dict (verdict → state name).
  - **Extra routes**: arbitrary `on_<verdict>:` keys captured in `extra_routes` at `schema.py:256`.
- The "replace vs. append" question for transitions therefore reduces to: "do scalar `on_*` fields in the child override the parent's?" The answer follows the existing `_deep_merge` rule (override wins on scalars, see `scripts/little_loops/fsm/fragments.py:41-61`) — so **override is the natural default** with no special flag needed for the shorthand. The remaining design choice is the `route:` dict and `extra_routes` (verdict → state mapping): default to deep-merge by verdict (child verdicts win, parent verdicts that the child does not redefine are preserved). If a use case requires "wipe parent verdicts entirely," add an opt-in `route_replace: true` per state — but no built-in YAML has demonstrated this need, so defer until a concrete case appears.
- Child top-level fields (`description`, `initial`, `category`, `labels`, `context`, etc.) override parent. The `name:` field MUST be the child's own name (the loop is identified by filename / loaded name, not the parent's name).
- Resolution must happen at `scripts/little_loops/fsm/validation.py:563` — the same hook where `resolve_fragments()` runs today. Add a new `resolve_inheritance(data, path.parent)` call **before** `resolve_fragments(...)`, so a parent's `import:`/`fragments:` blocks are still expanded after merging.
- The `from:` field must be added to `KNOWN_TOP_LEVEL_KEYS` at `scripts/little_loops/fsm/validation.py:78` so it does not trigger the unknown-key warning.

## Implementation Steps

1. Identify the loop loader entry point and confirm where YAML is parsed into the FSM model.
2. Add `from:` parsing + resolution: load the parent YAML, recursively resolve its own `from:` chain, then deep-merge child on top.
3. Detect cycles in the `from:` chain and fail fast with a clear error.
4. Decide and implement transition merge policy (replace vs. append) — surface as a documented rule.
5. Update loop validation (`/ll:review-loop`, FSM diagram generation) to operate on the resolved loop, not the raw YAML.
6. Pick 2–3 high-redundancy loops in `scripts/little_loops/loops/` (candidates: APO variants, harness variants) and refactor them to use `from:` as the proof-of-value.
7. Document the feature in `docs/` (loops guide) and add an example to `templates/` if loop templates exist there.
8. Add tests covering: simple inheritance, transition merge policy, deep state override, cycle detection, missing parent.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file:line anchors for each step:_

1. **Loader entry point**: `scripts/little_loops/fsm/validation.py:518` — `load_and_validate(path: Path)`. YAML is parsed at `validation.py:536`, fragments are expanded at `validation.py:563` via `resolve_fragments(data, path.parent)`, then `FSMLoop.from_dict(data)` is called at `validation.py:566`. Add inheritance resolution **between lines 539 and 562** (after the YAML mapping check, before fragment expansion — so a parent's `import:`/`fragments:` blocks survive into the merged result). Keep the unknown-keys check (lines 551–560) updated to permit `from:`.
2. **Inheritance resolver**: add a new function `resolve_inheritance(data: dict, loop_dir: Path, _seen: tuple = ()) -> dict` in `scripts/little_loops/fsm/fragments.py` (alongside `resolve_fragments`). Body:
   - If `"from"` not in `data`: return `data` unchanged.
   - Use `from little_loops.cli.loop._helpers import resolve_loop_path` (already imported lazily in `fsm/executor.py:410` — established pattern). Resolve the parent path against `loop_dir` as the `loops_dir` argument.
   - Open the parent YAML with `yaml.safe_load`, recurse with `_seen + (parent_name,)`, merge with the existing `_deep_merge(parent_data, child_data)` at `fragments.py:41`, then return.
   - The child's `name:` field must overwrite the parent's after merge — `_deep_merge` already does this since `name` is a scalar.
   - Strip the `from:` key from the merged result before returning (analogous to how `resolve_fragments` strips the `fragment:` key per state at `fragments.py:140`).
3. **Cycle detection**: pass `_seen: tuple[str, ...]` through the recursion. Before recursing on the parent, check `if parent_name in _seen: raise ValueError(f"Circular 'from:' chain: {' -> '.join(_seen + (parent_name,))}")`. Tuple is used (not set) so the error message preserves chain order. Mirrors the cycle-style errors already raised by `resolve_fragments` at `fragments.py:131`.
4. **Merge policy** — see API/Interface above. The shorthand `on_*` fields on `StateConfig` (`schema.py:230-256`) are scalars and naturally override via `_deep_merge`. The `route:` dict deep-merges by verdict (child verdicts override the same parent verdict; parent verdicts not redefined are preserved). No new policy flag is required for the v1 implementation. Document this in the loops guide.
5. **Validation/diagram tools**: no code changes required. `cmd_validate` in `scripts/little_loops/cli/loop/config_cmds.py:20` calls `resolve_loop_path` → `load_and_validate`, and `info.py` (FSM diagram) calls `load_loop_with_spec` at `_helpers.py:131`. Both consume the post-`load_and_validate` `FSMLoop`, so they already see the materialized loop once step 1 lands. **However**: `load_loop_with_spec` returns the raw spec dict separately at `_helpers.py:149` for callers that want the raw YAML — those callers (`info.py:882`) will see the unresolved YAML with `from:` still present. Decide whether to (a) leave that as raw (fine for display purposes), or (b) also expose a resolved spec. Recommend (a) for v1 — display the YAML the author wrote, not the merged form.
6. **Refactor candidates** (line counts confirmed via `wc -l`):
   - `scripts/little_loops/loops/apo-beam.yaml` (61 lines), `apo-textgrad.yaml` (64), `apo-contrastive.yaml` (72), `apo-feedback-refinement.yaml` (81), `apo-opro.yaml` (89) — five APO variants share the same plan/execute/evaluate/loop skeleton. Best candidate set: extract the shared skeleton into `scripts/little_loops/loops/apo-base.yaml` (or `lib/apo-base.yaml`), then have all five inherit via `from: apo-base`.
   - `scripts/little_loops/loops/harness-single-shot.yaml` (149), `harness-multi-item.yaml` (180), `harness-optimize.yaml` (142) — three harness variants. Same approach with `harness-base.yaml`.
   - Pick **2** for the proof-of-value (acceptance criteria minimum): two APO variants give the highest signal-to-LOC ratio.
7. **Documentation**:
   - `docs/guides/LOOPS_GUIDE.md` — add a new section after the existing "Reusable State Fragments" block (around line 20) titled "Loop Template Inheritance via `from:`", showing one parent + child example and the merge rules.
   - `docs/generalized-fsm-loop.md` — append an "Inheritance pattern" example alongside the existing patterns (fix-until-clean, drive-metric, etc.).
   - No `templates/` loop YAML exists; skip that bullet.
   - `skills/review-loop/SKILL.md` and `skills/create-loop/SKILL.md` — add a one-line note: "Loops with `from:` are validated after merge resolution; the materialized loop is what the validator and diagrams see."
8. **Test plan** — model after `scripts/tests/test_fsm_fragments.py` (1080+ lines, comprehensive fixture-based tests using `tmp_path` and inline YAML strings). Either add to that file or create `scripts/tests/test_fsm_inheritance.py`. Cover:
   - Simple inheritance (child overrides parent state's `action`).
   - Deep override (child overrides nested `evaluate.target`, parent's `evaluate.type` survives).
   - Top-level field override (`description`, `category`, `labels`).
   - Routing override (child redefines `on_no` for one state; parent's `on_yes` for that state survives).
   - Multi-level chain (`grandchild → child → parent`).
   - Circular chain detection (A → B → A) raises `ValueError` containing the chain path.
   - Missing parent raises `FileNotFoundError` (same surface as `resolve_loop_path`).
   - `from:` combined with `import:`/`fragments:` (parent has fragments, child uses them; child has fragments, parent does not).
   - End-to-end: load a child via `load_and_validate` and assert the resulting `FSMLoop` matches a hand-written equivalent.

## Acceptance Criteria

- [ ] Loop YAML accepts an optional top-level `from:` field referencing another loop by name.
- [ ] Loader resolves `from:` recursively, merging parent states with child overrides before validation.
- [ ] Circular `from:` chains produce a clear error, not a stack overflow or silent hang.
- [ ] At least 2 existing loops are refactored to use `from:` and remain functionally identical (passes existing tests / `ll-loop validate`).
- [ ] Transition merge policy is documented (default: replace, with explicit opt-in for append) and covered by tests.
- [ ] `/ll:review-loop` and FSM diagram tools work on inherited loops.

## Impact

- **Priority**: P3 - Quality-of-life improvement; reduces YAML bloat but no current loop is blocked without it.
- **Effort**: Medium - Loader change + cycle detection + merge policy + refactoring 2 sample loops + tests.
- **Risk**: Medium - Affects all loop loading; bugs would silently mis-resolve states. Mitigated by deterministic resolution and running existing tests through the materialized loop.
- **Breaking Change**: No - `from:` is opt-in; loops without it behave unchanged.

## Open Questions

- ~~Should `from:` resolve only against the same directory, or also across extension paths (`built-in-loops/` vs. project loops)?~~ **Resolved (refine-issue):** reuse `resolve_loop_path()` at `scripts/little_loops/cli/loop/_helpers.py:93`, which already searches project `loops_dir` first then falls back to the bundled built-in `scripts/little_loops/loops/` directory. Same precedence as everything else.
- ~~Default transition merge: replace (predictable) or append (less surprising for additive cases)? Both have foot-guns.~~ **Resolved (refine-issue):** there is no `transitions:` list in this codebase; routing uses scalar `on_*` shorthand and a `route:` dict on `StateConfig` (`schema.py:230-256`). Scalars naturally override via `_deep_merge`; the `route:` dict deep-merges by verdict. No special flag needed for v1. Add `route_replace: true` later only if a real use case demands a wholesale verdict-table reset.
- Do we need a "base loop" convention (e.g., `lib/apo-base.yaml`) that is never run directly, only inherited from? **Recommendation (refine-issue):** yes — place inheritance-only bases under `scripts/little_loops/loops/lib/` (the existing fragment library directory), and have `ll-loop list`/builtin discovery skip files under `lib/` so they are never offered as runnable loops. Verify the discovery logic does this already; if not, add a one-liner exclusion.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/validation.py` — add `resolve_inheritance(...)` call at line 562 (just before the existing `resolve_fragments` call) and add `"from"` to `KNOWN_TOP_LEVEL_KEYS` at line 78.
- `scripts/little_loops/fsm/fragments.py` — add the new `resolve_inheritance(data, loop_dir, _seen=())` function alongside the existing `_deep_merge` and `resolve_fragments`. Reuse `_deep_merge` directly; do not duplicate it.
- `scripts/little_loops/fsm/schema.py` — **optional**: no change needed if `from:` is stripped during resolution. Only add a `from_: str | None` field on `FSMLoop` if we want the materialized loop to remember its parent for diagnostic display.
- `scripts/little_loops/loops/lib/apo-base.yaml` — **new file** (proof-of-value): shared APO skeleton.
- `scripts/little_loops/loops/apo-beam.yaml`, `scripts/little_loops/loops/apo-textgrad.yaml` — **refactor to** `from: apo-base`. Other APO variants can follow.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/_helpers.py:117` — `load_loop()` calls `load_and_validate()`. No change required; picks up the new resolution automatically.
- `scripts/little_loops/cli/loop/_helpers.py:131` — `load_loop_with_spec()` returns the raw spec separately. No change for v1; consider exposing a resolved-spec variant later if a caller needs it.
- `scripts/little_loops/cli/loop/run.py:105` — invokes `resolve_loop_path` then `load_and_validate`. Picks up resolution automatically.
- `scripts/little_loops/cli/loop/config_cmds.py:20` — `cmd_validate` calls `resolve_loop_path` → `load_and_validate`. Automatically validates the merged loop.
- `scripts/little_loops/cli/loop/info.py:634, 882` — diagram/info commands. Operate on the resolved `FSMLoop`; no change.
- `scripts/little_loops/fsm/executor.py:410` — already lazy-imports `resolve_loop_path` for sub-loop calls. No change.

### Similar Patterns (Reference Implementations)

- `scripts/little_loops/fsm/fragments.py:41-61` — `_deep_merge` (reuse directly).
- `scripts/little_loops/fsm/fragments.py:64-144` — `resolve_fragments` (model for the new `resolve_inheritance` function: same shape, same loop_dir parameter, same "expand-then-strip" idiom).
- `scripts/little_loops/cli/loop/_helpers.py:93-114` — `resolve_loop_path` (reuse for parent lookup, including the built-in fallback).

### Tests

- `scripts/tests/test_fsm_fragments.py` — model file (1080+ lines of fixture-based loader tests using `tmp_path` and inline YAML strings).
- `scripts/tests/test_fsm_validation.py` — model for end-to-end `load_and_validate` integration tests.
- **New**: `scripts/tests/test_fsm_inheritance.py` — covers all cases listed in Implementation Steps step 8.
- `scripts/tests/test_builtin_loops.py` — re-run after refactoring APO variants to confirm they still load and validate identically.

### Documentation

- `docs/guides/LOOPS_GUIDE.md` — new "Loop Template Inheritance" section after the existing "Reusable State Fragments" block.
- `docs/generalized-fsm-loop.md` — add an inheritance pattern example.
- `skills/review-loop/SKILL.md`, `skills/create-loop/SKILL.md` — one-line note that `from:` is resolved before validation/diagrams.

### Configuration

- No `.ll/ll-config.json` schema change required — `from:` is loop YAML, not project config.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM loop architecture — extension point for loader changes |

## Labels

feature, loops, fsm, yaml, loader, inheritance, captured

## Session Log
- `/ll:ready-issue` - 2026-05-02T01:23:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8b5d0503-0ff9-4660-9753-3a6da844502e.jsonl`
- `/ll:confidence-check` - 2026-05-01T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d63e8ea-5e14-4a5d-8d02-e5160454b094.jsonl`
- `/ll:refine-issue` - 2026-05-01T20:58:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1a27e94-952b-4a2d-adc7-4cec048a5642.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:format-issue` - 2026-05-01T17:38:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1483ec77-4cf9-4aca-8312-065f15a52a5f.jsonl`
- `/ll:capture-issue` - 2026-05-01T17:30:19Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0010190c-509e-453e-bb85-c00575d1e590.jsonl`

---

## Status

**Open** | Created: 2026-05-01 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, 2026-05-01): Cross-reference with FEAT-1283 (`learning` FSM state). FEAT-1308 proposes states as a YAML mapping (`states.<name>: ...` with deep-merge by name), while FEAT-1283's example uses a YAML list (`states: - name: ...`). The `from:` deep-merge semantics in this issue REQUIRE the mapping form. Resolve as follows: pin the canonical states schema to the mapping form. FEAT-1283 must declare its `learning` state under the same shape FEAT-1308 inherits from. Whichever issue lands first MUST settle this — do not ship the inheritance loader against an ambiguous schema.

Cross-reference with FEAT-1310 (verify-issue-loop generator): once `from:` is available, FEAT-1310-generated YAMLs SHOULD inherit a base verify loop (e.g. `from: verify-issue-base`) instead of emitting fully-expanded ~100-line files.
