---
id: FEAT-1287
type: FEAT
priority: P2
status: done
captured_at: '2026-04-25T00:00:00Z'
completed_at: '2026-05-11T22:12:36Z'
discovered_date: '2026-04-25'
discovered_by: issue-size-review
size: Medium
parent: FEAT-1282
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1287: ll:explore-api Skill

## Summary

Implement `skills/explore-api/SKILL.md` — a new skill that guides agents through the full Feathers Learning Test lifecycle (Ingest → Hypothesize → Execute → Refine) for any external system target, then writes a proof record to the `.ll/learning-tests/` registry via `ll-learning-tests`. Also includes the count/table updates to README, CONTRIBUTING, CLAUDE.md, and ARCHITECTURE.md that completing the full feature requires.

## Parent Issue

Decomposed from FEAT-1282: Learning Test Registry and ll:explore-api Skill

## Use Case

A developer is unfamiliar with the Anthropic SDK's streaming API and wants to understand what events are emitted before writing production code. They run `/ll:explore-api "Anthropic SDK streaming"` and the skill: reads existing registry records and SDK docs; generates 5 falsifiable claims about event structure; runs a minimal proof script; and persists a `LearnTestRecord` to `.ll/learning-tests/anthropic-sdk-streaming.md` showing which claims passed or failed — all without the developer writing a single test script by hand.

## Current Behavior

N/A — This skill does not yet exist. There is no guided workflow for exploring external API behavior and persisting proof records to the Learning Test Registry.

## Expected Behavior

Invoking `/ll:explore-api "<target>"` guides the agent through four phases (Ingest → Hypothesize → Execute → Refine), produces a `.ll/learning-tests/<slug>.md` `LearnTestRecord`, and reports proven/refuted/untested claims back to the conversation.

## Motivation

- Without this skill, agents must manually piece together docs, write ad-hoc proof scripts, and discard results — repeating the same exploration on every related task.
- The Learning Test Registry (FEAT-1285/1286) provides the storage layer but has no guided skill to populate it; this skill closes that gap.
- Enables future agents to skip Phase 1 (Ingest) by querying existing records via `ll-learning-tests check`, compounding knowledge over time.

## Proposed Solution

### Skill invocation

```
/ll:explore-api "Anthropic SDK streaming"
/ll:explore-api "Claude API tool use" --assume "tools is a list" --assume "stop_reason is tool_use"
```

### Four-phase lifecycle

**Phase 1 — Ingest**: Read relevant docs, existing code samples, and any prior registry records for the target (via `ll-learning-tests check "<target>"`). Summarize what is already known.

**Phase 2 — Hypothesize**: Generate 3-7 specific, falsifiable claims about the target's behavior. Each claim should be testable with a minimal script. Example: _"streaming events are dicts with a `type` key"_.

**Phase 3 — Execute**: Scaffold a minimal runnable proof script (Python or TypeScript depending on target). Run it via `Bash` capturing stdout/stderr. Save raw output to `.ll/learning-tests/raw/<slug>.txt`.

**Phase 4 — Refine**: Diff expected vs actual. Update claim pass/fail results. Persist a `LearnTestRecord` to `.ll/learning-tests/<slug>.md` via the `Write` tool (CLI has no `write` subcommand — see Codebase Research Findings). Report proven/refuted/untested claims back to the conversation.

### Skill structure

Follow `skills/manage-issue/SKILL.md` as the canonical multi-phase skill template:
- Frontmatter: `description`, `argument-hint`, `allowed-tools`, `arguments`
- Numbered `## Phase N:` sections
- `{{config.*}}` interpolation where needed
- Use `Bash(ll-learning-tests:*)` permission for registry reads (check/list)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis of FEAT-1285/1286 (both completed):_

**CLI subcommand reality** — `ll-learning-tests` (defined at `scripts/little_loops/cli/learning_tests.py`) exposes only three subcommands:
- `check "<target>"` — `cmd_check()`: prints record as JSON on exit 0, exit 1 with stderr error if missing
- `list` — `cmd_list()`: prints JSON array of all records (always exit 0)
- `mark-stale "<target>"` — `cmd_mark_stale()`: patches `status: stale`, no stdout

