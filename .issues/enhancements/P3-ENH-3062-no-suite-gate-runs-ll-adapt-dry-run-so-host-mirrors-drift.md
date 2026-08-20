---
id: ENH-3062
title: No suite gate runs ll-adapt --dry-run, so host mirrors drift undetected
type: ENH
priority: P3
status: open
testable: true
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T16:06:39Z'
relates_to:
- ENH-3046
- FEAT-2274
labels:
- testing
- host-adapters
- drift
supersedes:
- ENH-2968
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3062: No suite gate runs ll-adapt --dry-run, so host mirrors drift undetected

## Summary

`ll-adapt` already detects mirror drift — it content-compares generated output
against the on-disk mirror and rewrites only on mismatch — and it already has a
`--dry-run` mode. Nothing in the test suite invokes it, so drift is caught only
when a human happens to look.

ENH-2996 added a drift test, but hardcoded a single source/mirror pair rather
than using the adapter that already knows about all 107.

## Motivation

Drift exists right now, on two hosts:

```
$ ll-adapt --host gemini --dry-run
  DRY    confidence-check
  DRY    scope-epic
  DRY    ll-refine-issue
Done: 3 adapted, 104 skipped, 0 errors

$ ll-adapt --host kimi-code --dry-run
Done: 3 adapted, 104 skipped, 0 errors
```

`--host codex` is clean (0 adapted, 107 skipped).

This was found by hand, in the course of unrelated work, after a stale mirror
caused real rework: `commands/refine-issue.md` gained content during ENH-3046
while `.gemini/commands/refine-issue.toml` did not, and the staleness surfaced
only because someone grepped the mirror directly.

## Current Behavior

**The detection already works.** `adapters/gemini.py:94`:

```python
if out_path.exists() and out_path.read_text() == new_content:
    print(f"  SKIP   {skill_name}: already adapted")
    return "skipped"
```

"already adapted" is a content equality check, not an existence check, and the
same shape appears in `adapters/codex.py:262` and `:309`. Any mirror whose
content differs from freshly-generated output is reported as `DRY` under
`--dry-run` and rewritten under `--apply`.

**Nothing calls it.** `grep -rn "ll-adapt\|ll_adapt" scripts/tests/` finds only
the failure message inside ENH-2996's test, not an invocation.

**The existing test covers 2 of 107 artifacts.**
`scripts/tests/test_wiring_skills_and_commands.py:355-371` hardcodes:

```python
WIRE_ISSUE_SKILL_MIRRORS = [
    ".gemini/skills/wire-issue/SKILL.md",
    ".kimi-code/skills/wire-issue/SKILL.md",
]
```

Uncovered by any test: 28 `.gemini/commands/*.toml`, 17 of 18
`.gemini/skills/`, 9 `.gemini/agents/`, 45 of 46 `.kimi-code/skills/`, 9
`.kimi-code/agents/`, and the whole `.codex/` tree.

## Expected Behavior

The suite fails when any host mirror is stale, naming the drifted artifacts and
the regeneration command. Coverage tracks the adapter's own artifact list, so a
newly added command or skill is covered the moment it is adapted — no test-side
list to keep in sync.

## Proposed Solution

Replace the hardcoded pair with a parametrized test over hosts that runs the
adapter in dry-run mode and asserts nothing would be written.

Per the project's no-hosted-CI policy (`.claude/CLAUDE.md` § Testing & CI
Policy), this is an ordinary pytest test invoking the adapter directly — no
workflow file. `ll-adapt` is Python, so the adapter functions can be called
in-process rather than shelling out; if the CLI's counting logic is the clearer
contract, a subprocess asserting `Done: 0 adapted` is acceptable.

The failure message should carry the drifted artifact names and the exact fix,
matching ENH-2996's existing wording:

```
ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply
```

Decisions to make during implementation:

- Whether `disable-model-invocation: true` artifacts (skipped by the adapter)
  should be asserted absent from mirrors, or left unchecked as they are today.
- Whether to fix the three live drifts in the same change or a preceding one.
  They should land first, or the new gate fails on arrival.

