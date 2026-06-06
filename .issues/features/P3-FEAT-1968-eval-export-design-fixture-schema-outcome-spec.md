---
id: FEAT-1968
title: 'eval-export design: fixture schema + outcome extraction spec'
type: FEAT
priority: P3
status: open
parent: FEAT-1920
relates_to:
- FEAT-1920
- FEAT-1969
- EPIC-1918
labels:
- ll-logs
- eval
- design
- decision
decision_needed: true
confidence_score: 84
outcome_confidence: 88
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 25
size: Very Large
---

# FEAT-1968: eval-export design — fixture schema + outcome extraction spec

## Summary

Resolve the open design decisions blocking `ll-logs eval-export` (FEAT-1920):
confirm the fixture schema `ll-harness` expects, define how "outcome" is extracted
from session logs via the ENH-1919 extractor, specify what constitutes "input context",
and document the redaction approach. Output: a decision record and an updated spec
consumed by FEAT-1969.

## Parent Issue

Decomposed from FEAT-1920: ll-logs eval-export — sessions to ll-harness fixtures

## Current Behavior

`ll-harness` and `/ll:create-eval-from-issues` consume fixtures in an undocumented
(or only implicitly specified) format. The ENH-1919 extractor yields skill-invocation
n-gram sequences, not the surrounding user prompt or any outcome quality signal.
These gaps block a correct implementation.

## Expected Behavior

After this issue:

1. The fixture schema `ll-harness` expects is documented (fields, types, required vs. optional).
2. A concrete definition of "outcome" extractable from logs exists — what log evidence
   qualifies as a success/failure signal and how to represent it in a fixture record.
3. "Input context" is specified — which fields from the log record (user prompt text,
   issue ID, skill name, etc.) are captured and how they map to fixture fields.
4. A redaction strategy is documented — what patterns are stripped before writing fixtures,
   and whether redaction is best-effort or blocking.
5. The spec is recorded as a `ll-issues decisions add` entry so FEAT-1969 can reference it.

## Motivation

This design issue unblocks FEAT-1969 (eval-export implementation):
- Without a confirmed fixture schema, FEAT-1969 implementers must guess at field names, types, and required vs. optional constraints — leading to inconsistencies with `ll-harness` expectations.
- The ENH-1919 extractor yields invocation sequences but no definition of "outcome" exists — without this, any fixture generation logic would be arbitrary.
- Recording decisions in `.ll/decisions.yaml` creates a durable, referenceable spec across all eval-export sub-issues (FEAT-1969, FEAT-1970, FEAT-1971).

## Use Case

**Who**: Developer picking up FEAT-1969 (eval-export implementation)

**Context**: About to implement `ll-logs eval-export` and needs design clarity before writing any code

**Goal**: Confirm what a `ll-harness`-compatible fixture file looks like, what counts as an "outcome" extractable from logs, which fields constitute "input context", and what the redaction scope is

**Outcome**: Has a `decisions.yaml` entry with the confirmed spec to reference throughout FEAT-1969, FEAT-1970, and FEAT-1971 implementation

## Proposed Solution

### Step 1 — Confirm fixture schema

Read `scripts/little_loops/cli/harness.py`. Identify the dataclass or dict structure
that `ll-harness` loads from fixture files. Note required vs. optional fields, types,
and any validation logic.

### Step 2 — Assess ENH-1919 extractor output

Read the invocation extractor (in `cli/logs.py` or adjacent module introduced by ENH-1919).
Determine what fields it yields per invocation: skill name, session ID, surrounding
messages, timestamps, exit signals. Map each field to a fixture field or mark as
unrepresentable.

### Step 3 — Define "outcome"

Decide: does `eval-export` capture *quality* outcomes (was the skill output good?) or
*execution* outcomes (did the invocation complete without error, did the user accept
the result)? Logs provide execution signals only. Document the chosen definition and
its limitations.

### Step 4 — Define "input context"

Specify which log fields constitute the input context for a fixture: the raw user
message, the issue ID extracted from the session, the skill invocation command, or
some combination. Define the extraction rule.

### Step 5 — Document redaction approach

Specify: what is redacted (absolute file paths? email addresses? API keys?), whether
redaction is regex-based or model-assisted, and whether a session with unredactable
content is skipped or partially redacted. Keep scope minimal — best-effort regex
pattern list is sufficient for MVP.

### Step 6 — Record decisions

Use `ll-issues decisions add` to record the schema mapping, outcome definition,
input-context spec, and redaction approach as a decision entry referencing FEAT-1968.
Update this issue's frontmatter to `decision_needed: false` once recorded.

## Integration Map

### Files to Read (no writes in this issue)
- `scripts/little_loops/cli/harness.py` — fixture schema source of truth
- `scripts/little_loops/cli/logs.py` — ENH-1919 extractor output fields

### Files to Write
- `.ll/decisions.yaml` — decision record via `ll-issues decisions add`

## Implementation Steps

1. Read `cli/harness.py` and extract fixture schema definition.
2. Read `cli/logs.py` and map ENH-1919 extractor output fields.
3. Write outcome definition, input-context spec, and redaction approach.
4. Record as a `ll-issues decisions add` entry.
5. Update frontmatter: `decision_needed: false`.

## Acceptance Criteria

- `cli/harness.py` fixture schema is documented (fields + types).
- Outcome definition is written and recorded in decisions.yaml.
- Input-context extraction rule is written and recorded.
- Redaction approach is documented.
- `decision_needed: false` in this issue's frontmatter after decisions are recorded.

## API/Interface

N/A — No public API changes. This issue produces a `decisions.yaml` entry documenting the fixture schema and extraction spec; no new code or public interfaces are introduced.

## Impact

- **Priority**: P3 — unblocks FEAT-1969 implementation
- **Effort**: Small — read existing code + write decisions; no new code
- **Risk**: Low — read-only investigation with a single write to decisions.yaml
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-05_

**Readiness Score**: 84/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 88/100 → HIGH CONFIDENCE

### Concerns
- Step 1 contains a false premise: it instructs the implementer to "identify the dataclass or dict structure that `ll-harness` loads from fixture files," but `ll-harness` (`cli/harness.py`) does not load fixture files — it is a CLI tool accepting arguments (`runner`, `target`, `--exit-code`, `--semantic`). There is no fixture-loading dataclass to discover. The implementer must **design** the fixture schema from scratch, deciding what a `ll-harness`-compatible fixture file should contain (e.g., pre-defined runner/target/criteria fields in YAML).

## Session Log
- `/ll:format-issue` - 2026-06-06T03:28:17 - `6297c89c-86c7-4c08-ae25-157a34cfb566.jsonl`
- `/ll:issue-size-review` - 2026-06-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8be904b6-a889-49bc-bc5f-f854cacc72bb.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8be904b6-a889-49bc-bc5f-f854cacc72bb.jsonl`
