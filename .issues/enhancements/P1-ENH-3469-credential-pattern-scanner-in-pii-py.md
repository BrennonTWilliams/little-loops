---
id: ENH-3469
title: Credential-pattern deterministic scanner in pii.py
type: ENH
priority: P1
status: done
discovered_date: '2026-09-13'
completed_at: '2026-09-14T17:24:36Z'
parent: ENH-3466
labels:
- goal-7,security,verification
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3469: Credential-pattern deterministic scanner in pii.py

## Summary

Build a deterministic, non-LLM credential/API-key/token pattern scanner in
`scripts/little_loops/pii.py`: a frozen-dataclass rule table, a redacted
frozen-dataclass finding, a text-in scan function, and a pinned
`rules_sha`/version pair. This is the standalone primitive that ENH-3470's
evidence-bundle integration calls; it must be independently testable and
usable without any evidence-bundle wiring. It is a library primitive only —
no CLI entry point, no exit-code convention, no suppression comment (see
Design for why each is excluded).

## Current Behavior

`scripts/little_loops/pii.py` detects and redacts only email, phone, and SSN
patterns (`PII_PATTERNS`, `detect_pii`, `redact_pii`, `apply_pii_action`).
There is no deterministic scanner for credential-shaped strings (AWS keys,
GitHub tokens, Anthropic keys, Slack tokens, PEM private-key blocks, JWTs),
so the `sft-corpus.yaml` `check_pii` gate — and any other consumer of
`detect_pii`/`redact_pii` — never flags, redacts, or discards
credential-bearing content.

## Expected Behavior

`pii.py` gains a `CredentialRule` frozen-dataclass rule table
(`CREDENTIAL_RULES`), a redacted `CredentialFinding` frozen dataclass (no
`excerpt` field, per the no-leak rationale in Design), `scan_text`/`scan_file`
functions, and a pinned `CREDENTIAL_SCANNER_VERSION`/`credential_rules_sha()`
pair. `detect_pii` and `redact_pii` consult both `PII_PATTERNS` and
`CREDENTIAL_RULES`, so the existing `sft-corpus.yaml` `check_pii` gate picks
up credentials automatically with no further wiring changes.

## Impact

Unblocks ENH-3470 (the `EvidenceBundle` credential-scan integration), which
requires this primitive to be independently testable before it can wire
against it. Also changes `sft-corpus.yaml`'s `check_pii` gate behavior: a
`redact` run now emits `[AWS_ACCESS_KEY]`-style placeholders and a `discard`
run drops examples containing credentials — documented in
`docs/reference/loops.md` and covered by new tests in
`test_loops_sft_corpus.py`. No consumer outside `pii.py`'s two existing entry
points (`detect_pii`, `redact_pii`) needs to change.

## Parent Issue

Decomposed from ENH-3466: Goal 7 — credential-scan verification primitive
(FEAT-034 extension). Scoring 11/11 (Very Large): the parent bundled
building this scanner *and* wiring it into `EvidenceBundle` into a single
issue with the reproducibility-invariant conflict layered on top. This
child covers the scanner build only.

## Design

### Shape decision (resolved)

