---
id: EPIC-2178
title: Gemini CLI host adapter — tracking
type: EPIC
status: open
priority: P4
captured_at: "2026-06-15T17:09:51Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
relates_to:
- EPIC-2257
- EPIC-1463
labels:
- epic
- captured
- gemini
- host-compat
- tracking
---

# EPIC-2178: Gemini CLI host adapter — tracking

## Summary

Google's `gemini-cli` is a major AI coding-agent platform. This epic is the
umbrella tracking Gemini host adapter support — analogous to EPIC-1463 (Codex
interop gaps) and EPIC-1713 (Pi parity gap tracking). No implementation should
land before the research spike establishes the gemini-cli hook/lifecycle model,
binary surface, and plugin discovery mechanism.

## Motivation

`gemini-cli` is a major AI coding-agent CLI from Google with significant and
growing adoption. Adding it as a supported host brings little-loops automation
(`ll-auto`, `ll-sprint`, `ll-loop`, FSM loops) to Gemini users. The
architecture already supports N hosts via `resolve_host()` / `HostRunner`
protocol; adding Gemini follows the established 4-layer pattern:

1. Runner stub → `host_runner.py`
2. Hook adapter → `hooks/adapters/gemini/`
3. Config probe → `config/core.py`
4. Parity matrix → `docs/reference/HOST_COMPATIBILITY.md`

## Goal

Gemini CLI users can run `ll-auto`, `ll-loop`, and FSM-based automation loops
with `LL_HOST_CLI=gemini`, with hook lifecycle events (`session_start`,
`pre_compact` at minimum) firing correctly.

End-state acceptance: a Gemini column exists in
`docs/reference/HOST_COMPATIBILITY.md` with no unknown or untracked cells —
every cell is ✓, ✗ (with a tracking issue), or N/A.

## Scope

**In scope:**

- **Research spike** — audit `gemini` CLI binary surface: headless/streaming
  flags, JSON output mode, lifecycle hook events (payload shape, available
  events), plugin/skill/command discovery surface. Analogous to FEAT-1483
  (Codex research spike).
- **`GeminiRunner` stub** in `scripts/little_loops/host_runner.py` — raises
  `HostNotConfigured` on all `build_*` calls; added to `_HOST_RUNNER_REGISTRY`
  and `_PROBE_ORDER` as `("gemini", "gemini")`. Analogous to `PiRunner`.
- **Hook adapter** `hooks/adapters/gemini/` — adapter scripts translating
  gemini-cli lifecycle events → `LLHookEvent`. Shape depends on research spike.
- **Config probe** — `.gemini/ll-config.json` probe path added to
  `config/core.py _config_candidates()`.
- **`HOST_COMPATIBILITY.md` Gemini column** — new column tracking parity cells
  (hook intents, skill/command discovery, orchestration CLI flags).
- **`GeminiRunner` full implementation** — real `build_streaming`,
  `build_blocking_json`, `build_detached`, `build_version_check` once CLI
  surface is audited.

**Delivered generically (no longer bespoke Gemini children):**

Per EPIC-2257 / ARCHITECTURE-049, host-parameterized components replace the
per-host skill/command/conformance children. These are reached by running the
generic tool with `--host gemini` once `GeminiRunner` lands:

- **Skill + command adaptation** — **FEAT-2260** (`done`); was FEAT-2188/FEAT-2189.
- **Conformance suite** — **FEAT-2259** (`done`); was FEAT-2192. `ll-auto` /
  `ll-sprint` / `ll-loop` golden paths against `gemini -p` run via the generic
  harness with `--host gemini`.

**Out of scope:**

- Gemini API direct integration (this is about the `gemini-cli` coding-agent
  host, not the Gemini REST API)
- Changes to existing Claude Code, Codex, OpenCode, or Pi adapters
- Bespoke per-host skill/command/conformance tooling — superseded by the
  EPIC-2257 generic components (FEAT-2259 / FEAT-2260, both `done`)

## Children

**Live (Gemini-specific work):**

- **FEAT-2179** — Research spike: gemini-cli binary surface, hook events, and plugin discovery — ✅ **done**
- **ENH-2184** — GeminiRunner stub in host_runner.py — ✅ **done**
- **ENH-2185** — GeminiRunner full implementation (build_streaming, build_blocking_json, build_detached, build_version_check) — ✅ **done**
- **FEAT-2186** — Hook adapter — hooks/adapters/gemini/ — open (decision **ratified**: Option A, settings.json injection — ARCHITECTURE-046)
- **ENH-2187** — Config probe — .gemini/ll-config.json in _config_candidates() — open (XS, independent)
- **FEAT-2190** — GEMINI.md project context file (ll:init --gemini) — open (independent)
- **ENH-2191** — HOST_COMPATIBILITY.md Gemini column — populate cells as children land — open (final gate)

**Cancelled — folded into EPIC-2257 generic host-parameterized components** (per ARCHITECTURE-049; run the generic tool with `--host gemini` instead of building bespoke):

- **FEAT-2188** — ~~Skills adaptation — ll-adapt-skills-for-gemini~~ — ❌ cancelled 2026-06-25, superseded by **FEAT-2260** (generic skill+command adapter, `done`)
- **FEAT-2189** — ~~Commands adaptation — ll-adapt-commands-for-gemini (.md → .toml)~~ — ❌ cancelled 2026-06-25, superseded by **FEAT-2260** (`done`)
- **FEAT-2192** — ~~Conformance test suite (ll-auto/ll-sprint/ll-loop golden paths)~~ — ❌ cancelled 2026-06-25, superseded by **FEAT-2259** (generic conformance harness, `done`)

