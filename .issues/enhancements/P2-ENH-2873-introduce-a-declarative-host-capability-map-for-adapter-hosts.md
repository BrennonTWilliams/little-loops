---
id: ENH-2873
title: Introduce a declarative host-capability map for adapter hosts
type: ENH
parent: EPIC-2257
priority: P2
status: done
completed_at: '2026-07-28T05:34:07Z'
discovered_date: 2026-07-27
blocks:
- ENH-2874
- ENH-2883
labels:
- multi-host
- ll-adapt
decision_needed: false
confidence_score: 98
outcome_confidence: 93
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 23
---

# ENH-2873: Introduce a declarative host-capability map for adapter hosts

Origin: ll-product #ENH-056

Parent EPIC: EPIC-2257 (multi-host generalization — portfolio coordination), which already
owns shared per-host infrastructure including skill/command adapters.

Scope note (2026-07-27): originally written as map + emitter collapse. The emitter refactor
is Medium-risk and gated on a golden-output corpus, while this half is small, additive, and
is the whole of what ENH-2874 depends on — so the refactor split out to ENH-2883 rather
than chaining ENH-2874 behind it.

## Summary

Adding an adapter host today means writing a module, because host-specific knowledge —
which frontmatter fields the host reads, whether it takes agents at all, how tools map to a
sandbox mode — lives as code in `adapters/codex.py` (395 lines), `gemini.py` (187), and
`omp.py` (28, a stub), where it can drift between hosts with nothing to catch it. There are
also already three partial, independently maintained views of "what a host supports."
Establish one declarative per-host entry, reconcile it with what exists, and make the
doc↔map relationship mechanically checked. ENH-2883 then drives emission from it.

## Current Behavior

`adapters/core.py` (306 lines) is **already** the shared transformer: it owns
`process_skills` / `process_commands` / `process_agents`, the frontmatter helpers
(`_read_frontmatter`, `_extract_body`, `_is_model_invocation_disabled`), the `HostEmitter`
protocol, and a lazy `_EMITTER_MAP` registry keyed by host name. The issue is not the
absence of a generic path — it is that each registry entry resolves to a class carrying
policy, not just serialization:

- `codex.py` derives sandbox mode from a tool list (`_derive_sandbox_mode`), derives MCP
  servers (`_derive_mcp_servers`), formats agent TOML, and synthesizes skill markdown.
- `gemini.py` injects `name:`, strips `metadata.short_description`, formats command TOML,
  and hard-stubs agent emission behind `_AGENT_STUB_MSG` (Gemini agents are a preview
  feature).
- `omp.py` is a 28-line placeholder whose emitter raises with a "not yet implemented"
  remediation string.

Separately, `host_runner.py` already defines a **runtime** capability surface —
`HostCapabilities(streaming, permission_skip, agent_select, tool_allowlist,
structured_output)` plus `HostRunner.describe_capabilities()`, consumed by `ll-doctor`.
Its host set (claude-code, codex, opencode, pi) overlaps but does not match the adapter
host set (codex, gemini, omp). `docs/reference/HOST_COMPATIBILITY.md` is a third,
hand-maintained view; it is stamped `Last Updated: 2026-07-03`, covers hooks/orchestration,
and has no `omp` row at all.

## Expected Behavior

One declarative entry per adapter host is the single place host knowledge is written. The
capability map and `HOST_COMPATIBILITY.md` are mechanically checked against each other, so
the "two sources cannot disagree" claim is enforced rather than asserted, and the
relationship between the build-time adapter map and the runtime `HostCapabilities` is
stated explicitly rather than left as two independent notions of "capability." Emission
behavior is unchanged by this issue — the map is authoritative but not yet consumed by
`core.py` (that is ENH-2883).

## Proposed Change

1. **`scripts/little_loops/adapters/capabilities.py`** (new) — one declarative entry per
   adapter host, keyed the same as `_EMITTER_MAP`: config dir, output formats per artifact
   kind (skills / commands / agents), which frontmatter fields the host reads, agent file
   format, and capability flags (`agents`, `hooks`, `subagents`, …). A frozen dataclass,
   matching the `frozen=True` value-object convention `HostInvocation` establishes.

2. **Reconcile with `host_runner.HostCapabilities` — this is a required decision, not an
   implementation detail.** Pick one and record it in the module docstring:
   - (a) the adapter map **extends/embeds** `HostCapabilities` for hosts present in both, or
   - (b) it is a distinct **build-time** surface, with a docstring on each side pointing at
     the other and naming the split (emission-time vs. invocation-time).

   Shipping a third independent notion of "capability" while this issue's own thesis is
   "no independently maintained sources that can disagree" is the failure mode to avoid.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option A**: the adapter map extends/embeds `HostCapabilities` for hosts present in
both.

