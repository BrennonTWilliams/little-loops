---
id: ENH-1878
title: Add queue_pop and queue_track fragment definitions and tests to common.yaml
type: ENH
priority: P3
status: done
completed_at: 2026-06-02 07:18:38+00:00
parent: ENH-1875
size: Small
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1878: Add queue_pop and queue_track fragment definitions and tests to common.yaml

## Summary

Add `queue_pop` and `queue_track` fragment definitions to `scripts/little_loops/loops/lib/common.yaml`, along with the corresponding test classes in `test_fsm_fragments.py`. This is the foundation layer for ENH-1879, which converts loop callers to use these fragments.

## Current Behavior

`queue_pop` and `queue_track` fragment definitions do not exist in `loops/lib/common.yaml`. Loops that implement the head-pop and skip-list-append idioms must inline the full shell boilerplate and evaluator config in every state, with no shared abstraction.

## Expected Behavior

`common.yaml` defines `queue_pop` (action_type: shell, evaluate.type: exit_code, description) and `queue_track` (action_type: shell, no evaluate, description) fragments. `TestQueuePopFragment` and `TestQueueTrackFragment` pass in `test_fsm_fragments.py`. The `test_all_common_yaml_fragments_have_description` coverage test passes automatically.

## Scope Boundaries

- This issue covers only adding the two fragment definitions to `common.yaml` and the corresponding test classes — no loop callers are modified here (that is ENH-1879 scope).
- Documentation updates to `docs/guides/LOOPS_GUIDE.md` and `skills/create-loop/reference.md` are in scope as wiring touchpoints (steps 6–7).

## Impact

- **Priority**: P3 — Foundation layer required before ENH-1879 can convert callers; no user-facing impact until callers convert.
- **Effort**: Small — Two YAML stanzas (~15 lines) and two test classes (~50 lines); models directly from existing `shell_exit` and `convergence_gate` patterns.
- **Risk**: Low — Additive-only change to `common.yaml`; existing fragments and tests are unaffected.
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `fragments`, `testing`

## Parent Issue

Decomposed from ENH-1875: Add queue_pop and queue_track fragments to common.yaml

## Implementation Steps

1. Add `queue_pop` fragment to `scripts/little_loops/loops/lib/common.yaml` — model after `shell_exit` (lines 15–21); add `action_type: shell`, `evaluate: {type: exit_code}`, and `description:` block documenting the head-pop idiom and what caller must supply

   ```yaml
   queue_pop:
     description: |
       Shell state that atomically pops the head of a queue file (head-1/tail-n+2/mv idiom).
       State must supply: action (the three-line pop shell script, plus any per-loop extras
       such as inflight sentinels or counter increments), on_yes (item popped), on_no (queue empty).
       Optionally: on_error, capture.
     action_type: shell
     evaluate:
       type: exit_code
   ```

2. Add `queue_track` fragment immediately after `queue_pop` in `common.yaml` — `action_type: shell`, no `evaluate` block, `description:` block documenting the skip-list append idiom and that caller must supply `next:`

   ```yaml
   queue_track:
     description: |
       Shell state that appends an ID to a skip or visited tracking file (echo >> idiom).
       No evaluator — this state always transitions unconditionally via next:.
       State must supply: action (echo "<ID>" >> <track-file>), next:.
     action_type: shell
   ```

