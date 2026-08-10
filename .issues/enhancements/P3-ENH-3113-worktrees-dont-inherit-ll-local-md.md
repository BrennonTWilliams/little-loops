---
id: ENH-3113
title: Worktrees don't inherit machine-local .ll/ state (ll.local.md overrides and
  Active Rules)
type: ENH
priority: P3
status: done
parent: EPIC-3111
captured_at: '2026-08-08T20:32:03Z'
completed_at: '2026-08-10T04:08:31Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
labels:
- worktree
- config
relates_to:
- BUG-3123
decision_needed: false
confidence_score: 90
verify_verdict: NON_VALID
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# ENH-3113: Worktrees don't inherit machine-local `.ll/` state

## Summary

`.ll/ll.local.md` is gitignored, so it never reaches an auto-created worktree.
A worktree session therefore runs with a different effective configuration than
the main tree — missing local overrides like `project.test_cmd` and
`scan.focus_dirs`, and missing the machine-written `## Active Rules` section
that `ll-issues decisions sync` maintains.

## Current Behavior

`setup_worktree` (`scripts/little_loops/worktree_utils.py:157`) copies `.claude/`
in full and the files named in `parallel.worktree_copy_files` (default
`[".claude/settings.local.json", ".env"]`). Tracked `.ll/` content
(`ll-config.json`, `decisions.yaml`, `decisions.d/`, `learning-tests/`,
`ll-goals.md`) arrives via the git checkout.

Gitignored `.ll/` state does not cross: `ll.local.md` (`.gitignore:53`),
`ll-context-state.json`, `ll-sync-state.json`, `queue.db*`,
`private-refs.local.txt`.

Note the asymmetry: `.claude/settings.local.json` — the Claude Code analogue of
this file — *is* carried across, both by the default `copy_files` entry and by
the wholesale `.claude/` `copytree`. The little-loops equivalent is not.

## Expected Behavior

A worktree session resolves the same effective config as the main tree. If
`.ll/ll.local.md` sets `project.test_cmd`, a run inside the worktree uses that
command.

## Motivation

`ll.local.md` exists precisely to hold per-machine settings that shouldn't be
committed — which makes it exactly the class of file that must be copied rather
than checked out. Silent divergence here means an autonomous worktree run can
execute a *different test command* than the developer's own tree, and can miss
active decision rules the main tree enforces.

## Scope Boundaries

Explicitly out of scope for this issue:

- **`BUG-3123`** (`BRConfig` never reads/merges `.ll/ll.local.md` at all, even
  in the main tree) — a separate, broader defect in the override-resolution
  mechanism itself; this issue is scoped to worktree copy semantics only, not
  to `BRConfig`'s consumption of the file.
- **`.ll/history.db*`** — deliberately not copied; `BUG-3112` (now `done`)
  shares it via the `LL_HISTORY_DB` env var instead of copying.
- **`.ll/queue.db*`** and **`*.lock`** files — shared/live state, not per-tree
  config; copying either into a new worktree is actively wrong.
- **Interactive config UI surfaces** (`skills/configure/areas.md`,
  `scripts/little_loops/init/tui.py`) that independently hardcode their own
  "which files to copy" option lists — whether to also surface
  `.ll/ll.local.md` there is left as an open sub-decision for implementation,
  not resolved by this issue.
- **The migration gap** for projects with an explicit `worktree_copy_files`
  override that would silently drop the new default entry — accepted as a
  bounded, one-line-per-project fix rather than solved with a merge-not-replace
  config mechanism (none exists in this codebase today).

## Proposed Solution

Two candidate approaches, to be decided during implementation:

1. **Extend the `worktree_copy_files` default** to include `.ll/ll.local.md`
   (and consider `.ll/ll-context-state.json`). Smallest change; consistent with
   how `.claude/settings.local.json` is already handled. Requires deciding
   migration behavior for projects with an explicit `worktree_copy_files` that
   overrides the default.
2. **Copy machine-local `.ll/` state unconditionally** in `setup_worktree`,
   alongside the `.claude/` `copytree` — an explicit allowlist of gitignored
   `.ll/` files that should follow a worktree.

