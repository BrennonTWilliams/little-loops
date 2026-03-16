---
id: FEAT-754
priority: P3
type: FEAT
status: open
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 97
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
- `loops/issue-refinement.yaml` — Existing real-world multi-skill loop (uses `capture`, chained routing, modulo commit counter)
- `loops/fix-quality-and-tests.yaml:9-81` — Uses `llm_structured` + `exit_code` evaluators; `on_partial` routing variant
- `loops/dead-code-cleanup.yaml:61-78` — Canonical `check_concrete` pattern reading `test_cmd` from `ll-config.json`
- Guide's "Worked Example" section (`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:474-544`) — Canonical multi-item YAML to extract into a real file

### Guide Reference Points
- "See Also" section to update: `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:575-579`
- Phase ordering table: `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:412-420`
- Single-shot Variant A: `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:165-207`
- Multi-item Variant B with `max_retries`: `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:211-273`
- `check_mcp` pattern: `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:320-352`
- `check_skill` pattern: `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:376-406`
- `check_stall` pattern: `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:446-455`

### Validation Path Resolution
- `ll-loop test loops/examples/harness-single-shot.yaml` — uses `resolve_loop_path()` at `scripts/little_loops/cli/loop/_helpers.py:119`; checks project `loops_dir` first, then built-in `loops/` directory
- Structural validation logic: `scripts/little_loops/fsm/validation.py:274-386`
- `cmd_test()` implementation: `scripts/little_loops/cli/loop/testing.py:12`

### Notable: check_mcp and check_skill are guide-only
Neither `mcp_result` nor skill-as-judge (`check_skill` as `slash_command + llm_structured`) appear in any existing `loops/*.yaml` — they exist only in the guide. The example files will be the first real-file instances of these patterns.

### Tests
- `ll-loop test loops/examples/harness-single-shot.yaml` — Validate YAML structure and terminal reachability
- `ll-loop test loops/examples/harness-multi-item.yaml` — Same for multi-item variant

## Implementation Steps

1. Create `loops/examples/` directory
2. Author `loops/examples/harness-single-shot.yaml` (Variant A):
   - Pattern: `execute → check_stall → check_concrete → check_semantic → check_invariants → done`
   - Use `check_concrete` pattern from `loops/dead-code-cleanup.yaml:61-78` (reads `test_cmd` from `ll-config.json`)
   - Use `llm_structured` for `check_semantic` following `loops/fix-quality-and-tests.yaml:9-22`
   - Include `check_mcp` and `check_skill` as commented-out optional states with inline explanation
3. Author `loops/examples/harness-multi-item.yaml` (Variant B):
   - Pattern: `discover → execute → check_stall → check_concrete → check_mcp → check_skill → check_semantic → check_invariants → advance → discover` (cycle)
   - Extract and annotate from `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:474-544`
   - Add `max_retries: 3` + `on_retry_exhausted: advance` on `execute` state (Variant B pattern from guide lines 211-273)
