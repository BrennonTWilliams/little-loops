---
id: EPIC-3008
title: ll-init / config-schema wiring and UX audit
type: EPIC
status: open
priority: P3
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
testable: false
labels:
- epic
- ll-init
- config-schema
- ux
- docs
---

# EPIC-3008: ll-init / config-schema wiring and UX audit

## Goal

Close the config-schema/`ll-init`/docs drift surfaced by the 2026-08-02
audit: make `cache`/`deferred_tools` config actually take effect, stop
`ll-init` from surfacing raw tracebacks on expected failures, and bring
`docs/reference/CLI.md`, `docs/guides/GETTING_STARTED.md`, and
`docs/reference/CONFIGURATION.md` back in sync with actual code behavior.

## Scope

In scope: the 10 children listed below (config wiring bugs, `ll-init`
error-handling/UX gaps, and doc/schema drift). Out of scope: adding real
JSON-Schema validation at config-load time (a larger design decision, noted
as context below but not an actionable child) and expanding what `ll-init`
prompts for interactively (the current "everyday features only" scope of the
wizard is treated as intentional, not a gap).

## Summary

Three-agent audit of the `ll-init` CLI (entry point, headless/`--plan`/`apply`/TUI
flows) and its relationship to `scripts/little_loops/config-schema.json` (all 38
top-level schema keys cross-referenced against `BRConfig` parsing, real runtime
call sites, `ll-init` prompting, and `docs/reference/CONFIGURATION.md`), plus a
UX/polish pass over user-facing output, error handling, `--help` text, and
doc/code consistency.

Six candidate findings (dead-config-clobbering, null-leaf writes, apply/yes
lossiness, dropped `--upgrade`, missing logo, missing CLI.md docs — formerly
BUG-2310/2311/2313/2755/2439 and ENH-2019) were already fixed and closed; they
are not part of this epic. Everything below is net-new as of the 2026-08-02
audit.

## Context: why these gaps can exist silently

No JSON-Schema validation happens at config-load time anywhere in the codebase —
`jsonschema` isn't even a project dependency (confirmed: `scripts/tests/
test_config_schema.py` explicitly notes its schema tests are "a sentinel guard
rather than runtime validation"). `config-schema.json` functions purely as
defaults-metadata and an IDE-completion hint, consumed by `ll-init` via
`schema_default()`. This is why dead config keys (children #1) and reverse
schema drift (child #6) can persist undetected — nothing currently rejects a
malformed or unused key at runtime. Fixing that gap is a larger design decision
than this audit should decide unilaterally, so it's called out here as shared
context rather than filed as its own child.

Separately: roughly half of the schema's top-level sections (`automation`,
most of `commands`, `scan`, `sprints`, `loops` beyond `run_defaults`,
`compression`, `cache`, `deferred_tools`, `dependency_mapping`, `code_query`,
`tamper_guard`, `cli`, `extensions`, `hooks`, `events`, `observability`,
`orchestration`, `artifacts`, `refine_status`, most of `issues`, `continuation`,
most of `history`, `queue`) are never prompted by `ll-init`/the TUI, relying
entirely on silent schema defaults. This appears to be intentional (keeping the
wizard to the ~13 "everyday" feature toggles) rather than an oversight, and is
noted here for awareness, not as an actionable gap.

## Children

- **BUG-3009** — `cache`/`deferred_tools` config parsed but never threaded into `host_runner` dispatch calls (functionally inert)
- **BUG-3010** — `ll-init` has no top-level exception handling; unexpected errors surface as raw tracebacks despite a documented 0/1/2 exit-code contract
- **ENH-3011** — `ll-init` performs no git-repo check and silently writes/updates `.gitignore` outside a git repo
- **BUG-3012** — `BRConfig.to_dict()` omits `refine_status` and `extensions`, breaking `ll-config get` for those sections
- **ENH-3013** — `config-schema.json`'s `issues` object declares 8 properties that read as per-issue-frontmatter fields, never consumed as global config
- **ENH-3014** — `skill_budget.threshold_tokens` is a real, working config key missing from both `config-schema.json` and `docs/reference/CONFIGURATION.md`
- **ENH-3015** — `docs/reference/CONFIGURATION.md` has no section documenting the top-level `cache` block
- **ENH-3016** — `docs/reference/CLI.md` / `docs/guides/GETTING_STARTED.md` host list omits `kimi-code` and doesn't flag `opencode`/`pi` as recognized-but-unimplemented
- **ENH-3017** — `docs/reference/CLI.md` describes the TUI wizard as 6 screens; code has 7 (missing "Plugin Install" screen, the first thing a new user sees)
- **ENH-3018** — `skills/init/SKILL.md` cites hardcoded `cli.py` line numbers for `_run_plan`/`_run_apply` that have already drifted

## Sequencing and file contention

Children are **not** all independent. Two ordering constraints are declared in
child frontmatter (`depends_on`), not just prose:

- **ENH-3015 `depends_on: [BUG-3009]`** — the `cache` doc section must state
  where `require_repeat` actually takes effect. Until BUG-3009 lands, the honest
  answer is "nowhere," so documenting first ships a doc that's wrong either way.
- **ENH-3017 `depends_on: [ENH-3016]`** — both edit the same `## ll-init`
  section of `docs/reference/CLI.md` (host lists at `:37,49`; wizard table at
  `:65-76`). Serialized to avoid a merge conflict under `parallel.epic_branches`.

Lower-risk overlap to be aware of but not gated: ENH-3014 and ENH-3015 both edit
`docs/reference/CONFIGURATION.md`, in different sections.

Everything else (BUG-3010, ENH-3011, BUG-3012, ENH-3013, ENH-3018) is genuinely
independent and safe to run concurrently.

## Acceptance Criteria

- Each child issue is resolved per its own Acceptance Criteria section (the four
  code children — BUG-3009, BUG-3010, BUG-3012, ENH-3011 — now carry explicit,
  testable ACs rather than relying on this generic epic-level statement).
- Docs children bring `docs/reference/CLI.md`, `docs/guides/GETTING_STARTED.md`,
  `docs/reference/CONFIGURATION.md`, and `config-schema.json` back in sync with
  actual code behavior.
- The two `depends_on` edges above are respected by whatever runs the children
  (sprint ordering or serialized epic branches).
- No regression to existing `scripts/tests/test_init_*.py` or
  `scripts/tests/test_config_schema.py` coverage; `python -m pytest
  scripts/tests/` exits 0 after each child.

## Impact

- **Priority**: P3 — mix of P2 correctness bugs and P3/P4 docs/cleanup; no
  single child is urgent, but the aggregate closes real drift.
- **Effort**: Medium (aggregate) — most children are small, isolated fixes.
- **Risk**: Low — additive/corrective, no architectural changes.
- **Breaking Change**: No.

## Related Key Documentation

- `.claude/CLAUDE.md` — Project Configuration section documents `.ll/ll-config.json`
  and `scripts/little_loops/config-schema.json` as the canonical config schema.
- `docs/reference/CONFIGURATION.md` — full config key reference; several children
  correct gaps in this doc.
- `docs/reference/CLI.md` — `ll-init` CLI reference; several children correct
  gaps in this doc.

## Status

**Open** | Created: 2026-08-02 | Priority: P3