Keep `PII_PATTERNS`, `detect_pii`, `redact_pii`, and `apply_pii_action`
as they are. Add a **separate** credential rule table alongside them, and
have `detect_pii`/`redact_pii` consult **both** tables so the existing
`sft-corpus.yaml` `check_pii` emit gate picks up credentials automatically
(the parent's second consumer). This is a deliberate behavior change to the
gate: a `redact` run now emits `[AWS_ACCESS_KEY]`-style placeholders and a
`discard` run drops examples containing credentials. Document it in
`docs/reference/loops.md` and cover it in `test_loops_sft_corpus.py`.

### Rule table

Follow `verify_private_refs.py`'s `PrivateRefRule` as the precedent:

```python
@dataclass(frozen=True)
class CredentialRule:
    name: str
    pattern: re.Pattern[str]
    rationale: str

CREDENTIAL_RULES: tuple[CredentialRule, ...] = (...)
```

Default rule set (low false-positive risk only; this list is what
`rules_sha` pins, so it is part of the spec, not an implementation detail):

| name | pattern | rationale |
|---|---|---|
| `aws_access_key` | `\bAKIA[0-9A-Z]{16}\b` | AWS long-term access key ID prefix |
| `github_token` | `\bgh[pousr]_[A-Za-z0-9]{36,}\b` | GitHub PAT / OAuth / user-server / refresh token prefixes |
| `anthropic_key` | `\bsk-ant-[A-Za-z0-9_-]{20,}\b` | Anthropic API / OAuth key prefix |
| `slack_token` | `\bxox[baprs]-[A-Za-z0-9-]{10,}\b` | Slack bot/app/user token prefixes |
| `private_key_pem` | `-----BEGIN (?:RSA \|EC \|DSA \|OPENSSH \|PGP )?PRIVATE KEY-----` | PEM private-key block header |
| `jwt` | `\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b` | Three-segment base64url JWT |

Do **not** include a generic `password=`/`api_key=` assignment rule in the
default set — its false-positive rate against loop transcripts (which quote
config keys constantly) would make the ENH-3470 gap signal useless. If one
is wanted later it goes in a separately named, opt-in tuple.

### Finding (redacted by construction)

```python
@dataclass(frozen=True)
class CredentialFinding:
    rule: str          # CredentialRule.name
    line: int          # 1-based line within the scanned text
    fingerprint: str   # sha256(matched span)[:12]
```

**No `excerpt` field.** This diverges from `PrivateRefFinding` on purpose:
a finding that quotes the matched span would re-leak the credential into
whatever artifact records the finding (the ENH-3470 bundle's `hits`, a log
line, a test failure message). The fingerprint is enough to correlate two
scans of the same text without carrying the secret.

### Scan API (text-in, not file-in)

```python
def scan_text(text: str, rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES) -> list[CredentialFinding]
def scan_file(path: Path, rules: ... = CREDENTIAL_RULES) -> list[CredentialFinding]  # thin wrapper
```

`scan_text` is the primitive. ENH-3470 scans in-memory strings and archived
file bytes; the parent's third consumer (longitudinal `history.db`) scans
row values. `verify_private_refs.py`'s `scan_all(base_dir)` directory walk
is the wrong precedent for this consumer set and is not needed.
Findings are returned sorted by `(line, rule)` so output is deterministic
regardless of rule order.

### Version pinning

```python
CREDENTIAL_SCANNER_VERSION: int = 1   # bump only when scan semantics change

def credential_rules_sha(rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES) -> str:
    """sha256 over '\n'.join(f'{r.name}\t{r.pattern.pattern}\t{r.pattern.flags}')"""
```

`rationale` is **excluded** from the hash so doc-string edits do not churn
it. ENH-3470 reads `CREDENTIAL_SCANNER_VERSION` for its `version` field and
`credential_rules_sha()` for `rules_sha`. No existing helper hashes an
in-memory rule set (`_sha256_file` in `codegraph.py` hashes file bytes;
`VerdictCache`'s `{version, algo}` pair is literal constants), so this is
net-new code.

### Explicitly excluded

- **Suppression escape hatch** (`ll-credential-ok:`-shaped): not added. A
  suppression comment makes sense for a lint over source files, not for
  evidence data where a matched secret is never "ok". Revisit only if a
  source-file lint CLI is added later.
- **CLI entry point / exit-code convention**: not in scope. No
  `ll-verify-credentials` is registered; the primitive is consumed by
  Python callers only.

### Test fixtures vs. the gitleaks pre-commit hook

`.pre-commit-config.yaml` runs gitleaks v8.30.1 on every staged diff. Any
realistic fake token committed in a test file is exactly what it blocks.
**Assemble fixtures at runtime from fragments** (e.g.
`"AKIA" + "I" * 16`, `"gh" + "p_" + "a" * 36`) the way
`verify_private_refs.py` builds `_USER_SEG` to avoid self-matching. Do not
add a `.gitleaks.toml` allowlist; a committed literal secret-shaped string
is the thing this whole issue exists to prevent. ENH-3470's fixtures follow
the same rule.

## Integration Map

**Files to modify**
- `scripts/little_loops/pii.py` — add `CredentialRule`, `CREDENTIAL_RULES`,
  `CredentialFinding`, `scan_text`, `scan_file`,
  `CREDENTIAL_SCANNER_VERSION`, `credential_rules_sha`; extend
  `detect_pii`/`redact_pii` to iterate both tables. Update the module
  docstring (currently "email, phone, and SSN patterns").
- `scripts/little_loops/__init__.py:64,177-179` — export the new public
  symbols (`CredentialFinding`, `CredentialRule`, `CREDENTIAL_RULES`,
  `CREDENTIAL_SCANNER_VERSION`, `credential_rules_sha`, `scan_text`) with
  matching `__all__` entries, same pattern as `apply_pii_action` et al.

**Dependent files**
- `scripts/little_loops/cli/logs.py:1843-1852` — calls `redact_pii(text)`
  directly; signature unchanged, credential redaction now flows through.
  Verify no test in `test_logs*.py` asserts on a string that the new rules
  would now match.
- `scripts/tests/test_extension.py:765,771,777` — one smoke test per newly
  exported symbol.
- `scripts/tests/test_loops_sft_corpus.py` (`TestPiiFlagPassthrough`,
  `TestPiiRedact`, `TestPiiDiscard`, `TestPiiDefaultBehavior`) — the gate
  inherits credential detection via `detect_pii`/`redact_pii`; add sibling
  test methods covering a credential-bearing example under each action.
- `scripts/little_loops/loops/sft-corpus.yaml:321-340` — `check_pii` state
  comment text if it enumerates the pattern set.

**Documentation**
- `docs/reference/API.md` (`## little_loops.pii`, ~line 8077-8163) — add
  the credential rule table, `CredentialFinding`, `scan_text`,
  `credential_rules_sha`, and `CREDENTIAL_SCANNER_VERSION`; note the
  no-excerpt design.
- `docs/reference/loops.md:418,439-490` — `pii_action` row and `check_pii`
  description now cover credentials; list the placeholder names.

## Program Design

### Types

New, no existing precedent to extend:
- `CredentialRule` — frozen dataclass, `name: str`, `pattern: re.Pattern[str]`,
  `rationale: str`. Modeled on `PrivateRefRule`
  (`scripts/little_loops/cli/verify_private_refs.py:119`).
- `CredentialFinding` — frozen dataclass, `rule: str`, `line: int`,
  `fingerprint: str`. Diverges from the precedent's `PrivateRefFinding` by
  omitting an `excerpt` field (see Design › no-leak rationale).

### Signatures

New (`scripts/little_loops/pii.py`):
- `scan_text(text: str, rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES) -> list[CredentialFinding]`
- `scan_file(path: Path, rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES) -> list[CredentialFinding]`
- `credential_rules_sha(rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES) -> str`

Existing, extended to also consult `CREDENTIAL_RULES` (signatures unchanged):
- `detect_pii(text: str) -> list[str]` — `pii.py:26`
- `redact_pii(text: str) -> str` — `pii.py:39`

### Call Path

`scripts/little_loops/cli/logs.py:1852` calls `redact_pii(text)` (`pii.py:39`)
→ `redact_pii` iterates `PII_PATTERNS` then the new `CREDENTIAL_RULES` table,
substituting an uppercase `[RULE_NAME]` placeholder per hit → no caller-side
change needed. The `sft-corpus.yaml` `check_pii` gate's handler calls
`detect_pii`/`apply_pii_action` the same way, so credential detection flows
through automatically. `scan_text` itself has no existing caller — it is the
new primitive `detect_pii`/`redact_pii` route through internally, and
ENH-3470 is its first external consumer.

### Decision Rules

N/A — no new branching or classification logic beyond "does the rule's
`pattern` match," mirroring `PrivateRefRule.pattern.search` in
`verify_private_refs.py`'s `scan_all` (`verify_private_refs.py:365`).

## Tests

- `scripts/tests/test_pii.py` — per rule: one positive and one negative
  (near-miss) pair, following the existing class-per-function convention;
  fixtures assembled from fragments per Design.
- `scan_text` returns findings sorted by `(line, rule)`; `line` is 1-based;
  a multi-hit line yields one finding per rule.
- **No-leak test**: for every rule, `repr(finding)` and every field of the
  finding do not contain the matched span.
- `credential_rules_sha()` is stable across calls, changes when a pattern
  changes, and does **not** change when only a `rationale` changes.
- `detect_pii`/`redact_pii` on existing email/phone/ssn fixtures are
  unchanged (regression), and a credential-bearing string yields the rule
  name / uppercased placeholder.
- Smoke test per newly exported symbol in `test_extension.py`.

## Scope Boundaries

In scope: the standalone scanner primitive in `pii.py` (rule table, finding
type, `scan_text`/`scan_file`, version pin) and extending `detect_pii`/
`redact_pii` to consult it, plus the sibling test/doc updates listed in
Integration Map. Out of scope: see `## Out of Scope` below.

## Out of Scope

- Wiring into `EvidenceBundle` (ENH-3470).
- The longitudinal `history.db` leakage signal (parent's third consumer) —
  not covered by either child; see ENH-3466 Resolution.
- Suppression comments, a CLI, and a generic assignment-style rule (see
  Design › Explicitly excluded).

## Status

Done. Implemented per the Design/Program Design as specified.

## Resolution

Added `CredentialRule`, `CREDENTIAL_RULES` (6 rules: `aws_access_key`,
`github_token`, `anthropic_key`, `slack_token`, `private_key_pem`, `jwt`),
`CredentialFinding` (no `excerpt`), `scan_text`, `scan_file`,
`CREDENTIAL_SCANNER_VERSION`, and `credential_rules_sha` to
`scripts/little_loops/pii.py`, exactly per the issue's Design and Program
Design sections. `detect_pii`/`redact_pii` now also consult
`CREDENTIAL_RULES`, so the `sft-corpus.yaml` `check_pii` gate picks up
credentials automatically. All new symbols exported from
`scripts/little_loops/__init__.py`. TDD: tests written first in
`scripts/tests/test_pii.py` (new classes `TestCredentialRules`,
`TestScanText`, `TestScanFile`, `TestNoLeak`, `TestCredentialRulesSha`,
`TestDetectPiiRedactPiiCredentials`), confirmed Red (`ImportError` — new
symbols didn't exist), then Green after implementation. Sibling tests added
to `test_extension.py` (6 smoke-import tests) and
`test_loops_sft_corpus.py` (one credential case per `TestPii*` class).
Fixtures assembled from fragments (`"AKIA" + "I"*16`, etc.) to avoid
tripping the gitleaks pre-commit hook, per Design. Docs updated:
`docs/reference/API.md` (`## little_loops.pii` section) and
`docs/reference/loops.md` (`pii_action` predicate description).

Full suite: `python -m pytest scripts/tests/` → 24267 passed, 51 skipped, 3
failed. The 3 failures (`test_prose_dep_sweep_gate`,
`TestCorpusHasNoMalformedDepIds`, `TestRepoGate::test_no_new_unverifiable_evidence`)
are pre-existing issue-corpus consistency gates on unrelated issues
(ENH-3470's bare-numeric `depends_on: 3469` vs. TYPE-NNN prose, ENH-3463/
ENH-3464's similarly malformed `blocked_by`, and a stale evidence quote in
ENH-3467) — none reference `pii.py`, `ENH-3469`, or any file this issue
touched, and they predate this session's changes. `ruff check` and `mypy`
clean on all touched files.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-14_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 89/100 → HIGH CONFIDENCE

_Updated 2026-09-14: `## Program Design` section added (types, signatures,
call path citing `pii.py:26`/`pii.py:39` and `verify_private_refs.py:119`);
`ll-issues check-design ENH-3469` now passes. The prior STOP — ADDRESS GAPS
verdict is resolved._

## Session Log
- `/ll:manage-issue` - 2026-09-14T17:23:41 - `c286af01-1fa9-40fd-bc0d-381da6bba313.jsonl`
- `/ll:ready-issue` - 2026-09-14T17:06:24 - `e6ff9aed-893e-402b-a2dd-417c88258c41.jsonl`
- `/ll:confidence-check` - 2026-09-14T16:52:57 - `b233366b-10ab-4e31-a82f-311f95b747f5.jsonl`
- `/ll:issue-size-review` - 2026-09-13T17:50:41 - `d24791a3-28b5-4b07-851d-ac809549dbb5.jsonl`
- manual review - 2026-09-13 - resolved shape decision, fixed rule list, redacted finding, text-in API, version pinning, gitleaks fixture rule; removed suppression/CLI scope