There is **no `write`/`add` subcommand**. To persist a new record the skill must use the `Write` tool to emit a YAML-frontmatter markdown file directly (matching the format produced by `write_record()` in `scripts/little_loops/learning_tests.py`).

**`LearnTestRecord` schema** (at `scripts/little_loops/learning_tests.py`, `LearnTestRecord` dataclass):
- `target: str` — human-readable name (required)
- `date: str` — ISO date (required), e.g. `"2026-04-25"`
- `status: Literal["proven", "refuted", "stale"]` — defaults to `"proven"`
- `assertions: list[Assertion]` — each `Assertion` is `{claim: str, result: Literal["pass", "fail", "untested"]}`
- `raw_output_path: str | None` — optional pointer to raw stdout file

**Slug derivation** — filename is `slugify(target) + ".md"` via `little_loops.issue_parser.slugify()`. Example: `"Anthropic SDK streaming"` → `anthropic-sdk-streaming.md`. Skill should preview the resolved slug before writing.

**Raw output subdirectory** — `write_record()` does **not** auto-create `.ll/learning-tests/raw/`. The skill must `mkdir -p` the directory before writing raw output, and set `raw_output_path` as a string pointer in the record.

**On-disk format** (verbatim shape produced by `write_record()`):
```yaml
---
target: Anthropic SDK streaming
date: '2026-04-25'
status: proven
assertions:
- claim: streaming events are dicts with a `type` key
  result: pass
raw_output_path: .ll/learning-tests/raw/anthropic-sdk-streaming.txt
---
```
File body is empty — frontmatter fences only.

### Documentation touchpoints (included here as these are the last deliverable)

- `README.md` — increment skill count (`"28 skills"` → `"29 skills"`) in the "What's included" bullet only. Do NOT add a skill table row or a `### ll-learning-tests` CLI section — README is now a hero page; CLI docs go in `docs/reference/CLI.md` and skill tables are removed from README. CLI count increment is owned by FEAT-1286. [wiring note updated 2026-05-10 after README rewrite]
- `CONTRIBUTING.md` — increment skill count (line 125); add `├── explore-api/` to skills tree and `├── learning_tests.py` to module tree
- `.claude/CLAUDE.md` — increment skill count (line 38); add `ll-learning-tests` to CLI tools list. Note: `skills/init/SKILL.md` allow-list and `skills/configure/areas.md` count increment are **owned by FEAT-1286** — do not touch those files here.
- `docs/ARCHITECTURE.md` — add learning test registry section describing the lifecycle and registry format

## API/Interface

```
/ll:explore-api "<target>"
/ll:explore-api "<target>" --assume "<claim>"   # can repeat for multiple pre-seeded claims
```

- `target`: Free-text description of the system/API to explore (e.g., `"Anthropic SDK streaming"`)
- `--assume "<claim>"`: Pre-seed a claim as assumed-true without executing a proof script

Output: `.ll/learning-tests/<slug>.md` in `LearnTestRecord` format (FEAT-1285 schema); raw output at `.ll/learning-tests/raw/<slug>.txt`

## Integration Map

