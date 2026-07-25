---
id: FEAT-2787
title: Implement the `omp` host adapter — all `OmpEmitter` methods currently raise
type: feature
status: open
priority: P5
parent: EPIC-2258
depends_on: [FEAT-2260]
relates_to: [FEAT-2797]
labels: [host-compat, omp, adapters, skills, commands]
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
confidence_score: 56
outcome_confidence: 61
score_complexity: 16
score_test_coverage: 20
score_ambiguity: 5
score_change_surface: 20
size: Very Large
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

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/omp.py` — replace the three raising stubs
  with real `emit_skill`/`emit_command`/`emit_agent` implementations
- `scripts/little_loops/cli/adapt.py` — parameterize the `process_agents()`
  output-dir argument (currently hardcoded `plugin_root / ".codex" /
  "agents"`) so `--host omp` writes agent artefacts to omp's own directory

### Dependent Files (Callers/Importers)
- `scripts/little_loops/adapters/core.py:_EMITTER_MAP` — already registers
  `"omp": ("little_loops.adapters.omp", "OmpEmitter")` (FEAT-2260); no
  change needed, listed for context
- `scripts/little_loops/adapters/core.py:resolve_emitter()` — instantiates
  `OmpEmitter` via lazy import; no change needed

### Similar Patterns
- `scripts/little_loops/adapters/codex.py:CodexEmitter` (lines 255-395) —
  primary reference implementation to mirror
- `scripts/little_loops/adapters/gemini.py:GeminiEmitter` (lines 106-187) —
  secondary reference; shows the "real adapter, one artefact type
  deliberately unsupported" fallback shape

### Tests
- `scripts/tests/test_adapters.py` — has one stub-era test
  (`resolve_emitter("omp")` + `emit_skill({})` raises `AdapterError`) that
  will need updating; mirror `TestCodexEmitterEmitSkill`/`EmitCommand`/
  `EmitAgent` test-class structure and fixture builders for the new
  `OmpEmitter` coverage

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — the "Skill discovery" /
  "Slash-command discovery" rows have no `omp` column entry yet; update
  once the artefact format is implemented

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — four spots restate the current stub behavior
  and must be updated once `OmpEmitter` is implemented: the
  `little_loops.adapters` module-summary table row (~line 37, currently
  says only `CodexEmitter`/`GeminiEmitter` are fully implemented), the
  `## little_loops.adapters` section intro blockquote (~line 9009), the
  `AdapterError` docstring line referencing "stub emitter called before
  implementation is wired up" (~line 9043), and the `Built-in emitters`
  table's `OmpEmitter` row (~line 9055, documents the raise-on-call
  behavior and `_REMEDIATION` text verbatim)

## Acceptance Criteria

- `emit_skill`/`emit_command`/`emit_agent` produce valid omp-format artefacts
- `ll-adapt --host omp --apply` completes without `AdapterError`
- `ll-doctor` reports omp capability support accurately
- Tests mirror the existing codex adapter test coverage

## Proposed Solution