Explicitly out of scope: changing what the adapters generate, adding new hosts,
and the `.gemini`/`.kimi-code`/`.codex` tree layouts.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- No existing test in the suite calls `main_adapt()` (the real `ll-adapt` CLI entry point, `cli/adapt.py:32`) directly; the closest precedent for exercising a `main_adapt_*`-style entry point in-process is `test_adapt_skills_for_codex.py:296-334`, which patches `sys.argv`/`_find_plugin_root` and asserts the int return code.
- Every existing adapter test reads the `(adapted, skipped, errors)` int tuple returned by `process_skills`/`process_commands`/`process_agents`/`process_mcp_config` (`core.py:414/471/544/622`), or the single `"adapted"`/`"skipped"`/`"error"` string from an emitter's own `emit_*` call — none parses `ll-adapt`'s printed `"Done: N adapted..."` stdout summary (`cli/adapt.py:148`).
- `CodexEmitter.emit_mcp_config` (`codex.py:427-478`) reads/writes the real `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`) rather than a project-relative path — a suite-wide dry-run gate that includes `process_mcp_config` for host `codex` needs `CODEX_HOME` redirected to a tmp dir, or it touches the operator's real global Codex config (read-only under dry-run, since `apply=False` skips the write at `:471`, but still a real filesystem read outside the repo).
- The `disable-model-invocation: true` skill filter (`core.py:438-443`, `_is_model_invocation_disabled()`) runs in `process_skills()` before `emitter.emit_skill` is ever called — such skills are counted `skipped` and no existing test asserts anything about their presence/absence in a mirror. This bears on this section's first open decision (whether disabled-invocation artifacts should be asserted absent from mirrors).
- Confirmed against current HEAD: `CodexEmitter.emit_command()` (`codex.py:333-377`) is fully presence-only as the Scope Addition describes (no `read_text()` at all; `.exists()` checks at `:359`, `:366`, `:368`). `CodexEmitter.emit_skill()` (`codex.py:294-331`) is only partially presence-only — the SKILL.md body already gets a real content diff via `_insert_skill_fields()` (`:308`, `skill_changed`), but the sibling `agents/openai.yaml` companion is checked with a bare `.exists()` (`:310`, `yaml_exists`) and is never rewritten once present, even under `--apply` (`:320`). `emit_agent()` (`:379-425`) and `emit_mcp_config()` (`:427-478`) already do full content comparisons.
- Established remediation-message convention across every existing adapter/mirror guard test: name the stale path, then append the literal fix command as `"...Run: <cmd>"` or `"...Regenerate with: <cmd>"`. Evidence: `test_wiring_skills_and_commands.py:415-419`, `test_adapters.py:1121-1123`, `test_adapt_agents_for_codex.py:350`, `test_adapt_skills_for_codex.py:403`.

## Scope Boundaries

**In scope**: a suite gate invoking the existing adapters in dry-run mode across
all configured hosts, replacing the ENH-2996 hardcoded pair.

**Out of scope**: adapter output format, host onboarding, and the unrelated
`commands/*.md` → `.gemini/commands/*.toml` count mismatch (29 sources vs 28
mirrors), which may be a legitimate `disable-model-invocation` exclusion and
should be confirmed rather than assumed to be a bug.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- `scripts/tests/test_adapters.py:1887-1896` defines `MIRROR_SKILL_EMITTERS: list[tuple[type, str]] = [(QwenEmitter, ".qwen"), (KimiEmitter, ".kimi-code"), (GeminiEmitter, ".gemini"), (OmpEmitter, ".omp")]`, parametrizing `TestMirrorEmitterSkillCompanions` (`:1899-1903`) — the closest existing precedent for a parametrized drift test, but it covers only 4 of the 6 `_EMITTER_MAP` hosts (omits `codex`, `claude-code`) and calls `emitter.emit_skill()` directly rather than driving `main_adapt()` end-to-end. `test_companion_drift_is_repaired` (`:1943-1955`) is the closest existing template for a "call unchanged → skipped, mutate companion → adapted" drift-regression sequence.
- `main_adapt()` (`cli/adapt.py:32`) returns exit-code only (`0`/`1`, `:149`) and never returns/exposes the `(adapted, skipped, errors)` tuples it computes as locals (`:105-146`) — only prints them (`"Done: N adapted, ..."`, `:148`). A test asserting "0 adapted" against `main_adapt()` itself must either call `process_skills`/`process_commands`/`process_agents`/`process_mcp_config` directly (matching the established convention every existing adapter test already follows — see Conventions in Force), or capture and parse stdout, which no existing test does.
- `test_adapt_golden_corpus.py:199-212` (`test_gemini_agent_excluded_from_byte_identity_claim`) is the established pattern for making a *scoping* decision test-visible: a dedicated test whose sole job is to assert a named exclusion's docstring exists, rather than silently omitting a host/path from coverage. Relevant if the new gate carries any host-specific exclusion (e.g. `claude-code` emitting no skill/command/agent artifacts).
- `SKILL_MIRRORS_MUST_MATCH_SOURCE` (`test_wiring_skills_and_commands.py:385-407`) and its test `test_skill_mirror_matches_source` (`:410-419`) — confirmed current failure message: `f"{mirror_rel} is stale relative to {source_rel}. Regenerate with: ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply"` (now three hosts, not two).

