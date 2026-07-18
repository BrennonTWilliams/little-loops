---
id: FEAT-2681
title: "F1-prereq (c.2) \u2014 Learning test: anthropic SDK/API accepts cache_control\
  \ on a tool-definition block"
type: FEAT
priority: P2
status: done
parent: EPIC-2456
relates_to:
- FEAT-2673
- FEAT-2680
- FEAT-2679
learning_tests_required:
- anthropic
decision_needed: false
spike_needed: false
confidence_score: 99
outcome_confidence: 86
score_complexity: 23
score_test_coverage: 18
score_ambiguity: 23
score_change_surface: 22
completed_at: '2026-07-18T20:50:43Z'
---

# FEAT-2681: F1-prereq (c.2) — Learning test: anthropic SDK/API accepts cache_control on a tool-definition block

## Summary

Add a learning-test claim proving the `anthropic` Python SDK's `tools=[...]`
Messages API param accepts a `cache_control` key per tool-definition block
and that the API honors it. This extends the existing
`learning_tests_required: [anthropic]` proof set, which currently only
covers basic SDK-client claims, with a claim specific to tool-block caching.

## Parent Issue

Decomposed from FEAT-2679: F1-prereq (c) — Tool-definition JSON schema
catalog for the Anthropic Messages API. Covers Implementation Step 3 from
the parent (learning-test claim for `cache_control` on tool blocks).

This claim does not depend on FEAT-2680's catalog-assembly function — it
proves the wire-format/SDK behavior independently, against a hand-built
tool-definition block, so it can be worked in parallel with FEAT-2680.

## Current Behavior

The `.ll/learning-tests/anthropic.md` record is `status: proven`, but its
6 assertions only cover client construction, the exception hierarchy, and
`__version__` — none touch `cache_control` on a tool-definition block. Any
issue gating on `learning_tests_required: [anthropic]` (including this one
and FEAT-2673) currently passes the gate without that claim being proven.

## Expected Behavior

The Learning Test Registry's `anthropic` record includes falsifiable
assertions proving the `anthropic` SDK's `tools=[...]` param accepts a
`cache_control` key on an individual tool-definition dict, and that
building the request payload with it does not raise/reject client-side.
Downstream issues (e.g. FEAT-2673) can then cite this proof instead of an
unverified assumption.

## Use Case

As the implementer of FEAT-2673's `cache_control: ephemeral` marking
logic, I want proof that the Anthropic SDK/API accepts `cache_control` on
tool-definition blocks so I don't ship untested caching behavior on that
block type.

## Impact

Blocks FEAT-2673's confidence in marking tool blocks with
`cache_control: ephemeral`. Low complexity and isolated to the Learning
Test Registry (`.ll/learning-tests/anthropic.md` + raw output) — no
production code changes.

## Motivation

FEAT-2673 ("cache_control: ephemeral integration") specifies that
`build_anthropic_request()` marks `cache_control: ephemeral` on "system,
tool, and stable-skill blocks." Whether the `anthropic` SDK/API actually
accepts and honors that key on a *tool*-definition block (as opposed to
system/message content blocks, which are already proven elsewhere) is an
unverified claim blocking FEAT-2673's confidence.

## Proposed Solution

Follow the existing Learning Test Registry pattern (`/ll:explore-api`,
`ll-learning-tests prove <target>`) to record proof that:

1. The `anthropic` SDK's `tools` param accepts a `cache_control` key inside
   an individual tool-definition dict (alongside `name`, `description`,
   `input_schema`).
2. The API does not reject the request when `cache_control: {"type":
   "ephemeral"}` is set on a tool block.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The existing `anthropic` target record (`.ll/learning-tests/anthropic.md`)
  is already `status: proven`, but its 6 assertions only cover client
  construction, exception hierarchy, and `__version__` — **none touch
  `cache_control`**. Because `ll-learning-tests check anthropic` exits 0
  today, any issue gating on `learning_tests_required: [anthropic]`
  (including this one and FEAT-2673) currently passes the gate without the
  cache_control claim actually being proven. This issue must **append**
  new assertions to the existing record via `/ll:explore-api`, not treat a
  passing gate check as already covering the claim.
