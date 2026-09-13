---
id: 3469
title: "Credential-pattern deterministic scanner in pii.py"
type: ENH
priority: P1
status: open
discovered_date: '2026-09-13'
parent: ENH-3466
labels:
- goal-7,security,verification
decision_needed: false
---

# ENH-3469: Credential-pattern deterministic scanner in pii.py

## Summary

Build a deterministic, non-LLM credential/API-key/token pattern scanner in
`scripts/little_loops/pii.py`, matching the frozen-dataclass rule-table ->
finding-list -> scan function -> exit-code convention already used by
`verify_private_refs.py` / `verify_evidence.py` / `verify_skill_prose.py`.
This is the standalone primitive that ENH-3466's evidence-bundle integration
(a separate follow-on issue) will call; it must be independently testable
and usable without any evidence-bundle wiring, the same way `gitleaks` and
the existing deterministic scanners stand alone before any caller uses them.

## Parent Issue

Decomposed from ENH-3466: Goal 7 — credential-scan verification primitive
(FEAT-034 extension). Scoring 11/11 (Very Large): the parent bundled
building this scanner *and* wiring it into `EvidenceBundle` into a single
issue with the reproducibility-invariant conflict layered on top. This
child covers the scanner build only.

## Design

- `pii.py`'s current shape (`PII_PATTERNS: dict[str, re.Pattern[str]]`, no
  `Finding` dataclass, no `scan_file`/`scan_all`, no exit-code convention)
  does not match the target convention. Matching it is net-new structure:
  either convert `PII_PATTERNS` to a frozen-dataclass rule table, or add a
  parallel credential rule table alongside it. Resolve this explicitly
  rather than leaving both shapes coexisting.
- Follow `verify_private_refs.py`'s shape as the closer precedent (it has a
  rule-table dataclass; `verify_evidence.py` does not):
  `Rule(name: str, pattern: re.Pattern[str], rationale: str)` (frozen
  dataclass) -> `RULES: tuple[Rule, ...]` -> `Finding(path, line, rule,
  rationale, excerpt)` (frozen dataclass) -> `scan_file(path, rules) ->
  list[Finding]` / `scan_all(base_dir, rules) -> list[Finding]`.
- Compute a `rules_sha` for the in-memory rule table. No existing helper
  hashes an in-memory rule set (`_sha256_file` in `codegraph.py` hashes
  on-disk file bytes only; `VerdictCache`'s `{version, algo}` pair in
  `verify_evidence.py` is a pair of literal constants, not a hash
  function). This is net-new code.
- Decide whether a suppression escape hatch is needed
  (`ll-credential-ok:`-shaped, analogous to `verify_private_refs.py`'s
  `_SUPPRESS_RE` checked on the finding's own or preceding line). If added,
  it needs a counter-example test proving a fixture that quotes a fake
  secret still flags pre-suppression (see
  `TestSuppressionEscapeHatch::test_counter_example_quote_flags_before_suppression`,
  `scripts/tests/test_verify_evidence.py:517-565`, as the pattern to
  follow).

## Integration Map

**Files to modify**
- `scripts/little_loops/pii.py` — add the credential rule table / scan
  functions per Design above.

**Dependent files**
- `scripts/little_loops/__init__.py:64,177-179` — if the scanner is exposed
  as a new public `pii.py` symbol, add the same
  export-plus-`__all__`-entry pattern already used for
  `apply_pii_action`/`detect_pii`/`redact_pii`.
- `scripts/little_loops/cli/logs.py:1843-1852` — calls `redact_pii(text)`
  directly. Its call signature is unchanged by this work; verify credential
  redaction added to `redact_pii` (if that's the chosen shape) flows
  through this call site correctly.
- `scripts/tests/test_extension.py:765,771,777` — one smoke test per
  exported `pii.py` symbol (`test_smoke_import_detect_pii` etc.). Add a
  matching smoke test for any new exported symbol.
- `scripts/tests/test_loops_sft_corpus.py` (`TestPiiFlagPassthrough`,
  `TestPiiRedact`, `TestPiiDiscard`, `TestPiiDefaultBehavior`) — the
  end-to-end coverage for the `sft-corpus.yaml` `check_pii` gate, which
  calls into `pii.py`. If credential detection is wired through
  `PII_PATTERNS`/`apply_pii_action` directly (rather than a fully separate
  rule table with no shared call path), this gate inherits the new
  behavior automatically — add sibling test methods/classes here to cover
  it. If the chosen shape keeps the credential rule table fully separate
  from `apply_pii_action`'s call path, state that explicitly and confirm no
  test here is affected.

**Documentation**
- `docs/reference/API.md` (`## little_loops.pii` section, ~line
  8077-8163) — documents `PII_PATTERNS` as exactly the 3-row
  email/phone/ssn table with a worked example; add the credential-pattern
  row/section.
- `docs/reference/loops.md:439-490` — describes the `check_pii` state,
  `pii_action` predicate, and `apply_pii_action()`. Update only if the
  gate's behavior or pattern set changes as a result of the shape chosen
  above.

## Tests

- `scripts/tests/test_pii.py` — new credential-pattern positive/negative
  test pairs, following the existing class-per-function convention.
- If a suppression escape hatch is added: a same-line, preceding-line, and
  counter-example (quoted-secret-still-flags) test set, mirroring
  `test_verify_private_refs.py`'s `TestSuppression` /
  `test_verify_evidence.py`'s `TestSuppressionEscapeHatch`.
- Smoke test for any newly exported `pii.py` symbol in `test_extension.py`.

## Out of Scope

Wiring this scanner into the `EvidenceBundle`'s `credential_scan` entry
(the `_EVIDENTIARY_SOURCES` frozenset fit, the `rules_sha`/`scanned_at`
recording in the bundle entry, the reproducibility-invariant conflict) is
covered by a separate follow-on issue that depends on this one.

## Session Log
- `/ll:issue-size-review` - 2026-09-13T17:50:41 - `d24791a3-28b5-4b07-851d-ac809549dbb5.jsonl`
