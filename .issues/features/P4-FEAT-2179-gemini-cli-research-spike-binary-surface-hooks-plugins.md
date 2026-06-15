---
id: FEAT-2179
title: Research spike — gemini-cli binary surface, hook events, and plugin discovery
type: feature
status: done
priority: P4
parent: EPIC-2178
captured_at: "2026-06-15T17:09:51Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
labels: [research, gemini, host-compat, spike]
---

# FEAT-2179: Research spike — gemini-cli binary surface, hook events, and plugin discovery

## Summary

Before any gemini-cli adapter code lands, we need to know what the `gemini`
binary actually supports. This research spike audits the CLI surface, lifecycle
hook model, and plugin/skill discovery mechanism — answering the three questions
that block all downstream EPIC-2178 children.

Analogous to FEAT-1483 (Codex research spike), which established that Codex uses
the Skills API (`~/.codex/skills/`) rather than a `.codex/prompts/` surface.

## Use Case

A developer wants to contribute a `GeminiRunner` and `hooks/adapters/gemini/`
implementation. Without this spike, they don't know: what flags to call, what
events fire, or what the extension surface looks like. This spike produces a
`thoughts/research/gemini-cli-surface.md` artifact that answers all three
questions with evidence from the actual binary and official docs.

## Research Questions

### 1. Binary surface

- What is the canonical binary name? (`gemini`? `gemini-cli`? `gcloud gemini`?)
- Does it support a headless/non-interactive mode analogous to `claude -p`?
- What flag enables streaming JSON output? (needed for `build_streaming`)
- Does it support: `--model`, agent/persona select, tool allowlist, session resume?
- What does `gemini --version` output? (needed for `build_version_check`)
- Can it run a one-shot prompt and return structured JSON? (needed for `build_blocking_json`)

### 2. Lifecycle hooks / extension events

- Does gemini-cli expose lifecycle hooks (session start, pre-compact, tool use, etc.)?
- If yes: what events, what payload shape, how are handlers registered?
- Is there a hooks config file analogous to `.claude/settings.json` `hooks` section?
- Can external scripts be wired as event handlers?
- What is the equivalent of Claude Code's `PreToolUse` / `PostToolUse` / `Stop` events?

### 3. Plugin / skill / command discovery

- Does gemini-cli support custom commands or skills?
- Is there an analog to Claude Code's `commands/*.md` or Codex's `~/.codex/skills/`?
- What is the GEMINI_TOOLS or extension mechanism (if any)?
- What is the equivalent of `CLAUDE.md` / project instructions? (`GEMINI.md`?)

## Implementation Steps

1. ~~Install `gemini-cli` locally; run `gemini --help` and capture full output.~~ ✓ (`gemini` v0.46.0 at `/Users/brennon/.npm-global/bin/gemini`)
2. ~~Check `gemini-cli` GitHub repo for hook/extension documentation.~~ ✓ (bundled docs at `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/`)
3. ~~Search for `GEMINI.md`, `gemini.json`, or per-project config conventions.~~ ✓ (`GEMINI.md` confirmed; config at `.gemini/settings.json`)
4. ~~Test `gemini -p "hello"` (or equivalent) to confirm headless mode exists.~~ ✓ (`-p`/`--prompt` flag confirmed identical to Claude Code)
5. ~~Test streaming JSON output flag (compare to `claude --output-format stream-json`).~~ ✓ (`-o stream-json` — identical flag name)
6. ~~Check for lifecycle event docs (analogous to Claude Code's hooks docs).~~ ✓ (11 hook events; hooks configured in `settings.json`)
7. ~~Check for plugin/skill/command discovery surface.~~ ✓ (3 surfaces: commands TOML, skills SKILL.md, extensions)
8. ~~Write findings to `thoughts/research/gemini-cli-surface.md`.~~ ✓ (2026-06-15)
9. ~~Update this issue with a findings summary and recommended child issues for EPIC-2178.~~ ✓ (below)

## Acceptance Criteria

- `thoughts/research/gemini-cli-surface.md` exists with findings on all 3 research questions.
- Each research question has a definitive answer: ✓ (supported), ✗ (not supported), or
  (unknown — requires upstream PR or further investigation).
- Recommended child issues for EPIC-2178 are listed in the findings doc, including:
  - Binary name and headless-mode flag to use in `GeminiRunner`
  - Whether a hook adapter is feasible (and what events to wire)
  - Whether a skill/command adaptation step is needed (and what surface to target)
- `HOST_COMPATIBILITY.md` Gemini column stub is added (all cells `(unknown)` with link to this issue), so the matrix has a placeholder while research completes.

## API/Interface

No code changes in this issue — output is a research artifact:

- **New**: `thoughts/research/gemini-cli-surface.md`
- **Modified**: `docs/reference/HOST_COMPATIBILITY.md` (Gemini column stub)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Gemini column stub added here as part of this spike |
| `thoughts/research/codex-command-discovery.md` | Pattern to follow for the research output artifact |
| `hooks/adapters/codex/README.md` | Adapter contract that Gemini adapter will need to match |
| `scripts/little_loops/host_runner.py` | `PiRunner` / `CodexRunner` patterns for `GeminiRunner` |

## Session Log
- `/ll:capture-issue` - 2026-06-15T17:09:51Z - `63a402ce-7d2e-45a1-befc-4392e24ffc82.jsonl`

---

**Open** | Created: 2026-06-15 | Priority: P4
