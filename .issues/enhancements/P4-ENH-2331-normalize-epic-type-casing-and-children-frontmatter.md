---
id: ENH-2331
title: 'Normalize EPIC schema: type: casing + migrate EPIC-1880 off children: frontmatter'
type: ENH
priority: P4
status: open
captured_at: '2026-06-26T22:37:02Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- FEAT-2332
decision_ref:
- ARCHITECTURE-065
labels:
- captured
- epic
- issue-management
- schema
- normalization
---

# ENH-2331: Normalize EPIC schema (type casing + EPIC-1880 children migration)

## Summary

Two schema inconsistencies surfaced by the 2026-06-26 EPIC audit: the `type:`
field is split across two casings, and exactly one EPIC uses a frontmatter
`children:` array that nobody else uses (and which is itself out of sync).
Normalize both onto a single convention aligned with ARCHITECTURE-065.

## Current Behavior

- **`type:` casing split: 13 `type: epic` / 19 `type: EPIC`.** This works only
  because `compute_epic_progress` uppercases the EPIC ID
  (`scripts/little_loops/issue_progress.py:80`); any case-sensitive consumer
  could break. The `scope-epic` template emits `type: EPIC`.
- **EPIC-1880 is the only EPIC with a frontmatter `children:` array**
  (`.issues/epics/P3-EPIC-1880-slm-fine-tuning-from-session-logs.md`). It is out
  of sync: lists 10, only 6 have `parent: EPIC-1880`. ENH-1943/1944 are
  grandchildren (via `parent: ENH-1941`); ENH-1948/1949 have no `parent:` at
  all, only `relates_to`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The casing split is inert for `compute_epic_progress`, but a latent
  case-sensitive consumer already exists.** `issue_progress.py:80`
  (`epic_id = epic_id.upper()`) uppercases the *caller-supplied EPIC ID string*,
  not the frontmatter `type:` field — `compute_epic_progress` never reads
  `type:` (children resolve via `i.parent == epic_id`, line 87). The real
  exposure is `issue_history/doc_synthesis.py:177`, a strict
  `issue.issue_type != issue_type` filter against the uppercase `--type EPIC`
  CLI flag, where `issue.issue_type` is the value `session_store.py` persisted
  verbatim from frontmatter (`fm.get("type")` at lines 726 / 1009 / 1116). A
  `type: epic` file therefore lands in `.ll/history.db` as `epic` and silently
  fails to match a `--type EPIC` synthesis filter **today** — a live (if
  low-traffic) inconsistency, not purely future debt.
- **`cli/migrate.py:169` is safe** — it does `type_prefix.upper()` before its
  category lookup, so both casings route correctly there.
- **Dropping `children:` is provably safe.** No Python reads a frontmatter
  `children:` array: a `get("children")` sweep across `scripts/little_loops/`
  returns zero issue-parser hits (the lone match in
  `finalize_decomposition.py:57` is an unrelated dict key). `IssueParser.parse_file`
  never reads `children:`; `EpicProgress.children` is built independently from
  `parent:` backrefs.

## Expected Behavior

- EPIC frontmatter uses a single `type:` convention (`type: EPIC`) across all 32
  files, so case-sensitive consumers stay correct without relying on
  `compute_epic_progress` uppercasing the EPIC ID.
- No EPIC carries a frontmatter `children:` array; child membership is derived
  from `parent:` backrefs plus the body `## Children` list per ARCHITECTURE-065,
  and EPIC-1880's listing matches its real children (grandchildren noted as prose).

## Proposed Solution

- **Canonicalize `type: EPIC`** (matches filenames, the `scope-epic` template,
  and the 19/32 majority). One-time normalize the 13 `type: epic` files. Add a
  lint check (fold into FEAT-2332's `epic-consistency` or
  `ll-deps validate`/`validate_frontmatter_fields`).
