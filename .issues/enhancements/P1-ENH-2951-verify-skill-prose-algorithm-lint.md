---
id: ENH-2951
title: 'll-verify-skill-prose: lint gate that fails on algorithm-as-prose in skill/command
  markdown'
type: ENH
priority: P1
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-01T08:25:12Z'
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- skills
- determinism
- gate
relates_to:
- ENH-2939
- ENH-2941
confidence_score: 98
outcome_confidence: 88
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
---

# ENH-2951: `ll-verify-skill-prose` — enforce EPIC-2938's core invariant

## Summary

EPIC-2938's first success criterion — "no skill/command markdown contains a prose
reimplementation of an algorithm that exists in `scripts/little_loops/`" — has no
enforcement mechanism. Every other invariant in this repo has an `ll-verify-*` gate
(`ll-verify-skills`, `ll-verify-decisions`, `ll-verify-cli-allowlist`, …). Without one,
the epic's deletions regress silently.

## Current Behavior

Nothing checks for algorithm-as-prose. The regression is not hypothetical: commit
`5e29c4d4` (ENH-2936) added Pattern E option-detection prose to
`skills/decide-issue/SKILL.md` **three commits after** EPIC-2938 was scoped to delete
exactly that class of content, and simultaneously duplicated it into
`issue_parser.py:449`. `ll-verify-skills` only enforces the 500-line cap, which such
prose can satisfy while still being a duplicated algorithm.

## Expected Behavior

`ll-verify-skill-prose [--json]` scans `skills/*/SKILL.md` + `commands/*.md` and exits 1
on any of a curated marker set, each mapped to the CLI that owns the logic:

| Marker | Owner |
|---|---|
| Jaccard/overlap formula (`intersection / union`, `∩`/`∪` over word sets) | `text_utils.calculate_word_overlap` |
| an inline stop-word list | `text_utils.extract_words` |
| scanning `~/.claude/projects/` for session JSONL | `ll-issues append-log` |
| inline `python3 -c` computation the model is told to run | the owning CLI |
| `git mv` loops over globbed issue filenames | `ll-issues normalize` |
| union-find / cluster-merge instructions | `ll-issues link-epics` |

Findings report `file:line`, the matched marker, and the owning CLI. An
`<!-- ll-prose-ok: reason -->` comment on the preceding line suppresses a checked-in
false positive.

## Proposed Solution

