---
id: ENH-1284
title: Learning Test Gate in Issue Lifecycle
type: ENH
priority: P4
captured_at: "2026-04-25T18:06:01Z"
discovered_date: "2026-04-25"
discovered_by: capture-issue
parent: EPIC-1694
status: open
decision_needed: false
---

# ENH-1284: Learning Test Gate in Issue Lifecycle

## Summary

Add a `learning_tests_required` field to issue frontmatter. `ll:ready-issue` and `ll:go-no-go` check whether learning tests have been executed for each declared assumption about external systems, blocking readiness with "unproven assumption: X" when tests are missing or stale.

## Current Behavior

`ll:ready-issue` (`commands/ready-issue.md`) and `ll:go-no-go` (`skills/go-no-go/SKILL.md`) evaluate issue quality based on completeness of written fields (Summary, Integration Map, Implementation Steps, etc.) but have no mechanism to verify that assumptions about external systems have been empirically proven. An issue claiming "this uses the Anthropic streaming API in mode X" is accepted as-is even if that behavior has never been tested against the live system.

The `ready-issue` command performs six sequential check phases (flags, file resolution, content validation, closure conditions, verdict, auto-correction) with a Dependency Status check already present in section 2 (`commands/ready-issue.md:163`) — but no equivalent check for epistemic readiness against the learning test registry.

The learning test registry itself already exists: `scripts/little_loops/learning_tests.py` and the `ll-learning-tests check <target>` CLI (exit 0 = record found, exit 1 = not found) are fully operational.

## Expected Behavior

Issue frontmatter can declare required learning tests:

```yaml
learning_tests_required:
  - "Anthropic SDK streaming events"
  - "GitHub API pagination"
```

When `ll:ready-issue` runs, it queries the learning test registry (via `check_learning_test()` or `ll-learning-tests check <target>`) for each target:
- **Proven and fresh** (`status: "proven"`) → passes, noted in VALIDATION table
- **Stale** (`status: "stale"`) → WARN row in VALIDATION; does not block readiness
- **Missing** (exit 1 from `ll-learning-tests check`) → NOT_READY with: `❌ Unproven assumption: "Anthropic SDK streaming events" — run /ll:explore-api "Anthropic SDK streaming events"`
- **Refuted** (`status: "refuted"`) → hard NOT_READY with explanation of what the actual behavior was

`ll:go-no-go` surfaces unproven assumptions as additional context injected into the judge agent's evaluation dimensions (not a numeric delta — the skill uses adversarial qualitative reasoning, not numeric scoring).

## Motivation

Issue lifecycle gates (ready-issue, go-no-go) currently check structural quality but not epistemic quality — whether the issue's premises are grounded in observed reality. This is the human-workflow complement to the FSM learning state (FEAT-1283): even in interactive (non-loop) sessions, the gate prevents an agent from starting implementation on an issue where key external behaviors are assumed rather than proven.

The shell-primitive (`scripts/little_loops/loops/ready-to-implement-gate.yaml`, FEAT-1695) and assumption-firewall loop (FEAT-1696) already handle this at the FSM layer. ENH-1284 adds the same gate to the interactive workflow via `ready-issue` and `go-no-go`.

## Proposed Solution

### 1. `IssueInfo` frontmatter field registration

Add to `scripts/little_loops/issue_parser.py`:

```python
# IssueInfo dataclass (after line 269, following testable/decision_needed/missing_artifacts pattern)
learning_tests_required: list[str] | None = None

# to_dict() (after line 314)
"learning_tests_required": self.learning_tests_required,

# from_dict() (after line 352)
learning_tests_required=data.get("learning_tests_required"),

# from_frontmatter() — simple list of strings; parse_frontmatter() already handles
# `- item` lists, so no coercion block is needed (unlike bool fields)
learning_tests_required=frontmatter.get("learning_tests_required"),
```

### 2. `commands/ready-issue.md` — new check phase

Insert a **Learning Test Gate** subsection immediately after the Dependency Status check (line 163). Follow the exact structural pattern:

```markdown
#### Learning Test Gate
- [ ] If `learning_tests_required` frontmatter field is present and non-empty:
  - For each target string in the list:
    - Run: `ll-learning-tests check "<target>"`
    - Exit 0 + `"status": "proven"` → PASS row in VALIDATION
    - Exit 0 + `"status": "stale"` → WARN row: "Stale: re-run /ll:explore-api \"<target>\""
    - Exit 0 + `"status": "refuted"` → FAIL: hard NOT_READY block; include refutation summary
    - Exit 1 (not found) → FAIL: NOT_READY block with: "❌ Unproven assumption: \"<target>\" — run /ll:explore-api \"<target>\""
- [ ] If `learning_tests_required` is absent or empty: PASS (gate is opt-in)
```

Also add a `Learning Tests` row to the `## VALIDATION` output table (currently at line 334), between `Blockers` and other rows.

### 3. `skills/go-no-go/SKILL.md` — registry context in judge dimensions

The go-no-go skill uses adversarial agents (pro/con) feeding a judge (Phase 3b/3d) that evaluates four qualitative dimensions. There are no numeric score deltas. To surface learning test status:

Before launching the pro/con agents (Step 3b), pre-fetch registry status for all `learning_tests_required` targets and inject a **Learning Test Context** block into both adversarial agent prompts and the judge prompt:

```
## Learning Test Context
- "Anthropic SDK streaming events": proven (2026-05-10)
- "GitHub API pagination": MISSING — unproven assumption
```

The judge's `RATIONALE` and `DECIDING FACTOR` sections will incorporate this evidence naturally. No numeric deltas needed.

### 4. `docs/reference/ISSUE_TEMPLATE.md` — field documentation

Add `learning_tests_required` to the `## Frontmatter Fields` table (around line 876) and a dedicated `### learning_tests_required` sub-section with example YAML.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — add `learning_tests_required: list[str] | None = None` to `IssueInfo` dataclass (line ~267), `to_dict()` (line ~312), `from_dict()` (line ~350), and `from_frontmatter()` (line ~447); no coercion block needed (plain string list)
- `commands/ready-issue.md` — add Learning Test Gate subsection after Dependency Status (line 163); add VALIDATION table row (line 334)
- `skills/go-no-go/SKILL.md` — inject pre-fetched registry context block into adversarial agent and judge prompts in Phase 3b/3d
- `docs/reference/ISSUE_TEMPLATE.md` — add `learning_tests_required` to `## Frontmatter Fields` table and add a dedicated sub-section

### Dependent Files (read-only)
- `scripts/little_loops/learning_tests.py` — `check_learning_test(target: str) -> LearnTestRecord | None` (line 140); `LearnTestRecord.status: Literal["proven", "refuted", "stale"]`; `LearnTestRecord.to_dict()` for JSON serialization
- `scripts/little_loops/cli/learning_tests.py` — `cmd_check()` exit contract: exit 0 = record found (check `status` in JSON stdout), exit 1 = not found

### Similar Patterns
- `scripts/little_loops/issue_parser.py:267` — `decision_needed: bool | None = None` — field registration pattern
- `commands/ready-issue.md:163` — Dependency Status check — structural template for the new gate
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — `check_next` state — existing shell gate using `ll-learning-tests check` (status parsing: `| python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('status',''))"`)

### Tests
- `scripts/tests/test_ready_issue_lint.py` — existing ready-issue test patterns to extend
- `scripts/tests/test_learning_tests.py` — existing registry tests; add fixtures for proven/stale/refuted/missing scenarios
- New tests: issue with `learning_tests_required` + missing target → NOT_READY; issue with all proven targets → READY; refuted target → hard NOT_READY

### Documentation
- `docs/reference/ISSUE_TEMPLATE.md` — `## Frontmatter Fields` table (line ~876)
- `docs/development/TROUBLESHOOTING.md` — add entry for learning test gate failures

### Configuration
- N/A — uses registry from `scripts/little_loops/learning_tests.py`; no new config needed

## Implementation Steps