Deliberately excluded either way: `history.db*` (BUG-3112 shares rather than
copies), `queue.db*` (shared queue state, not per-tree config), and `*.lock`
(copying a lock file into a new tree is actively wrong).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

> **Selected:** Option A — config-driven default-list extension matches the only established pattern for adding single files, and avoids Option B's leak of `.ll/ll.local.md` into the verify-only worktree.

**Option A**: Extend the default `worktree_copy_files` list (`config/automation.py:91-93` and `:130-132`) to include `.ll/ll.local.md`. Matches the established convention that all three real `setup_worktree` call sites (`fsm/executor.py:946`, `cli/loop/run.py:459,488`, `parallel/worker_pool.py:778`) thread `parallel.worktree_copy_files` straight through unmodified — none of them hardcode or append their own allowlist. The fourth call site (`worktree_utils.py:445`, `verify_epic_branch_before_merge`) already passes `copy_files=[]` explicitly and is unaffected by a default-list change. Open sub-decision this option must resolve: projects with an explicit `worktree_copy_files` override in their own config lose the new default entry unless the migration path re-adds it (e.g. documented upgrade note, or a config-schema default that merges rather than replaces).

**Option B**: Copy `.ll/ll.local.md` unconditionally inside `setup_worktree`, alongside the existing unconditional `.claude/` `copytree` (`worktree_utils.py:236-243`), as a small explicit allowlist of gitignored `.ll/` files. Avoids the migration gap in Option A (no config to override), but is the only place in the current codebase where `setup_worktree` itself — rather than its config-driven `copy_files` parameter — decides what gets copied; every other addition to what a worktree receives today goes through the `copy_files` list, so this introduces a second code path for the same kind of decision.

**Recommended**: Option A — for consistency with the codebase's existing convention (Convention 2 in the pattern-finder research: `copy_files` is always config-driven, never hardcoded per-call-site) and because `.claude/settings.local.json`, the closest existing precedent, is handled exactly this way. Option A's migration gap is real but bounded: it only affects projects that already set an explicit `worktree_copy_files` override, and is a one-line addition to fix per project.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **No canonical single source of truth exists yet** for "which gitignored `.ll/` files are worth copying to a worktree." The precedent table in this issue's own prior research is the closest thing on record; ENH-3115 (sibling doc issue) proposes writing this as a documented table for the first time, not consolidating an existing one. The other place `.ll/ll.local.md` appears in an enumerated Python list is `cli/doctor_trim.py:44-51`'s `_MEMORY_CANDIDATES` — a different purpose (memory-file injection), not a worktree-copy allowlist.
- **BUG-3112 status update**: the `.ll/history.db*` precedent row above should be read as landed, not proposed — BUG-3112 is `done` (completed 2026-08-09T14:42:44Z) and its `LL_HISTORY_DB` env-var idiom is now live at `worktree_utils.py:198-206`. This confirms the env-injection pattern as an established, shipped precedent (not merely a plausible alternative) for cases where a file must not be copied — though, as previously noted, `.ll/ll.local.md` is read-only config from the worktree's perspective, so a copy (not an env-pointer) remains what both options here assume.

### Decision Rationale

**Selected: Option A** (extend the default `worktree_copy_files` list).

Two independent codebase-pattern-finder agents evaluated the options against actual usage:

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 1 |
| Simplicity | 3 | 2 |
| Testability | 3 | 2 |
| Risk | 3 | 0 |
| **Total** | **12/12** | **5/12** |

