---
id: ENH-3115
title: Document what does and does not cross into an auto-created worktree
type: ENH
priority: P4
status: done
parent: EPIC-3111
testable: false
program_design_not_applicable: true
captured_at: '2026-08-08T20:32:03Z'
completed_at: '2026-08-10T05:45:40Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
labels:
- worktree
- documentation
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3115: Document what does and does not cross into an auto-created worktree

## Summary

No documentation states which files an auto-created worktree inherits. Answering
"does my `.env` / `.ll/` / `history.db` reach the worktree?" currently requires
reading `worktree_utils.setup_worktree`, three call sites, the
`worktree_copy_files` default in `config/automation.py`, and the `.ll/` rules in
`.gitignore`. This documentation should state the contract in one place.

## Current Behavior

The behavior is spread across:
- `scripts/little_loops/worktree_utils.py:157-269` — git identity, `.claude/`
  `copytree`, `copy_files` loop, session marker
- `scripts/little_loops/config/automation.py:131` — the default
  `[".claude/settings.local.json", ".env"]`
- `scripts/little_loops/config-schema.json:360` — one-line schema description
- `.gitignore:99-147` — which `.ll/` content is tracked (and so arrives via
  checkout) versus ignored (and so does not)
- `worktree_utils.py:445` — the verify gate's `copy_files=[]` exception

