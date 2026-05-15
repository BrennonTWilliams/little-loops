---
id: EPIC-1463
type: epic
status: open
priority: P5
captured_at: "2026-05-15T12:15:21Z"
discovered_date: 2026-05-15
discovered_by: capture-issue
relates_to: [FEAT-957, FEAT-1462, FEAT-992]
labels: [epic, captured, codex, host-compat, tracking]
---

# EPIC-1463: Track deferred Codex CLI interop gaps

## Summary

FEAT-957 landed hook-level Codex CLI compatibility (the `session_start` and
`pre_compact` intents, a `.codex/ll-config.json` probe path, and
`/ll:init --codex` install). The [Host Compatibility Matrix](../../docs/reference/HOST_COMPATIBILITY.md)
still shows several ✗ cells in the Codex column that are explicitly
out of scope for FEAT-957 and not covered by FEAT-1462 (orchestration
CLI). This epic is the umbrella tracking those gaps so the matrix
footnotes point at a real issue link instead of prose.

In scope for this epic:

- **Codex slash-command discovery** — Codex reads `.codex/prompts/`; ll
  ships `.claude/commands/*.md`. No bridge today. Solutions: a
  template-render step (build-time `.claude/commands/*.md` → `.codex/prompts/*.md`)
  or a runtime adapter. Format research required.
- **Codex skill discovery** — No known Codex mirror for `.claude/skills/*/SKILL.md`.
  Research required: does Codex have a skill/agent registration surface
  at all? If yes, mirror it; if no, document the gap as permanent.
- **Deferred Codex hook intents** — `post_compact` and `permission_request`
  are Codex-native events that ll currently ignores. Hot-path intents
  (`pre_tool_use`, `post_tool_use`) are deferred for latency reasons
  inherited from the OpenCode adapter; revisit if a sidecar/IPC story
  emerges.
- **Per-host state directory redirection** — Today `LL_STATE_DIR=.codex`
  is scoped narrowly to the config probe only. Other state surfaces
  (`.issues/`, `.loops/`, `.loops/tmp/scratch/`, `.ll/ll-continue-prompt.md`)
  remain at their default paths regardless of host. The
  `HOST_COMPATIBILITY.md` `[^state]` footnote explicitly says "file a
  separate issue" if full per-host state redirection becomes needed.
  Research required before implementing — is a Codex user actually
  better served by `.codex/issues/` etc., or is the current shared-path
  behavior the right default? Likely the latter (a project's `.issues/`
  is host-independent), but worth confirming rather than assuming.

Explicitly out of scope (tracked elsewhere):