### Files to Modify
- `skills/explore-api/SKILL.md` — create (new skill); follow `skills/manage-issue/SKILL.md` (5+ phases) or `skills/wire-issue/SKILL.md` (10-phase template with `--auto`/`--dry-run` modes) as the structural template
- `README.md` — skill count only (28 → 29 in the "What's included" bullet); CLI count owned by FEAT-1286
- `CONTRIBUTING.md:122` — skill count (28 → 29 skill definitions); `CONTRIBUTING.md:148` — insert `├── explore-api/` in skills tree alphabetically (between `decide-issue/` and `format-issue/`); `learning_tests.py` line at `CONTRIBUTING.md:207` is already present
- `.claude/CLAUDE.md:38` — skill count (28 → 29); `.claude/CLAUDE.md:125` — add `ll-learning-tests` to CLI tools list
- `docs/ARCHITECTURE.md` — add learning test registry section (lifecycle, schema, storage)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/learning_tests.py` — `cmd_check()`, `cmd_list()`, `cmd_mark_stale()`, `main_learning_tests()`: skill invokes via `Bash(ll-learning-tests:*)` for Phase 1 (Ingest) registry lookups
- `scripts/little_loops/learning_tests.py` — `Assertion`, `LearnTestRecord` dataclasses; `write_record()`, `read_record()`, `list_records()`, `check_learning_test()`, `mark_stale()` (skill emits on-disk format directly via Write tool — does not call write_record from skill body)
- `scripts/little_loops/issue_parser.py` — `slugify()` is the slug source of truth; skill must compute the slug to know the output filename
- `scripts/pyproject.toml:72` — entry point registration for `ll-learning-tests` (already in place)
- `scripts/little_loops/cli/__init__.py:37,67` — `main_learning_tests` import/export (already in place)

### Similar Patterns
- `skills/manage-issue/SKILL.md` — canonical multi-phase skill template; frontmatter shape, phase gates, `{{config.*}}` interpolation
- `skills/wire-issue/SKILL.md` — multi-phase skill with `--auto`/`--dry-run` mode handling; cleanest argument-parsing pseudocode to adopt
- `skills/audit-loop-run/SKILL.md` and `skills/debug-loop-run/SKILL.md` — most populated frontmatter examples (`disable-model-invocation`, `model`, full `allowed-tools` list)
- `skills/create-eval-from-issues/SKILL.md` — closest on-disk-artifact pattern: scaffolds a YAML file to a registry-style directory, then validates via a `ll-*` CLI; pattern of `mkdir -p` + slug-derived filename + Write
- `skills/capture-issue/SKILL.md` — pattern for writing a markdown file with YAML frontmatter via Write tool

### Allowed-Tools Block (template)
```yaml
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash(ll-learning-tests:*, mkdir:*, python:*, node:*)
```
Comma-separating multiple commands inside one `Bash(...)` entry is the convention used in `skills/audit-loop-run/SKILL.md:6-7` and `skills/create-eval-from-issues/SKILL.md:5-6`.

### Tests
- Manual: run `/ll:explore-api "Python pathlib"` and verify `.ll/learning-tests/python-pathlib.md` is created with at least one `pass` or `fail` assertion
- Smoke: confirm `ll-learning-tests check "Python pathlib"` returns exit 0 and parseable JSON after the skill writes a record
- Existing test patterns to reference: `scripts/tests/test_learning_tests.py` (FEAT-1285 tests; verifies `slugify` outputs and frontmatter round-trip)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_learning_tests.py` — existing coverage; `TestDocWiring` class asserts `ll-learning-tests` appears in `commands/help.md` and `docs/reference/CLI.md`; won't break but not previously listed
- `scripts/tests/test_feat1287_doc_wiring.py` — **new test file to write** following `scripts/tests/test_feat1407_doc_wiring.py` pattern; assert `skills/explore-api/SKILL.md` exists and contains required section headers (Phase 1–4, `ll-learning-tests`); assert `README.md` contains `"29 skills"`; assert `CONTRIBUTING.md` contains `"explore-api/"`; assert `.claude/CLAUDE.md` updated count phrase; assert `docs/ARCHITECTURE.md` contains learning-tests section

### Documentation
- All doc files listed in "Files to Modify" are in scope per issue
- `docs/ARCHITECTURE.md` section should document: registry directory layout, slug derivation, four-phase lifecycle diagram, CLI surface (3 subcommands), and that `write` is intentionally not exposed (skills/agents own record creation)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — `## Quick Reference Table` (line 277) and command reference block have no `explore-api` entry; skill listing must be added manually here by FEAT-1287 (note: FEAT-1286 owns the CLI-surface `ll-learning-tests` sections of this file — add only the `/ll:explore-api` skill row, not CLI tool entries)

### Configuration
- N/A — no config schema changes needed
- Skill body should reference `{{config.issues.base_dir}}` only if listing related issues; otherwise no `{{config.*}}` interpolation required (registry path `.ll/learning-tests/` is fixed by the registry module, not configurable)

## Implementation Steps