- **Migrate EPIC-1880 off `children:`.** Drop the frontmatter `children:` array;
  rely on `parent:` backrefs + body `## Children` per ARCHITECTURE-065.
  Resolve the stragglers:
  - ENH-1943/1944: document as grandchildren in prose (they belong to ENH-1941,
    not directly to EPIC-1880).
  - ENH-1948/1949: add `parent: EPIC-1880` if they are true direct children;
    otherwise move them to `relates_to`/prose.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Re-home the durable lint.** `dependency_mapper/analysis.py:491`
  `validate_frontmatter_fields(issues) -> None` is **warning-only** (emits
  `logger.warning()` per `_DEPRECATED_RELATIONSHIP_KEYS`; no return, no exit
  code) **and is invoked by no CLI command** — it is only exported from
  `dependency_mapper/__init__.py`. So "fold into `validate_frontmatter_fields` /
  `ll-deps validate`" cannot satisfy the AC "a lint check **fails**" without also
  returning structured violations and wiring an exit code. Land the guard in
  **FEAT-2332's `epic-consistency`** linter (it already owns the epic fail/fix
  surface); this issue's own deliverable is then the one-time data normalization
  plus the `ISSUE_TEMPLATE.md` doc fix. A stop-gap is a dedicated exit-code
  `ll-verify-*` tool modeled on `cli/verify_design_tokens.py`
  (`ProfileResult.has_violations` → `return 1 if results else 0`).
- **EPIC-1880 stragglers, resolved against current files:** direct
  `parent: EPIC-1880` children today are exactly FEAT-1826, ENH-1827, ENH-1885,
  ENH-1886, ENH-1941, ENH-1942 (6). ENH-1943/1944 carry `parent: ENH-1941`
  (grandchildren → prose). ENH-1948/1949 have neither `parent:` nor a backref to
  EPIC-1880 — confirm intent, then add `parent: EPIC-1880` or move to
  `relates_to:`/prose. The `children:` array is safe to delete outright (no reader).

## Acceptance Criteria

- All 32 EPIC files use `type: EPIC`.
- EPIC-1880 has no frontmatter `children:` field; its body `## Children`
  reflects only its real `parent:` children, with grandchildren documented as
  prose.
- A lint check fails on a non-`EPIC` `type:` value or a reappearing frontmatter
  `children:` array on an EPIC.

## Implementation Steps

1. **Normalize `type:` casing.** Change `type: epic` → `type: EPIC` in the 13
   files listed in the Integration Map (hand-edit, or a one-shot normalizer
   modeled on `cli/migrate_status.py`). Verify:
   `grep -rl '^type: epic$' .issues/epics/*.md` returns nothing.
2. **Migrate EPIC-1880 off `children:`.** Delete the `children:` frontmatter line
   in `.issues/epics/P3-EPIC-1880-…md`; ensure its body `## Children` lists only
   the 6 real `parent:` children, with ENH-1943/1944 noted as grandchildren in
   prose. Resolve ENH-1948/1949 (`parent: EPIC-1880` or `relates_to:`).
3. **Add the regression lint** in FEAT-2332's `epic-consistency` linter: fail on
   (a) a `^type:` value other than `EPIC` on any `.issues/epics/` file, and
   (b) a `^children:` key on any EPIC. If FEAT-2332 has not landed, a stop-gap
   exit-code `ll-verify-*` tool modeled on `cli/verify_design_tokens.py` works.
   Pair with tests per `test_migrate_status.py` /
   `test_dependency_mapper.py::TestValidateFrontmatterFields`.
4. **Fix the doc.** Update `docs/reference/ISSUE_TEMPLATE.md:522` to drop
   `children:` frontmatter as an enumeration option (parent-only per
   ARCHITECTURE-065), so the template stops advertising the field being removed.
5. **Validate.** Run `ll-issues epic-progress EPIC-1880` to confirm child counts
   are unchanged after dropping `children:`, plus the lint's tests.

## Integration Map

- EPIC files under `.issues/epics/` (13 casing fixes + EPIC-1880).
- Lint hook: extend FEAT-2332's `epic-consistency` or
  `dependency_mapper/analysis.py::validate_frontmatter_fields`.
