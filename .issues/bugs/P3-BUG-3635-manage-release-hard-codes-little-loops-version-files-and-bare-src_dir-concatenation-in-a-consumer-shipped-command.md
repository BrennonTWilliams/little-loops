---
id: BUG-3635
type: BUG
title: manage-release hard-codes little-loops version files and bare src_dir concatenation
  in a consumer-shipped command
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T06:09:13Z'
confidence_score: 100
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
---

# BUG-3635: manage-release hard-codes little-loops version files and bare src_dir concatenation in a consumer-shipped command

## Summary

`commands/manage-release.md` ships to every consuming project but hard-codes little-loops' own version files: `{{config.project.src_dir}}pyproject.toml`, `.claude-plugin/plugin.json`, and `{{config.project.src_dir}}little_loops/__init__.py`. In a consuming project these paths name files that do not exist (there is no `little_loops/` package, usually no `.claude-plugin/plugin.json`, and a Go/JS project has no `pyproject.toml`). The paths are also built by bare concatenation (`{{config.project.src_dir}}pyproject.toml`), which relies on a trailing slash: `src_dir: "."` (the `go` template default) yields `.pyproject.toml`, and a no-slash value like `src` yields `srcpyproject.toml`.

Split out of BUG-3631 (root-layout prefix handling), where fixing only the separator would have produced correctly joined paths to files that still don't exist.

## Current Behavior

- Nine concatenation sites in `commands/manage-release.md`: the "Version is tracked in these files" list (lines 38, 40), the Agent 3 version-discovery prompt (249, 251), the `bump` action's Edit comments and `git add` (302, 304, 310), and the dry-run "Version Files" example (453, 455).
- The same nine sites exist in the git-tracked host mirrors: `.gemini/commands/manage-release.toml`, `.qwen/commands/ll/manage-release.md`, `.kimi-code/skills/ll-manage-release/SKILL.md`.
- A tenth hard-coded spot, not a concatenation site: the dry-run preview's `[bump]      Update version in 3 files` (line 437) assumes little-loops' file count.
- The Agent 3 prompt already has a catch-all ("4. Any other files containing the current version string"), so discovery partly works in consuming projects, but the `bump` action's `git add` line stages the hard-coded paths, which fails (`pathspec did not match`) when they don't exist.
- The catch-all is unfiltered: in the little-loops source repository the current version string (`1.166.0`) matches `CHANGELOG.md` as well as the real manifests, and in consuming projects it can match lockfile entries for dependencies that share the version number. It is harmless today only because `git add` ignores it; once staging follows Agent 3's results, it would bump historical changelog entries or lockfiles.
- The hard-coded list also omits `.claude-plugin/marketplace.json`, which carries the version twice (lines 3 and 12) and which the source-repo-only `.claude/commands/publish.md` bumps; today it is reached only through the catch-all.
- In the little-loops source repository `src_dir` is `scripts/`, so all three paths happen to resolve and the defect is invisible here.

## Steps to Reproduce

1. In a consuming Go project initialized with `ll-init` (`project.src_dir: "."`), run `/ll:manage-release` with the `bump` action.
2. The command's version-file list names `.pyproject.toml` and a dot-prefixed `little_loops` package `__init__.py` (bare concatenation with `.`), neither of which exists.
3. The `bump` step's `git add` line fails with `pathspec did not match` for the hard-coded paths.

## Expected Behavior

