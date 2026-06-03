---
id: ENH-1889
type: ENH
priority: P4
status: open
captured_at: '2026-06-03T03:59:40Z'
discovered_date: '2026-06-03'
discovered_by: capture-issue
---

# ENH-1889: ll:init sets up Codex hooks adapter and trust-dialog guidance

## Summary

Running `/ll:init` in Claude Code now creates a `.codex/hooks.json` Codex CLI hook
adapter alongside the standard `ll` files. After init, Codex shows a hook-trust
dialog on the next session start; the user must choose **"Trust All"** (or review
individually) before little-loops hooks fire. The current init output surfaces this
as a bare note — this issue tracks whether the onboarding guidance is complete and
whether the next-steps section covers the trust step explicitly.

## Motivation

Users who run `/ll:init` and then switch to Codex CLI can miss the trust-dialog step
and wonder why hooks aren't firing. The init output already prints a `[Codex]` notice,
but it appears at the end of a long block and is easy to skim past. Ensuring the
guidance is prominent reduces "hooks not working" support questions.

## Current Behavior

`/ll:init` produces:

```
Created: .codex/hooks.json (Codex CLI hook adapter)

[Codex] .codex/hooks.json written. Codex will show a hook-trust dialog on next
session start — choose "Trust All" (or "Review Hooks").
Until you do, little-loops hooks will not fire (Codex silently skips untrusted hooks).
```

The trust-dialog step is mentioned but only at the foot of the full init output.

## Desired Behavior

- The trust-dialog note stays where it is (or moves into the **Next steps** list)
- Ideally the next-steps list includes a Codex-specific step: e.g.
  `5. (Codex) On next Codex session, accept the hook-trust dialog to activate hooks`
- No change needed if users consistently notice and act on the existing note — this
  is a UX polish item.

## Implementation Steps

1. Review `skills/init/SKILL.md` output template — locate where the next-steps block
   is rendered.
2. Add a conditional Codex next-step bullet: shown only when `.codex/hooks.json` was
   created (i.e. always for the current flow, gated if a `--no-codex` flag is added).
3. Optionally move the `[Codex]` notice inline with the "Created:" lines so it reads
   as part of the file-creation summary rather than an afterthought.
4. Update any related README / docs that describe the init flow.

## Session Log
- `/ll:capture-issue` - 2026-06-03T03:59:40Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a5977da-38c2-4bf3-b837-0ce39c29bad5.jsonl`

---
## Status

`open`
