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

Add a pure history-specific text policy and JSON sanitizer. Remove supported credential/PII matches from decoded strings and mapping keys while preserving the protocol structure needed for replay. This issue supplies the policy, types, fixtures, and API documentation; ENH-3751 wires persistence and ENH-3752 scrubs stored rows.

## Current Behavior

Verified on branch `main` on 2026-10-05:

- `scripts/little_loops/pii.py` provides `PII_PATTERNS`, the six-family `CREDENTIAL_RULES`, `redact_pii`, `detect_pii`, `scan_text`, and SFT `apply_pii_action`. It has no JSON traversal or protocol-context policy.
- The current PEM rule matches the BEGIN header only, leaving private key body/END text. Existing serialized-JSON substitution would miss credentials represented through decoded Unicode escapes.
- `scripts/little_loops/session_store/sessions.py` yields host-native inner Codex payloads for most event types and Claude-shaped records for normalized Codex exec pairs. Thus the payload alone does not reliably supply its host or original event type.
- `claude_transcript_contract` and `normalize_host_usage` require producer version, session/message IDs, and numeric usage components. Codex replay also consumes root header ID, turn/thread/response IDs, model and subtype fields. Arbitrary tool data containing a key named `id` has no such structural status.

## Expected Behavior

The sanitizer returns a fresh JSON-compatible payload plus deterministic per-rule replacement counts. It does not mutate any input dict/list, redact numbers/bools/nulls, or run regex substitution on serialized JSON. Callers provide host and event type as out-of-band context; the policy never chooses the ambient host or trusts a nested tool object's self-described type.

Pure text redaction accepts arbitrary strings. Protocol-identity changes, mapping-key collisions, invalid payload shape, or resource limits fail safely with a fixed reason code. No result, exception, traceback, or diagnostic contains matched text, secret-bearing mapping keys, or secret fingerprints.

## Motivation

A distinct history policy can handle decoded/nested payloads and complete credential spans without changing SFT, logs, or evidence-scanner semantics. Concrete protocol paths are necessary to keep sanitization from silently corrupting usage attribution or allowing tool-controlled exemption bypasses.

## Proposed Solution

### Rule and placeholder contract

Keep the history rule table separate from `CREDENTIAL_RULES`. Reuse the existing fixed-shape credential and PII definitions without modifying their public semantics, but replace the history PEM matcher with a whole-block scan. Enumerate accepted private-key labels in fixtures (including supported RSA/EC/DSA/OPENSSH forms and encrypted private-key blocks); do not substitute a public-key header. Document a finite rule-ID/replacement table and precedence:

| Family | Replacement/count rule |
|---|---|
| Private-key PEM | Entire complete block, or BEGIN-to-end for a truncated block, becomes `[PRIVATE_KEY_PEM]`; count one enclosing replacement |
| Bearer credential | Keep the `Bearer` scheme and replace the entire credential with `[BEARER_CREDENTIAL]`; case-insensitive scheme, bounded delimiters |
| URI userinfo | Remove the complete userinfo and its `@`; preserve scheme, host/IPv6/port, path, query and fragment; count `uri_userinfo` |
| Explicit credential field/assignment | Entire supported string value becomes `[CREDENTIAL_FIELD]`; count `credential_field` |
| Existing fixed-shape credentials and PII | Existing uppercase `[TYPE]` replacements and rule IDs |

URI removal deliberately inserts no raw bracketed placeholder into the authority: that can make an otherwise usable URI fail parsing. Do not decode/rewrite the rest of the URI. Userinfo includes percent-encoded credentials and username-only authority userinfo. Standalone emails must remain the email family, not be treated as URIs.

Apply enclosing PEM/bearer/userinfo/credential-context matches before narrower matches, with deterministic overlap resolution: a replaced enclosing span is not counted again as a nested token/PII match. Handle multiple PEM blocks, real and literal-escaped newline separators, BEGIN-without-END, and legacy `[PRIVATE_KEY_PEM]` followed by recognizable key-material/END context. A standalone placeholder stays unchanged.

Credential names use exact matching after ASCII case/separator normalization (case-insensitive, remove `_` and `-`; camelCase folds naturally). V1 aliases: `api_key`, `api_token`, `access_token`, `refresh_token`, `auth_token`, `id_token`, `authorization`, `proxy_authorization`, `password`, `passwd`, `private_key`, `client_secret`, `secret_access_key`, `aws_secret_access_key`, `aws_access_key_id`. No substring matches or bare `key`, `id`, `token`, `secret` heuristics; `input_tokens`, `max_tokens`, `token_count`, UUIDs, SHAs, hashes, base64-looking text, and native IDs remain ordinary unless a supported explicit context applies.

