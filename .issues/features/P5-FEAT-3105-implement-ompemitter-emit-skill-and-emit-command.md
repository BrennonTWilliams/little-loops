---
id: FEAT-3105
title: "Implement `OmpEmitter.emit_skill`/`emit_command` against the FEAT-3103 discovery format"
type: feature
status: open
priority: P5
parent: FEAT-2787
depends_on:
- FEAT-2260
- FEAT-3103
labels:
- host-compat
- omp
- adapters
---

# FEAT-3105: Implement `OmpEmitter.emit_skill`/`emit_command` against the FEAT-3103 discovery format

## Summary

Implement `OmpEmitter.emit_skill` and `OmpEmitter.emit_command` in
`scripts/little_loops/adapters/omp.py`, replacing their raising stubs, once
FEAT-3103's research spike has documented omp's native skill/command
discovery format. Blocked on FEAT-3103 — do not start implementation before
that spike's `thoughts/research/omp-skill-command-surface.md` artifact
lands.

## Parent Issue

Decomposed from FEAT-2787: Implement the `omp` host adapter (all
`OmpEmitter` methods currently raise).

## Location

- **File**: `scripts/little_loops/adapters/omp.py` — `OmpEmitter.emit_skill`,
  `OmpEmitter.emit_command` (currently both `raise
  AdapterError(_REMEDIATION)`)
- **File**: `scripts/little_loops/adapters/capabilities.py` —
  `HOST_CAPABILITIES["omp"]` entry, skill/command-related fields:
  `skill_output_format`, `command_output_format`, remaining
  `frontmatter_fields_read` entries, `commands=True`
- **File**: `scripts/little_loops/cli/adapt.py` — resolve the
  `process_commands`'s `output_dir` design fork (currently `cmd_meta
  ["output_dir"]` is unconditionally the plugin's `skills_dir`,
  `adapt.py:113-115`): decide whether `OmpEmitter.emit_command` bridges into
  `skills_dir` (Codex shape, `codex.py:303`) or self-derives an omp-native
  path (Gemini shape, `gemini.py:127-129`), per FEAT-3103's findings

## Proposed Solution

1. Read FEAT-3103's `thoughts/research/omp-skill-command-surface.md`
   (landed 2026-08-08) for omp's actual skill and command discovery layout.
2. Implement `OmpEmitter.emit_skill(self, skill_meta: dict) -> str` per that
   format, following the shared idempotency shape (compute full content,
   `"skipped"` on byte-match, else write and return `"adapted"`).
3. Implement `OmpEmitter.emit_command(self, cmd_meta: dict) -> str`,
   resolving the `output_dir` design fork per FEAT-3103's findings.
4. Update `HOST_CAPABILITIES["omp"]` (`capabilities.py`): set
   `skill_output_format`, `command_output_format`, remaining
   `frontmatter_fields_read` entries, and `commands=True`.
5. Confirm/update `scripts/little_loops/cli/verify_host_map.py:
   _check_emitter_agreement()` and its module docstring (already touched by
   FEAT-3104 for `agents`; this issue adds the `commands` half of the same
   check).
6. Update `scripts/tests/test_verify_host_map.py::TestHostCapabilities::
   test_omp_fully_unimplemented` (lines 34-37): remove/flip the
   `entry.commands is False` assertion.
7. Update `scripts/tests/test_adapters.py:89-92`
   (`TestResolveEmitter::test_omp_returns_emitter_that_raises`) — no longer
   raises; replace with real skill/command emit coverage mirroring
   `TestCodexEmitterEmitSkill`/`EmitCommand` (`test_adapters.py:350-603`),
   using the `_meta`/`_make_skill`/`_make_command` fixture builders
   (lines 29-76): `test_returns_adapted_on_first_run`,
   `test_dry_run_does_not_write`, `test_already_adapted_returns_skipped`,
   `test_idempotent`.
8. Update `scripts/tests/test_adapt_golden_corpus.py:196-214`
   (`test_omp_and_gemini_agent_excluded_from_byte_identity_claim` asserts
   `OmpEmitter().emit_skill({})` raises) and its module docstring
   (lines 13-15, the "28-line stub" named exclusion) — both now stale.
9. Update `docs/reference/HOST_COMPATIBILITY.md`'s "Skill discovery" /
   "Slash-command discovery" rows and "Adapter Host Capabilities" table
   (skill/command columns), and `docs/reference/API.md`'s remaining stub
   references (module-summary table, `## little_loops.adapters` section
   intro, `AdapterError` docstring, `Built-in emitters` table row).
10. Update `docs/ARCHITECTURE.md` § "Host Adapter Capability Map" prose if
    it still implies `omp.py` is a stub.

## Acceptance Criteria

- `OmpEmitter.emit_skill`/`emit_command` produce valid omp-format artefacts
  per FEAT-3103's documented discovery format
- `ll-adapt --host omp --apply` completes without `AdapterError` for any of
  the three artefact types (combined with FEAT-3104's `emit_agent`)
- `HOST_CAPABILITIES["omp"].commands` is `True` and `ll-verify-host-map`
  passes
- Tests mirror the existing codex adapter skill/command test coverage
- `docs/reference/HOST_COMPATIBILITY.md` and `docs/reference/API.md` no
  longer describe `omp` as an unimplemented stub

## Impact

- **Scope**: Medium — gated on FEAT-3103 landing first.


## Session Log
- `/ll:issue-size-review` - 2026-08-08T10:09:55 - `70da93c7-f4f5-4a9e-85c1-cf030ebd11cb.jsonl`
