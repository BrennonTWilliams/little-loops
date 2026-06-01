---
id: FEAT-1857
type: FEAT
priority: P3
status: open
captured_at: '2026-06-01T17:35:32Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to: [FEAT-1810, FEAT-1737]
parent: EPIC-1864
---

# FEAT-1857: `/ll:scope-epic` — theme-to-EPIC decomposition skill

## Summary

Add a `/ll:scope-epic` skill that takes a high-level theme/goal description and produces (1) an EPIC issue file scoped to the theme and (2) 3–8 child issue stubs pre-wired with `parent: EPIC-NNN`. This is the upstream creation step that `/ll:capture-issue --parent` assumes already happened.

## Current Behavior

To start an EPIC-shaped initiative today the user must:

1. Manually compose an EPIC issue (or call `/ll:capture-issue "epic: ..."`).
2. Manually identify child scope.
3. Repeatedly call `/ll:capture-issue --parent EPIC-NNN ...` for each child.

There is no skill that decomposes a theme into the EPIC + skeleton children in one pass. `/ll:capture-issue` creates *one* issue at a time and `--parent` requires the EPIC to already exist.

## Expected Behavior

```
$ /ll:scope-epic "Harness Codex CLI as a full claude-p replacement"

[skill proposes]
EPIC-XXXX: Harness Codex CLI as a full claude-p replacement
  ├── FEAT-XXXX: Codex auth & session management
  ├── FEAT-XXXX: Model selection & defaulting
  ├── FEAT-XXXX: Streaming output adapter
  ├── FEAT-XXXX: Tool-use bridge
  └── ENH-XXXX: MCP server compatibility

Proceed? [y/n]
```

On confirm: writes all 6 files with wiring (`parent:` on children, `relates_to:` + `## Children` on the EPIC). User then runs `/ll:refine-issue` on each child as needed.

## Motivation

Theme-to-EPIC decomposition is currently the highest-friction step in starting any multi-issue initiative. Users either skip the EPIC and end up with orphan issues, or write the EPIC and skip the children (so `/ll:scan-codebase` discovers them as orphans later, requiring `/ll:link-epics` to wire them back in).

Capturing the decomposition once at the start — when the theme is freshest in the user's head — produces better-scoped children than discovering them piecewise weeks later.

## Proposed Solution

Skill flow:

1. **Accept theme** — natural-language description, optional file path to a goals doc.
2. **Decompose (LLM)** — propose EPIC summary + 3–8 child issues, each with type (FEAT/ENH/BUG), priority, and one-line summary. Hint that children should be **independently shippable** (mirror `/ll:issue-size-review`'s principle).
3. **Present plan** — table view with type, priority, summary. User can edit interactively (add/remove/reorder/retype) before committing.
4. **Allocate IDs** — sequential via `ll-issues next-id`.
5. **Write EPIC first** — full template, `## Children` section with all proposed children, `relates_to:` frontmatter populated.
6. **Write each child** — minimal template (mirror `--quick`), `parent: EPIC-NNN` frontmatter set.
7. **Stage all files**.
8. **Print next-step hint**: `/ll:refine-issue` on any child whose scope needs deepening.

**Boundary vs. FEAT-1810 (`goal-cluster`)**: `goal-cluster` *executes* a list of related goals through loops; `scope-epic` *creates* the issue files that represent those goals. They are upstream/downstream of each other and may share the decomposition LLM prompt.

## Integration Map

### Files to Modify
- `skills/scope-epic/SKILL.md` (new)
- `skills/scope-epic/templates.md` (new)
- `commands/help.md` — add listing
- `.claude/CLAUDE.md` — Commands & Skills section

### Dependent Files (Callers/Importers)
- `skills/capture-issue/SKILL.md` — adjacent flow; share `--parent` wiring logic from Phase 4c
- `skills/issue-size-review/SKILL.md` — share independently-shippable principle

### Similar Patterns
- `skills/capture-issue/SKILL.md` — file-write + git-add pattern; reuse Phase 4c wiring of EPIC `relates_to:` + `## Children`
- `skills/issue-workflow/SKILL.md` — multi-step LLM + commit flow

### Tests
- Snapshot test of decomposition output for a known theme (mock LLM)
- File-write verification: EPIC + N children written with correct `parent:` and `relates_to:` wiring

### Documentation
- `docs/guides/EPIC_GUIDE.md` — workflow: scope → review → ship
- `/ll:help` listing

### Configuration
- `epics.scope.min_children` (default 3)
- `epics.scope.max_children` (default 8) — beyond this, suggest sub-EPICs

## Implementation Steps

1. **Scaffold skill directory** — `skills/scope-epic/SKILL.md` with phases mirroring `capture-issue`.
2. **Decomposition prompt** — LLM proposes EPIC scope + child list as structured JSON.
3. **Interactive edit loop** — `AskUserQuestion` for confirm/edit/cancel.
4. **ID allocation + file writes** — EPIC first, children second, all wired.
5. **Share wiring code with `capture-issue`** — factor Phase 4c (EPIC update) into a shared helper if not already.
6. **Tests** — snapshot + wiring verification.
7. **Docs** — guide section + help listing.

## Impact

- **Priority**: P3 — Quality-of-life; not blocking but eliminates a multi-step manual flow.
- **Effort**: Medium — Reuses `capture-issue` writing + wiring; new LLM prompt + interactive UI.
- **Risk**: Low — Additive skill; no behavioral change to existing tools.
- **Breaking Change**: No

## Use Case

User opens little-loops with the goal "make our docs sweep automatic" and runs `/ll:scope-epic "Automatic docs sweep — detect drift, propose updates, verify links"`. Skill proposes EPIC-XXXX with 5 children (detection, proposal, verification, scheduling, reporting). User accepts. 6 issue files exist 30 seconds later, all wired. Today this would take 5+ manual `/ll:capture-issue` invocations and a separate EPIC creation step.

## Acceptance Criteria

- [ ] `/ll:scope-epic "<theme>"` proposes an EPIC + 3–8 children.
- [ ] User can edit/remove/retype proposed children before commit.
- [ ] On commit, EPIC file is written first with full `relates_to:` and `## Children` populated.
- [ ] Each child is written with `parent: EPIC-NNN` frontmatter.
- [ ] All files staged for git.
- [ ] Cancellation at the confirm step writes nothing.
- [ ] Theme that produces fewer than `min_children` proposals emits a warning ("this might be a single-issue task, consider `/ll:capture-issue`").
- [ ] Theme that produces more than `max_children` proposals suggests sub-EPIC decomposition.

## API/Interface

```bash
/ll:scope-epic "<theme description>"
/ll:scope-epic --from-doc thoughts/goals/feature-x.md
/ll:scope-epic "<theme>" --priority P2          # override default EPIC priority
```

No Python API.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `epics`, `skill`, `decomposition`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-01T17:44:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/756a4b19-3f84-45ba-b4ff-aeb860ba5ecf.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
