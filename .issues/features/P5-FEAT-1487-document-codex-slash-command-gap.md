---
id: FEAT-1487
type: FEAT
priority: P5
status: open
captured_at: '2026-05-15T23:00:00Z'
discovered_date: 2026-05-15
discovered_by: manage-issue
parent: EPIC-1463
decision_needed: false
testable: false
---

# FEAT-1487: Update HOST_COMPATIBILITY.md Codex Slash-Command Entry

## Summary

Research in FEAT-1483 confirmed that Codex has no `.codex/prompts/` slash-command
surface — the prior `[^cmds]` footnote in `HOST_COMPATIBILITY.md` was speculative.
The Codex Skills API (`~/.codex/skills/`) covers both "skill" and "command"
use-cases. This issue updates the parity matrix and footnote to accurately reflect
the research outcome, and documents the gap as "skills only — no separate
slash-command registration."

## Current Behavior

`docs/reference/HOST_COMPATIBILITY.md` footnote `[^cmds]` references
`.codex/prompts/` as the Codex slash-command path. This path does not exist on
the Codex CLI. The "Slash-command discovery" row shows `✗` for Codex with
misleading guidance about `.codex/prompts/`.

## Expected Behavior

After this issue:
- `[^cmds]` footnote references `~/.codex/skills/` (not `.codex/prompts/`), notes
  that no separate slash-command surface exists, and points to FEAT-1486 for skill
  adaptation work.
- The "Slash-command discovery" parity matrix cell for Codex is updated to reflect
  "skills-only — no separate command surface; see FEAT-1486" (remains `✗` until
  a full skill bridge lands in FEAT-1486, or is documented as N/A).
- `hooks/adapters/codex/README.md` "Out of scope" note is updated to reflect the
  research outcome.

## Use Case

**Who**: Maintainer or contributor checking `HOST_COMPATIBILITY.md` for Codex slash-command support

**Context**: After FEAT-1483 confirmed Codex has no separate slash-command surface (only `~/.codex/skills/`), a developer looking up how to register commands on Codex finds `.codex/prompts/` referenced — a path that does not exist

**Goal**: Find accurate documentation so they route slash-command work through `~/.codex/skills/` and understand the FEAT-1486 scope for skill bridging

## Acceptance Criteria

- [ ] `docs/reference/HOST_COMPATIBILITY.md` `[^cmds]` footnote references
      `~/.codex/skills/` instead of `.codex/prompts/`
- [ ] The footnote mentions that no separate slash-command surface exists and
      points to FEAT-1486 for skill discovery work
- [ ] `hooks/adapters/codex/README.md` "Out of scope" line references
      `thoughts/research/codex-command-discovery.md` and notes the Skills API is confirmed

## API/Interface

N/A — documentation only; no public API or interface changes.

## Motivation

The `[^cmds]` footnote references `.codex/prompts/` — a path that does not exist on the Codex CLI. This misleads anyone looking up Codex slash-command support. FEAT-1483 already produced the research confirming `~/.codex/skills/` is the correct surface. Updating two files closes the accuracy gap at zero runtime risk.

## Proposed Solution

1. In `docs/reference/HOST_COMPATIBILITY.md`, locate the `[^cmds]` footnote definition and replace `.codex/prompts/` with `~/.codex/skills/`; add a sentence: "No separate slash-command surface exists; see FEAT-1486 for skill-bridge work."
2. Check the "Slash-command discovery" parity matrix row for Codex and ensure the `✗` cell note is consistent with the updated footnote.
3. In `hooks/adapters/codex/README.md`, update the "Out of scope" bullet referencing slash-commands to cite `thoughts/research/codex-command-discovery.md` and note the Skills API path is confirmed.

## Integration Map

### Files to Modify

- `docs/reference/HOST_COMPATIBILITY.md` — `[^cmds]` footnote revision; "Slash-command discovery" parity matrix cell note
- `hooks/adapters/codex/README.md` — "Out of scope" line update

### Dependent Files (Callers/Importers)

- N/A — documentation only; no runtime code references these footnotes

### Similar Patterns

- N/A — no other footnotes reference CLI paths that need verification

### Tests

- N/A — documentation change; `ll-check-links` can verify no broken anchors are introduced

### Documentation

- `thoughts/research/codex-command-discovery.md` — primary research source confirming `~/.codex/skills/` and absence of `.codex/prompts/`

### Configuration

- N/A

## Implementation Steps

1. Update `[^cmds]` footnote in `docs/reference/HOST_COMPATIBILITY.md` (`.codex/prompts/` → `~/.codex/skills/`)
2. Add inline note to the "Slash-command discovery" Codex cell referencing the footnote
3. Update `hooks/adapters/codex/README.md` "Out of scope" bullet
4. Grep for remaining `.codex/prompts/` references and update any stragglers

## Impact

- **Priority**: P5 — documentation accuracy fix; no runtime behavior change
- **Effort**: Small — two file edits, no code changes
- **Risk**: Low — documentation-only; no tests required
- **Breaking Change**: No

## Labels

codex, docs, host-compat

## Status

**Open** | Created: 2026-05-15 | Priority: P5


## Session Log
- `/ll:format-issue` - 2026-05-16T03:55:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/604904cc-0700-49df-ba1a-c56e52eb7fa1.jsonl`
- `/ll:format-issue` - 2026-05-16T03:45:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0311cf7-493f-4a79-bc9d-67419d002020.jsonl`
