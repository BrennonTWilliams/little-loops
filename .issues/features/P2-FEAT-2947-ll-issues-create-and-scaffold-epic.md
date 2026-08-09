---
id: FEAT-2947
title: 'll-issues create and scaffold-epic: atomic issue/epic creation'
type: FEAT
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- issues
- scaffolding
testable: true
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
size: Large
---

# FEAT-2947: `ll-issues create` + `scaffold-epic` — atomic issue/epic creation

## Summary

There is no `ll-issues create`: `next-id` + `sections` provide the pieces, but file assembly — ID allocation with duplicate-retry, slugging, path selection, frontmatter, template body, staging — is narrated in prose in every creating skill. This is why `skills/scope-epic/SKILL.md` (484 lines) and `skills/capture-issue/SKILL.md` (497 lines) are so heavy. Add the write path and an epic-scaffolding composition.

## Current Behavior

- scope-epic Phase 4 (L284–380): `next-id` immediately-before-each-Write, three filename templates with slugification (L299, L338, L363), a duplicate-ID retry loop (L324); Phase 5 (L384–420) wires `parent:`/`## Children` both directions; Phase 6 stages.
- capture-issue Phase 4 (L249–333): the same dance independently restated.

## Expected Behavior

- `ll-issues create --type FEAT|BUG|ENH|EPIC --title "..." [--priority P2] [--body-file PATH|-] [--parent EPIC-N] [--labels a,b] [--stage] --json` — atomic: allocates ID (retry on collision), slugs, selects the type dir, writes frontmatter + template body (from `ll-issues sections`), optionally wires `parent:` both directions, optionally `git add`s. Returns `{id, path}`.
- `ll-issues scaffold-epic --title "..." --children <json|@file> [--priority P2] [--stage] --json` — composes `create`: EPIC + pre-wired child stubs (`parent:`, EPIC `## Children`), staged atomically.
- `skills/scope-epic/SKILL.md` shrinks to: decompose the theme into child titles/scopes (real reasoning), emit children JSON, call the CLI.
- **capture-issue is a named adopter**: it is the highest-traffic creation path and ENH-2941 already slims its dedup phase; its Phase 4 must switch to `create` (in this issue or an explicit follow-up AC) — do not land the CLI with scope-epic as its only consumer.

## Proposed Solution

Reuse `issue_parser.get_next_issue_number` + `slugify`, `frontmatter.update_frontmatter`, `ll-issues sections` templates, `file_utils.acquire_lock` for ID allocation, and the `_commit_issue_completion` `git add`/`git reset` idiom for `--stage`. `create` lands first inside the issue; `scaffold-epic` composes it.

### Resolved Design Decisions

_Added 2026-08-09 — resolves every ambiguity flagged by `/ll:confidence-check`. Each decision is evidence-backed; implementation must follow them, not re-litigate them._

**D1 — Parser registration: use the delegated `add_<name>_parser(subs)` style.**
Not actually contested — it is legacy vs. current, and the split is lopsided. 17 subcommand modules define `add_*_parser(subs)` (`link.py:17`, `normalize.py:502`, `size.py:158`, `format_check.py:55`, `fold_findings.py:33`, `research_triage.py:25`, `prioritize.py:162`, `set_flags.py:334`, `epic_progress.py:16`, `epic_consistency.py:262`, `deferred_triage.py:39`, `decisions.py:15`, `finalize_decomposition.py:64`, `link_epics.py:257`, `check_*.py` ×3), all registered from `__init__.py:731-733,862-863,948-959`; only three legacy subcommands (`next-id`, `sections`, `path`) are wired inline. New code follows the 17, not the 3. Dispatch stays in the existing flat `if/elif` chain (`__init__.py:974-1061`) — no dict table.

