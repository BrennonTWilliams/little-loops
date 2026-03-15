---
id: FEAT-754
priority: P3
type: FEAT
status: open
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# FEAT-754: Add Example FSM Loops Demonstrating Automatic Harnessing

## Summary

Add built-in and/or example FSM loop YAML files to the `loops/` directory that demonstrate the Automatic Harnessing patterns described in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`. These examples would serve as ready-to-use templates showing single-shot and multi-item harness variants with all evaluation phases (tool gates, LLM-as-judge, diff invariants, MCP tool gates, skill-as-judge).

## Current Behavior

The guide at `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` documents the harness loop pattern in detail but contains only inline YAML code blocks as illustrations. The existing `loops/` directory has 14 real-world operational loops (e.g., `issue-refinement.yaml`, `docs-sync.yaml`) but none are structured as canonical harness demonstrations.

## Expected Behavior

One or more example harness loops exist in `loops/` (or a `loops/examples/` subdirectory) that:
- Illustrate Variant A (single-shot harness) and Variant B (multi-item harness)
- Show all supported evaluation phases in sequence: `check_concrete` → `check_mcp` → `check_skill` → `check_semantic` → `check_invariants`
- Include `check_stall` demonstrating stall detection for prompt-based skills
- Are referenced from the guide's "See Also" section
- Can be used directly via `ll-loop run loops/examples/harness-single-shot.yaml` or as copy-paste starting points

## Use Case

**Who**: Developer adopting FSM-based automatic harnessing for issue refinement or code quality loops

**Context**: Reading `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` and wanting to apply the harness pattern to their own workflow

**Goal**: Copy or adapt a working YAML harness loop rather than authoring one from scratch

**Outcome**: Has runnable `loops/examples/harness-single-shot.yaml` and `loops/examples/harness-multi-item.yaml` files that demonstrate all evaluation phases and can be validated with `ll-loop test`

## Acceptance Criteria

- [ ] `loops/examples/harness-single-shot.yaml` exists and demonstrates Variant A (single-shot harness)
- [ ] `loops/examples/harness-multi-item.yaml` exists and demonstrates Variant B (multi-item harness)
- [ ] Both files include all evaluation phases in sequence: `check_concrete` → `check_mcp` → `check_skill` → `check_semantic` → `check_invariants`
- [ ] Both files include `check_stall` demonstrating stall detection for prompt-based skills
- [ ] `ll-loop test loops/examples/harness-single-shot.yaml` passes structural validation
- [ ] `ll-loop test loops/examples/harness-multi-item.yaml` passes structural validation
- [ ] Guide's "See Also" section references the new example files

## Motivation

The guide teaches the harness concept but users have no runnable reference to validate their understanding. Example loops lower the barrier to adopting harnessing — a user can inspect, copy, and adapt a working YAML rather than authoring one from scratch. This also makes the guide self-contained: the "Worked Example" section can link to a real file instead of embedding a long inline block.

## Proposed Solution

Create example harness loop files. Two approaches:

**Option A — `loops/examples/` subdirectory**: Add `harness-single-shot.yaml` and `harness-multi-item.yaml` as annotated examples. Update the guide's "See Also" to reference them.

**Option B — Built-in starter loops**: Promote example harnesses to first-class named loops (e.g., `harness-refine-issue.yaml`) alongside existing operational loops. Include a `# EXAMPLE` comment block at the top.

Option A keeps examples isolated; Option B makes them immediately actionable. Both can coexist.

## Integration Map

### Files to Modify
- `loops/` — Add new YAML files (examples subdirectory or root)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Update "See Also" section to reference new files
- `README.md` or `docs/` — Optionally mention example loops in the quickstart

### Dependent Files (Callers/Importers)
- `ll-loop run` — Must parse and execute the new YAML files without errors
- `ll-loop test` — Should validate example files pass structural checks

### Similar Patterns
- `loops/issue-refinement.yaml` — Existing real-world multi-skill loop to use as structural reference
- Guide's "Worked Example" section (lines 474–544) — Canonical YAML to extract into a real file

### Tests
- `ll-loop test loops/examples/harness-single-shot.yaml` — Validate YAML structure and terminal reachability
- `ll-loop test loops/examples/harness-multi-item.yaml` — Same for multi-item variant

## Implementation Steps

1. Create `loops/examples/` directory (or decide on root placement)
2. Extract the "Worked Example" YAML from the guide into `harness-refine-issue.yaml` as the canonical multi-item harness
3. Add a single-shot variant (`harness-single-shot.yaml`) demonstrating Variant A
4. Add comments/annotations to the YAML files to make them pedagogically useful
5. Run `ll-loop test` on each new file to confirm structural validity
6. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` "See Also" section with links to new files

## API/Interface

```yaml
# Example: loops/examples/harness-multi-item.yaml
name: "harness-refine-issue"
initial: discover
max_iterations: 200
# ... (all phases as documented in guide)
```

## Impact

- **Priority**: P3 - Improves developer experience and guide usability
- **Effort**: Small — The canonical YAML already exists in the guide; implementation is extraction + annotation
- **Risk**: Low — New files only; no code changes
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Primary guide this feature extends |
| `loops/issue-refinement.yaml` | Existing loop to use as structural reference |

## Labels

`feat`, `loops`, `harnessing`, `developer-experience`, `captured`

---

## Status

**Open** | Created: 2026-03-15 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-03-15T19:08:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:format-issue` - 2026-03-15T19:06:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/121e4920-b20f-4051-b1be-b7df4a928d30.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
