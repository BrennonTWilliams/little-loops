---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
---

# FEAT-2787: Implement the `omp` host adapter (all `OmpEmitter` methods currently raise)

## Summary

`OmpEmitter` is registered in the adapter dispatch so `--host omp` resolves
to a real class instead of a `KeyError`, but all three emitter methods
(`emit_skill`, `emit_command`, `emit_agent`) unconditionally raise
`AdapterError`. Full `omp` host support (mirroring `adapters/codex.py` for
Codex) does not exist.

## Location

- **File**: `scripts/little_loops/adapters/omp.py`
- **Line(s)**: 1-29 (entire file, at scan commit: fb567390)
- **Anchor**: `class OmpEmitter`, constant `_REMEDIATION`
- **Code**:
```python
_REMEDIATION = "omp emitter not yet implemented — open a PR adding adapters/omp.py"

class OmpEmitter:
    """Stub emitter for the omp surface.  All methods raise :class:`AdapterError`."""
    name = "omp"

    def emit_skill(self, skill_meta: dict) -> str:
        raise AdapterError(_REMEDIATION)
    def emit_command(self, cmd_meta: dict) -> str:
        raise AdapterError(_REMEDIATION)
    def emit_agent(self, agent_meta: dict) -> str:
        raise AdapterError(_REMEDIATION)
```

## Current Behavior

`ll-adapt --host omp` fails at the first emit with the remediation message.

## Expected Behavior

`ll-adapt --host omp --apply` regenerates skills, commands, and agent
artefacts in the omp host's native format, as `ll-adapt --host codex` does
for Codex.

## Use Case

Users on the omp host get the same generated-artefact parity Codex users
have, instead of a dead-end error.

## Acceptance Criteria

- `emit_skill`/`emit_command`/`emit_agent` produce valid omp-format artefacts
- `ll-adapt --host omp --apply` completes without `AdapterError`
- `ll-doctor` reports omp capability support accurately
- Tests mirror the existing codex adapter test coverage

## Proposed Solution

Model the implementation on `adapters/codex.py`: map skill/command/agent
metadata into omp's artefact format, register file layout in the adapt
apply path, and add fixture-based emit tests.

## Impact

- **Scope**: Large

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:57 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