**D2 — Frontmatter serialization: build the block with `update_frontmatter("", {...})` and concatenate; do NOT modify `assemble_issue_markdown`.**
Verified by execution, not inspection:
- `update_frontmatter("", {...})` from scratch is correct — emits `parent: null` for `None`, quotes colon-bearing titles (`title: 'a: colon title'`), and block-serializes lists. Round-trips through `parse_frontmatter` to exactly the input dict.
- **The naive composition is broken and must not be used.** Calling `assemble_issue_markdown(..., frontmatter={})` and then `update_frontmatter(body, {...})` on the resulting empty `---\n---` block produces corrupt output (`labels:\n- cli---`, no newline before the closing fence) which `parse_frontmatter` reads as `{}` — total frontmatter loss. Confirmed by running it.
- **Therefore**: extract the section-assembly half of `assemble_issue_markdown` into a new `assemble_issue_body(sections_data, issue_type, variant, issue_id, title, content) -> str`, and redefine `assemble_issue_markdown` as `frontmatter-loop + assemble_issue_body` so its output stays byte-identical for its one production caller (`sync.py:735`, the GitHub import path). `create_issue()` calls `update_frontmatter("", fm) + "\n" + assemble_issue_body(...)`.
- **Blast radius is zero, not seven call sites.** The confidence-check concern about 7 downstream `.parent`-truthiness sites is void under this decision: `assemble_issue_markdown`'s behavior is unchanged, so the stringified-`"None"` path is neither fixed nor relied upon here — `create_issue()` simply never enters it. Independently confirmed: `grep` finds no `"None"`-string special-casing in `cli/issues/*.py` or `issue_parser.py`, and zero issue files on disk carry `parent: None`.

**D3 — ID collision: allocate under `file_utils.acquire_lock`, with `O_EXCL` as the backstop.**
The "no precedent, write from scratch" finding was wrong — `file_utils.acquire_lock(path, timeout=10.0)` (`file_utils.py:61`) is a general `fcntl.flock(LOCK_EX|LOCK_NB)` polling context manager, and `rn_synth_queue.try_pop_ready` (`rn_synth_queue.py:109-122`) is a working precedent for exactly this shape: read-select-write under one lock hold so concurrent callers never claim the same slot. `create_issue()` holds `acquire_lock(issues_dir / ".id-alloc.lock")` across `get_next_issue_number()` → path construction → file write, and writes via `open(path, "x")` so a cross-process racer that bypasses the lock still fails loudly rather than clobbering; on `FileExistsError`, retry up to 5 times. This also subsumes the bash `check-duplicate-issue-id*.sh` hooks that the pure-Python path bypasses.

**D4 — `--stage` copies the `_commit_issue_completion` idiom; it does not call it.**
Correcting an earlier research finding: `_commit_issue_completion` (`issue_lifecycle.py:648-671`) *commits*, and takes an `IssueInfo` — wrong shape and wrong side effect for `create`. Write a local `_stage(paths, repo_root)` that reuses only the idiom: `subprocess.run(["git","add","--",*paths], timeout=60)`, `git reset -- <paths>` on non-zero exit, never `git add -A` (BUG-2421).

**D5 — `scaffold-epic` atomicity: assemble-all-then-write, unlink-on-failure. `scaffold-epic` stays in this issue.**
The "no transactional multi-file rollback pattern exists" finding is true but irrelevant here, because every file `scaffold_epic()` touches is one it just created — there is no prior content to roll back, so `Path.unlink()` is a complete undo. Sequence: allocate all N+1 IDs under a single lock hold → assemble all contents in memory → write all files → on any exception, unlink every path created in this call and re-raise → stage once with all paths on success. This makes the Notes section's "split `scaffold-epic` out if atomic-staging/rollback semantics get involved" escape hatch unnecessary; both commands ship together.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `finalize-decomposition` (`scripts/little_loops/cli/issues/finalize_decomposition.py`, delegating to `recursive_finalize.finalize_decomposed_parent()`) operates on already-existing parent/children issue files after an `rn-decompose` loop run — it closes the parent and re-links children to the parent's EPIC ancestor. It does not allocate IDs, write new issue files, or stage anything via git — it is not a staging pattern this issue can reuse. The closest actual git-staging precedent is `issue_lifecycle.py:648-671` (`_commit_issue_completion`), see Integration Map / Program Design findings.