## Implementation Steps

1. ✅ Land research spike (FEAT-2179) — all downstream work depends on its findings. **done**
2. Add `GeminiRunner` stub to `host_runner.py` + `_PROBE_ORDER` entry (ENH-2184). ← **next up**
3. Implement full `GeminiRunner` — replace stub `HostNotConfigured` raises (ENH-2185).
4. Wire `hooks/adapters/gemini/` adapter via `.gemini/settings.json` injection (FEAT-2186, Option A).
5. Add `.gemini/ll-config.json` config probe (ENH-2187).
6. Generate `GEMINI.md` from `ll:init --gemini` (FEAT-2190).
7. Run the generic skill+command adapter (FEAT-2260, `done`) and conformance harness
   (FEAT-2259, `done`) with `--host gemini` to exercise the skill/command/conformance
   cells — replaces the cancelled bespoke FEAT-2188/2189/2192.
8. Flip Gemini column cells in `HOST_COMPATIBILITY.md` to ✓ as each lands (ENH-2191).

## Success Metrics

- `LL_HOST_CLI=gemini` resolves without error on a machine with `gemini` on PATH.
- `session_start` and `pre_compact` hook intents fire on Gemini.
- `ll-auto` can process at least one issue end-to-end using the Gemini runner.
- All Gemini column cells in `HOST_COMPATIBILITY.md` are ✓, ✗ (linked), or N/A.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — `GeminiRunner` class, `_HOST_RUNNER_REGISTRY`, `_PROBE_ORDER`, `_remediation_hint()`
- `scripts/little_loops/config/core.py` — `_config_candidates()` for `.gemini/ll-config.json` probe
- `docs/reference/HOST_COMPATIBILITY.md` — new Gemini column
- `docs/ARCHITECTURE.md` — `GeminiRunner` in component table

### New Files

- `hooks/adapters/gemini/hooks.json`
- `hooks/adapters/gemini/session-start.sh`
- `hooks/adapters/gemini/pre-compact.sh`
- `hooks/adapters/gemini/README.md`
- `scripts/tests/test_gemini_adapter.py`

### Dependent Files

- `scripts/little_loops/hooks/__main__.py` — intent dispatch table
- `scripts/tests/test_host_runner.py` — `GeminiRunner` coverage

## Impact

- **Priority**: P4 — Gemini is a widely-used platform with significant user
  demand potential; higher than the Pi/Codex tracking epics (P5) but still a
  tracking epic with no confirmed user demand in hand.
- **Effort**: Large (aggregate) — each child is Small–Medium; total is
  Medium–Large once all 8 steps land.
- **Risk**: Low-Medium — additive, host-specific; no Claude Code behavior
  change. Main risk is that gemini-cli's hook/lifecycle model differs enough
  from Claude Code's that the adapter layer needs new abstractions. Research
  spike de-risks this.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Parity matrix this epic targets; Gemini column added here |
| `docs/ARCHITECTURE.md` | `HostRunner` protocol and adapter tree |
| `.claude/CLAUDE.md` § Host CLI Abstraction | `resolve_host()` contract all new runners must satisfy |
| `scripts/little_loops/host_runner.py` | Implementation home for `GeminiRunner` |
| `hooks/adapters/codex/README.md` | Adapter contract template to follow |

## Verification Notes

2026-06-18 (IN PROGRESS): FEAT-2179 (research spike) is complete — `thoughts/research/gemini-cli-surface.md` exists. All remaining 9 children still open. No `GeminiRunner` in `host_runner.py`; `hooks/adapters/gemini/` does not exist; no `.gemini` config probe; no skills/commands adaptation scripts. Next logical child: ENH-2184 (GeminiRunner stub, XS effort).

2026-06-30 (BOOKKEEPING REFRESH): Child roster reconciled. Of 10 children: 1 done (FEAT-2179), 3 cancelled (FEAT-2188, FEAT-2189, FEAT-2192 — superseded 2026-06-25 by EPIC-2257 generic components FEAT-2260 / FEAT-2259, both now `done`), 6 open. Updated `## Children`, `## Scope`, and `## Implementation Steps` to record the supersession (previously described the abandoned bespoke per-host approach). FEAT-2186's settings.json-vs-extension decision is **ratified** (Option A, ARCHITECTURE-046). No Gemini-specific implementation code exists yet: no `GeminiRunner` in `host_runner.py`, no `hooks/adapters/gemini/`, no `.gemini` config probe, no `GEMINI.md` template. Critical path is clean — start at ENH-2184 (stub) → ENH-2185 (full impl) + FEAT-2186 (hook adapter); ENH-2187 and FEAT-2190 are independent; ENH-2191 closes last. Closeout still requires running FEAT-2259/FEAT-2260 with `--host gemini` to satisfy the skill/command/conformance cells — nothing has yet exercised the generic harness against Gemini.

## Session Log
- `/ll:format-issue` - 2026-06-15T20:17:24 - `7addc9bb-4a3e-4aad-bbbd-6f11fcae2b61.jsonl`
- `/ll:capture-issue` - 2026-06-15T17:09:51Z - `63a402ce-7d2e-45a1-befc-4392e24ffc82.jsonl`

---

**Open** | Created: 2026-06-15 | Priority: P4
