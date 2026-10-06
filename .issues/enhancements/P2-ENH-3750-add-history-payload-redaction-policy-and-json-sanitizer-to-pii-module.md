---
id: ENH-3750
title: Add history payload redaction policy and JSON sanitizer to the pii module
type: ENH
priority: P2
status: open
discovered_date: '2026-10-05'
parent: ENH-3743
labels:
- security
- privacy
- history
learning_tests_required:
- hypothesis
decision_needed: false
---

# ENH-3750: Add history payload redaction policy and JSON sanitizer to the pii module

## Summary

Add the pure, host-agnostic history redaction policy to `scripts/little_loops/pii.py`: a JSON-aware sanitizer (`sanitize_history_payload`) and text redactor (`redact_history_text`) that remove supported credential/PII matches from decoded payload strings before any persistence. This child ships the policy and its tests/docs only; wiring into ingest is ENH-3751 and the maintenance command is ENH-3752.

## Parent Issue

Decomposed from ENH-3743: Redact history raw payloads before persistence and provide a resumable scrub. Covers parent **Proposed Solution §1** ("Add a history payload policy without changing unrelated scanner contracts"). Read ENH-3743 for the full Current Behavior, Motivation, and Codebase Research Findings.

## Scope

Follow ENH-3743 Proposed Solution §1 verbatim. In brief:

- Decode JSON, traverse string leaves recursively, return a fresh payload (no mutation of parser-owned objects); never regex-replace serialized JSON.
- Whole-PEM block replacement (body + END marker; BEGIN-without-END redacts to end of string; real and literal-escaped newlines; legacy header-only `[PRIVATE_KEY_PEM]` followed by key material/END context). Broad enclosing matches (PEM, bearer, URI credentials, credential fields) apply before narrower PII/token matches.
- Whole bearer credential and URI userinfo (incl. percent-encoded), keeping non-credential URI structure.
- Enumerated credential field names (`api_key`, `access_token`, `authorization`, `password`, `private_key`, `client_secret`, …) with documented case/separator normalization, redacted regardless of entropy; delimited assignments/header text in free-form text; no bare `key`/`id` heuristics.
- Context-bound detection only: no unconditional high-entropy rule. UUIDs, SHAs, hashes, base64, native IDs stay; hex secrets in explicit credential fields are redacted.
- Protect verified protocol identity paths only; a secret match in a required structural identity, or a key-replacement collision, raises a safe sanitizer error (content-free message — `cli/backfill_worker.py` echoes `{exc}` to stderr).
- Preserve typed opaque values (thinking signatures, `redacted_thinking` data, image/base64 blocks); document that encrypted/encoded opaque data is outside coverage.
- Keep a **separate history rule table** — do not add families to `CREDENTIAL_RULES`; leave `redact_pii()`, `detect_pii()`, `scan_text()`, `CredentialFinding`, `CREDENTIAL_SCANNER_VERSION`, `credential_rules_sha()` intact.
- Report rule names and counts only. Bound detector work (no backtracking-heavy regexes, capped lookaround).
- Types: `HistoryRedactionResult(payload, counts)`, `HISTORY_REDACTION_VERSION: int`.
- Decide explicitly whether the new helpers join `little_loops/__init__.py` exports (`detect_pii`/`redact_pii`/`apply_pii_action` stay exported — `test_extension.py`).

## Files

- `scripts/little_loops/pii.py` (policy, traversal, types; update stale module docstring)
- `scripts/little_loops/__init__.py` (export decision)

## Tests

- `scripts/tests/test_pii.py`: history-policy fixture table parallel to `_RULE_FIXTURES` (positive + near-miss per family), `TestNoLeak`-style check, existing-API parity, first Hypothesis properties (determinism/idempotence, valid serialization, no input mutation, overlapping matches/key collisions, nonsecret structure preserved, placeholders match no detector), legacy header-only PEM remnants, opaque signed/image fields, PII near misses, adversarial multi-MB input with bounded runtime/scaling (well under the 120s thread timeout).
- Existing tests to keep green: `TestCredentialRules::test_has_one_rule_per_expected_name`, `TestCredentialRulesSha`, `test_feat3182_evidence_bundle.py::TestCredentialScan`, `test_extension.py`.
- Secret fixtures assembled from fragments (gitleaks); no `/home/<user>/` paths.

## Docs

- `docs/reference/API.md` — `## little_loops.pii` section/module-table row (new helpers, history policy, version).

## Acceptance Criteria

- [ ] Every supported rule family has positive and near-miss fixtures; decoded Unicode escapes and multiline/truncated PEM bodies are redacted; existing uppercase `[TYPE]` placeholders and public scanner contracts unchanged.
- [ ] Hypothesis properties pass per ENH-3743 AC3 (determinism, idempotence, serialization validity, no mutation, key collisions, structure preservation).
- [ ] Unlabelled UUIDs/hashes/base64/native IDs are intact; labelled credentials of the same shapes are redacted; structural-identity secret matches and key collisions raise a content-free sanitizer error.
- [ ] Multi-MB adversarial inputs complete in bounded time with a scaling check.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Blocks

- ENH-3751, ENH-3752


## Session Log
- `/ll:issue-size-review` - 2026-10-06T00:26:44 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`
