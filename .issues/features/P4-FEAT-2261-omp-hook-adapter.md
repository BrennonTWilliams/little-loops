---
id: FEAT-2261
title: "omp hook adapter \u2014 hooks/adapters/omp/"
type: feature
status: done
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
completed_at: "2026-08-31T00:57:11Z"
parent: EPIC-2258
depends_on:
- FEAT-1850
labels:
- host-compat
- omp
- hooks
blocked_by:
- FEAT-2263
verify_verdict: VALID
decision_needed: false
reconcile_attempted: true
learning_tests_required:
- oh-my-pi
- bun
confidence_score: 100
outcome_confidence: 88
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-2261: omp hook adapter — hooks/adapters/omp/

## Summary

Create `hooks/adapters/omp/` translating oh-my-pi (`omp`) lifecycle events into
`LLHookEvent` and invoking the host-agnostic ll hook handler. Analogous to
`hooks/adapters/codex/`.

## Current Behavior

No `hooks/adapters/omp/` directory exists. oh-my-pi's native `HookAPI.on()`
lifecycle events (`tool_call`, `session_before_compact`, `before_agent_start`,
etc.) are never translated into an `LLHookEvent` or forwarded to
`main_hooks()`, so none of ll's host-agnostic hook intents (session-start
context injection, tool telemetry, pre-compact handoff, ...) fire for omp
sessions. `_KNOWN_HOSTS` in `scripts/little_loops/init/cli.py` has no `"omp"`
entry, so `ll-init --hosts omp` errors with "Unknown host".

## Expected Behavior

`hooks/adapters/omp/` (with runnable shims packaged under
`scripts/little_loops/hooks/adapters/omp/` per the pip-wheel split) exists
with an event→handler mapping: a `session_start`-equivalent omp event
triggers the `session_start` ll intent, and at least one tool-lifecycle event
triggers `pre_tool_use`/`post_tool_use`, both by piping the native event JSON
through `python -m little_loops.hooks <intent>` with `LL_HOOK_HOST=omp` set.
`ll-init --hosts omp` recognizes the host via an info-only
`_dispatch_host_adapters()` branch (no "Unknown host" warning, no generated
config artifact — Option B, matching the `opencode` precedent).

## Motivation

oh-my-pi exposes richer hook events than vanilla pi-mono, so the parity gap
that plagued the cancelled Pi adapter (FEAT-1715) is expected to be narrower.
The exact event set is established by FEAT-2263 (hook-event parity audit).

## Use Case

As an omp (oh-my-pi) user, I want ll's host-agnostic hook intents (context
injection at session start, tool-lifecycle telemetry, pre-compact handoff,
...) to fire the same way they already do under Claude Code, Codex, Kimi,
and Qwen, so that little-loops' automation and issue-tracking features work
identically regardless of which host CLI I'm running.

## Acceptance Criteria

- `hooks/adapters/omp/` exists with an event→handler mapping.
- A `session_start`-equivalent omp event triggers the `session_start` ll intent.
- At least one tool-lifecycle omp event triggers `pre_tool_use`/`post_tool_use`.
- `hooks/adapters/omp/README.md` documents activation + the event mapping table.
- Tests in `scripts/tests/test_omp_adapter.py` pass.
- `ll-init --hosts omp` recognizes the host (no "Unknown host" warning) via an
  info-only `_dispatch_host_adapters()` branch — no `install_omp_adapter()`
  writer, per the Option B decision.
- `python -m pytest scripts/tests/test_wiring_guides_and_meta.py scripts/tests/test_init_core.py`
  pass (host-tier table stays in sync with `_KNOWN_HOSTS`; the new info-branch
  test covers `ll-init --hosts omp`).

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

**Option A**: Build `install_omp_adapter()` in `scripts/little_loops/init/writers.py` matching `install_codex_adapter()`'s four-parameter signature and `True`/`False`/`None` return convention, generating a real config artifact (whatever native registration format omp's `HookAPI` loader expects) and wiring it into `_KNOWN_HOSTS` / `_dispatch_host_adapters()` in `scripts/little_loops/init/cli.py` the same way codex/kimi/qwen are wired.

