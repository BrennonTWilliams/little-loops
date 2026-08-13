---
id: EPIC-3154
title: Qwen Code host adapter — tracking
type: EPIC
status: open
verify_verdict: VALID
priority: P3
captured_at: "2026-08-13T01:28:37Z"
discovered_date: 2026-08-12
discovered_by: capture-issue
decision_ref: ARCHITECTURE-046, ARCHITECTURE-047, ARCHITECTURE-048
relates_to:
- EPIC-2257
- FEAT-3155
- ENH-3156
- ENH-3157
- FEAT-3158
- FEAT-3159
- FEAT-3160
- ENH-3161
- ENH-3162
labels:
- epic
- captured
- qwen
- host-compat
- tracking
---

# EPIC-3154: Qwen Code host adapter — tracking

## Summary

Qwen Code (binary `qwen`, verified against 0.21.6) is the cheapest
first-class host little-loops has profiled — cheaper than Kimi (EPIC-2910),
which set the previous low bar. Its headless surface is a Claude-shaped
superset of what `QwenRunner` needs (`-p`, `--output-format
text|json|stream-json`, `--continue`/`--resume`, `--yolo`, run budgets, and
an inline `--json-schema` flag making Qwen only the **second host after
Claude Code** with `structured_output = True`); its hook system is
Claude-compatible by design (17 lifecycle events, same stdin/stdout JSON
protocol, `${CLAUDE_PLUGIN_ROOT}` substitution); and its discovery surfaces
(commands, skills, agents) are Markdown-native and accept ll's existing
artifact formats with near-zero translation. This epic is the umbrella
tracking Qwen Code as a first-class little-loops host — analogous to
EPIC-2910 (Kimi), which it mirrors nearly child-for-child.

Source: `thoughts/qwen-code-host-integration-report.md` (2026-08-05,
desk-research complete against qwen 0.21.6 installed on this machine).

## Motivation

Qwen Code complements the Gemini adapter (it is to Gemini CLI what omp is to
pi-mono — a maintained superset fork — but targets a distinct, much larger
user base). Adding it brings little-loops automation (`ll-auto`, `ll-loop`,
FSM loops) to Qwen users, and re-enables the FSM evaluators'
schema-constrained verdict path (`structured_output=True`, ENH-2627 gate) on
a non-Claude host for the first time. The architecture already supports N
hosts via `resolve_host()` / `HostRunner`; Qwen follows the established
4-layer pattern:

1. Runner → `host_runner.py`
2. Hook adapter → `hooks/adapters/qwen/`
3. Config probe → `config/core.py`
4. Parity matrix → `docs/reference/HOST_COMPATIBILITY.md`

plus the generic EPIC-2257 tooling (`ll-adapt --host qwen`, conformance
harness).

## Naming Decisions

Ratified at capture time (2026-08-12), per §5.1 of the integration report:

- **Runner host key**: `qwen` (binary `qwen`). Un-suffixed, matching the
  majority convention where key = binary name (`codex`, `gemini`, `omp`);
  key/binary/config-dir align on one string (`qwen` / `qwen` / `.qwen` —
  the config dir is dictated by Qwen Code's own convention, unlike Kimi
  whose `.kimi-code` dir motivated the `kimi-code` key).
- **Emitter/capabilities key**: ALSO `qwen` — one key at every seam
  (`_HOST_RUNNER_REGISTRY`, `_EMITTER_MAP`, `HOST_CAPABILITIES`,
  `_KNOWN_HOSTS`); `ll-verify-host-map` only cross-validates the
  intersection, so a mismatched key would silently escape the check.
- **Config dir**: `.qwen` → probe `.qwen/ll-config.json` before
  `.ll/ll-config.json`.
- **Plugin/extension id**: `ll` (preserves the `/ll:*` command namespace).
- **`_PROBE_ORDER`**: append `("qwen", "qwen")` at the END (registry
  comment: never insert mid-list — probe order decides auto-detection and
  must not change resolution for existing users).

