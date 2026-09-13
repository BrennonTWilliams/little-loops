---
id: 3470
title: "Wire credential scan into the FEAT-3182 EvidenceBundle"
type: ENH
priority: P1
status: open
discovered_date: '2026-09-13'
parent: ENH-3466
depends_on: [3469]
labels:
- goal-7,security,verification
decision_needed: false
---

# ENH-3470: Wire credential scan into the FEAT-3182 EvidenceBundle

## Summary

Add a `credential_scan` entry (`{tool, version, rules_sha, scanned_at,
hits}`) to `EvidenceBundle` (`scripts/little_loops/cli/loop/evidence.py`),
backed by the credential scanner built in ENH-3469 (blocked on it — this
issue calls the scanner, it does not build it). This is the actual
FEAT-3182 extension: the bundle re-reads its own evidentiary data and fails
on a credential/PII pattern match rather than trusting the upstream
redaction pass.

## Parent Issue

Decomposed from ENH-3466: Goal 7 — credential-scan verification primitive
(FEAT-034 extension). This child covers wiring the scanner (ENH-3469) into
the evidence bundle and resolving the bundle-shape conflicts that only
exist at the integration point.

## Design

- `EvidenceEntry.source` is a closed `frozenset` literal
  (`_EVIDENTIARY_SOURCES = {"git_ref", "history_db_row", "run_dir_file"}`,
  `evidence.py:25`), test-enforced by
  `test_every_evidentiary_entry_traces_to_deterministic_source`
  (`scripts/tests/test_feat3182_evidence_bundle.py:153-159`). A
  `credential_scan` entry needs either to fit one of the three existing
  values or add a fourth — update both the frozenset and its enforcing
  test.
- **Reproducibility conflict (must resolve explicitly, not silently)**:
  `credential_scan.scanned_at` is in tension with `EvidenceBundle`'s
  byte-identical reproducibility invariant
  (`test_rerun_over_unchanged_inputs_is_byte_identical`) — the bundle
  deliberately has no timestamp field today (FEAT-3182 step 3e). Either
  exclude `scanned_at` from the reproducibility-tested scope, or resolve
  the conflict another explicit way. This also trips
  `test_carries_schema_version_and_comment_no_timestamp`
  (`test_feat3182_evidence_bundle.py:168`) — that test greps only the
  literal keys `"ts"`/`"timestamp"`/`"generated_at"` so `scanned_at` won't
  trip the assertion mechanically, but it directly conflicts with the
  design invariant the test encodes and must be reconciled, not just
  papered over.
- `assemble_bundle()` (`evidence.py:193`) builds entries procedurally in a
  fixed order (git predicates, `loop_runs_row` fields, `run_dir` file
  hashes, loop-start facts, gap checks, issue-path evidence, then
  segregated `context_non_evidentiary` entries). Append the
  `credential_scan` entry as a new `EvidenceEntry(...)` call in this
  sequence, calling ENH-3469's scanner over the bundle's own
  already-collected evidentiary data.
- `_BUNDLE_COMMENT` (`evidence.py:27-36`) and `canonical_json()`'s
  docstring (`evidence.py:116-118`) both assert the "no timestamp field"
  invariant in code comments, not just in tests — revise both if
  `scanned_at` is added.

## Integration Map

**Files to modify**
- `scripts/little_loops/cli/loop/evidence.py` — `EvidenceEntry`/
  `EvidenceBundle` definitions, `_EVIDENTIARY_SOURCES`, `assemble_bundle()`,
  `_BUNDLE_COMMENT`, `canonical_json()` docstring.

**Dependent files**
- `scripts/tests/test_feat3182_evidence_bundle.py` — the reproducibility
  test (`TestReproducibility.test_rerun_over_unchanged_inputs_is_byte_identical`),
  the no-timestamp test (`test_carries_schema_version_and_comment_no_timestamp`),
  and the source-enforcement test
  (`test_every_evidentiary_entry_traces_to_deterministic_source`) all need
  updates or explicit reconciliation. New tests for the `credential_scan`
  entry should follow this file's existing convention: a segregation
  invariant test, a reproducibility test (scoped to exclude or otherwise
  handle `scanned_at`), a shape test (`to_dict()` plain JSON only), an
  allowlist test.
- `scripts/little_loops/cli/loop/__init__.py:1001-1006,1127-1128` —
  registers/dispatches `ll-loop evidence` -> `cmd_evidence()`, the sole
  caller of `assemble_bundle()`. No signature change expected; verify the
  new entry surfaces correctly end-to-end through this call path.

**Documentation**
- `docs/reference/CLI.md:1297-1322` — states verbatim that "no timestamp
  field exists anywhere in the shape, by design, so reruns over unchanged
  inputs are byte-identical." This sentence becomes false the moment
  `credential_scan.scanned_at` lands; revise it, and add a
  `credential_scan: {tool, version, rules_sha, scanned_at, hits}` clause to
  the `#### ll-loop evidence` "Bundle shape" list.
- `docs/reference/API.md:4504-4568` — `EvidenceEntry`/`EvidenceBundle`/
  `canonical_json` API reference; document the new `credential_scan` entry
  shape.
- `docs/ARCHITECTURE.md` — update if it references the bundle shape
  directly.

## Tests

- New `credential_scan`-entry tests in
  `scripts/tests/test_feat3182_evidence_bundle.py`, following the existing
  segregation/reproducibility/shape/allowlist convention, adapted so the
  reproducibility test correctly handles the entry's scan-time field.
- Update the three existing tests named in Design above to reflect the new
  entry rather than leaving them contradicting the new bundle shape.

## Blocked By

ENH-3469 (credential-pattern scanner in `pii.py`) — this issue calls that
scanner; it cannot be implemented until the scanner's function signature
exists.

## Session Log
- `/ll:issue-size-review` - 2026-09-13T17:50:41 - `d24791a3-28b5-4b07-851d-ac809549dbb5.jsonl`