- Optionally a one-shot `ll-migrate-*` style normalizer if doing it by script.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to normalize (13 × `type: epic` → `type: EPIC`)** — verified via
`grep -l '^type: epic$' .issues/epics/*.md`:
`EPIC-1663, EPIC-1978, EPIC-2167, EPIC-2207, EPIC-2279, EPIC-2171, EPIC-1626,
EPIC-2178, EPIC-2257, EPIC-2258, EPIC-1463, EPIC-1622, EPIC-1713`.

**`type:` consumers (read verbatim — only `migrate.py` normalizes on read):**
- `session_store.py:726 / 1009 / 1116` — `fm.get("type")` stored verbatim into
  the history DB (`issue_snapshots` / `issue_events`); persists the split into
  analytics data.
- `issue_history/doc_synthesis.py:177` — strict `issue.issue_type != issue_type`
  (the latent case-sensitive filter; see Current Behavior findings).
- `cli/migrate.py:169` — `type_prefix.upper()`; casing-safe.
- `cli/issues/list_cmd.py` `_find_epic_ancestor()` — compares the filename ID
  prefix (always uppercase), not `type:`.

**Lint surface:** `dependency_mapper/analysis.py:491`
`validate_frontmatter_fields` (constants `_DEPRECATED_RELATIONSHIP_KEYS` :487,
`_FRONTMATTER_RE` :488) is warning-only and unwired to any CLI — see Proposed
Solution findings for why the guard belongs in FEAT-2332 instead.

**Documentation:** `docs/reference/ISSUE_TEMPLATE.md:522` still lists `children:`
frontmatter as a valid enumeration option — update to `parent:`-only.

**Migration template (if scripting):** `cli/migrate_status.py` — pure
`_migrate_content(content) -> tuple[str, list[str]]` + `main_*()` with
`issues_dir.rglob("*.md")`, `add_dry_run_arg` / `add_config_arg`,
`cli_event_context`. Prefer the regex `_set_fields()` approach
(`cli/migrate_relationships.py`) over `frontmatter.update_frontmatter` (which
yaml-roundtrips and reorders fields). Registration is 3 places:
`pyproject.toml [project.scripts]`, plus `cli/__init__.py` import + `__all__` +
docstring line.

**Tests:** model after `scripts/tests/test_migrate_status.py` (pure-function unit
tests on `_migrate_content` + `tmp_path` dry-run-makes-no-change) and
`test_dependency_mapper.py::TestValidateFrontmatterFields` (`caplog.at_level`
assertions).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter()` reads `type:`
  verbatim with **no normalization** (unlike `status:` synonyms at line 118 which
  ARE coerced on read); this is the root path through which `session_store.py`
  picks up lowercase `"epic"` and persists it into `.ll/history.db` [Agent 2]
- `scripts/little_loops/cli/sprint/edit.py` — imports `validate_frontmatter_fields`
  from `dependency_mapper`; relevant if the function gains a structured return type
  + exit-code wiring as part of the stop-gap `ll-verify-*` approach [Agent 1]
- `scripts/little_loops/dependency_mapper/__init__.py` — exports
  `validate_frontmatter_fields` (the entry point any caller would use; must be
  updated if the function signature changes) [Agent 1]

### Files to Modify (Registration — if new CLI tool added)

_Wiring pass added by `/ll:wire-issue`:_

If an `ll-migrate-epic-type` or `ll-verify-epic-schema` tool is introduced, all
four registration points must be updated (the issue currently says "3 places" but
there are four):
- `scripts/pyproject.toml` — `[project.scripts]` entry (lines 51-88) [Agent 1]
- `scripts/little_loops/cli/__init__.py` — `import` + `__all__` + docstring line
  (lines 63-66 / 99-102) [Agent 1]
- `.claude/CLAUDE.md` — "CLI Tools" section listing (4th point omitted from the
  issue's "3 places" count) [Agent 2]
- `docs/reference/CLI.md` — `ll-migrate*` / `ll-verify*` family entries [Agent 1]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` — line 418 explicitly describes `children:` as a valid EPIC
  field (`"An epic file has… a \`children:\` list of member issue IDs"`); must be
  updated in step 4 alongside `docs/reference/ISSUE_TEMPLATE.md:522` [Agent 2]