## Goal

Qwen Code users can run `ll-auto`, `ll-loop`, and FSM-based automation loops
with `LL_HOST_CLI=qwen`, with hook lifecycle events firing correctly — the
full v1 event set (9 Qwen event types → 10 intents + 2 legacy scripts),
including under `qwen -p` headless.

End-state acceptance: a qwen column exists in
`docs/reference/HOST_COMPATIBILITY.md` with no unknown or untracked cells —
every cell is ✓, ✗ (with a tracking issue), or N/A.

## Scope

**In scope:**

- **Research verification spike** (FEAT-3155) — live confirmation of the
  report's desk research: `--yolo` argv acceptance (R1), `.qwen/settings.json`
  hooks firing under `qwen -p` (R2, the Kimi BUG-2921 analog), marketplace
  conversion fidelity (R3), stream-json event/usage shapes (R4), skill
  frontmatter tolerance (R7). Artifact: `thoughts/research/qwen-code-surface.md`.
- **`QwenRunner`** (ENH-3156) in `scripts/little_loops/host_runner.py` —
  full implementation (Kimi landed without a stub stage; expect the same).
- **Config probe** — `.qwen/ll-config.json` in `_config_candidates()`
  (ENH-3157).
- **Hook adapter + `ll-init` wiring** (FEAT-3158) — managed, marker-delimited
  `hooks` block in project `.qwen/settings.json` (ARCHITECTURE-046 "Option A"
  precedent ratified for Gemini), gen-version stamped for `ll-init --upgrade`,
  `LL_HOOK_HOST=qwen` shims, `write_agents_md()` reuse (Qwen reads
  `AGENTS.md` natively). ← critical path with ENH-3156.
- **ll-adapt emitter** (FEAT-3159) — `QwenEmitter` + `HOST_CAPABILITIES`
  row, landed atomically with the matrix adapter row.
- **`qwen-extension.json` packaging** (FEAT-3160) — repo-root native
  extension manifest (the `kimi.plugin.json` analog) + marketplace install
  docs. Headless automation never depends on it for hooks (BUG-2921 lesson
  applied up front).
- **Conformance + host-list plumbing** (ENH-3161) — `_HOST_BINARY` entry,
  config-schema `host_cli` enum, `ll-session --host qwen`,
  `get_project_folder()` qwen branch.
- **HOST_COMPATIBILITY.md qwen column + `docs/qwen/` onboarding trio**
  (ENH-3162) — final gate.
- **Contingent BUG** — headless-hook gap, filed only if spike R2 fails
  (BUG-2921 analog; fallback = user-level `~/.qwen/settings.json` managed
  block).

**Out of scope:**

- Changes to existing claude/codex/gemini/omp/kimi adapters.
- `qwen serve` SDK-native path (experimental HTTP daemon; the only
  SDK-native carve-out per ARCHITECTURE-047 is OpenCode — future at best).
- New hook intents for Qwen-only events (`PostToolUseFailure`,
  `PermissionRequest`/`PermissionDenied`, `Notification`, `SessionDelete`,
  `MessageDisplay`, `TodoCreated`, `TodoCompleted`) — documented as N/A /
  future in the matrix column.
- Parsing Qwen's `~/.qwen/projects/<cwd>/chats` JSONL wire format — locating
  session logs is in scope (ENH-3161); wire-format parsing is a likely
  follow-up, as it was on Kimi.

## Children

- **FEAT-3155** — Research verification spike: live qwen 0.21.6 surface confirmation — **done**
- **ENH-3156** — QwenRunner registration + full build_* implementation — **done**
- **ENH-3157** — Config probe — .qwen/ll-config.json in _config_candidates() — **done**
- **FEAT-3158** — Hook adapter — hooks/adapters/qwen + ll-init wiring + managed settings block — **done**
- **FEAT-3159** — ll-adapt emitter for qwen — **done**
- **FEAT-3160** — qwen-extension.json packaging + marketplace install path — **done**
- **ENH-3161** — Conformance + host-list plumbing for qwen — **done**
- **ENH-3162** — HOST_COMPATIBILITY.md qwen column + docs/qwen/ onboarding — **done**

