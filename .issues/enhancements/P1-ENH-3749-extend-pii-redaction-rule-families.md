---
id: ENH-3749
title: Extend pii.redact_pii() rule families (bearer tokens, credentialed URIs, entropy)
type: ENH
priority: P1
status: open
parent: ENH-3743
relates_to:
- ENH-3750
captured_at: "2026-10-05T00:00:00Z"
labels: [redaction, pii, rule-extension, security]
---

# ENH-3749: Extend pii.redact_pii() rule families

## Summary

Per ENH-3743's promotion scope, the existing redactor must be extended
with rule families beyond its current coverage. Three families:
bearer tokens (e.g. `Authorization: Bearer <token>`), credentialed URIs
(`postgres://user:pass@host/db`, `mysql://`, `mongodb://`, `redis://`),
and entropy heuristics (long high-entropy strings >= 4.5 bits/char).

## Acceptance Criteria

- New rule family: bearer tokens. Recognize `Authorization: Bearer ...`
  headers and any standalone `<40+ hex chars>` token.
- New rule family: credentialed URIs. Recognize `postgres://`,
  `mysql://`, `mongodb://`, `redis://` schemes with userinfo before `@`.
- New rule family: entropy heuristic. Recognize strings of length >= 20
  with Shannon entropy >= 4.5 bits/char (configurable threshold).
- All three families are pure functions of the input string (no I/O) so
  the property tests in `test_pii_redaction.py` cover them without
  fixtures.
- Property test: redactor is monotonic (longer input → never fewer
  redactions); idempotent (running on already-redacted output produces
  same output).
- False-positive guard: known-benign inputs (low-entropy prose, code
  snippets, README excerpts, JSON literals, UUIDs) are NOT redacted.
  Tune thresholds against a held-out corpus.
- The rule families are pluggable (a registry pattern) so new families
  can be added without touching `redact_pii()` directly.

## Out of Scope

- Insert-site redaction wiring — separate issues ENH-3745/3746/3747.
- Backfill — separate issue ENH-3748.