1. Create `skills/explore-api/` directory and author `SKILL.md` frontmatter (description starting "Use when...", `argument-hint: "<target> [--assume <claim>]..."`, `allowed-tools` per Integration Map template, `arguments` block per `skills/wire-issue/SKILL.md:14-30` pattern)
2. Write argument-parsing pseudocode block (model after `skills/wire-issue/SKILL.md` Phase 1 — token walk extracting positional `target` and repeatable `--assume` flag into an array; no equivalent of repeatable-flag-collection exists yet, so document the convention here)
3. Author Phase 1 (Ingest): call `ll-learning-tests check "<target>"` via Bash; on exit 0 parse JSON and short-circuit with the prior record; on exit 1 proceed to hypothesize
4. Author Phase 2 (Hypothesize): generate 3-7 claims; pre-seed any `--assume` claims as `result: untested` initially
5. Author Phase 3 (Execute): scaffold proof script to a temp location (NOT `.ll/learning-tests/raw/` yet — keeps registry clean if the script fails); run via Bash capturing stdout+stderr; on success `mkdir -p .ll/learning-tests/raw/` and move raw output to `.ll/learning-tests/raw/<slug>.txt`
6. Author Phase 4 (Refine): compute slug via the same algorithm as `little_loops.issue_parser.slugify()` (lowercase, strip non-word chars, collapse hyphens) and emit `.ll/learning-tests/<slug>.md` using Write tool with the exact YAML frontmatter shape shown in "Codebase Research Findings" above; status = `proven` if any assertion passed, else `refuted`
7. Manually test: run `/ll:explore-api "Python pathlib"`; verify `.ll/learning-tests/python-pathlib.md` exists; verify `ll-learning-tests check "Python pathlib"` returns the record as JSON
8. Update README (line containing "28 skills" → "29 skills"), CONTRIBUTING.md (line 122 count, line 148 skills-tree insertion), `.claude/CLAUDE.md` (line 38 count, line 125 CLI list entry)
9. Add learning test registry section to `docs/ARCHITECTURE.md` covering lifecycle, schema, storage, and CLI surface
10. Run `python -m pytest scripts/tests/test_learning_tests.py -v` to confirm no registry regressions from any peripheral changes

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Add `/ll:explore-api` skill entry to `commands/help.md` — insert into `## Quick Reference Table` (line 277) and the command reference block; add only the skill row (FEAT-1286 owns the CLI-tool `ll-learning-tests` entries in this file)
12. Create `scripts/tests/test_feat1287_doc_wiring.py` — follow the `test_feat1407_doc_wiring.py` / `test_cli_learning_tests.TestDocWiring` pattern; assert SKILL.md key headers present, count strings updated in README/CONTRIBUTING/CLAUDE.md, and `docs/ARCHITECTURE.md` contains learning-tests section

## Acceptance Criteria

- `/ll:explore-api "Python pathlib"` (or any real target) produces a `.ll/learning-tests/<slug>.md` with at least one `pass` or `fail` assertion
- The skill queries existing registry records before hypothesizing (avoids redundant proofs)
- Counts in README and CONTRIBUTING are accurate after update
- `docs/ARCHITECTURE.md` has a learning test registry section

## Dependencies

- FEAT-1285 (learning_tests module) must be complete
- FEAT-1286 (CLI tool) must be installable — the skill invokes it via `Bash`

## Impact

- **Priority**: P2 — Completes the Learning Test lifecycle: registry (FEAT-1285) and CLI (FEAT-1286) exist but are unusable without a guided skill entrypoint.
- **Effort**: Medium — New skill file plus doc updates across 4 files; no new Python code needed.
- **Risk**: Low — New isolated skill; no changes to existing behavior or public APIs.
- **Breaking Change**: No

## Labels

`feat`, `skill`, `learning-tests`, `learning-testing`, `captured`

---

**Done** | Created: 2026-04-25 | Completed: 2026-05-11 | Priority: P2

## Resolution

Implemented by `/ll:manage-issue` on 2026-05-11.

