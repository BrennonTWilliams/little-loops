---
id: FEAT-2787
title: "Implement the `omp` host adapter \u2014 all `OmpEmitter` methods currently\
  \ raise"
type: feature
status: done
priority: P5
parent: EPIC-2258
depends_on:
- FEAT-2260
relates_to:
- FEAT-2797
labels:
- host-compat
- omp
- adapters
- skills
- commands
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
confidence_score: 75
outcome_confidence: 64
verify_verdict: VALID
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 0
score_change_surface: 25
size: Very Large
learning_tests_required:
- oh-my-pi
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
  > ⚠ Superseded — already parameterized via `config_dir`; see Codebase Research Findings

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/verify_host_map.py` — `_check_emitter_agreement()`
  (lines 163-168) hardcodes `if omp_entry is not None and (omp_entry.agents
  or omp_entry.commands): raise ...` — this check fails `ll-verify-host-map`
  the moment `HOST_CAPABILITIES["omp"]` declares real `agents`/`commands`
  support, which this issue's AC 3 requires. Must be updated in lockstep
  with the `capabilities.py` edit. The module docstring (lines 19-21) also
  asserts "`omp` must stay `False`/`False`" and needs the matching prose fix.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapt_golden_corpus.py:196-214` —
  `test_omp_and_gemini_agent_excluded_from_byte_identity_claim` directly
  asserts `OmpEmitter().emit_skill({})` raises `AdapterError`; will fail
  once implemented. The module docstring (lines 13-15) also documents omp
  as a "28-line stub" named exclusion from the byte-identity claim — both
  need updating together, not just the test body.
- `scripts/tests/test_adapters.py:940-943` — a class-level docstring (for
  the ENH-2874 degraded-agent test class) states "`omp` is explicitly
  excluded — its emitter is an all-stub"; update alongside the emitter
  implementation since this prose will become stale.
