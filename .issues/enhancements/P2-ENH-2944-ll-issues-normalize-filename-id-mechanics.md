---
id: ENH-2944
title: 'll-issues normalize: filename/ID mechanics out of normalize-issues.md'
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- ENH-2941
- ENH-2953
labels:
- cli
- issues
- normalization
confidence_score: 96
outcome_confidence: 81
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 20
testable: true
---

# ENH-2944: `ll-issues normalize` — filename/ID mechanics

## Summary

`commands/normalize-issues.md` (511 lines — the largest file in EPIC-2938's scope) is dominated by rename/ID bookkeeping the LLM executes by hand. Convert to an `ll-issues` subcommand; the LLM keeps only semantic type-classification review.

**Descoped after review** (2026-07-31): `prioritize --apply` split to **ENH-2953**. It is thin (233 lines, one judgment step) and was being gated behind the meatiest conversion in the epic for no reason. The two share a `git mv` rename helper — whichever lands first owns it.

## Current Behavior

**normalize-issues**: legacy-dir checks (L80–107), per-basename ID regex scans (L117–131), ID→file map + `sort | uniq -d` duplicate detection written to `.loops/tmp/` (L137–154), `ll-issues next-id` + keep-oldest-duplicate rules + slug generation (L215–246), three fixed report tables (L251–289), `git mv` loops (L293–312). Even "type misclassification" (L158–202) is a keyword→type lookup with a `(signals_for_top_type)/(total_signals+1)` confidence formula and a 0.7 cutoff — a Python function, not judgment.

## Expected Behavior

`ll-issues normalize [ISSUE_ID...] [--check] [--auto] [--strict] [--json]` — detects missing/duplicate/malformed IDs, legacy dirs, and type mismatches; `--auto` applies renames via `git mv`; `--check` is a deterministic exit-code gate (EPIC convention: no LLM-narrated exits). Keyword-count type classification included; optionally cross-references ENH-2941's `find-similar --batch` for content-duplicate flagging (may land as a follow-up flag).

**Finding classes split by auto-fixability** (decided 2026-08-01 — see Design Decisions below):

| Kind | `--auto` fixes it? | In `--check`'s exit code? |
|------|--------------------|---------------------------|
| `missing_id` | yes (`git mv`) | yes |
| `malformed_id` | yes (`git mv`) | yes |
| `duplicate_id` | yes (`git mv`, reassign non-keeper) | yes |
| `legacy_dir` | no — `ll-migrate` owns this | only under `--strict` |
| `type_mismatch` | **never** — semantic judgment, left to the command's LLM-review step | only under `--strict` |

**Scoping**: bare `ll-issues normalize` operates on the whole corpus. Positional `ISSUE_ID`s scope which findings are *reported and applied*; the scan is always corpus-wide, because duplicate-ID detection and `get_next_issue_number()` allocation are inherently global.

### Design Decisions

_Resolved during pre-implementation review (2026-08-01) — these were open contradictions in the earlier draft:_

1. **`--check` must converge.** The old command (`commands/normalize-issues.md:61`) exits 1 on type-misclassification, but `--auto` will never fix a `type_mismatch` (semantic) or a `legacy_dir` (a directory move owned by `ll-migrate`, ENH-1390). Any FSM `gate → --auto → gate` cycle would therefore never reach exit 0. **Decision**: `--check`'s exit code covers only the three auto-fixable ID-mechanics classes; `legacy_dir`/`type_mismatch` are always *reported* (in text and `--json`) but only affect the exit code under an explicit `--strict`. This is a deliberate, documented behavior change from the current command.
2. **Per-issue scoping is preserved, not dropped.** `scripts/little_loops/loops/prompt-across-issues.yaml:19` invokes `/ll:normalize-issues {issue_id} --auto`, pinned by `scripts/tests/test_bug_2816_cli_invocations.py:83-90`. The command's `arguments:` block declares only `flags`, so today the ID falls into `$FLAGS` and is silently ignored (whole-corpus normalize). **Decision**: give the CLI a real `[ISSUE_ID...]` positional per the Scoping note above, and have the slimmed command forward it — closing the silent-ignore bug rather than inheriting it. The pinned invocation string is unchanged, so the test still passes.
3. **`bad_slug` is dropped.** It appeared in the finding enum with no detection rule, no definition, and no acceptance criterion. `is_normalized()`'s regex (`issue_parser.py:94`) already folds slug validity into `missing_id`/`malformed_id`; a separate class would be unreachable.

## Proposed Solution

Reuse `issue_parser` (`find_issues`, `slugify`, `get_next_issue_number`, `is_normalized`) and `frontmatter.py`. Duplicate-keep rule (oldest by git history, else alphabetical) implemented via `git log --follow` or file mtime fallback. Factor the `git mv` rename into a shared helper — ENH-2953 needs the same one.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. **Line numbers re-verified 2026-08-01**; the original refine pass cited a stale `issue_parser.py` revision and two modules that do not exist._

- **The `git mv` implementation to extract** — one real precedent, not the two originally cited:
  - `scripts/little_loops/issue_lifecycle.py:966-990` (inside `skip_issue()`) — `git mv` when `_is_git_tracked()` (line 393, via `git ls-files`) is true, `atomic_write()` + `Path.rename()` fallback for untracked files or on failure. **This is the block to extract** into the shared helper. `docs/reference/CLI.md:1772` already names that helper `git_mv_with_fallback()` in `issue_lifecycle.py` — extract under exactly that name so the prewritten doc becomes true (see Prewritten Docs below).
  - ~~`cli/issues/format_check.py:70` `_move_file()`~~ — **does not exist**; `format_check.py` has no move helper at all. (Already flagged by the wiring pass below; recorded here so the research bullet itself is not misleading.)
  - ~~`cli/loop/rename.py:199` `_apply_rename()`~~ — **does not exist**. ENH-2943 hit the same false-completion as this issue and its module was never committed (commit `3e76f972` stripped the wiring). Do not treat `RenameReport`/`rename_loop()` as an existing pattern to mirror; the dry-run/apply-parity shape is still right, but model it on `format_check.py`'s `--fix`/`--fix --apply` split instead (real, committed).
  - `scripts/little_loops/cli/migrate.py` has `_move_file()`/`_get_git_completion_date()` (git-log-based "which file is older") — the precedent for the keep-oldest-duplicate rule, using `git log --format=%as -1 -- <path>` with a `timeout=30` guard. `ll-migrate` also **owns legacy `completed/`/`deferred/` directory remediation** (ENH-1390), which is why `legacy_dir` is report-only here.
- **`find_issues()` signature and status coverage**: `scripts/little_loops/issue_parser.py:1855` — `find_issues(config, category=None, skip_ids=None, only_ids=None, type_prefixes=None, status_filter=None, *, skip_blocked=False) -> list[IssueInfo]`. `scan_normalize()` should pass `status_filter=set(_ALL_STATUSES)` (as `format_check.py:185`'s `--all` sweep does, importing it from `little_loops.issue_progress` per `format_check.py:160`) so done/deferred issues with malformed filenames aren't silently skipped.
- **`is_normalized`/`slugify`/`get_next_issue_number` are at the exact signatures assumed** by this issue: `issue_parser.py:94` (`is_normalized(filename: str) -> bool`, regex `^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$` — matches the Validation Rules regex at `commands/normalize-issues.md:429-434` exactly), `issue_parser.py:1027` (`slugify`), `issue_parser.py:1041` (`get_next_issue_number(config, category=None) -> int`, already scans all category dirs globally for the max `PREFIX-NNN`). `cli/issues/refine_status.py:337,362,441` already consumes `is_normalized()` for its normalized column (ENH-560) — reuse it, don't reimplement.
- **No existing duplicate-ID-detection helper**: the ID→file map + `sort | uniq -d` dedup logic (`commands/normalize-issues.md:133-156`) exists only as inline bash today — `scan_normalize()` needs to implement this fresh in Python (iterate `find_issues()` results, group by parsed ID, flag groups with len > 1).
- **CLI wiring convention** (`scripts/little_loops/cli/issues/__init__.py`): one module per subcommand under `cli/issues/<name>.py`, either registered inline in `main_issues()` (simple case, e.g. `next-id` at lines 162-176) or via a self-registering `add_<name>_parser(subs)` helper for subcommands with more flags (e.g. `add_format_check_parser(subs)` at line 893) — `normalize`'s `--check`/`--auto`/`--json` flag surface should use the `add_normalize_parser(subs)` form, dispatched from the `if args.command == "normalize":` chain around lines 909-977.
- **`NormalizeFinding` dataclass precedent**: `scripts/little_loops/cli/issues/find_similar.py`'s `SimilarityMatch` (per-item dataclass with a `to_dict()` returning rounded/plain fields, produced by a pure `find_similar()` function and JSON-printed by a thin `cmd_find_similar()` wrapper) is the closer template than `FormatGaps`' per-category-list shape, since `NormalizeFinding` is per-file.
- **Exact line ranges in `commands/normalize-issues.md` to extract/delete**: legacy-dir checks (76-113), ID regex scan (115-131), ID→file map + duplicate detection writing to `.loops/tmp/` (133-156), type-misclassification keyword table + confidence formula (158-202, keep only as the LLM review prompt, not the scoring math), category/prefix mapping (204-213), next-ID lookup (215-223), filename generation incl. keep-oldest-duplicate rule (225-245, keep-oldest rule at line 239), the two report tables (247-291 "Normalization Plan", 374-425 "Issue Normalization Report"), and the `git mv` rename loop (293-312).
- **Test fixture pattern to follow**: ~~`scripts/tests/test_cli_loop_rename.py`'s `TestRenameLoopDryRunParity`~~ — **does not exist** (same ENH-2943 false-completion). Use `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckFix` (FEAT-2851) for the dry-run-preview/`--apply`-idempotency criterion instead: it asserts a second apply reports no further gap and leaves the file byte-identical. `scripts/tests/test_ll_issues_find_similar.py`'s `_run(argv, temp_project_dir, sample_config)` helper shows the `main_issues()`-level CLI invocation pattern (patches `sys.argv`, writes `.ll/ll-config.json`, redirects stdout) for testing `ll-issues normalize` end-to-end.

## Integration Map

### Files to Modify
- `commands/normalize-issues.md` — slim from 511 → ~80 lines; delete the mechanical sections listed above, keep only the flag-parsing intro, the type-misclassification LLM-review prompt (stripped of the confidence-formula math), and the final "review + confirm" narration.
- `scripts/little_loops/cli/issues/__init__.py` — add `normalize` module import, `add_normalize_parser(subs)` registration (or inline parser if flag surface stays small), and dispatch arm in the `if args.command == "..."` chain (around lines 838-977).

### New Files
- `scripts/little_loops/cli/issues/normalize.py` — `NormalizeFinding` dataclass, `scan_normalize(issues_dir_or_config) -> list[NormalizeFinding]`, `apply_normalize(findings) -> None`, `classify_type(issue) -> tuple[str, float]`, `cmd_normalize(config, args) -> int`.

### Dependent Files (Callers/Importers)
- `skills/ll-normalize-issues/SKILL.md` — thin wrapper pointing at `commands/normalize-issues.md`; no code change needed but should be checked after the command is slimmed to ensure trigger examples still match.
- `commands/prioritize-issues.md` / ENH-2953 — expected to import the same `git mv` helper this issue factors out; coordinate the helper's exact location/signature so ENH-2953 doesn't duplicate it.

### Similar Patterns

_Re-verified 2026-08-01. `cli/loop/rename.py` and `cli/loop/cleanup.py` were cited by the refine pass but **do not exist** — ENH-2943's modules were never committed. Only the entries below are real._

- `scripts/little_loops/cli/issues/format_check.py` — the primary sibling: `--check` exit-code convention (0 clean / 1 violations), `scan`-vs-`apply` split, `--fix`/`--fix --apply` dry-run parity, and `add_format_check_parser(subs)` self-registration.
- `scripts/little_loops/cli/issues/find_similar.py` — pure-function-returns-`list[dataclass]` + thin `cmd_*` JSON-printing wrapper, the template for `NormalizeFinding`.
- `scripts/little_loops/issue_lifecycle.py:934-990` (`skip_issue()`) — the git-mv-with-fallback block to extract.
- `scripts/little_loops/cli/migrate.py` — `_get_git_completion_date()` for the keep-oldest-duplicate rule.

_Wiring pass added by `/ll:wire-issue`:_
- **Correction to the git-mv helper pointer above**: `cli/issues/format_check.py` has no `_move_file()`/`_is_git_tracked()` — those live in `scripts/little_loops/issue_lifecycle.py`: `_is_git_tracked()` at line 393, and the git-mv-with-fallback pattern to mirror is `skip_issue()` (~line 934-990: `git mv` when tracked, `atomic_write()` + `Path.rename()` fallback on failure or when untracked). Import from `issue_lifecycle`, not `format_check`. **Confirmed accurate 2026-08-01.**

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_bug_2816_cli_invocations.py:83-90` (`TestPromptAcrossIssuesQuickFix`) — pins `/ll:normalize-issues {issue_id} --auto` as the exact invocation string used by `scripts/little_loops/loops/prompt-across-issues.yaml:19`, and asserts no `--quick` flag exists. The `--auto` flag name/behavior on the slimmed command must survive unchanged.
- `skills/ll-normalize-issues/SKILL.md`, `.kimi-code/skills/ll-normalize-issues/SKILL.md`, `.gemini/commands/help.toml` — generated host-adapter mirrors of `commands/normalize-issues.md` (via `ll-adapt`). These go stale once the command is slimmed; regenerate with `ll-adapt --host <host> --apply` for each host after editing.

### Documentation

**⚠ Prewritten docs already exist — this is a reconcile, not an add.** The false-completion cycle (see Notes) left full documentation in the tree for a CLI that was never written. Verified 2026-08-01:

- `docs/reference/CLI.md:1768-1789` — a complete `#### ll-issues normalize` section already exists, describing the finding kinds, the `signals_for_top_type / (total_signals + 1)` ≥0.7 heuristic, the `--check`/`--auto`/`--json` table, and examples. It is a **more precise spec than this issue's original draft** (notably: `type_mismatch` is never auto-applied) and should be treated as the target contract. Two claims in it are **false today and must be made true or deleted**:
  - `git_mv_with_fallback()` in `issue_lifecycle.py` — **no such symbol exists.** Extract `skip_issue()`'s git-mv block under exactly this name to make the doc true.
  - "The `ensure_formatted` gate in `rn-remediate.yaml` calls this as a shell action" — **false**; `rn-remediate.yaml:98` calls `ll-issues format-check`. Delete this line or wire it for real.
  - Also update the flag table for the `[ISSUE_ID...]` positional and `--strict` added by the Design Decisions above.
- `.claude/CLAUDE.md:251` — the `ll-issues` bullet **already lists** `normalize (--check/--auto/--json; filename/ID mechanics ... ENH-2944)`. Amend it for `[ISSUE_ID...]`/`--strict` rather than adding a duplicate entry. (No test cross-checks this enumeration against actual argparse subparsers — `test_wiring_cli_registry.py`'s `DOC_STRINGS_PRESENT` only asserts individual substrings — so this is a by-hand edit.)
- `scripts/little_loops/cli/verify_skill_prose.py:100-101` and `docs/reference/CLI.md:3335` — the `git_mv_glob_loop` marker already names `ll-issues normalize` as its owning CLI. No change needed; it becomes accurate on landing.
- `docs/guides/LOOPS_GUIDE.md:1004` — documents the `--check` flag's FSM exit-code evaluator contract (`evaluate: type: exit_code`) shared across several "issue prep skills" including `normalize-issues`; the slimmed command's `--check` passthrough to `ll-issues normalize --check` must preserve this contract (0 clean / 1 violations).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py:134-135` — **hard constraint**: asserts literal substrings `"EPIC"` and `"epics/"` are present in `commands/normalize-issues.md` (FEAT-1407, epic-type support). The slimmed ~80-line command must retain at least one occurrence of each (e.g. in the retained type-classification LLM-review prompt's EPIC row/epics/ directory example) or this test fails.
- `scripts/tests/test_ll_issues_format_check.py` — closest sibling CLI test file; its `format_check_dir` fixture, `_write_issue()` helper, and `_invoke(argv)` (patches `sys.argv`, calls `main_issues()` directly, not subprocess) is an equally-valid alternate model to `test_ll_issues_find_similar.py`'s `_run()` harness already cited above. Its `TestFormatCheckFix` (FEAT-2851) is the closest existing dry-run-preview/`--apply`-idempotent precedent (second apply reports no further gap, file byte-identical) — model the `--check`/`--auto` idempotency test on this rather than deriving it fresh.
- `scripts/tests/test_verify_skill_prose.py:19` — `BASELINE_COUNT = 23`, asserted as a ceiling by `TestBaselineNeverIncreases`. **Corrected 2026-08-01**: the tree currently reports **21** findings, not 23. Two are this issue's exact target (`commands/normalize-issues.md:299` and `:304`, both `[git_mv_glob_loop]`); two more are ENH-2953's (`commands/prioritize-issues.md:110,171`, also attributed to `ll-issues normalize`). Landing this issue must drop the constant `23 → 19`, and ENH-2953 must then drop it `19 → 17`. **These two issues edit the same line — whichever lands second must re-verify and re-lower rather than assume its own delta.** This is an enforceable acceptance criterion, not a manual spot-check.

## Implementation Steps

0. Extract `git_mv_with_fallback()` into `scripts/little_loops/issue_lifecycle.py` from `skip_issue()`'s inline block (lines 966-990), and refactor `skip_issue()` to call it. The name is fixed by the prewritten `docs/reference/CLI.md:1772`; ENH-2953 imports the same helper.
1. Create `scripts/little_loops/cli/issues/normalize.py`: `NormalizeFinding` dataclass, `scan_normalize()` (built on `issue_parser.find_issues(config, status_filter=set(_ALL_STATUSES))`, `is_normalized()`, and fresh Python ID-duplicate-detection logic replacing the bash map/`uniq -d` at `commands/normalize-issues.md:133-156`), `classify_type()` (port the keyword-signal table + `(signals_for_top_type)/(total_signals+1)` confidence formula from lines 166-182, ≥0.7 cutoff), and `apply_normalize()` (using the step-0 helper; must never overwrite an existing path, never allocate a colliding ID, and never act on a `type_mismatch` or `legacy_dir` finding).
2. Wire `ll-issues normalize [ISSUE_ID...] [--check] [--auto] [--strict] [--json]` into `scripts/little_loops/cli/issues/__init__.py` following the `add_format_check_parser(subs)` self-registration convention; `--check` returns 0/1 per the `format_check.py:cmd_format_check` pattern, over the auto-fixable classes only (`--strict` widens it — see Design Decisions).
3. Slim `commands/normalize-issues.md` (511 → ~80), deleting the mechanical sections cataloged above, keeping only the type-misclassification LLM-review step; forward the positional issue ID through to the CLI rather than dropping it into `$FLAGS`.
4. Tests in `scripts/tests/test_ll_issues_normalize.py`: fixture tree with missing/dup/malformed IDs (model fixtures on `test_ll_issues_find_similar.py`'s `_write_issue()`/`_run()` helpers); check-mode exit codes **including the convergence case** (a corpus whose only findings are `type_mismatch`/`legacy_dir` must exit 0 without `--strict`, and 1 with it); apply idempotency (model on `test_ll_issues_format_check.py::TestFormatCheckFix` — second apply reports no further gap, files byte-identical); `[ISSUE_ID...]` scoping restricts applied renames while duplicate detection stays corpus-wide.
5. Coordinate the shared helper with ENH-2953: this issue owns creating `git_mv_with_fallback()`; ENH-2953 imports it. Also coordinate the `BASELINE_COUNT` decrement (see Tests).
6. Reconcile the prewritten docs (see Documentation) — this includes deleting or making true the two false claims in `docs/reference/CLI.md:1768-1789`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. ~~Mirror the git-mv-with-fallback helper~~ — **folded into step 0 above** (extract, don't mirror; the name `git_mv_with_fallback()` is fixed by prewritten docs).
8. When slimming `commands/normalize-issues.md`, retain at least one occurrence each of the literal strings `"EPIC"` and `"epics/"` — `test_wiring_skills_and_commands.py:134-135` asserts their presence (FEAT-1407) and will fail otherwise. **Verified still present 2026-08-01.**
9. ~~Add `#### ll-issues normalize` to `docs/reference/CLI.md` … add `normalize` to `.claude/CLAUDE.md`~~ — **both already exist** (false-completion residue). Superseded by step 6: reconcile and correct them. See Documentation.
10. After slimming, regenerate host-adapter mirrors of the command via `ll-adapt --host <host> --apply` (Codex, etc. — `skills/ll-normalize-issues/SKILL.md`, `.kimi-code/skills/ll-normalize-issues/SKILL.md`, `.gemini/commands/`).

## Program Design

### Types

- `NormalizeFinding: dataclass`
  - `path: Path`
  - `kind: str`  (missing_id | duplicate_id | malformed_id | legacy_dir | type_mismatch) — `bad_slug` dropped, see Design Decision 3
  - `proposed_path: Path | None`
  - `confidence: float | None`
  - `to_dict() -> dict` — rounded/plain fields for `--json`, per `find_similar.SimilarityMatch`
- `AUTO_FIXABLE_KINDS: frozenset[str]` = `{"missing_id", "malformed_id", "duplicate_id"}` — the single source of truth shared by `--auto`'s apply filter and `--check`'s non-`--strict` exit code

### Signatures

- `scan_normalize(config: BRConfig, only_ids: set[str] | None = None) -> list[NormalizeFinding]` — via `issue_parser.find_issues(config, status_filter=set(_ALL_STATUSES))`, `is_normalized`, `slugify`. Takes `BRConfig`, not a bare `issues_dir`, because `get_next_issue_number()` and `find_issues()` are both config-driven. `only_ids` filters the returned findings; duplicate detection still runs over the full corpus.
- `apply_normalize(findings: list[NormalizeFinding]) -> list[NormalizeFinding]` — returns the subset actually applied; skips any kind outside `AUTO_FIXABLE_KINDS`. Uses `issue_lifecycle.git_mv_with_fallback()`, ID allocation via `get_next_issue_number`.
- `classify_type(issue: IssueInfo) -> tuple[str, float]` — keyword-signal table + `(signals_for_top_type)/(total_signals+1)` confidence, flagged at ≥0.7
- `cmd_normalize(config: BRConfig, args: Namespace) -> int` — thin wrapper: text or `{"findings": [...], "applied": [...]}` JSON, exit 0/1

### Call Path

- `scan_normalize()` -> `find_issues()` (existing) -> `slugify()` (existing, `issue_parser.py`)
- `apply_normalize()` -> `get_next_issue_number()` (existing, `issue_parser.py`)

## Scope Boundaries

- In scope: the `normalize` subcommand (`--check`/`--auto`), slimming `commands/normalize-issues.md`, the deterministic exit-code gate, and the shared `git mv` rename helper.
- Out of scope: semantic (LLM) type reclassification, content-duplicate merging (flagging only, via ENH-2941 follow-up), `prioritize` (ENH-2953), changing the P0–P5 taxonomy.

## Impact

- **Priority**: P2 - Converts the largest single file in scope (511 lines) and fixes a narrated exit-code gate
- **Effort**: Medium - normalize is meaty
- **Risk**: Low-Medium - Renames via `git mv` with `--check` preview; collision-safe ID allocation tested

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues normalize --check` exit code is the FSM-usable gate (0 clean / 1 violations)
- [ ] **`--check` converges**: a corpus whose only remaining findings are `type_mismatch`/`legacy_dir` exits 0 without `--strict` (and 1 with it), so a `gate → --auto → gate` FSM cycle terminates
- [ ] `--auto` renames preserve git history (`git mv`) and never allocate colliding IDs
- [ ] `--auto` **never** applies a `type_mismatch` or `legacy_dir` finding
- [ ] `--json` emits `{"findings": [...], "applied": [...]}` with every finding kind representable, `applied` empty unless `--auto`
- [ ] Positional `[ISSUE_ID...]` scopes reported/applied findings; duplicate-ID detection and next-ID allocation remain corpus-wide
- [ ] `legacy_dir` findings are detected and reported (pointing at `ll-migrate`), not silently dropped
- [ ] `commands/normalize-issues.md` is ≤ ~80 lines and `ll-verify-skill-prose` reports **0** findings for it; `BASELINE_COUNT` in `test_verify_skill_prose.py:19` lowered accordingly (23 → 19, re-verified against the tree at land time)
- [ ] `git_mv_with_fallback()` exists in `issue_lifecycle.py`, is called by `skip_issue()`, and is importable by ENH-2953
- [ ] `docs/reference/CLI.md:1768-1789` contains no false claims (`git_mv_with_fallback` real; the `rn-remediate.yaml` line true or deleted) and matches the shipped flag surface
- [ ] `python -m pytest scripts/tests/` exits 0, with new coverage in `scripts/tests/test_ll_issues_normalize.py`

## Notes

`prioritize` was split to ENH-2953 so it ships without waiting on this issue's classification heuristics.

**False-completion history (2026-08-01)**: an `ll-auto` run marked this issue done via the "automated fallback" path ("Command exited early but issue was addressed") without writing any code. The bogus `completed_at` and `## Resolution` section have been stripped, and the issue was reopened in commit `6eb6dd21`. The run did, however, leave **documentation for the unwritten CLI** in the tree — `docs/reference/CLI.md:1768-1789` and `.claude/CLAUDE.md:251` — plus a `verify_skill_prose.py` marker attributing `git_mv_glob_loop` to `ll-issues normalize`. Commit `3e76f972` stripped the CLI wiring but not the docs. Implementation must therefore *reconcile* prewritten docs rather than author new ones, and must not trust their claims (two are false — see Documentation). ENH-2943 and ENH-2952 hit the same failure; ENH-2943's `cli/loop/rename.py`/`cleanup.py` are likewise documented-but-absent, which is why several of this issue's original "similar pattern" citations were dangling.


## Session Log
- `ll-auto` - 2026-08-01T09:09:26 - `ec714973-d76f-4116-84ff-2e2c0251f99e.jsonl`
- `/ll:confidence-check` - 2026-08-01T08:56:23 - `07fe8ff1-a654-49aa-b711-930081c502cd.jsonl`
- `/ll:wire-issue` - 2026-08-01T08:55:16 - `f37cbe16-d840-480f-83e5-7eb99669367a.jsonl`
- `/ll:refine-issue` - 2026-08-01T08:50:10 - `6d9c28da-0fa7-4143-9794-2101fbcb91ff.jsonl`