## Implementation Steps

1. Extract `assemble_issue_body()` out of `assemble_issue_markdown()` (**D2**); assert byte-identical output for the existing `sync.py:735` caller via the existing `test_issue_template.py:104-201` suite.
2. `create` (all types) + tests (ID collision retry under `acquire_lock`, template body, parent wiring, `--stage`).
3. `scaffold-epic` + tests (both-direction wiring, unlink-on-failure atomicity per **D5**).
4. Slim scope-epic Phases 4–6 and capture-issue Phase 4.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Route `create_issue()`'s frontmatter through `frontmatter.update_frontmatter("", {...})` concatenated with a new `assemble_issue_body()`, leaving `assemble_issue_markdown()` untouched — see **D2** in Resolved Design Decisions for the verified failure of the simpler composition and why the downstream `.parent` blast radius is zero
- Replace the `ll-issues next-id` call sites in `skills/scope-epic/SKILL.md:286,295,326,336,361` with `ll-issues scaffold-epic`
- Replace the `ll-issues next-id` / `ll-issues sections` call sites in `skills/capture-issue/SKILL.md:225,256,309` with `ll-issues create`
- Add `create`/`scaffold-epic` entries to the `main_issues()` epilog in `scripts/little_loops/cli/issues/__init__.py:110-205` (one-subcommand-per-line, alongside every other subcommand)
- Update the stale forward-reference note in `docs/reference/CLI.md:2138-2140` ("pending `ll-issues create` (FEAT-2947)") once `create` lands
- Add `("docs/reference/CLI.md", "ll-issues create", "FEAT-2947")` and `("docs/reference/CLI.md", "ll-issues scaffold-epic", "FEAT-2947")` to `scripts/tests/test_wiring_cli_registry.py`'s `DOC_STRINGS_PRESENT`
- Update `scripts/tests/test_scope_epic_skill.py:85-87` (`test_git_staging_referenced`) and `:73-77` (`test_ll_issues_next_id_referenced`), which assert on the current prose-based `git add`/`next-id` flow and will break once scope-epic switches to calling `scaffold-epic --stage`
- Write a new concurrent-collision-retry test modeled on `scripts/tests/test_git_lock.py:421-479`'s `threading.Event`-sequenced `threading.Thread` pattern (and on `scripts/tests/test_file_utils.py`'s existing `acquire_lock` coverage) — no existing test simulates two callers racing for the same next-ID
- Write a `--stage` test using the real-repo fixture `scripts/tests/helpers.py:44` (`copy_git_template`) per `scripts/tests/test_git_operations.py:239-299`, rather than mocking `subprocess.run(["git","add",...])`

## Use Case

`/ll:capture-issue` mines a conversation, drafts title/body, then calls `ll-issues create --type BUG --title "..." --body-file - --stage` and gets back `{id, path}` — no ID-collision retry dance, no filename templating in prose. `/ll:scope-epic` decomposes a theme, emits children JSON, and one `scaffold-epic` call writes the fully wired EPIC + stubs.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

### Behavior Parity

What each new surface replaces, and what must behave identically after the swap:

- `ll-issues create` replaces the prose ID/slug/filename dance in `skills/capture-issue/SKILL.md:225,256,309` and `skills/scope-epic/SKILL.md:286,295,326,336,361`. Parity requirement: same type→directory mapping (now read from `config/core.py:486` `get_issue_dir` rather than restated in prose), same `P<n>-<TYPE>-<NNN>-<slug>.md` filename shape, same template body as `ll-issues sections` emits today.
- `ll-issues scaffold-epic` replaces scope-epic Phase 5's both-direction wiring prose (`parent:` on each child + `## Children` on the EPIC) and Phase 6's `git add` prose. Parity requirement: output must still pass `ll-issues epic-consistency` and `format-check`, which is what the prose flow was implicitly guaranteeing.
- `assemble_issue_body()` replaces nothing — it is an extraction. Parity requirement: `assemble_issue_markdown()` output is byte-identical before and after, guarded by the existing `test_issue_template.py:104-201` suite running unmodified.
- The bash duplicate-ID hooks (`check-duplicate-issue-id*.sh`) remain in force for the Claude `Write` path; `create_issue()`'s lock + `O_EXCL` (**D3**) is the equivalent guarantee for the pure-Python path, not a replacement of those hooks.

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register new `create` and `scaffold-epic` subcommands via `add_create_parser(subs)` / `add_scaffold_epic_parser(subs)` alongside the existing delegated calls at :948-959, and add two arms to the flat if/elif dispatch chain at :974-1061 (**D1**)
- `scripts/little_loops/cli/issues/create.py` — new file, houses `cmd_create`/`add_create_parser`
- `scripts/little_loops/cli/issues/scaffold_epic.py` — new file, composes `create_issue()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/normalize.py:277-284` (`_alloc`) and `:124-131` (`_slug_for`) — closest existing precedent for ID-allocation/slugging composition; `_alloc` is an in-process monotonic counter seeded once from `get_next_issue_number()`, not a filesystem-collision-retry loop
- `scripts/little_loops/issue_parser.py:1559` (`get_next_issue_number`) — pure filesystem scan, returns `max+1`; does not reserve/lock; calling twice without an intervening write returns the same number
- `scripts/little_loops/issue_parser.py:1545` (`slugify`) — no max-length truncation
- `scripts/little_loops/issue_template.py:86` (`assemble_issue_markdown`) — existing "type-dir template + frontmatter + body" assembler; frontmatter is hand-built via a `key: value` string loop, not `yaml.dump`/`update_frontmatter`, so list/dict frontmatter values are stringified naively
- `scripts/little_loops/frontmatter.py:439` (`update_frontmatter`) — supports `update_frontmatter("", {...})` to build fresh YAML frontmatter correctly (verified by execution, **D2**), but no existing caller uses it that way today; every caller splices into existing content. Note the adjacent trap: splicing into an *empty* `---\n---` block corrupts the output, so `create_issue()` must build the block standalone and concatenate
- `hooks/scripts/check-duplicate-issue-id.sh` (PreToolUse) / `check-duplicate-issue-id-post.sh` (PostToolUse) — the only live duplicate-ID collision safety today; both fire only on the Claude `Write` tool path. A pure-Python `create_issue()` invoked from `ll-issues create` bypasses these hooks entirely and needs its own collision handling — no `while path.exists(): n += 1` retry loop exists anywhere in the codebase today

_Wiring pass added by `/ll:wire-issue`:_
- `skills/scope-epic/SKILL.md:286,295,326,336,361` — actual call sites of `ll-issues next-id` that Implementation Step 3 ("Slim scope-epic Phases 4–6") must replace with `ll-issues scaffold-epic` [Agent 2 finding]
- `skills/capture-issue/SKILL.md:225,256,309` — actual call sites of `ll-issues next-id` / `ll-issues sections` that Implementation Step 3 ("Slim capture-issue Phase 4") must replace with `ll-issues create` [Agent 2 finding]
- `scripts/little_loops/cli/issues/next_id.py` — direct thin CLI wrapper around `get_next_issue_number()`; closest existing single-purpose subcommand precedent for how `create`/`scaffold-epic` should be structured as separate modules under `cli/issues/` [Agent 1 finding]
- `scripts/little_loops/cli/issues/__init__.py:110-205` (`main_issues()` epilog, one-subcommand-per-line at lines 111-147) — needs `create`/`scaffold-epic` entries added for consistency with every other subcommand; not test-enforced but is the CLI's own self-documentation [Agent 3 finding]

