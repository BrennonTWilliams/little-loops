---
id: EPIC-1745
title: Skill Quality & Discoverability
type: EPIC
priority: P3
status: open
captured_at: "2026-05-27T00:00:00Z"
discovered_date: "2026-05-27"
discovered_by: manual
labels: [epic, skills, context-engineering, routing]
relates_to: [ENH-1617, ENH-1618, ENH-977, ENH-494, BUG-1799, BUG-1800, ENH-1801, ENH-1802]
---

# EPIC-1745: Skill Quality & Discoverability

## Summary

Improve the health of the ll skill surface in four dimensions: **routing** (negative instructions that reduce misrouting between adjacent issue-lifecycle skills), **organization** (consolidate the five `audit-*` skills behind a single meta-skill entry point), **size enforcement** (500-line SKILL.md limit with companion files), and **CI enforcement** (an `ll-verify-skills` lint command that exits non-zero on violations). Together these reduce listing-budget waste, cut routing collisions, and make the skill surface maintainable at scale.

## Goal

When this epic is done:
- Tier 1 skill descriptions include explicit "Do NOT use for X — use Y instead" disambiguation, measurably reducing routing collisions on adjacent issue-lifecycle requests.
- The five `audit-*` skills are reachable through a single Tier 1 entry point, cutting the audit footprint in the listing budget from ~5 entries to 1.
- All `skills/*/SKILL.md` files are under 500 lines; overflowing content has been moved to companion files.
- CI rejects any new skill that exceeds 500 lines via `ll-verify-skills`.

## Motivation

The SEO plugin case study (referenced in ENH-1617 and ENH-1618) validated two patterns for Claude Code skill surfaces:
1. Negative routing instructions in descriptions reduce misrouting by ~90%.
2. A meta-skill dispatcher can replace a cluster of same-domain Tier 1 entries, shrinking listing-budget consumption while preserving full functionality through delegation.

ENH-494 (companion files) and ENH-977 (lint CLI) are the size-discipline side of the same story: skills that balloon in size consume context on every load, and without a lint gate the 500-line convention is not enforced.

## Scope

### In scope

- Negative routing instructions in the 14 Tier 1 skill descriptions (ENH-1617)
- `audit` meta-skill dispatcher for `audit-claude-config`, `audit-docs`, `audit-issue-conflicts`, `audit-loop-run`, `ll-audit-architecture` (ENH-1618)
- 500-line SKILL.md limit with overflow in companion files (ENH-494)
- `ll-verify-skills` CLI lint command and CI wiring (ENH-977, depends on ENH-494)

### Out of scope

- Changing skill _functionality_ — this epic only changes descriptions, organization, and size
- Consolidating non-audit skill clusters (separate follow-up if the pattern proves out)
- Skill metric dashboards or automated quality scoring

## Children

- **ENH-1617** — Add negative routing instructions to Tier 1 skill descriptions (depends on ENH-1618 landing first so audit dispatch is settled)
- **ENH-1618** — Consolidate audit-* skills into a single meta-skill entry point
- **ENH-494** — Enforce 500-Line SKILL.md limit with flat companion files
- **ENH-977** — Add `ll-verify-skills` CLI lint command (depends on ENH-494)
- **BUG-1799** — audit-issue-conflicts scans terminal (done/deferred) issues alongside active ones
- **BUG-1800** — audit-issue-conflicts `git add .issues/` stages unrelated untracked files
- **ENH-1801** — audit-issue-conflicts intra-batch design misses cross-theme conflicts at scale
- **ENH-1802** — audit-issue-conflicts re-appends Scope Boundary section on every run

## Implementation Order

1. **ENH-494** — establishes the companion-file convention and cap; prerequisite for ENH-977.
2. **ENH-977** — adds the lint gate once the convention is defined.
3. **ENH-1618** — consolidates audit skills; finalizes Tier 1 topology before descriptions are written.
4. **ENH-1617** — writes negative routing instructions; best done after Tier 1 shape is stable (ENH-1618 done).

## Integration Map

### Primary Files

- `skills/*/SKILL.md` — all children touch the skill surface; ENH-494 may split overlong skills
- `skills/audit/SKILL.md` — new meta-skill dispatcher created by ENH-1618
- `scripts/little_loops/cli/verify_skills.py` (new) — ENH-977
- `Makefile` / CI config — ENH-977 lint gate

### Tests

- `scripts/tests/test_ll_verify_skills.py` (new) — ENH-977
- `ll-verify-skill-budget` — should pass after ENH-1617/1618 reduce listing tokens

## Impact

- **Priority**: P3 — quality/ergonomics; not blocking
- **Effort**: Small per child; Medium aggregate (ENH-494 may require splitting several skills)
- **Risk**: Low — descriptions and file splits are non-breaking; meta-skill delegation is tested by the SEO case study
- **Breaking Change**: No — existing `/ll:<name>` invocations continue to work through the dispatcher

## Labels

`epic`, `skills`, `context-engineering`, `routing`

---

**Open** | Created: 2026-05-27 | Priority: P3

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: NEEDS_UPDATE** — ENH-494 and ENH-977 are now done (ll-verify-skills CLI exists). ENH-1801 and ENH-1802 are also done. Still open: ENH-1617 (negative routing instructions) and ENH-1618 (consolidate audit skills); skills/audit/ meta-skill does not exist yet.

## Session Log

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:verify-issues` - 2026-06-04T22:14:37 - `ab906855-95d7-4c4f-93f3-78db8cba1111.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:07 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:49:02 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:19 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`

**Update 2026-06-04 (re-verified)**:
- 4 of 8 children done: ENH-494 (500-line limit), ENH-977 (ll-verify-skills CLI), ENH-1801, ENH-1802.
- Remaining: ENH-1617 (negative routing), ENH-1618 (audit consolidation — `skills/audit/` does not exist), BUG-1799, BUG-1800 (both `open`).
- Body and Implementation Order sections should be updated to reflect completed foundational items (ENH-494 and ENH-977) and remaining work.

## Verification Notes (2026-06-05)

- **Child completion count outdated**: Prior verification notes say "4 of 8 children done"
  (ENH-494, ENH-977, ENH-1801, ENH-1802). Current check shows **6 of 8 done**: BUG-1799 and
  BUG-1800 have also been completed since last verification.
- **verify_skills.py path mismatch**: Epic specifies `scripts/little_loops/cli/verify_skills.py`
  but the actual implementation landed in `scripts/little_loops/cli/docs.py:237` as `main_verify_skills`.
- **Test file path**: Epic specifies `scripts/tests/test_ll_verify_skills.py` but actual test
  coverage is in `scripts/tests/test_cli_docs.py`.
- Remaining open children: ENH-1617, ENH-1618.
