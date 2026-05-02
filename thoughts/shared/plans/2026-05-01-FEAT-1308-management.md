# FEAT-1308: Loop YAML Template Inheritance via `from:` Field — Implementation Plan

## Summary

Add a `from:` top-level field to loop YAML files. Loader resolves the parent loop, deep-merges child overrides, then proceeds to fragment expansion and validation. Refactor 2 APO variants as proof-of-value.

## Design Decisions

1. **Resolution order in `load_and_validate`**: Inheritance must run *before* the required-fields check so a child can omit `initial`/`states` if the parent provides them. Order:
   1. Type check (data is dict)
   2. `resolve_inheritance(data, path.parent)` — NEW
   3. Required-fields check (`name`, `initial`, `states`)
   4. Unknown-keys check
   5. `resolve_fragments(data, path.parent)`
   6. `FSMLoop.from_dict(data)`

2. **`from:` key is stripped** by `resolve_inheritance` before returning. This means the unknown-keys check never sees it. We still add `"from"` to `KNOWN_TOP_LEVEL_KEYS` defensively in case any future code path checks unknown keys before inheritance resolution.

3. **Parent path resolution**: reuse `resolve_loop_path()` from `cli/loop/_helpers.py` with the child's `loop_dir` as the `loops_dir` argument. This gives us project-loop precedence with built-in fallback for free.