1. **Register `learning_tests_required` in `IssueInfo`** (`scripts/little_loops/issue_parser.py:267`): add dataclass field, `to_dict()` key, `from_dict()` read, and `from_frontmatter()` passthrough — follow the `decision_needed` pattern (lines 268, 313, 351, 457)
2. **Add Learning Test Gate to `commands/ready-issue.md`**: insert subsection after Dependency Status (line 163); add VALIDATION table row (line 334); follow the exact bullet-list structure of Dependency Status for consistency
3. **Inject learning test context into `skills/go-no-go/SKILL.md`** Phase 3b: before launching adversarial agents, fetch registry status for each `learning_tests_required` target via `ll-learning-tests check`; inject a formatted context block into both pro/con agent prompts and the judge prompt
4. **Write tests** in `scripts/tests/test_ready_issue_lint.py` and `scripts/tests/test_learning_tests.py`: proven target passes, missing target blocks with message, refuted target hard-blocks, empty `learning_tests_required` is ignored
5. **Document** `learning_tests_required` in `docs/reference/ISSUE_TEMPLATE.md` `## Frontmatter Fields` table; add `docs/development/TROUBLESHOOTING.md` entry

## Success Metrics

- An issue with `learning_tests_required` and missing registry entries is blocked by `ll:ready-issue` with the exact message: `❌ Unproven assumption: "<target>" — run /ll:explore-api "<target>"`
- An issue with all proven targets passes the gate with a PASS row in the VALIDATION table
- `ll:go-no-go` reflects registry status in the judge's evidence when `learning_tests_required` is present
- Issues without `learning_tests_required` are unaffected

## Scope Boundaries

- Out of scope: auto-running `ll:explore-api` from within `ll:ready-issue` (user should run it manually)
- Out of scope: requiring `learning_tests_required` for all issues (field is opt-in)
- Out of scope: changing issue file structure beyond adding the frontmatter field
- Out of scope: numeric confidence score deltas in `go-no-go` — the skill uses qualitative adversarial reasoning; inject as context, not as numeric modifiers

## API/Interface

```yaml
# Issue frontmatter
---
id: ENH-1300
learning_tests_required:
  - "Anthropic SDK streaming events"
  - "GitHub API pagination"
---
```

```bash
# Shell gate pattern (from ready-to-implement-gate.yaml)
ll-learning-tests check "Anthropic SDK streaming events"
# exit 0 → record found; parse status from stdout JSON
# exit 1 → record not found (missing)
STATUS=$(ll-learning-tests check "$TARGET" 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('status',''))" \
  2>/dev/null || echo "")
```

## Impact

- **Priority**: P4 (deferred) — Valuable but lower urgency than FEAT-1283; depends on registry adoption after FEAT-1282 ships
- **Effort**: Small-Medium — Additive check in two existing commands + one dataclass field; no new infrastructure
- **Risk**: Low — Opt-in field; issues without it are unaffected
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/research/_Archive/deterministic-backpressure-learning-tests.md` | Source philosophy; "assumption leakage" concept |
| `docs/ARCHITECTURE.md` | Issue lifecycle and ready-issue architecture |
| `scripts/little_loops/loops/ready-to-implement-gate.yaml` | Already-shipped FSM primitive; ENH-1284 is the interactive-workflow complement |
| `.issues/features/P2-FEAT-1695-ready-to-implement-gate-shell-driven-learning-test-gate-primitive.md` | Shell-driven gate — same `ll-learning-tests check` pattern used here |

## Labels

`enhancement`, `deferred`, `issue-lifecycle`, `learning-tests`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-06-02T23:42:40 - `87fe1b1a-2ce7-4463-81b3-4d0dd2ce232e.jsonl`
- `/ll:refine-issue` - 2026-06-02T00:00:00 - `refine-issue-run`
- `/ll:format-issue` - 2026-06-02T23:33:49 - `65f77860-d771-4c40-9ba9-2bc9f9139bfe.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:35 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`

- `/ll:capture-issue` — 2026-04-25T18:06:01Z — `771faa3d-a5a9-41eb-a550-7a0938c98004.jsonl`

---

**Open (Deferred)** | Created: 2026-04-25 | Priority: P4
