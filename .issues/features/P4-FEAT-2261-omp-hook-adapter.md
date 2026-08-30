---
id: FEAT-2261
title: "omp hook adapter \u2014 hooks/adapters/omp/"
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
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
---

# FEAT-2261: omp hook adapter — hooks/adapters/omp/

## Summary

Create `hooks/adapters/omp/` translating oh-my-pi (`omp`) lifecycle events into
`LLHookEvent` and invoking the host-agnostic ll hook handler. Analogous to
`hooks/adapters/codex/`.

## Motivation

oh-my-pi exposes richer hook events than vanilla pi-mono, so the parity gap
that plagued the cancelled Pi adapter (FEAT-1715) is expected to be narrower.
The exact event set is established by FEAT-2263 (hook-event parity audit).

## Acceptance Criteria

- `hooks/adapters/omp/` exists with an event→handler mapping.
- A `session_start`-equivalent omp event triggers the `session_start` ll intent.
- At least one tool-lifecycle omp event triggers `pre_tool_use`/`post_tool_use`.
- `hooks/adapters/omp/README.md` documents activation + the event mapping table.
- Tests in `scripts/tests/test_omp_adapter.py` pass.

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
- `scripts/little_loops/hooks/adapters/omp/*` — the runnable shim(s) plus a
  host-native config template (the `hooks.json`/`hooks.toml`/`settings-block.json`
  analog, whichever shape omp needs). **Whether these are Bash shims (Codex-shaped)
  or an in-process TS/Bun plugin (OpenCode-shaped) is not yet decidable by
  analogy** — omp is itself a Bun package (`@oh-my-pi/pi-coding-agent`), so it is
  not automatically Codex-shaped just because Codex has no Bun SDK. This is the
  open question FEAT-2263's audit (currently unblocked, its own research doc
  `thoughts/research/omp-hook-event-parity.md` not yet written) must resolve
  before this file's shape can be chosen.
- `scripts/tests/test_omp_adapter.py` — required by this issue's own acceptance
  criteria; naming matches the existing `scripts/tests/test_<host>_adapter.py`
  convention (`test_codex_adapter.py`, `test_kimi_adapter.py`, `test_qwen_adapter.py`).

### Files to Modify

- `scripts/little_loops/init/cli.py` — `_KNOWN_HOSTS` (a `frozenset`) has no
  `"omp"` entry, and `_dispatch_host_adapters()` has no `elif host == "omp":`
  branch — its own comment states omp is "deliberately absent because they have
  no install wiring and would warn 'Unknown host'." Both need an omp entry for
  `ll-init` to wire this adapter.
- `scripts/little_loops/init/writers.py` — needs a new `install_omp_adapter()`
  function, matching the return-value convention of `install_codex_adapter()`/
  `install_kimi_adapter()` in the same file (`None` = template missing from
  package install, `False` = destination exists without `--force` (no-op skip),
  `True` = written).

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
- Adapter test files follow `scripts/tests/test_<host>_adapter.py` and assert
  file existence + executability at minimum; two further conventions coexist
  and disagree — Codex's subprocess/sentinel-file approach
  (`test_adapter_sets_ll_hook_host_codex`, stubs a fake `hooks/__main__.py` on
  `PYTHONPATH`) vs. Qwen's lighter substring-match approach (`EXPECTED_SHIMS`
  dict + `"export LL_HOOK_HOST=qwen" in body` assertions) — either satisfies
  the acceptance criteria's "Tests ... pass" bar.

### Reference Templates (read-only)

- `hooks/adapters/codex/README.md` — the explicit pattern-to-follow cited in
  this issue's own Reference section (4-column mapping table, README skeleton).
- `scripts/little_loops/hooks/adapters/codex/*.sh` + `hooks.json` — Bash-shim
  transport layer, the closest analog if FEAT-2263 finds omp is CLI-hook-shaped.
- `hooks/adapters/opencode/index.ts` — TS/Bun-plugin transport layer, the
  closest analog if FEAT-2263 finds omp needs an in-process plugin instead.

### Dependency / Blocker

- `blocked_by: FEAT-2263` — the omp→ll event mapping and the Bash-vs-TS-plugin
  shim-shape decision both depend on FEAT-2263's audit landing first; that
  issue is unblocked (its own `depends_on: FEAT-1850, FEAT-2797` are
  satisfied/being resolved) but its research doc
  (`thoughts/research/omp-hook-event-parity.md`) does not exist yet.

## Program Design

_Added by `/ll:refine-issue` — populated from analyzer findings; the intent-to-event
mapping itself is pending FEAT-2263, so this states only what is already fixed by
the existing host-agnostic dispatch layer._

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
- New: `install_omp_adapter(...)` (`scripts/little_loops/init/writers.py`) —
  matches the `None`/`False`/`True` return convention of `install_codex_adapter()`
  in the same file.

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

## Implementation Steps

_Added by `/ll:refine-issue` — outcome-phrased, concrete references; ordering
is incidental except where FEAT-2263's output is a hard prerequisite._

1. Once FEAT-2263's `thoughts/research/omp-hook-event-parity.md` exists, the
   omp→ll event mapping and the Bash-vs-TS-plugin shim shape are both settled —
   this issue's shim(s) cannot be written correctly before that.
2. `scripts/little_loops/init/cli.py`'s `_KNOWN_HOSTS` and `_dispatch_host_adapters()`
   gain an `"omp"` entry so `ll-init` can wire the adapter (currently absent by
   the file's own comment).
3. `scripts/little_loops/init/writers.py` gains `install_omp_adapter()`,
   matching `install_codex_adapter()`'s file-existence/`--force` semantics.
4. Each new shim exports `LL_HOOK_HOST=omp` and forwards its native event to
   `python -m little_loops.hooks <intent>` unmodified — no adapter-side business
   logic, per the "adapter-as-pure-transport" convention documented above.
5. `hooks/adapters/omp/README.md` documents the event mapping and activation,
   matching the 4-column Codex shape FEAT-2263 already directs.
6. `scripts/tests/test_omp_adapter.py` covers file existence, executability, and
   at least one host-identification assertion (either convention above satisfies
   this), plus this issue's own acceptance criteria (`session_start`-equivalent
   and at least one tool-lifecycle event dispatching correctly).
7. Verify: `python -m pytest scripts/tests/test_omp_adapter.py -v` passes.

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


## Session Log
- `/ll:refine-issue` - 2026-08-30T17:31:05 - `1854d5ae-85d4-485b-ae33-828a3400cc7b.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:46 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