For named credential fields, redact nonempty string values regardless of entropy; if the value is a list/object, carry credential context to its string leaves without exempting or dropping the container. Numeric/bool/null values are preserved, including in credential fields; non-string credentials are outside V1 coverage. For free-form assignments/headers, define quoted/unquoted terminators and multiline boundaries in fixtures; do not guess at an unbounded prose suffix. Preserve only exact placeholders from the finite current/historical placeholder set, with zero count on a second pass; placeholder-like strings containing extra text are still scanned.

Scan arbitrary mapping keys as strings too. If a replacement would collide with another key (including an existing placeholder key), raise `key_collision` rather than dropping, merging, or inventing suffixed keys. Preserve insertion order and nonsecret key spelling.

### Protocol context and opaque fields

Use a finite root-anchored path registry keyed by the supplied host/event type and validated sibling discriminators. No recursive name-based exemptions. Cover all eight registered hosts' actual parser shapes, including normalized Codex exec records; do not claim that every host's payload has the same envelope.

| Verified shape | Minimum protected paths to establish from consumers |
|---|---|
| Claude-shaped envelope (Claude, qwen/gemini/omp normalization, opencode/pi, normalized Codex exec) | Root `sessionId`, `uuid`, `parentUuid`, protocol `type`/`timestamp`/`version`; `message.id`/model/role; actual typed tool-use `id` and tool-result `tool_use_id` at fixed content-block paths |
| Native Codex inner payload | `session_meta` root `id`; `turn_context`/task events root `turn_id`; `token_usage_record` root `thread_id`/`turn_id`/`response_id`; required subtype/model fields |
| Native Kimi wire | Establish the fields actually read by current session/replay consumers; no invented request-ID exemptions |

A protected string is still scanned. If the policy would change it, raise `unsafe_identity`; never preserve an original supported secret merely because it is structural, or replace it and silently alter replay. Numeric counters remain typed and untouched. Map this registry to `sessions` parsers, `claude_transcript_contract`, and replay consumers before implementing exclusions; fixture each protected path and a same-named arbitrary tool field that is scanned normally.

Opaque preservation is limited to verified native content paths for thinking signatures, `redacted_thinking` data, image/base64, and supported encrypted reasoning fields, with the expected type/encoding shape. Preserve only the opaque value, not adjacent plaintext reasoning/text. User/tool dictionaries merely named `signature`, `data`, `id`, or `type` do not gain exemptions; free-form tool input/result subtrees stay scan targets. Do not decode opaque/encrypted bytes or treat every base64-looking string as opaque.

Unknown/missing host context has no protocol or opaque exemptions; generic JSON use remains supported but has no replay-preservation claim. Protocol ingest must supply a registered host and event type. ENH-3752 must report stored rows whose context cannot be established safely instead of applying generic mode and claiming replay safety. Legacy null `host_basis` alone is not a reason to reject: it is an attribution qualifier, not the payload's format.

### Errors, resource bounds, and compatibility

Use iterative traversal or a checked depth budget, with a fixed `resource_limit` error before exhausting recursion/memory; never silently skip or truncate content. PEM scanning must avoid nested/backtracking-heavy regexes; bound credential-context lookaround. Include multi-MB text and nesting/scaling tests. No new runtime dependency; Hypothesis is already in the dev extras and its learning-test proof is currently proven.

Keep `redact_pii`, `detect_pii`, `scan_text`, `CredentialFinding`, `CREDENTIAL_SCANNER_VERSION`, `credential_rules_sha`, and their package exports unchanged. Export the new API from `little_loops.pii` only in this issue; do not widen the top-level package surface. Set `HISTORY_REDACTION_VERSION = 1`; bump on history semantics changes. Future extensions must preserve prior placeholders and the canonical fixed-point relation; removing/narrowing a prior rule requires an explicit compatibility/migration plan.

## Program Design

### Signatures

Proposed new definitions:

- `redact_history_text(text: str) -> str`
- `sanitize_history_payload(payload: dict[str, Any], *, host: str | None = None, event_type: str | None = None) -> HistoryRedactionResult`

```python
@dataclass(frozen=True)
class HistoryRedactionResult:
    payload: dict[str, Any]
    counts: dict[str, int]

class HistorySanitizationError(ValueError):
    # reason is a finite content-free code, never an input path/value.
    reason: str

HISTORY_REDACTION_VERSION: int = 1

def redact_history_text(text: str) -> str: ...
def sanitize_history_payload(
    payload: dict[str, Any],
    *,
    host: str | None = None,
    event_type: str | None = None,
) -> HistoryRedactionResult: ...
```

Only decoded JSON objects/arrays and JSON scalar types are accepted under the dict root; reject unsupported objects/cycles/non-string keys and non-finite numeric values safely. Error messages/args/attributes contain only the fixed reason; suppress input-bearing exception chains with `raise ... from None`. Test `str`, `repr`, and formatted tracebacks, since the backfill worker prints exceptions.

### Call Path