**Option B**: it is a distinct build-time surface, with a docstring on each side
pointing at the other and naming the split (emission-time vs. invocation-time).

> **Selected:** Option B — distinct build-time surface, cross-referenced by docstring; no
> inheritance. `adapters/core.py` has zero import coupling with `host_runner.py` today, and
> the adapter-host key set (`codex`, `gemini`, `omp`) is not congruent with the runtime host
> set (adds `claude-code`, `opencode`, `pi`), which makes an "extends" relationship
> structurally awkward. `cli/doctor.py`'s `CheckResult` (mirrors `host_runner.CapabilityEntry`
> in its docstring without subclassing it) is direct precedent for this shape.

`host_runner.py`'s `HostCapabilities` (frozen dataclass, lines 118-136: `streaming`,
`permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`) is a *runtime
invocation* surface — each `HostRunner` subclass sets a class-level `capabilities =
HostCapabilities(...)` and implements `describe_capabilities() -> CapabilityReport`
(a hand-written `list[CapabilityEntry]`, e.g. `ClaudeCodeRunner.describe_capabilities`
line 382, `CodexRunner.describe_capabilities` line 671). A prior drift between the
boolean flags and the `CapabilityEntry.status` strings was manually corrected per
BUG-2759 (comment at `host_runner.py:392-395`) — direct evidence the two views can
already disagree today, which is exactly the failure mode Option B's cross-reference
docstrings and the new verifier's third check (shared-host contradiction) are meant to
catch mechanically instead of by manual discovery. `docs/reference/HOST_COMPATIBILITY.md`
already has a `## Runner Capabilities` section (line 124) mirroring
`HostCapabilities`/`CapabilityEntry` — the artifact `ll-verify-host-map` cross-checks
against for the adapter-host section this issue adds.

The adapter-side host set (`codex`, `gemini`, `omp` — `adapters/core.py`'s
`_EMITTER_MAP`, lines 45-49) and the runtime `_HOST_RUNNER_REGISTRY`
(`host_runner.py:1255`: `claude-code`, `codex`, `opencode`, `pi`, `gemini`, `omp`) are
already non-identical sets (e.g. `claude-code`/`opencode`/`pi` have no adapter-side
entry at all), which is a structural argument for Option B — an "extends" relationship
(Option A) is awkward when the key sets don't line up 1:1.

3. **`ll-verify-host-map`** (new `ll-verify-*` entry point, repo idiom) — asserts every
   capability-map key has a `HOST_COMPATIBILITY.md` row and vice versa, and that hosts
   present in both the adapter map and `host_runner` do not contradict each other on
   shared flags. Wired into `scripts/tests/` as a pytest gate (no hosted CI — see
   CLAUDE.md § Testing & CI Policy) and into `ll-doctor --full` alongside the other
   `ll-verify-*` checks.

4. **`docs/reference/HOST_COMPATIBILITY.md`** — add an adapter-host section covering
   codex / gemini / omp (omp is currently absent entirely), and a **`Last Verified`** date
   with a point-in-time warning, distinct from the existing `Last Updated` line: *updated*
   means the file changed, *verified* means someone re-checked the vendor's product. State
   which artifact is authored and which is derived.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-28.

**Selected**: Option B — distinct build-time surface, cross-referenced by docstring

**Reasoning**: Option A (extends/embeds `HostCapabilities`) has no inheritance precedent
anywhere in the codebase — the only related pattern (`HostInvocation.capabilities:
HostCapabilities`) is composition, not subclassing — and the adapter-host key set
(`codex`/`gemini`/`omp`) is not congruent with the runtime host set (adds
`claude-code`/`opencode`/`pi`), making "extends" structurally awkward for hosts on only
one side of the set. Option B has a direct, working precedent: `cli/doctor.py`'s
`CheckResult` frozen dataclass explicitly documents itself as mirroring
`host_runner.CapabilityEntry`'s shape without inheriting from it, and imports
`host_runner` only under `TYPE_CHECKING` — the same one-directional, docstring-linked,
runtime-decoupled relationship this option proposes. `adapters/core.py` currently has
zero imports from `host_runner.py` at all, so Option B requires no new coupling.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 0/3 | 1/3 | 2/3 | 1/3 | 4/12 |
| Option B | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: No dataclass-inheritance precedent exists in `scripts/little_loops/`; adapter
  host keys (`codex`/`gemini`/`omp`) and runtime host keys (adds `claude-code`/`opencode`/`pi`)
  are non-identical, undermining a 1:1 "extends" relationship.