### Files to Modify
- `scripts/tests/test_wiring_skills_and_commands.py` — the `SKILL_MIRRORS_MUST_MATCH_SOURCE` hardcoded-pair test (`:385`, test function `test_skill_mirror_matches_source` `:411`) is the gate this issue replaces; renamed from `WIRE_ISSUE_SKILL_MIRRORS`/`test_wire_issue_skill_mirror_matches_source` since capture.
- `scripts/little_loops/adapters/codex.py` — `CodexEmitter.emit_command()` (`:333-377`) is fully presence-only (`.exists()` checks at `:359`, `:366`, `:368`, no `read_text()` anywhere); `emit_skill()` (`:294-331`) does a real content diff for the SKILL.md body (`_insert_skill_fields`, `:308`) but only a presence check for the sibling `agents/openai.yaml` companion (`yaml_exists = openai_yaml.exists()`, `:310`, never rewritten under `--apply` once present, `:320`). Per the merged Scope Addition, this is the defect to fix alongside the gate.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_adapters.py:25` and `scripts/tests/test_adapt_golden_corpus.py:32` import `adapters/gemini.py`.
- `scripts/little_loops/cli/adapt_skills_for_codex.py:20,23,26`, `scripts/tests/test_adapters.py:12`, `scripts/tests/test_adapt_golden_corpus.py:31` import `adapters/codex.py`.
- `scripts/little_loops/cli/adapt.py:32` (`main_adapt`) is the real `ll-adapt` CLI entry point (registered in `scripts/pyproject.toml`); it delegates to `adapters/core.py`'s `process_skills()` (`:414`), `process_commands()` (`:471`), `process_agents()` (`:544`), `process_mcp_config()` (`:622`), each returning a real `(adapted, skipped, errors)` int tuple. `main_adapt()` itself only returns an exit code and prints the summary to stdout — it does not return the counts.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/adapt_agents_for_codex.py:15,19` — imports `CodexEmitter` from `adapters/codex.py`, but only exercises the agents pathway; it does not call `emit_command`, so the content-comparison fix to `emit_command` does not affect it. Awareness only, no change needed. [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py:47` — re-exports `main_adapt` from `cli/adapt.py` for the `ll-adapt` console script; a pure re-export, no change needed. [Agent 1 finding]
- `scripts/little_loops/adapters/claude_code.py` — registered in `_EMITTER_MAP` (`adapters/core.py:58`) as host `claude-code`; the new gate parametrizes over every `_EMITTER_MAP` key including this one. `claude-code` emits no skill/command/agent mirror artifacts (`skill_output_format=None` etc., `capabilities.py:163-180`) — only `emit_mcp_config` does anything for this host. The new parametrized test must handle this host without spuriously asserting on skill/command/agent output it never produces. [Agent 1 finding, confirmed against `capabilities.py`]
- `scripts/little_loops/cli/help.py:17`, `scripts/little_loops/cli/verify_triggers.py:24`, `scripts/little_loops/cli/verify_host_map.py:39`, `scripts/little_loops/mcp_server/prompts.py:74` (deferred import) — import `_is_model_invocation_disabled` or `HOST_CAPABILITIES` from `adapters/core.py`/`adapters/capabilities.py`, unrelated symbols to those this issue changes (`process_commands`, `CodexEmitter.emit_command`). Awareness only, no change needed. [Agent 1 finding]

### Conventions in Force
- Every adapter test invokes adapter logic in-process — none shells out to the installed CLI. Assertions read the `(adapted, skipped, errors)` tuple from `process_*`, or the single `"adapted"`/`"skipped"`/`"error"` string from an emitter's own `emit_*` call — never `ll-adapt`'s printed stdout summary. Evidence: `test_adapters.py:216-220`, `:434-436`, `:1207-1249`.
- The canonical host registry for what `ll-adapt` writes is `_EMITTER_MAP` (`adapters/core.py:53-60`: codex, gemini, omp, kimi-code, claude-code, qwen), mirrored by `HOST_CAPABILITIES` (`adapters/capabilities.py:68-181`) and kept in sync by `test_verify_host_map.py:21` (`assert set(HOST_CAPABILITIES) == set(_EMITTER_MAP)`). This differs from the runtime `_HOST_RUNNER_REGISTRY` in `little_loops.host_runner`, which additionally has `opencode`/`pi`. Precedent for parametrizing a test directly off a registry rather than a hand-typed list: `scripts/tests/conformance/test_host_conformance.py:65`.
- `claude-code` is registered in `_EMITTER_MAP`/`HOST_CAPABILITIES` but emits no skill/command/agent mirror artifacts (`skill_output_format=None` etc., `capabilities.py:163-180`) — only `emit_mcp_config` does anything for that host. `omp` mirrors are not git-tracked in this repo (`test_adapters.py:1104-1111`, `test_wiring_skills_and_commands.py:428-432`).
- Real-repo-scan guard shape used elsewhere for "is the tracked mirror content current" (closest existing precedent to this gate): resolve repo root via `Path(__file__).parent.parent.parent`, glob real source/mirror dirs, and `return` (not `pytest.skip()`) early if the mirror dir doesn't exist yet. Evidence: `test_adapters.py:1104-1123`, `test_adapt_skills_for_codex.py:382-386`. The session-scoped `project_root` fixture (`conftest.py:229-232`) is the fixture form of the same path.
- Actionable-remediation message convention, consistent across every existing adapter/mirror guard: name the stale path, then append the literal fix command as `"...Run: <cmd>"` or `"...Regenerate with: <cmd>"`. Evidence: `test_wiring_skills_and_commands.py:415-419`, `test_adapters.py:1121-1123`, `test_adapt_agents_for_codex.py:350`, `test_adapt_skills_for_codex.py:403`.
- `CodexEmitter.emit_mcp_config()` (`codex.py:427-478`) reads/writes the real `~/.codex/config.toml` (or `$CODEX_HOME`), not a project-relative path — a suite-wide dry-run gate that includes `process_mcp_config` for host `codex` needs `CODEX_HOME` redirected to a tmp dir or it touches the operator's real global config.
- `process_skills()` filters `disable-model-invocation: true` skills out (`core.py:438-443`) before `emitter.emit_skill` is ever called; no existing test asserts anything about such a skill's presence/absence in a mirror.

### Tests
- `scripts/tests/test_wiring_skills_and_commands.py` — the gate being replaced.
- `scripts/tests/test_adapters.py`, `scripts/tests/test_adapt_golden_corpus.py` — established in-process adapter test patterns (see Conventions in Force).
- `scripts/tests/conformance/test_host_conformance.py:65` — precedent for `@pytest.mark.parametrize("host", list(<registry>.keys()))`.
- `scripts/pyproject.toml:271-274` registers only `integration`/`conformance` markers (both excluded from the default CI run); the current mirror-drift test carries no marker and runs in the default suite.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_host_map.py:19-21` — existing precedent asserting `set(HOST_CAPABILITIES) == set(_EMITTER_MAP)`; the closest non-parametrized analog to the new gate's registry iteration, no change needed but useful cross-reference. [Agent 3 finding]
- `scripts/tests/test_wiring_cli_registry.py` — asserts CLI registry wiring for `route_owner="ll-adapt"`; unaffected by this change but covers the same CLI surface, worth re-running as part of verification. [Agent 1 finding]
- `scripts/tests/test_doc_counts.py` — asserts doc-catalog entries reference `ll-adapt-skills-for-codex`, `ll-adapt-agents-for-codex`, `ll-adapt`, `adapters/`; unaffected, re-run as part of verification. [Agent 1 finding]
- **New test needed** — no existing test pins `CodexEmitter.emit_command`'s behavior across two calls with *different* content for the same command (the exact regression this issue's Scope Addition targets). `TestCodexEmitterEmitCommand.test_already_adapted_returns_skipped` (`test_adapters.py:498-501`) only reuses the same `meta` dict on both calls, so it stays green under both old presence-only and new content-based logic and does not itself catch the defect. Follow the idempotency-test pattern already used for the already-content-based `emit_agent`/`emit_mcp_config` (`test_up_to_date_returns_skipped`, `test_idempotent`, `test_adapters.py:~594/~599`): call with content A, mutate to content B, assert `"adapted"` on the second call; then call again unchanged and assert `"skipped"`. [Agent 3 finding]
- **New test needed** — no test covers the sibling `agents/openai.yaml` companion going stale after the source `SKILL.md`/command changes; `codex.py:~310/~320` currently marks it `skipped` via bare `.exists()` and never rewrites it even under `--apply`. Add a companion-content-drift test alongside the `emit_command` fix. [Agent 3 finding]
- `scripts/tests/test_adapters.py:658-677` (`TestCodexEmitterEmitMcpConfig._config_path`) — existing per-class `monkeypatch.setenv("CODEX_HOME", str(tmp_path))` helper is the only precedent for isolating `emit_mcp_config`'s real filesystem side effect; the new gate's `process_mcp_config` call for host `codex` should reuse this pattern rather than touching the operator's real `~/.codex/config.toml`. [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` § ll-adapt
- `docs/reference/HOST_COMPATIBILITY.md`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Handle host `claude-code` in the new parametrized test: it is in `_EMITTER_MAP` but emits no skill/command/agent artifacts (`skill_output_format=None`, `capabilities.py:163-180`) — only `emit_mcp_config` applies. Don't let the parametrization spuriously assert on outputs this host never produces.
- Add a new `emit_command` content-drift regression test in `test_adapters.py` (same-command, two different content payloads, second call must return `"adapted"` not `"skipped"`) — no existing test exercises this and it is the exact defect this issue's Scope Addition fixes.
- Add a new companion-drift test for the `agents/openai.yaml` sibling file (`codex.py:~310/~320`), which is currently never rewritten under `--apply` once present.
- Reuse the `monkeypatch.setenv("CODEX_HOME", str(tmp_path))` pattern from `TestCodexEmitterEmitMcpConfig._config_path` (`test_adapters.py:658-677`) when the new gate's dry-run pass reaches `process_mcp_config` for host `codex`, so it never touches the operator's real `~/.codex/config.toml`.
- No doc, hook, loop, skill, or command consumes `ll-adapt`'s exit code or `"Done: N adapted..."` stdout summary (confirmed via repo-wide grep across `loops/ hooks/ skills/ commands/`) — no gate-consumer updates required.