### Conventions in Force
- Subcommand modules expose `cmd_<name>(config, args) -> int`, with heavy imports deferred inside the function body — evidence: `next_id.py:23`, `link.py:109-110`
- `--json` output goes through the single shared `little_loops.cli.output.print_json()` (`cli/output.py:227-229`), fed a plain dict built either inline or via a dataclass `.to_dict()` — evidence: `normalize.py:105-115` (`NormalizeFinding.to_dict()`), `cli/loop/_scaffold_core.py:36-43` (`ScaffoldResult.to_dict()`)
- Parser registration: the delegated `add_<name>_parser(subs)` style is the convention (17 modules, all modern subcommands); inline wiring in `main_issues()` survives only in three legacy subcommands (`next-id`, `sections`, `path`). **Resolved in D1 — use the delegated style.** Dispatch itself is always a flat `if/elif` chain (`__init__.py:974-1061`), never a dict table
- Every `git add` in the codebase goes through `subprocess.run(["git", "add", "--", *paths], ...)` with an explicit failure path that runs `git reset -- <paths>` to unstage (never content rollback) — evidence: `issue_lifecycle.py:648-671` (`_commit_issue_completion`), which also bans `git add -A` for scoping reasons (comment at `:634-643`)
- No transactional multi-file rollback pattern exists anywhere in the codebase — multi-file writers (`migrate_relationships.py:106-137`, `normalize.py:432-474` `apply_normalize`) write independently, collect errors, and leave already-written files in place on partial failure
- The `parent:` frontmatter field is read/rewritten during ID-reassignment repair (`normalize.py:_REFERENCING_KEYS`, `:27-34`, used by `rewrite_inbound_refs()` at `:393-429`) but no CLI command writes a fresh `parent:` edge at creation time; `ll-issues link` (`link.py`) explicitly does not support `parent`/`epic` fields (`link.py:14`, `_FIELD_FLAGS`)
- No CLI code writes the `## Children` prose section today — only skill prose (`scope-epic/SKILL.md` Phase 5) does this