- `scripts/little_loops/init/writers.py:85` — writes the `## little-loops` stub
  block into a project's `.claude/CLAUDE.md` on `ll-init`; if
  `ll-verify-epic-schema` is intended to be surfaced in the init-generated stubs,
  this file needs updating [Agent 2]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_migrate_relationships.py` — additional migration test
  model using `_set_fields()` pattern; complement to `test_migrate_status.py`
  when writing the new normalizer's tests [Agent 1]
- `scripts/tests/test_migrate_labels.py` — parallel migration test model
  (alternate fixture structure) [Agent 1]
- `scripts/tests/test_issue_progress.py` — covers `compute_epic_progress` with
  parent: backrefs; run as part of step 5 validation to confirm child counts are
  derived from `parent:`, not from the frontmatter `children:` array [Agent 1]
- `scripts/tests/test_ll_issues_sections.py` — parametrized with lowercase
  `["bug", "feat", "enh", "epic"]`; check whether any test fixture creates a file
  with `type: epic` — if so, it will fail the new lint after normalization and
  needs updating [Agent 1]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation:_

6. **Retroactive `.ll/history.db` correction.** `session_store.py` stores
   `fm.get("type")` verbatim (lines 726 / 1009 / 1116); on-disk normalization
   alone leaves any EPIC rows already backfilled into `issue_snapshots` /
   `issue_events` as `"epic"` (lowercase). After step 1, run
   `ll-session backfill` against the normalized files to overwrite the stale rows,
   or apply a targeted SQL `UPDATE ... SET issue_type = 'EPIC' WHERE issue_type =
   'epic'` directly on `.ll/history.db` before verifying analytics queries.
7. **Register new CLI tool at all 4 points (if added).** The issue currently says
   "3 places" but there are four: `scripts/pyproject.toml [project.scripts]`;
   `scripts/little_loops/cli/__init__.py` (import + `__all__` + docstring);
   `.claude/CLAUDE.md` "CLI Tools" section; `docs/reference/CLI.md` under the
   `## Issue Management` family. Optionally also `init/writers.py:85` if the
   verify tool should appear in ll-init–generated project stubs.
8. **Update `test_ll_issues_sections.py` if any fixture writes `type: epic`.**
   The parametrize uses lowercase `["bug", "feat", "enh", "epic"]` as
   *subcommand* arguments (not frontmatter values), so no fixture change is needed
   unless section-template fixtures also embed `type: epic` in their YAML body —
   verify before implementing the lint guard.

## Scope Boundaries

- Body/parent drift reconciliation for other EPICs (FEAT-2332 `--fix`).
- Reader/writer semantics (BUG-2333 / ENH-2330).

## Impact

- **Priority**: P4 - Schema hygiene. The dual-casing currently works because
  `compute_epic_progress` uppercases EPIC IDs
  (`scripts/little_loops/issue_progress.py:80`), so there is no active breakage —
  this is debt cleanup ahead of the next case-sensitive consumer, not a live defect.
- **Effort**: Small - One-time normalize of 13 `type: epic` files plus EPIC-1880's
  frontmatter; the lint guard folds into FEAT-2332's `epic-consistency` /
  `validate_frontmatter_fields` rather than new infrastructure.
- **Risk**: Low - Mechanical frontmatter edits over `.issues/epics/`, guarded by a
  lint check to prevent regression; no runtime code paths change.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-26 | Priority: P4


## Session Log
- `/ll:wire-issue` - 2026-06-26T23:14:28 - `f73d0bf6-c23d-4784-89ac-3dfc12aa0b8a.jsonl`
- `/ll:refine-issue` - 2026-06-26T23:01:53 - `64adeb74-858e-4aba-8e05-0d67aa559f7c.jsonl`
- `/ll:format-issue` - 2026-06-26T22:50:09 - `33bd8519-5b11-4f17-8c2a-08d7788bb9b2.jsonl`
