---
id: FEAT-1737
type: FEAT
priority: P3
status: open
captured_at: "2026-05-27T05:02:23Z"
discovered_date: "2026-05-27"
discovered_by: capture-issue
---

# FEAT-1737: Accept EPIC Issues as Sprint Arguments in Skills and CLI Commands

## Summary

Add `SprintManager.load_or_resolve()` as a single-point resolver that accepts either a sprint name (existing file-based path) or an EPIC ID, transparently propagating to all sprint subcommands and skills. Resolution uses a union of the EPIC's `relates_to:` field (forward) and `parent:` on child issues (backward), filtered to active statuses. An optional `--save` flag on `ll-sprint run` materializes the resolved sprint YAML for inspect/edit-before-run workflows.

## Current Behavior

There is no way to pass an EPIC issue ID directly as a sprint argument. To run all issues under an EPIC, users must first create a sprint YAML file manually listing each child issue, then pass that file to `ll-sprint`. EPICs function as organizational containers but are not first-class execution units — the link between an EPIC and its runnable child set requires a manual intermediate step.

## Motivation

EPICs are already used as organizational containers for related issues via the `parent:` / `relates_to:` relationship. However, to run an EPIC's issues as a batch you currently need to first create a sprint file manually. Accepting EPICs directly as sprint arguments eliminates that friction and makes EPICs a first-class execution unit — the same way sprint files are.

## Expected Behavior

- `ll-sprint run EPIC-1234` resolves EPIC-1234's children and executes them in dependency order, exactly as if a sprint file listing those issues had been passed.
- Resolution is a union of forward lookup (`relates_to:` on the EPIC file) and backward scan (`parent: EPIC-NNN` on child issues), deduplicated and filtered to active statuses (`open`, `in_progress`, `blocked`).
- Skills that call `SprintManager` through the Python path (`/ll:create-sprint`, `/ll:review-sprint`) inherit EPIC resolution automatically — no separate wiring per skill.
- `ll-sprint run EPIC-1234 --save` also writes `.ll/sprints/epic-1234.yaml` before executing.
- If the EPIC has no active children, a clear message is printed and the runner exits cleanly (exit 0).
- Resume (`--resume`) works because `.sprint-state.json` tracks `sprint_name: epic-1234`.

## Acceptance Criteria

- [ ] `SprintManager.load_or_resolve(arg)` is implemented in `sprint.py` and handles both sprint names and `EPIC-NNN` IDs.
- [ ] All sprint subcommands (`run`, `show`, `analyze`, `delete`, `edit`) switch from `manager.load()` to `manager.load_or_resolve()`.
- [ ] Resolution uses the union of forward (`relates_to:`) and backward (`parent:`) lookups, deduplicated.
- [ ] Child issues are filtered to active statuses (`open`, `in_progress`, `blocked`) before execution.
- [ ] Resolved issues are ordered by priority, then dependency graph — matching existing sprint file behavior.
- [ ] When the EPIC has no active children, a clear message is printed and the runner exits cleanly (exit 0).
- [ ] When the EPIC ID does not exist, `load_or_resolve` returns `None` and the caller prints an informative error (exit non-zero).
- [ ] `ll-sprint run EPIC-NNN --save` writes `.ll/sprints/epic-{id}.yaml` before executing.
- [ ] `ll-sprint run EPIC-NNN --resume` works correctly using `sprint_name: epic-{id}` in state.
- [ ] Skills (`/ll:create-sprint`, `/ll:review-sprint`) work with EPIC IDs without additional changes.
- [ ] Existing sprint YAML file paths continue to work unchanged (no regressions).
- [ ] Unit tests cover `load_or_resolve` (file path, EPIC ID, not-found, empty children); integration test covers the `ll-sprint run EPIC-NNN` path.

## Use Case

A developer wants to work through all open issues under EPIC-1405 (EPIC Type Registration). Instead of generating a sprint file first, they run:

```bash
ll-sprint EPIC-1405
```

The runner resolves the child issues, orders them by dependency/priority, and processes them in sequence.

## Implementation Steps

1. **Add `SprintManager.load_or_resolve(arg, config)`** — single detection point in `scripts/little_loops/sprint.py`:
   - If `arg` matches `^EPIC-\d+$`, resolve it to an ephemeral `Sprint` object (name = `epic-{id}`, no YAML written)
   - Otherwise, fall through to the existing `load(arg)` file-based path
   - All subcommands that today call `manager.load(args.sprint)` switch to `manager.load_or_resolve(args.sprint)` — one-line change per subcommand (`run.py`, `show.py`, `manage.py`)

2. **Union resolution strategy** — inside `load_or_resolve`, collect children via two passes:
   - **Forward**: read `relates_to:` from the EPIC's own frontmatter
   - **Backward**: scan all issue files for `parent: EPIC-NNN` in frontmatter (authoritative source of truth)
   - Take the union; deduplicate; filter to active statuses (`open`, `in_progress`, `blocked`)
   - Order by priority field, then dependency graph (reuse existing `DependencyGraph` logic)

3. **Error handling** — `load_or_resolve` returns `None` (same contract as `load`) when:
   - The EPIC ID is not found → callers already handle `None` with a meaningful error message
   - The EPIC has no active children → return a `Sprint` with an empty `issues` list; the run path already handles this with a clean exit

4. **`--save` flag on `ll-sprint run`** — optional flag that materializes the resolved sprint YAML to `.ll/sprints/epic-{id}.yaml` before executing, enabling inspect/edit-before-run workflows without requiring it for normal use

5. **Wire into skills** — `/ll:create-sprint` and `/ll:review-sprint` skills: since they invoke `SprintManager` through the Python path, they inherit the capability automatically; update their argument descriptions to note EPIC ID support

6. **Tests** — unit test `load_or_resolve` (file path, EPIC ID, not-found cases); integration test `ll-sprint run EPIC-NNN` path; test `--save` flag materializes YAML correctly

## API/Interface

```python
# scripts/little_loops/sprint.py — SprintManager

def load_or_resolve(self, arg: str) -> "Sprint | None":
    """Load a sprint by name or resolve an EPIC ID to an ephemeral Sprint.

    Args:
        arg: Sprint name (file-based) or EPIC ID matching ^EPIC-\\d+$

    Returns:
        Sprint instance, or None if not found / EPIC not found
    """
    ...
```

CLI usage (no new flags required for basic use):

```bash
ll-sprint run EPIC-1694             # run all active children of EPIC-1694
ll-sprint run EPIC-1694 --save      # also write .ll/sprints/epic-1694.yaml first
ll-sprint run EPIC-1694 --dry-run   # preview execution plan without running
ll-sprint run my-sprint             # existing sprint YAML — unchanged behavior
```

## Impact

- **Priority**: P3 — Reduces friction for EPIC-driven workflows; not blocking but provides meaningful quality-of-life improvement for users who organize work under EPICs
- **Effort**: Medium — `SprintManager.load_or_resolve()` + union resolver + one-line subcommand updates; existing pipeline handles ordering/filtering; `--save` flag is additive
- **Risk**: Low — New detection branch; existing sprint file behavior is fully unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `sprint-runner`, `epics`, `cli`

## Status

**Open** | Created: 2026-05-27 | Priority: P3

## Session Log
- `rewrite` - 2026-05-27 - Redesigned to Option C (`SprintManager.load_or_resolve()` + union resolution + `--save` flag) after exploring Epic→Sprint mapping approaches
- `/ll:format-issue` - 2026-05-27T05:04:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c37f932-1d34-4311-ac57-0faf89f85130.jsonl`
- `/ll:capture-issue` - 2026-05-27T05:02:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c91edf22-5820-4f59-9f8d-4ab2ca66f171.jsonl`
