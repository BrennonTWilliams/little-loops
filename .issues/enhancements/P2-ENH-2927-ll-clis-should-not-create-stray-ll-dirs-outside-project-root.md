---
id: ENH-2927
title: ll-* CLIs should not implicitly create .ll/ directories outside a resolved project root
type: ENH
status: open
priority: P2
discovered_date: 2026-07-30
discovered_by: review
labels:
- robustness
- cli
- hygiene
relates_to:
- ENH-2924
- ENH-2870
blocked_by:
- ENH-2924
---

# ENH-2927: ll-* CLIs should not implicitly create `.ll/` directories outside a resolved project root

## Summary

Certain `ll-*` commands and PostToolUse hooks implicitly create a `.ll/` directory at
the current working directory when run from a subdirectory. These strays regenerate
faster than manual cleanup (four new strays — `scripts/.ll`,
`scripts/little_loops/.ll`, `skills/.ll`, `hooks/adapters/opencode/.ll` — appeared
within two days of a 50-dir cleanup on 2026-07-27). ENH-2924 makes root *resolution*
skip strays and lands the shared `little_loops.paths` module; this issue stops
*producing* them, so every other `.ll` consumer (session store, hook state, queue DB)
anchors correctly too.

## Current Behavior

The generator set is narrower than a "every `ll-*` command" framing suggests. Measured
by invoking commands from a subdirectory of a scratch git repo whose root has `.ll/`
and observing what appears at the subdirectory:

| Creator | Artifact created at cwd |
|---|---|
| `ll-doctor`, `ll-ctx-stats`, `ll-gitignore` | `.ll/history.db` |
| `edit_batch_nudge.py` PostToolUse hook | `.ll/ll-edit-batch-state.json` + `.lock` |
| `drift_check.py` PostToolUse hook | `.ll/ll-doc-drift-state.json` + `.lock` |

`ll-issues list`, `ll-loop list`, `ll-queue list`, `ll-session recent`, `ll-config get`,
`ll-issues next-id`, `ll-logs stats`, `ll-deps validate`, `ll-learning-tests list`, and
`ll-code status` created nothing. The quarantined strays confirm the same inventory:
`.ll/stray-quarantine-2026-07-29/scripts/` holds `history.db` and
`ll-doc-drift-state.json`; `hooks-adapters-opencode/` holds `ll-edit-batch-state.json`.
**The decisions store and the queue DB are not offenders** and should be dropped from
the suspect list.

Two mechanisms produce all of it:

1. **Module-level relative paths in hooks.** `edit_batch_nudge.py:70` sets
   `_STATE_PATH = Path(".ll/ll-edit-batch-state.json")`; `drift_check.py:39` does the
   equivalent. Hooks run with whatever cwd the host hands them, so the write lands
   wherever that is. Neither reads `CLAUDE_PROJECT_DIR`, which Claude Code sets for
   exactly this purpose — the variable is referenced nowhere in `scripts/` or `hooks/`.
2. **No upward resolution anywhere in the config/DB layer.** `_config_db_path()`
   (`session_store/db.py:47`) does `root = Path.cwd()` and calls
   `resolve_config_path(root)`, which probes that one directory and does not walk up.
   `BRConfig.__init__` (`config/core.py:214`) has the same shape: it takes a
   `project_root` and every caller passes `Path.cwd()`. So `DEFAULT_DB_PATH`
   (`.ll/history.db`, relative) resolves against cwd and `ensure_db`'s
   `db_path.parent.mkdir(parents=True, exist_ok=True)` (`session_store/schema.py:1040`)
   creates it. A secondary consequence worth noting: from a subdirectory the project's
   config is not found *at all*, so every `ll-*` invocation there silently runs on
   defaults.

Visibility differs by audience. **This repo** ignores nested strays via a `**/.ll/`
pattern (`.gitignore:126-131`), so they accumulate silently here. A **consuming
project** gets no such pattern — `ll-init`'s `_GITIGNORE_ENTRIES`
(`init/writers.py:17-23`) lists only five specific root-level state files — so strays
there surface as untracked noise instead.

## Expected Behavior

`.ll/` is only ever created at a *resolved* project root:

