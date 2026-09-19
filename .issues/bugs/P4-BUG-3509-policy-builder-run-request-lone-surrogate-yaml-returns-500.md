---
id: BUG-3509
type: BUG
title: Policy builder run-request returns 500 for YAML containing a lone surrogate
priority: P4
status: open
discovered_by: manual-review
discovered_date: '2026-09-19'
captured_at: '2026-09-19T00:00:00Z'
parent: EPIC-3493
labels:
- policy-builder
relates_to:
- FEAT-3504
- FEAT-3505
---

# BUG-3509: Policy builder run-request returns 500 for YAML containing a lone surrogate

## Summary

`POST /{token}/run-request` answers `500 internal_error` instead of `400 bad_request` when the JSON `yaml` string contains an unpaired UTF-16 surrogate. Found while reviewing FEAT-3505.

## Location

- **File**: `scripts/little_loops/cli/artifact/policy_builder_routes.py`
- **Anchor**: `_parse_run_request` — `yaml=yaml_text.encode("utf-8")`

## Steps to Reproduce

1. `ll-artifact serve --policy-builder`.
2. POST an otherwise valid run-request body whose `yaml` value contains `"\ud800"` (a JSON-escaped lone surrogate).

## Current Behavior

`json.loads` accepts the escape and yields a `str` holding a lone surrogate. `yaml_text.encode("utf-8")` raises `UnicodeEncodeError`, which is not a `_RouteError`, so `_json_error_boundary` logs it and returns `500 internal_error`.

## Expected Behavior

`400 bad_request` with `missing or malformed field: yaml` — malformed client input is a definitive application rejection, not a server failure.

## Motivation

The page (FEAT-3505) treats 5xx as `outcome_unknown` and reconciles via readback; readback returns `404 request_not_found`, which offers a retry of the identical envelope — a loop with no exit. FEAT-3505 adds a client-side `isWellFormed()` review guard, but the server should still classify the input correctly for any other client.

## Proposed Solution

In `_parse_run_request`, wrap the encode:

```python
try:
    yaml_bytes = yaml_text.encode("utf-8")
except UnicodeEncodeError:
    raise _RouteError(400, "bad_request", "missing or malformed field: yaml") from None
```

`projectId`/`issueId` are never encoded by the route, but check whether a surrogate in them reaches SQLite (`create_or_get_run_request`) and fails the same way; if so, reject them in `_require_simple_str_field`.

## Acceptance Criteria

- [ ] A run-request whose `yaml` contains a lone surrogate returns `400 bad_request` with a JSON `ErrorBody`; nothing is persisted or enqueued.
- [ ] Lone surrogates in `projectId`/`issueId` return `400`, not `500` (or are shown not to fail).
- [ ] Regression test in `scripts/tests/test_feat3504_policy_builder_serve.py`.

## Impact

- Priority: P4 — malformed-input edge case; the builder's serializer does not normally emit lone surrogates.
- Effort: Small.
- Risk: Low.

## Status

**Open** | Created: 2026-09-19 | Priority: P4
