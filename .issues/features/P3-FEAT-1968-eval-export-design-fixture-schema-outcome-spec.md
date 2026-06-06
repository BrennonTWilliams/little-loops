---
id: FEAT-1968
title: 'eval-export design: fixture schema + outcome extraction spec'
type: FEAT
priority: P3
status: done
testable: false
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
decision_needed: false
completed_at: 2026-06-06 04:47:30+00:00
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`harness.py` — CLI interface (no fixture loading)**
- `harness.py:32` — `_build_harness_parser()`: runner subcommands are `skill`, `cmd`, `mcp`, `prompt`
- `harness.py:22` — `RunnerResult` dataclass: `stdout`, `stderr`, `exit_code`, `timed_out`, `error`
- `harness.py:55` — evaluator flags: `--exit-code INT`, `--semantic TEXT`, `--timeout`, `--output`, `--verbose`
- **`ll-harness` does NOT load fixture files** (confirmed by confidence check + code read). A `--fixture FILE` mode does not exist. Fixture format must be designed by the FEAT-1969 implementer as a YAML record that serializes one `ll-harness` invocation.

**`logs.py` — ENH-1919 extractor (confirmed fields)**
- `logs.py:213` — `InvocationEvent` dataclass: only 3 fields: `tool_name: str`, `timestamp: str`, `session_id: str`
- `logs.py:221` — `_extract_ll_event_streams(project_folder, *, window_days)` → `dict[session_id, list[InvocationEvent]]`
- `logs.py:291` — `_extract_tool_name(record)` → detects skill name from `user` records (via `<command-name>/ll:name` pattern), `queue-operation` enqueues, and `assistant` Bash invocations
- `logs.py:1208` — `_events_from_jsonl(jsonl_path)` → extract invocation events from a single JSONL file
- The user prompt text is available in the same `user`-type JSONL record that triggers `_extract_tool_name` — `message.content[].text` contains the full user message including the `/ll:skill` invocation

**`pii.py` — existing redaction utilities (reusable)**
- `pii.py:26` — `detect_pii(text)` → `list[str]` of matched PII types
- `pii.py:39` — `redact_pii(text)` → replaces with `[EMAIL]`, `[PHONE]`, `[SSN]` placeholders
- `pii.py:54` — `apply_pii_action(example, action)` → flag/redact/discard on a dict of string values
- **Coverage gap**: `pii.py` covers email, phone, SSN only. Absolute paths (e.g., `/Users/brennon/`) are not yet covered — FEAT-1969 must add a path-stripping pass.

**`decisions.yaml` — existing entry schema**
- Confirmed fields: `id`, `type`, `timestamp`, `category`, `labels`, `rationale`, `rule`, `scope`, `issue`, `alternatives_rejected` (optional)
- Use `ll-issues decisions add` CLI — don't write `.ll/decisions.yaml` directly

**Related files for FEAT-1969 implementer**
- `scripts/tests/test_cli_harness.py` — test patterns for harness (model new harness batch tests after these)
- `scripts/tests/test_pii.py` — test patterns for PII utilities
- `scripts/little_loops/pii.py` — import: `from little_loops.pii import apply_pii_action, detect_pii, redact_pii`

## Implementation Steps

1. Read `cli/harness.py` and extract fixture schema definition.
2. Read `cli/logs.py` and map ENH-1919 extractor output fields.
3. Write outcome definition, input-context spec, and redaction approach.
4. Record as a `ll-issues decisions add` entry.
5. Update frontmatter: `decision_needed: false`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete references for each step:_

1. **Step 1 correction** — `cli/harness.py` has no fixture loader; `_build_harness_parser()` at `harness.py:32` is the fixture schema source: `runner` (skill/cmd/mcp/prompt), `target`, `runner_args`, `--exit-code`, `--semantic`, `--timeout`. A "fixture" is a YAML record serializing these args + provenance metadata. Design the `EvalFixture` schema from this surface.

2. **Step 2 confirmed** — `InvocationEvent` at `logs.py:213` yields only `tool_name`, `timestamp`, `session_id`. The user prompt is available from the same `user`-type record via `message.content[].text` — same record that `_extract_tool_name()` at `logs.py:291` operates on. The issue_id can be extracted via regex from that text if present.

3. **Step 3 guidance** — Two outcome signals available:
   - *Execution*: `history_reader.lookup_session_metadata(session_id)` returns `has_corrections` (bool), `issue_outcome` ("done" | None), `tool_count`, `files_modified`
   - *Error*: `_cmd_scan_failures()` in `logs.py` pattern — pair Bash `tool_use.id → ll_tool_name`, match `tool_result` with `is_error=True` or traceback text
   - Recommend classifying as: `accepted` (no correction, no error), `corrected` (`has_corrections=True`), `failed` (`is_error` found), `unknown`

4. **Step 4 command** — `ll-issues decisions add --type decision --category architecture --rule "<spec>" --rationale "<why>" --issue FEAT-1968 --config .`. See `test_cli_decisions.py:TestDecisionsCLIAdd` for working invocation examples.

5. **Step 5 — redaction guidance** — Reuse `redact_pii()` from `scripts/little_loops/pii.py:39` for email/phone/SSN. For absolute paths use `_ABS_PATH_RE = re.compile(r"/(?:[^\s,;\"']+/)+[^\s,;\"']+")` already defined at `logs.py:867` — call `.sub("<path>", text)`. Best-effort: emit `pii_detected: true` flag; do not block export.

