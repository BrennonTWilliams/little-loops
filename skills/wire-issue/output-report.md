# Phase 10: Output Report template

Emit this block verbatim at the end of a run, substituting the bracketed values.

```
================================================================================
WIRE ISSUE: {{ISSUE_ID}}
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH|EPIC]
- Title: [title]
- Mode: [Interactive | Auto] [--dry-run]

## WIRING RESEARCH SUMMARY
- Agents run: Caller Tracer, Side-Effect Tracer, Test Gap Finder
- Key symbols traced: [N] (e.g., function_name, ClassName, --flag)

## MISSING WIRING FOUND

| Category | Count | Files |
|----------|-------|-------|
| Callers/Importers | N | [brief list] |
| Registrations/Manifests | N | [brief list] |
| Documentation | N | [brief list] |
| Tests (update) | N | [brief list] |
| Tests (new) | N | [brief list] |
| Config/Schema | N | [brief list] |
| Impl Step gaps | N | [brief descriptions] |

## INTEGRATION MAP CHANGES

### Added to Dependent Files
- `path/to/caller.py` — calls `affected_fn()` in `handle_request()`
### Added to Files to Modify
- `plugin.json` — registration entry needed
### Added to Documentation
- `docs/api.md` — describes changed interface under section "API Reference"
### Added to Tests
- `tests/test_affected.py` — update for new behavior
- `tests/test_new.py` — new test file needed

## IMPLEMENTATION STEPS CHANGES
- [N] wiring touchpoints added

## FILE STATUS
- [Modified | Not modified (--dry-run | nothing to add)]

## NEXT STEPS
- Run `/ll:confidence-check {{ISSUE_ID}}` to re-evaluate readiness with full wiring
- Run `/ll:ready-issue {{ISSUE_ID}}` to validate the enriched issue
- Run `/ll:manage-issue` to implement
- If `/ll:confidence-check` or `/ll:ready-issue` still fail after this wiring pass (and 2+ prior refinement passes), run `/ll:issue-size-review {{ISSUE_ID}}` — a persistent readiness gap after wiring often signals the issue is too large or ambiguously scoped, not just under-researched
- Note: if `decision_needed: true` is still set, run `/ll:decide-issue {{ISSUE_ID}}` before wiring to select the implementation approach

================================================================================
```
