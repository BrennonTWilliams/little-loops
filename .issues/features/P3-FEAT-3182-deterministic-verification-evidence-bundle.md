---
id: 3182
title: Deterministic verification-evidence bundle from verify-loop runs
type: FEAT
priority: P3
status: open
parent: EPIC-2087
discovered_date: '2026-08-15'
labels:
- path-a
- verification
- audit-evidence
---

## Summary

Export a reproducible evidence bundle from `verify-loop` / `adversarial-verify-loop` runs, assembled **only** from deterministic sources — git predicates, `history.db` records, and on-disk run artifacts. No LLM self-evaluation contributes to the attestation.

## Motivation

An attestation that a change was verified is only as trustworthy as its weakest input. A bundle assembled from git refs, `history.db` rows, and run-directory files can be re-checked by anyone holding the repo. A bundle that folds in a model's own assessment of its own work inherits the self-evaluation bias MR-1 documents, and cannot be handed to a reviewer who did not run the loop.

Two consumers need the first kind and cannot use the second: a team reviewing agent-produced changes at merge time, and any process that has to answer "what was checked, and how do you know" months after the run.

## Acceptance Criteria

- Bundle contents are enumerable, and each entry traces to a deterministic source (git ref/diff, `history.db` row, or run-directory file).
- **Reproducible**: re-running the exporter over unchanged inputs produces byte-identical output.
- Any LLM-produced content included for context is segregated and labeled non-evidentiary.
- A run whose evidence is incomplete produces an explicit gap list rather than a bundle that looks complete.
- The bundle is readable without little-loops installed — it is evidence, not a proprietary format.

## Notes

_2026-08-28, unparented-issues review:_ downgraded P2 → P3 and parented under
EPIC-2087 (Loop Harness Quality & Evaluation Tooling). The motivation and ACs
are sound, but the issue has had no refine/wire/confidence pass — no proposed
solution, no integration map, no file references. **Run `/ll:refine-issue
FEAT-3182` before scheduling implementation**; at minimum it must identify the
verify-loop run artifacts and `history.db` tables the bundle draws from, and
the exporter's CLI surface.