- The version-file list is discovered per project, not hard-coded to little-loops' layout. Common manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, a package `__init__.py` / `__version__` holder) are candidates, resolved relative to repo root and `project.src_dir`.
- Paths join `src_dir` with exactly one separator; `src_dir` of `.` / `./` resolves to repo root; `src/`, `scripts/` and no-slash `src` all resolve correctly.
- Agent 3 reports only **version declarations** (a manifest `version` field or a `__version__ =` assignment) as bump targets. Incidental matches of the version string (`CHANGELOG.md`, lockfiles, `node_modules/`, `.issues/`, docs) are excluded, or reported as info-only and never edited or staged.
- The `bump` action edits and stages exactly the declaration files Agent 3 found, not a hard-coded list.
- Behavior in the little-loops source repository still bumps `scripts/pyproject.toml`, `.claude-plugin/plugin.json`, `scripts/little_loops/__init__.py`, and now also `.claude-plugin/marketplace.json` (both version fields) as a first-class candidate rather than via the catch-all. `CHANGELOG.md` is never edited by `bump`.

## Proposed Solution

**Decision: Option 1 (discovery-only prose change).** No `release.*` config
key exists today, and Agent 3 already does discovery (the catch-all at line
252) while the `bump` action's own prose already says "Update version in all
files found by Agent 3" (line 298) — only the bash comments and `git add` at
302–310 contradict that by hardcoding little-loops' three paths. Option 2
(an optional `release.version_files` config key) would add new schema
surface to re-solve a problem that's already half-solved; rejected per the
project's "check existing primitives before adding a new flag" convention.

Implementation notes for Option 1:

- **Avoid path-string concatenation entirely, don't just fix the join.**
  Rather than teaching the prose a rule for joining `src_dir` + filename with
  exactly one `/` (the same class of mistake the current hard-coded prompt
  already makes), have Agent 3's `Explore` subagent **Glob-search** for
  candidate manifest filenames (`pyproject.toml`, `package.json`,
  `Cargo.toml`, `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`) under the repo root and under
  `{{config.project.src_dir}}`, using the Glob tool it already has. This
  never constructs a literal joined path string in the prompt, so the
  separator bug (`.` → `.pyproject.toml`, no-slash `src` →
  `srcpyproject.toml`) can't recur — a stronger fix than a prose join-rule,
  which an LLM could flub the same way.
- **Globs must be non-recursive: repo-root and `src_dir` top level only,
  never `**/`.** A recursive `pyproject.toml` glob in the little-loops source
  repository returns 8 hits, including `.claude/worktrees/agent-*/scripts/pyproject.toml`
  (stale agent worktrees) and vendored copies under
  `.claude/skills/excalidraw-diagram/references/` and `.agents/skills/`.
  Consuming projects have the same hazard (worktrees, vendored deps,
  fixtures).
- **Find the `__version__` holder with Grep, not Glob.** Globbing for
  `__init__.py` matches every package in the tree. Instead, Grep for
  `^__version__\s*=` scoped to `{{config.project.src_dir}}`.
- **Filter the catch-all to declarations.** Keep "4. Any other files
  containing the current version string" for visibility, but the prompt must
  have Agent 3 classify each hit as a *declaration* (manifest `version`
  field, `__version__ =`) or *incidental* (`CHANGELOG.md`, lockfiles such as
  `package-lock.json`/`uv.lock`/`Cargo.lock`, `node_modules/`, `.issues/`,
  docs). Only declarations are bump targets. This matters because the fix
  makes Agent 3's result the source of truth for both the Edit and `git add`;
  unfiltered, it would rewrite the version in historical `CHANGELOG.md`
  entries (the current version `1.166.0` appears there in this repo) and in
  lockfile entries for dependencies that share the number.
- **Fix the `bump` action's `git add`** (line 310) to stage exactly the
  declaration files Agent 3 found and the prior step edited, not the
  hardcoded three paths — e.g. "stage exactly the files you just edited
  above" (explicit paths, never `git add -A`/`-u`), consistent with the
  existing instruction at line 298.