- No file anywhere in the repo (registry, tests, or `thoughts/` planning
  docs) currently exercises `cache_control` against the live Anthropic
  API/SDK on any block type. FEAT-2673's Motivation section's claim that
  message/system-block `cache_control` is "already proven elsewhere" is
  not backed by an existing `.ll/learning-tests/*.md` record — this issue
  is the first actual proof for `cache_control`, not just an extension for
  the tool-block case specifically.
- `/ll:explore-api` (`skills/explore-api/SKILL.md`) is a 4-phase workflow
  (Ingest → Hypothesize → Execute → Refine) with **no CLI `write`
  subcommand by design** — records are only written by the skill/agent via
  the `Write` tool so prompt context captures proof reasoning, not just
  the pass/fail result. Since `anthropic` already has a record, Phase 1
  (Ingest) will detect it and this issue's new claims must be merged in
  (old 6 assertions preserved + new cache_control assertions appended),
  not overwritten.
- Precedent for the raw-proof-output format: `.ll/learning-tests/raw/anthropic.txt`
  has one `[PASS]`/`[FAIL] claim N: ...` line per assertion plus a
  `SUMMARY: N/M passed, K failed` footer — the new script should follow
  this exact format.
- Precedent for the "can't exercise live API in this sandbox" pattern:
  existing claim 6 in `anthropic.md` records `result: untested` (not
  skipped) for `live messages.create() calls without an API key cannot be
  exercised in this environment (acknowledged constraint, not a runtime
  claim)`. If this environment also lacks an API key, the new claim should
  follow the same pattern — prove SDK-side acceptance (no `TypeError`/
  validation error when constructing the request payload with
  `cache_control` on a tool dict) and record `untested` for the live
  round-trip/cache-hit behavior, rather than blocking on API access.
- The exact tool-definition-block shape to hand-build the proof against is
  `ToolDefinition`/`to_anthropic_tools()` in
  `scripts/little_loops/tool_catalog.py:27,157` — `{"name", "description",
  "input_schema", "cache_control"}` with `cache_control` set to
  `{"type": "ephemeral"}` only when present (never emitted as a literal
  `null` key — see `scripts/tests/test_tool_catalog.py:179`
  `test_serializes_required_keys_only_when_no_cache_control`). The proof
  script should mirror this shape rather than inventing a new one.

## Acceptance Criteria

- [x] Learning test proves the `anthropic` SDK/API accepts `cache_control`
      on a tool-definition block, recorded in the Learning Test Registry.
- [x] FEAT-2673 can cite this proof as its basis for marking tool blocks
      `cache_control: ephemeral` without further investigation.

## Integration Map

### Files to Modify
- `.ll/learning-tests/anthropic.md` — append new `cache_control`-on-tool-block
  assertions to the existing 6-assertion list (do not overwrite; status stays
  `proven` if the new assertions pass)
- `.ll/learning-tests/raw/anthropic.txt` — append/replace raw proof output
  for the new assertions, following the existing `[PASS]`/`[FAIL] claim N:
  ...` + `SUMMARY: N/M passed, K failed` format

### Reference Implementation (proof-script shape to mirror)
- `scripts/little_loops/tool_catalog.py:27` — `ToolDefinition` dataclass
  (`name`, `description`, `input_schema`, `cache_control: dict[str, str] |
  None`)
- `scripts/little_loops/tool_catalog.py:157` — `to_anthropic_tools()`,
  the conditional-emit logic the proof script's hand-built tool dict should
  match (never emit `cache_control` as a literal `null`)

### Workflow / CLI Entry Points
- `skills/explore-api/SKILL.md` — 4-phase workflow (Ingest → Hypothesize →
  Execute → Refine) this issue must follow to record the claim
- `scripts/little_loops/cli/learning_tests.py` — `cmd_check()`, `cmd_prove()`
  (`ll-learning-tests check|prove anthropic`)
- `scripts/little_loops/learning_tests/__init__.py` — `LearnTestRecord`,
  `Assertion`, `write_record()`, `read_record()` — the on-disk record shape
  Phase 4 (Refine) writes

### Consumers (who cites this proof)
- `.issues/features/P2-FEAT-2673-f1-cache-control-ephemeral-integration-and-cache-marking-cost-oracle.md`
  — Motivation section currently asserts tool-block `cache_control`
  acceptance is unverified; this issue's proof unblocks that claim. Note:
  FEAT-2673 does not currently list `learning_tests_required: [anthropic]`
  in its own frontmatter, so citation today is prose-only
  (`relates_to`/`depends_on`), not gate-enforced.