### Tests
- `scripts/tests/test_ll_issues_normalize.py:32-40` (`normalize_dir` fixture) and `:71-81` (`_invoke()` — patches `sys.argv`, calls `main_issues()` directly, captures stdout) is the closest existing test-harness precedent for `test_ll_issues_create.py`/`test_ll_issues_scaffold_epic.py`
- `scripts/tests/test_migrate_relationships.py:34-51` — sibling pattern, `_make_project()` + `_run_migrate_relationships()`, asserts directly on `frontmatter.parse_frontmatter()` output and filename globs rather than stdout parsing

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py:862-983` (`TestGetNextIssueNumber`) and `:31-62` (slugify tests) — behavior contract `create_issue()`'s collision-retry must not violate; `slugify("")` returns `""`, an edge case `create_issue()` must handle itself since `slugify()` doesn't [Agent 3 finding]
- `scripts/tests/test_issue_template.py:104-201` (`TestAssembleIssueMarkdown`) — covers `variant="minimal"|"full"` and `ValueError` on unknown variant; no existing test exercises EPIC-variant assembly, which `scaffold_epic()` needs [Agent 3 finding]
- `scripts/tests/test_frontmatter.py:400-551` (`update_frontmatter` tests), esp. `test_update_appends_to_existing_list:457` — precedent for the both-direction `parent:`/`## Children` list-append wiring [Agent 3 finding]
- `scripts/tests/test_issue_lifecycle.py:239-306` (`_commit_issue_completion` tests: `test_successful_commit`, `test_nothing_to_commit`, `test_commit_failure`) — behavior contract for `--stage`, though this is a full commit path, heavier than a bare `git add` staging call [Agent 3 finding]
- `scripts/tests/test_git_operations.py:239-299` (`TestSnapshotAndPreserve`) + `scripts/tests/helpers.py:44` (`copy_git_template`) — real-repo-fixture precedent for a `--stage` test; no test in the codebase mocks `subprocess.run(["git","add",...])` directly, so `--stage` should follow this real-repo pattern [Agent 3 finding]
- `scripts/tests/test_git_lock.py:421-479` (`test_second_thread_waits_for_first`, `test_no_deadlock_with_many_threads`) — closest structural pattern (`threading.Event`-sequenced `threading.Thread`s) to model the new concurrent-ID-collision-retry test after; no existing test anywhere simulates two callers racing for the same next-ID [Agent 3 finding]
- `scripts/tests/test_wiring_cli_registry.py:20-156` (`DOC_STRINGS_PRESENT` parametrized list) — new entries needed: `("docs/reference/CLI.md", "ll-issues create", "FEAT-2947")` and `("docs/reference/CLI.md", "ll-issues scaffold-epic", "FEAT-2947")` [Agent 3 finding]
- `scripts/tests/test_scope_epic_skill.py:85-87` (`test_git_staging_referenced`, asserts literal `"git add"` in `SKILL.md`) — **will break** once scope-epic's Phase 6 switches from prose `git add` instructions to `ll-issues scaffold-epic --stage` [Agent 3 finding]
- `scripts/tests/test_scope_epic_skill.py:73-77` (`test_ll_issues_next_id_referenced`) — may break if the slimmed skill drops all mention of `next-id` in favor of `scaffold-epic` [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — currently documents `next-id`, `sections`, `normalize`, `finalize-decomposition`; needs `create`/`scaffold-epic` entries
- `docs/reference/API.md` — needs `create_issue()`/`scaffold_epic()` signatures alongside `issue_template.assemble_issue_markdown()`, `frontmatter.update_frontmatter()`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2138-2140` — the `ll-issues size` section's "Scope note" prose explicitly forward-references this issue by ID ("Phase 6's child-issue creation mechanics... remain in the skill pending `ll-issues create` (FEAT-2947)"); this stale pending-TODO note must be updated once `create` lands [Agent 2 finding]

### Configuration
- `scripts/little_loops/config/core.py:486` (`get_issue_dir`) / `:518` (`get_issue_prefix`) — category→directory/prefix mapping `create_issue()` should read from config rather than restating scope-epic's hardcoded type→dir prose mapping (`SKILL.md` L288-289)

## Program Design

### Types

- `IssueSpec: dataclass`
  - `type: str`
  - `title: str`
  - `priority: str`
  - `body: str | None`
  - `parent: str | None`
  - `labels: list[str]`
  - `stage: bool`
- `CreatedIssue: dataclass`
  - `id: str`
  - `path: Path`
- `ChildSpec: dataclass`
  - `type: str`
  - `title: str`
  - `priority: str`
  - `summary: str`

### Signatures

- `create_issue(spec: IssueSpec, issues_dir: Path) -> CreatedIssue` — under `acquire_lock`: `get_next_issue_number` → `slugify` → `open(path,"x")` with bounded retry (**D3**); body from `assemble_issue_body`, frontmatter from `update_frontmatter("", ...)` (**D2**); parent wiring both directions
- `scaffold_epic(title: str, children: list[ChildSpec], priority: str, stage: bool) -> tuple[CreatedIssue, list[CreatedIssue]]` — composes `create_issue`; assemble-all-then-write with unlink-on-failure (**D5**)
- `assemble_issue_body(sections_data, issue_type, variant, issue_id, title, content=None) -> str` — new, extracted from `assemble_issue_markdown`; sections + heading only, no frontmatter block (**D2**)
- `_stage(paths: list[str], repo_root: Path) -> bool` — `git add -- <paths>`, `git reset -- <paths>` on failure; never `git add -A` (**D4**)

### Call Path

- `create_issue()` -> `get_next_issue_number()` (existing) -> `slugify()` (existing, `issue_parser.py`)
- `create_issue()` -> `update_frontmatter()` (existing, `frontmatter.py`)
- `scaffold_epic()` -> `create_issue()`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `get_next_issue_number(config: BRConfig, category: str | None = None) -> int` — `scripts/little_loops/issue_parser.py:1559`. Pure filesystem scan (union regex over all type prefixes, globs `*.md` per category dir), returns `max+1`; no reservation/lock — calling twice without an intervening write returns the same number.
- `slugify(text: str) -> str` — `scripts/little_loops/issue_parser.py:1545`. `re.sub` strip non-word/space/hyphen chars → collapse runs → strip leading/trailing `-` → lowercase. No max-length truncation.
- `assemble_issue_markdown(sections_data, issue_type, variant, issue_id, title, frontmatter, content=None) -> str` — `scripts/little_loops/issue_template.py:86`. Existing template+frontmatter+body assembler; frontmatter is written via a hand-built `key: value` string loop (not `yaml.dump`), so list/dict frontmatter values stringify naively. **Resolved in D2**: `create_issue()` does not use this function's frontmatter loop at all — the loop is left exactly as-is for its one production caller (`sync.py:735`), and the section-assembly half is extracted to `assemble_issue_body()` for `create_issue()` to compose with `update_frontmatter("", {...})`.
- `resolve_templates_dir(config) -> Path` — `scripts/little_loops/issue_template.py:39`, 4-tier precedence lookup; already the entry point `ll-issues sections` uses.
- `update_frontmatter(content: str, updates: dict) -> str` — `scripts/little_loops/frontmatter.py:439`. `update_frontmatter("", {...})` is a valid from-scratch call path (untested/uncalled that way today) that YAML-serializes correctly, unlike `assemble_issue_markdown`'s frontmatter loop.
- `_alloc()` closure — `scripts/little_loops/cli/issues/normalize.py:277-284` — in-process monotonic counter seeded once from `get_next_issue_number()`; not collision-checked against the filesystem. ~~No retry-on-collision loop exists anywhere in the codebase … must be written from scratch~~ — **corrected, see D3**: `file_utils.acquire_lock` (`file_utils.py:61`) plus the `rn_synth_queue.try_pop_ready` read-select-write-under-one-lock precedent (`rn_synth_queue.py:109-122`) is a direct reuse. The bash-hook coordination point stands: a pure-Python path bypasses `check-duplicate-issue-id*.sh`, which is why `open(path,"x")` is the backstop.
- `_commit_issue_completion()` — `scripts/little_loops/issue_lifecycle.py:648-671` — timeout-guarded, explicit-target `git add` wrapper (`subprocess.run(["git","add","--",*targets], timeout=60)`, unstages via `git reset` on failure). ~~`--stage` should call this~~ — **corrected, see D4**: it commits and takes an `IssueInfo`; copy the idiom, don't call the function.

_Wiring pass added by `/ll:wire-issue`:_
- Concrete failure mode resolving the frontmatter-path disagreement above: `assemble_issue_markdown()`'s `f"{key}: {value}"` loop emits `parent: None` (Python `None`'s string form) for a childless `IssueSpec.parent`. `frontmatter.parse_frontmatter()` uses `yaml.BaseLoader`, which does not recognize the bare word `None` as YAML null — only `null`/`~`/empty — so it round-trips as the **live string `"None"`**, not an absent field. `issue_parser.py:1971` (`parent = frontmatter.get("parent")`) returns that string verbatim with no null-coercion, so any `.parent` truthiness check downstream (`cli/issues/clusters.py`, `list_cmd.py`, `search.py`, `skip.py`, `set_status.py`, `prioritize.py`, `finalize_decomposition.py`) would treat a childless issue as parented by literal `"None"`. `update_frontmatter("", {...})` YAML-serializes `None` correctly (omitted/`null`) and avoids this — this is the deciding evidence for that path. [Agent 2 finding]

## Impact

- **Priority**: P2 - Fills the biggest primitive gap; two ~490-line skills depend on the prose it deletes
- **Effort**: Medium - `create` simple; scaffold-epic atomicity needs care
- **Risk**: Medium - Write path with staging; mitigated by collision-retry tests + `epic-consistency`/`format-check` gates on output

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues create` never produces a colliding ID under concurrent calls (threaded test proves two racers get distinct IDs; `open(path,"x")` backstop tested by pre-creating the target)
- [ ] `create --parent EPIC-N` writes `parent:` as YAML (never the literal string `None` for an unset parent) and the created file round-trips through `parse_frontmatter` to the exact input dict
- [ ] `assemble_issue_markdown()` output is byte-identical before and after the `assemble_issue_body()` extraction (existing `test_issue_template.py` suite passes unmodified)
- [ ] `scaffold-epic` leaves zero files behind when a mid-write failure is injected (unlink-on-failure), and stages all paths in one `git add` on success
- [ ] `scaffold-epic` output passes `ll-issues epic-consistency` and `format-check`
- [ ] scope-epic and capture-issue contain no ID/slug/filename templating prose
- [ ] pytest coverage in `scripts/tests/`

## Notes

~~Split `scaffold-epic` out if atomic-staging/rollback semantics get involved~~ — superseded by **D5**: every file `scaffold_epic()` writes is one it just created, so `unlink()` is a complete undo and no transactional-rollback machinery is needed. Both commands ship together. `create` alone remains independently shippable if step 3 must be dropped.

## Related Key Documentation

- `.claude/CLAUDE.md` — adds `ll-issues create`/`scaffold-epic` to the documented `ll-issues` CLI catalog and directly touches the issue file format (frontmatter, template body, `parent`/`## Children` wiring) rules this doc defines.
- `docs/reference/API.md` — new `create_issue`/`scaffold_epic` functions belong alongside the documented `cli/*` entry points and `issue_parser`/`frontmatter` module reference.


## Confidence Check Notes

_Re-scored by `/ll:confidence-check` on 2026-08-09 after the Resolved Design Decisions (D1–D5) landed._

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

Superseding the earlier 85/63 pass. What changed, and why each prior risk factor no longer applies:

- **Ambiguity 18 → 25.** The two open design decisions (parser registration; frontmatter serialization) are resolved in **D1**/**D2** with codebase evidence, and D3–D5 close the three remaining judgment calls. No `TBD`/either-or/`pick one` language remains in the issue.
- **Complexity 10 → 14 (Depth 5 → 9).** The "collision-retry and atomic staging have no precedent" premise was false. `file_utils.acquire_lock` (`file_utils.py:61`) + `rn_synth_queue.try_pop_ready` (`rn_synth_queue.py:109-122`) is a direct precedent for allocate-under-lock (**D3**), and `scaffold-epic`'s rollback is `unlink()` on files it just created, not transactional rewind (**D5**). Typical per-site change is now Local, not Moderate.
- **Change surface 10 → 18.** The 7 downstream `.parent`-truthiness call sites are out of scope entirely under **D2** — `assemble_issue_markdown` is not modified, so nothing downstream of it changes. Verified independently: no `"None"`-string special-casing exists in `cli/issues/*.py` or `issue_parser.py`, and zero issue files on disk carry `parent: None`. Real dependents are three: `sync.py:735`, scope-epic, capture-issue.
- **Test coverage 25 unchanged** — every modified module has an existing test file.
- **New risk surfaced and pre-empted**: the obvious composition (`assemble_issue_markdown(frontmatter={})` then `update_frontmatter`) silently destroys the frontmatter. Caught by executing it, documented in **D2**, and now a required implementation step (the `assemble_issue_body()` extraction) rather than a bug waiting to be found mid-implementation.

### Gaps to Address
- `format-check` still reports `stale_cli_flag` for `ll-issues create` / `scaffold-epic` / `scaffold-epic --stage`. This is unavoidable and expected — they are the subcommands this issue creates. Per the ENH-3047 parity/claim rule this caps Criterion 4 at 10/20, which is the entire gap between the 90 readiness score and 100. No action possible before implementation. (`missing_behavior_parity` and `testable` were real gaps and are now cleared.)

## Session Log
- `/ll:confidence-check` - 2026-08-09T20:33:46 - `20730683-2565-4a26-b2cc-54e8c3853f7b.jsonl`
- `/ll:confidence-check` - 2026-08-09T20:20:01 - `5613d883-5d20-43a9-b2d2-17dd9f34e4f5.jsonl`
- `/ll:verify-issues` - 2026-08-09T20:17:48 - `72353bae-7ae9-4e82-b2a6-bcec5fa1628e.jsonl`
- `/ll:wire-issue` - 2026-08-09T20:15:17 - `705db7a6-e1f0-464f-8848-38cff0e4593e.jsonl`
- `/ll:refine-issue` - 2026-08-09T20:07:23 - `32521b66-f99f-445d-87f7-1a027f6ea6c9.jsonl`