- `scripts/tests/test_adapters.py:1089-1309` — `TestKimiEmitterEmitSkill`/
  `EmitCommand`/`EmitAgent` + `TestResolveEmitterKimi` (`KimiEmitter`,
  `adapters/kimi.py:46-159`) is a second reusable test-class pattern beyond
  the Codex one already cited — the "native subagent, no degraded routing"
  shape, including `test_not_degraded_no_inline_preamble` and
  `test_process_agents_does_not_route_kimi_to_degraded`. Mirror this
  instead of (or alongside) the Codex pattern if `OmpEmitter.emit_agent`
  resolves the open agent-routing fork toward a genuine native format
  rather than `core._emit_degraded_agent` delegation.

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
- `docs/ARCHITECTURE.md` § "Host Adapter Capability Map" (~lines 1307-1326)
  — enumerates `omp.py` alongside `codex.py`/`gemini.py`/`kimi.py` as one of
  the per-host emitter modules `HOST_CAPABILITIES` replaces conditional
  code for; verify the surrounding prose stays accurate once `omp.py` holds
  a real implementation rather than a stub

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Correction — `cli/adapt.py` is already host-parameterized for agents.** `main_adapt()` (`cli/adapt.py:126-128`) reads `config_dir = (capability_entry.config_dir if capability_entry else None) or ".codex"` then `agent_output_dir = plugin_root / config_dir / "agents"`. It is not hardcoded to `.codex`; it falls back to `.codex` only when `HOST_CAPABILITIES[host]` is missing or its `config_dir` is `None` — which is exactly omp's current state (`capabilities.py:109`, `config_dir=None`). The real remaining gap is a one-line capability-map edit, not a `process_agents()`/`cli/adapt.py` code change. Skills and commands are not parameterized this way at all — `skills_dir`/`commands_dir` are fixed to the plugin's own source trees (`adapt.py:91-92`), and each concrete emitter derives its own output path internally.
- **New file to modify: `scripts/little_loops/adapters/capabilities.py`.** The `HOST_CAPABILITIES["omp"]` entry (lines 102-118) currently declares `config_dir=None`, all three `*_output_format=None`, `frontmatter_fields_read=()`, `agents=False`, `commands=False`, `hooks=False`, `subagents="none"`. These fields drive both the `cli/adapt.py` fallback above and the degraded-agent routing decision below, so implementing `OmpEmitter` requires updating this entry alongside `omp.py`.
- **New dependent test: `scripts/tests/test_verify_host_map.py`.** `TestHostCapabilities::test_keys_match_emitter_map` (lines 18-21) asserts `set(HOST_CAPABILITIES) == set(_EMITTER_MAP)`. `TestHostCapabilities::test_omp_fully_unimplemented` (lines 34-37) currently asserts `entry.agents is False` and `entry.commands is False` for omp — this assertion must change in lockstep with any `capabilities.py` edit or it will fail once `OmpEmitter` is real. `TestCheckDocParity::test_current_tree_has_no_mismatch` (line 47-48, backed by `ll-verify-host-map`) mechanically cross-checks the capability map against `docs/reference/HOST_COMPATIBILITY.md`'s "Adapter Host Capabilities" table (lines 229-234) — a table separate from the "Skill discovery"/"Slash-command discovery" rows already noted above, and it must also be updated.
- **Third precedent, not previously listed: `KimiEmitter`** (`scripts/little_loops/adapters/kimi.py:46-159`). It is a second "native subagent" precedent alongside `CodexEmitter` — `emit_agent` (lines 127-158) copies the source file through via `core._select_frontmatter_fields`, and its tests assert the *absence* of the degraded-mode marker (`test_adapters.py:1254-1260`, `test_not_degraded_no_inline_preamble`).
- **Correction — `GeminiEmitter` no longer raises for any artefact type.** Contrary to this issue's Proposed Solution framing, `GeminiEmitter.emit_agent` (`gemini.py:150-157`) now delegates to `core._emit_degraded_agent` instead of raising (landed by ENH-2874, see `capabilities.py:85-94`). The "real adapter, one artefact type deliberately unsupported via raise" shape no longer exists anywhere in `adapters/`; an `OmpEmitter` needing a similar fallback would either reintroduce that shape or follow the degraded-mode delegation pattern instead.
- **Open agent-routing fork.** `process_agents` (`core.py:409-484`) chooses degraded vs. native purely from the capability map: `degraded = entry.subagents == "none" and entry.agent_output_format is not None` (`core.py:438-441`). omp's current entry satisfies only the first condition, so `emitter.emit_agent` is always invoked directly today (never routed to `_emit_degraded_agent`). Whether `OmpEmitter.emit_agent` should implement a genuine native format or instead set `agent_output_format` to a real value and delegate to `core._emit_degraded_agent` (the Gemini pattern) is unresolved without omp's own subagent-invocation docs. `thoughts/research/omp-headless-flags.md:43` notes omp subagents "are spawned in-session by the model (task delegation), not selected at invocation" — suggestive of the degraded/no-native-format shape, but not conclusive; folds into the same blocking unknown already flagged above (omp's native artefact discovery format).
- **Shared `core.py` utilities available for reuse:** `core._extract_body` (`core.py:98-108`), `core._select_frontmatter_fields` (`core.py:114-177`, map-driven frontmatter inject/strip keyed off `HOST_CAPABILITIES[...].frontmatter_fields_read`), `core._emit_degraded_agent` (`core.py:220-271`). `core._read_frontmatter`/`core._is_model_invocation_disabled` run centrally in the traversal functions before an emitter is ever invoked — `OmpEmitter` does not need to call either directly. No shared TOML serializer exists; Codex/Gemini each build TOML content with local string formatting (`codex.py:185-225`, `gemini.py:44-59`).
- **Return contract, confirmed across all three current emitters:** each `emit_*` method returns the literal string `"adapted"` or `"skipped"`, or raises `AdapterError` for a per-item (not whole-run) failure — `process_skills`/`process_commands`/`process_agents` catch `AdapterError` per item and bump an `errors` counter (`core.py:321-325, 394-398, 472-476`) rather than aborting. `apply`/`quiet` are always read from the `meta` dict, never module-level state.
- **Test-file location correction.** All emitter tests live in the single `scripts/tests/test_adapters.py` (1309 lines) — there is no per-host `test_<host>_adapter.py` for emitter logic. (`test_codex_adapter.py`/`test_kimi_adapter.py` test an unrelated concept: hook Bash-shim adapters under `hooks/adapters/<host>/`.) The exact existing stub test to update is `TestResolveEmitter::test_omp_returns_emitter_that_raises` at `test_adapters.py:89-92`.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **New design fork — `process_commands`'s `output_dir` argument is unconditionally `skills_dir` for every host, not host-parameterized.** `cli/adapt.py:113-115` calls `process_commands(emitter, commands_dir, skills_dir, apply, args.quiet)` — the third positional arg flows into `cmd_meta["output_dir"]` (`core.py:389`) as the plugin's own `skills_dir`, regardless of `--host`. The two existing command emitters disagree on whether to honor it: `CodexEmitter.emit_command` (`codex.py:303`) uses it to bridge commands into `skills_dir / f"ll-{stem}"`; `GeminiEmitter.emit_command` (`gemini.py:127-129`) ignores the meta key entirely and self-derives `.gemini/commands/<stem>.toml` from `cmd_path.parent.parent`. `OmpEmitter.emit_command` must resolve this the same way — bridge into `skills_dir` (Codex shape) or self-derive an omp-native path (Gemini shape) — before it can be written.
- **`HOST_CAPABILITIES["omp"]` entry, field-by-field vs. a "real" adapter entry.** Comparing `capabilities.py`'s `"codex"` (lines 65-79) / `"kimi-code"` (lines 119-137) entries against omp's stub (lines 102-118): a real entry has a non-`None` `config_dir` string, non-`None` `*_output_format` prose strings describing the concrete artifact path (e.g. `agent_output_format="TOML (.codex/agents/<name>.toml)"`), a populated `frontmatter_fields_read` tuple, and `agents`/`commands`/`hooks` set `True` where the emitter actually produces that artifact. omp's stub has all of these at their zero-value (`None`/`()`/`False`). `test_verify_host_map.py::TestHostCapabilities::test_omp_fully_unimplemented` (lines 34-37) is the one test that encodes this stub-vs-real distinction as an assertion and will need updating alongside the entry.
- **Idempotency check is a shared shape across all three existing emitters**, confirmed at `kimi.py:71-74,111-114,144-147`, `gemini.py:134`, `codex.py:353-362`: compute the full target content, then `if out_path.exists() and out_path.read_text() == new_content: return "skipped"`. No frontmatter is patched in place — content is always recomputed whole. Codex's agent path additionally gates on a generated-marker prefix (`codex.py:353-358`) to distinguish user-authored files (skip, don't overwrite) from ll-generated ones (safe to overwrite); Kimi/Gemini use plain byte-equality only.
- **Confirmed: no `omp` special-casing exists in `cli/doctor.py` today** — a full-file grep for `\bomp\b` returns zero matches, corroborating this issue's existing claim that AC 3 (`ll-doctor` capability reporting) needs no code change. The actual capability-parity tests live entirely in `test_verify_host_map.py` (`TestHostCapabilities`, `TestCheckDocParity`, `TestCheckEmitterAgreement`, `TestRun`/`TestMainVerifyHostMap`) — a separate CLI/test surface from `doctor.py`.

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

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Codebase convention for an undocumented external format: a dedicated research-spike issue precedes the emitter issue, every prior time this has happened.** `EPIC-2910`/`FEAT-2911` (kimi CLI surface spike, cited by `adapters/kimi.py:3-4`), `EPIC-2178`/`FEAT-2179` (gemini CLI research spike), and `EPIC-1463`/`FEAT-1483` (codex slash-command/skill discovery spike) each split "figure out the external tool's file format" into its own issue that landed `done` before the corresponding `*Emitter` implementation issue started; `EPIC-2910`'s summary states this explicitly ("The research spike (FEAT-2911) is already complete, so implementation children can start immediately"). omp's existing spike artifact, `thoughts/research/omp-headless-flags.md` (from `FEAT-1850`), explicitly excludes "Conformance + skill/command adaptation" from its scope (lines 93-98) — it only ever covered CLI invocation flags, matching the shape of a not-yet-closed discovery gap rather than an oversight.
- **Partial resolution for the agent-artefact case: `FEAT-2797` (already `relates_to` this issue) already documents oh-my-pi's real agent-discovery contract.** Its "Audit findings (2026-07-25)" section cites `docs/task-agent-discovery.md:37` (per-agent `output:` frontmatter schema) and `:60` (`TASK_AGENT_CONFIG_SOURCE = ".omp"`, which explicitly excludes `.claude/agents`/`.codex/agents`/`.gemini/agents` from omp's own discovery), and its own Acceptance Criteria state that this issue's `emit_agent` must write to `.omp/agents/` (not a reused `.claude/agents` path) and populate a frontmatter `output:` key. This narrows this issue's "blocking unknown" to skills and commands specifically — the agent-artefact format is no longer undocumented, only unimplemented against a known contract.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
N/A — no new data shapes. `emit_skill`/`emit_command`/`emit_agent` continue to accept the existing `meta: dict` shapes already used by `CodexEmitter`/`GeminiEmitter`/`KimiEmitter` (see Integration Map for the exact key sets per method).