- If an ancestor of cwd already contains `.ll/` (per ENH-2924's `.git`-aware,
  repo-bounded resolution), all writes anchor there — never at cwd.
- If no project root resolves at all:
  - **CLI commands** that need `.ll/` state fail with a clear "not inside a
    little-loops project; run `ll-init`" error.
  - **Hooks silently no-op.** A PostToolUse hook running in an arbitrary cwd must
    never error or emit a diagnostic — an erroring hook is a worse outcome than the
    stray it replaces. Skip the nudge, exit 0, write nothing.
  - `ll-init` itself creates `.ll/` deliberately at the chosen root.
- No `ll-*` command creates `.ll/` as an incidental side effect of a read-only
  operation (`list`, `show`, `validate`, `stats`, `doctor`).
- Hooks prefer `CLAUDE_PROJECT_DIR` when the host provides it, falling back to upward
  resolution from cwd. This deterministically fixes the majority-by-count generator
  without depending on any heuristic.
- `ll-init` writes the **nested-only** ignore pair into a consuming project's
  `.gitignore`, matching what this repo already carries, so residual strays stay
  contained everywhere:

  ```
  **/.ll/
  !/.ll/
  ```

  This gives `.ll/` the same shape as `.claude/`: **tracked with exceptions** at the
  repo root, fully ignored at every nested depth. Verified on a scratch repo carrying
  exactly the proposed block:

  | tracked (shared with the team) | ignored |
  |---|---|
  | `.ll/decisions.yaml` | `.ll/history.db` |
  | `.ll/decisions.d/*.json` | `.ll/ll-context-state.json` |
  | `.ll/templates/*` | `.ll/*.lock` |
  | `.ll/ll-goals.md` | `sub/.ll/`, `.issues/epics/.ll/`, `scripts/.ll/` (any depth) |

  `git add -A` stages only the left column. The mechanism works because `!/.ll/`
  un-excludes the **directory entry**, so git still descends into it and applies the
  per-file rules inside — git's "cannot re-include a file under an excluded parent"
  limitation does not apply.

  **Maintenance cost to accept explicitly:** under this model a *new* noisy root-level
  artifact is tracked by default until someone adds its ignore line. That gap is live
  right now — FEAT-2906 added `.ll/queue.db` and no entry was added, so it currently
  shows as untracked in `git status`. Adding `.ll/queue.db` (plus `-shm`/`-wal`) to
  both this repo's `.gitignore` and `_GITIGNORE_ENTRIES` is part of this issue.

  The root `.ll/` stays **tracked and committed** — the decisions log
  (`.ll/decisions.yaml` and the `.ll/decisions.d/*.json` fragments), learning test
  registry, `templates/`, and `ll-goals.md` are curated artifacts teams share. Only
  nested strays (`.issues/epics/.ll/`, `scripts/.ll/`) are caught. Noisy root-level
  state stays ignored by the existing per-file entries (`history.db`, `*.lock`,
  `ll-context-state.json`, …), never by a blanket directory rule.

## Proposed Solution

1. Introduce a single `resolve_ll_dir(start=None, create=False)` helper in
   `scripts/little_loops/paths.py` (the module ENH-2924 creates) — the only place
   allowed to `mkdir` `.ll/`. It delegates upward resolution to `find_project_root`.
2. Reroute the measured creation sites:
   - `_config_db_path()` and `DEFAULT_DB_PATH` resolution in `session_store/db.py` —
     anchor at the resolved root instead of cwd.
   - `edit_batch_nudge.py` / `drift_check.py` — replace the module-level relative
     `Path(".ll/…")` constants with a call-time resolution that honors
     `CLAUDE_PROJECT_DIR` first, then upward resolution, then no-ops.
3. Sweep for any remaining site the measurement missed:
   `grep -rn "Path(\"\.ll" scripts/little_loops --include='*.py'` plus
   `grep -rn -B3 "mkdir(parents=True" scripts/little_loops --include='*.py' | grep '\.ll'`.
   Classify each as read-path (`create=False`, error or graceful empty), write-path
   (anchor at resolved root), or init-path (`ll-init`, allowed to create).
