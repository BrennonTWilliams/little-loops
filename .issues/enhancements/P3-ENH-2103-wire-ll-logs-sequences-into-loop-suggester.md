---
id: ENH-2103
title: Wire `ll-logs sequences` output into `/ll:loop-suggester`
type: ENH
priority: P3
status: open
captured_at: "2026-06-12T00:00:00Z"
discovered_date: 2026-06-12
discovered_by: review-epic
parent: EPIC-1918
relates_to: [ENH-1919, FEAT-1309]
labels:
  - telemetry
  - ll-logs
  - loops
  - integration
---

# ENH-2103: Wire `ll-logs sequences` output into `/ll:loop-suggester`

## Summary

Update `/ll:loop-suggester` to optionally consume `ll-logs sequences` n-gram
output as an alternative (or supplement) to its current message-history
parsing path, so the sequences primitive shipped in ENH-1919 has a real
consumer.

## Motivation

EPIC-1918's first success metric requires "at least one existing feature
consumes an ll-logs telemetry subcommand as a real input." ENH-1919 (done)
built the `sequences` extraction primitive, but its intended consumer —
FEAT-1309's passive notification UX — is deferred. Today nothing consumes
the primitive at the loop-suggester integration layer: `/ll:loop-suggester`
still parses raw message history via `ll-messages`.

Wiring sequences into loop-suggester unblocks the telemetry pipeline without
requiring FEAT-1309's notification surface.

## Acceptance Criteria

- [ ] `/ll:loop-suggester` accepts a mode/flag (e.g. `--from-sequences`) that
  reads `ll-logs sequences` JSONL output instead of (or in addition to)
  `ll-messages` output
- [ ] Repeated command n-grams from sequences are mapped to loop-suggestion
  candidates with the same YAML-generation path as the existing flow
- [ ] Graceful degradation: missing/empty sequences output falls back to the
  message-history path with a notice
- [ ] Skill docs updated (`skills/loop-suggester/SKILL.md` argument table and
  trigger keywords)

## Integration Map

### Files to Modify
- `skills/loop-suggester/SKILL.md` — new input mode
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` (or relevant guide) — document the
  sequences-driven path

### Similar Patterns
- Existing `--from-commands` mode in loop-suggester — precedent for an
  alternative input source

## Impact

- **Priority**: P3 — satisfies EPIC-1918 success metric 1
- **Effort**: Small — input-mode addition to an existing skill
- **Risk**: Low — additive; existing paths unchanged
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-12 | Priority: P3