**Files changed:**
- `skills/explore-api/SKILL.md` — new four-phase skill (Ingest → Hypothesize → Execute → Refine) with `--assume` repeatable-flag parsing, slug derivation matching `little_loops.issue_parser.slugify`, and direct `Write` of `LearnTestRecord` YAML.
- `README.md` — `28 skills` → `29 skills` in the "What's included" bullet.
- `CONTRIBUTING.md` — `28 skill definitions` → `29 skill definitions`; inserted `├── explore-api/` in the skills tree alphabetically between `decide-issue/` and `go-no-go/`.
- `.claude/CLAUDE.md` — `(28 skills)` → `(29 skills)`; added `ll-learning-tests` to the CLI tools list noting that record creation is owned by `/ll:explore-api`.
- `docs/ARCHITECTURE.md` — added `## Learning Test Registry` section (lifecycle mermaid, `LearnTestRecord` schema table, storage layout, CLI surface explainer); also updated the High-Level Architecture mermaid (`28 composable skills` → `29`) and directory-structure tree (`28 skill definitions` → `29`).
- `commands/help.md` — added `/ll:explore-api "<target>"` entry under SCANNING & ANALYSIS, plus the `explore-api` entry in the Quick Reference Table.
- `scripts/tests/test_feat1287_doc_wiring.py` — new doc-wiring regression tests (36 assertions across 6 test classes; all pass).

**Verification:** `python -m pytest scripts/tests/test_feat1287_doc_wiring.py scripts/tests/test_learning_tests.py -v` → 36 passed. Full suite passes except 7 pre-existing failures in `test_generate_schemas.py` and `test_update_skill.py` (unrelated to this issue). `ruff check scripts/` → clean.

**Scope-boundary respected:** Did not touch `commands/help.md` CLI-tool entries (owned by FEAT-1286), `docs/reference/CLI.md` (owned by FEAT-1286), `skills/init/SKILL.md`, or `skills/configure/areas.md` (owned by FEAT-1286).

**Known cosmetic:** `ll-verify-docs` reports a false positive at `CONTRIBUTING.md:521` because the doc_counts regex matches "0 skill descriptions dropped"; this pre-dates FEAT-1287 and is a doc_counts.py issue, not a content issue.

Closes FEAT-1287

## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- No `skills/explore-api/` directory ✓
- No `skills/explore-api/SKILL.md` ✓
- Feature not yet implemented ✓

## Session Log
- `/ll:manage-issue` - 2026-05-11T22:12:36Z - `692f5e04-dfe2-4a5c-91ed-d3238a84db6e.jsonl`
- `/ll:ready-issue` - 2026-05-11T22:04:02 - `e482f432-46d0-4b91-a742-72fb3143034c.jsonl`
- `/ll:confidence-check` - 2026-05-11T22:00:00 - `589c0299-e4b4-41b5-824c-35261e2d556d.jsonl`
- `/ll:wire-issue` - 2026-05-11T21:59:46 - `cc33feb4-8058-4666-850c-46bdc4c5cf79.jsonl`
- `/ll:refine-issue` - 2026-05-11T21:52:35 - `c040503b-8c26-457b-8005-3919a14f60e7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T00:00:00 - `cf03929d-b936-46f6-9fc6-0edf5cab2290.jsonl`
- `/ll:format-issue` - 2026-04-25T20:14:31 - `9e97fb3c-4c81-4d9a-b8ce-a2bcf181afa8.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): **Narrative doc ownership split with FEAT-1286.** FEAT-1287 owns: README skill count, CONTRIBUTING skills tree, `.claude/CLAUDE.md`, and `docs/ARCHITECTURE.md`. FEAT-1286 owns CLI-surface docs (`commands/help.md`, `docs/reference/CLI.md`). The CLI count increment is owned by FEAT-1286 — do not increment CLI count in this issue. Apply this issue's doc changes after FEAT-1286 has landed.

**Note** (added 2026-05-11): **Wiring file ownership resolved.** `skills/init/SKILL.md` (allow-list + CLAUDE.md boilerplate blocks) and `skills/configure/areas.md` (count increment + tool enumeration) are owned by FEAT-1286. FEAT-1287 owns `.claude/CLAUDE.md` (skill count + CLI tools list), `CONTRIBUTING.md`, `README.md` (skill count only), and `docs/ARCHITECTURE.md`.
