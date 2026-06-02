---
id: ENH-1814
title: Docs pass for `LEARNING_TESTS_GUIDE.md` and `LOOPS_GUIDE.md` covering the EPIC-1694 surface
type: ENH
priority: P3
status: open
captured_at: "2026-05-30T21:35:04Z"
discovered_date: "2026-05-30"
discovered_by: capture-issue
parent: EPIC-1694
relates_to: [EPIC-1694, FEAT-1695, FEAT-1696, FEAT-1692, FEAT-1697, FEAT-1738, FEAT-1739, FEAT-1743, FEAT-1813]
testable: false
---

# ENH-1814: Docs pass for `LEARNING_TESTS_GUIDE.md` and `LOOPS_GUIDE.md` covering the EPIC-1694 surface

## Summary

Refresh `docs/guides/LEARNING_TESTS_GUIDE.md` and `docs/guides/LOOPS_GUIDE.md`
so the full EPIC-1694 surface (four gate loops + `proof-first-task` wrapper +
feature flag + audit/migrate loops) is discoverable from documentation, not
just from `ll-loop list`. The epic explicitly defers this doc pass; without
it the feature is invisible to anyone reading the guides.

## Current Behavior

- `LOOPS_GUIDE.md` § API Adoption (lines 374–400) **already documents** the
  four gate loops (`ready-to-implement-gate`, `assumption-firewall`,
  `integrate-sdk`, `adopt-third-party-api`) and `proof-first-task`. This
  section is in good shape and only needs cross-links and (later) entries
  for `learning-tests-audit` and `migrate-sdk-version`.
- `LEARNING_TESTS_GUIDE.md` only cross-references `adopt-third-party-api`
  and `assumption-firewall` in a single line at the end (around line 210,
  in "Further Reading" / "For end-to-end workflows…"). The "Using Learning
  Tests in Loops" section does not enumerate the four gate entry points or
  explain when to pick each.
- Neither guide mentions the `learning_tests.enabled` feature flag
  (FEAT-1743) or recommends `proof-first-task` as the safe default
  wrapper for a developer new to the registry.

## Expected Behavior

- `LEARNING_TESTS_GUIDE.md § Using Learning Tests in Loops` lists the four
  gate entry points with one line each + a "when to pick this" sentence:
  - `ready-to-implement-gate` — when you already have an explicit target list
  - `assumption-firewall` — when you have an issue and want the gate to
    extract assumptions
  - `integrate-sdk` — when starting from an SDK discovery
  - `adopt-third-party-api` — when starting from docs
  - `proof-first-task` — the recommended wrapper around any impl loop
- `LEARNING_TESTS_GUIDE.md § Quick Start` mentions the feature flag
  (`learning_tests.enabled`) and recommends running through
  `proof-first-task` first.
- `LEARNING_TESTS_GUIDE.md § Troubleshooting` adds a bullet on bulk
  staleness management referencing `learning-tests-audit` (FEAT-1739) and
  `migrate-sdk-version` (FEAT-1813) — added once those loops ship; until
  then, a placeholder TODO is acceptable.
- `LOOPS_GUIDE.md § API Adoption` gains a cross-link to
  `LEARNING_TESTS_GUIDE.md` for the registry/lifecycle background and
  (once they ship) entries for `learning-tests-audit` and
  `migrate-sdk-version` in the same section.
- `LEARNING_TESTS_GUIDE.md` and `LOOPS_GUIDE.md § API Adoption` are
  bidirectionally cross-linked.

## Motivation

- **EPIC-1694 explicitly defers this doc pass.** Without it the gate stack
  ships but stays invisible to anyone reading the guides — the registry
  becomes "infrastructure agents could use" rather than "the default safe
  path for unfamiliar APIs."
- **Discoverability beats opt-in.** A developer reading the guide is one
  step from typing the right loop name; a developer reading only
  `ll-loop list` has to know what they're looking for.
- **Single source of truth for the feature flag.** FEAT-1743 added the
  flag but documenting it in the guides is what makes it a first-class
  knob teams know exists.

## Scope Boundaries

- **In scope**:
  - Expand `LEARNING_TESTS_GUIDE.md § Using Learning Tests in Loops` with
    the four gate entry points + `proof-first-task` recommendation.
  - Add a Troubleshooting bullet for bulk staleness management
    (placeholder until FEAT-1739 / FEAT-1813 land).
  - Mention `learning_tests.enabled` in the Quick Start.
  - Bidirectional cross-links between `LEARNING_TESTS_GUIDE.md` and
    `LOOPS_GUIDE.md § API Adoption`.
- **Out of scope**:
  - Rewriting the four-phase workflow section (already in good shape).
  - New diagrams or screenshots.
  - Per-loop deep dives (those belong in the loop docs / skill docs, not
    the guide).
  - Updating `LOOPS_GUIDE.md § API Adoption` content beyond
    cross-links — the four loops are already documented there.

## Acceptance Criteria

- `LEARNING_TESTS_GUIDE.md § Using Learning Tests in Loops` enumerates all
  four gate loops + `proof-first-task` with a one-line "when to pick"
  guide for each.
- `LEARNING_TESTS_GUIDE.md § Quick Start` mentions the
  `learning_tests.enabled` feature flag and `proof-first-task` as the
  recommended starting wrapper.
- `LEARNING_TESTS_GUIDE.md § Troubleshooting` references
  `learning-tests-audit` (or a TODO placeholder if FEAT-1739 hasn't
  shipped) for bulk staleness management.
- `LOOPS_GUIDE.md § API Adoption` and `LEARNING_TESTS_GUIDE.md` link to
  each other.
- `ll-check-links` reports no broken links introduced by this change.
- `ll-verify-docs` (if it covers these guides) passes.

## Impact

- **Priority**: P3 — High value for adoption; low risk.
- **Effort**: Small — additive edits to two existing guides; no new files,
  no schema changes.
- **Risk**: Low — docs-only change; nothing in production code touches
  these guides.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/LEARNING_TESTS_GUIDE.md` | Primary target of this pass |
| `docs/guides/LOOPS_GUIDE.md` § API Adoption | Cross-link target; minor edits |

## Labels

`enh`, `docs`, `learning-tests`, `loops`, `adoption`, `captured`

---

**Open** | Created: 2026-05-30 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-06-02T22:48:35 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-30T21:35:04Z - `f3ee23bc-341c-48d2-b09f-f34e658c7031.jsonl`