`docs/reference/CLI.md` documents `--worktree` as a flag but not its file
semantics.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- Sibling status as of this pass: `ll-issues show BUG-3112/ENH-3113/ENH-3114 --json` now report all three as `Completed`, confirmed directly in source at HEAD (not just issue status) — the crossing-table contract this issue documents is no longer hypothetical.
- `setup_worktree()` (`scripts/little_loops/worktree_utils.py:157-279`) current step order, post-landing: mutual-exclusion guard (195-196); `LL_HISTORY_DB` export via `os.environ.setdefault(...)` (198-206, BUG-3112); stale-path cleanup (208-211); `base_branch` verify (213-220); `git worktree add` (222-235); git identity copy (238-244); `.claude/` copytree — unconditional `rmtree`-then-`copytree`, replace semantics (247-253); `copy_files` loop (256-271) — now branches on `src.is_dir()`, using `shutil.copytree(src, dest, dirs_exist_ok=True)` (merge semantics, distinct from the `.claude/` block's replace semantics) for directories (ENH-3114) and `shutil.copy2` for files; missing `src` is a silent `logger.debug` skip; session marker `.ll-session-<pid>` (276-279).
- BUG-3112 landed via the env-injection option (not copy-based): no `LL_HISTORY_DB` setter exists in `fsm/executor.py`, `cli/loop/run.py`, or `parallel/worker_pool.py` — all four `setup_worktree()` callers (`fsm/executor.py:942`, `cli/loop/run.py:484`, `parallel/worker_pool.py:774`, `worktree_utils.py:450` verify-gate) inherit the export transitively. Readers: `session_store/db.py:96` (`_resolve_db_path`, env takes precedence), `hooks/session_start.py`, `hooks/post_commit.py:95`, `pytest_history_plugin.py:45`. No worktree-local `history.db*` is ever created; documented today at `docs/reference/HOST_COMPATIBILITY.md:409`.
- ENH-3113 landed via the default-list option (not a hardcoded copy step): `worktree_copy_files` default is now `[".claude/settings.local.json", ".env", ".ll/ll.local.md"]` in three mirrored locations — `scripts/little_loops/config/automation.py:91-93` and `:130-132`, `scripts/little_loops/parallel/types.py:416-418`. `.ll/ll.local.md` flows through the same generic `copy_files` file branch as `.env`, not a special case.
- ENH-3114 landed: the old `logger.warning`-and-skip directory branch is gone; directories now copy via `shutil.copytree(dirs_exist_ok=True)` as described above.
- `config-schema.json:360-367`'s `worktree_copy_files` description was updated in the same landing to state both the directory-recursion behavior and the `.ll/ll.local.md` default entry — this schema description is the only place in the codebase where the corrected contract is currently written down; no `docs/reference/*.md` file exists yet (confirmed via glob — 12 files in `docs/reference/`, none worktree-named, none mention worktree copy semantics as a topic). `docs/reference/CLI.md`'s `--worktree` row (line 601) still has no cross-link. This issue's deliverable is still fully outstanding — only the ground truth it needs to describe has stabilized.
- Verify-gate exception line drifted: `worktree_utils.py:445` cited in the original issue body is now `:450-458` (`verify_epic_branch_before_merge`), after the two sibling fixes landed above it in the same function. Still gets `LL_HISTORY_DB` (step 2 is unconditional, not gated on `copy_files`) and `.claude/`, but no `.env`/`settings.local.json`/`.ll/ll.local.md` (`copy_files=[]`).
- Current `.ll/` tracked-vs-ignored split re-verified at `.gitignore:98-147` (unchanged shape from the prior pass, individually-listed ignore patterns confirmed present); `.ll/ll.local.md` is not gitignored by a matching pattern in *this* repo's own `.gitignore` in that range — it is treated as gitignored-by-default in ENH-3113/BUG-3123's own issue text as a general per-project convention, not a rule visible in this repo's `.gitignore`. Verify per-project when the doc is written.

## Expected Behavior

A single documented reference answers, for each category, whether it crosses:

| Category | Crosses? | Mechanism |
|---|---|---|
| Tracked files | Yes | `git worktree add` checkout |
| `.claude/` (including gitignored contents) | Yes | wholesale `copytree` |
| git `user.name` / `user.email` | Yes | copied via `git config` |
| `worktree_copy_files` entries (`.env`, `settings.local.json` by default) | Yes, files only | `shutil.copy2` |
| Tracked `.ll/` content (`ll-config.json`, `decisions.d/`, `learning-tests/`) | Yes | checkout, because repo-root `.ll/` is tracked |
| Gitignored `.ll/` state (`ll.local.md`, `history.db`, `queue.db`, locks) | No | not copied |
| Other untracked/gitignored files outside `.claude/` | No | not copied |

Plus the exceptions: the verify-gate worktree passes `copy_files=[]`, so it gets
`.claude/` but no `.env`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- Corrections needed to the crossing table above, now that BUG-3112/ENH-3113/ENH-3114 have landed (the table above still reflects the pre-landing/hypothetical contract):
  - `worktree_copy_files` entries row: "Yes, files only" is stale — ENH-3114 landed directory support via `shutil.copytree(src, dest, dirs_exist_ok=True)` (`worktree_utils.py:256-271`). Correct value: "Yes, files and directories (directories merge into an existing destination; files use `copy2`)."
  - Tracked `.ll/` content row and default-entries note: the `worktree_copy_files` default is now a 3-entry list — `[".claude/settings.local.json", ".env", ".ll/ll.local.md"]` (`config/automation.py:91-93`, `:130-132`; `parallel/types.py:416-418`) — so `.ll/ll.local.md` moves from "Gitignored `.ll/` state ... No, not copied" to its own row: "Yes, via `worktree_copy_files` default" (mechanism: generic `copy_files` file branch, same as `.env`, not a special case).
  - Gitignored `.ll/` state row (`history.db`, `queue.db`, locks): still correct that these are not *copied*, but needs a caveat for `history.db` specifically — BUG-3112 landed via `os.environ.setdefault("LL_HISTORY_DB", str(resolve_history_db()))` (`worktree_utils.py:198-206`), so worktree-scoped processes read/write the main repo's shared `history.db` by reference, not an isolated copy and not simply absent. `queue.db*` and `*.lock` remain deliberately excluded with no analogous env-sharing mechanism.
- These corrections are also documented at `config-schema.json:360-367`, which already carries the post-landing prose for the `.ll/ll.local.md` and directory-recursion changes (the only place in the codebase where the corrected contract exists in writing today — see Current Behavior findings above for the full detail and remaining doc gap).

## Motivation

This is the question a user actually asks before trusting an autonomous
worktree run, and the answer is currently only derivable by reading source. The
documentation is also the natural place to record the *reasoning* behind the
sibling issues — why `history.db` is shared rather than copied (BUG-3112), and
which machine-local `.ll/` files deliberately do or don't follow a worktree
(ENH-3113).

## Proposed Solution

Add a worktree copy-semantics section to the docs — either a new
`docs/reference/WORKTREES.md` or a section in an existing reference doc,
whichever fits the current docs layout. Cross-link from:
- `docs/reference/CLI.md` at `ll-loop run --worktree`
- `config-schema.json:360`'s description (pointer only)

Write it **after** BUG-3112, ENH-3113, and ENH-3114 land, so it documents the
final contract rather than the current one.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Sibling status as of this pass: BUG-3112, ENH-3113, and ENH-3114 are all still `open` — none has landed, so the final contract is not yet confirmed and this issue's Implementation Step 1 ("Confirm the final behavior once the sibling issues are resolved") remains blocking.
- Per-sibling post-fix implication for the crossing table this issue will write (from `codebase-analyzer`, cross-referencing each sibling issue's own Proposed Solution):
  - **BUG-3112** (preferred option): worktree-scoped processes get `LL_HISTORY_DB=<main repo>/.ll/history.db` injected at the three creation call sites (`fsm/executor.py:942`, `cli/loop/run.py:484`, `parallel/worker_pool.py:774`), so the worktree reads/writes the main repo's shared DB instead of an isolated one. The table's "Gitignored `.ll/` state ... No, not copied" row will need a caveat: `history.db` becomes "shared by reference via `LL_HISTORY_DB`," not simply absent. Whether the verify-gate worktree (`copy_files=[]` at `worktree_utils.py:445`) shares or stays isolated is explicitly still an open decision inside BUG-3112 itself.
  - **ENH-3113**: one of two options — either extend `parallel.worktree_copy_files`'s default to include `.ll/ll.local.md`, or have `setup_worktree` copy an explicit gitignored-`.ll/` allowlist unconditionally alongside the `.claude/` copytree. Either way, `history.db*`, `queue.db*`, and `*.lock` files stay deliberately excluded. Once landed, `ll.local.md` moves from "No" to "Yes, copied" in the table.
  - **ENH-3114**: preferred option branches `copy_files` handling on `src.is_dir()` and calls `shutil.copytree(src, dest, dirs_exist_ok=True)`, mirroring the existing `.claude/` treatment; the alternative is validate-and-reject at config load. The table's "`worktree_copy_files` entries ... Yes, files only" row becomes either "Yes, files and directories" or gets an explicit validation-rejection note, depending which option is chosen.
- Doc location precedent (from `codebase-pattern-finder`): the closest size/shape match for a new standalone file is `docs/reference/DEFERRAL_CODES.md` (32 lines: `# Title` → one pipe-table → `## Related`). The closest match for the specific "what crosses / what doesn't" table shape is `docs/reference/HOST_COMPATIBILITY.md`'s capability tables, though its axis is host rather than file category — today the "what crosses" rule lives only as inline prose in `config-schema.json`'s `worktree_copy_files` description, not in any docs/reference table.
- Cross-link target confirmed precise: `docs/reference/CLI.md:601`, a row inside the `--worktree` flag table under H4 `#### \`ll-loop run <loop>\` / \`ll-loop r <loop>\`` (line 572) — no anchor exists for the flag alone, so the link is `CLI.md#ll-loop-run-loop--ll-loop-r-loop`. Verify this anchor manually against the live heading slug before publishing: `ll-check-links` does not validate internal `.md#anchor` resolution (see Integration Map findings), so a wrong slug will not be caught by tooling.
- A `config-schema.json` "see docs/reference/X.md" pointer at the `worktree_copy_files` description (~line 358, not 360) would be a new convention for that file — no existing property description in `config-schema.json` links out to a prose doc today.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- Sibling blocker cleared: BUG-3112, ENH-3113, and ENH-3114 are all landed on `main` (confirmed in source, not just issue status — see Current Behavior findings). The "write it after the siblings land" precondition in this section is now satisfied; Implementation Step 1 no longer blocks Step 3's table write.
- Doc-location precedent, re-confirmed at HEAD: no `docs/reference/WORKTREES.md` or similarly-named file exists yet (glob of `docs/reference/*.md` returns 12 files, none worktree-named); no doc anywhere mentions worktree copy semantics as a dedicated topic. `docs/reference/DEFERRAL_CODES.md` (31 lines: `# Title` → prose context with a pointer to the mechanism doc doesn't re-explain → one `## Codes` pipe-table → `## Related` bullet list of bare file/command paths) remains the closest size/shape precedent for a new standalone file. `docs/reference/HOST_COMPATIBILITY.md` is the closest precedent for the "crosses/doesn't cross" table shape specifically, though its axis is host, not file category, and it is far larger (485 lines) with footnote-heavy freshness markers (`> **Last Updated:**`) — not a proportionate model for a doc this small.
- Cross-reference syntax convention (from pattern-finder): same-directory reference-to-reference links are relative bare filenames with a `#`-anchor GitHub-slug of the literal heading text, e.g. `[CONFIGURATION.md](CONFIGURATION.md#parallel)`; links out to `docs/guides/` use `../`. No explicit `{#id}` anchors are used anywhere in `docs/reference/`.
- `docs/reference/HOST_COMPATIBILITY.md:409` already carries an `LL_HISTORY_DB` env-var table row documenting BUG-3112's worktree-inheritance behavior — the new doc's `history.db` row should cross-reference that existing row rather than duplicate its content.
- `scripts/little_loops/link_checker.py`'s `is_internal_reference()`/`check_markdown_links()` route any `.md`/`#`/relative-path match straight to `status="internal"` and do not verify the anchor resolves — a wrong slug on the `CLI.md#ll-loop-run-loop--ll-loop-r-loop` cross-link will not be caught by `ll-check-links` or `/ll:audit-docs` (an LLM audit, not a mechanical anchor checker). Verify the anchor manually against the live heading slug before publishing.
- No existing precedent for a "see docs/reference/X.md" pointer *inside* a `config-schema.json` property description (grep for `docs/`/`CLI.md`/`CONFIGURATION.md` in that file returns zero matches) — the schema-description pointer this section proposes would be a new convention for that file, not a continuation of one.
- Doc-content regression coverage precedent: `scripts/tests/test_wiring_reference_docs.py` holds a flat `DOC_STRINGS_PRESENT: list[tuple[str, str, str]]` list asserting expected strings appear in doc files, and a parallel `DOC_FILES_MUST_EXIST` list for file-existence — the established mechanism for giving a new doc file regression coverage, rather than a bespoke test module. No existing entry references a worktree-named doc.

## Implementation Steps

1. Confirm the final behavior once the sibling issues are resolved.
   > ⚠ Superseded — siblings landed; use confirmed contract in Codebase Research Findings below
2. Choose the documentation location (new reference file vs. existing section).
3. Write the crossing table, the exceptions (verify gate), and the rationale for
   share-vs-copy of `history.db`.
4. Cross-link from `docs/reference/CLI.md` and run `/ll:audit-docs`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Step 1 ("confirm final behavior") is verifiably blocked right now: `ll-issues show BUG-3112/ENH-3113/ENH-3114 --json` all report `status: open` as of this pass — re-check status before starting Step 3's table write.
- Step 3 ("write the crossing table") ground truth to draw from (see Integration Map / Proposed Solution findings above for full detail): the exact `setup_worktree()` step order and line numbers (`worktree_utils.py:157-269`), the verify-gate exception (`worktree_utils.py:445`, `copy_files=[]`), the full tracked-vs-ignored `.ll/` file list (`.gitignore:99-147`), and each sibling's post-fix table-row delta.
- Step 4 ("cross-link from CLI.md") target anchor confirmed: `docs/reference/CLI.md:601` inside the `--worktree` row of the flag table under H4 `#### \`ll-loop run <loop>\` / \`ll-loop r <loop>\`` — link as `CLI.md#ll-loop-run-loop--ll-loop-r-loop`. `ll-check-links` does not validate internal anchor resolution, so confirm the slug manually against the live heading before running `/ll:audit-docs`.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- Step 1 is now resolved, not blocking: BUG-3112, ENH-3113, and ENH-3114 are all confirmed landed on `main` at HEAD (verified in source, not just issue status). The final contract is: `worktree_copy_files` default is `[".claude/settings.local.json", ".env", ".ll/ll.local.md"]`; `copy_files` entries support directories via `copytree(dirs_exist_ok=True)`; `history.db` is shared by reference via `LL_HISTORY_DB` env-var injection, not copied or isolated. See Current Behavior and Expected Behavior findings above for full detail and exact anchors.
- Step 3's crossing table should draw on the corrections filed under Expected Behavior above (directories now supported, `.ll/ll.local.md` now crosses, `history.db` caveat) rather than the table as originally written.
- Step 4's cross-link target remains `docs/reference/CLI.md:601` (`CLI.md#ll-loop-run-loop--ll-loop-r-loop`) — unchanged by the sibling landings; still unverified mechanically (see Proposed Solution findings on `ll-check-links` not validating internal anchors).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add regression coverage in `scripts/tests/test_wiring_reference_docs.py` (`DOC_FILES_MUST_EXIST` + `DOC_STRINGS_PRESENT`) for the new doc file's existence and key content
- Add a regression entry in `scripts/tests/test_wiring_cli_registry.py` for the new `--worktree` cross-link text added to `docs/reference/CLI.md`
- Cross-link (or reconcile) `docs/development/TROUBLESHOOTING.md`'s `### Worktree not inheriting settings` section, which already states the current copy contract, with the new doc
- Optionally add a "see docs/reference/WORKTREES.md" pointer to `docs/reference/CONFIGURATION.md`'s `worktree_copy_files` row and/or `docs/reference/API.md`'s `worktree_copy_files`/`worktree_utils` entries

## Integration Map

### Files to Modify
- `docs/reference/` — new or extended worktree reference
- `docs/reference/CLI.md` — cross-link at `--worktree`

### Dependent Files (Callers/Importers)
- N/A — documentation only

### Tests
- N/A — documentation only; existing link/anchor checks apply
  > ⚠ Superseded — two concrete test mechanisms apply; see wiring findings below

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_reference_docs.py` — append `("docs/reference/WORKTREES.md", "ENH-3115")` to `DOC_FILES_MUST_EXIST` (list[tuple[str, str]], line 246) and one or more `(doc_path, expected_string, "ENH-3115")` tuples to `DOC_STRINGS_PRESENT` (line 20) asserting key new-doc content (e.g. `.ll/ll.local.md`, `LL_HISTORY_DB`). Pattern to copy: `("docs/reference/API.md", "update_frontmatter", "FEAT-1172")` [Agent 3 finding]
- `scripts/tests/test_wiring_cli_registry.py` — this file, not `test_wiring_reference_docs.py`, owns regression coverage for `docs/reference/CLI.md` content specifically (all entries have `"docs/reference/CLI.md"` as the doc path). No existing entry references `--worktree`/"worktree". Since this issue's Step 4 edits `CLI.md`'s `--worktree` row, add a `("docs/reference/CLI.md", "<cross-link text>", "ENH-3115")` tuple here for the cross-link addition [Agent 3 finding]

### Documentation
- This issue is the documentation change

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md` — `### Worktree not inheriting settings` section already states "Both are copied automatically via the default `worktree_copy_files` list (`[".claude/settings.local.json", ".env", ".ll/ll.local.md"]`)" — the most directly overlapping existing content; cross-link both directions so the two don't drift [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `worktree_copy_files` row under `### parallel` is a one-line description with no pointer to the fuller semantics (directories, `.claude/` copytree, `LL_HISTORY_DB`); add a "see docs/reference/WORKTREES.md" pointer [Agent 2 finding]
- `docs/reference/API.md` — `ParallelConfig` dataclass field listing and **Fields** bullet for `worktree_copy_files`, plus the `little_loops.worktree_utils` module-table row; candidate for a pointer to the new doc for behavioral semantics vs. API signatures [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- `scripts/little_loops/worktree_utils.py` `setup_worktree()` (157-269) — exact step order confirmed:
  1. stale-path cleanup (198-201) via `cleanup_worktree()`
  2. `base_branch` verify (203-210)
  3. `git worktree add` (212-225)
  4. git identity copy: `user.email`/`user.name` read from `repo_path`, set in `worktree_path` (227-234)
  5. `.claude/` wholesale `copytree` — unconditional, includes gitignored contents e.g. `settings.local.json` (236-243)
  6. `copy_files` loop (245-262): skips `.claude/`-prefixed entries (already covered by step 5); skips missing `src` with a debug log; **skips directories with only a `logger.warning`** (251-256, the exact gap ENH-3114 targets); otherwise `shutil.copy2` (257-259)
  7. session marker `.ll-session-<pid>` written (266-269)
- Verify-gate exception confirmed at `worktree_utils.py:445` — the merge-verify-gate helper calls `setup_worktree(..., copy_files=[], checkout_existing=True)`, so that worktree gets `.claude/` + git identity but no `.env`/`settings.local.json`. Same helper injects `LL_VERIFY_GATE=1` into the subprocess env (see `worktree_utils.py:458-461`) — the precedent BUG-3112 proposes reusing for an `LL_HISTORY_DB` override.
- `scripts/little_loops/config/automation.py:130-132` — confirmed config key is `parallel.worktree_copy_files` (nested under `AutomationConfig.from_dict`), default `[".claude/settings.local.json", ".env"]`.
- `scripts/little_loops/config-schema.json` `worktree_copy_files` property (~line 358, not 360) — description states `.claude/` is always auto-copied but does not state the files-only constraint (the ENH-3114 gap).
- `.gitignore:99-147` full tracked/ignored `.ll/` split (confirmed via `git ls-files .ll` + gitignore rules):
  - **Tracked** (crosses via ordinary `git worktree add` checkout, no special-case code needed): `.ll/decisions.yaml`, `.ll/decisions.d/*.json`, `.ll/ll-config.json`, `.ll/ll-goals.md`, `.ll/learning-tests/**`, `.ll/private-refs-baseline.json`, `.ll/program-design-cutover.json`, `.ll/spikes/*.md` — enabled by the `!/.ll/` un-ignore rule.
  - **Ignored** (does not cross): `.ll/*.lock`, `.ll/ll-context-state.json`, `.ll/ll-sync-state.json`, `.ll/history.db*`, `.ll/queue.db*`, `.ll/ll-update-docs.watermark`, `.ll/ll-continue-prompt.md`, `.ll/ll-context-handoff-needed`, `.ll/loop-suggestions/`, `.ll/workflow-analysis/`, `.ll/user-messages-*.jsonl`, `.ll/export*.jsonl`, `.ll/stray-quarantine-*/`, `.ll/private-refs.local.txt`, `.ll/ll.local.md`; nested `.ll/` dirs at any depth are ignored via `**/.ll/` (137-138).

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- `scripts/little_loops/worktree_utils.py` `setup_worktree()` is now 157-279 (line drift from sibling landings): mutual-exclusion guard (195-196), `LL_HISTORY_DB` `setdefault` export (198-206, BUG-3112), stale-path cleanup (208-211), `base_branch` verify (213-220), `git worktree add` (222-235), git identity copy (238-244), `.claude/` copytree — replace semantics (247-253), `copy_files` loop with file/directory branch (256-271, ENH-3114's `copytree(dirs_exist_ok=True)` merge semantics), session marker (276-279). Verify-gate exception (`verify_epic_branch_before_merge`, `copy_files=[]`) is now at 380-462, call at 450-458 — line numbers cited in the original Integration Map (`:157-269`, `:445`) are stale by this drift.
- `scripts/little_loops/config/automation.py:91-93` and `:130-132` — `worktree_copy_files` default now 3 entries (`.ll/ll.local.md` added, ENH-3113).
- `scripts/little_loops/parallel/types.py:416-418` — second independent mirror of the same default, used when `ParallelConfig` is constructed directly bypassing `config/core.py`. Not previously listed in this Integration Map.
- `scripts/little_loops/config-schema.json:360-367` — `worktree_copy_files` description already updated post-landing with directory-recursion and `.ll/ll.local.md` prose; this is the only place in the codebase where the corrected contract exists in writing today, and the natural source to draw the doc's language from.
- `docs/reference/HOST_COMPATIBILITY.md:409` — existing `LL_HISTORY_DB` env-var table row documents BUG-3112's worktree-inheritance behavior already; the new doc should cross-reference this row for the `history.db` case rather than duplicate it. Not previously listed as a Documentation dependency.
- Doc-content regression coverage: `scripts/tests/test_wiring_reference_docs.py`'s `DOC_STRINGS_PRESENT`/`DOC_FILES_MUST_EXIST` tuple lists are the established mechanism for giving a new doc file test coverage — add an entry here rather than a bespoke test module. Supersedes the original Tests row's "N/A — documentation only."

### Conventions in Force
- Comparable short standalone reference docs (`docs/reference/DEFERRAL_CODES.md`, 32 lines) use `# Title` → one enumerable-state pipe-table (`## Codes`) → `## Related` bullet list of file paths — the closest size/shape precedent for a new `WORKTREES.md`.
- `docs/reference/HOST_COMPATIBILITY.md` is the closest precedent specifically for a "crosses/doesn't cross per category" table shape (`## Adapter Host Capabilities`, `## Environment variables`), though its axis is host, not worktree file category.
- Cross-reference syntax: same-directory reference-to-reference links are relative bare filenames with a `#`-anchor, e.g. `[CONFIGURATION.md](CONFIGURATION.md#parallel)` (`docs/reference/CLI.md:430`); links from `docs/reference/` out to `docs/guides/` or repo-root use `../`. Anchors are the GitHub-slug of the literal heading text.
- `--worktree` (the `ll-loop run` flag this issue is about) is documented at `docs/reference/CLI.md:601`, a row inside the flag table under H4 `#### \`ll-loop run <loop>\` / \`ll-loop r <loop>\`` (line 572) — no separate anchor exists for the flag itself, so the correct cross-link target is `CLI.md#ll-loop-run-loop--ll-loop-r-loop`. (Note: `--worktree-base`/`--cleanup`/`--clean-start` at CLI.md:400-428 are a *different* `ll-parallel` surface, not this flag.)
- `scripts/little_loops/link_checker.py` (`ll-check-links`) does NOT validate that internal `FILE.md#anchor` references resolve to a real heading — `is_internal_reference()`/`check_markdown_links()` route any `.md`/`#`/relative-path match straight to `status="internal"` and skip it; only bare external URLs get a reachability check. `/ll:audit-docs` is an LLM-driven audit, not a mechanical anchor checker either. So an added cross-link's anchor correctness is not automatically enforced — verify it manually against the target heading's actual GitHub slug.
- No existing precedent for a "see docs/reference/X.md" pointer *inside* `config-schema.json` descriptions (grep for `docs/`/`CLI.md`/`CONFIGURATION.md` in that file returns zero matches) — this issue's proposed pointer at the `worktree_copy_files` description would be a new convention for that file, not a continuation of one. The reverse direction (prose docs linking to config-schema-backed keys, e.g. `CONFIGURATION.md#code_query`) is well established.

## Impact

- **Priority**: P4 - Discoverability; no functional defect
- **Effort**: Small - One reference section
- **Risk**: Low - Documentation only
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:manage-issue` - 2026-08-10T05:45:23 - `fed51a0b-5183-4442-a231-235274a67a35.jsonl`
- `/ll:ready-issue` - 2026-08-10T05:21:22 - `d16dd69d-e71f-447d-b5fe-81a3509e19f4.jsonl`
- `/ll:confidence-check` - 2026-08-10T05:19:24 - `a32a61c1-016c-46e5-a117-eb8fd9ed80db.jsonl`
- `/ll:verify-issues` - 2026-08-10T05:16:48 - `c2bd18ef-6f46-433e-9b15-1191f3563213.jsonl`
- `/ll:wire-issue` - 2026-08-10T05:15:17 - `957ac768-f6bb-40bf-82a4-d5b8cd650297.jsonl`
- `/ll:refine-issue` - 2026-08-10T05:10:19 - `7a6c49f8-6baa-41a5-a12f-06efb1801534.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:01:17 - `605ffe70-3699-4408-99fb-492dcea91832.jsonl`
- `/ll:capture-issue` - 2026-08-08T20:35:50 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`

---

## Status

**Open** | Created: 2026-08-08 | Priority: P4