### Signatures
- `OmpEmitter.emit_skill(self, skill_meta: dict) -> str` — existing signature (`adapters/omp.py`), body currently only raises
- `OmpEmitter.emit_command(self, cmd_meta: dict) -> str` — existing signature
- `OmpEmitter.emit_agent(self, agent_meta: dict) -> str` — existing signature
- Each must return the literal string `"adapted"` or `"skipped"`, or raise `AdapterError` for a per-item (not whole-run) failure — the contract enforced by `core.py`'s `process_skills`/`process_commands`/`process_agents` (`core.py:321-325, 394-398, 472-476`), which catch `AdapterError` per item and count it toward an `errors` tally rather than aborting the run

### Call Path
`main_adapt()` (`cli/adapt.py:31-137`) → `resolve_emitter("omp")` (`core.py:59-76`) → `process_skills` / `process_commands` / `process_agents` (`core.py:279-484`) → `OmpEmitter.emit_skill` / `emit_command` / `emit_agent` → (implementation-dependent) `core._select_frontmatter_fields` (`core.py:114-177`) and/or `core._emit_degraded_agent` (`core.py:220-271`) if the open agent-routing fork (see Integration Map) resolves toward the degraded-mode pattern

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold. This issue implements existing interface contracts (`emit_skill`/`emit_command`/`emit_agent`, the `"adapted"`/`"skipped"`/`AdapterError` return contract) rather than introducing new classification logic. The still-open agent-routing fork (native `emit_agent` vs. capability-map-driven delegation to `core._emit_degraded_agent`) is an implementation-approach choice contingent on external omp documentation, not a new decision rule within this codebase — see Integration Map → Codebase Research Findings.