## Program Design

### Signatures

- `adapt_skill(skill_path: Path, apply: bool, quiet: bool) -> str` — existing, `adapters/gemini.py:88`; returns `"skipped"` on content match, the drift signal this gate consumes.
- `main() -> int` — existing `ll-adapt` entry point; already supports `--host`, `--dry-run`, `--only`, `--quiet`.
- `test_host_mirrors_are_not_stale(host: str) -> None` — new, parametrized over hosts, in `scripts/tests/test_wiring_skills_and_commands.py`.

### Call Path

`test_wire_issue_skill_mirror_matches_source` (`scripts/tests/test_wiring_skills_and_commands.py:362`) is the gate being replaced. The new test drives `main()` (`ll-adapt`) -> per-host adapter -> `GeminiEmitter.emit_skill` (`adapters/gemini.py:81`) / `emit_command` (`adapters/gemini.py:117`) / the codex equivalents (`CodexEmitter.emit_skill`/`emit_command`, `adapters/codex.py:~294`/`~333`), asserting the adapted count is zero. `_body_after_frontmatter` (`scripts/tests/test_wiring_skills_and_commands.py:345`) becomes unused if the hardcoded pair is fully removed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

The Signatures/Call Path above are stale as of current HEAD:

- The entry point is `main_adapt() -> int` (`scripts/little_loops/cli/adapt.py:32`), not a bare `main()`. It supports `--host`, `--apply`, `--dry-run`, `--only`, `--quiet`, but only returns an exit code (`0` if `total_errors == 0` else `1`, `:149`) and prints `"Done: N adapted, M skipped, K errors"` to stdout (`:148`) — it never returns the counts themselves.
- There is no `adapt_skill(skill_path, apply, quiet) -> str` function in `adapters/gemini.py`. The current shape is `GeminiEmitter.emit_skill(skill_meta: dict) -> str` (`gemini.py:81`) and `GeminiEmitter.emit_command(cmd_meta: dict) -> str` (`gemini.py:91`, not `:117`).
- `main_adapt()` delegates to `adapters/core.py`'s `process_skills()` (`:414`), `process_commands()` (`:471`), `process_agents()` (`:544`), `process_mcp_config()` (`:622`) — each returns a real `(adapted, skipped, errors)` int tuple, which is what every existing adapter test asserts on; no test parses `ll-adapt`'s stdout.
- The gate this issue targets is `test_skill_mirror_matches_source` guarding `SKILL_MIRRORS_MUST_MATCH_SOURCE` (`test_wiring_skills_and_commands.py:385`/`:411`), renamed from `WIRE_ISSUE_SKILL_MIRRORS`/`test_wire_issue_skill_mirror_matches_source` since this issue was captured.
- No existing test calls `main_adapt()` directly, in-process or via subprocess. The closest precedent for exercising an `main_adapt_*`-style entry point in-process is `main_adapt_skills_for_codex()`'s test, which patches `sys.argv` and `_find_plugin_root`, then asserts the int return code (`test_adapt_skills_for_codex.py:296-334`).
- Host registry to parametrize over: `_EMITTER_MAP` (`adapters/core.py:53-60`: codex, gemini, omp, kimi-code, claude-code, qwen), mirrored by `HOST_CAPABILITIES` (`adapters/capabilities.py:68-181`, equality-enforced by `test_verify_host_map.py:21`) — not the runtime `_HOST_RUNNER_REGISTRY`, which also carries opencode/pi.

