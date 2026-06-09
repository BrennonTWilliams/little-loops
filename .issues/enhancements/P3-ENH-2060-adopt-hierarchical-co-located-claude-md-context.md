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

### Documentation
- `CONTRIBUTING.md` and `docs/ARCHITECTURE.md` may describe the monolithic root
  `CLAUDE.md` and should be checked for stale references after the split.
- Many `docs/` files cross-reference CLAUDE.md sections (e.g.
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `LOOPS_GUIDE.md`,
  `docs/reference/API.md`); run `ll-check-links` after moving sections.

### Configuration
- N/A for the core move. The optional verify check would add one
  `[project.scripts]` entry point to `scripts/pyproject.toml`.

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

## Open Questions

- Confirm Claude Code's nested-`CLAUDE.md` auto-load semantics (loads when CWD /
  edited file is within the subtree) match the assumed behavior before relying
  on it for critical rules like MR-1.
- Should the flat-`core/` idea from ENH-278 still cover truly global behavioral
  rules (principles/style), with co-located docs handling only location-specific
  rules? Possibly a hybrid.

## Session Log
- `/ll:capture-issue` - 2026-06-09T18:14:42Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99d80192-68ec-4cb3-941a-f77e8c20623b.jsonl`

---

## Status

**Open** | Created: 2026-06-09 | Priority: P3