- **Lines 38–40** (the "Version is tracked in these files" list) become
  generic candidate guidance instead of a little-loops-specific hard list.
  Phrase it as examples ("e.g. `pyproject.toml`, `package.json`,
  `Cargo.toml`, `.claude-plugin/*.json`, a `__version__` assignment") so the
  model does not treat it as a required checklist. Replace the three lines
  with exactly three lines to stay line-count-neutral above the line-134 pin
  (see below). Little-loops' own files still surface naturally via discovery
  since they exist in this repo (satisfies AC re: unchanged source-repo
  behavior).
- **Line 437** (dry-run `[bump] Update version in 3 files`) → "Update
  version in N files".
- **Lines 453/455** (dry-run example) are illustrative, not functional —
  genericize them or add a one-line caveat that the example paths are
  little-loops-specific.
- **Add a regression test** so AC1/AC2 are enforced, not hand-checked once:
  a static test that fails if `{{config.project.src_dir}}` is immediately
  followed by `[A-Za-z_.]` in `commands/manage-release.md`, and if any
  `little_loops/` path remains in it. Consider widening the concatenation
  check to all of `commands/` and `skills/`, since that is the BUG-3631 bug
  class (currently only `manage-release.md` has hits, so a corpus-wide gate
  passes after this fix).
- **Spawn-site line pin**: `scripts/tests/test_wiring_skills_and_commands.py:754`
  does not pin the file's total length (it is 558 lines, not 134) — it pins
  `("commands/manage-release.md", 134)` in `SPAWN_SITE_INVENTORY`, asserting
  that the "Spawn all 3 agents..." instruction sits at line 134. Lines 38–40
  sit above that anchor, so any net line-count change introduced above line
  134 shifts that instruction to a different line and breaks the pin. Keep
  edits above line 134 line-count-neutral, or update the tuple to the new
  line number in the same commit.

## Integration Map

- `commands/manage-release.md` — the nine sites above, plus line 437 (`Update version in 3 files`).
- Mirrors: regenerate with `ll-adapt --host gemini --apply`, `ll-adapt --host qwen --apply`, `ll-adapt --host kimi-code --apply`; mirror gates fail otherwise.
- `scripts/tests/test_wiring_skills_and_commands.py`'s `SPAWN_SITE_INVENTORY` pins `("commands/manage-release.md", 134)` — the line of the "Spawn all 3 agents..." instruction, not a total-file-line-count pin (the file is 558 lines); edits above line 134 (sites 38, 40) must be line-count-neutral or update the pinned line number in the same change.
- New regression test (e.g. in `scripts/tests/test_wiring_skills_and_commands.py`, alongside the existing `manage-release.md` pins at lines 59–60 and 429) for the no-concatenation and no-`little_loops/` checks.
- Not affected: `skills/ll-manage-release/SKILL.md` is a 24-line frontmatter shim with no `src_dir` or version-file references — no change needed, not a missed mirror.
- Reference only: `.claude/commands/publish.md` (source-repo-only) is the authoritative list of little-loops' version files (`plugin.json`, `marketplace.json`, `pyproject.toml`, `__init__.py`); `/ll:manage-release` in this repo should discover the same four.

## Program Design

### Types

- No new types. The fix is prose in `commands/manage-release.md` and its mirrors; no config schema or dataclass changes.

### Signatures

- `expand_skill(name: str, args: list[str], config: BRConfig) -> str | None` — unchanged; expands the command body for non-Claude hosts
- `_substitute_config(content: str, config: BRConfig) -> str` — unchanged; still interpolates `{{config.project.src_dir}}`, but no longer directly abutting a filename anywhere in this command

No Python signatures change.

### Call Path

`expand_skill` -> `_substitute_config` (placeholder interpolation of the rewritten version-file lines); in the command itself: Agent 3 (`Explore` subagent) non-recursively Glob-searches candidate manifests at repo-root and `{{config.project.src_dir}}` top level, Greps `^__version__\s*=` under `{{config.project.src_dir}}`, and classifies catch-all hits as declaration vs incidental -> `bump` Edit of declaration files only -> `git add` of exactly those edited files (not a hard-coded list)

## Impact

- **Priority**: P3 — `/ll:manage-release` stages nonexistent files in any consuming project that isn't laid out like little-loops.
- **Effort**: Small (option 1) to Medium (option 2).
- **Risk**: Low; release flow in the little-loops source repository must keep working.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] No `{{config.project.src_dir}}` placeholder is directly followed by a filename in `commands/manage-release.md` or its three mirrors.
- [ ] No hard-coded `little_loops/__init__.py` path remains in `commands/manage-release.md` or its mirrors.
- [ ] Agent 3's version-file discovery uses Glob search over candidate manifest names (including `.claude-plugin/marketplace.json`) at repo-root and `src_dir` top level only — no recursive `**/` glob — not string concatenation.
- [ ] The `__version__` holder is found by Grep for `^__version__\s*=` scoped to `src_dir`, not by globbing `__init__.py`.
- [ ] Agent 3 classifies hits as declarations vs incidental matches; `CHANGELOG.md`, lockfiles, `node_modules/`, `.issues/` and docs are never bump targets.
- [ ] The `bump` action's `git add` (line 310) stages exactly the declaration files Agent 3 found and the prior step edited (explicit paths, not `-A`/`-u`), not a hard-coded list.
- [ ] Lines 38–40 read as example candidates ("e.g. …"), not a fixed checklist, and are replaced line-count-neutrally.
- [ ] The dry-run preview no longer says "Update version in 3 files" (line 437); it reports the discovered count.
- [ ] A regression test fails if `{{config.project.src_dir}}` is directly followed by `[A-Za-z_.]` or a `little_loops/` path appears in `commands/manage-release.md`.
- [ ] In the little-loops source repository, discovery yields exactly `scripts/pyproject.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `scripts/little_loops/__init__.py` as bump targets (matching `.claude/commands/publish.md`), with `CHANGELOG.md` reported as incidental at most.
- [ ] `test_wiring_skills_and_commands.py`'s `SPAWN_SITE_INVENTORY` entry `("commands/manage-release.md", 134)` (the "Spawn all 3 agents..." line, not a total-line-count pin) still points at the correct line, or is updated to the new one in the same commit.
- [ ] Mirrors match after `ll-adapt --apply` for gemini, qwen and kimi-code.
- [ ] `python -m pytest scripts/tests/` exits 0 (mirror gates and the `test_wiring_skills_and_commands.py` line pin included).

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the
same pass, so the issue as it now reads is up to date — this section is a
record of what was wrong and fixed, not an outstanding action item)

- All nine `{{config.project.src_dir}}`-abutting concatenation sites (lines
  38, 40, 249, 251, 302, 304, 310, 453, 455) verified present and accurate in
  `commands/manage-release.md`, and at the analogous line numbers in all
  three mirrors (`.gemini/commands/manage-release.toml`,
  `.qwen/commands/ll/manage-release.md`,
  `.kimi-code/skills/ll-manage-release/SKILL.md`).
- Confirmed `go.json`'s template default `src_dir: "."` (bare concatenation
  produces `.pyproject.toml`), supporting the Steps to Reproduce claim.
- `scripts/tests/test_wiring_skills_and_commands.py:754` was misdescribed as
  a total-file-line-count pin ("134 lines"); the file is actually 558 lines.
  It is a `SPAWN_SITE_INVENTORY` entry pinning the line of the "Spawn all 3
  agents..." instruction. Corrected in place in the Proposed Solution's
  Implementation notes, the Integration Map, and the Acceptance Criteria.
- BUG-3631 (Related) confirmed `done`.
- No active required decision rules; `ll-verify-evidence` reported no
  unverifiable evidence spans.

## Related

- Split from BUG-3631 (root-layout `src_dir` / `focus_dirs` prefix handling).

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-27T20:19:56 - `c758ef8d-094a-49af-b905-13aeada69b25.jsonl`
- `/ll:verify-issues` - 2026-09-27T20:08:13 - `7e522036-3dd2-4d72-a54c-33d788eff962.jsonl`