3. Add `TestQueuePopFragment` and `TestQueueTrackFragment` classes to `scripts/tests/test_fsm_fragments.py` after `TestConvergenceGateFragment` (after line 1594), following the exact class structure at lines 1525–1594:

   **TestQueuePopFragment** (5 methods — mirrors TestConvergenceGateFragment):
   ```python
   class TestQueuePopFragment:
       """Tests that queue_pop exists in the real lib/common.yaml."""

       @staticmethod
       def _load_common_yaml() -> dict:
           import yaml
           lib_path = (
               Path(__file__).parent.parent
               / "little_loops" / "loops" / "lib" / "common.yaml"
           )
           with open(lib_path) as f:
               return yaml.safe_load(f)

       def test_queue_pop_defined_in_common_yaml(self) -> None:
           data = self._load_common_yaml()
           assert "queue_pop" in data["fragments"]

       def test_queue_pop_has_correct_action_type(self) -> None:
           data = self._load_common_yaml()
           assert data["fragments"]["queue_pop"]["action_type"] == "shell"

       def test_queue_pop_has_exit_code_evaluator(self) -> None:
           data = self._load_common_yaml()
           evaluate = data["fragments"]["queue_pop"].get("evaluate", {})
           assert evaluate.get("type") == "exit_code"

       def test_queue_pop_has_description(self) -> None:
           data = self._load_common_yaml()
           frag = data["fragments"]["queue_pop"]
           assert "description" in frag
           assert frag["description"].strip()

       def test_queue_pop_resolves_in_loop(self) -> None:
           loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
           raw = {
               "name": "test", "initial": "pop",
               "import": ["lib/common.yaml"],
               "states": {
                   "pop": {
                       "fragment": "queue_pop",
                       "action": "if [ ! -s /tmp/q.txt ]; then exit 1; fi; head -1 /tmp/q.txt",
                       "capture": "item",
                       "on_yes": "done",
                       "on_no": "done",
                   },
                   "done": {"terminal": True},
               },
           }
           result = resolve_fragments(raw, loops_dir)
           state = result["states"]["pop"]
           assert state["action_type"] == "shell"
           assert state["evaluate"]["type"] == "exit_code"
           assert "fragment" not in state
   ```

   **TestQueueTrackFragment** (4 methods — no evaluator test since no `evaluate:` block):
   ```python
   class TestQueueTrackFragment:
       """Tests that queue_track exists in the real lib/common.yaml."""

       @staticmethod
       def _load_common_yaml() -> dict:
           import yaml
           lib_path = (
               Path(__file__).parent.parent
               / "little_loops" / "loops" / "lib" / "common.yaml"
           )
           with open(lib_path) as f:
               return yaml.safe_load(f)

       def test_queue_track_defined_in_common_yaml(self) -> None:
           data = self._load_common_yaml()
           assert "queue_track" in data["fragments"]

       def test_queue_track_has_correct_action_type(self) -> None:
           data = self._load_common_yaml()
           assert data["fragments"]["queue_track"]["action_type"] == "shell"

       def test_queue_track_has_description(self) -> None:
           data = self._load_common_yaml()
           frag = data["fragments"]["queue_track"]
           assert "description" in frag
           assert frag["description"].strip()

       def test_queue_track_resolves_in_loop(self) -> None:
           loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
           raw = {
               "name": "test", "initial": "track",
               "import": ["lib/common.yaml"],
               "states": {
                   "track": {
                       "fragment": "queue_track",
                       "action": 'echo "item1" >> /tmp/visited.txt',
                       "next": "done",
                   },
                   "done": {"terminal": True},
               },
           }
           result = resolve_fragments(raw, loops_dir)
           state = result["states"]["track"]
           assert state["action_type"] == "shell"
           assert "evaluate" not in state  # unconditional — no evaluator
           assert "fragment" not in state
   ```

4. Verify `test_all_common_yaml_fragments_have_description` passes for both new fragments (no separate assertion needed — auto-covered once `description:` field is present)

5. Run `python -m pytest scripts/tests/test_fsm_fragments.py -v --tb=short` to confirm all fragment tests pass

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/guides/LOOPS_GUIDE.md` — add `queue_pop` and `queue_track` rows to the `#### lib/common.yaml — type-pattern fragments` table (Fragment | Description | Provides | Caller must supply)
7. Update `skills/create-loop/reference.md` — add `queue_pop` and `queue_track` rows to the `### lib/common.yaml fragments` table (Fragment | Provides | Caller must supply); this is the reference catalog read by the `/ll:create-loop` skill