### Tests
- `scripts/tests/test_tool_catalog.py:179,195` — existing unit tests for
  `to_anthropic_tools()` cache_control serialization (local/offline only;
  do not duplicate — this issue's proof is the missing live/SDK-acceptance
  layer those tests can't cover)
- `scripts/tests/test_learning_tests.py`, `scripts/tests/test_cli_learning_tests.py`
  — registry/CLI test coverage; no changes expected, listed for awareness
  only

## Implementation Steps

1. Run `ll-learning-tests check --stale-aware anthropic` to confirm current
   record state before starting (baseline: 5 pass / 1 untested, no
   cache_control claims).
2. Invoke `/ll:explore-api anthropic` (or equivalent Phase 2 hypothesis
   step) to add 2 falsifiable claims matching the Acceptance Criteria:
   the SDK accepts `cache_control` in a `tools=[...]` dict, and building
   the request payload with it does not raise/reject client-side.
3. Scaffold the proof script to a `mktemp -d` temp path (per
   `skills/explore-api/SKILL.md` Phase 3), constructing a tool-definition
   dict shaped like `to_anthropic_tools()`'s output
   (`scripts/little_loops/tool_catalog.py:157`) with
   `cache_control: {"type": "ephemeral"}` set.
4. Run the script, capture stdout+stderr, `mv` into
   `.ll/learning-tests/raw/anthropic.txt` — merge with (not replace) the
   existing 5 pass / 1 untested claims already in that file.
   **Wiring note (`/ll:wire-issue`):** `raw/anthropic.txt` already ends
   with a stale `SUMMARY: 5/5 passed, 0 failed` footer covering only the
   5 `[PASS]`-lined claims (claim 6, `untested`, has no raw-output line at
   all — a pre-existing mismatch, not introduced by this issue). Appending
   the new claims' output after that footer would leave two conflicting
   `SUMMARY:` lines in the file. Replace the stale footer with one
   reconciled `SUMMARY: N/M passed, K failed` line that accounts for all
   6 original + new claims (counting `untested` as neither passed nor
   failed), rather than blindly appending after it.
5. Write the updated `LearnTestRecord` via `Write` (Phase 4), preserving
   all 6 existing assertions and appending the new ones; verify with
   `ll-learning-tests check anthropic` (expect exit 0, `status: proven`).
6. Update FEAT-2681's `learning_tests_required` gate check —
   `ll-learning-tests check --stale-aware anthropic` should now reflect a
   record whose assertions include the cache_control claims, not just the
   original 6.

## Resolution

Appended 3 new assertions to the existing `anthropic` Learning Test Registry
record (`.ll/learning-tests/anthropic.md`), proving that the `anthropic` SDK's
`tools=[...]` param accepts a `cache_control` key on an individual
tool-definition block (mirroring `to_anthropic_tools()`'s emit shape in
`scripts/little_loops/tool_catalog.py:157`), and that building request
kwargs with that block does not raise client-side. No `ANTHROPIC_API_KEY`
is available in this environment, so the live round-trip is recorded
`untested`, following the existing claim-6 precedent. All 6 prior
assertions were preserved unmodified; `ll-learning-tests check anthropic`
now returns `status: proven` with 9 total assertions (7 pass, 2 untested,
0 failed). `.ll/learning-tests/raw/anthropic.txt`'s stale `SUMMARY: 5/5
passed, 0 failed` footer was replaced with a reconciled `SUMMARY: 7/9
passed, 0 failed, 2 untested` line.

## Status

**Done** | Created: 2026-07-18 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-07-18T20:40:32 - `41be1c74-3982-4825-be41-c51a8ef7a667.jsonl`
- `/ll:confidence-check` - 2026-07-18T00:00:00Z - `c82f0499-9715-4c79-ba2f-ebfe76e65b30.jsonl`
- `/ll:wire-issue` - 2026-07-18T20:37:02 - `8b16d86b-1699-4f83-8bd3-ca454cb57bdd.jsonl`
- `/ll:refine-issue` - 2026-07-18T20:32:06 - `5358f7fd-22a7-4dcf-b038-85c6c3c8b19a.jsonl`
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `478e94ef-30f6-4532-a6ed-1ba334c74117.jsonl`
- `/ll:manage-issue` - 2026-07-18T20:50:01Z - `000ba01e-76b0-4308-a39e-fdaf76f9715c.jsonl`
