---
id: ENH-1495
type: ENH
priority: P3
status: done
captured_at: '2026-05-16T13:04:12Z'
completed_at: '2026-05-16T18:52:52Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
blocked_by:
- FEAT-1493
- FEAT-1496
labels:
- captured
- codex
- docs
- onboarding
testable: false
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1495: Add `docs/codex/` user-facing onboarding walkthrough

## Summary

The repo has `docs/claude-code/` with user-facing onboarding content for Claude Code users, but no equivalent for Codex. `docs/reference/HOST_COMPATIBILITY.md` is maintainer-oriented (a capability matrix), not a walkthrough. New Codex users have no entry-point doc explaining how to install, configure, and use little-loops with the Codex CLI.

## Current Behavior

- `docs/claude-code/` — exists, contains user-facing setup and usage guidance
- `docs/codex/` — does not exist
- `docs/reference/HOST_COMPATIBILITY.md` — capability matrix, requires reading to understand which features map across hosts; not an onboarding doc
- `hooks/adapters/codex/README.md` — adapter-internal documentation about hook shims and trust hashes; not user-facing

A Codex user has to read three different files to assemble a mental model of how to set up and run ll.

## Expected Behavior

A new `docs/codex/` directory exists with at least:

- `docs/codex/README.md` — landing page: what works, what doesn't, how to install
- `docs/codex/getting-started.md` — install steps (including `/ll:init --codex`), trust prompt walkthrough, first-run verification
- `docs/codex/usage.md` — running ll-auto/ll-parallel/ll-sprint/ll-loop under `LL_HOST_CLI=codex`, invoking skills, current limitations (no `--agent` / `--tools` translation)

Top-level `README.md` links to `docs/codex/` alongside `docs/claude-code/`.

## Motivation

Codex integration is technically present (host runner, hook adapter, skills adaptation all implemented and tested), but a new user has no obvious starting point. The audit's recommendation: "claim first-class parity" requires not just code, but discoverability. A 15-minute walkthrough doc closes the gap between "works if you know what to do" and "works if you read the README".

## Success Metrics

- `docs/codex/` directory exists with all three planned files (README.md, getting-started.md, usage.md)
- `ll-check-links` passes on all new pages (no broken links)
- Top-level `README.md` links to `docs/codex/` alongside `docs/claude-code/`

## Proposed Solution

1. Study style from `docs/claude-code/cli-programmatic-usage.md` (getting-started style: Basic usage → Examples → Next steps) and `docs/claude-code/checkpointing.md` (limitations section pattern). Note: `docs/claude-code/` is a scraped upstream platform reference archive — there are no README.md, getting-started.md, or usage.md files there to mirror structurally. The three new files must be created from scratch.
2. Pull existing content from `hooks/adapters/codex/README.md` (trust-model section, install steps, event→intent mapping, fire-and-forget pattern) and rewrite for a user audience
3. Also pull from `docs/reference/HOST_COMPATIBILITY.md` (Installation table, Config probe path table, Orchestration CLI ✓ table), `docs/guides/GETTING_STARTED.md` (lines 87–90, `--codex` flag description), and `docs/development/TROUBLESHOOTING.md` (Codex-specific troubleshooting: binary detection, `chmod` adapter scripts, `LL_HOOK_HOST=codex` smoke-test)
4. Add a "Current Limitations" section covering: deferred hook intents (`stop`, `post_compact`, `permission_request`), `pre_tool_use` opt-in only, `--agent` and `--tools` not supported by `CodexRunner` (emit `CapabilityNotSupported`), inline `json_schema` unsupported, `ll-doctor check` not yet available (FEAT-1496 in progress — FEAT-1523/FEAT-1503/FEAT-1504)
5. Run `ll-adapt-skills-for-codex --apply` as a verified install step (skill and command discovery is how Codex users invoke `/ll:*` commands)
6. Add Codex install path to top-level `README.md` Install section (currently Claude Code-exclusive; does not reference `docs/claude-code/` — add a new "Codex CLI" subsection or note alongside the existing install steps) and cross-link from `docs/reference/HOST_COMPATIBILITY.md`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`docs/codex/README.md` content outline:**
- What works: hook intents (`session_start` startup-only, `pre_compact`, `user_prompt_submit`, `post_tool_use` fire-and-forget), orchestration CLIs (all ✓), skill/command discovery via `ll-adapt-skills-for-codex --apply`
- What is deferred: `stop`, `post_compact`, `permission_request` (no current consumer); `pre_tool_use` opt-in
- Where to get help: links to getting-started.md, usage.md, HOST_COMPATIBILITY.md

