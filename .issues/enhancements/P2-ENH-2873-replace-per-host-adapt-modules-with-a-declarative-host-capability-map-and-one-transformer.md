---
id: ENH-2873
title: Replace per-host adapt modules with a declarative host-capability map and one transformer
type: ENH
parent: EPIC-2257
priority: P2
status: open
discovered_date: 2026-07-27
labels:
- multi-host
- ll-adapt
---

# ENH-2873: Replace per-host adapt modules with a declarative host-capability map and one transformer

Origin: ll-product #ENH-056

Parent EPIC: EPIC-2257 (multi-host generalization — portfolio coordination), which already
owns shared per-host infrastructure including skill/command adapters.

## Summary

Adding an adapter host today means writing a module. `scripts/little_loops/adapters/`
carries `codex.py` (395 lines), `gemini.py` (187), and `omp.py` (28, a stub), and the
host-specific knowledge inside them — which frontmatter fields the host reads, whether it
takes agents at all, how tools map to a sandbox mode — is expressed as code rather than as
data, so it can drift between hosts with nothing to catch it. Move that knowledge onto a
declarative per-host entry and leave the emitters as format serializers only.

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

Adding an adapter host is a data change plus a documentation row. A new host that needs
behavior the map cannot express is a signal to add a field to the map, not a module. The
capability map and `HOST_COMPATIBILITY.md` are mechanically checked against each other, so
the "two sources cannot disagree" claim is enforced rather than asserted, and the
relationship between the build-time adapter map and the runtime `HostCapabilities` is
stated explicitly rather than left as two independent notions of "capability."

## Proposed Change

Two separable phases. Phase A is the whole of what ENH-2874 depends on and is
independently shippable; Phase B is the payoff.

### Phase A — the map, and its relationship to what already exists

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

### Phase B — collapse policy into the map

5. Drive `process_skills` / `process_commands` / `process_agents` from the map:
   field-selection, agent-support, and skip/stub decisions read from the entry instead of
   from per-host branches. Emitters retain only serialization (TOML vs. markdown writers)
   plus genuinely non-data behavior.

6. Capture a **golden-output corpus before any refactor** (`scripts/tests/fixtures/adapt/`)
   over the current skill/agent/command corpus for `codex` (skills, commands, agents) and
   `gemini` (skills, commands), and assert byte-identity after.

## Acceptance Criteria

- [ ] A capability map exists with one entry per adapter host, and its relationship to
      `host_runner.HostCapabilities` is stated in-code (option (a) or (b) above), not left
      implicit.
- [ ] `ll-verify-host-map` exits non-zero when a map key has no `HOST_COMPATIBILITY.md`
      row, when a documented adapter host has no map entry, and when a shared host's flags
      contradict `host_runner`. A pytest test invokes it and asserts exit 0 for the current
      tree.
- [ ] `docs/reference/HOST_COMPATIBILITY.md` covers all three adapter hosts including
      `omp`, and carries a `Last Verified` date plus a point-in-time warning that is
      distinct from `Last Updated`.
- [ ] **Byte-identity, scoped honestly**: golden-corpus snapshots for `codex`
      (skills/commands/agents) and `gemini` (skills/commands) are byte-identical before and
      after, or each difference is explained in the PR. `omp` is excluded (its emitter
      raises — there is no output to compare), and `gemini` agent emission is excluded (an
      intentional preview stub); both exclusions are named in the test, not silent.
- [ ] Adding a hypothetical fourth host requires only a map entry, a doc row, and a
      serializer if its output format is new — demonstrated by a test that registers a
      fixture host through the map alone and emits for it.
- [ ] `ll-verify-cli-allowlist` (BUG-2764) still passes if any entry point changes.

## Scope Boundaries

- **In scope**: `adapters/capabilities.py`, the drift verifier, `HOST_COMPATIBILITY.md`
  adapter section, and driving `core.py` from the map.
- **Out of scope**: implementing the `omp` emitter (still a stub after this issue — the map
  gains an entry describing it, the emitter stays unimplemented); un-stubbing Gemini agent
  emission (blocked on the vendor preview, and superseded for degraded hosts by ENH-2874);
  any change to `host_runner`'s runtime dispatch behavior; hook adapters under
  `hooks/adapters/`, which are a separate translation layer.
- **Already done — do not re-do**: `ll-adapt-skills-for-codex` and
  `ll-adapt-agents-for-codex` are *already* thin aliases that delegate to `CodexEmitter` +
  `adapters.core` (see the module docstring in `cli/adapt_skills_for_codex.py`). The
  original framing of this issue asked for that work; it exists. Only re-verify it still
  holds after Phase B.
- **Deliberate limit**: "zero per-host code" is not achievable and is not the goal. A TOML
  writer and a markdown writer are irreducibly different code. The target is that *policy*
  (which fields, which artifacts, which capabilities) is data and *serialization* is
  pluggable code selected by that data.

## Impact

- **Priority**: P2 — prerequisite for ENH-2874, and the per-host drift it prevents is
  silent (a host quietly emitting a field another host reads, or missing one it needs).
- **Effort**: Medium — Phase A is small (one dataclass module, one verifier, one doc
  section); Phase B is the bulk, gated on the golden corpus landing first.
- **Risk**: Medium — a refactor of live emission paths. Mitigated by capturing golden
  output before touching `core.py`; the byte-identity AC is the safety net.
- **Breaking Change**: No — entry points and CLI surface unchanged.

## Notes

Prerequisite for ENH-2874: that issue selects its emission path from the `subagents`
capability flag introduced here. Phase A alone unblocks it.

## Status

**Open** | Created: 2026-07-27 | Priority: P2