**Contingent BUG (headless-hook gap): NOT FILED** — the spike's R2 probe
succeeded (project `.qwen/settings.json` hooks fire under `qwen -p`), so
the BUG-2921-analog fallback never became necessary. One narrower finding
was absorbed into design instead: `SessionEnd` does not fire headless
(documented in `[^qwenheadless]`; cleanup rides the `Stop` legacy scripts).
- **BUG-3163** — ll-adapt --host qwen mirrors omit skill companion files (open)


## Implementation Steps

1. Land research verification spike (FEAT-3155) — downstream hook/packaging
   work depends on R2/R3 findings. Desk research from the integration report
   is its seed.
2. Add `QwenRunner` (ENH-3156) — the report expects a full implementation
   with no stub stage (Kimi precedent).
3. Implement the hook adapter + `ll-init` wiring (FEAT-3158) — the critical
   path with 2.
4. Independent tracks (any order, parallel with 2-3): config probe
   (ENH-3157), ll-adapt emitter (FEAT-3159), extension packaging
   (FEAT-3160), conformance/plumbing (ENH-3161).
5. Docs last: complete the HOST_COMPATIBILITY.md qwen column and land
   `docs/qwen/` onboarding (ENH-3162).
6. Live end-to-end smoke: `LL_HOST_CLI=qwen ll-auto` on one issue,
   `qwen extensions install` in the TUI.

## Success Metrics

- `LL_HOST_CLI=qwen` resolves without error on a machine with `qwen` on PATH.
- `session_start` and `pre_compact` hook intents fire on Qwen Code
  (interactive and `-p` headless) — plus the full v1 event set.
- `ll-auto` can process at least one issue end-to-end using the qwen runner.
- FSM evaluators use the inline `--json-schema` path on Qwen
  (`structured_output=True`) — first non-Claude host to do so.
- All qwen column cells in `HOST_COMPATIBILITY.md` are ✓, ✗ (linked), or N/A.
- `ll-doctor --full`, `ll-verify-host-map`, and `--conformance-host qwen`
  golden paths all green.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — `QwenRunner`, `_HOST_RUNNER_REGISTRY`, `_PROBE_ORDER`, `_remediation_hint()`
