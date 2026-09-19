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
- **Docs**: `docs/reference/API.md` (~line 11073 body-guard list; ~11087 error-boundary paragraph) documents the run-request 400/500 contract; `docs/ARCHITECTURE.md` has no mention of `policy_builder_routes`/`_RouteError`/run-request (verified by grep) — no change needed.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/serve.py` — `cmd_serve` (line ~219) imports `make_run_request_routes`; consumes the route table only, no change needed [Agent 1 finding]
- `scripts/tests/test_feat3504_policy_builder_serve.py` — also imports `make_run_request_routes` (line 26) and monkeypatches `policy_builder_routes` (line ~300, in the unsupported-mode test); unaffected by an added `except` in `_parse_run_request` [Agent 1 finding]
- `.issues/features/P3-FEAT-3505-policy-builder-connected-page-submission-controller-and-ui.md` — `relates_to`; its client-side `isWellFormed()` review guard is the paired half of this fix, and its `outcome_unknown` → `404 request_not_found` retry loop is what the 400 removes for other clients [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat3504_policy_builder_serve.py` — add `test_lone_surrogate_yaml_returns_400` in `TestSubmitRoute`, modeled on `test_malformed_json_returns_400` (line 318): build the raw body by hand (the `_submit_payload` helper, line 81, UTF-8-decodes `yaml_bytes` and cannot carry `\ud800`), POST via `_lb_http_request(_port(bridge), "POST", f"/{bridge._token}/run-request", body=...)`, assert `status == 400` and `error.code == "bad_request"`, then assert `list_entries(DEFAULT_DB_PATH, root=project) == []` as the 404/422 tests do [Agent 3 finding]
- No existing test asserts a 500 for this input, so none will break [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `## little_loops.cli.artifact.policy_builder_routes`, "Submit (`POST run-request`)" step 1 (line ~11073): the body-guard list says "`yaml` a non-empty string"; extend to "a non-empty string encodable as UTF-8 (a lone surrogate is `400`)" [Agent 2 finding]
- `scripts/tests/test_wiring_reference_docs.py` — asserts the `policy_builder_routes` section of `docs/reference/API.md` exists (line 243); a wording edit inside the section will not trip it [Agent 2 finding]
- `docs/ARCHITECTURE.md` — grep for `policy_builder_routes`/`run-request` returned no hits, so the "~line 845" note in the map above is unverified; no change needed [Agent 2 finding]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/artifact/policy_builder_routes.py` — wrap `yaml_text.encode("utf-8")` in `_parse_run_request` in `try/except UnicodeEncodeError` and raise `_RouteError(400, "bad_request", "missing or malformed field: yaml") from None`
- Update `scripts/tests/test_feat3504_policy_builder_serve.py` — add the hand-built-body lone-surrogate regression test in `TestSubmitRoute`
- Update `docs/reference/API.md` — amend the step-1 body-guard list for `yaml`

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

## Verification Notes

Verified 2026-09-19 by `/ll:verify-issues --auto`.

Verdict at time of check: **NEEDS_UPDATE** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- **Corrected**: Integration Map claimed `docs/ARCHITECTURE.md` (~line 845) mentions `_RouteError`/run-request; grep finds no such mention. Replaced with a "no change needed" note (the wiring pass had already flagged this).
- **Confirmed**: all `policy_builder_routes.py` anchors and lines match current code (`_parse_run_request` 164, `json.loads` 167, `yaml` guard 178–179, unguarded `.encode` 187, `_json_error_boundary` 103–126, `_submit` 194, boundary wrap 275); `_send_json` uses `json.dumps(...).encode("utf-8")`; regexes at lines 46–48. Test anchors (`test_malformed_json_returns_400` 318, `_submit_payload` 81, `list_entries`/`DEFAULT_DB_PATH` import) and `docs/reference/API.md` line 11073 body-guard text confirmed.
- **Cause claim** (unencodable lone surrogate → `UnicodeEncodeError` → generic `except Exception` → 500) is read directly from the code path, not inferred.
- **Proposal check (B6)**: the proposed `except UnicodeEncodeError` sits outside the `_json_error_boundary`-caught path only until translated to `_RouteError`; no handler or fixture conflict; ACs cover all listed integration points.
- **Other checks**: no active required decision rules; `ll-verify-evidence` clean; no file modified since FEAT-3504 introduced the route.
- Graph: no `ll-code` queries were needed (the index has no hits for these symbols; verified by direct reading).

## Status

**Open** | Created: 2026-09-19 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-09-19T05:03:56 - `aa2a75e7-1776-48b9-b2b9-b1a0d3366543.jsonl`
- `/ll:wire-issue` - 2026-09-19T05:02:18 - `9675dd68-c6a3-46ca-a4f4-9deec88ce9a0.jsonl`
- `/ll:refine-issue` - 2026-09-19T05:00:47 - `a66fb80c-9d10-4fe7-8d3d-b0bd004691a0.jsonl`
- `/ll:format-issue` - 2026-09-19T04:57:19 - `69495f4f-08a7-41bc-a23e-7129d0989d49.jsonl`