**Option B**: Follow the closer structural analog's precedent — `hooks/adapters/opencode/` (also a TS/Bun-plugin-shaped adapter) has **no** `install_opencode_adapter()` function at all; `_dispatch_host_adapters()`'s `elif host == "opencode":` branch is a pure `info()` no-op, and opencode's README documents a fully manual install route (`bun install` + hand-edit the consuming project's entry point to import and register the plugin). Under this option, `hooks/adapters/omp/` still gets an `_KNOWN_HOSTS` entry and an info-only branch in `_dispatch_host_adapters()` (so `ll-init --hosts omp` doesn't warn "Unknown host"), but no new writer function or generated config artifact.

> **Selected:** Option B — matches the confirmed structural analog (opencode, same TS/Bun-plugin shape) exactly; no existing declarative registration format exists for omp's `HookAPI` to generate against.

**Recommended**: Option B for v1 — it matches the confirmed structural analog (opencode) exactly rather than importing codex's Bash-shim-era installer convention onto a TS/Bun-plugin shape it was never designed for, and keeps the adapter's own README (this issue's own AC) as the single source of installation truth, consistent with how opencode's parity gap is currently handled. Revisit if a future issue finds omp's native loader supports declarative registration (a `hooks.json`-equivalent) the way codex's does.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-30.

**Selected**: Option B — info-only `_KNOWN_HOSTS` entry, no `install_omp_adapter()` writer

**Reasoning**: `hooks/adapters/opencode/` is the confirmed structural analog to omp — both are TS/Bun-plugin-shaped adapters registered via native code (`Plugin` factory / `HookAPI.on()`), not declarative config. Opencode has no `install_opencode_adapter()` function and no generated artifact; its `_dispatch_host_adapters()` branch is a pure `info()` no-op. No declarative registration format exists for omp's `HookAPI` surface to generate against (its one file-drop mechanism, `.omp/hooks/pre|post/`, is a narrower legacy surface FEAT-2263's own audit rules out of scope), so Option A would invent new infrastructure with nothing to reuse.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |
| Option B | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- The writer-based approach (A): only 3 of 6 `_KNOWN_HOSTS` entries (codex, kimi-code, qwen) have a real `install_*_adapter()` writer — all Bash-shim/declarative-config hosts, none TS/Bun-plugin-shaped like omp; no existing test-class shape covers a `HookAPI`-native-registration writer.
- The info-only approach (B): `hooks/adapters/opencode/` matches omp's confirmed shape byte-for-byte (five-file layout, `spawnIntent()` transport helper, `test_opencode_adapter.py`'s Bun-driver harness) and its info-only dispatch branch (`cli.py:158-159`) is directly reusable as a template.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis._

### Files to Create (Deliverables)

- `hooks/adapters/omp/README.md` — the only file this adapter keeps at repo-root
  `hooks/adapters/omp/`, following the pip-wheel packaging split every other
  Bash-shim host adapter uses (Codex, Kimi, Qwen): `pyproject.toml:202`'s
  `include = ["little_loops/**", "LICENSE", "README.md"]` only ships paths under
  `little_loops/**`, so runnable shims/config live under
  `scripts/little_loops/hooks/adapters/omp/` and only the README stays at
  repo-root (established by BUG-2275). Model the README's Event → Intent
  Mapping table on `hooks/adapters/codex/README.md`'s 4-column shape
  (`event key | ll intent | Python invocation | Status`), and its section
  skeleton (Installation, Event → Intent Mapping, Host Identification,
  Subprocess Contract, host quirks, Smoke Test, Related) on the same file.
- `scripts/little_loops/hooks/adapters/omp/*` — mirrors the five-file
  TS/Bun-plugin shape confirmed on disk at `hooks/adapters/opencode/`:
  `index.ts` (a shared `spawnIntent()` transport helper plus a hook-registration
  function calling `HookAPI.on()` per event), `package.json`, `tsconfig.json`
  (`strict: true`, `types: ["bun"]`, `noEmit: true`), `bun.lock`. FEAT-2263's
  `thoughts/research/omp-hook-event-parity.md` (2026-08-30) settled the shim
  shape: omp hooks are native Bun/TS modules subscribed via `HookAPI.on()`, not
  JSON-config or Bash-shim based — the codex Bash-shim shape does not apply.
- `scripts/tests/test_omp_adapter.py` — required by this issue's own acceptance
  criteria; naming matches the existing `scripts/tests/test_<host>_adapter.py`
  convention (`test_codex_adapter.py`, `test_kimi_adapter.py`, `test_qwen_adapter.py`).

### Files to Modify

- `scripts/little_loops/init/cli.py` — `_KNOWN_HOSTS` (a `frozenset`) has no
  `"omp"` entry, and `_dispatch_host_adapters()` has no `elif host == "omp":`
  branch — its own comment states omp is "deliberately absent because they have
  no install wiring and would warn 'Unknown host'." Both need an omp entry for
  `ll-init` to wire this adapter.
- `scripts/little_loops/init/writers.py` — **not modified.** Per the
  Proposed Solution decision (Option B), no `install_omp_adapter()` writer is
  added — `hooks/adapters/opencode/` (the confirmed structural analog, same
  TS/Bun-plugin shape) has no installer either; its `_dispatch_host_adapters()`
  branch is a pure `info()` no-op.

### Dependent Files (Already-Wired, No Change Needed)

