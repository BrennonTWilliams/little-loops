---
id: FEAT-3105
title: Implement `OmpEmitter.emit_skill`/`emit_command` against the FEAT-3103 discovery
  format
type: feature
status: done
priority: P5
completed_at: '2026-08-08'
parent: FEAT-2787
depends_on:
- FEAT-2260
- FEAT-3103
labels:
- host-compat
- omp
- adapters
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-3105: Implement `OmpEmitter.emit_skill`/`emit_command` against the FEAT-3103 discovery format

## Summary

Implement `OmpEmitter.emit_skill` and `OmpEmitter.emit_command` in
`scripts/little_loops/adapters/omp.py`, replacing their raising stubs,
against omp's native skill/command discovery format. FEAT-3103's research
spike has landed (2026-08-08) and documented that format in
`thoughts/research/omp-skill-command-surface.md` — the dependency is
satisfied and implementation may proceed.

## Current Behavior

`OmpEmitter.emit_skill` and `OmpEmitter.emit_command`
(`scripts/little_loops/adapters/omp.py:39,42`) are unconditional
`raise AdapterError(_REMEDIATION)` stubs. `ll-adapt --host omp --apply`
fails for skill and command artefacts (only `emit_agent` works, per
FEAT-3104). `HOST_CAPABILITIES["omp"].commands` is `False` and
`skill_output_format`/`command_output_format` are `None`.

## Expected Behavior

`OmpEmitter.emit_skill`/`emit_command` write real `.omp/skills/`/
`.omp/commands/` artefacts per the format FEAT-3103 documented in
`thoughts/research/omp-skill-command-surface.md`, following the same
idempotency contract as `emit_agent` (`"skipped"` on byte-match, else
write and return `"adapted"`). `HOST_CAPABILITIES["omp"].commands` is
`True` and `ll-adapt --host omp --apply` completes without `AdapterError`
for all three artefact types.

## Use Case