The new sanitizer -> context/path classification -> recursive-content policy with bounded traversal -> fresh result. ENH-3751 will call it between `iter_events` and serialization; ENH-3752 will call it after decoding each stored column. The pure helpers import no database/backend/host runner and never print.

## Integration Map

### Files to Modify

- `scripts/little_loops/pii.py` — add history table, traversal/context rules, result/error types, and update the SFT-only module docstring.
- `scripts/tests/test_pii.py` — separate history fixtures and properties; leave scanner fixtures intact.
- `docs/reference/API.md` — module row, new signatures, finite policy/aliases/placeholders, context/error contract and coverage limits.

### Dependent Files and Similar Patterns

`session_store/sessions.py`, `session_store/claude_usage.py`, and `session_store/writers.py` are sources for verified protocol shapes, not files to change here. `cli/logs.py`, `cli/loop/evidence.py`, SFT consumers, and `little_loops/__init__.py` retain the old API. `cli/backfill_worker.py` is a downstream error-formatting consumer.

### Behavior Parity

| Artifact | Preserved | Changed | Dropped |
|---|---|---|---|
| `pii.py` | All existing scanner/SFT detection, placeholders, counts/fingerprints, version/hash contracts | Add separate context-aware history API and policy version | None |
| `little_loops/__init__.py` | Existing PII exports | No new top-level exports in this issue | None |

### Tests

- Positive and near-miss fixture per family/alias/context; decoded Unicode escapes, quoted assignments, bearer punctuation/multiline boundaries, valid URI parsing including IPv6/percent encoding, multiple/truncated/legacy PEM.
- Hypothesis properties: deterministic/idempotent payload and text output, second-pass zero counts, valid serialization, no input mutation/aliasing, overlap counts, key-collision rejection, nonsecret structure preservation, finite placeholders match no detector. Generate collision/nesting inputs deliberately, not only independent arbitrary strings.
- Per-host protected/opaque paths and spoofed tool lookalikes, normalized Codex exec vs inner payload, unknown context, numeric counters and non-string credential scope. Secret on protected paths fails safely; ordinary UUID/hash/native IDs survive.
- Canary leakage assertions for result/error/traceback; multi-MB adversarial text plus deep nesting with bounded scaling and safe resource failures.
- Existing `TestCredentialRules`, `TestCredentialRulesSha`, `test_feat3182_evidence_bundle.py::TestCredentialScan`, and `test_extension.py` remain green. Assemble fake credential fixtures from fragments so repository secret scanning stays clean.

### Configuration

Default history policy has no opt-out or new config in this issue. No database schema/version marker or persistence wiring.

## Implementation Steps

1. Establish and fixture the finite family/alias/placeholder and per-host path tables from current consumers.
2. Add failing history-policy fixtures and Hypothesis properties, including safe errors and resource boundaries.
3. Implement the separate pure policy/traversal without changing public scanner behavior.
4. Document the new API, run focused parity/secret-scan checks, then `python -m pytest scripts/tests/`.

## Acceptance Criteria

- [ ] Every supported family has positive/near-miss coverage; complete/truncated/escaped/legacy PEM and decoded Unicode matches are removed without partial credential remnants.
- [ ] Determinism, idempotence, zero second-pass counts, valid serialization, no mutation, collision rejection and structure preservation pass for generated and explicit cases.
- [ ] Supplied host/event context protects verified replay fields without broad name-based exemptions; opaque exceptions are narrow and spoof-resistant; numeric/UUID/hash/base64 near misses survive.
- [ ] Identity, key-collision, invalid-shape and resource failures expose only fixed codes, including formatted tracebacks; large input work is bounded and never silently bypasses redaction.
- [ ] Existing scanner/SFT APIs, placeholders, version/hash and top-level exports are unchanged; policy/coverage/API docs and `python -m pytest scripts/tests/` pass.

## Scope Boundaries

Pure policy only. No storage writes, ingest/refresh wiring, maintenance CLI, schema migration, entropy-based arbitrary-secret detector, encoded/encrypted-content inspection, non-string credential replacement, identity hashing, or renamed collision keys. Supported-match removal is not universal secret detection.

## Impact

- **Priority**: P2 — foundation for preventing supported secrets from entering raw history/remote payloads.
- **Effort**: Medium/Large — finite protocol policy and adversarial/property testing, with no new backend work.
- **Risk**: Medium — overly broad exemptions or rules could leak content or alter replay; explicit paths and parity tests bound this risk.
- **Breaking Change**: No to existing scanner APIs; the new history API has its own contract.

## Review Notes

Reviewed on `main`, 2026-10-05, with `/ll:advise` using `claude-opus-5-5`. Added host plus event-type context because Codex inner payloads lack their envelope; settled aliases, placeholders/counts, URI handling, exports and safe errors. Retained fail-safe key-collision/identity rejection instead of the advisor's suggested key suffixing or replacement payload, which would change replay structure.

## Blocks

- ENH-3751
- ENH-3752

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-10-06T00:26:44 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`
