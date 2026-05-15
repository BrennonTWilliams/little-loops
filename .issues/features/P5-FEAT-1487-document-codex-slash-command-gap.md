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

## Acceptance Criteria

- [ ] `docs/reference/HOST_COMPATIBILITY.md` `[^cmds]` footnote references
      `~/.codex/skills/` instead of `.codex/prompts/`
- [ ] The footnote mentions that no separate slash-command surface exists and
      points to FEAT-1486 for skill discovery work
- [ ] `hooks/adapters/codex/README.md` "Out of scope" line references
      `thoughts/research/codex-command-discovery.md` and notes the Skills API is confirmed

## Integration Map

### Files to Modify

- `docs/reference/HOST_COMPATIBILITY.md` — `[^cmds]` footnote revision
- `hooks/adapters/codex/README.md` — "Out of scope" line update

## Labels

codex, docs, host-compat