- `scripts/little_loops/config/core.py` — `QWEN_CONFIG_DIR`, `_config_candidates()` probe
- `scripts/little_loops/init/cli.py` — `_KNOWN_HOSTS`, `_detect_hosts()`, `_dispatch_host_adapters()`, `--hosts` help
- `scripts/little_loops/init/tui.py` — host checkbox
- `scripts/little_loops/init/writers.py` — `install_qwen_adapter()`, `AGENTS_MD_HOSTS` entry
- `scripts/little_loops/adapters/core.py` — `_EMITTER_MAP` entry
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES` entry
- `scripts/little_loops/user_messages.py` — `get_project_folder()` qwen branch
- `scripts/little_loops/cli/session.py` — `--host` choices entry
- `scripts/little_loops/config-schema.json` — `orchestration.host_cli` enum
- `scripts/tests/conformance/test_host_conformance.py` — `_HOST_BINARY` entry
- `docs/reference/HOST_COMPATIBILITY.md` — qwen column
- `docs/ARCHITECTURE.md` — `QwenRunner` in component table
- `README.md` — Qwen Code install section

### New Files

- `scripts/little_loops/hooks/adapters/qwen/` — shims, settings-block template, README
- `scripts/little_loops/adapters/qwen.py` — ll-adapt emitter
- `qwen-extension.json` — native extension manifest (repo root)
- `scripts/tests/test_qwen_adapter.py` — adapter/emitter tests
- `docs/qwen/` — onboarding trio (getting-started, hook-events, automation)
- `thoughts/research/qwen-code-surface.md` — spike artifact

### Dependent Files

- `scripts/little_loops/hooks/__init__.py` — `main_hooks` dispatch (no new intents in v1)
- `ll-doctor` / `ll-verify-host-map` — stay green (`HOST_CAPABILITIES ∩ _HOST_RUNNER_REGISTRY` cross-check)

## Impact

- **Priority**: P3 — tracking epic for a major host with the most
  Claude-compatible surface yet profiled; lowest adaptation cost of any
  remaining host on pure friction metrics.
- **Effort**: Large (aggregate) — each child is XS–Medium; the critical path
  is the runner + hook adapter.
- **Risk**: Low-Medium — additive, host-specific; no existing host behavior
  change. R2 (headless hook firing) is the main open risk; spike verifies
  before the hook adapter lands.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `thoughts/qwen-code-host-integration-report.md` | Source research report; desk-research seed for the spike |
| `docs/reference/HOST_COMPATIBILITY.md` | Parity matrix this epic targets; qwen column added here |
| `docs/ARCHITECTURE.md` | `HostRunner` protocol and adapter tree |
| `scripts/little_loops/host_runner.py` | Implementation home for `QwenRunner` |
| `.issues/epics/P3-EPIC-2910-kimi-code-host-adapter-tracking.md` | Template epic, mirrored child-for-child |

## Verification Notes

2026-08-12 (PLANNED): EPIC and 8 children captured from
`thoughts/qwen-code-host-integration-report.md` (2026-08-05). Desk research
complete against qwen 0.21.6; live verification (FEAT-3155) still needed for
R1-R4/R7 before the hook adapter's settings-scope decision is final. No
implementation code exists yet. ARCHITECTURE decision entry recorded in
`.ll/decisions.d/` ratifying the P3 slot, the `qwen` key, and the Option A
hook strategy; EPIC-2257 updated as portfolio coordinator (relates_to +
"Tracked per-host epics" prose, not `parent:`, per the 2026-06-30
normalization).

2026-08-12 (IMPLEMENTATION COMPLETE, all 8 children done):
- **Spike (FEAT-3155)** live-verified the full surface on qwen 0.21.6
  (`thoughts/research/qwen-code-surface.md`); the one design-affecting
  finding: `SessionEnd` does not fire under `-p` headless.
- **Runner (ENH-3156)**: full `QwenRunner`, `structured_output=True` —
  required a host-aware persistence flag in `fsm/evaluators.py`
  (`--chat-recording false` for qwen; qwen rejects claude's
  `--no-session-persistence`).
- **Config probe (ENH-3157)**, **hook adapter (FEAT-3158** — first
  ARCHITECTURE-046 Option A implementation: structured JSON merge into
  project `.qwen/settings.json`), **emitter (FEAT-3159** — native
  `/ll:<stem>` namespacing, no bridging), **packaging (FEAT-3160** —
  inline-hooks manifest, link/unlink verified), **plumbing (ENH-3161)**,
  **docs (ENH-3162)** all landed with tests.
- Green checks: `ll-verify-host-map` OK · 1466 targeted tests + 262
  host-map/evaluator tests passed · conformance 20 passed (4/4 golden
  paths on the real qwen binary) · `ll-adapt --host qwen --apply`
  55/0 errors · `.qwen/` mirror under wiring-test enforcement.
- **Remaining epic gate:** the live end-to-end smoke (step 6 —
  `LL_HOST_CLI=qwen ll-auto` on one issue, `qwen extensions install` in
  the TUI). Deliberately not run autonomously: it spends model tokens and
  mutates issue state. Epic stays open until that smoke passes.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:07:49 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:capture-issue` - 2026-08-13T01:28:37Z - qwen-code host integration report capture

---

**Open** | Created: 2026-08-12 | Priority: P3