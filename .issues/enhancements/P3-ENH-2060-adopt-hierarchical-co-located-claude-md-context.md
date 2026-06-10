---
id: ENH-2060
captured_at: "2026-06-09T18:14:42Z"
discovered_date: 2026-06-09
discovered_by: capture-issue
status: open
relates_to: [ENH-278]
labels: [enhancement, documentation, architecture, dx]
testable: false
---

# ENH-2060: Adopt hierarchical, co-located CLAUDE.md context (DOX-inspired)

## Summary

Split the monolithic root `.claude/CLAUDE.md` (now 238 lines) into a hierarchy
of co-located `CLAUDE.md` files placed at durable subsystem boundaries, leaning
on Claude Code's native auto-loading of nested `CLAUDE.md` files. This moves
location-specific rules next to the code they govern, shrinks per-session
root-context token load, and keeps the most-edited rule sets (loop authoring,
hooks, scratch-pad) physically beside their implementations.

## Motivation

A review of the [DOX framework](https://github.com/agent0ai/dox) — a zero-code
"tiny AGENTS.md framework" — surfaced one genuinely valuable idea: distribute
context into co-located, hierarchical docs at durable boundaries instead of one
monolithic root file. DOX reinvents this as an honor-system convention, but
**Claude Code already auto-loads nested `CLAUDE.md` files** when work happens in
a subdirectory, so we can capture ~90% of the value natively.

Today every session pays the full token cost of a 238-line root `CLAUDE.md`,
much of which is location-specific (e.g. the large "Loop Authoring" / meta-loop
MR-1…MR-5 block only matters when editing `loops/`). Co-locating those rules:
- reduces always-on root-context bloat,
- puts rules where they actually fire (less chance of being ignored),
- and makes each subsystem's contract independently maintainable.

This supersedes the *approach* in **ENH-278** (closed 2026-02-11 via tradeoff
review), which proposed a **flat** `core/RULES.md` + `core/PRINCIPLES.md` split
(SuperClaude pattern) and was deferred because CLAUDE.md was only ~109 lines.
Two things have changed: (1) the file is now 238 lines, past ENH-278's own
200-line reopen trigger; (2) the DOX-inspired **hierarchical co-located** shape
is a better fit than the flat `core/` decomposition for location-specific rules.

## Current Behavior

- Single root `.claude/CLAUDE.md` (238 lines) carries everything: project
  config, key directories, the full Loop Authoring / meta-loop rule set, Host
  CLI Abstraction, Automation Scratch Pad, Issue File Format, CLI tool catalog.
- Flat `docs/` tree; no co-located context docs anywhere in the repo
  (confirmed: only `./.claude/CLAUDE.md` exists, no nested `CLAUDE.md`).

## Expected Behavior

Move location-specific sections out of root into nested `CLAUDE.md` files at
durable boundaries, leaving root as a lean overview + pointers. Candidate split:

- `scripts/little_loops/loops/CLAUDE.md` ← the entire "Loop Authoring" +
  meta-loop rules (MR-1…MR-5) section
- `scripts/little_loops/hooks/CLAUDE.md` ← adapter/handler conventions
- `hooks/CLAUDE.md` ← prompt/adapter layout rules
- Root `.claude/CLAUDE.md` keeps: project config paths, key directories, dev
  commands, code style, dev preferences, Issue File Format, CLI tool catalog,
  and short pointers to the nested docs.

Borrow DOX's **precedence rule** verbatim into root so conflict resolution is
unambiguous: *"the closer doc controls local work details, but no child doc may
weaken the root."*

## Implementation Steps

1. Inventory root `CLAUDE.md` sections; tag each as global vs location-specific.
2. Create nested `CLAUDE.md` files at the boundaries above; move the
   location-specific blocks verbatim (preserve ENH references).
3. Trim root to overview + precedence rule + one-line pointers to each child.
4. Verify with `/context` that nested docs load when editing those subtrees and
   that root token footprint drops.
5. (Optional, follow-up) Add an `ll-verify` check that every declared durable
   boundary has a co-located `CLAUDE.md` and that root pointers resolve —
   turning DOX's honor-system convention into something we can actually gate on,
   consistent with the existing `ll-verify-*` family.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_wiring_cli_registry.py` — before or immediately after
   moving sections out of root, audit all `(".claude/CLAUDE.md", ...)` rows in
   `DOC_STRINGS_PRESENT`; for any needle whose content moves to a nested file,
   either update the test row to point at the new nested path or ensure root retains
   a pointer line containing the needle string. Minimum: the two `FEAT-1457` rows
   (`"scripts/little_loops/hooks/"`, `"adapters/"`); also audit `FEAT-1462`
   (`"host_runner"`) and `ENH-1130` (`".loops/tmp/scratch/"`).
7. Decide on `scripts/little_loops/loops/apply-research.yaml` `load_context` state
   — either extend the `head -60 .claude/CLAUDE.md` shell action to also cat
   `scripts/little_loops/loops/CLAUDE.md`, or document the scope reduction as
   intentional (loop-authoring rules only matter when editing loops, not during
   apply-research runs).
8. Decide on `skills/improve-claude-md/SKILL.md` Step CT-1 dedup scope — after the
   split the dedup grep targets root only, so moved rules falsely appear as `OPEN`.
   Options: (a) update Step CT-1 to also grep nested CLAUDE.md files when
   `--file` is not passed, or (b) add a `## Known Limitations` note to the skill
   documenting the post-split single-file scope.

## Integration Map

### Files to Modify
- `.claude/CLAUDE.md` — trim to overview + pointers + precedence rule
- New `scripts/little_loops/loops/CLAUDE.md` (Loop Authoring + MR-1…MR-5)
- New `scripts/little_loops/hooks/CLAUDE.md` (adapter/handler conventions)
- New `hooks/CLAUDE.md` (prompt/adapter layout rules)
- (Optional, follow-up) new `ll-verify` check + `scripts/tests/` coverage

### Dependent Files (Callers/Importers)
- No code imports `.claude/CLAUDE.md` (it is host-loaded context, not a module),
  so there are no Python callers to update.
- **Relative-link hazard**: the Loop Authoring section currently links
  `[docs/guides/HARNESS_OPTIMIZATION_GUIDE.md](../docs/guides/HARNESS_OPTIMIZATION_GUIDE.md)`
  relative to `.claude/CLAUDE.md`. Moving that block to
  `scripts/little_loops/loops/CLAUDE.md` changes the relative depth — the link
  must be re-pathed (or made repo-root-relative) or it breaks `ll-check-links`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/apply-research.yaml` — `load_context` state runs
  `head -60 .claude/CLAUDE.md`; after the Loop Authoring block moves to the
  nested file, this project-context snapshot will silently omit MR-1…MR-5 rules.
  Either extend the shell action to also cat the new nested file, or document the
  reduced context as a known limitation. [Agent 2 finding]
- `skills/improve-claude-md/SKILL.md` (Step CT-1 dedup grep) — the dedup step
  greps only `$FILE_ARG` (always resolves to root `.claude/CLAUDE.md` by default).
  After the split, rules that were moved to nested files will not appear in the
  dedup grep, causing the skill to report them as `OPEN` and propose re-adding
  them to root. This is silent wrong behavior (not a hard failure). Either update
  Step CT-1 to also grep nested CLAUDE.md files, or note this as a known
  post-split scope gap in the skill's documentation. [Agent 2 finding]

### Similar Patterns
- No existing nested `CLAUDE.md` in the repo (confirmed: only
  `./.claude/CLAUDE.md`), so this establishes the co-location convention.
- The optional verify check should mirror the existing `ll-verify-*` family for
  consistency: `ll-verify-docs`, `ll-verify-skills`, `ll-verify-skill-budget`,
  `ll-verify-triggers`, `ll-check-links` (all `little_loops.cli:main_verify_*`
  entry points in `scripts/pyproject.toml`).

### Tests
- Core reorganization (steps 1–4) has no automated test — verified manually via
  `/context` (see Implementation Steps 4). This is why the issue is
  `testable: false`.
- If the optional `ll-verify` check (step 5) ships: add coverage under
  `scripts/tests/` following the existing `ll-verify-*` test pattern, and flip
  `testable: true`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_cli_registry.py` — **WILL BREAK** (CI failure):
  `DOC_STRINGS_PRESENT` contains at minimum two parametrized entries that assert
  specific strings exist in `.claude/CLAUDE.md`:
  - `(".claude/CLAUDE.md", "scripts/little_loops/hooks/", "FEAT-1457")`
  - `(".claude/CLAUDE.md", "adapters/", "FEAT-1457")`
  These needles are in the hooks adapter conventions section that moves to
  `scripts/little_loops/hooks/CLAUDE.md`. After the move, those entries fail
  unless either (a) the root retains a pointer line containing those exact
  strings, or (b) the test entries are updated to reference the new nested file
  path. Also audit `FEAT-1462` (`"host_runner"`) and `ENH-1130`
  (`".loops/tmp/scratch/"`) entries against whichever sections move. [Agent 3 finding]

### Documentation
- `CONTRIBUTING.md` and `docs/ARCHITECTURE.md` may describe the monolithic root
  `CLAUDE.md` and should be checked for stale references after the split.
- Many `docs/` files cross-reference CLAUDE.md sections (e.g.
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `LOOPS_GUIDE.md`,
  `docs/reference/API.md`); run `ll-check-links` after moving sections.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/USER_GUIDE_AUDIT_REPORT.md` (lines 50, 93) — prose references
  "CLI tool entries in CLAUDE.md" and "Skill count documented in CLAUDE.md" as a
  single-source fact; after the split these remain in root, but the report's framing
  as a monolithic file becomes inaccurate. Verify after the split whether entries
  still hold. [Agent 1 finding]

### Configuration
- N/A for the core move. The optional verify check would add one
  `[project.scripts]` entry point to `scripts/pyproject.toml`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Hard link re-pathing targets (will break `ll-check-links` after the Loop Authoring move):**
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` lines 86, 243 — two occurrences of `../../.claude/CLAUDE.md` → `../../scripts/little_loops/loops/CLAUDE.md`
- `docs/guides/LOOPS_GUIDE.md` line 3626 — `[CLAUDE.md § Loop Authoring](../../.claude/CLAUDE.md)` → same re-pathing

**Prose-only references (no link break, but text becomes inaccurate after split):**
- `CONTRIBUTING.md` line 356 — table row references `.claude/CLAUDE.md`
- `docs/reference/COMMANDS.md` line 466 — `improve-claude-md` command description

**Optional `ll-verify-claude-context` (step 5) — three-file touch:**
- New: `scripts/little_loops/cli/verify_claude_context.py` — `main_verify_claude_context()` following `main_verify_skills()` in `scripts/little_loops/cli/docs.py`
- Edit: `scripts/little_loops/cli/__init__.py` lines 44–49, 108–111 — add import + `__all__` entry
- Edit: `scripts/pyproject.toml` under `[project.scripts]` — `ll-verify-claude-context = "little_loops.cli:main_verify_claude_context"`
- Test: `scripts/tests/test_cli_docs.py` — follow existing `ll-verify-*` test patterns there

**Nested `CLAUDE.md` content inventory (conventions found in code, beyond what the issue already specifies):**

`scripts/little_loops/loops/CLAUDE.md` — in addition to Loop Authoring + MR-1…MR-5, include:
- **Bash variable escaping**: `action:` block shell variables must use `$${VAR}` (not `${VAR}`) to prevent FSM interpolation before the shell sees the variable
- **Fragment library usage**: `import: [lib/common.yaml]` at loop top-level; reference via `fragment: <name>` in state definitions; `lib/` = non-runnable fragments; top-level = runnable loops; `oracles/` = runnable oracle loops
- **`circuit:` block fields**: `window`, `on_repeated_failure`, `exclude_paths` (used in `general-task.yaml`)

`scripts/little_loops/hooks/CLAUDE.md` — include:
- One module per intent, each exporting exactly `handle(event: LLHookEvent) -> LLHookResult` (types in `scripts/little_loops/hooks/types.py`)
- New intent checklist: (1) module under `scripts/little_loops/hooks/`, (2) entry in `_dispatch_table()` in `__init__.py:_dispatch_table`, (3) update `_USAGE` constant, (4) adapter script(s) in `hooks/adapters/<host>/`, (5) entry in `hooks/hooks.json`
- Exit code semantics: `0` = pass-through; `2` = block + inject feedback into model context

`hooks/CLAUDE.md` — include:
- **Adapter minimalism**: adapter scripts must only set `LL_HOOK_HOST` (Codex only) and pipe stdin to `python -m little_loops.hooks <intent>` — any logic beyond this flips Codex's trust status and forces user re-trust (documented in `hooks/adapters/codex/` comments)
- **Prompt template convention**: new templates go in `hooks/prompts/` using `{{PLACEHOLDER}}` syntax; loaded at runtime via `Path(__file__).resolve().parents[3] / "hooks" / "prompts" / <name>` (established in `user_prompt_submit.py:_PROMPT_FILE`)
- **Event registry**: `hooks/hooks.json` is the single source of truth for registered event types and timeouts; new intents require an entry here

## Scope Boundaries

In scope:
- Moving location-specific sections from root `.claude/CLAUDE.md` into nested
  `CLAUDE.md` files at the named durable boundaries (loops, hooks).
- Adding the DOX precedence rule and one-line pointers to root.

Out of scope:
- **Rewriting rule content** — sections move verbatim (preserve ENH references);
  no behavioral rule changes.
- **The optional `ll-verify` gate (step 5)** — explicitly a follow-up; the core
  ships without it.
- **AGENTS.md / DOX framework adoption** — only the co-location *idea* is
  borrowed, not the honor-system tooling.
- **Reorganizing non-`CLAUDE.md` docs** — the flat `docs/` tree is unchanged.
- **The flat `core/RULES.md` decomposition from ENH-278** — deferred to the
  hybrid question in Open Questions, not part of this change.

## Impact

- **Priority**: P3
- **Effort**: Low (mechanical move) — Medium if the optional verify check ships
- **Risk**: Low — reorganization only, no behavioral rule changes; main risk is
  a nested doc silently not loading, mitigated by the `/context` verification
  step.
- **Breaking Change**: No

## Open Questions

- Confirm Claude Code's nested-`CLAUDE.md` auto-load semantics (loads when CWD /
  edited file is within the subtree) match the assumed behavior before relying
  on it for critical rules like MR-1.
- Should the flat-`core/` idea from ENH-278 still cover truly global behavioral
  rules (principles/style), with co-located docs handling only location-specific
  rules? Possibly a hybrid.

## Session Log
- `/ll:wire-issue` - 2026-06-10T04:50:43 - `7b22612d-4a83-4078-bae9-22b2686b4ac6.jsonl`
- `/ll:refine-issue` - 2026-06-10T04:41:43 - `2e0448dd-be80-44fc-a9c5-493f4e1343b7.jsonl`
- `/ll:format-issue` - 2026-06-10T04:33:27 - `a169cf57-e620-4e48-972e-dd9665d2a3ce.jsonl`
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:format-issue` - 2026-06-09T18:20:06 - `f0b9ba1f-183d-434e-8ac8-158f3081ee9d.jsonl`
- `/ll:capture-issue` - 2026-06-09T18:14:42Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99d80192-68ec-4cb3-941a-f77e8c20623b.jsonl`

---

## Status

**Open** | Created: 2026-06-09 | Priority: P3