4. Annotate both YAML files with `# EXAMPLE:` comments explaining each state's pedagogical purpose
5. Validate: `ll-loop test loops/examples/harness-single-shot.yaml` (uses `testing.py:12`, `validation.py:274-386`)
6. Validate: `ll-loop test loops/examples/harness-multi-item.yaml`
7. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:575-579` ("See Also") to reference both new files

## API/Interface

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

All harness phase patterns below are derived from `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` and existing `loops/*.yaml` files.

**Variant A — Single-Shot (`harness-single-shot.yaml`):**
```yaml
name: "harness-single-shot"
description: "Example: wrap a skill in quality gates (no discovery loop)"
initial: execute
max_iterations: 5
timeout: 3600

states:
  execute:
    action: "/ll:manage-issue FEAT-NNN"
    action_type: slash_command
    max_retries: 3
    on_retry_exhausted: done
    next: check_stall

  check_stall:
    action: "echo 'checking stall'"
    action_type: shell
    evaluate:
      type: diff_stall
      max_stall: 2
    on_yes: check_concrete     # progress detected
    on_no: done                # stalled — give up

  check_concrete:
    action: |
      CMD=$(python3 -c "
      import json, pathlib
      p = pathlib.Path('.claude/ll-config.json')
      cfg = json.loads(p.read_text()) if p.exists() else {}
      print(cfg.get('project', {}).get('test_cmd', 'pytest'))
      ")
      eval "$CMD" 2>&1
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: check_semantic
    on_no: execute

  check_semantic:
    action: "Summarize what was changed."
    action_type: prompt
    evaluate:
      type: llm_structured
      prompt: |
        Did the skill complete its task successfully with meaningful changes?
        Return "yes" only if clearly successful.
        Return "no" if clearly failed or incomplete.
        Return "partial" if ambiguous.
    on_yes: check_invariants
    on_no: execute
    on_partial: check_semantic

  check_invariants:
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: done
    on_no: execute

  done:
    terminal: true
```

**Variant B — Multi-Item (`harness-multi-item.yaml`) key structure:**
```yaml
name: "harness-multi-item"
description: "Example: process a list of items with full harness evaluation"
initial: discover
max_iterations: 200
timeout: 14400

states:
  discover:
    action: "ll-issues list --status open --format id | head -1"
    action_type: shell
    capture: current_item
    evaluate:
      type: exit_code
    on_yes: execute
    on_no: done

  execute:
    action: "/ll:manage-issue ${captured.current_item.output}"
    action_type: slash_command
    max_retries: 3
    on_retry_exhausted: advance
    next: check_stall

  check_stall:           # diff_stall — detect no-op executions
    action: "echo 'checking stall'"
    action_type: shell
    evaluate:
      type: diff_stall
      max_stall: 2
    on_yes: check_concrete
    on_no: advance

  check_concrete:        # cheapest gate first — exit_code from test_cmd
    # ... (same as single-shot)
    on_yes: check_mcp
    on_no: execute

  check_mcp:             # deterministic tool gate (optional — skip if no MCP server)
    action_type: mcp_tool
    action: "playwright/screenshot"
    params:
      url: "http://localhost:3000"
    capture: mcp_result
    route:
      success: check_skill
      tool_error: execute
      not_found: check_skill   # graceful skip when server absent
      timeout: execute

  check_skill:           # agentic user simulation (optional)
    action: "/ll:ready-issue ${captured.current_item.output}"
    action_type: slash_command
    timeout: 300
    evaluate:
      type: llm_structured
      prompt: |
        Did the skill report the issue as ready for implementation?
        Answer YES or NO.
    on_yes: check_semantic
    on_no: execute

  check_semantic:        # LLM quality judgment
    # ... (same as single-shot)
    on_yes: check_invariants
    on_no: execute

  check_invariants:      # diff size gate
    # ... (same as single-shot)
    on_yes: advance
    on_no: execute

  advance:
    action: "echo 'Item complete'"
    action_type: shell
    next: discover

  done:
    terminal: true
```

**Key schema facts for implementation** (`scripts/little_loops/fsm/validation.py:274-386`, `schema.py:379-471`):
- Required top-level fields: `name`, `initial`, `states`
- Every non-terminal state needs at least one of: routing (`on_yes`/`on_no`/`on_error`/`route`), `next`, or `terminal: true`
- At least one state must have `terminal: true` (ERROR if missing)
- `max_retries` requires paired `on_retry_exhausted`
- `params` only valid with `action_type: mcp_tool`
- `diff_stall` verdicts map to `on_yes` (progress) / `on_no` (stalled) / `on_error`
- `mcp_result` verdicts use full `route:` table with keys: `success`, `tool_error`, `not_found`, `timeout`

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
- `/ll:refine-issue` - 2026-03-16T02:10:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f28a12c5-6dae-4415-bc85-15a3d7f258d5.jsonl`
- `/ll:verify-issues` - 2026-03-15T19:08:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:format-issue` - 2026-03-15T19:06:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/121e4920-b20f-4051-b1be-b7df4a928d30.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fac56d79-3579-4d9f-92ac-185268df5162.jsonl`