## Impact

Silent divergence between what a Claude Code user sees and what a Gemini, Kimi,
or Codex user sees. The mirrors exist specifically so non-Claude hosts get the
same instructions; when they drift, those hosts run older behavior with no
signal to anyone.

The cost is concrete and already paid once: ENH-3046's refine-issue changes had
to be hand-applied to the mirror, and the hand-applied version is itself still
reported as drifted — meaning a manual patch is not a reliable substitute for the
generator.

Low-to-moderate priority because the blast radius is limited to non-Claude hosts,
but the fix is small and the detection machinery already exists unused.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § Testing & CI Policy | Requires the gate live in the local pytest suite, not a workflow |
| `docs/reference/HOST_COMPATIBILITY.md` | Which hosts have mirrors and why |
| `docs/reference/CLI.md` § ll-adapt | Adapter flags including `--dry-run` |

## Status

**Open**

---

## Scope Addition

**Source**: Merged from [ENH-2968] during `/ll:audit-issue-conflicts` conflict resolution.

ENH-2968 independently found the same gap (no test asserts committed `.gemini`/`.kimi-code`/`.codex` mirrors match `ll-adapt` output) and additionally documented a real defect: `CodexEmitter`'s presence-only `.exists()` checks (now around `codex.py:310`, `:359`, `:405`) are not content comparisons, unlike Gemini/Kimi's `out_path.exists() and out_path.read_text() == new_content` pattern. Fix these content-comparison checks as part of implementing this issue's gate, so a fully-drifted Codex tree can't report false success.

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: core gap still
real — no test invokes `ll-adapt --dry-run`; codex.py presence-only checks
confirmed near lines 258-260/307-309, closely matching prior citations.
However: (1) the hardcoded-pair test has grown from 2 to 6 entries and was
renamed to SKILL_MIRRORS_MUST_MATCH_SOURCE (from WIRE_ISSUE_SKILL_MIRRORS),
now around line 368, not 355-371; (2) this issue's `relates_to: ENH-2996` was
a BROKEN/MISLINKED reference — ENH-2996 actually resolves to an unrelated P4
issue about wire-issue phase numbering. Removed that `relates_to` entry from
the frontmatter.