## Acceptance Criteria

- `cli/harness.py` fixture schema is documented (fields + types).
- Outcome definition is written and recorded in decisions.yaml.
- Input-context extraction rule is written and recorded.
- Redaction approach is documented.
- `decision_needed: false` in this issue's frontmatter after decisions are recorded.

### Codebase Research Findings

_Added by `/ll:refine-issue`:_

- **Fixture schema** must address the false premise: `ll-harness` has no fixture loader. The designed schema must map to `ll-harness` CLI arguments (`runner`, `target`, `runner_args`, `exit_code`, `semantic`, `timeout`) plus provenance fields (`session_id`, `timestamp`, `input_context`, `issue_id`, `skill_name`, `outcome`, `pii_detected`). There is no existing dataclass to discover.
- **Outcome signal** is available from `history_reader.lookup_session_metadata()` (returns `has_corrections`, `issue_outcome`, etc.) — this is DB-backed and avoids re-parsing JSONL.
- **Similar fixture shape**: SFT corpus `_make_enriched_example()` in `test_loops_sft_corpus.py` (fields: `source`, `messages`, `metadata`) is the closest existing precedent.
- **Decisions.yaml `DecisionEntry` dataclass** in `scripts/little_loops/decisions.py` has fields: `id`, `type`, `timestamp`, `category`, `labels`, `rationale`, `rule`, `alternatives_rejected`, `issue`, `scope`, `outcome`. The `--alternatives-rejected` flag is optional but should be used to document rejected approaches for the fixture schema decision.

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

## Resolution

Recorded as decision **`ARCHITECTURE-017`** (`.ll/decisions.yaml`, scope: project,
issue: FEAT-1968) via `ll-issues decisions add`. All five design questions resolved;
each claim verified against current code before recording.

### Fixture schema — `EvalFixture` v1
One YAML record per reconstructed `ll-harness` invocation. **`ll-harness` has no
fixture loader** (`_build_harness_parser()` at `cli/harness.py:32` is argument-only) —
a fixture is an *export* artifact replayed by serializing fields back into
`ll-harness <runner> <target> [runner_args…] [--exit-code N] [--semantic TEXT] [--timeout S]`.

| Field | Req? | Type / notes |
|---|---|---|
| `runner` | required | `skill` \| `cmd` \| `mcp` \| `prompt` |
| `target` | required | str (skill name / command / mcp tool / prompt) |
| `runner_args` | optional | `list[str]`, default `[]` |
| `exit_code` | optional | int, `null` = unchecked |
| `semantic` | optional | str, `null` = unchecked |
| `timeout` | optional | int seconds, default `120` |
| `session_id` | required | provenance |
| `timestamp` | required | ISO 8601 |
| `input_context` | optional | redacted user-message text |
| `issue_id` | optional | regex `[A-Z]+-\d+` from `input_context` |
| `skill_name` | optional | `== target` when `runner == skill` |
| `outcome` | required | enum (below) |
| `pii_detected` | optional | bool, default `false` |

Required set = `{runner, target, session_id, timestamp, outcome}`.

### Outcome — execution, not quality
Logs carry no output-quality signal, so outcome is an **execution** taxonomy sourced
from `history_reader.lookup_session_metadata(session_id)` (DB-backed; avoids re-parsing
JSONL):
- `accepted` — `has_corrections=False` and no error
- `corrected` — `has_corrections=True`
- `failed` — a `tool_result` with `is_error` or a traceback present in the session
- `unknown` — `lookup_session_metadata()` returned `{}`

Precedence: `failed > corrected > accepted`.

### Input context
The raw user-message text (`message.content[].text`) of the `user`-type record that
`_extract_tool_name()` matched (`cli/logs.py:291`), after redaction. `issue_id` is
regex-extracted from that text when present.

### Redaction — best-effort, non-blocking
Apply `pii.redact_pii()` (email/phone/SSN, `pii.py:39`) then
`logs._ABS_PATH_RE.sub("<path>", text)` (`logs.py:867`) for absolute paths. Set
`pii_detected=true` if either fires. A session is **never skipped** for unredactable
content — export proceeds with the flag set. FEAT-1969 owns wiring the path pass
(coverage gap: `pii.py` lacks path stripping today).

**Unblocks** FEAT-1969 (implementation), FEAT-1970, FEAT-1971.

## Session Log
- `/ll:manage-issue` - 2026-06-06T04:47:30 - `40f687fb-36c6-40f9-b6a2-93b73f737f61.jsonl`
- `/ll:ready-issue` - 2026-06-06T04:44:05 - `cb6217e4-e5bc-41f3-bea2-80872161de84.jsonl`
- `/ll:refine-issue` - 2026-06-06T04:39:47 - `5f09e7a1-85ba-46b2-a083-2a7cc09d26a3.jsonl`
- `/ll:format-issue` - 2026-06-06T03:28:17 - `6297c89c-86c7-4c08-ae25-157a34cfb566.jsonl`
- `/ll:issue-size-review` - 2026-06-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8be904b6-a889-49bc-bc5f-f854cacc72bb.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8be904b6-a889-49bc-bc5f-f854cacc72bb.jsonl`