## Success Metrics

- `queue_pop` and `queue_track` entries appear in `loops/lib/common.yaml` with correct `action_type` and `description` fields
- `TestQueuePopFragment` and `TestQueueTrackFragment` pass in `test_fsm_fragments.py`
- `test_all_common_yaml_fragments_have_description` passes

## Files to Modify

- `scripts/little_loops/loops/lib/common.yaml` — add two fragment entries
- `scripts/tests/test_fsm_fragments.py` — add two test classes

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — append `queue_pop` and `queue_track` after `convergence_gate` (currently line 122, end of file)
- `scripts/tests/test_fsm_fragments.py` — append `TestQueuePopFragment` and `TestQueueTrackFragment` after `TestConvergenceGateFragment` (after line 1594)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — section `#### lib/common.yaml — type-pattern fragments` contains a hand-maintained four-column table (`Fragment | Description | Provides | Caller must supply`) enumerating all common.yaml fragments; add rows for `queue_pop` and `queue_track` [Agent 2 finding]
- `skills/create-loop/reference.md` — section `### lib/common.yaml fragments` contains a hand-maintained three-column table (`Fragment | Provides | Caller must supply`) used by the `/ll:create-loop` skill during loop authoring; add rows for `queue_pop` and `queue_track` [Agent 2 finding]

### Resolution Engine (read-only)
- `scripts/little_loops/fsm/fragments.py:64` — `resolve_fragments()`: loads `import:` libs, merges namespaces, expands `fragment:` keys via `_deep_merge`
- `scripts/little_loops/fsm/fragments.py:41` — `_deep_merge(base, override)`: recursive merge; caller keys win; nested dicts (like `evaluate:`) recurse so fragment's `{type: exit_code}` and caller's `{target: X}` merge cleanly

### Auto-coverage
- `scripts/tests/test_fsm_fragments.py:1120` — `test_all_common_yaml_fragments_have_description` iterates all `fragments:` in common.yaml and asserts each has a non-empty `description`; new fragments are covered automatically once the `description:` field is present — no edits to this test needed

### Future Callers (ENH-1879 scope — reference only)
- `scripts/little_loops/loops/autodev.yaml:56` — `dequeue_next` state (current `fragment: shell_exit`; will convert to `fragment: queue_pop`)
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml:49` — `implement_next` state (current `fragment: shell_exit`; will convert to `fragment: queue_pop`)
- `scripts/little_loops/loops/autodev.yaml` — `skip_inflight` state (echo >> idiom; will convert to `fragment: queue_track`)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `skip_and_continue` state (echo >> idiom; will convert to `fragment: queue_track`)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — `skip_and_continue` state (echo >> idiom; will convert to `fragment: queue_track`)

## Reference Pattern

- `convergence_gate` (`common.yaml:111`) — evaluator fragment with two locked sub-keys (`type: convergence`, `direction: maximize`); caller supplies `evaluate.target`, `evaluate.tolerance`, and `route.*`
- `shell_exit` (`common.yaml:15`) — minimal shell fragment: `action_type: shell` + `evaluate.type: exit_code`; caller supplies `action`, `on_yes`, `on_no`
- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()` at line 64, `_deep_merge()` at line 41 (read to understand merge semantics and that `description:` is stripped at line 138 before merge)

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-02T07:16:49 - `0c6b620d-14a7-47c2-89f3-41dbefc28c15.jsonl`
- `/ll:wire-issue` - 2026-06-02T07:12:42 - `015f8a95-dcd9-4230-a0dd-858f0031b54d.jsonl`
- `/ll:refine-issue` - 2026-06-02T07:08:35 - `909f5fc3-6d99-4859-9b77-0ada988d311e.jsonl`
- `/ll:issue-size-review` - 2026-06-02T12:00:00Z - `073bc8f6-ad34-4a16-9ace-92422f178aac.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `55dc50ab-5d63-4eec-b340-4b6a490876d9.jsonl`