Marker table as module data (regex + owner + rationale), mirroring `fsm/validation.py`'s
MR-rule table shape. Resolve the skill/command dirs via
`skill_expander._find_plugin_root` (the shared helper, per FEAT-2940's registration note)
rather than a `__file__` walk. Register as a pytest test in `scripts/tests/` — the only
CI — and add it to `ll-doctor --full`'s aggregate.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`fsm/validation.py` no longer exists as a flat file** — ENH-2774 split it into a
  package: `scripts/little_loops/fsm/validation/{_base.py, meta_rules.py,
  shell_safety.py, evaluator_rules.py, reachability.py, structural_rules.py}`. There is
  no single `MR_RULES`-style dataclass/tuple table there — each MR is its own
  `_validate_*` function scattered across the family modules and re-exported through
  `fsm/validation/__init__.py:44-255`. The `.claude/CLAUDE.md` MR table documents these
  functions' behavior; it isn't a mirror of a Python data structure. The closest thing
  to a genuine "curated table as module data" shape is
  `EVALUATOR_REQUIRED_FIELDS: dict[str, list[str]]` in
  `scripts/little_loops/fsm/validation/_base.py:45-61`. **Better structural template**:
  `EscapeViolation`/`LintResult` dataclasses + `_lint_file()`/`run_escape_lint()` in
  `scripts/little_loops/cli/verify_package_data.py:55-163` — single dataclass, single
  regex-per-line loop, directly analogous to the proposed `ProseFinding`/`scan_prose()`
  shape.
- **Closest domain-matched existing tool is `ll-verify-skills`**, not `ll-verify-decisions`.
  `main_verify_skills()` (`scripts/little_loops/cli/docs.py:237-310`) already scans
  `skills/*/SKILL.md` via `check_skill_sizes()`
  (`scripts/little_loops/doc_counts.py:384-419`), including the
  `disable-model-invocation` skip check via `_parse_skill_frontmatter()`. It does **not**
  scan `commands/*.md` — ENH-2951 needs to add that. Its skeleton (argparse,
  `-C/--directory`, `add_json_arg`, `print_json`) is worth copying; its per-file (not
  per-line) violation shape is not — ENH-2951 needs `file:line` granularity, closer to
  `verify_package_data.py`'s `_lint_file()`.
- **No existing verify tool calls `skill_expander._find_plugin_root()`.**
  `check_skill_sizes()`/`check_skill_budget()` (`doc_counts.py`) and
  `main_verify_triggers()` (`verify_triggers.py:706-707`) all instead take a
  `-C/--directory`-overridable `base_dir` defaulting to `Path.cwd()` and compute
  `base_dir / "skills"` directly — not a `__file__` walk and not `_find_plugin_root()`.
  Adopting `_find_plugin_root()` (`skill_expander.py:25-35`, respects
  `CLAUDE_PLUGIN_ROOT` env var) as this issue proposes would make `ll-verify-skill-prose`
  the first `ll-verify-*` scanner to do so, diverging from the sibling tools'
  `-C/--directory` convention — worth a conscious choice, not an oversight, since it
  changes how the tool composes with `-C` overrides other verify tools support.
- **No suppression-comment mechanism exists anywhere in this codebase today** (searched
  `scripts/`, `skills/`, `commands/` for `noqa` / `<!-- ll-` style directives — none
  found; existing `<!--` HTML comments in `skills/` are ordinary prose, not directives).
  The established suppression idiom is a **whole-loop boolean flag** (e.g. `fsm/
  validation/meta_rules.py`'s `if fsm.shared_state_ok: return []`), documented per-flag
  in `.claude/CLAUDE.md`'s MR table. ENH-2951's per-line `<!-- ll-prose-ok: reason -->`
  inline suppression is a genuinely new mechanism, not a variant of an existing one —
  flag this explicitly in the PR description since reviewers may look for a precedent
  that doesn't exist.
- **`issue_parser.py:449` is a stale line reference.** Current content at that line is
  an unrelated import (`from little_loops.issues.prose_deps import
  extract_prose_deps`). The actual Pattern E option-detection prose duplication (ENH-2936)
  lives at `issue_parser.py:614-723`: `_DECIDE_IMPERATIVE_RE`/`_PREFERENCE_MARKER_RE`/
  `_INLINE_OR_RE` constants (614-642) and `_locate_directive_alternatives()` (654-723),
  whose own docstring self-declares the "ENH-2936, Pattern E" mirroring of
  `skills/decide-issue/SKILL.md` Phase 3b. Use `issue_parser.py:614-723` as the citation
  in the marker table / baseline record, not `:449`.
- **`ll-doctor --full` registration**: two-function adapter pattern —
  `_full_<name>_data() -> dict` calling the underlying tool's internal function directly
  (not shelling out), followed by an `@register_full_check`-decorated
  `_full_<name>_check() -> list[CheckResult]` wrapping it into a `CheckResult`. See
  `_full_skills_data`/`_full_skills_check` (`doctor.py:551-565`) as the closest template.
  `register_full_check` / `_FULL_CHECKS` live at `doctor.py:477-491`.

## Implementation Steps

1. Marker table + scanner + `--json`; suppression comment support.
2. Baseline the current tree: every existing hit must map to an EPIC-2938 child that
   deletes it, or get an explicit suppression with a reason. Record the baseline count.
3. Register the entry point (triple registration per BUG-2764: `scripts/pyproject.toml`,
   `skills/configure/areas.md` preset, `init/writers.py::_LL_PERMISSIONS`); add to
   `ll-doctor --full`.
4. Tests: one fixture per marker (positive + negative), suppression-comment behavior,
   and a test asserting the baseline only ever shrinks.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Land `scripts/pyproject.toml`'s new entry point, `skills/configure/areas.md`'s preset
   line, and `scripts/little_loops/init/writers.py::_LL_PERMISSIONS` together in the same
   commit — `test_verify_cli_allowlist.py::test_clean_state_returns_zero` reads live repo
   state and goes red if they land separately.
6. Update `scripts/tests/test_cli_doctor_full.py`: add `_full_skill_prose_data()`/
   `_full_skill_prose_check()` test coverage, and add the new check name to
   `test_run_full_checks_returns_check_result_per_verifier`'s literal expected-names set
   (line 255-273) — this existing test breaks once `@register_full_check` is registered.
7. Add a new `### ll-verify-skill-prose` section to `docs/reference/CLI.md` and a one-line
   bullet to `.claude/CLAUDE.md`'s `## CLI Tools` list.
8. Add a one-line catalog entry to each of the three independently hand-maintained CLI
   catalog mirrors: `commands/help.md`, `.gemini/commands/help.toml`,
   `.kimi-code/skills/ll-help/SKILL.md`.

## Program Design

### Types

- `ProseMarker: dataclass`
  - `name: str`
  - `pattern: re.Pattern`
  - `owner_cli: str`
  - `rationale: str`
- `ProseFinding: dataclass`
  - `path: Path`
  - `line: int`
  - `marker: str`
  - `owner_cli: str`
- `PROSE_MARKERS: tuple[ProseMarker, ...]` — the curated table

### Signatures

- `scan_prose(plugin_root: Path) -> list[ProseFinding]`
- `main_verify_skill_prose(argv: list[str] | None = None) -> int`

Exits 1 on any unsuppressed finding, matching the other `ll-verify-*` tools' contract.

### Call Path

- `main_verify_skill_prose()` -> `scan_prose()` -> `parse_skill_frontmatter()` (existing, `little_loops/frontmatter.py`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- New module: `scripts/little_loops/cli/verify_skill_prose.py`, following
  `verify_package_data.py`'s shape — `ProseMarker`/`ProseFinding` dataclasses, a
  `_lint_file(md_file, markers) -> list[ProseFinding]` per-line scanner (`enumerate(lines,
  start=1)` + `pattern.search(line)`), `scan_prose(base_dir) -> list[ProseFinding]`
  walking `sorted((base_dir / "skills").glob("*/SKILL.md"))` +
  `sorted((base_dir / "commands").glob("*.md"))`, text + JSON reporters, and
  `main_verify_skill_prose()` wrapped in `cli_event_context(DEFAULT_DB_PATH,
  "ll-verify-skill-prose", sys.argv[1:])` with the family-standard `-C/--directory` +
  `--json` argparse flags (via `add_json_arg`) — matching `main_verify_skills()`
  (`docs.py:237-310`) and `main_verify_package_data()` (`verify_package_data.py:235`)
  rather than introducing the untested `_find_plugin_root()` path (see Proposed
  Solution research findings above).
- Wire into `scripts/little_loops/cli/__init__.py`'s import/`__all__` block (add
  `main_verify_skill_prose`, following the existing `main_verify_*` entries).
- `ll-doctor --full` adapter: `_full_skill_prose_data()` / `_full_skill_prose_check()`
  in `scripts/little_loops/cli/doctor.py`, mirroring `_full_skills_data`/
  `_full_skills_check` (`doctor.py:551-565`), calling `scan_prose()` directly.

## Integration Map

### Files to Modify (new module + registration)
- `scripts/little_loops/cli/verify_skill_prose.py` — new module (marker table, scanner, CLI entry)
- `scripts/little_loops/cli/__init__.py` — import + `__all__` export of `main_verify_skill_prose`
- `scripts/pyproject.toml` — new `[project.scripts]` entry `ll-verify-skill-prose = "little_loops.cli:main_verify_skill_prose"`
- `skills/configure/areas.md` — add `Bash(ll-verify-skill-prose:*)` to the "All ll- commands" preset description string (existing `ll-verify-decisions` entry is the template)
- `scripts/little_loops/init/writers.py` — add `"Bash(ll-verify-skill-prose:*)"` to `_LL_PERMISSIONS` (alphabetical, near the other `Bash(ll-verify-*:*)` entries)
- `scripts/little_loops/cli/doctor.py` — new `_full_skill_prose_data()`/`_full_skill_prose_check()` pair, `@register_full_check`

### Dependent/Reference Files (existing owners the markers point to)
- `scripts/little_loops/text_utils.py` — `calculate_word_overlap()` (Jaccard marker owner), `extract_words()` (stop-word-list marker owner)
- `scripts/little_loops/issue_parser.py:614-723` — self-declared Pattern E prose duplication (ENH-2936 regression example; corrects the issue's stale `:449` citation)
- `skills/decide-issue/SKILL.md` — the regression site (commit `5e29c4d4`) that duplicates `issue_parser.py`'s Pattern E logic

### Similar Patterns
- `scripts/little_loops/cli/verify_package_data.py:55-235` — closest structural template: dataclasses, per-line scanner, text+JSON reporters, `main_*()` shape
- `scripts/little_loops/cli/docs.py:237-310` + `scripts/little_loops/doc_counts.py:384-419` — closest domain template: scans `skills/*/SKILL.md`, frontmatter skip-check
- `scripts/little_loops/cli/verify_cli_allowlist.py` — triple-registration consistency checker (the gate ENH-2951's registration must satisfy)

### Tests
- `scripts/tests/test_verify_package_data.py` — test structure to mirror: one test class per unit, positive/negative fixture files via inline `write_text()`, `patch("sys.argv", ...)` + `patch("builtins.print")` for CLI-level tests, `capsys.readouterr()` + `json.loads()` for JSON-output tests, explicit line-number-correctness assertions
- New: `scripts/tests/test_verify_skill_prose.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_doctor_full.py` — add a `TestFullAdapters` method for `_full_skill_prose_data()`, mirroring `test_package_data_reports_full_when_clean`/`test_package_data_reports_unsupported_on_missing_root` (which test `_full_package_data_data()`, `doctor.py:630`). **Also update `test_run_full_checks_returns_check_result_per_verifier` (`test_cli_doctor_full.py:255-273`)** — it asserts an exact literal set of check names (`{"full:docs", "full:skill_budget", ..., "full:package_data", ...}`); registering `_full_skill_prose_check()` via `@register_full_check` will make this test fail until the new name is added to that set. This is a break, not an addition. [Agent 1 + Agent 3 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add a new `### ll-verify-skill-prose` section (prose description, Flags table, Exit codes, Examples), following the existing `### ll-verify-package-data` (line 3206) / `### ll-verify-decisions` (line 3263) sections. Heavier obligation than a catalog bullet — this file documents each `ll-verify-*` tool individually. [Agent 2 finding]
- `.claude/CLAUDE.md` — add a one-line bullet to the `## CLI Tools` section (after the existing `ll-verify-package-data` bullet at line 240), matching the `ll-verify-*` bullet format already used there. [Agent 1 + Agent 2 finding]
- `commands/help.md` — add a one-line entry to the `CLI TOOLS (pip install little-loops)` block (confirmed at line 279, alongside `ll-verify-skills`). [Agent 2 finding]
- `.gemini/commands/help.toml` — independent hand-copied mirror of the same catalog block (confirmed at line 275); needs the same one-line entry added separately — no generator wires these three from a single source. [Agent 2 finding]
- `.kimi-code/skills/ll-help/SKILL.md` — third independent hand-copied mirror of the same catalog block (confirmed at line 280); needs the same one-line entry added separately. [Agent 2 finding]
- `CHANGELOG.md` — every prior `ll-verify-*` tool introduction got a CHANGELOG entry under its shipped-version section (e.g. `ll-verify-package-data`, ENH-2277). Per `feedback_changelog_no_unreleased` convention, add this at release-prep time under a concrete `## [X.Y.Z] - DATE` section, not now. Noted for awareness, not an Implementation Step. [Agent 2 finding]

### Configuration
- None beyond the triple-registration files above

### Sequencing Note
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero` reads live repo state (dynamic discovery via `_all_ll_entry_points()`, `_areas_md_preset_tools()`, `_writers_preset_tools()` — no fixture/list to hand-edit). It will go red if `scripts/pyproject.toml`'s new entry point lands before `skills/configure/areas.md` and `writers.py::_LL_PERMISSIONS` are updated. Land all three triple-registration files in the same commit. [Agent 2 + Agent 3 finding]

## Scope Boundaries

- In scope: the marker table, scanner, suppression mechanism, entry-point registration,
  pytest gate, baseline record.
- Out of scope: deleting the prose itself (that is each sibling child's job), semantic
  detection of *any* duplicated algorithm (the marker table is deliberately curated, not
  general), FSM loop YAML (covered by `ll-loop validate`'s MR rules).

## Impact

- **Priority**: P1 - Wave 1; without it EPIC-2938's headline criterion is unenforceable and demonstrably regresses
- **Effort**: Small - Marker table + scanner, same shape as existing `ll-verify-*` tools
- **Risk**: Low - Read-only lint; suppression escape hatch prevents hard-blocking

## Resolution

Implemented `ll-verify-skill-prose` (`scripts/little_loops/cli/verify_skill_prose.py`):
`PROSE_MARKERS` curated table (6 markers), per-line `_lint_file()` scanner,
`<!-- ll-prose-ok: reason -->` suppression, `scan_prose()` walking
`skills/*/SKILL.md` (skipping `disable-model-invocation: true`) + `commands/*.md`,
text/JSON reporters, `main_verify_skill_prose()`. Registered in
`scripts/pyproject.toml`, `skills/configure/areas.md`, `writers.py::_LL_PERMISSIONS`
(triple registration verified via `ll-verify-cli-allowlist`), and `ll-doctor --full`
(`_full_skill_prose_data`/`_full_skill_prose_check`). Baseline over the current tree
is 23 findings (19 `inline_python_computation`, 4 `git_mv_glob_loop`); recorded as
`BASELINE_COUNT` in `scripts/tests/test_verify_skill_prose.py`, which asserts the
live count never exceeds it. Docs updated: `docs/reference/CLI.md`,
`.claude/CLAUDE.md`, and the three hand-maintained catalog mirrors
(`commands/help.md`, `.gemini/commands/help.toml`, `.kimi-code/skills/ll-help/SKILL.md`).

## Status

**Open** | Created: 2026-07-31 | Priority: P1

## Acceptance Criteria

- [ ] `ll-verify-skill-prose` exits 1 on each marker with a fixture, 0 on a clean tree
- [ ] Every current-tree hit is either mapped to an EPIC-2938 child or suppressed with a stated reason; the baseline count is recorded
- [ ] A test asserts the baseline count never increases
- [ ] `ll-verify-cli-allowlist` passes with the new entry point (triple registration)
- [ ] Included in `ll-doctor --full`
- [ ] pytest coverage in `scripts/tests/`

## Notes

Deliberately a curated marker list, not a general duplicate-algorithm detector — the
value is catching the six known shapes cheaply, not proving a hard problem.


## Session Log
- `/ll:manage-issue` - 2026-08-01T08:24:50 - `d3f34f19-199a-4834-b76c-bc6f3baf8371.jsonl`
- `/ll:ready-issue` - 2026-08-01T08:13:34 - `ba70f12d-1eda-4589-9fdf-81d718e544a7.jsonl`
- `/ll:confidence-check` - 2026-08-01T08:12:30 - `398b7069-3b38-4c38-9a0b-926dda12b66d.jsonl`
- `/ll:wire-issue` - 2026-08-01T08:11:38 - `e62ace6d-4d32-4630-a8b2-6f64d26f348a.jsonl`
- `/ll:refine-issue` - 2026-08-01T08:07:05 - `fbd4e306-e0e0-45cc-9f5b-16f63a255cd3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-01T00:26:02 - `6fbac205-468a-44ce-b7fb-4626b0ac42e4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-01T00:25:50 - `6fbac205-468a-44ce-b7fb-4626b0ac42e4.jsonl`