## Impact

- **Scope**: Large

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-08_

**Readiness Score**: 75/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 64/100 → Below threshold (65)

### Concerns
- omp's native artefact discovery format (skill/command layout) is still
  undocumented anywhere in this repo — it must be sourced from oh-my-pi's
  own docs/source (https://github.com/can1357/oh-my-pi) before
  `emit_skill`/`emit_command` can be written correctly. The agent-artefact
  case is now partially resolved via `FEAT-2797`'s documented `.omp/agents/`
  + `output:` frontmatter contract, but skills/commands remain the open
  blocker.
- The open agent-routing fork (native `emit_agent` vs. capability-map-driven
  delegation to `core._emit_degraded_agent`, the Gemini pattern) is
  unresolved and depends on the same external unknown.
- `ll-issues format-check` flags `missing_behavior_parity` (`omp.py`) and a
  `stale_symbol_ref` ("omp" claimed against `codex.py`) — advisory gaps that
  cap Criterion 4 (Issue Well-Specified) at 10/20 regardless of the
  otherwise-thorough spec.
- `learning_tests_required: [oh-my-pi]` resolves to a `proven` record with
  2 failing assertions (`omp --version`, `omp -p "<prompt>"` both fail in
  this environment) — a −5 modifier applied to Criterion 1 (No Duplicate
  Implementations) per the `proven`-with-failing-claims rule (BUG-3072).

### Outcome Risk Factors
- Ambiguity axis scored 0/25: the blocking external format unknown plus the
  unresolved agent-routing fork mean the actual implementation shape isn't
  settled yet — expect rework once oh-my-pi's real artefact format is
  confirmed.
- `learning_tests_required: [oh-my-pi]` resolves to a `proven` record, but
  its assertions only cover CLI invocation (binary presence, `--version`,
  `-p`, `--mode json`) — none touch the actual blocking unknown (skill/
  command/agent file layout), and 2 of those CLI-invocation assertions
  themselves currently fail. The `proven` status does not retire the real
  risk here.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-08
- **Reason**: Issue too large for single session (size score 11/11, Very
  Large) with a genuine blocking unknown (omp's skill/command discovery
  format) that gates only part of the work — the agent-artefact path is
  independently unblocked via FEAT-2797's documented contract, so a single
  monolithic issue would force unrelated, unblocked work to wait on
  external research.

### Decomposed Into
- FEAT-3103: Research spike: oh-my-pi (omp) native skill/command discovery
  format
- FEAT-3104: Implement `OmpEmitter.emit_agent` against the FEAT-2797
  `.omp/agents/` contract
- FEAT-3105: Implement `OmpEmitter.emit_skill`/`emit_command` against the
  FEAT-3103 discovery format (depends on FEAT-3103)

## Status

`done` — decomposed by `/ll:issue-size-review`.

## Related Key Documentation

- `.claude/CLAUDE.md` — `ll-adapt`/`ll-adapt-agents-for-codex` are documented in the CLAUDE.md CLI catalog; this issue implements the omp counterpart of that same emitter path.
- `docs/reference/API.md` — implements the `adapters` module's `OmpEmitter`, documented alongside `CodexEmitter`/`GeminiEmitter` in the module-summary and `Built-in emitters` table this issue must also update.
- `/ll:confidence-check` - 2026-07-25T08:15:00 - `47fe161b-4234-42ac-a6c0-f8c1be3f6f0f.jsonl`
- `/ll:wire-issue` - 2026-07-25T08:00:50 - `b80aba0a-8c41-4406-bf61-9e60bb3dfe4a.jsonl`
- `/ll:refine-issue` - 2026-07-25T07:56:22 - `09a15f4f-e0dc-48eb-bfc2-cbe00a641199.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:57 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`


## Session Log
- `/ll:issue-size-review` - 2026-08-08T10:10:02 - `70da93c7-f4f5-4a9e-85c1-cf030ebd11cb.jsonl`
- `/ll:confidence-check` - 2026-08-08T10:06:53 - `772caaf9-fa13-4083-91b0-4c107a089b71.jsonl`
- `/ll:verify-issues` - 2026-08-08T10:03:55 - `a9d6b1e5-e446-4914-901b-a072284e7ff3.jsonl`
- `/ll:refine-issue` - 2026-08-08T10:01:46 - `1fb1c730-9da2-4c3c-8c01-07a8e333f3d5.jsonl`
- `/ll:confidence-check` - 2026-08-08T09:56:02 - `2791bc87-e745-44eb-b09e-983d3a86346d.jsonl`
- `/ll:verify-issues` - 2026-08-08T09:52:32 - `3c07cf86-c768-4452-b1c2-41c99b9e1674.jsonl`
- `/ll:wire-issue` - 2026-08-08T09:50:44 - `c78f2d65-df71-4341-991b-e3469b44d452.jsonl`
- `/ll:refine-issue` - 2026-08-08T09:42:21 - `c2c99ce1-d489-4a0e-a785-45c22a6b5c0e.jsonl`