4. **Required field on child**: child must have `name:` (the loop is identified by its own name, not the parent's). Validate this explicitly before merging.

5. **Cycle detection**: pass `_seen: tuple[str, ...]` through recursion. Tuple preserves order for the error message.

6. **Merge semantics**: `_deep_merge(parent, child)` — child wins on scalars, dicts merge recursively, lists are replaced (existing `_deep_merge` semantics). The shorthand `on_*` fields are scalars and override naturally. The `route:` dict deep-merges by verdict.

## Phase 0: Write Tests (Red)

Create `scripts/tests/test_fsm_inheritance.py` with these test cases (model after `test_fsm_fragments.py`):

- `test_no_from_field_unchanged` — loop without `from:` returns identical dict.
- `test_simple_inheritance` — child overrides parent state's `prompt`/`action`.
- `test_deep_override_preserves_unmodified_parent_keys` — child overrides nested `evaluate.target`, parent's `evaluate.type` survives.
- `test_top_level_field_override` — child overrides `description`, `category`, `labels`.
- `test_route_dict_deep_merges_by_verdict` — child redefines `on_no` for one state; parent's `on_yes` for that state survives.
- `test_multi_level_chain` — `grandchild → child → parent` resolves correctly.
- `test_circular_chain_raises` — `A → B → A` raises `ValueError` with chain path in message.
- `test_self_reference_raises` — `A → A` raises `ValueError`.
- `test_missing_parent_raises` — `from: nonexistent` raises `FileNotFoundError`.
- `test_from_combined_with_fragments` — parent uses `import:`/`fragments:`, child inherits and uses parent's fragments.
- `test_child_must_have_name` — child without `name:` raises `ValueError`.
- `test_from_key_stripped_from_result` — resolved dict has no `from:` key.
- `test_load_and_validate_end_to_end` — load a child via `load_and_validate` and assert resulting `FSMLoop` matches a hand-written equivalent.
- `test_load_and_validate_no_unknown_key_warning_for_from` — `from:` does not trigger unknown-keys warning.

## Phase 1: Implement `resolve_inheritance`

File: `scripts/little_loops/fsm/fragments.py`

```python
def resolve_inheritance(
    raw_loop_dict: dict[str, Any],
    loop_dir: Path,
    _seen: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Resolve `from:` inheritance by deep-merging parent loop into child."""
    if "from" not in raw_loop_dict:
        return raw_loop_dict

    parent_name = raw_loop_dict["from"]
    if not isinstance(parent_name, str):
        raise ValueError(f"`from:` must be a string, got {type(parent_name).__name__}")

    if parent_name in _seen:
        chain = " -> ".join(_seen + (parent_name,))
        raise ValueError(f"Circular `from:` chain: {chain}")

    # Lazy import to mirror executor.py's pattern and avoid circular import.
    from little_loops.cli.loop._helpers import resolve_loop_path

    parent_path = resolve_loop_path(parent_name, loop_dir)
    with open(parent_path) as f:
        parent_data = yaml.safe_load(f)

    if not isinstance(parent_data, dict):
        raise ValueError(
            f"Parent loop '{parent_name}' is not a YAML mapping (got {type(parent_data).__name__})"
        )

    # Recurse into parent's own from: chain first
    parent_data = resolve_inheritance(parent_data, parent_path.parent, _seen + (parent_name,))

    # Deep-merge: parent is base, child overrides
    child_without_from = {k: v for k, v in raw_loop_dict.items() if k != "from"}
    merged = _deep_merge(parent_data, child_without_from)
    merged.pop("from", None)
    return merged
```

## Phase 2: Wire into `load_and_validate`

File: `scripts/little_loops/fsm/validation.py`

1. Add `"from"` to `KNOWN_TOP_LEVEL_KEYS` (line 78).
2. Import `resolve_inheritance` alongside `resolve_fragments`.
3. Insert `data = resolve_inheritance(data, path.parent)` immediately after the dict-type check (line 539) and *before* the required-fields check (line 541).

## Phase 3: Refactor 2 APO Loops

1. Create `scripts/little_loops/loops/lib/apo-base.yaml` with the shared APO skeleton (extracted from common parts of apo-beam and apo-textgrad).
2. Refactor `apo-beam.yaml` and `apo-textgrad.yaml` to use `from: lib/apo-base`.
3. Verify with `ll-loop validate <name>` and `python -m pytest scripts/tests/test_builtin_loops.py`.

**Note on path**: `resolve_loop_path` searches `<loops_dir>/<name>.yaml` — so `from: lib/apo-base` resolves to `<loops_dir>/lib/apo-base.yaml`. If `lib/` is a sibling of the YAML being loaded, `from: lib/apo-base` works correctly because `loop_dir` for the child is `scripts/little_loops/loops/`.

## Phase 4: Documentation

- `docs/guides/LOOPS_GUIDE.md` — new "Loop Template Inheritance via `from:`" section after the existing "Reusable State Fragments" block.
- `docs/generalized-fsm-loop.md` — append an "Inheritance pattern" example.
- `skills/review-loop/SKILL.md`, `skills/create-loop/SKILL.md` — one-line note that `from:` is resolved before validation/diagrams.

## Phase 5: Verification

Automated:
- [ ] `python -m pytest scripts/tests/test_fsm_inheritance.py -v` — all new tests pass.
- [ ] `python -m pytest scripts/tests/test_fsm_fragments.py -v` — fragment tests still pass.
- [ ] `python -m pytest scripts/tests/test_fsm_validation.py -v` — validation tests still pass.
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py -v` — all built-in loops still load (including refactored APO).
- [ ] `python -m pytest scripts/tests/ -q` — full suite green.
- [ ] `ruff check scripts/` — no new lint errors.
- [ ] `python -m mypy scripts/little_loops/fsm/` — no new type errors.

Manual smoke:
- [ ] `ll-loop validate apo-beam` — succeeds on refactored loop.
- [ ] `ll-loop validate apo-textgrad` — succeeds on refactored loop.

## Acceptance Criteria

- [x] Loop YAML accepts an optional top-level `from:` field referencing another loop by name.
- [x] Loader resolves `from:` recursively, merging parent states with child overrides before validation.
- [x] Circular `from:` chains produce a clear error, not a stack overflow or silent hang.
- [x] At least 2 existing loops are refactored to use `from:` and remain functionally identical.
- [x] Merge policy is documented (default: deep-merge with child wins on scalars; route dict deep-merges by verdict).
- [x] `/ll:review-loop` and FSM diagram tools work on inherited loops (no code change needed — they consume the post-`load_and_validate` `FSMLoop`).