- `scripts/little_loops/hooks/__init__.py` — `main_hooks()`/`_dispatch_table()`
  is the host-agnostic dispatcher every adapter shim pipes into via
  `python -m little_loops.hooks <intent>`; it already supports every ll intent
  this issue's acceptance criteria name. `LL_HOOK_HOST` unset defaults to
  `"claude-code"` — the new shim(s) must set `LL_HOOK_HOST=omp` explicitly.
- `scripts/little_loops/config/core.py` (`_config_candidates()`) — `.omp` config-dir
  probing (`OMP_CONFIG_DIR`) is already registered and keyed on `host == "omp"`
  (landed under the sibling FEAT-2262); it activates automatically once the new
  shim(s) export `LL_HOOK_HOST=omp`, no code change needed here.

### Conventions in Force

- Every non-Claude-Code Bash adapter shim follows a fixed 4-line shape:
  `export LL_HOOK_HOST=<host>`, read stdin, resolve `$LL_PYTHON` fallback
  (`python3` → `python` → bare `python`), pipe into
  `python -m little_loops.hooks <intent>` — evidence:
  `scripts/little_loops/hooks/adapters/codex/session-start.sh`,
  `scripts/little_loops/hooks/adapters/qwen/session-start.sh`.
- Shims stay deliberately minimal ("env-set + exec only") because editing one
  can flip a host's own hook-trust status — evidence: `hooks/adapters/codex/README.md`
  § Trust-Hash Churn ("any edit flips Codex's trust status to `Modified`").
- Adapter READMEs share one section skeleton (Installation → Event → Intent
  Mapping table → Host Identification → Subprocess Contract → host quirks →
  Smoke Test → Related) — evidence: `hooks/adapters/{codex,kimi,qwen,opencode}/README.md`.
  Two Event→Intent Mapping table shapes coexist and disagree on column count:
  Codex/Kimi use 4 columns (`event | ll intent | Python invocation | Status`);
  OpenCode uses 3 (folding status into prose). FEAT-2263's own Integration Map
  already directs the omp README to the 4-column Codex shape.
