---
id: ENH-2883
title: Collapse per-host adapter emitters onto the capability map
type: ENH
parent: EPIC-2257
priority: P2
status: open
discovered_date: 2026-07-27
blocked_by:
- ENH-2873
relates_to:
- ENH-2874
labels:
- multi-host
- ll-adapt
---

# ENH-2883: Collapse per-host adapter emitters onto the capability map

Split from ENH-2873 (2026-07-27): that issue's Phase A (the capability map, the drift
verifier, and the `HOST_COMPATIBILITY.md` adapter section) is small, additive, and is the
whole of what ENH-2874 depends on. This — the refactor of live emission paths — is
Medium-risk and gated on a golden-output corpus. Chaining ENH-2874 behind it bought
nothing, so it moved here.

## Summary

With ENH-2873's capability map in place, the per-host emitters still carry policy: which
frontmatter fields a host reads, whether it accepts agents at all, how a tool list maps to
a sandbox mode. Drive those decisions from the map so the emitters retain only
serialization, and adding a host stops meaning writing a module.

## Current Behavior

`adapters/core.py` (306 lines) owns the shared pipeline — `process_skills` /
`process_commands` / `process_agents`, the frontmatter helpers, the `HostEmitter` protocol,
and the lazy `_EMITTER_MAP` registry — but each registry entry resolves to a class holding
host policy alongside its format writer:

- `codex.py` (395 lines): `_derive_sandbox_mode` from a tool list, `_derive_mcp_servers`,
  agent TOML formatting, skill-markdown synthesis.
- `gemini.py` (187 lines): `_inject_name`, `_strip_metadata_short_description`, command
  TOML formatting, and a hard agent stub behind `_AGENT_STUB_MSG`.
- `omp.py` (28 lines): a placeholder that raises for every artifact kind.

After ENH-2873 the map describes each host declaratively, but nothing reads it — `core.py`
still dispatches on the emitter class.

## Expected Behavior

`process_skills` / `process_commands` / `process_agents` read field-selection,
agent-support, and skip/stub decisions from the host's capability-map entry. Emitters
implement serialization only (a TOML writer and a markdown writer are irreducibly different
code, and stay code). A host needing behavior the map cannot express is a signal to add a
field to the map. Output for every currently-supported host is byte-identical to what
shipped before the refactor.

## Proposed Change

1. **Golden corpus first, before touching `core.py`** — capture
   `scripts/tests/fixtures/adapt/` snapshots over the current skill/command/agent corpus for
   `codex` (skills, commands, agents) and `gemini` (skills, commands). This is the safety
   net every other step depends on; landing it in a separate commit makes the refactor's
   diff reviewable against a fixed baseline.

2. **Drive `core.py` from the map** — replace per-host branching and emitter-held policy
   with lookups against the ENH-2873 capability entry: readable frontmatter fields, agent
   support, artifact kinds emitted, output directory.

3. **Reduce the emitters** — `CodexEmitter` and `GeminiEmitter` keep their format writers
   and any behavior genuinely not expressible as data; policy moves to the map. Where a
   derivation (e.g. `_derive_sandbox_mode`) is host-specific *logic* rather than a host
   *setting*, keep it as a function the map names, rather than forcing it into a data field.

4. **Fixture-host test** — register a synthetic fourth host through the map alone (entry +
   an existing serializer) and emit for it, proving no module was required.

## Acceptance Criteria

- [ ] Golden-corpus snapshots land in a commit **preceding** any `core.py` change, and the
      refactor leaves them byte-identical for `codex` (skills/commands/agents) and `gemini`
      (skills/commands) — or each difference is explained in the PR as intentional.
- [ ] The exclusions are named in the test, not silent: `omp` (emitter raises — no output to
      compare) and `gemini` agent emission (intentional preview stub, superseded for
      degraded hosts by ENH-2874).
- [ ] `core.py` contains no host-name branches; host behavior is read from the capability
      map. Asserted by a test, not by review alone.
- [ ] A test registers a fixture host via a map entry plus an existing serializer, emits
      for it, and passes — with no new module under `scripts/little_loops/adapters/`.
- [ ] `ll-verify-host-map` (ENH-2873) still passes, and `python -m pytest scripts/tests/`
      exits 0.

## Scope Boundaries

- **In scope**: the golden corpus, driving `core.py` from the map, thinning the emitters,
  the fixture-host test.
- **Out of scope**: the capability map, the drift verifier, and the `HOST_COMPATIBILITY.md`
  adapter section (all ENH-2873); the degraded-mode agent path (ENH-2874); implementing the
  `omp` emitter, which stays a stub; un-stubbing Gemini agent emission; hook adapters under
  `hooks/adapters/`, a separate translation layer.
- **Deliberate limit**: "zero per-host code" is not the goal and is not achievable. The
  target is that *policy* is data and *serialization* is pluggable code the data selects.

## Impact

- **Priority**: P2 — the payoff of ENH-2873's map; without it the map is descriptive only
  and the per-host drift it was built to prevent can still happen.
- **Effort**: Medium — the corpus is mechanical; the `core.py` refactor is the bulk.
- **Risk**: Medium — touches live emission paths for hosts in use. Mitigated entirely by
  the corpus landing first; the byte-identity AC is the gate.
- **Breaking Change**: No — entry points, CLI surface, and emitted output all unchanged.

## Status

**Open** | Created: 2026-07-27 | Priority: P2
