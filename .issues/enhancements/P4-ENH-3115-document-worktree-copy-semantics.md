---
id: ENH-3115
title: Document what does and does not cross into an auto-created worktree
type: ENH
priority: P4
status: open
parent: EPIC-3111
testable: false
program_design_not_applicable: true
captured_at: '2026-08-08T20:32:03Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
labels:
- worktree
- documentation
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

## Implementation Steps

1. Confirm the final behavior once the sibling issues are resolved.
2. Choose the documentation location (new reference file vs. existing section).
3. Write the crossing table, the exceptions (verify gate), and the rationale for
   share-vs-copy of `history.db`.
4. Cross-link from `docs/reference/CLI.md` and run `/ll:audit-docs`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Step 1 ("confirm final behavior") is verifiably blocked right now: `ll-issues show BUG-3112/ENH-3113/ENH-3114 --json` all report `status: open` as of this pass — re-check status before starting Step 3's table write.
- Step 3 ("write the crossing table") ground truth to draw from (see Integration Map / Proposed Solution findings above for full detail): the exact `setup_worktree()` step order and line numbers (`worktree_utils.py:157-269`), the verify-gate exception (`worktree_utils.py:445`, `copy_files=[]`), the full tracked-vs-ignored `.ll/` file list (`.gitignore:99-147`), and each sibling's post-fix table-row delta.
- Step 4 ("cross-link from CLI.md") target anchor confirmed: `docs/reference/CLI.md:601` inside the `--worktree` row of the flag table under H4 `#### \`ll-loop run <loop>\` / \`ll-loop r <loop>\`` — link as `CLI.md#ll-loop-run-loop--ll-loop-r-loop`. `ll-check-links` does not validate internal anchor resolution, so confirm the slug manually against the live heading before running `/ll:audit-docs`.

## Integration Map

### Files to Modify
- `docs/reference/` — new or extended worktree reference
- `docs/reference/CLI.md` — cross-link at `--worktree`

### Dependent Files (Callers/Importers)
- N/A — documentation only

### Tests
- N/A — documentation only; existing link/anchor checks apply

### Documentation
- This issue is the documentation change

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
- `/ll:refine-issue` - 2026-08-08T21:01:17 - `605ffe70-3699-4408-99fb-492dcea91832.jsonl`
- `/ll:capture-issue` - 2026-08-08T20:35:50 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`

---

## Status

**Open** | Created: 2026-08-08 | Priority: P4