**`docs/codex/getting-started.md` content outline:**
- Prerequisites: `codex` binary on PATH, `pip install little-loops`
- Install: `/ll:init --codex` (or auto-detected when `codex` is on PATH or `.codex/` exists) — writes `.codex/hooks.json` from `hooks/adapters/codex/hooks.json` template with `{{LL_PLUGIN_ROOT}}` substituted
- Trust prompt: Codex shows a hook-trust dialog on first session start; must choose "Trust All" or "Review Hooks" — hooks silently skip if not trusted. Trust key format: `file:<project>/.codex/hooks.json:<event>:0:0`. Hash lives in `~/.codex/config.toml`. Script body edits do NOT invalidate the hash; only `hooks.json` path/timeout/matcher changes do.
- Config file: `.codex/ll-config.json` (probed before `.ll/ll-config.json`); all other state dirs (`.issues/`, `.loops/`, etc.) use default project-root paths regardless of host
- Skill discovery: run `ll-adapt-skills-for-codex --apply` once after install — bridges `skills/*/SKILL.md` and `commands/*.md` into `~/.codex/skills/<name>/SKILL.md`
- Smoke test: reference `scripts/tests/test_codex_adapter.py` pattern for manual verification

**`docs/codex/usage.md` content outline:**
- Running orchestration CLIs: `LL_HOST_CLI=codex ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, `ll-sprint` (all ✓)
- Auto-detection: `LL_HOST_CLI` env var, or `LL_HOOK_HOST=codex`, or binary probe; `apply_host_cli_from_config()` reads `config.orchestration.host_cli`
- Invoking skills: `/ll:<name>` via Codex slash-command after `ll-adapt-skills-for-codex --apply`
- Opt-in `pre_tool_use`: add manual JSON block to `.codex/hooks.json`
- Current Limitations: `--agent` (persona selection) → `CapabilityNotSupported`, silently dropped; `--tools` → sandbox modes only; `json_schema` → NDJSON only (no inline dict); `ll-doctor check` coming soon (FEAT-1496 via FEAT-1523/FEAT-1503/FEAT-1504)

## Integration Map

### Files to Create
- `docs/codex/README.md`
- `docs/codex/getting-started.md`
- `docs/codex/usage.md`

### Files to Modify
- `README.md` — add Codex entry alongside Claude Code section
- `docs/reference/HOST_COMPATIBILITY.md` — cross-link to the new user docs

### Source Files (Content to Lift and Rewrite)
- `hooks/adapters/codex/README.md` — trust model, install steps, event→intent mapping, fire-and-forget pattern, state directory behavior, smoke test reference
- `docs/reference/HOST_COMPATIBILITY.md` — Installation table (lines 146–151), Config probe path table (lines 117–126), Orchestration CLI table (lines 93–99), deferred/opt-in intent rows
- `docs/guides/GETTING_STARTED.md` (lines 87–90) — `--codex` flag description for init flags table
- `docs/development/TROUBLESHOOTING.md` — Codex binary detection, `chmod` adapter scripts, `LL_HOOK_HOST=codex` smoke-test invocation

### Style Reference (Not Structural Template)
- `docs/claude-code/cli-programmatic-usage.md` — getting-started style: Basic usage → Examples → Next steps
- `docs/claude-code/checkpointing.md` — limitations section pattern with named subsections

### Dependent Files (Callers/Importers)
- N/A — documentation changes have no callers or importers

### Registration / Navigation Files

_Wiring pass added by `/ll:wire-issue`:_
- `mkdocs.yml` — `nav:` block has a `Claude Code:` section (three pages) but no `Codex:` section; new `docs/codex/` pages will be built but invisible in the sidebar without a nav entry [Agent 1 finding]
- `docs/index.md` — "User Documentation" section enumerates hosted doc pages but has no Codex entry; `docs/codex/` would be absent from the documentation index [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1495_doc_wiring.py` — new test file needed following the `test_*_doc_wiring.py` pattern (used in `test_enh1362`, `test_feat1457`, `test_feat1483`, etc.); assert: `docs/codex/README.md` exists, `docs/codex/getting-started.md` exists, `docs/codex/usage.md` exists, `HOST_COMPATIBILITY.md` references `docs/codex/`, `README.md` references Codex [Agent 3 finding]
- `scripts/tests/test_readme_structure.py::TestReadmeIsHeroPage::test_readme_is_under_200_lines` — runs against real `README.md`; currently 184 lines; adding a Codex install subsection risks approaching the 200-line limit — keep the addition brief or update the assertion threshold [Agent 3 finding — risk to watch]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` — "Project Structure" ASCII tree block enumerates `docs/claude-code/` but has no `codex/` entry; adding `docs/codex/` without updating this leaves the directory absent from the contributor-facing structure diagram [Agent 2 finding]

### Configuration
- N/A — no configuration changes

## Implementation Steps

1. Read `docs/claude-code/cli-programmatic-usage.md` and `docs/claude-code/checkpointing.md` for heading/section style reference (H1 → H2 sections → See also/Next steps; named subsections under Limitations)
2. Draft `docs/codex/README.md`: landing page summarizing what works (hook intents, orchestration CLIs, skill discovery), what is deferred (stop/post_compact/permission_request), and links to getting-started.md and usage.md. Source: `hooks/adapters/codex/README.md` overview + `HOST_COMPATIBILITY.md` Codex column summary.
3. Draft `docs/codex/getting-started.md`: prerequisites (`codex` binary + `pip install little-loops`), install step (`/ll:init --codex` or auto-detection), trust-prompt walkthrough (four trust states, trust key format, `~/.codex/config.toml`), config file location (`.codex/ll-config.json`), skill discovery (`ll-adapt-skills-for-codex --apply`), smoke-test verification. Source: `hooks/adapters/codex/README.md` Trust Model section (lines 132–175) + Installation section (lines 17–27) + `docs/guides/GETTING_STARTED.md:87-90`.
4. Draft `docs/codex/usage.md`: orchestration CLI invocations (`LL_HOST_CLI=codex ll-auto/ll-parallel/ll-action/ll-loop/ll-sprint`), skill invocation via `/ll:<name>`, opt-in `pre_tool_use` manual config, Current Limitations section (with named subsections for `--agent`, `--tools`, `json_schema`, `ll-doctor` coming soon referencing FEAT-1496/FEAT-1523). Source: `HOST_COMPATIBILITY.md` Orchestration CLI table + `scripts/little_loops/host_runner.py` `CodexRunner.capabilities`.
5. Add Codex install path to top-level `README.md` Install section: add a "Codex CLI" note or subsection with `pip install little-loops` + `/ll:init --codex`; current Install section is Claude Code-exclusive.
6. Add cross-link to `docs/codex/` from `docs/reference/HOST_COMPATIBILITY.md` (a "User onboarding" row in the Installation table or a See also section).
7. Run `ll-check-links docs/codex/` — must exit 0 before marking done.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `mkdocs.yml` — add a `Codex:` nav group under `nav:` parallel to the existing `Claude Code:` section, listing `codex/README.md`, `codex/getting-started.md`, `codex/usage.md`; without this the new pages are built but invisible in the sidebar
9. Update `docs/index.md` — add a Codex subsection in the "User Documentation" section linking to the three new pages
10. Update `CONTRIBUTING.md` — add `codex/` entry to the "Project Structure" ASCII tree block under `docs/`
11. Create `scripts/tests/test_enh1495_doc_wiring.py` — follow the `test_*_doc_wiring.py` pattern (see `test_feat1457_doc_wiring.py` for nav/index assertions, `test_enh1362_doc_wiring.py` for file-existence pattern); assert: all three `docs/codex/*.md` files exist, `HOST_COMPATIBILITY.md` references `docs/codex/`, `README.md` references Codex; keep README.md additions brief (currently 184 lines — 200-line limit in `test_readme_structure.py::test_readme_is_under_200_lines`)

## Scope Boundaries

- **In scope**: `docs/codex/` directory (README.md, getting-started.md, usage.md); cross-links from top-level `README.md` and `docs/reference/HOST_COMPATIBILITY.md`
- **Out of scope**: Feature parity work tracked by EPIC-1463 (tool/agent flag support, etc.); changes to `docs/claude-code/`; Codex adapter code changes; rewriting `hooks/adapters/codex/README.md` (only reference it as a source)

## Impact

- **Priority**: P3 — Visible-to-users parity item, but not blocking
- **Effort**: Small/Medium — mostly content; little code
- **Risk**: Low — Docs only
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Source of truth for what works; the new docs translate this for users. Installation table (lines 146–151), Config probe table (lines 117–126), Orchestration CLI table (lines 93–99). |
| `hooks/adapters/codex/README.md` | Trust model, event→intent mapping, install flow, fire-and-forget pattern — primary source for getting-started.md |
| `docs/guides/GETTING_STARTED.md` | Lines 87–90: `--codex` flag description, init flags table |
| `docs/development/TROUBLESHOOTING.md` | Codex-specific troubleshooting section: binary detection, chmod scripts, LL_HOOK_HOST smoke test |
| `scripts/little_loops/host_runner.py` (`CodexRunner`) | Definitive list of supported/unsupported capabilities (`capabilities` field, `build_streaming`, `build_blocking_json`) |
| `.claude/CLAUDE.md` | Lists `ll-adapt-skills-for-codex` and Codex-related CLI tools |
| `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md` | Full scope of remaining gaps; what "Current Limitations" must cover |
| `.issues/features/P4-FEAT-1496-host-capability-preflight-check.md` | ll-doctor coming-soon note; --agent/--tools capability gap description |

## Labels

`enh`, `captured`, `codex`, `docs`, `onboarding`

## Status

**Open** | Created: 2026-05-16 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-16T18:47:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b419efc-0732-45e0-82f9-b8b4c4d4e81a.jsonl`
- `/ll:confidence-check` - 2026-05-16T19:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ba4c5ec-2d42-4053-a848-118900b7348b.jsonl`
- `/ll:wire-issue` - 2026-05-16T18:43:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94688b95-bc32-436c-8b56-9743e9e09c95.jsonl`
- `/ll:refine-issue` - 2026-05-16T18:39:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6487f336-e8fe-42e7-b7a7-05842c2215c1.jsonl`
- `/ll:format-issue` - 2026-05-16T18:27:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4b5d3d5-e5c5-4a85-bbdf-08e895ec5704.jsonl`
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`
