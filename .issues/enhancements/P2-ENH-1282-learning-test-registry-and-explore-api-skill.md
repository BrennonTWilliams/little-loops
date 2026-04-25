---
id: ENH-1282
type: ENH
priority: P2
captured_at: "2026-04-25T18:06:01Z"
discovered_date: "2026-04-25"
discovered_by: capture-issue
---

# ENH-1282: Learning Test Registry and ll:explore-api Skill

## Summary

Add a `.ll/learning-tests/` registry directory that stores executed proof records of external system behaviors, paired with a new `ll:explore-api` skill that implements the full Feathers Learning Test lifecycle (Ingest → Hypothesize → Execute → Refine). Together they give agents institutional knowledge of proven assumptions before committing to architecture.

## Current Behavior

When an agent encounters an unfamiliar external system (API, SDK, binary), it either hallucinates behavior from stale docs or requires a human to manually investigate. There is no structured way to capture, execute, and store proof-of-behavior for external systems. Assumption leakage causes faulty premises at discovery time to invalidate entire implementations.

## Expected Behavior

Running `/ll:explore-api "Anthropic SDK streaming"` triggers a structured discovery session:
1. **Ingest** — reads relevant docs and existing code samples for the target
2. **Hypothesize** — generates specific testable claims (e.g., "streaming events are dicts with `type` key")
3. **Execute** — scaffolds and runs a proof script against the live system, capturing stdout/stderr
4. **Refine** — diffs expected vs actual, updates claims, and saves a proof record to `.ll/learning-tests/<target>.md`

The registry then serves as institutional knowledge: any skill or loop can query it to check whether an assumption about a system has been deterministically proven before implementation begins.

## Motivation

The "slop code crisis" described in our architecture notes is directly caused by agents building on unproven assumptions. A learning test registry transforms one-off exploration into reusable, time-stamped proof. This prevents the same faulty assumption from being re-made across sessions and provides the deterministic foundation that the FSM learning state (ENH-1283) and issue lifecycle gate (ENH-1284) will build on. Without this, both dependent features have nothing to query.

## Proposed Solution

**Registry format** — `.ll/learning-tests/<slug>.md` with frontmatter:
```yaml
---
target: "Anthropic SDK streaming"
date: "2026-04-25"
status: proven  # proven | refuted | stale
assertions:
  - claim: "streaming events are dicts with a `type` key"
    result: pass
  - claim: "fork_session=true is required for resumed sessions"
    result: pass
raw_output_path: ".ll/learning-tests/raw/anthropic-sdk-streaming.txt"
---
```

**`ll:explore-api` skill** (new file: `skills/explore-api/SKILL.md`):
- Accepts a target string and optional assumption list
- Scaffolds a minimal runnable proof script (Python or TypeScript based on target)
- Executes via `Bash` and captures output
- Parses pass/fail per claim, writes registry record
- Reports proven facts back to conversation context

**Query interface** — `ll-issues` or a helper function that other skills can call: `check_learning_test(target: str) -> LearnTestRecord | None`

## Integration Map

### Files to Modify
- `scripts/little_loops/` — add `learning_tests.py` module for registry read/write
- `scripts/pyproject.toml` — no new deps expected

### Dependent Files (Callers/Importers)
- ENH-1283 (`learning` FSM state) will call the registry to verify tests ran before advancing
- ENH-1284 (issue lifecycle gate) will query the registry during `ll:ready-issue`

### Similar Patterns
- `.ll/ll-config.json` — same directory pattern for project-local state
- `scripts/little_loops/issue_parser.py` — frontmatter parsing pattern to reuse

### Tests
- `scripts/tests/test_learning_tests.py` — new test file for registry CRUD
- Test: create record, read back, mark stale

### Documentation
- `docs/ARCHITECTURE.md` — add learning test registry section
- `docs/reference/API.md` — document `learning_tests` module

### Configuration
- `.ll/ll-config.json` — optional `learning_tests.stale_after_days` setting

## Implementation Steps

1. Create `.ll/learning-tests/` directory structure and define registry record schema
2. Implement `scripts/little_loops/learning_tests.py` with read/write/query functions
3. Scaffold `skills/explore-api/SKILL.md` with Ingest → Hypothesize → Execute → Refine flow
4. Wire skill to write registry records on completion
5. Add `scripts/tests/test_learning_tests.py` with unit tests
6. Update `docs/ARCHITECTURE.md` and `docs/reference/API.md`

## Success Metrics

- Running `/ll:explore-api` produces a `.ll/learning-tests/` record with at least one proven/refuted claim
- Registry records are queryable by other skills/loops without re-executing proofs
- Stale records (configurable age) are flagged during queries

## Scope Boundaries

- Out of scope: automatic staleness enforcement (records are flagged, not auto-deleted)
- Out of scope: sharing registry records across projects
- Out of scope: UI for browsing the registry (plain markdown files serve as the interface)

## API/Interface

```python
# scripts/little_loops/learning_tests.py

@dataclass
class Assertion:
    claim: str
    result: Literal["pass", "fail", "untested"]

@dataclass
class LearnTestRecord:
    target: str
    date: str
    status: Literal["proven", "refuted", "stale"]
    assertions: list[Assertion]
    raw_output_path: str | None

def write_record(record: LearnTestRecord) -> Path: ...
def read_record(target_slug: str) -> LearnTestRecord | None: ...
def list_records() -> list[LearnTestRecord]: ...
def mark_stale(target_slug: str) -> None: ...
```

## Impact

- **Priority**: P2 — This is the foundation for two downstream features (ENH-1283, ENH-1284) and directly addresses assumption leakage in autonomous runs
- **Effort**: Medium — New skill + new Python module + registry schema design; reuses existing frontmatter parsing patterns
- **Risk**: Low — Additive only; no existing behavior changes
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | System design context for where registry fits |
| `docs/deterministic-backpressure-learning-tests.md` | Source philosophy and Learning Test lifecycle definition |

## Labels

`enhancement`, `autonomy`, `learning-tests`, `captured`

## Session Log

- `/ll:capture-issue` — 2026-04-25T18:06:01Z — `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/771faa3d-a5a9-41eb-a550-7a0938c98004.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P2
