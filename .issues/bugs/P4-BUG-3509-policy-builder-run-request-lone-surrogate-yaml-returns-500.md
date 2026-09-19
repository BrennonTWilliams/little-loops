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

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- **File**: `scripts/little_loops/cli/artifact/policy_builder_routes.py`
- **Anchor**: `_parse_run_request` (line 164) — `yaml=yaml_text.encode("utf-8")` at line 187, inside the `RunRequest(...)` construction, outside any `try`.
- **Cause**: `json.loads` (line 167) accepts `\ud800` escapes; only `json.JSONDecodeError`/`UnicodeDecodeError` are translated to 400. The `yaml` guard (lines 178–179) checks only "non-empty `str`". `UnicodeEncodeError` is not a `_RouteError`, so the generic `except Exception` in `_json_error_boundary` (lines 103–126) returns `500 internal_error`. It is the only `.encode()` on client input in the request path.
- **Nothing is persisted before the failure**: the encode is `_submit`'s second statement (after `_read_request_body`), before `get_run_request`, `find_issues`, `validate_policy_revision`, `persist_policy_revision` and `create_or_get_run_request`.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- **Conventions in force**: input failures are raised as `_RouteError(400, "bad_request", "missing or malformed field: <name>")`, never handled inline; the `_require_*_field` validators and the inline `yaml` check share that message shape and never echo the value (evidence: `_parse_run_request`, `_require_str_field`, `_require_simple_str_field`). Two translation idioms exist and differ only in chaining: `from None` (JSON/Content-Length parse errors) vs `from exc` (`PolicyRevisionConflictError` → 409). No `UnicodeEncodeError`/lone-surrogate handling exists anywhere in the codebase to reuse.
- **Scope**: the `projectId`/`issueId` half of the fix is not needed — neither can reach a SQLite bind with a surrogate (see Integration Map). Only the `yaml` encode needs translation.
- **Test constraint**: `_submit_payload` decodes `yaml_bytes` as UTF-8 and cannot carry a lone surrogate; the regression test needs a hand-built body (as `test_malformed_json_returns_400` does with raw bytes) containing the JSON escape `\ud800`. Assert `status == 400`, `error.code == "bad_request"`, and `list_entries(DEFAULT_DB_PATH, root=project) == []` (as the 404/422 tests do); no existing test asserts that no revision snapshot was persisted.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- **Files to Modify**: `scripts/little_loops/cli/artifact/policy_builder_routes.py` (`_parse_run_request`, line 164); `scripts/tests/test_feat3504_policy_builder_serve.py` (`TestSubmitRoute`).
- **Dependents**: `_parse_run_request` is called only from `_make_submit_handler`'s `_submit` (line 194, wrapped by `_json_error_boundary` at line 275); registered by `make_run_request_routes` (line 327). The code-graph index returned no hits for these symbols, so this comes from direct reading.
- **`projectId`/`issueId` question resolved** (checked by execution: `sqlite3` binding a `"\ud800"` `str` raises `UnicodeEncodeError`):
  - `projectId` is only stored in `RunRequest.project_id` (line 176/184); never hashed, encoded or bound to SQLite. Not reachable as a failure.
  - `issueId` never reaches SQLite with a surrogate: `existing.issue_id != request.issue_id` (line 214) is a string comparison (surrogate → 409 `request_conflict`), and `find_issues` matching (line 229) fails for a surrogate value (→ 404 `issue_not_found`). It reaches `create_or_get_run_request` (`queue_store.py:793`, INSERT at ~863) only if it equals a real on-disk issue ID. So the SQLite path is not a live 500 for these two fields; whether a real issue ID could itself contain a surrogate (filesystem `surrogateescape`) was not verified.
  - `requestId`/`revisionId`/`workspaceId` are regex-guarded ASCII hex (`_REQUEST_ID_RE`, `_REVISION_ID_RE`, `_WORKSPACE_ID_RE`, lines 46–48) and reject surrogates as 400.
  - `_send_json` (line 79) uses `json.dumps(...).encode("utf-8")` with default `ensure_ascii`, and error messages are static, so the response path cannot re-raise.
- **Docs**: `docs/reference/API.md` (~line 11073 body-guard list; ~11087 error-boundary paragraph) documents the run-request 400/500 contract; `docs/ARCHITECTURE.md` (~line 845) mentions `_RouteError`/run-request.

## Program Design

### Types

- `_RouteError`: existing exception carrying `(status, code, message)`; caught by `_json_error_boundary`

### Signatures

- `_parse_run_request(payload_bytes: bytes) -> tuple[RunRequest, dict[str, Any]]` — existing; wrap the `yaml_text.encode("utf-8")` call
- `_require_simple_str_field(payload: dict[str, Any], name: str) -> str` — existing; extend only if a surrogate in `projectId`/`issueId` is shown to fail in SQLite

### Call Path

`_json_error_boundary` -> `_make_submit_handler` (`_submit`) -> `_parse_run_request` -> `_RouteError(400, "bad_request", ...)`

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


## Session Log
- `/ll:refine-issue` - 2026-09-19T05:00:47 - `a66fb80c-9d10-4fe7-8d3d-b0bd004691a0.jsonl`
- `/ll:format-issue` - 2026-09-19T04:57:19 - `69495f4f-08a7-41bc-a23e-7129d0989d49.jsonl`
