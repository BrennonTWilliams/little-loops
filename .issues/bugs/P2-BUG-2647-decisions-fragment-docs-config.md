---
id: BUG-2647
title: Update docs and config schema for `.ll/decisions.d/` fragment storage
type: BUG
status: done
priority: P2
parent: BUG-2642
discovered_date: '2026-07-15'
completed_at: '2026-07-15T16:00:06Z'
discovered_by: issue-size-review
decision_needed: false
confidence_score: 99
outcome_confidence: 80
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 24
score_change_surface: 18
---

# BUG-2647: Update docs and config schema for `.ll/decisions.d/` fragment storage

## Summary

Decomposed from BUG-2642 (Option A: append-only fragment files). Depends on
BUG-2644 (fragment storage layer). Docs, config schema, and skill/command
bodies that frame `.ll/decisions.yaml` as a single `cat`/`grep`-able file
need updating once storage splits across a legacy file + a fragment
directory; and `decisions.log_path` gains a sibling `.ll/decisions.d/`
directory that may need independent config surfacing.

## Current Behavior

Docs, config-schema prose, and five skill/command bodies still frame
`.ll/decisions.yaml` as a single `cat`/`grep`-able file and describe the old
count-based `ARCHITECTURE-NNN` id scheme. After BUG-2644/2645/2646 landed,
storage is hybrid (legacy flat file + `.ll/decisions.d/*.json` fragments), ids
are UUID4, and a fresh install has only `.ll/decisions.d/` until compaction. The
`[ -f .ll/decisions.yaml ]` presence gates therefore **silently skip governance**
on any never-compacted install.

## Expected Behavior

Documentation, the `.gitignore` comment, `.claude/CLAUDE.md`, `CHANGELOG.md`, and
the affected skill/command bodies describe the as-shipped hybrid storage layout
and UUID4 ids. The presence gates accept a populated `.ll/decisions.d/` (not just
the flat file). Config stays derived (Option A — no schema change).

## Impact

Governance gates can be silently skipped on fresh installs (functional gap,
highest priority), and stale docs mislead users and implementers about storage
layout and id scheme. No hosted CI; validated via `ll-check-links` and
`python -m pytest scripts/tests/test_config_schema.py`.

## Steps to Reproduce

1. On a fresh install where decisions live only in `.ll/decisions.d/*.json`
   (never compacted, so no `.ll/decisions.yaml`), run any skill/command whose
   governance is gated on `[ -f .ll/decisions.yaml ]` (e.g. `/ll:go-no-go`).
2. Observe the decisions governance block is silently skipped.
3. Read `docs/guides/DECISIONS_LOG_GUIDE.md` — observe it still describes a single
   file and `ARCHITECTURE-NNN` ids.

## Parent Issue

Decomposed from BUG-2642: Concurrent `.ll/decisions.yaml` appends collide on
ARCHITECTURE-NNN id and block EPIC merges.

## Depends On

BUG-2644 must land first — docs should describe the shipped storage layout,
not a speculative one.

## Scope

### Documentation
- `docs/guides/DECISIONS_LOG_GUIDE.md` — storage-layout / id-scheme change.
- `docs/development/MERGE-COORDINATOR.md`, `docs/ARCHITECTURE.md`,
  `docs/reference/API.md` — merge path / decisions API changes.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — documents `check-decisions-yaml.sh`;
  update for the fragment-write path (post BUG-2646).
- `docs/reference/CONFIGURATION.md` — documents the `decisions.log_path`
  config key (default `.ll/decisions.yaml`); note the derived/added
  `.ll/decisions.d/` directory.
- `docs/reference/CLI.md`, `docs/reference/COMMANDS.md` — `ll-issues
  decisions` flag surface / storage-file references.
- `CONTRIBUTING.md` — references the decisions.yaml validation / pre-commit
  flow.
- `CHANGELOG.md` — user-facing storage-format change; add a concrete
  `## [X.Y.Z]` section entry (not `[Unreleased]`).