Model the implementation on `adapters/codex.py`: map skill/command/agent
metadata into omp's artefact format, register file layout in the adapt
apply path, and add fixture-based emit tests.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Blocking unknown — omp's artefact discovery format is undocumented.**
`thoughts/research/omp-headless-flags.md` and the `[^omp]` footnote in
`docs/reference/HOST_COMPATIBILITY.md` only cover omp's *CLI invocation*
flags (`--mode json`, `--tools <comma-list>`) via `OmpRunner` in
`host_runner.py` — a separate, already-complete concern. Nowhere in the
codebase or `thoughts/research/` is omp's native skill/command/agent
*discovery* file format (equivalent to Codex's `~/.codex/skills/<name>/SKILL.md`
+ `agents/openai.yaml` Skills API, or Gemini's `.gemini/skills/<name>/SKILL.md`
+ `.gemini/commands/*.toml`) recorded. This must be established (via
oh-my-pi's own docs/source at https://github.com/can1357/oh-my-pi) before
`emit_skill`/`emit_command`/`emit_agent` can be implemented — the AC "produce
valid omp-format artefacts" is not yet researchable from this repo alone.

**Registry/dispatch already wired — no `core.py` changes needed.**
`scripts/little_loops/adapters/core.py:_EMITTER_MAP` already registers
`"omp": ("little_loops.adapters.omp", "OmpEmitter")` (landed by FEAT-2260,
the generic host-parameterized adapter this issue's epic, EPIC-2258, defers
skill/command adaptation to per ARCHITECTURE-049). `resolve_emitter()` and
the `HostEmitter` `@runtime_checkable` Protocol require no changes; `omp.py`
already satisfies the protocol structurally.

**Reference implementation to mirror: `CodexEmitter`**
(`scripts/little_loops/adapters/codex.py:CodexEmitter`, lines 255-395).
Each `emit_*` method returns one of the literal strings `"adapted"` /
`"skipped"` / `"error"` (the contract `process_skills`/`process_commands`/
`process_agents` in `core.py` switch on) and honors `apply: bool` (dry-run
computes content without writing) and `quiet: bool` (print gating).
`GeminiEmitter` (`scripts/little_loops/adapters/gemini.py:GeminiEmitter`,
lines 106-187) shows the alternate precedent of a real adapter that still
raises `AdapterError` for one artefact type it deliberately doesn't support
(`emit_agent`) — a fallback shape if omp's artefact model turns out not to
map cleanly onto one of the three surfaces.

**Meta dict shapes each `emit_*` method receives** (built by the traversal
functions in `core.py`):
- `emit_skill`: `skill_name`, `skill_path` (`Path`), `content` (str), `fm`
  (parsed frontmatter dict), `apply`, `quiet`
- `emit_command`: `stem`, `cmd_path` (`Path`), `content`, `fm`, `output_dir`
  (`Path`), `apply`, `quiet`
- `emit_agent`: `agent_name`, `agent_path` (`Path`), `content`, `fm`,
  `output_dir` (`Path`), `apply`, `quiet`

`disable-model-invocation` frontmatter filtering already happens centrally
in `core.py` before the emitter is invoked — `omp.py` does not need to
reimplement it.

**CLI wiring gap for `emit_agent`.** `main_adapt()`
(`scripts/little_loops/cli/adapt.py`) calls `process_agents(emitter,
agents_dir, codex_dir, ...)` where `codex_dir = plugin_root / ".codex" /
"agents"` is **hardcoded literally**, regardless of `--host`. An
`OmpEmitter.emit_agent()` implementation would currently receive
`output_dir=".codex/agents"` even under `--host omp` unless this call site
is also parameterized per host (e.g. a small `_agents_output_dir(host,
plugin_root)` helper). This is in scope for this issue since AC 2 requires
`ll-adapt --host omp --apply` to complete correctly end-to-end.

**Existing stub-era test to update.** `scripts/tests/test_adapters.py`
(`TestResolveEmitter` or similar) currently has
`test_omp_returns_emitter_that_raises`, asserting `resolve_emitter("omp")`
raises `AdapterError` on `emit_skill({})`. This test's assertion is
inverted once `OmpEmitter` is implemented — mirror the
`TestCodexEmitterEmitSkill`/`EmitCommand`/`EmitAgent` class structure (with
a private `_meta(self, tmp_path, name, apply=True, **kwargs)` fixture
builder) and the standard per-method test set: `test_returns_adapted_on_first_run`,
`test_dry_run_does_not_write`, `test_already_adapted_returns_skipped`,
`test_idempotent`.

**Wiring pass findings (`/ll:wire-issue`):** Exact locations —
`TestCodexEmitterEmitSkill`/`EmitCommand`/`EmitAgent` live at
`scripts/tests/test_adapters.py:350-603`, with fixture builders `_make_skill`/
`_make_command`/`_make_agent` at lines 29-76.
`TestCodexEmitterEmitAgent` additionally has
`test_user_authored_file_not_overwritten` (lines 471-603) — write user
content to the output path first, assert the emitter returns `"skipped"`
and leaves it untouched; worth reusing for `OmpEmitter.emit_agent` given
any omp output format that risks clobbering hand-edited files.
No existing test exercises `main_adapt()`/`cli/adapt.py` directly (no
`test_adapt.py`, no `main_adapt` references under `scripts/tests/`) — once
the `codex_dir` hardcode at `cli/adapt.py:120-124` is parameterized per
host, there is no existing template to mirror for a `main_adapt(host="omp")`
output-dir test; closest pattern is `TestCodexEmitterEmitAgent._meta`'s
`output_dir` key (lines 483-489) plus the fixture-and-assert shape in
`scripts/tests/test_adapt_agents_for_codex.py:130-263` (a separate,
Codex-only CLI alias entry point — not itself in scope for omp awareness).
`ll-doctor`'s capability reporting (AC 3) needs **no code change**: its
tests (`scripts/tests/test_cli_doctor.py`) exercise `host_runner.OmpRunner`
via `resolve_host()`, a CLI-invocation-probing concern entirely separate
from `resolve_emitter()`/`OmpEmitter` — nothing in `doctor.py` special-cases
the emitter stub today, so AC 3 is satisfied automatically once
`OmpEmitter` stops raising.

## Impact

- **Scope**: Large

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-25_

**Readiness Score**: 56/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 61/100 → Below threshold (65)

### Concerns
- Requirements clarity for the actual artefact format is not yet
  established — the issue's own "Codebase Research Findings" section states
  the blocking unknown explicitly rather than papering over it.
- File-level plan (which two files to touch, how `CodexEmitter`/
  `GeminiEmitter` map onto the work) is solid; it's the omp-side contract
  that's missing.

### Gaps to Address
- omp's native skill/command/agent discovery file format has no precedent
  anywhere in this repo or `thoughts/research/` — only omp's CLI-invocation
  flags (`OmpRunner`) are documented. This must be resolved against
  oh-my-pi's own docs/source (https://github.com/can1357/oh-my-pi) before
  `emit_skill`/`emit_command`/`emit_agent` can be written; starting
  implementation now means guessing at the target format.
- `cli/adapt.py`'s hardcoded `.codex/agents` output-dir needs
  parameterizing per host — straightforward once the omp artefact layout is
  known, but currently unverified end-to-end for `--host omp --apply`.

### Outcome Risk Factors
- High ambiguity axis: no precedent exists for omp's artefact discovery
  format in this codebase — an unproven external API surface (oh-my-pi),
  not an internal mechanism, so the correct remedy is external-docs
  research rather than a code spike.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:confidence-check` - 2026-07-25T08:15:00 - `47fe161b-4234-42ac-a6c0-f8c1be3f6f0f.jsonl`
- `/ll:wire-issue` - 2026-07-25T08:00:50 - `b80aba0a-8c41-4406-bf61-9e60bb3dfe4a.jsonl`
- `/ll:refine-issue` - 2026-07-25T07:56:22 - `09a15f4f-e0dc-48eb-bfc2-cbe00a641199.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:57 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
