---
id: ENH-3743
title: Redact secrets at write time on every history.db raw_events insert path, with a backfill of stored rows
type: ENH
priority: P2
status: open
discovered_date: '2026-10-05'
labels: []
---

## Summary

history.db stores host transcript lines verbatim, and nothing redacts secrets before they are written. `raw_events.raw_line` keeps each host log line as-is. None of the three code paths that insert into `raw_events` calls the redactor the package already ships.

Credentials, tokens and PII that appear anywhere in a transcript therefore land on disk unredacted. If a shared remote store is configured, they are pushed to it as well. This includes reasoning (`thinking`) blocks, which can carry secrets that never appear in the visible conversation.

This is not hypothetical. Claude Code session lines with non-empty plaintext `thinking` blocks are already present, unredacted, in `raw_events` on working installs.

Redact at write time, before persistence, on every `raw_events` insert path. Run a one-time pass over rows already stored.

## Current Behavior

- `scripts/little_loops/pii.py` `redact_pii()` covers email, phone and SSN, plus credential rules for AWS, GitHub, Anthropic, Slack, PEM and JWT. It is used by the sft-corpus filter, `cli/logs.py` and the `cli/loop/evidence.py` scanner.
- No `raw_events` insert calls it. All three paths are in `scripts/little_loops/session_store/lifecycle.py`:
  - the local insert (~L873);
  - the remote push via `_REMOTE_RAW_INSERT` (~L777, flushed ~L840), which ships `raw_line` to a shared remote store when one is configured;
  - `refresh_usage_source` (~L1581).
- The rules do not cover bearer tokens, credentialed URIs (`scheme://user:pass@host`) or high-entropy secrets.

## Expected Behavior

- Every `raw_events` write passes `raw_line` (and any stored parsed payload) through the redactor before persistence. That covers the local insert, the remote push and the usage refresh.
- The redactor is a **pure** string-in/string-out function: no I/O, deterministic, and property-testable.
- Each redacted span becomes a typed placeholder (for example `[REDACTED:github_token]`), so downstream analysis can see that something was removed and of what kind.
- A redacted JSON line still parses as JSON.
- Redaction is on by default, and no configuration is needed to get it.
- A one-time backfill redacts rows already stored.

## Proposed Implementation

1. Extend `pii.py` with rule families for bearer tokens, credentialed URIs and high-entropy tokens. The high-entropy rule needs a false-positive guard so commit SHAs, UUIDs and content hashes are not redacted.
2. Add a single redaction call on each of the three insert paths, applied before the row is built. If any ingest dedup, watermark or fingerprint keys on `raw_line` content, compute it consistently: either always from the redacted form, or before redaction. Do not mix the two.
3. Add a backfill command or migration over existing `raw_events` rows. It must be idempotent and safe to re-run, and it reports counts per rule.

## Acceptance Criteria

- All three insert paths redact before writing. There is a test per path that plants a secret from each rule family and asserts it is absent from the stored row, local and remote alike.
- The new rule families are present (bearer tokens, credentialed URIs, high-entropy tokens). Tests assert commit SHAs, UUIDs and content hashes are left intact.
- Property tests on the redactor:
  - idempotence: `redact(redact(x)) == redact(x)`;
  - it never adds secret-shaped content;
  - a JSON line stays valid JSON after redaction.
- The backfill redacts existing rows, is idempotent, prints per-rule counts, and leaves ingest dedup and watermarks working.

## Out of Scope

- Redaction on export paths beyond ingest. That is follow-on work once ingest is clean.
- Whether reasoning blocks should be stored at all. This issue only guarantees that whatever is stored is redacted.
