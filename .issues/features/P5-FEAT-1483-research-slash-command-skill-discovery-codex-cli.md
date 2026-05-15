---
id: FEAT-1483
type: FEAT
priority: P5
status: done
captured_at: '2026-05-15T20:37:29Z'
completed_at: '2026-05-15T23:02:13Z'
discovered_date: 2026-05-15
discovered_by: capture-issue
parent: FEAT-957
decision_needed: false
confidence_score: 100
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
---

# FEAT-1483: Research Slash-Command and Skill Discovery for Codex CLI

## Summary

ll's commands (`commands/*.md`) and skills (`skills/*/SKILL.md`) are natively discoverable by Claude Code via its plugin SDK. Codex CLI has no known equivalent plugin/command-discovery API. This issue tracks researching whether such a mechanism exists — and if so, what wiring is needed to make ll commands and skills discoverable from within a Codex session.

## Current Behavior

`hooks/adapters/codex/README.md` notes:

> Out of scope (tracked separately): … slash-command and skill discovery for Codex

No wiring exists. Codex users can manually invoke `ll-action` or `ll-auto` from a terminal, but cannot discover or invoke `/ll:*` commands from within an active Codex session.

## Expected Behavior

After this research spike:
- Document whether Codex CLI exposes a plugin/command-discovery API (analogous to Claude Code's `.claude-plugin/plugin.json`)
- If yes: produce a follow-on implementation issue with specific wiring steps
- If no: document the gap and close; revisit when Codex adds extensibility

## Use Case

A developer running an active Codex CLI session wants to invoke ll commands (e.g., capture a new issue, run code checks) without dropping out to a terminal. Currently there is no in-session discovery mechanism for Codex users — they must call `ll-action` or `ll-auto` externally. This research spike determines whether the Codex Skills API provides the surface needed to make ll commands first-class in a Codex session.

## Acceptance Criteria

- [ ] `thoughts/research/codex-command-discovery.md` exists, documents the `~/.codex/skills/<name>/SKILL.md` + `agents/openai.yaml` format, and records the compatibility gap analysis vs. ll's existing SKILL.md frontmatter
- [ ] `docs/reference/HOST_COMPATIBILITY.md` footnote `[^cmds]` updated to reference `~/.codex/skills/` (replacing `.codex/prompts/`) and the two Codex parity matrix `✗` cells are corrected to reflect research outcome
- [ ] `hooks/adapters/codex/README.md` "Out of scope" note updated to reflect research findings (Codex Skills API confirmed stable)
- [ ] Two follow-on FEATs filed as children of `EPIC-1463` (FEAT-A: adapt SKILL.md for Codex; FEAT-B: slash-command bridge / document gap), or closure note if deferred
- [ ] `scripts/tests/test_feat1483_doc_wiring.py` created, asserting `HOST_COMPATIBILITY.md` references `~/.codex/skills/`, `codex-command-discovery.md` exists, and codex README out-of-scope note is updated

## Motivation

Command discovery is what makes ll feel native inside an agent session rather than an external tool. Claude Code users get `/ll:capture-issue`, `/ll:check-code`, etc. as first-class commands. Codex users get nothing from within the session. Closing this parity gap (if the API exists) would be the highest-value codex integration work remaining.

## Proposed Solution

### Research Phase

1. **Check Codex CLI docs** for plugin, extension, or command-registration concepts:
   - `codex --help` and any `codex plugin` / `codex extension` subcommands
   - GitHub: `openai/codex` README and docs directory
   - Any `PLUGIN.md`, `extensions.md`, or API reference in the Codex CLI repo
2. **Check for config-file extensibility** — does `.codex/config.toml` support a `commands` or `tools` section analogous to Claude Code's `.claude-plugin/`?
3. **Check hooks as a proxy** — can a hook respond to slash-commands typed in the Codex TUI? (Likely no, but worth confirming.)
4. **Summarize findings** in `thoughts/research/codex-command-discovery.md`

### Decision Tree

```
Codex has a plugin/command API?
├── Yes → File FEAT-XXXX: Implement ll command wiring for Codex plugin API
│          with specific implementation steps derived from the research
└── No  → Document gap in thoughts/research/codex-command-discovery.md
           Update hooks/adapters/codex/README.md "Out of scope" note
           Close this issue as "deferred pending Codex extensibility"
```

## Integration Map

### Files to Create

- `thoughts/research/codex-command-discovery.md` — research findings

### Files to Potentially Modify (if API exists)

- `hooks/adapters/codex/README.md` — update out-of-scope note
- `.claude-plugin/plugin.json` equivalent for Codex — TBD
- `docs/reference/HOST_COMPATIBILITY.md` — update `[^cmds]` footnote and parity matrix `✗` cells after research concludes (regardless of whether a discovery API exists) [Agent 2 finding]
- `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md` — replace `(unfiled)` child-issue entries with actual filed FEAT IDs after filing follow-ons [Agent 2 finding]

### Files to Reference

- `.claude-plugin/plugin.json` — Claude Code's command-discovery manifest (template)
- `hooks/adapters/codex/README.md` — current out-of-scope note
- `hooks/adapters/opencode/` — TypeScript/Bun plugin pattern (may be analogous if Codex gains a similar model)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Primary research lead**: `docs/reference/HOST_COMPATIBILITY.md` (lines 44–52) — the parity matrix footnote `[^cmds]` already documents that **Codex reads `.codex/prompts/`** for slash-command discovery. The research question is now more targeted: what is the `.codex/prompts/` file format, and does Codex have any equivalent surface for skills/agents?

- `docs/reference/HOST_COMPATIBILITY.md` — parity matrix showing `✗` for both Codex command and skill discovery; footnote `[^cmds]` records the known path (`.codex/prompts/`) and two implementation options; **must be updated** after research resolves the format question
- `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md` — umbrella epic that already has the two follow-on FEATs outlined as `(unfiled)`: slash-command bridge via `.codex/prompts/` and skill discovery (or permanent-gap documentation); file against this epic when closing or spawning follow-ons
- `thoughts/research/codex-headless-invocation.md` — **format template** for the output artifact `thoughts/research/codex-command-discovery.md`; follow its `Status/Sources/Flag-table/Capability-map/Gating-recommendation` structure; also notes that the `codex` binary is **not installed on the dev host** (last verified 2026-05-15) — external research required
- `hooks/adapters/opencode/index.ts` — TypeScript/Bun plugin via `@opencode-ai/plugin` v1.2.27; **not analogous** to Codex — Codex is Rust-based with no TypeScript SDK (confirmed in `hooks/adapters/codex/README.md`); plugin surface in OpenCode only wires hook events, not command/skill discovery anyway
- `scripts/little_loops/host_runner.py:HostCapabilities` — frozen dataclass with capability flags (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`); if research confirms a Codex command-discovery API, a `command_discovery` flag may be warranted here for the orchestration layer

### Local CLI Research Findings (2026-05-15)

_Added by `/ll:refine-issue` — from running `codex` locally (npm-installed v0.x):_

**Codex Skills API: CONFIRMED (stable)**

`codex` has a native skills extension system — the research answer is YES. Key API surfaces:

- **Skills directory**: `~/.codex/skills/<skill-name>/` — each skill is a folder with at minimum a `SKILL.md`
- **`SKILL.md` frontmatter** (required):
  ```yaml
  name: skill-name           # required; identifies the skill; no equivalent in ll SKILL.md
  description: When/why to use this skill (used by Codex to decide when to activate it)
  metadata:
    short-description: One-line UI label
  ```
  Body: Markdown instructions loaded into context only after the skill is triggered
- **UI metadata** (`agents/openai.yaml`, recommended):
  ```yaml
  interface:
    display_name: "Human Name"
    short_description: "One-line chip label"
    icon_small: "./assets/icon-small.svg"
    icon_large: "./assets/icon.png"
  ```
- **Optional bundled resources**: `scripts/`, `references/`, `assets/`
- **Installation paths**:
  - `codex plugin marketplace add <source>` — supports `owner/repo[@ref]`, HTTP/HTTPS Git URLs, SSH URLs, local dirs; `--sparse <PATH>` installs a subtree
  - Built-in `skill-installer` skill: `scripts/install-skill-from-github.py --repo <owner>/<repo> --path <path/to/skill>`
  - Skills install into `$CODEX_HOME/skills/<skill-name>` (default `~/.codex/skills`)
  - After install: user must restart Codex to pick up new skills

**No `.codex/prompts/` slash-command surface found**

- No `~/.codex/prompts/` directory exists on the dev host; no `prompts`-related config in `codex --help` or `~/.codex/config.toml`
- The `[^cmds]` footnote's reference to `.codex/prompts/` appears to describe a mechanism not present in the current Codex CLI; skills are the effective slash-command analogue
- Feature flags: `plugins = stable`, `hooks = stable`, `plugin_hooks = under development` (not yet stable)

**ll `skills/*/SKILL.md` compatibility gap**

ll's existing `skills/*/SKILL.md` frontmatter uses different keys (`description`, `argument-hint`, `allowed-tools`, `arguments`) — not directly Codex-compatible. What's needed:
1. Add `name:` field to each SKILL.md (Codex requires it; Claude Code doesn't use it)
2. Add `agents/openai.yaml` to each skill directory (UI metadata)
3. Register via `codex plugin marketplace add BrennonTWilliams/little-loops --sparse skills` (or individual install via `skill-installer`)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner.py` — conditional: if `command_discovery: bool = False` is added to `HostCapabilities` in a follow-on issue, update `TestCodexRunner::test_capabilities_disable_agent_and_tools` (line 278–283) to assert the new field; follow the existing pattern of one assertion per capability flag [Agent 3 finding]
- `docs/reference/API.md` — conditional: if `command_discovery` flag is added, the `HostCapabilities` fields table under `little_loops.host_runner` needs a new row [Agent 2 finding]
- `docs/ARCHITECTURE.md` — conditional: if `command_discovery` flag is added, the "Host Runner Layer" field enumeration `(streaming, permission_skip, agent_select, tool_allowlist)` becomes stale [Agent 2 finding]
- `scripts/tests/test_feat1462_doc_wiring.py` — update `TestHostCompatibilityWiring` to add a test case asserting `~/.codex/skills/` (or `codex/skills`) appears in `HOST_COMPATIBILITY.md` after the `[^cmds]` footnote is revised; the class already checks for "Orchestration" and "Pi" tokens — follow the same `assert "token" in content` pattern [Agent 3 finding]
- `scripts/tests/test_feat1483_doc_wiring.py` — new test file to create, following the `test_feat1462_doc_wiring.py` skeleton; assert: (a) `HOST_COMPATIBILITY.md` no longer references `.codex/prompts/` (or references `~/.codex/skills/`), (b) `thoughts/research/codex-command-discovery.md` exists, (c) `hooks/adapters/codex/README.md` "Out of scope" section is updated [Agent 3 finding]

## Implementation Steps

1. Read Codex CLI docs and GitHub repo for plugin/extension/command concepts
2. Run `codex --help` and explore all subcommands
3. Check `.codex/config.toml` schema for extensibility fields
4. Document findings in `thoughts/research/codex-command-discovery.md`
5. File follow-on implementation issue OR close as deferred

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 0 (before external research)**: Read `docs/reference/HOST_COMPATIBILITY.md` footnote `[^cmds]` and `EPIC-1463` — both already document that Codex reads `.codex/prompts/` and outline the two implementation paths; this narrows Step 1 to verifying the `.codex/prompts/` format and discovering any skill/agent surface
- **Step 2 caveat**: ~~`codex` binary is not installed on the dev host~~ — `codex` is now installed via npm (2026-05-15); `codex --help` and subcommand exploration can be run locally
- **Step 3 refinement**: Check `~/.codex/config.toml` (user-level, not project-level) in addition to `.codex/config.toml` — the trust-hash mechanism documented in `hooks/adapters/codex/README.md` shows that user config lives at `~/.codex/config.toml`; look for a `[commands]` or `[plugins]` section
- **Output artifact format**: Follow `thoughts/research/codex-headless-invocation.md` structure (`Status`, `Sources`, table, `Capability map`, `Gating recommendation`) when writing `thoughts/research/codex-command-discovery.md`
- **Binary available**: `codex` installed via npm on dev host (2026-05-15) — all steps can be run locally; no need for GitHub-only research path
- **Step 5 filing target**: File any follow-on FEATs as children of `EPIC-1463` (it already has the two `(unfiled)` slots: slash-command bridge + skill discovery)
- **CLI research outcome (2026-05-15)**: Research question answered — Codex Skills API is **confirmed stable**. Steps 1–3 are now complete. Remaining actions:
  - Step 4: Write `thoughts/research/codex-command-discovery.md` documenting the `~/.codex/skills/` API (not `.codex/prompts/`), the SKILL.md + `agents/openai.yaml` format spec, and the compatibility gap analysis vs. ll's existing SKILL.md frontmatter
  - Step 5: File two follow-on FEATs as children of `EPIC-1463`:
    - **FEAT-A** (skill-discovery): Adapt ll's `skills/*/SKILL.md` for Codex — add `name:` to frontmatter, add `agents/openai.yaml` per skill, register via `codex plugin marketplace add`
    - **FEAT-B** (slash-command bridge, tentative): Document that no `.codex/prompts/` slash-command surface exists; update `[^cmds]` footnote in `HOST_COMPATIBILITY.md` to reflect skills-only extensibility
  - **Update `[^cmds]` footnote** in `docs/reference/HOST_COMPATIBILITY.md`: replace `.codex/prompts/` reference with `~/.codex/skills/` and correct both parity matrix cells for Codex

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/HOST_COMPATIBILITY.md` — revise `[^cmds]` footnote and the `✗` cells in the "Slash-command and skill discovery" parity row to reference `thoughts/research/codex-command-discovery.md` and reflect the research outcome
7. Update `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md` — replace the two `(unfiled)` child-issue entries with actual filed FEAT IDs (or a "closed as deferred" note if no API exists)
8. Update `scripts/tests/test_feat1462_doc_wiring.py` — add test case to `TestHostCompatibilityWiring` asserting `~/.codex/skills/` appears in `HOST_COMPATIBILITY.md`; follow existing `assert "token" in content` pattern
9. Create `scripts/tests/test_feat1483_doc_wiring.py` — doc-wiring test verifying: (a) `HOST_COMPATIBILITY.md` references `~/.codex/skills/`, (b) `thoughts/research/codex-command-discovery.md` exists, (c) `hooks/adapters/codex/README.md` "Out of scope" note is updated; follow `test_feat1462_doc_wiring.py` skeleton

## Impact

- **Scope**: Research only — no code changes in this issue
- **Risk**: None
- **Dependency note**: This is blocked by Codex CLI's own extensibility roadmap; if the API doesn't exist today, this issue should be re-evaluated with each major Codex release

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `hooks/adapters/codex/README.md` | Current out-of-scope note on command discovery |
| `.claude-plugin/plugin.json` | Claude Code command manifest (reference for what we'd want to replicate) |
| `thoughts/research/codex-headless-invocation.md` | Prior Codex research from FEAT-1465; format template for output artifact |
| `docs/reference/HOST_COMPATIBILITY.md` | Parity matrix; footnote [^cmds] already documents `.codex/prompts/` as the Codex command path and the two implementation options |
| `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md` | Umbrella epic; has `(unfiled)` slots for slash-command bridge FEAT and skill-discovery FEAT |

## Labels

codex, research, commands, skills

---

## Resolution

**Status:** Done (2026-05-15)

- Codex Skills API confirmed stable (`~/.codex/skills/<name>/SKILL.md`).
- No `.codex/prompts/` slash-command surface exists in Codex CLI.
- Created `thoughts/research/codex-command-discovery.md` documenting the Skills API spec,
  compatibility gap vs. ll's SKILL.md frontmatter, and installation methods.
- Updated `docs/reference/HOST_COMPATIBILITY.md`: `[^cmds]` footnote revised to reference
  `~/.codex/skills/`, removed `.codex/prompts/` reference, added FEAT-1483/1486/1487 tracking.
- Updated `hooks/adapters/codex/README.md` "Out of scope" note to reference confirmed API.
- Updated EPIC-1463 children: replaced two `(unfiled)` entries with FEAT-1486 and FEAT-1487.
- Created FEAT-1486 (adapt SKILL.md for Codex) and FEAT-1487 (parity matrix update) as
  children of EPIC-1463.
- Created `scripts/tests/test_feat1483_doc_wiring.py` (10 tests, all passing).
- Added `test_codex_skills_path_present` to `scripts/tests/test_feat1462_doc_wiring.py`.

## Status

**Done** | Created: 2026-05-15 | Completed: 2026-05-15 | Priority: P5

## Session Log
- `/ll:ready-issue` - 2026-05-15T22:58:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1fce2a9a-5f39-49db-8501-6abacda70207.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/242e7bd0-56c9-4de6-a36d-68ac7b97d673.jsonl`
- `/ll:wire-issue` - 2026-05-15T22:53:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99232db3-8d20-454e-8776-772a4ccd707a.jsonl`
- `/ll:refine-issue` - 2026-05-15T22:49:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8ea0b66-61a8-4204-b490-073127e17124.jsonl`
- `/ll:refine-issue` - 2026-05-15T21:25:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c6fcfa4-b17c-4d21-8cbb-87bc6c248119.jsonl`
- `/ll:wire-issue` - 2026-05-15T21:15:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdf8b29b-c64d-4fd5-9d5c-9082345d0652.jsonl`
- `/ll:refine-issue` - 2026-05-15T21:08:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d42dbf9b-cc4b-408b-9155-54a52d42f2f2.jsonl`
- `manual update` - 2026-05-15 - codex installed via npm on dev host; binary blocker resolved, all research steps now runnable locally; `depends_on: FEAT-1481` added
- `/ll:capture-issue` - 2026-05-15T20:37:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ac48eaf-913e-40cd-8b15-98d99f2901cc.jsonl`
- `/ll:manage-issue implement` - 2026-05-15T23:02:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