An `ll` project author running `ll-adapt --host omp --apply` expects
skills and slash commands (not just agents) to become discoverable by
oh-my-pi, matching the parity already delivered for `codex`/`gemini`.

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
   > ⚠ Superseded — actual test is `test_omp_agents_true_matches_native_emission` (lines 34-42); assertion is at line 42
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Delete/replace `test_emit_skill_still_raises` and `test_emit_command_still_raises` (`scripts/tests/test_adapters.py:1363-1370`, inside `TestOmpEmitterEmitAgent`) — both assert `pytest.raises(AdapterError)` for the now-real methods.
- Add `TestOmpEmitterEmitSkill`/`TestOmpEmitterEmitCommand` to `scripts/tests/test_adapters.py`, mirroring `TestKimiEmitterEmitSkill`/`TestKimiEmitterEmitCommand` (nearest structural analog per matching `frontmatter_fields_read`) — see Integration Map § Tests for exact method names.
- Update the stale `_comment` field in `scripts/tests/fixtures/adapt/agent_cases.json:2` ("emit_skill/emit_command still raise, nothing to snapshot there").

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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/adapters/omp.py` — `OmpEmitter.emit_skill` (line 39) and `emit_command` (line 42) are currently unconditional `raise AdapterError(_REMEDIATION)` bodies; `emit_agent` (line 45) is the working idempotency-shape precedent already on this class (byte-identity check → `"skipped"`, else write guarded by `apply` → `"adapted"`). Module docstring (lines 1-15) and the stale `_REMEDIATION` string (line 26, "omp emitter not yet implemented") both still describe the pre-FEAT-3104 state and need updating alongside the new methods.
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES["omp"]` (lines 102-119): `skill_output_format=None`, `command_output_format=None`, `commands=False`, `frontmatter_fields_read=("description", "name")`. The comment block at lines 104-109 explicitly states these await FEAT-3103/FEAT-3105.
- `scripts/little_loops/cli/verify_host_map.py` — `_check_emitter_agreement()` (lines 126-177) currently only checks `agents`/`subagents`/`agent_output_format` self-consistency for `gemini_entry` and `omp_entry` (added for `omp` under FEAT-3104). There is no analogous check for `commands`/`skill_output_format`/`command_output_format`; module docstring (lines 19-21) says `"commands" stays False until FEAT-3105`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/adapt.py:112-115` — `process_commands(emitter, commands_dir, skills_dir, apply, args.quiet)` passes `skills_dir` positionally as `output_dir` for every host unconditionally; there is no host branch in `adapt.py` itself. `scripts/little_loops/adapters/core.py:process_commands` (~line 336) places this into `cmd_meta["output_dir"]` (~line 389) before calling `emitter.emit_command(...)`. The Codex/Gemini fork is enacted entirely inside each emitter, not at this call site: `CodexEmitter.emit_command` (`codex.py:281`) reads and uses `cmd_meta["output_dir"]` (used at `codex.py:303`); `GeminiEmitter.emit_command` (`gemini.py:110`) never reads `cmd_meta["output_dir"]` and instead self-derives `plugin_root = cmd_path.parent.parent` then `.gemini/commands/<stem>.toml` (`gemini.py:128-129`). Since `.omp/commands/<stem>.md` is flat and unrelated to the plugin's `skills/` tree per the research doc, `OmpEmitter.emit_command` needs the Gemini shape (self-derive from `cmd_meta["cmd_path"]`, ignore the `output_dir` argument) — no change to `adapt.py` or `process_commands`'s signature is required.
- `scripts/tests/test_adapters.py` — `TestResolveEmitter::test_omp_returns_emitter_that_raises` (~lines 90-93) asserts both methods raise today. Reference patterns to mirror: `TestCodexEmitterEmitSkill`/`EmitCommand` (~lines 352-410, ~416+), `TestGeminiEmitterEmitSkill`/`EmitCommand` (~lines 635-705, ~730-805), `TestKimiEmitterEmitCommand` (~lines 1195-1230), `TestOmpEmitterEmitAgent::test_emit_command_still_raises` (~line 1370, in the existing `TestOmpEmitterEmitAgent` class starting ~line 1317).
- `scripts/tests/test_adapt_golden_corpus.py` — `test_omp_and_gemini_agent_excluded_from_byte_identity_claim` (~line 215) asserts `OmpEmitter().emit_skill({})` raises; module docstring (lines 13-15) still names the "28-line stub" exclusion. `test_codex_skill_emission_matches_golden_corpus` (~line 54) and `test_gemini_skill_emission_matches_golden_corpus` (~line 82) are the byte-identity-claim patterns to potentially extend to `omp`.
- `scripts/tests/test_verify_host_map.py::TestHostCapabilities::test_omp_fully_unimplemented` (lines 34-37) asserts `entry.commands is False`.

### Conventions in Force
- Two established emitter shapes for `emit_command`'s `output_dir` handling, both already exercised by sibling emitters: the Codex shape reads and uses the caller-supplied `output_dir` to bridge into the plugin's `skills/` tree (`codex.py:281-303`); the Gemini shape ignores it and self-derives a native path from `cmd_meta["cmd_path"]`'s own directory ancestry (`gemini.py:110-129`). Evidence the fork is per-emitter, not per-callsite: `adapt.py`'s single unconditional call (lines 112-115) feeds the same `output_dir` value to both.
- The idempotency shape shared by every real emitter (`omp.py:emit_agent` lines 61-64, `gemini.py:emit_skill` lines 93-97, `gemini.py:emit_command` ~line 134): compute full target content first, skip via a byte-identity `out_path.exists() and out_path.read_text() == new_content` check, else write (guarded by `apply`) and print `APPLY`/`DRY`, returning `"skipped"`/`"adapted"`. `CodexEmitter.emit_skill`/`emit_command` diverge with compound/existence-only idempotency checks (sidecar file plus main file), evidence this is a convention with a documented exception, not an absolute rule.
- `HOST_CAPABILITIES["omp"]` internal-consistency checks live in `_check_emitter_agreement()` (`verify_host_map.py:126-177`) as per-field boolean assertions on the dataclass itself, not emitter-vs-map comparisons (per the function's own docstring, ENH-2883). The existing `agents`/`subagents`/`agent_output_format` triad check for `omp_entry` (lines 163-175) is the direct precedent for what a `commands`/`command_output_format` (and likely `skill_output_format`) triad check would look like.

### Tests
- `scripts/tests/test_adapters.py` — no `TestOmpEmitterEmitSkill`/`TestOmpEmitterEmitCommand` classes exist yet; `TestOmpEmitterEmitAgent` (~line 1317) is the sibling class in the same file to place them near.
- `scripts/tests/test_verify_host_map.py::TestHostCapabilities::test_omp_fully_unimplemented` (lines 34-37) — name and assertion both describe pre-FEAT-3105 state once `commands=True` lands.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapters.py:1358-1366` (inside `TestOmpEmitterEmitAgent`) — delete/replace `test_emit_skill_still_raises` and `test_emit_command_still_raises`, both of which assert `pytest.raises(AdapterError)` for the now-real methods. [Agent 3 finding]
- `scripts/tests/test_adapters.py` — new `TestOmpEmitterEmitSkill`/`TestOmpEmitterEmitCommand` classes should mirror `TestKimiEmitterEmitSkill` (`_meta` lines 1095-1120, `_out_path` 1122-1123 — closest structural analog since omp's `frontmatter_fields_read=("description", "name")` matches Kimi's, not Codex's) and `TestKimiEmitterEmitCommand` (`_meta` 1169-1191, `_out_path` 1193-1194). Reuse fixture helpers `_make_skill`/`_make_skill_with_short_desc` (lines 31-44, 612-632) and `_make_command` (47-59). Target test method names to reproduce: `test_returns_adapted_on_first_run`, `test_already_adapted_returns_skipped`, `test_dry_run_does_not_write`, `test_dry_run_returns_adapted`, `test_idempotent_no_double_name_insert`/`test_idempotent_no_double_insert`, `test_injects_name_when_absent`, `test_does_not_duplicate_name_when_present`, `test_no_description_returns_skipped`/`test_skips_when_no_body`. Only include `test_strips_metadata_short_description` if FEAT-3103's discovery-format doc confirms omp strips a `metadata.short-description` block. [Agent 3 finding]
- `scripts/tests/fixtures/adapt/agent_cases.json:2` — the `_comment` field states "emit_skill/emit_command still raise, nothing to snapshot there"; this goes stale once they're real and needs updating alongside `test_adapt_golden_corpus.py`'s own docstring. [Agent 2 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — "Skill discovery"/"Slash-command discovery" rows and the "Adapter Host Capabilities" table's skill/command columns for `omp`.
- `docs/reference/API.md` — module-summary table, `## little_loops.adapters` section intro, `AdapterError` docstring, and the "Built-in emitters" table row for `omp` all still describe it as an unimplemented stub.
- `docs/ARCHITECTURE.md` — "Host Adapter Capability Map" section, if it still implies `omp.py` is a stub.

### Configuration
- `scripts/little_loops/adapters/capabilities.py:102-119` is the sole configuration surface for this change (no separate config file).

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types

- `skill_meta: dict` (input to `emit_skill`) — established shape per `GeminiEmitter.emit_skill` (`gemini.py:80-107`): `skill_name: str`, `skill_path: Path`, `content: str`, `apply: bool`, `quiet: bool`.
- `cmd_meta: dict` (input to `emit_command`) — established shape per `GeminiEmitter.emit_command` (`gemini.py:110-140`): `stem: str`, `cmd_path: Path`, `content: str`, `fm: dict`, `apply: bool`, `quiet: bool` (plus an `output_dir: Path` key set by `adapt.py:112-115` that the Gemini-shape emitter ignores — see Call Path).

### Signatures

- `OmpEmitter.emit_skill(self, skill_meta: dict) -> str` — existing signature (`omp.py:39`), body currently `raise AdapterError(_REMEDIATION)` (line 40); must return `"adapted"` or `"skipped"` per the shared idempotency shape (see `emit_agent`, `omp.py:45-75`).
- `OmpEmitter.emit_command(self, cmd_meta: dict) -> str` — existing signature (`omp.py:42`), body currently `raise AdapterError(_REMEDIATION)` (line 43); same return contract.
- `_fields_read() -> tuple[str, ...]` (`omp.py:29-31`) — already returns `HOST_CAPABILITIES["omp"].frontmatter_fields_read`; reusable as-is for skill/command frontmatter selection once `HOST_CAPABILITIES["omp"].frontmatter_fields_read` is updated per FEAT-3103's findings.
- `HostCapabilityEntry` fields to update (`capabilities.py:55-61` for the dataclass shape, `102-119` for the `omp` entry): `skill_output_format: str | None`, `command_output_format: str | None`, `commands: bool`.

### Call Path

`process_skills` (`core.py`) -> `OmpEmitter.emit_skill(skill_meta)` -> writes `<plugin_root>/.omp/skills/<skill.name>/SKILL.md`.

This targets the format documented in FEAT-3103's research doc § "Summary for `OmpEmitter.emit_skill`/`emit_command`": one directory per skill, non-recursive, frontmatter `description` required or the file is silently skipped by omp's own loader, `name` falls back to the directory basename when absent.

`adapt.py:112-115` `process_commands(emitter, commands_dir, skills_dir, apply, quiet)` -> `core.py:process_commands` builds `cmd_meta` with `output_dir=skills_dir` (unconditionally, same value passed to every host) -> `OmpEmitter.emit_command(cmd_meta)` must ignore `cmd_meta["output_dir"]` (the Gemini shape, `gemini.py:110-129`, not the Codex shape which reads it at `codex.py:303`) and self-derive `<plugin_root>/.omp/commands/<stem>.md` from `cmd_meta["cmd_path"]`'s own ancestry — flat, no subdirs, per the research doc's "Commands" findings. `description` frontmatter is optional (omp falls back to a truncated first body line if absent) but should be set explicitly to avoid the lossy fallback.

### Decision Rules

N/A — no new decision logic. This issue implements two emitter methods against an already-documented external format (FEAT-3103); it introduces no new gap kind, gate, keyword list, or threshold.

## Impact

- **Scope**: Medium — FEAT-3103 has landed, so this is unblocked.

## Status

done

## Session Log
- `/ll:ready-issue` - 2026-08-08T11:51:43 - `316bbd1a-af3a-4bea-beb9-cf2f78cbe319.jsonl`
- `/ll:confidence-check` - 2026-08-08T11:48:09 - `1a45c831-76d5-49ff-8069-81689c208bb5.jsonl`
- `/ll:verify-issues` - 2026-08-08T11:46:14 - `f0657184-449c-4b4d-8104-4f32c8975eba.jsonl`
- `/ll:wire-issue` - 2026-08-08T11:44:28 - `d35cce01-243c-43c4-a79b-85bac6e66c4f.jsonl`
- `/ll:refine-issue` - 2026-08-08T11:30:02 - `3718927d-3639-41db-9ebc-0e2d65fe3e32.jsonl`
- `/ll:issue-size-review` - 2026-08-08T10:09:55 - `70da93c7-f4f5-4a9e-85c1-cf030ebd11cb.jsonl`
