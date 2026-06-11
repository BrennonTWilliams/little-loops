---
id: ENH-2068
title: Document built-in hooks in a user guide and fix orphaned guide nav
type: ENH
priority: P3
status: done
captured_at: '2026-06-09T00:00:00Z'
discovered_date: 2026-06-09
discovered_by: user-session
labels:
- docs
- hooks
- mkdocs
- onboarding
size: Medium
completed_at: '2026-06-09T00:00:00Z'
---

# ENH-2068: Document built-in hooks in a user guide and fix orphaned guide nav

## Summary

A documentation-gap review of `docs/guides/` and `docs/reference/` surfaced two
clean, unblocked wins: (1) three finished, valuable user guides existed on disk
but were never added to the published `mkdocs.yml` nav — so site visitors could
not reach them; and (2) the single highest-value *new* guide that no open issue
already owned was a user-facing reference for little-loops' built-in Claude Code
hooks (the prompt optimizer, context monitor, auto-handoff, analytics, issue-ID
guards, etc.) — behaviors that fire silently and had no consolidated "what is
happening and how do I turn it off" page. Both were completed this session,
along with relocating a stray internal audit artifact out of the published
guides directory and removing a dead link into the excluded `research/` tree.

## Motivation

The gap review was deliberately re-scoped against the open backlog before any
writing started. Two of the initially-highest-ranked guide ideas were
**demoted** because they overlap with in-flight work and would churn or
duplicate it:

- A **Parallel & Autonomous Processing** guide (`ll-auto` / `ll-parallel`) is
  partly owned by EPIC-1867's docs children (FEAT-2002 for the `ll-auto` FSM
  migration docs, ENH-1903 for documenting `ll-parallel` as the canonical
  substrate) and is gated on FEAT-1899 (the `ll-sprint` wave driver) landing —
  writing it now would document a mid-migration execution model.
- A **Context & Analytics** guide overlaps EPIC-1707 (turning `history.db` from
  a telemetry sink into an agent context layer), whose consumer surface is
  actively changing.

That left the **Built-in Hooks** guide as the top greenfield slot — no competing
owner, no migration churn, high trust value — and the nav-orphan fix as the
cheapest possible win (three completed guides made visible for zero new prose).

## Changes Made

### `mkdocs.yml`
- Added four entries to the Guides nav: **Decisions Log**, **Learning Tests**,
  **History & Sessions** (the three previously-orphaned guides), and the new
  **Built-in Hooks** guide.
- Repointed the `exclude_docs` entry from `guides/AUDIT_REPORT.md` to
  `development/USER_GUIDE_AUDIT_REPORT.md` after the move below (keeps the
  internal audit artifact out of the published site).

### `docs/index.md`
- Added index entries (with one-line descriptions) for the same four guides
  under the User Documentation section.

### `docs/guides/BUILTIN_HOOKS_GUIDE.md` (new)
- New ~330-line user guide documenting all 14 shipped hooks across the 6
  lifecycle events (SessionStart → UserPromptSubmit → PreToolUse → PostToolUse →
  Stop → PreCompact). For each hook: observable effect, exact config gate key +
  fresh-install schema default, what the user sees, and whether it can
  block/deny a tool call or return exit-2 feedback.
- Includes: an adapter→handler architecture paragraph, a lifecycle "at a glance"
  table, a "Safe by Default" section (opt-in vs. on-by-default behaviors), a
  "Turning Hooks Off" section, and a config-key→hook reference table.
- Every behavior and default was verified against the actual hook scripts under
  `hooks/` and against `config-schema.json` defaults (not inferred). Noted that
  this repo's own `.ll/ll-config.json` tunes some defaults (e.g.
  `analytics.enabled: true`, `context_monitor.auto_handoff_threshold: 50`).

### `docs/guides/AUDIT_REPORT.md` → `docs/development/USER_GUIDE_AUDIT_REPORT.md`
- `git mv` of an internal, dated user-guide audit artifact out of the
  user-facing guides directory into developer docs.

### `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`
- Removed the See-Also hyperlink into `../research/Towards-Direct-Evaluation-of-Harness-Optimizers.md`
  (the `research/` tree is excluded from the published site, so the link was dead
  on the site). Kept the paper title as plain italic text so no information was
  lost. The external `anthropic.com/research/...` URL elsewhere was intentionally
  left untouched.

## Acceptance Criteria

- [x] All three previously-orphaned guides (Decisions Log, Learning Tests,
  History & Sessions) appear in `mkdocs.yml` nav and `docs/index.md`
- [x] New `BUILTIN_HOOKS_GUIDE.md` exists, is in the nav + index, and documents
  every hook in `hooks/hooks.json` with accurate config gates and defaults
- [x] `AUDIT_REPORT.md` relocated to `docs/development/` and still excluded from
  the published site
- [x] No internal links into `research/` remain in published docs
- [x] `ll-check-links -C docs` reports **zero** broken links in any touched file
  (remaining broken links are pre-existing external HTTP failures and links
  inside the excluded `research/` tree)

## Impact

- **Priority**: P3 — docs-only; high onboarding/trust value, zero code change
- **Effort**: Medium — one new guide + nav/index wiring + one move + one link fix
- **Risk**: Low — documentation only; link-checked

## Files Touched

- `mkdocs.yml`
- `docs/index.md`
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` (new)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`
- `docs/development/USER_GUIDE_AUDIT_REPORT.md` (moved from `docs/guides/AUDIT_REPORT.md`)

## Notes

Deferred (not filed, per user) — the two demoted guides remain real gaps to
revisit when their blockers land: the **Parallel & Autonomous** guide after
FEAT-1899 / ENH-1903, and the **Context & Analytics** guide once EPIC-1707's
consumer surface stabilizes. Also noted but out of scope: GETTING_STARTED leans
on `/ll:init` + `configure`, which ENH-1982 / EPIC-1978 are re-platforming —
avoid init-heavy doc rewrites until those land.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-10T04:34:53 - `f5268e1f-16b3-4c16-83a5-2edb8acbe645.jsonl`