- `.claude/CLAUDE.md` — the `ll-issues` / `ll-verify-decisions` surface notes.
- Skill/command bodies that frame `.ll/decisions.yaml` as a single
  `cat`/`grep`-able file: `skills/decide-issue/SKILL.md`,
  `skills/capture-issue/SKILL.md`, `skills/go-no-go/SKILL.md`,
  `skills/wire-issue/static-coupling-layer.md`, `commands/verify-issues.md`,
  `commands/ready-issue.md` — scan for singular-file framing that breaks
  until fragments are compacted.
- `.gitignore` (~lines 126–130) — the `!/.ll/` un-ignore already tracks a new
  `.ll/decisions.d/` subdir (no new rule strictly needed), but the
  explanatory comment ("`.ll/decisions.yaml` is a curated, committed
  artifact") goes stale once storage splits; update it.

### Configuration
- `scripts/little_loops/config-schema.json` — `decisions` block
  (~lines 568–585) declares only `log_path` + `auto_generate`; add a
  `fragment_dir` (or equivalent) property only if `.ll/decisions.d/` needs
  independent configuration rather than derived from `log_path`'s parent.
- `scripts/little_loops/config/core.py` (`DecisionsConfig` dataclass) +
  `scripts/little_loops/config/features.py` — mirror any new schema key.

## Tests

- `scripts/tests/test_config_schema.py` — update if the `decisions` schema
  block changes.
- `ll-check-links` — run to confirm no broken links introduced by doc edits.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (BUG-2644/2645/2646
have all landed; this issue is the docs/config-schema follow-up):_

### Storage layout is now hybrid (as-shipped)

- Fragment dir is **derived, not configured**: `decisions.py:30`
  `_fragments_dir(log_path)` returns `log_path.with_suffix(".d")`
  (`.ll/decisions.yaml` → `.ll/decisions.d`). There is **no** `fragment_dir`
  config key anywhere — the path always tracks `decisions.log_path`.
- Reads union both tiers: `decisions.py:322` `load_decisions()` returns
  `legacy + _load_fragments(_fragments_dir(resolved))`. `_load_fragments()`
  globs `*.json`, **silently skips** malformed fragments, and sorts by
  `(timestamp, filename)`.
- New entries are fragment-only: `decisions.py` `add_entry()` writes
  `.ll/decisions.d/<uuid4>.json` via `atomic_write_json()` and never touches the
  flat file. **A fresh install therefore has `.ll/decisions.d/` but no
  `.ll/decisions.yaml`** until a compaction runs.
- In-place mutation: `decisions.py:378` `update_entry()` rewrites only the single
  backing file (one fragment, or the flat file); `set_outcome()` and
  `_cmd_promote()` route through it instead of `save_decisions()`.
- Compaction is the only fold-back point: `decisions.py:341` `save_decisions()`
  rewrites the flat file from the full list **and deletes all fragment files**.

### Id scheme changed — docs correction needed (not in original Scope)

The old count-based `ARCHITECTURE-NNN` / `{prefix}-{len+1:03d}` id scheme (the
BUG-2642 root cause) is **gone from the default path**. `cli/issues/decisions.py`
`_cmd_add()` and `_cmd_extract_from_completed()` now mint `str(uuid.uuid4())`
unless an explicit `--entry-id` is supplied. Any doc/skill/comment that describes
decision ids as `ARCHITECTURE-NNN` or a sequential counter is now stale and must
be corrected — this affects `docs/guides/DECISIONS_LOG_GUIDE.md` and the parent
BUG-2642 narrative.

### FUNCTIONAL GAP (higher priority than "stale framing") — presence-gate skip

Five skill/command bodies gate decisions governance on the flat file's existence
with `[ -f .ll/decisions.yaml ]`, which now **silently skips governance** whenever
decisions live only in `.ll/decisions.d/*.json` (i.e. any fresh install that has
never compacted):

- `skills/decide-issue/SKILL.md:420`
- `skills/capture-issue/SKILL.md:309`
- `skills/go-no-go/SKILL.md:406`
- `commands/verify-issues.md:74` (+ prose `:88`, `:208`)
- `commands/ready-issue.md:193` (+ prose `:208`, `:214`)
- `skills/wire-issue/static-coupling-layer.md:7,15,38` — same singular-file framing

Fixing the prose alone is insufficient: the `-f` guard must also accept a
populated `.ll/decisions.d/` (e.g. `[ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]`,
or gate on `ll-issues decisions list` returning entries). Document this in the
issue's implementation, but per refine-issue scope the code edits happen in
`/ll:manage-issue` — this finding records the gap.

### Validation gates already cover the fragment path (BUG-2646, landed)

- `cli/verify_decisions.py` `_run()` adds a **strict** second pass re-globbing
  `_fragments_dir()` and calling `_entry_from_dict()` directly (bypassing the
  swallowing `_load_fragments()`), so a malformed fragment → exit 1.
- `hooks/scripts/check-decisions-yaml.sh` matches both `*/.ll/decisions.yaml` and
  `*/.ll/decisions.d/*.json`.
- `.pre-commit-config.yaml` — `files: ^\.ll/decisions(\.yaml|\.d/.*\.json)$`.

`docs/guides/BUILTIN_HOOKS_GUIDE.md:*` and `docs/reference/CONFIGURATION.md:796-817`
(the ENH-2591/2592 gate prose) describe these as flat-file-only and need the
fragment path added.

### Note on `docs/development/MERGE-COORDINATOR.md`

The file **exists** (23 KB), but currently contains **zero** `.ll/decisions.yaml`
or `.ll/decisions.d` references. Confirm whether it actually needs a
storage-layout edit, or whether its inclusion in Scope is speculative — it may
be a no-op for this issue.

### Config decision point

Whether to surface `.ll/decisions.d/` as an independent config key:

> **Selected:** Option A (keep fragment dir derived) — `_fragments_dir()` is already the single, well-tested source of truth used by all 5 call sites; no demand for independent configurability exists.

**Option A**: Keep it derived. No schema/dataclass change. `_fragments_dir()`
(`decisions.py:30`) remains the single source of truth; the fragment dir always
tracks `decisions.log_path`. Config work reduces to zero; the `decisions` block
(`config-schema.json:568`, `DecisionsConfig` at `config/features.py:505`) is
untouched.

**Option B**: Add a `fragment_dir` property to the `decisions` schema block
(mirror in `DecisionsConfig` + `from_dict`, extend `test_decisions_in_schema`
at `test_config_schema.py:232`) and thread it through `_fragments_dir()`. Adds a
second source of truth alongside the derivation and a new `additionalProperties:
false` surface to maintain.

**Recommended**: Option A — the fragment dir has no use case for diverging from
`log_path`, and Option B introduces a competing source of truth against
`_fragments_dir()`. Scope the config half of this issue to "no schema change
needed; document the derived layout" unless a concrete need for independent
configuration emerges.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-15.

**Selected**: Option A — keep the fragment directory derived; no schema/dataclass change.

**Reasoning**: `_fragments_dir()` (`decisions.py:30`) is the single, load-bearing derivation used by all five read/write/verify call sites (`decisions.py:338,360,374,400`; `cli/verify_decisions.py:70`), and the `Path.with_suffix()` derived-sibling-path idiom is an established repo convention (lock files in `edit_batch_nudge.py`, `pre_compact_handoff.py`, `rate_limit_circuit.py`) — none independently configured. No call site, test, doc, or sibling issue (BUG-2644/2645/2646) anywhere requests a fragment dir that diverges from `log_path`, so Option B would only add a competing source of truth and a new `additionalProperties: false` surface with zero driving use case.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (derived) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (`fragment_dir` key) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: reuse score 3 — docs-only change, reuses `_fragments_dir()` and existing `DecisionsConfig`/schema exactly; `test_decisions_in_schema` needs no edit.
- Option B: reuse score 1 — no "independent secondary path" utility exists to reuse; introduces a new pattern that must be threaded through all 5 call sites (drift risk) plus a new schema key + dataclass field + test assertion, with no concrete divergence use case.

### Reference anchors (for the implementer)

- `config-schema.json:568-592` — `decisions` block (properties: `enabled`,
  `log_path`, `auto_generate`).
- `config/features.py:505-525` — `DecisionsConfig` dataclass + `from_dict`
  (note: the issue lists `config/core.py`, but the dataclass lives in
  `config/features.py`; `core.py:223,292` only imports/mounts it).
- `docs/reference/CONFIGURATION.md:786-794` — `decisions` doc table to update.
- `test_config_schema.py:232-255` — `test_decisions_in_schema()` to extend only
  if Option B is chosen.
- `CHANGELOG.md` latest concrete section `## [1.143.0] - 2026-07-13` — model the
  new `## [X.Y.Z]` entry after this format; a `decisions` precedent bullet
  already exists there (ENH-2592).

## Implementation Steps

1. Decide the config question (Option A vs B above); if Option A, remove the
   `config-schema.json` / `config/*.py` / `test_config_schema.py` items from
   scope.
2. Correct the id-scheme framing (`ARCHITECTURE-NNN` → UUID4) in
   `docs/guides/DECISIONS_LOG_GUIDE.md` and the BUG-2642 narrative.
3. Fix the presence-gate skip in the five skill/command bodies (accept a
   populated `.ll/decisions.d/`, not just the flat file) — the highest-impact
   change.
4. Add the fragment path to the gate prose in
   `docs/guides/BUILTIN_HOOKS_GUIDE.md` and `docs/reference/CONFIGURATION.md`.
5. Update `docs/reference/CLI.md`, `docs/reference/COMMANDS.md`,
   `.claude/CLAUDE.md`, `CONTRIBUTING.md`, `.gitignore` comment (~L126-130), and
   add a concrete `CHANGELOG.md` `## [X.Y.Z]` entry.
6. Drop the non-existent `docs/development/MERGE-COORDINATOR.md` from scope.
7. Run `ll-check-links` and `python -m pytest scripts/tests/test_config_schema.py`.

## Resolution

Resolved 2026-07-15. Config half was Option A (no schema change — `fragment_dir`
stays derived from `log_path` via `_fragments_dir()`), so `config-schema.json`,
`config/features.py`, and `test_config_schema.py` were left untouched.

**Functional gap fixed (highest impact):** the five skill/command presence gates
that skipped decisions governance on never-compacted installs now accept either
tier (`[ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]`):
`skills/capture-issue/SKILL.md`, `skills/decide-issue/SKILL.md`,
`skills/go-no-go/SKILL.md`, `commands/verify-issues.md`, `commands/ready-issue.md`
(prose lines updated too). `skills/wire-issue/static-coupling-layer.md` already
gated on query output, not file presence — only its singular-file framing was
corrected.

**Docs updated** for hybrid storage + UUID4 ids:
`docs/guides/DECISIONS_LOG_GUIDE.md` (new Storage Layout section, id-scheme
correction, config/validation notes), `docs/guides/BUILTIN_HOOKS_GUIDE.md`,
`docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`,
`docs/reference/COMMANDS.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md`,
`.claude/CLAUDE.md`, `CONTRIBUTING.md`, `.gitignore` comment, and a concrete
`CHANGELOG.md ## [1.144.0]` entry. `docs/development/MERGE-COORDINATOR.md` was
dropped from scope (zero decisions references — a no-op). The BUG-2642 narrative
was left as-is: its `ARCHITECTURE-NNN` references accurately describe the
historical root cause of that (completed) bug.

**Verification:** `python -m pytest scripts/tests/` (14981 passed), config-schema
suite (34 passed), `ll-verify-skills`, `ll-verify-decisions`, and `ll-check-links`
(no new broken links in touched files) all pass.

## Status

**Done** | Created: 2026-07-15 | Completed: 2026-07-15 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-07-15T15:43:58 - `f10cd2d9-1231-49cc-9375-ab7d3fec628e.jsonl`
- `/ll:confidence-check` - 2026-07-15T00:00:00 - `ae1a5c61-8602-45e8-a843-f08f9d82a330.jsonl`
- `/ll:decide-issue` - 2026-07-15T15:39:53 - `a83212f6-2135-43d1-b3ec-e246654ddf37.jsonl`
- `/ll:refine-issue` - 2026-07-15T15:36:31 - `1f817573-b8a5-4d4b-9410-5d5c4d1d9c50.jsonl`
- `/ll:issue-size-review` - 2026-07-15T00:00:00 - `1e8c4ff4-aeb1-4a0e-ae31-59bf29c066dd.jsonl`
- `/ll:manage-issue` - 2026-07-15T15:59:21 - `f10cd2d9-1231-49cc-9375-ab7d3fec628e.jsonl`
