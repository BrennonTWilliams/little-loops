---
id: ENH-3670
type: ENH
title: Route skill and loop hand-built .ll/history.db paths through the target-aware
  store
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T23:04:53Z'
relates_to:
- BUG-3652
- ENH-3657
- ENH-3658
---

# ENH-3670: Route skill and loop hand-built .ll/history.db paths through the target-aware store

## Summary

Skills and a loop YAML hand-build the literal path `.ll/history.db` instead of going through `ll-*` CLIs or `little_loops.session_store`. Under `history.backend.provider: libsql` they either silently read nothing (`Path(...).exists()` is false) or `sqlite3.connect` creates an empty local shadow DB. Found in the sixth `/ll:advise` review of BUG-3652; no existing issue owns them (BUG-3652's AST gate is Python- and name-keyed, ENH-3658 covers Python hand-built paths and `context-monitor.sh`).

## Current Behavior

Affected sites (verify each before editing): `skills/update-docs/SKILL.md:102`, `skills/go-no-go/SKILL.md:155`, `skills/capture-issue/SKILL.md:186-204`, `skills/analyze-history/SKILL.md:145`, `skills/compact-session/SKILL.md:41` (`--db` default), `scripts/little_loops/loops/sft-corpus.yaml` (history.db join). `skills/improve-claude-md` CT-0 is owned by ENH-3657.

## Expected Behavior

[What should happen instead]

## Proposed Solution

Route each through an `ll-*` CLI or `little_loops.session_store` (target-aware), or make it degrade explicitly on a remote backend. Add a text gate over `skills/`, `commands/` and `loops/*.yaml` for the literal `.ll/history.db`, with a reasoned allowlist. Editing skills trips the mirror gates (`ll-adapt --host <gemini|kimi-code|qwen> --apply`); docs stay end-user-audience (`test_docs_audience_gate.py`); `SKILL.md` stays under 500 lines.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] Each listed site either reaches the remote store correctly or degrades cleanly under a remote backend, and creates no local `.ll/history.db`.
- [ ] The text gate passes with only reasoned allowlist entries.
- [ ] Mirror gates and `python -m pytest scripts/tests/` pass.

## Related

- BUG-3652, ENH-3657, ENH-3658.

## Status

**Open** | Created: 2026-09-29 | Priority: P3