- Option B: `cli/doctor.py:32-47`'s `CheckResult` already mirrors `host_runner.CapabilityEntry`
  by docstring cross-reference with a `TYPE_CHECKING`-only import — direct, working precedent
  for the proposed relationship, with zero new runtime coupling required.

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/capabilities.py` (new) — the frozen-dataclass per-host
  entry, keyed to match `adapters/core.py`'s `_EMITTER_MAP` (`"codex"`, `"gemini"`,
  `"omp"`).
- `scripts/little_loops/cli/verify_host_map.py` (new) — the `ll-verify-host-map` checker,
  following the `_run() -> tuple[int, ...]` + `main_verify_host_map()` +
  `cli_event_context` shape of `scripts/little_loops/cli/verify_cli_allowlist.py`.
- `scripts/pyproject.toml:101` — add `ll-verify-host-map = "little_loops.cli:main_verify_host_map"`
  next to the existing `ll-verify-cli-allowlist` entry.
- `scripts/little_loops/cli/__init__.py:90,135` — import and re-export
  `main_verify_host_map` alongside the other `main_verify_*` functions.
- `scripts/little_loops/cli/doctor.py:624-637` — add `_full_host_map_data()` +
  `@register_full_check _full_host_map_check()`, mirroring the adjacent
  `_full_kinds_data()`/`_full_kinds_check()` pair (lines 455-638), so `ll-doctor --full`
  picks up the new verifier.
- `docs/reference/HOST_COMPATIBILITY.md:124` — the existing `## Runner Capabilities`
  section (mirroring `HostCapabilities`/`CapabilityEntry`) gets a sibling adapter-host
  section plus the `Last Verified` date/warning; add the missing `omp` row here too.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/adapters/core.py` — `HostEmitter` Protocol (lines 25-39),
  `_EMITTER_MAP` (45-49), `resolve_emitter()` (52) is the registry the new map must key
  identically to.
- `scripts/little_loops/adapters/codex.py` — `_derive_sandbox_mode` (173),
  `_derive_mcp_servers` (188), `CodexEmitter` (255) is the behavior the map's codex entry
  must agree with (AC: "map entries agree with what emitters actually do").
- `scripts/little_loops/adapters/gemini.py` — `_AGENT_STUB_MSG` (16), `GeminiEmitter`
  (106); `emit_agent` (186) unconditionally raises — the map's `gemini.agents` flag must
  reflect this stub, not aspirational support.
- `scripts/little_loops/adapters/omp.py` — 28-line stub, `OmpEmitter` (16), all three
  `emit_*` methods raise `AdapterError(_REMEDIATION)` — the map entry describes this
  as fully unimplemented, per Scope Boundaries.
- `scripts/little_loops/host_runner.py` — `HostCapabilities` (118-136), `HostInvocation`
  (139-157, establishes the `frozen=True` convention this new module follows),
  `CapabilityEntry`/`CapabilityReport` (160/173), `_HOST_RUNNER_REGISTRY` (1255,
  `claude-code`/`codex`/`opencode`/`pi`/`gemini`/`omp` — a *different* key set than the
  adapter side, direct evidence for the Option A/B split above). BUG-2759 (comment at
  `host_runner.py:392-395`) documents a prior manual fix for exactly the
  boolean-flag-vs-`CapabilityEntry.status` drift this issue's verifier targets.
- `scripts/little_loops/cli/adapt.py`, `cli/adapt_skills_for_codex.py`,
  `cli/adapt_agents_for_codex.py` — call `resolve_emitter()`; unaffected by this issue
  (map is not yet consumed) but are the reason emission-output-unchanged matters.

### Similar Patterns
- `scripts/little_loops/cli/verify_cli_allowlist.py` (full file, 138 lines) — the
  `ll-verify-*` idiom to model `ll-verify-host-map` after: a pure `_run() -> tuple[int,
  dict[str, list[str]]]`, a `main_verify_cli_allowlist()` wrapping it in
  `cli_event_context(DEFAULT_DB_PATH, "ll-verify-cli-allowlist", sys.argv[1:])` +
  argparse, `OK:`/`ERROR:` output.
- `scripts/little_loops/cli/verify_design_tokens.py` — alternative idiom using
  `@dataclass` violation value-objects (`ThemeViolation`, `ProfileResult`) instead of raw
  dicts; worth following if the host-map mismatch payload benefits from named fields.
- `host_runner.py`'s `HostInvocation` (139-157) and `CapabilityEntry`/`CapabilityReport`
  (160/173) — the `frozen=True` dataclass convention `capabilities.py`'s per-host entry
  should follow, including `field(default_factory=...)` for any list/dict fields.
- `scripts/little_loops/cli/doctor.py`'s `_full_kinds_data()`/`_full_kinds_check()`
  (near line 624) — the `@register_full_check` wiring pattern for `ll-doctor --full`.

### Tests
- `scripts/tests/test_verify_cli_allowlist.py` — pattern to model the new
  `test_verify_host_map.py` after: exercises `_run()`/helpers directly, plus a
  `main_verify_*` smoke test patching `sys.argv` and asserting exit code via `capsys`.
- `scripts/tests/test_adapters.py`, `test_codex_adapter.py` — existing adapter/emitter
  coverage; the AC's "emission unchanged" check should assert against these emitters'
  actual `emit_skill`/`emit_command`/`emit_agent` output.
- `scripts/tests/test_snapshot_output_primitives.py` (syrupy-based, `__snapshots__/*.ambr`
  golden files) — the closest existing shape for a golden-output test asserting
  `resolve_emitter("codex").emit_skill(...)` output is unchanged; regenerate via
  `pytest --snapshot-update`.
- `scripts/tests/test_host_runner.py` — existing `HostCapabilities`/`describe_capabilities()`
  coverage relevant to the reconciliation decision's tests.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:124` — `## Runner Capabilities` section already
  mirrors `HostCapabilities`/`CapabilityEntry`; this is the cross-check target for
  `ll-verify-host-map`'s "map ↔ doc agreement" check, alongside the new adapter-host
  section this issue adds.

## Acceptance Criteria

- [x] A capability map exists with one entry per adapter host, and its relationship to
      `host_runner.HostCapabilities` is stated in-code (option (a) or (b) above), not left
      implicit.
- [x] `ll-verify-host-map` exits non-zero when a map key has no `HOST_COMPATIBILITY.md`
      row, when a documented adapter host has no map entry, and when a shared host's flags
      contradict `host_runner`. A pytest test invokes it and asserts exit 0 for the current
      tree.
- [x] `docs/reference/HOST_COMPATIBILITY.md` covers all three adapter hosts including
      `omp`, and carries a `Last Verified` date plus a point-in-time warning that is
      distinct from `Last Updated`.
- [x] **Emission output is unchanged.** This issue adds a map and a verifier; it does not
      touch `core.py`'s dispatch. A test asserts current `codex`/`gemini` output is
      identical before and after — the map's correctness is checked against the emitters'
      existing behavior, not by rewriting them.
- [x] The map's entries are asserted to agree with what the emitters actually do today
      (e.g. `gemini.agents = none` matches `_AGENT_STUB_MSG`; `omp` declares no working
      emitter). A map that describes the wrong thing is worse than no map, and ENH-2883
      will consume it as truth.
- [x] `ll-verify-cli-allowlist` (BUG-2764) still passes if any entry point changes.

## Scope Boundaries

- **In scope**: `adapters/capabilities.py`, the reconciliation decision with
  `host_runner.HostCapabilities`, the drift verifier, and the `HOST_COMPATIBILITY.md`
  adapter section.
- **Out of scope**: driving `core.py` from the map and thinning the emitters (**ENH-2883**);
  the degraded-mode agent path (ENH-2874); implementing the `omp` emitter (still a stub —
  the map gains an entry describing it, the emitter stays unimplemented); un-stubbing
  Gemini agent emission (blocked on the vendor preview, and superseded for degraded hosts
  by ENH-2874); any change to `host_runner`'s runtime dispatch behavior; hook adapters
  under `hooks/adapters/`, which are a separate translation layer.
- **Already done — do not re-do**: `ll-adapt-skills-for-codex` and
  `ll-adapt-agents-for-codex` are *already* thin aliases that delegate to `CodexEmitter` +
  `adapters.core` (see the module docstring in `cli/adapt_skills_for_codex.py`). The
  original framing of this issue asked for that work; it exists. Only re-verify it still
  holds after Phase B.
- **Deliberate limit**: "zero per-host code" is not achievable and is not the goal, here or
  in ENH-2883. A TOML writer and a markdown writer are irreducibly different code. The
  target is that *policy* (which fields, which artifacts, which capabilities) is data and
  *serialization* is pluggable code selected by that data.

## Impact

- **Priority**: P2 — prerequisite for both ENH-2874 and ENH-2883, and the per-host drift it
  prevents is silent (a host quietly emitting a field another host reads, or missing one it
  needs).
- **Effort**: Small — one frozen-dataclass module, one `ll-verify-*` entry point plus its
  pytest gate, one documentation section.
- **Risk**: Low — purely additive. No emission path changes; the map is authoritative but
  not yet consumed.
- **Breaking Change**: No — entry points and CLI surface unchanged.

## Notes

Unblocks two issues that both read the map: ENH-2874 (selects its emission path from the
`subagents` flag) and ENH-2883 (drives `core.py` from the entries).

## Status

**Open** | Created: 2026-07-27 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-07-28T05:33:09 - `fc816510-5995-4ef2-a872-011c8ec32fb4.jsonl`
- `/ll:decide-issue` - 2026-07-28T05:19:40 - `1f7ee74d-825c-4852-93aa-d85cdb82a4e0.jsonl`
- `/ll:refine-issue` - 2026-07-28T05:16:09 - `8f9e2931-6d89-4c96-876d-c002e3cf197c.jsonl`
