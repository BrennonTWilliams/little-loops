---
id: FEAT-3104
title: "Implement `OmpEmitter.emit_agent` against the FEAT-2797 `.omp/agents/` contract"
type: feature
status: open
priority: P5
parent: FEAT-2787
depends_on:
- FEAT-2260
relates_to:
- FEAT-2797
labels:
- host-compat
- omp
- adapters
---

# FEAT-3104: Implement `OmpEmitter.emit_agent` against the FEAT-2797 `.omp/agents/` contract

## Summary

Implement `OmpEmitter.emit_agent` in `scripts/little_loops/adapters/omp.py`,
replacing its raising stub, plus the matching `HOST_CAPABILITIES["omp"]`
agent fields and tests. Unlike skills/commands (which need FEAT-3103 first),
the agent-artefact format is already documented: FEAT-2797 established that omp
discovers agents via `.omp/agents/` with a frontmatter `output:` key (not a
reused `.claude/agents`/`.codex/agents` path), so this child is unblocked
and can start immediately.

## Parent Issue

Decomposed from FEAT-2787: Implement the `omp` host adapter (all
`OmpEmitter` methods currently raise).

## Location

- **File**: `scripts/little_loops/adapters/omp.py` — `OmpEmitter.emit_agent`
  (currently `raise AdapterError(_REMEDIATION)`)
- **File**: `scripts/little_loops/adapters/capabilities.py` —
  `HOST_CAPABILITIES["omp"]` entry (lines 102-118 at discovery), agent-related
  fields only: `config_dir`, `agent_output_format`, `frontmatter_fields_read`
  (if agent-specific keys apply), `agents=True`

## Proposed Solution

1. Implement `OmpEmitter.emit_agent(self, agent_meta: dict) -> str`, writing
   to `.omp/agents/` and populating the `output:` frontmatter key per
   FEAT-2797's documented contract (`docs/task-agent-discovery.md:37,60`).
   Resolve the open agent-routing fork noted in FEAT-2787's research: decide
   whether this is a genuine native format (mirror `KimiEmitter.emit_agent`,
   `adapters/kimi.py:127-158`) or delegates to `core._emit_degraded_agent`
   (the `GeminiEmitter` pattern) — FEAT-2797's contract points toward a
   native format (real `.omp/agents/` output path + real frontmatter key),
   so mirror the Kimi shape unless FEAT-2797 says otherwise.
   Follow the shared idempotency shape used by all three existing emitters:
   compute full target content, return `"skipped"` if the on-disk file
   already matches, else write and return `"adapted"`.
2. Update `HOST_CAPABILITIES["omp"]` (`capabilities.py`): set `config_dir`
   to omp's real config directory, `agent_output_format` to a descriptive
   string (mirroring the `codex`/`kimi-code` entries), populate
   `frontmatter_fields_read` for the `output:` key, and set `agents=True`.
3. Fix `scripts/little_loops/cli/verify_host_map.py:_check_emitter_agreement()`
   (lines 163-168): it currently hard-fails the moment
   `HOST_CAPABILITIES["omp"].agents` is truthy
   (`if omp_entry is not None and (omp_entry.agents or omp_entry.commands):
   raise ...`). Update this check now that `agents=True` is real, and fix
   the module docstring (lines 19-21) asserting "`omp` must stay
   `False`/`False`" to match.
4. Update `scripts/tests/test_verify_host_map.py::TestHostCapabilities::
   test_omp_fully_unimplemented` (lines 34-37): the `entry.agents is False`
   assertion no longer holds; `entry.commands is False` still holds (owned
   by FEAT-3105).
5. Update `scripts/tests/test_adapters.py:940-943`'s class-level docstring
   ("`omp` is explicitly excluded — its emitter is an all-stub") — no
   longer accurate once `emit_agent` is real.
6. Add `OmpEmitter.emit_agent` test coverage in `scripts/tests/
   test_adapters.py`, mirroring `TestKimiEmitterEmitAgent` (native-subagent
   shape, `test_not_degraded_no_inline_preamble`) or
   `TestCodexEmitterEmitAgent` (including
   `test_user_authored_file_not_overwritten`, lines 471-603) — whichever
   matches the routing decision made in step 1.
7. Update `docs/reference/HOST_COMPATIBILITY.md`'s "Adapter Host
   Capabilities" table (agent column only) and `docs/reference/API.md`'s
   agent-related mentions of the `OmpEmitter` stub.

## Acceptance Criteria

- `OmpEmitter.emit_agent` produces valid `.omp/agents/` artefacts per the
  FEAT-2797 contract and returns `"adapted"`/`"skipped"` per the shared
  emitter contract
- `ll-adapt --host omp --apply` no longer raises `AdapterError` on agent
  processing specifically (skill/command may still raise until FEAT-3105)
- `HOST_CAPABILITIES["omp"].agents` is `True` and `ll-verify-host-map`
  passes with the updated `_check_emitter_agreement()` logic
- Tests mirror the existing codex/kimi adapter agent test coverage
  (idempotency, dry-run, user-authored-file-not-overwritten if applicable)

## Impact

- **Scope**: Medium


## Session Log
- `/ll:issue-size-review` - 2026-08-08T10:09:55 - `70da93c7-f4f5-4a9e-85c1-cf030ebd11cb.jsonl`