- **Option A evidence**: `setup_worktree`'s only hardcoded copy is the `.claude/` directory `copytree` (`worktree_utils.py:236-243`), which exists solely because the generic `copy_files` loop can't copy directories. Every single-file addition to date (`.claude/settings.local.json`, `.env`) went through the config-driven default list in `config/automation.py:91-93`/`:130-132`. EPIC-3111 itself scopes this fix to exactly those lines plus `config-schema.json:360`. The migration gap (projects with an explicit `worktree_copy_files` override) is real but bounded and mechanical to fix.
- **Option B evidence (rejected)**: copying unconditionally inside `setup_worktree`, alongside the `.claude/` copytree, would bypass `copy_files` entirely — the same way `.claude/` bypasses it today. `verify_epic_branch_before_merge` (`worktree_utils.py:445`) deliberately passes `copy_files=[]` to keep machine-local files out of its transient verify-only worktree; Option B's unconditional copy would leak `.ll/ll.local.md` into that worktree anyway, directly contradicting the issue's own requirement.
- **Known follow-up cost**: four literal-list locations need to move together (`config/automation.py` x2, `parallel/types.py`, `config-schema.json`), plus two existing tests asserting the default list contents (`test_config.py:401`, `test_parallel_types.py:782`) and one doc table row (`docs/reference/CONFIGURATION.md:390`).

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **BUG-3112 landed** (`status: done`, completed 2026-08-09T14:42:44Z) and its fix is now present in `setup_worktree()` at `worktree_utils.py:198-206`: `os.environ.setdefault("LL_HISTORY_DB", str(resolve_history_db()))`, run before worktree creation. This does not touch the `.claude/` copytree or the `copy_files` loop — no signature or call-site change, no conflict with this issue's planned edit.
- **Anchor drift from that landing** (BUG-3112's change shifted line numbers below it in the same function): the `.claude/` copytree is now at `worktree_utils.py:246-253` (was cited as `:236-243`); the `copy_files` loop is now at `worktree_utils.py:256-272` (was cited as `:246-262`), with the `.claude/`-prefix skip at `:257-258`; `verify_epic_branch_before_merge()`'s `copy_files=[]` call is now at `worktree_utils.py:451-459` (was cited as `:445`). Behavior at each of these anchors is unchanged — only line numbers moved.
- **No merge-not-replace mechanism exists** for list-type config defaults anywhere in this codebase: `deep_merge()` (`config/core.py:87-114`) is documented and tested (`test_hook_session_start.py:142-149`, `test_local_array_replaces`) to replace arrays wholesale, never append/union. This makes Option A's migration gap (a project with an explicit `worktree_copy_files` override loses the new default entry) unresolvable by any existing utility — it can only be fixed by a manual per-project config edit, not a code-level merge fallback.
- **No generic drift-prevention test exists** for the dataclass-default ↔ `from_dict()`-default ↔ `config-schema.json`-default triple (and, for this field, a fourth independent mirror in `parallel/types.py`). Every `test_from_dict_with_defaults` in `test_config.py` (34 occurrences) is a hand-written per-field literal assertion; ENH-650's own fix for this exact field was a manual three-file edit, not a new drift-prevention utility. A change here inherits the same manual-sync obligation, not an automated guard.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Anchor drift confirmed via direct read (2026-08-10, this pass)** — `/ll:verify-issues` flagged `hooks/session_start.py:136-147` (cited in `Call Path` above, and depended on by Implementation Step 4) as stale. Confirmed: the local-override merge block (`local_file = cwd / _LOCAL_OVERRIDE_FILE` through `deep_merge(base_config, local_overrides)`) now resolves to `session_start.py:113-125` (`local_file` assignment at 114, `deep_merge()` call at 124). Lines 136-147 now point to the FEAT-1112 session-store bootstrap / ENH-1830 JSONL-backfill dispatch block that immediately follows, not the override-merge logic.
- Two more citations in this issue's own `Signatures`/`Call Path` subsections above were also missed by the prior "Anchor drift from that landing" correction (which only updated the narrative Decision Rationale prose, not these subsections): `Signatures`' "the `copy_files` loop at `:246-262`" is now `worktree_utils.py:255-272` (the `.claude/`-prefix skip at `:257-258`, the `shutil.copy2` call at `:267-269`); `Call Path`'s "copies `.claude/` via `shutil.copytree` (`:236-243`)" is now `:246-253`, and "the fourth call site, `worktree_utils.py:445`" (`verify_epic_branch_before_merge`, function definition now at line 381) is now `worktree_utils.py:455`.
- `worktree_copy_files` default-list citations remain current, re-confirmed by direct read: `config/automation.py:91-93` (dataclass default) and `:130-132` (`from_dict()` mirror); `parallel/types.py:416-418`; `config-schema.json:360-366` (description + `"default"` array).
- Override-merge error handling (analyzer finding, informs Implementation Step 4's test): every failure mode in the merge block degrades silently to "no overrides applied" — missing file (`local_file.is_file()` false), unreadable file (`OSError` caught, falls through to `parse_local_override_frontmatter("")` which returns `{}`), and malformed/missing frontmatter or YAML parse error (handled inside `parse_local_override_frontmatter()`, `config/core.py:60-84`, always returns `{}` on failure). No exception ever propagates out of this block; a worktree missing `.ll/ll.local.md` today hits the first case (`local_file.is_file()` is `False`) and silently proceeds with `base_config` only.

### Types
N/A — no new data types introduced; `worktree_copy_files` stays `list[str]` of repo-relative path strings.

### Signatures
- `setup_worktree(repo_path: Path, worktree_path: Path, branch_name: str, copy_files: list[str], logger: Logger, git_lock: GitLock, base_branch: str | None = None, checkout_existing: bool = False) -> None` — `scripts/little_loops/worktree_utils.py:156-165`; the `copy_files` loop at `:246-262` is the only place a new entry needs to reach. Each `file_path` is skipped (not copied) if it starts with `.claude/`, if the source doesn't exist (logged via `logger.debug`), or if the source is a directory (logged via `logger.warning`) — `.ll/ll.local.md` is a plain file, so none of those skip branches apply to it.
- `worktree_copy_files: list[str]` — `ParallelAutomationConfig`, `scripts/little_loops/config/automation.py:91-93`, dataclass default `[".claude/settings.local.json", ".env"]`; the mirrored `from_dict()` default at `:130-132` must be edited together with it (a prior drift between these two, ENH-650, was filed against exactly this pair).
- `sync_to_local_md(decisions_path: Path, ...) -> None` — `scripts/little_loops/decisions_sync.py:31-38`; resolves its write target as `decisions_path.parent / "ll.local.md"`, where `decisions_path` comes from `_resolve_path()` calling `little_loops.paths.resolve_ll_dir()`, which calls `find_project_root()` (`scripts/little_loops/paths.py:14-42`).

### Call Path
`setup_worktree` -> `shutil.copytree` -> `copy_files` loop -> `shutil.copy2`

Concretely: `setup_worktree()` (`worktree_utils.py:156`) copies `.claude/` via `shutil.copytree` (`:236-243`), then iterates `copy_files`, calling `shutil.copy2` per entry (`:246-262`). Three real call sites thread `parallel.worktree_copy_files` straight through unmodified: `fsm/executor.py:946`, `cli/loop/run.py:459,488`, `parallel/worker_pool.py:778`. The fourth call site, `worktree_utils.py:445` inside `verify_epic_branch_before_merge`, deliberately passes `copy_files=[]` — a transient verify-only worktree that must NOT receive machine-local files; any fix here must not flow `.ll/ll.local.md` into that path.

Separately: `find_project_root()` (`paths.py:14-42`) walks upward for a directory with both `.ll` and `.git`, and a git worktree has its own `.git` file plus a checked-out (tracked) `.ll/` dir — so it resolves to the worktree root, not the main repo. Consequently `ll-issues decisions sync` run inside a worktree session today writes `## Active Rules` into a brand-new `<worktree>/.ll/ll.local.md` rather than updating the main tree's copy, and that file is deleted on teardown (`cleanup_worktree()`, `worktree_utils.py:272-317`, `shutil.rmtree`) since it is gitignored/untracked and outside `preserve_before_teardown()`'s git-object-based snapshot. Session config resolution: `scripts/little_loops/hooks/session_start.py:136-147` resolves `local_file = cwd / ".ll/ll.local.md"`; when absent (always true in a fresh worktree today), the override merge (`deep_merge()`, `config/core.py:57-84`) is silently skipped — no error, no warning, effective config falls back to base only.

### Decision Rules
N/A — no new gap kind, gate, or threshold; this is a copy-list/allowlist change, not new classification logic.

## Implementation Steps

1. Decide between extending the default `copy_files` list and an explicit
   in-function allowlist.
2. Determine the correct treatment of the `## Active Rules` section — copying is
   sufficient if the worktree session only reads it; confirm nothing re-syncs it
   inside the worktree and writes back somewhere that gets discarded.
3. Apply the change and update the config-schema description
   (`config-schema.json:360`) if the default changes.
4. Test: with a `ll.local.md` overriding `project.test_cmd` copied into a
   worktree, assert the SessionStart hook, run with that worktree as `cwd`,
   produces the same `deep_merge()`-overridden config the main tree would
   (`hooks/session_start.py:136-147`). Do **not** assert against a
   worktree-resolved `BRConfig` — see the resolved wiring note below.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Resolved** (decided during `/ll:confidence-check`, 2026-08-08): `BRConfig._load_config` (`config/core.py:229-240`) never reads or merges `.ll/ll.local.md` — only the SessionStart hook does (`hooks/session_start.py:136-147`, via `deep_merge()`), and that merge result is emitted as hook stdout only, never written back to disk or consumed by `BRConfig`. This is true in the main tree too, not just a worktree, so it is a separate, broader defect — filed as **BUG-3123** rather than folded in here, since EPIC-3111's scope is worktree copy semantics, not `BRConfig`'s override-resolution mechanism. Step 4's test targets the SessionStart hook (the actual current consumer of `ll.local.md` overrides), not `BRConfig`.
- Update `scripts/little_loops/parallel/types.py` (:416-418) — move `ParallelConfig.worktree_copy_files`'s mirrored default list alongside `config/automation.py`'s, so direct `ParallelConfig` construction (bypassing `config/core.py`) doesn't silently keep the stale default
- Update `scripts/tests/test_config.py:401` and `scripts/tests/test_parallel_types.py:782` — both assert the literal old default and will fail once it changes
- Update `docs/reference/CONFIGURATION.md` (:66, :390) and `docs/reference/API.md` (:524, :3596) — literal default-list reproductions
- Update `docs/development/TROUBLESHOOTING.md` (:183-195) — extend "Worktree not inheriting settings" to cover `.ll/ll.local.md`, not just `.claude/settings.local.json`

_Second wiring pass added by `/ll:wire-issue` — 2026-08-09:_
- Update `scripts/little_loops/config-schema.json` (:366) — the `"default"` array key, a fourth literal reproduction of the old default distinct from the `:362` description
- Decide whether `skills/configure/areas.md` (:231-242) and `scripts/little_loops/init/tui.py` (:415-430) — two independent hardcoded "which files to copy" option lists surfaced during interactive config — should also offer `.ll/ll.local.md`, or are explicitly out of scope for this issue

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py` (:236-262)
- `scripts/little_loops/config/automation.py` (:91, :131) — default list
- `scripts/little_loops/config-schema.json` (:360) — description

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/types.py` (:416-418) — `ParallelConfig.worktree_copy_files` mirrors the same literal default independently via its own `field(default_factory=...)`. Confirmed a live fallback, not dead code: `config/core.py:594` normally threads `automation.py`'s value through when building `ParallelConfig` via `BRConfig`, but any call site that constructs `ParallelConfig` directly (bypassing `config/core.py`) falls back to this literal, which would still read `[".claude/settings.local.json", ".env"]` if left unmodified [Agent 1/2 finding]

_Second wiring pass added by `/ll:wire-issue` — 2026-08-09:_
- `scripts/little_loops/config-schema.json` (:366) — a fourth independent literal reproduction of the same default, distinct from the `:362` description text already listed above: the JSON Schema `"default"` array key (`[".claude/settings.local.json", ".env"]`) sits on the same `worktree_copy_files` property block and must be updated alongside the description [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/core.py` — local-override merge path
- `scripts/little_loops/init/tui.py`, `init/summary.py` — surface `worktree_copy_files`

### Similar Patterns
- `.claude/settings.local.json` handling — the existing precedent for carrying
  machine-local config into a worktree

### Tests
- `scripts/tests/` — worktree_utils copy coverage; config-override resolution

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py:401` — `test_from_dict_with_defaults` asserts the literal `config.worktree_copy_files == [".claude/settings.local.json", ".env"]`; will break and needs updating once the default changes [Agent 3 finding]
- `scripts/tests/test_parallel_types.py:782` — asserts the same literal default on `ParallelConfig` directly (independent of `config/automation.py`, see `parallel/types.py` entry above); will break and needs updating [Agent 3 finding]

### Documentation
- Worktree copy-semantics reference (ENH-3115)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` (:66 JSON example, :390 table row) — spells out the literal default list `[".claude/settings.local.json", ".env"]` [Agent 2 finding]
- `docs/reference/API.md` (:524, :3596) — two separate dataclass-snippet reproductions of the same literal default (`ParallelAutomationConfig` and `ParallelConfig`) [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` (:183-195, "Worktree not inheriting settings") — currently scoped only to `.claude/settings.local.json`; becomes an incomplete troubleshooting entry once `.ll/ll.local.md` shares the same inheritance mechanism [Agent 2 finding]
- `skills/configure/show-output.md` (:49) — template line displaying the default (already stale today, showing only `[.env]`); worth correcting alongside this change [Agent 2 finding]

_Second wiring pass added by `/ll:wire-issue` — 2026-08-09:_
- `skills/configure/areas.md` (:193, :231-242) — independent "Copy files" question in the interactive `parallel` config area, with its own hardcoded option set (`.env`, `.env, .env.local`, `none`) that doesn't surface `.claude/settings.local.json` or `.ll/ll.local.md`; a separate file from `skills/configure/show-output.md` above [Agent 1/2 finding]
- `scripts/little_loops/init/tui.py` (:415-430) — the interactive `ll-init` "Copy these files into each worktree:" `questionary.checkbox()` prompt hardcodes its own independent choice set (`.env`, `.env.local`, `.secrets`), not derived from the `worktree_copy_files` default; if a user picks nothing, `worktree_copy_files` is set to `[]` directly (line 430), overriding the default entirely rather than falling back to it. Consider whether this checkbox's choices should include `.ll/ll.local.md` [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Additional Findings

- `.claude/settings.local.json` is copied redundantly two ways today: once by the `.claude/` wholesale `copytree` (`worktree_utils.py:236-243`) and again as the first default `worktree_copy_files` entry — the copy-loop explicitly `continue`s on any `.claude/`-prefixed entry (`:247-248`) to avoid double-copying. A `.ll/ll.local.md` entry would not hit that skip branch.
- Fourth `setup_worktree` call site to account for: `worktree_utils.py:445` (`verify_epic_branch_before_merge`) passes `copy_files=[]` deliberately — this transient verify-only worktree must keep receiving nothing, so any allowlist/default change must not silently add `.ll/ll.local.md` there too.
- `config-schema.json:360-366` documents the default's rationale today ("Includes .claude/settings.local.json by default because it carries Claude Code auth tokens required in each worktree. Note: .claude/ directory is always copied automatically.") — this description needs updating regardless of which of the two Proposed Solution options is chosen.
- Existing gitignored-`.ll/`-state precedent table (what is/isn't carried into a worktree today, and why):

  | File | Current treatment | Evidence |
  |---|---|---|
  | `.ll/ll.local.md` | Not copied — gitignored (`.gitignore:53`), absent from `setup_worktree` and from default `worktree_copy_files` | `worktree_utils.py:157-269` (no `.ll/` reference) |
  | `.ll/history.db*` | Deliberately not copied — BUG-3112 argues copying a live WAL SQLite file is unsafe (torn snapshot) and proposes *sharing* via an `LL_HISTORY_DB` env var instead | `.issues/bugs/P2-BUG-3112-worktree-sessions-write-history-to-throwaway-db.md` |
  | `.ll/queue.db*`, `.ll/*.lock` | Deliberately excluded per this issue's own Proposed Solution text | this issue, line ~70 |

  The env-injection idiom (point a worktree session at the main tree's file via an env var rather than copying/duplicating it) already has a precedent in this codebase: `worktree_utils.py:455-461` sets `env["LL_VERIFY_GATE"] = "1"` on the verify-gate worktree's child process, with a comment noting it "mirrors the `LL_NON_INTERACTIVE` marker idiom." This is the pattern BUG-3112 proposes reusing for `LL_HISTORY_DB`; it is a plausible alternative worth naming even though `ll.local.md` is read-only from the worktree's perspective (config resolution) so a copy, not an env-pointer, is what the two Proposed Solution options both assume.
- `.ll/ll.local.md` is parsed only by the SessionStart hook (`hooks/session_start.py:46,136-147`, `_LOCAL_OVERRIDE_FILE`), not by `BRConfig` itself — `config/core.py` never reads the file directly, only `deep_merge()`'s docstring references it.
- `## Active Rules` is read back into the agent's context via the host CLI's native memory-file auto-loading (same channel as `CLAUDE.md`), not parsed by any little-loops Python — confirmed via `cli/doctor_trim.py:44-51`'s `_MEMORY_CANDIDATES` list, which names `.ll/ll.local.md` alongside `.claude/CLAUDE.md` and root `CLAUDE.md` as files "injected verbatim at session start on every host."

### Tests (additional)
- `scripts/tests/test_cli_loop_worktree.py::test_copies_configured_files` (:137) — asserts a `copy_files=[".env"]` entry reaches `shutil.copy2`; the shape a new `.ll/ll.local.md` test would mirror.
- `scripts/tests/test_cli_loop_worktree.py::test_skips_claude_prefixed_copy_files` (:168) — asserts `.claude/`-prefixed entries are not re-copied via `copy2`.
- `scripts/tests/test_cli_loop_worktree.py::test_copy_files_directory_skipped_with_warning` (:317) — the directory-skip path (irrelevant to `.ll/ll.local.md`, which is a file, but relevant if `.ll/decisions.d/` were ever added to the same list — see ENH-3114).
- `scripts/tests/test_hook_session_start.py::TestSessionStartLocalOverrides` (:112-159) — covers the `deep_merge` override-application path a copied `ll.local.md` would need to actually take effect through.

## Impact

- **Priority**: P3 - Config divergence is real but lower-consequence than lost history; most projects don't override much locally
- **Effort**: Small - A default-list change plus a test
- **Risk**: Low - Additive copying of a file that is already read-only from the worktree's perspective
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:manage-issue` - 2026-08-10T04:08:12 - `971485e0-3067-4d1f-9928-29d6aef6939b.jsonl`
- `/ll:ready-issue` - 2026-08-10T03:52:31 - `f1cc520a-5f99-47bf-8a05-053c87f7be13.jsonl`
- `/ll:verify-issues` - 2026-08-10T03:46:45 - `53ea544f-d7ea-4882-98bc-46203ecdc90b.jsonl`
- `/ll:refine-issue` - 2026-08-10T03:41:18 - `bbe921ee-4d1c-43db-972b-44d5060280dc.jsonl`
- `/ll:verify-issues` - 2026-08-10T03:34:54 - `817c0050-4b7b-4bbc-8fc0-f2412304317c.jsonl`
- `/ll:wire-issue` - 2026-08-10T03:32:07 - `93eca2ef-017c-4122-986b-db0f5e8a1726.jsonl`
- `/ll:refine-issue` - 2026-08-10T03:22:19 - `1a846524-f20c-4b43-97e4-ce942ee59303.jsonl`
- `/ll:wire-issue` - 2026-08-08T21:41:41 - `5c29eabe-8674-4e2a-8f5b-4edb546e0270.jsonl`
- `/ll:decide-issue` - 2026-08-08T21:12:29 - `c7f56cd0-0af0-4888-afb5-9244e302ca34.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:06:19 - `29dcd8e6-5691-426f-91c4-b6457c12fffb.jsonl`
- `/ll:capture-issue` - 2026-08-08T20:35:50 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`

---

## Status

**Open** | Created: 2026-08-08 | Priority: P3