- 2026-08-16: Core gap still real (no test invokes `ll-adapt --dry-run`); cited code has been refactored to class-based emitters — `adapt_skill(skill_path, apply, quiet)` no longer exists. Updated citations above to `GeminiEmitter.emit_skill`/`emit_command` (`gemini.py:81`/`:117`) and `CodexEmitter.emit_skill`/`emit_command` (`codex.py:~294`/`~333`); presence-only `.exists()` checks in codex.py now sit around lines 310, 359, 405. Verdict: OUTDATED.

## Session Log
- `/ll:decide-issue` - 2026-08-20T20:07:05 - `08fa6b88-dde0-44e4-a3cb-8db52896afdd.jsonl`
- `/ll:refine-issue` - 2026-08-20T20:06:13 - `08fa6b88-dde0-44e4-a3cb-8db52896afdd.jsonl`
- `/ll:wire-issue` - 2026-08-20T19:59:31 - `4e5d030c-0ea9-48f8-8474-d8ffcc0cfe9e.jsonl`
- `/ll:refine-issue` - 2026-08-20T19:45:13 - `ec728862-173d-4fdf-85c5-0f68ffbf8e20.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:23 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:10 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:28 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-06T05:57:00 - `b806aadf-1033-4656-b34d-bd948c43350c.jsonl`
- `/ll:capture-issue` - 2026-08-05T16:14:07 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- `/ll:capture-issue` - 2026-08-05 - Captured from the ENH-3046 run forensics
  session, after a stale mirror required hand-patching.