- Orchestration CLI (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`,
  FSM evaluators, FSM handoff) — **FEAT-1462**.
- Raspberry Pi coding-agent compatibility — **FEAT-992**.

## Motivation

The Host Compatibility Matrix at `docs/reference/HOST_COMPATIBILITY.md`
links every ✗ cell to a tracking issue except these three. Without a
captured umbrella, the footnotes `[^cmds]` ("file a separate issue if
user demand surfaces") and the deferred-intent rows have no real
follow-up surface — they would silently rot.

This is a **tracking-only** epic. No current user demand. Worth
capturing so:

- The matrix has a coherent set of references (no "see footnote" dead
  ends).
- When a Codex user does ask for slash-commands or skill parity, the
  research notes and prior-art links accumulate here rather than
  starting from scratch.
- Decomposition into child FEAT/ENH issues happens lazily, when demand
  arrives.

## Goal

Codex CLI users have feature parity with Claude Code users for
non-orchestration surfaces: they can invoke ll slash-commands from
inside Codex, ll skills are discoverable from Codex, and the Codex
adapter handles every Codex-native hook event that ll has a real
consumer for.

End-state acceptance: every Codex column cell in
`docs/reference/HOST_COMPATIBILITY.md` is either ✓ or N/A — no ✗ or
(deferred) entries remain (except those pointing at FEAT-1462 /
FEAT-992).

## Scope

**In scope:**

- Research Codex command format (`.codex/prompts/` file shape, frontmatter,
  argument-passing convention).
- Research Codex skill/agent registration surface (or confirm no equivalent
  exists).
- Decide on render-time vs. runtime adapter strategy for command bridging.
- Implement chosen strategy with a child FEAT issue per discovery surface.
- Implement `post_compact` and `permission_request` adapter shims when
  a concrete consumer is identified.
- Decide whether `LL_STATE_DIR` should expand beyond the config probe
  (and if so, which state surfaces and with what migration story).
- Update `hooks/adapters/codex/README.md` and `HOST_COMPATIBILITY.md`
  as cells flip from ✗ to ✓.

**Out of scope:**

- Orchestration CLI host abstraction (FEAT-1462).
- Pi compatibility (FEAT-992).
- Hot-path hook intents (`pre_tool_use` / `post_tool_use`) — these
  remain deferred until the latency/sidecar question is answered for
  *all* non-Claude-Code hosts simultaneously. Not a Codex-specific
  problem.

## Children

No child issues filed yet. Decompose lazily when demand arrives:

- **(unfiled)** FEAT — Codex slash-command discovery via
  `.claude/commands/*.md` → `.codex/prompts/` bridge.
- **(unfiled)** FEAT — Codex skill discovery (or document permanent
  gap if Codex has no equivalent surface).
- **(unfiled)** ENH — Wire `post_compact` adapter intent (gated on
  finding a real consumer).
- **(unfiled)** ENH — Wire `permission_request` adapter intent (gated
  on finding a real consumer).
- **(unfiled)** ENH — Per-host state directory redirection. First
  step is a research note: enumerate each state surface
  (`.issues/`, `.loops/`, scratch, continuation prompt) and decide
  per-surface whether host-scoped paths make sense. Default
  recommendation is likely "leave shared," but the decision should
  be written down rather than implicit.

## Success Metrics

- The Codex column of the Host Compatibility Matrix has zero ✗ cells
  outside the orchestration-CLI rows (those resolve via FEAT-1462).
- At least one of `slash-command discovery` or `skill discovery` is
  either ✓ or has an explicit, documented "no Codex equivalent — gap
  is permanent" marker (with the research link that proved it).
- No silent footnote-only references remain in
  `HOST_COMPATIBILITY.md`; every ✗ links to a real issue.

## Integration Map

### Files to Modify

- `hooks/adapters/codex/hooks.json` — add `PostCompact` / hot-path
  matchers as children land.
- `hooks/adapters/codex/README.md` — event→intent mapping table
  expands.
- `docs/reference/HOST_COMPATIBILITY.md` — Codex column cells flip
  from ✗/(deferred) to ✓ as children complete.
- `scripts/little_loops/hooks/` — new handler modules per intent
  (e.g., `post_compact.py`, `permission_request.py`).
- New: `hooks/adapters/codex/prompts/` or build-time render target,
  depending on command-discovery strategy.
- `scripts/little_loops/config/core.py` — `_config_candidates()` and
  related helpers, if `LL_STATE_DIR` expands beyond the config probe.
- State-surface call sites: anything that hardcodes `.issues/`,
  `.loops/`, `.loops/tmp/scratch/`, or `.ll/ll-continue-prompt.md`
  would need to route through a per-host resolver if redirection is
  adopted (out of scope until the research decision lands).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/hooks/__main__.py` — intent dispatch table
  gains new entries.
- `scripts/tests/test_codex_adapter.py` — coverage expands per child.

### Tests

- Existing fixture: `scripts/tests/test_codex_adapter.py` (FEAT-957).
- Mirror `test_opencode_adapter.py` patterns for any new intent.

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — primary deliverable parity
  surface.
- `docs/claude-code/automate-workflows-with-hooks.md` — update mermaid
  / intro as new intents land.

## Impact

- **Priority**: P5 — Tracking only, no current user demand. The
  capture exists so the matrix has a real link instead of a footnote;
  promote when a user actually asks for one of these surfaces.
- **Effort**: Large (aggregate) — each child is Small-to-Medium, but
  there are 2–4 of them and command/skill discovery requires upstream
  Codex format research first.
- **Risk**: Low — additive, host-specific, no Claude Code behavior
  change. Risk of "render-time vs. runtime" architectural decision
  for command bridging being wrong is medium and best deferred until a
  real user is on the line.
- **Breaking Change**: No.

## Related Key Documentation

| Document                                                        | Why relevant                                                                          |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| [docs/reference/HOST_COMPATIBILITY.md](../../docs/reference/HOST_COMPATIBILITY.md) | Parity matrix this epic targets; every Codex ✗ cell here corresponds to scope.        |
| [hooks/adapters/codex/README.md](../../hooks/adapters/codex/README.md) | Adapter contract that any new intent wiring must follow.                              |
| [.claude/CLAUDE.md](../../.claude/CLAUDE.md)                    | Hook adapter architecture overview.                                                   |

## Labels

`epic`, `captured`, `codex`, `host-compat`, `tracking`

## Session Log

- `/ll:capture-issue` - 2026-05-15T12:15:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0010190c-509e-453e-bb85-c00575d1e590.jsonl`

---

**Open** | Created: 2026-05-15 | Priority: P5