4. Add the ordered pair `**/.ll/` then `!/.ll/` to `_GITIGNORE_ENTRIES` in
   `init/writers.py`. Order is load-bearing — git applies last-match-wins, so the
   negation must follow the ignore, and `update_gitignore`'s idempotent append must
   preserve tuple order rather than sorting or de-duplicating across the pair. A
   consuming project that already carries a broader hand-written `.ll/` line *after*
   this block would still ignore its root `.ll/`; detect that case and warn rather
   than silently rewriting the user's file.
5. Regression tests (below).

Deliberately **not** in this issue: making `BRConfig` resolve its root upward. That
fixes a real second-order bug (subdirectory invocations run on default config) but is a
behavior change with much wider blast radius than stray-directory hygiene. Capture it
separately once this lands.

## Program Design

### Signatures

- `def resolve_ll_dir(start: Path | None = None, create: bool = False) -> Path | None`

  New, in `scripts/little_loops/paths.py` alongside ENH-2924's `find_project_root`.
  Sole authority for locating and (when `create=True`) creating `.ll/`. Returns `None`
  when no root resolves and `create=False`; raises nothing.

### Call Path

`resolve_ll_dir` -> `find_project_root`

`_config_db_path` -> `resolve_ll_dir` -> `find_project_root`

`ensure_db` -> `resolve_history_db` -> `resolve_ll_dir`

### Tests

- Invoking `ll-doctor` (a measured offender) from a `tmp_path` repo subdirectory leaves
  no `.ll/` at that subdirectory and finds the root DB instead.
- Invoking `ll-issues list` from a subdirectory remains side-effect-free (guard against
  regression in the currently-clean set).
- `edit_batch_nudge` / `drift_check` invoked with cwd outside any project and no
  `CLAUDE_PROJECT_DIR` exit 0, emit nothing, and create nothing.
- `edit_batch_nudge` with `CLAUDE_PROJECT_DIR` set to a `tmp_path` root writes state
  there, not at cwd.
- `ll-init` on a fresh `tmp_path` project writes `**/.ll/` followed by `!/.ll/` into
  `.gitignore` idempotently (re-running adds no duplicate, and the negation stays
  after the ignore).
- **Root-`.ll/` protection:** in a `tmp_path` git repo initialized by `ll-init`, assert
  `git check-ignore` reports the root `.ll/decisions.yaml` and `.ll/decisions.d/` as
  **not** ignored, while a planted `sub/.ll/` **is** ignored. This is the test that
  fails if anyone later collapses the pair into a bare `.ll/`.

## Scope Boundaries

**In scope:** rerouting the measured creation sites through `resolve_ll_dir`; the
`CLAUDE_PROJECT_DIR` hook path; the `ll-init` gitignore entry; regression coverage that
subdirectory invocations create no stray `.ll/`.

**Out of scope:** ENH-2924's `find_project_root()` selection rule and the `paths.py`
module itself (both land first and this builds on them); making `BRConfig` /
`resolve_config_path` walk upward (separate issue, wider blast radius); deleting
existing strays (one-time manual cleanup, already quarantined); changing what lives
inside `.ll/`.

## Impact

- **Priority**: P2 — this is the recurring half of the problem. ENH-2924 hardens
  resolution against a case no observed stray has yet triggered; this issue stops the
  pollution that demonstrably regenerates every couple of days, in this repo and every
  consuming one.
- **Effort**: Small-Medium — the measured inventory is three call sites plus a sweep;
  the original "spans several modules" estimate assumed a larger offender set than
  exists.
- **Risk**: Low-Medium — a missed write-path anchored at cwd today would start erroring
  instead of silently writing to the wrong place; that surfacing is the point. The hook
  no-op rule keeps the risky path (hooks in arbitrary cwd) fail-quiet.
- **Breaking Change**: Only for workflows that (accidentally) depended on cwd-local
  `.ll/` creation.

## Session Log
- review - 2026-07-30 - replaced the assumed creation-site inventory with a measured one; added `CLAUDE_PROJECT_DIR`, hook-no-op, and `ll-init` gitignore items; moved `resolve_ll_dir` to `little_loops.paths`

## Status

**Open** | Created: 2026-07-30 | Priority: P2