- Adapter test files follow `scripts/tests/test_<host>_adapter.py`.
  `scripts/tests/test_opencode_adapter.py` is the applicable precedent for
  `test_omp_adapter.py` — not codex's subprocess-on-a-`.sh`-file or Qwen's
  substring-match approach, which target Bash shims. It skips on missing
  `bun`, writes a synthetic Bun "driver" script that imports the adapter's
  default-exported `Plugin` factory, calls it with a fabricated `ctx`, and
  invokes the named handler directly (`_write_driver()`); `LL_HOOK_HOST`
  propagation is asserted via a stubbed `little_loops.hooks.__main__` module
  on `PYTHONPATH` that writes the observed env var to a sentinel file. It also
  carries a `TestOpenCodeAdapterTypecheck`-style class running
  `bun x tsc --noEmit -p tsconfig.json` (per BUG-2922) under
  `python -m pytest scripts/tests/`.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` — test-enforced coupling, not just prose:
  `scripts/tests/test_wiring_guides_and_meta.py::test_host_tier_table_matches_known_hosts`
  (line 395) mechanically diffs the `## Host tiers` table's `ll-init --hosts`
  column against `set(_KNOWN_HOSTS)`; adding `"omp"` to `_KNOWN_HOSTS` (this
  issue's own Files to Modify) fails that test until the `omp` row (line 31,
  currently `| \`omp\` | ✓ | ✗ | ✗ | Orchestration-only |`) flips its
  `ll-init --hosts` cell ✗→✓ and its Tier text to `Recognized, adapter pending`
  (matching the `opencode`/`pi` rows at lines 28-29 — Hook adapter stays ✗
  since Option B adds no `install_omp_adapter`, so the sibling
  `test_host_tier_table_matches_adapter_installers` is unaffected). Also
  update: the `[^omp]` footnote (lines 260-262, "the hook adapter (FEAT-2261)
  is still pending, so all hook-intent cells above stay `(deferred)`") — cells
  stay `(deferred)` post-landing too (no auto-install under Option B) but the
  "is still pending" framing goes stale; the "Adapter locations" entry (lines
  584-588, "omp: `hooks/adapters/omp/` — **pending FEAT-2261.**") which needs
  the real file path (`scripts/little_loops/hooks/adapters/omp/`) and to drop
  "pending"; and the EPIC-2258 tracking-issues entry (lines 645-650, "hook
  adapter (FEAT-2261) is the remaining pending child").
- `docs/reference/CLI.md:49` — `--hosts` flag reference states *"note
  \`gemini\` and \`omp\` are orchestration-only and are **not** valid here"*;
  false for `omp` once `_KNOWN_HOSTS` changes — move `omp` into the
  adapter-pending list alongside `opencode`/`pi`.
- `docs/reference/CONFIGURATION.md:1330` — `orchestration.host_cli` doc states
  *"gemini and omp are valid here but are not `--hosts` values"*; the `omp`
  half goes false once it becomes a `--hosts` value (the enum itself is
  untouched — `host_cli` is the separate `_HOST_RUNNER_REGISTRY` set per this
  file's own column-to-source-of-truth table, not `_KNOWN_HOSTS`).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py::test_host_tier_table_matches_known_hosts`
  (line 395) — existing test that WILL BREAK once `_KNOWN_HOSTS` gains `"omp"`
  unless `docs/reference/HOST_COMPATIBILITY.md`'s table is updated in the same
  change (see Documentation above); its sibling
  `test_host_tier_table_matches_adapter_installers` (line 409) stays green
  since Option B adds no `install_omp_adapter`.
- `scripts/tests/test_init_core.py` — new test for the info-only `omp` branch
  in `_dispatch_host_adapters()`, mirroring `test_hosts_pi_graceful_unavailable`
  (lines 3015-3022: `main_init(["--yes", "--hosts", "pi", ...])` asserts
  `code == 0` and `"not yet available"` in stdout). No dedicated
  `test_hosts_opencode_*` info-branch test exists to copy instead — `pi`'s is
  the applicable precedent.

### Reference Templates (read-only)

- `hooks/adapters/codex/README.md` — README mapping-table template only
  (4-column shape, README skeleton); FEAT-2263 confirmed omp is not
  Bash-shim-shaped, so codex's `.sh` shims are not a transport-layer template.
- `hooks/adapters/opencode/index.ts` — the confirmed transport-layer template:
  `spawnIntent()` helper plus `HookAPI.on()`-based event registration.

### Dependency / Blocker

- `blocked_by: FEAT-2263` — **resolved.** FEAT-2263 is `done` (2026-08-30);
  its research doc `thoughts/research/omp-hook-event-parity.md` exists and
  settled both the omp→ll event mapping and the shim shape (TS/Bun plugin,
  matching opencode). This issue is unblocked.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- **Shim shape now decided (FEAT-2263 complete, `thoughts/research/omp-hook-event-parity.md`, 2026-08-30):** omp hooks are native Bun/TS modules subscribed via `HookAPI.on()` (`export default function(pi: HookAPI) { pi.on(...) }`), not JSON-config or Bash-shim based. This makes `hooks/adapters/opencode/` (a TS/Bun-plugin adapter) the structural analog, not `hooks/adapters/codex/` (a Bash-shim adapter) — the "not yet decidable by analogy" open question in this section is resolved.
- **Deliverable file set changes to match the opencode shape**, confirmed on disk at `hooks/adapters/opencode/`: `index.ts` (transport module — one shared `spawnIntent()` helper plus a `Plugin` factory returning an event→handler map keyed by native event names), `package.json` (declares `@opencode-ai/plugin` + `@types/bun`, `engines.bun >= 1.1.0`), `tsconfig.json` (`strict: true`, `types: ["bun"]`, `noEmit: true`), `bun.lock`, `README.md`. The omp adapter's `scripts/little_loops/hooks/adapters/omp/*` deliverable should mirror this five-file shape rather than the per-intent `.sh` + `hooks.json` shape codex uses.
- **`spawnIntent()` transport pattern** (`hooks/adapters/opencode/index.ts`): `Bun.spawn([PY, "-m", "little_loops.hooks", intent], {cwd, env: {...process.env, LL_HOOK_HOST: "<host>"}, stdin: "pipe", stdout: "pipe", stderr: "pipe"})`, writes `JSON.stringify(payload ?? {})` to stdin, awaits stdout/stderr as text and `proc.exited` for the exit code. `PY` resolution: `process.env.LL_PYTHON ?? Bun.which("python3") ?? Bun.which("python") ?? "python"`
  <!-- ll-evidence-ok: quote is hooks/adapters/opencode/index.ts:35 verbatim; the trailing "(cites BUG-2921)" note (that file's own line-28 comment independently references BUG-2921) gets mis-parsed by the low-precision (~0.13-0.20) evidence checker as the quote's source artifact instead of the file named earlier in the bullet — re-confirmed manually across three prior /ll:verify-issues and /ll:refine-issue passes, not a fabricated quote -->
  — the same fallback chain codex's Bash shims use via `command -v`, just through the Bun API.
- **Registration is NOT self-installing for the opencode shape**: per `hooks/adapters/opencode/README.md` § Installation, the consuming project must `bun install` in the adapter dir and hand-import the default export into its own OpenCode entry point (`plugins: [llHooks]`). There is no generated config file and **no `install_opencode_adapter()` function exists in `writers.py`** — `_dispatch_host_adapters()`'s `elif host == "opencode":` branch (`scripts/little_loops/init/cli.py:158-159`) only prints `info("OpenCode: adapter not yet available — opencode orchestration not yet wired.")`. This is the direct precedent for "a known host with a real adapter directory on disk but no install-wiring function" and bears on whether `install_omp_adapter()` (see Files to Modify below and the Proposed Solution decision) should exist in the codex-matching shape this issue originally assumed.
- **Event mapping** (full detail in `thoughts/research/omp-hook-event-parity.md`): all 7 canonical ll intents have a native omp event candidate. `pre_tool_use` (`tool_call`), `post_tool_use` (`tool_result`), and `pre_compact`/`pre_compact_handoff` (`session_before_compact`, second-handler-registration pattern matching every other host) map to *richer* native events than most hosts (full block + input/result revision). `user_prompt_submit` (`before_agent_start`) is *narrower* — injection-only, cannot block/reject, unlike Claude Code's `exit_code=2` reject path. `session_end` (`session_shutdown`) fires on both graceful-exit and signal paths but its handler-timeout behavior is **unverified**; the doc recommends the same `[^ssend]` pattern already used for Claude Code — dispatch `session_end` work from the *next* `session_start` rather than trusting `session_shutdown` for expensive work.
- **Test convention precedent**: `scripts/tests/test_opencode_adapter.py` is the applicable precedent for `test_omp_adapter.py`, not codex's subprocess-on-a-`.sh`-file approach. It skips on missing `bun`, writes a synthetic Bun "driver" script that imports the adapter's default-exported `Plugin` factory, calls it with a fabricated `ctx`, and invokes the named handler directly (`_write_driver()`); env-var propagation (`LL_HOOK_HOST`) is asserted via a stubbed `little_loops.hooks.__main__` module on `PYTHONPATH` that writes the observed env var to a sentinel file, not by reading `os.environ` directly. It also carries a `TestOpenCodeAdapterTypecheck` class running `bun x tsc --noEmit -p tsconfig.json` (per BUG-2922) as part of `python -m pytest scripts/tests/` — no Bash-shim adapter test has an analogous compile-check class.
- **FEAT-2263 is now `done`** (completed 2026-08-30) — the `blocked_by: FEAT-2263` edge on this issue's own frontmatter is resolved; the "Dependency / Blocker" subsection above describing it as pending (research doc "does not exist yet") is now stale — the doc exists at `thoughts/research/omp-hook-event-parity.md`.

## Program Design

_Added by `/ll:refine-issue` — populated from analyzer findings; the intent-to-event
mapping itself is pending FEAT-2263, so this states only what is already fixed by
the existing host-agnostic dispatch layer._

### Deviations

_Added by `/ll:manage-issue` — 2026-08-30:_

- **Call Path** describes `tool_call` -> `pre_tool_use` (blocking, via
  `ToolCallEventResult.block`) as the tool-lifecycle example. The landed
  implementation wires `tool_result` -> `post_tool_use` (fire-and-forget)
  instead, and does not register a `tool_call` handler. Reason: this issue's
  own Acceptance Criteria only require "at least one tool-lifecycle omp event"
  to dispatch; `pre_tool_use` via `tool_call` would be a *blocking* hot-path
  addition with no measured cold-start latency budget for omp (unlike
  OpenCode's benchmarked ≈10ms p95, documented in its README's Latency
  Target section) — wiring an unbenchmarked blocking hook by default would
  repeat the exact risk FEAT-1488/FEAT-1489 were opened to avoid for other
  hosts. `post_tool_use` is fire-and-forget by construction (no latency
  question) and matches every other host's default-wired convention. The
  `tool_call`/`pre_tool_use` mapping is documented as deferred (not dropped)
  in `hooks/adapters/omp/README.md`'s Event → Intent Mapping table, along
  with `pre_compact`, `pre_compact_handoff`, `user_prompt_submit`, and
  `session_end` — all deferred for the same reason (not required by this
  issue's ACs, and in `session_end`'s case, `session_shutdown`'s handler
  timeout is explicitly flagged unverified by FEAT-2263's own audit).

### Types

N/A — this adapter reuses the existing `LLHookEvent`/`LLHookResult` dataclasses
(`scripts/little_loops/hooks/types.py`) unmodified; it introduces no new data shape.

### Signatures

- `main_hooks()` (`scripts/little_loops/hooks/__init__.py`) — existing, unmodified
  entry point every adapter shim invokes via `python -m little_loops.hooks <intent>`.
- `LLHookEvent(host: str, intent: str, timestamp: str, payload: dict, session_id: str | None, cwd: str | None)`
  (`scripts/little_loops/hooks/types.py`) — existing envelope; the new shim(s)
  only need to set `LL_HOOK_HOST=omp` in the environment and pipe the native
  event JSON to stdin.
- ~~New: `install_omp_adapter(...)` (`scripts/little_loops/init/writers.py`)~~ —
  superseded by the Proposed Solution decision (Option B): no new writer function.
  `_KNOWN_HOSTS` gains an `"omp"` entry and `_dispatch_host_adapters()` gains an
  info-only `elif host == "omp":` branch, matching `opencode`'s existing shape
  (`scripts/little_loops/init/cli.py:158-159`).

### Call Path

omp fires a native lifecycle event -> `hooks/adapters/omp/<shim>` (shape TBD by
FEAT-2263) sets `LL_HOOK_HOST=omp` and forwards the event JSON on stdin ->
`python -m little_loops.hooks <intent>` -> `main_hooks()` builds an `LLHookEvent`
-> `_dispatch_table()[intent].handle()` -> returns an `LLHookResult` -> the shim
relays `exit_code`/`stdout`/`feedback` back through omp's own hook-result contract
(exact contract also pending FEAT-2263's audit).

### Decision Rules

N/A — no new gap kind, gate, or threshold; this issue wires the existing,
unmodified dispatch mechanism to a new host.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- **Concrete call path for the now-confirmed TS/Bun-plugin shape** (supersedes the "shape TBD" framing in the Call Path above): omp fires a native `HookAPI` event (e.g. `tool_call`, `session_before_compact`) -> the omp adapter's `hooks/adapters/omp/index.ts` (or `scripts/little_loops/hooks/adapters/omp/index.ts` per the packaging split) registers a handler via `pi.on(<event>, handler)` inside its default-exported hook-registration function -> the handler calls a local `spawnIntent(intent, payload, cwd)` helper (mirroring `hooks/adapters/opencode/index.ts`) that runs `Bun.spawn([PY, "-m", "little_loops.hooks", intent], {env: {...process.env, LL_HOOK_HOST: "omp"}, stdin: "pipe", ...})` -> `main_hooks()` builds an `LLHookEvent(host="omp", ...)` -> `_dispatch_table()[intent].handle()` -> `LLHookResult` -> the handler relays `stdout`/`stderr`/`exit_code` back through omp's own `HookHandler` return contract (e.g. `ToolCallEventResult.block`/`.input` for `tool_call`, `SessionBeforeCompactResult.cancel`/`.compaction` for `session_before_compact`) rather than opencode's throw-on-exit-2 convention, since omp's per-event result shapes are richer and typed (see `thoughts/research/omp-hook-event-parity.md`'s per-event `ll handler relevance` column).

## Implementation Steps

_Added by `/ll:refine-issue` — outcome-phrased, concrete references; ordering
is incidental except where FEAT-2263's output is a hard prerequisite._

1. **Settled** (FEAT-2263 `done`, `thoughts/research/omp-hook-event-parity.md`):
   omp hooks are native Bun/TS modules subscribed via `HookAPI.on()`, matching
   `hooks/adapters/opencode/`'s five-file TS/Bun-plugin shape
   (`index.ts`, `package.json`, `tsconfig.json`, `bun.lock`, `README.md`), not
   codex's Bash-shim shape. All 7 canonical ll intents have a native omp event
   candidate — see the event-mapping doc for the full table.
2. `scripts/little_loops/init/cli.py`'s `_KNOWN_HOSTS` and `_dispatch_host_adapters()`
   gain an `"omp"` entry so `ll-init` can wire the adapter (currently absent by
   the file's own comment).
3. `scripts/little_loops/init/writers.py` is **not modified** — Option B adds
   no `install_omp_adapter()` writer, matching opencode's info-only precedent.
4. `hooks/adapters/omp/index.ts` registers a `pi.on(<event>, handler)` handler
   per mapped omp event; each handler calls a shared `spawnIntent(intent,
   payload, cwd)` helper (mirroring `hooks/adapters/opencode/index.ts`) that
   spawns `python -m little_loops.hooks <intent>` with `LL_HOOK_HOST=omp` and
   pipes the event JSON to stdin — no adapter-side business logic, per the
   "adapter-as-pure-transport" convention documented above.
5. `hooks/adapters/omp/README.md` documents the event mapping and activation,
   matching the 4-column Codex shape FEAT-2263 already directs.
6. `scripts/tests/test_omp_adapter.py` follows `test_opencode_adapter.py`'s
   Bun-driver precedent (`_write_driver()`, stubbed `little_loops.hooks.__main__`
   sentinel for `LL_HOOK_HOST` propagation, plus a `bun x tsc --noEmit` typecheck
   class), covering this issue's own acceptance criteria (`session_start`-
   equivalent and at least one tool-lifecycle event dispatching correctly).
7. Add a `test_hosts_omp_graceful_unavailable`-style test to
   `scripts/tests/test_init_core.py` (mirrors `test_hosts_pi_graceful_unavailable`)
   and update `docs/reference/HOST_COMPATIBILITY.md`/`CLI.md`/`CONFIGURATION.md`
   per the Wiring Phase below, so `_KNOWN_HOSTS` gaining `"omp"` doesn't break
   `test_host_tier_table_matches_known_hosts`.
8. Verify: `python -m pytest scripts/tests/test_omp_adapter.py
   scripts/tests/test_wiring_guides_and_meta.py scripts/tests/test_init_core.py -v`
   passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/init/cli.py:44` — the `_KNOWN_HOSTS` comment
  ("gemini/omp are deliberately absent because they have no install wiring
  and would warn 'Unknown host'") goes stale for omp once it's added; keep
  the gemini half, drop or reword the omp half.
- Update `docs/reference/HOST_COMPATIBILITY.md` — flip the `omp` row's
  `ll-init --hosts` column (line 31) ✗→✓ and Tier text to `Recognized,
  adapter pending`; update the `[^omp]` footnote (lines 260-262), the
  "Adapter locations" entry (lines 584-588), and the EPIC-2258 tracking entry
  (lines 645-650) to reflect the adapter landing under Option B (real files
  exist, but no `ll-init` auto-install — hook-intent cells stay `(deferred)`).
  Required so `test_host_tier_table_matches_known_hosts` keeps passing.
- Update `docs/reference/CLI.md:49` and `docs/reference/CONFIGURATION.md:1330`
  — drop `omp` from the "not a `--hosts` value" / "orchestration-only" prose.
- Add a `test_hosts_omp_graceful_unavailable`-style test to
  `scripts/tests/test_init_core.py`, mirroring
  `test_hosts_pi_graceful_unavailable` (lines 3015-3022).

## Verification Notes

_Added by `/ll:verify-issues` — 2026-08-31:_

- **PROPOSAL_UNSOUND gap resolved.** The `reconcile-issue` pass added two new
  Acceptance Criteria (`ll-init --hosts omp` info-only recognition;
  `test_wiring_guides_and_meta.py`/`test_init_core.py` passing) that now cover
  the Integration Map's Wiring Phase touchpoints previously missing from the
  AC list. Re-checked: `test_wiring_guides_and_meta.py`'s `_KNOWN_HOSTS` usage
  is not duplicated anywhere else in `scripts/tests/`, and
  `test_unknown_host_warns_and_skips` uses a `"codx"` typo (not `"omp"`), so
  adding `"omp"` to `_KNOWN_HOSTS` per this issue's plan does not silently
  break an unrelated fixture. Verdict upgraded from `PROPOSAL_UNSOUND` to
  `VALID`.
- **All file/line citations re-confirmed accurate** against the current
  working tree: `cli.py` `_KNOWN_HOSTS` (line 46-47), `opencode`/`pi`
  info-only branches (`cli.py:158-161`), `writers.py`'s three
  `install_*_adapter` functions (codex/kimi/qwen only), `hooks/adapters/opencode/`'s
  five-file shape, `thoughts/research/omp-hook-event-parity.md` existing,
  `pyproject.toml:202`, `test_wiring_guides_and_meta.py` lines 395/409,
  `test_init_core.py:3016`'s `test_hosts_pi_graceful_unavailable`. Both
  `depends_on: FEAT-1850` and `blocked_by: FEAT-2263` remain `Completed`;
  FEAT-2263's `blocks: [FEAT-2261]` backlink confirmed present.
- **`ll-verify-evidence` re-flagged the same single span** (line 240, the `PY`
  resolution one-liner, attributed to `BUG-2921`) — re-checked against
  `hooks/adapters/opencode/index.ts:28-35`, still a verbatim match with an
  independent `BUG-2921` citation in the source file's own comment. Same
  tool mis-attribution as the prior pass, not a fabrication. No decisions-log
  required rules are active (`ll-issues decisions list` returned no entries).

_Added by `/ll:verify-issues` — 2026-08-30:_

- **Dependencies resolved**: both `depends_on: FEAT-1850` and `blocked_by:
  FEAT-2263` are now `Completed` (2026-08-30). This issue is unblocked; the
  Dependency/Blocker subsection's framing of FEAT-2263 as pending is stale
  (already flagged as stale by the issue's own later Codebase Research
  Findings entry).
- **All spot-checked file/line citations confirmed accurate** against the
  current working tree: `cli.py` `_KNOWN_HOSTS` (line 46-47, no `"omp"`),
  the `opencode` info-only branch (`cli.py:158-159`), `writers.py`'s three
  `install_*_adapter` functions (codex/kimi/qwen only, no opencode/omp),
  `hooks/adapters/opencode/`'s five-file shape, `thoughts/research/omp-hook-event-parity.md`
  existing, `pyproject.toml:202`'s `include` line, `test_wiring_guides_and_meta.py`
  lines 395/409, `test_init_core.py`'s `test_hosts_pi_graceful_unavailable`
  (line 3016, issue cites 3015-3022 — off by one, immaterial), and all four
  cited `docs/reference/HOST_COMPATIBILITY.md`/`CLI.md`/`CONFIGURATION.md`
  passages (still stale exactly as the issue describes — these docs have not
  yet been updated).
- **`ll-verify-evidence` flagged one span** (line 232, the `PY` resolution
  one-liner) as unverifiable against artifact `BUG-2921`. Manually checked:
  the quote is the primary-cited artifact's own text (`hooks/adapters/opencode/index.ts:35`,
  verbatim match), and that file's comment at line 28 does independently say
  "Interpreter resolution (BUG-2921)" — confirming the issue's trailing
  `(cites BUG-2921)` annotation is accurate. This reads as a tool
  mis-attribution (parsing the trailing citation note as the quote's source
  artifact rather than the file named earlier in the same bullet), not a
  fabricated quote. Not treated as `EVIDENCE_UNVERIFIED` per the check's
  documented low precision (~0.13–0.20) and the manual confirmation above.
- **Real gap (drives the `PROPOSAL_UNSOUND` verdict)**: the Acceptance
  Criteria (5 items: adapter dir, session_start/tool-lifecycle dispatch,
  README, `test_omp_adapter.py` passing) do not cover the Integration Map's
  own Wiring Phase touchpoints — `cli.py`'s `_KNOWN_HOSTS` entry and
  `_dispatch_host_adapters()` info-only branch, the three doc updates
  (`HOST_COMPATIBILITY.md`, `CLI.md`, `CONFIGURATION.md`), and the new
  `test_init_core.py` info-branch test. An implementer satisfying only the
  stated ACs would ship an adapter directory that `ll-init --hosts omp`
  still can't see ("Unknown host"), and would risk breaking
  `test_host_tier_table_matches_known_hosts` (not named in the ACs' "tests
  pass" bar) by touching `_KNOWN_HOSTS` without the paired doc update.
  **Recommended fix**: add an AC covering the `ll-init --hosts omp`
  info-only wiring + doc-sync bar, e.g. "`ll-init --hosts omp` recognizes
  the host (no 'Unknown host' warning) and `python -m pytest
  scripts/tests/test_wiring_guides_and_meta.py scripts/tests/test_init_core.py`
  pass."

## Reference

- `hooks/adapters/codex/` — pattern to follow.
- FEAT-2263 — supplies the omp→ll event mapping.

## Impact

- **Effort**: S–M.
- **Risk**: Low — additive.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-24 | Priority: P4

## Related Key Documentation

- `.claude/CLAUDE.md` — `hooks/adapters/` is documented in CLAUDE.md's Key Directories as the host translation layer (one subdir per host), the exact location and pattern this issue adds an `omp/` entry to.
- `docs/reference/API.md` — the new adapter wires oh-my-pi events into the documented `hooks` module's `LLHookEvent`/dispatch surface.
- `docs/reference/HOST_COMPATIBILITY.md` — canonical host-tier matrix;
  test-enforced to match `_KNOWN_HOSTS` (see Integration Map § Documentation).
- `docs/reference/CLI.md` — `--hosts` flag reference lists `omp` as
  orchestration-only; goes stale once this issue lands.


## Session Log
- `/ll:manage-issue` - 2026-08-31T00:40:44 - `c19a644a-2049-4417-9707-c3efee1a32c2.jsonl`
- `/ll:ready-issue` - 2026-08-31T00:27:36 - `abd2995f-d536-485c-b52b-5acb4dc078b1.jsonl`
- `/ll:verify-issues` - 2026-08-31T00:23:03 - `470800f1-1e1f-4658-9a0d-f92dcc9a5ba1.jsonl`
- `/ll:reconcile-issue` - 2026-08-31T00:21:00 - `bff5b5e6-5bca-45ad-a7d7-7ef56a566108.jsonl`
- `/ll:verify-issues` - 2026-08-31T00:17:38 - `6e564d20-5c0b-4b6c-82b3-3245d607885e.jsonl`
- `/ll:wire-issue` - 2026-08-31T00:14:34 - `aa6600d2-f4d1-4767-840c-f507eecebb9f.jsonl`
- `/ll:decide-issue` - 2026-08-31T00:08:54 - `3b64954b-3476-4b2b-af07-173e51858225.jsonl`
- `/ll:refine-issue` - 2026-08-31T00:02:59 - `64d4acf2-4e85-412e-a5c4-fdd65db25c8c.jsonl`
- `/ll:refine-issue` - 2026-08-30T17:31:05 - `1854d5ae-85d4-485b-ae33-828a3400cc7b.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:46 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
