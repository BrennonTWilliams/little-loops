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
blocked_by:
- ENH-3265
depends_on:
- ENH-3265
labels:
- testing
- host-adapters
- drift
supersedes:
- ENH-2968
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3062: No suite gate runs ll-adapt --dry-run, so host mirrors drift undetected

## Summary

`ll-adapt` mostly detects mirror drift — it content-compares generated output
against the on-disk mirror and rewrites only on mismatch — and it already has a
`--dry-run` mode. Nothing in the test suite invokes it, so drift is caught only
when a human happens to look.

Two qualifications, both established by the 2026-08-20 review:

- **The detection is not universal.** `CodexEmitter.emit_command` and
  `emit_skill`'s `openai.yaml` companion use presence-only `.exists()` checks,
  so for host `codex` a fully drifted tree reports clean. 11 files are drifted
  right now under a green `0 adapted`.
- **A uniform "nothing would be written" assertion is not the right gate.**
  Three of six hosts legitimately report `adapted > 0` in this repo. See the
  Host / Artifact Coverage Matrix.

An existing drift test hardcodes a handful of source/mirror pairs
(`SKILL_MIRRORS_MUST_MATCH_SOURCE`) rather than using the adapter that already
knows about all 108 artifacts. That hand-maintained list is what this issue
replaces.

## Motivation

**Superseded evidence (2026-08-05).** At capture time, `--host gemini` and
`--host kimi-code` each reported `3 adapted` (`confidence-check`, `scope-epic`,
`ll-refine-issue`), found by hand after a stale mirror caused real rework:
`commands/refine-issue.md` gained content during ENH-3046 while
`.gemini/commands/refine-issue.toml` did not. Those three drifts have since been
repaired. The gap this issue exists to close — that nothing *automatically*
notices — is unchanged.

**Current baseline (2026-08-20), measured directly:**

| Host | `ll-adapt --host <h> --dry-run` | Reading |
|---|---|---|
| `gemini` | `0 adapted, 108 skipped` | Genuinely clean |
| `kimi-code` | `0 adapted, 108 skipped` | Genuinely clean |
| `qwen` | `0 adapted, 108 skipped` | Genuinely clean |
| `codex` | `0 adapted, 108 skipped` | **False negative** — see below |
| `omp` | `55 adapted, 53 skipped` | Expected; `.omp/` is untracked in this repo |
| `claude-code` | `1 adapted, 107 skipped` | Expected and permanent; see Coverage Matrix |

`codex`'s clean report is exactly the defect the Scope Addition describes.
Bypassing the presence-only `.exists()` checks and content-comparing the codex
bridge tree against its own generators (`_synthesized_skill_md`,
`_make_openai_yaml_content`) finds **11 drifted files** that `ll-adapt` reports
as `skipped`:

```
skills/ll-cleanup-worktrees/SKILL.md              skills/ll-cleanup-worktrees/agents/openai.yaml
skills/ll-create-sprint/SKILL.md                  skills/ll-commit/agents/openai.yaml
skills/ll-loop-suggester/SKILL.md                 skills/ll-loop-suggester/agents/openai.yaml
skills/ll-ready-issue/SKILL.md                    skills/ll-reconcile-issue/agents/openai.yaml
skills/ll-reconcile-issue/SKILL.md
skills/ll-refine-issue/SKILL.md
skills/ll-verify-issues/SKILL.md
```

22 of the 29 bridged `SKILL.md` files are byte-identical to their generator, so
this is real divergence, not a systematically wrong generator.

Note what this means for the codex host specifically: **there is no `.codex/`
mirror for skills or commands.** `CodexEmitter.emit_skill` rewrites the real
`skills/<name>/SKILL.md` in place, and `emit_command` writes
`skills/ll-<stem>/` (64 git-tracked files). Only agents land under
`.codex/agents/`. The "mirror" for codex is the source tree itself.

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

Explicitly out of scope: changing what the adapters generate (all of that moved
to ENH-3265), adding new hosts, and the `.gemini`/`.kimi-code`/`.codex` tree
layouts.

### Host / Artifact Coverage Matrix

A uniform `adapted == 0` assertion across all six `_EMITTER_MAP` hosts is
**incorrect** — it fails permanently for three of them. The gate must be scoped
per `(host, artifact-kind)`:

| Host | skills | commands | agents | mcp_config | Rationale for exclusions |
|---|---|---|---|---|---|
| `gemini` | GATE | GATE | GATE | excluded | Mirrors are git-tracked and currently clean |
| `kimi-code` | GATE | GATE | GATE | excluded | Same |
| `qwen` | GATE | GATE | GATE | excluded | Same |
| `codex` | GATE | GATE | GATE | excluded | Skills/commands live in the source tree, agents in `.codex/agents/` |
| `omp` | GATE* | GATE* | GATE* | excluded | `.omp/` does not exist and has **0 git-tracked files** *in this repo*; there is no mirror to keep current — see the presence-based guard note below |
| `claude-code` | excluded | excluded | excluded | excluded | `emit_skill`/`emit_command`/`emit_agent` are no-op stubs returning `"skipped"` (`claude_code.py:30-40`) |

**Exclude `process_mcp_config` for every host.** None of the three mcp paths is
a tracked mirror; each is operator- or consumer-local state:

- `claude-code` — `config_dir="."`, so `emit_mcp_config` targets repo-root
  `.mcp.json`, which is currently `{"mcpServers": {}}`. This repo is the
  *source*, not a consumer, so the missing `ll-mcp` entry is correct and
  permanent. It will report `adapted` forever.
- `codex` — ignores `output_dir` entirely and reads/writes
  `$CODEX_HOME/config.toml` (`codex.py:427-478`). Against an isolated empty
  `CODEX_HOME` it returns `"adapted"` on first run.
- Excluding mcp_config dissolves the `CODEX_HOME` isolation requirement noted
  elsewhere in this issue. Keep the `monkeypatch.setenv("CODEX_HOME", ...)`
  guard anyway if `process_mcp_config` is ever reached — it is cheap insurance
  against touching the operator's real global config.

**`omp`'s exclusion must be presence-based, not hardcoded.** `GATE*` above means
"gated, but the guard returns early when the mirror root is absent" — the shape
`test_skill_mirrors_carry_companions` (`test_wiring_skills_and_commands.py:437`)
already uses for exactly this host. A hardcoded permanent exclusion would leave
the gate silently off if `.omp/` ever becomes tracked. Keep a named constant for
the *rationale*; make the *guard* dynamic. `claude-code` is different — its
emitters are no-op stubs by construction, so its exclusion is genuinely static.

Per the `test_adapt_golden_corpus.py:199-212` precedent, each exclusion above
should be *test-visible* (a named constant with a docstring explaining why),
not a silent omission.

### Prerequisite: ENH-3265 (split out 2026-08-20)

The gate fails on arrival unless the existing drift is resolved first, and the
11 files are **not** uniformly regenerable — three classes (stale drift,
hand-added fields the generator would delete, and a truncation defect where the
generator is worse than what is on disk). That triage, the
`CodexEmitter.emit_command` / `emit_skill` content-comparison fix, and the
generator-fidelity work all moved to **ENH-3265**, which this issue is now
`blocked_by`.

This matches the resolved decision below ("drift is fixed in a preceding
change, not this one"), which previously had no issue to point at.

**What this issue keeps**: the parametrized dry-run gate, its Coverage Matrix,
its exclusion visibility, and the removal of the hardcoded
`SKILL_MIRRORS_MUST_MATCH_SOURCE` list.

**What ENH-3265 must deliver before this can go green**: codex's bridged tree
byte-clean against its own generators, with `ll-adapt --host codex --apply`
idempotent.

### Resolved decisions

- **`disable-model-invocation: true` artifacts stay unchecked.** `process_skills`
  filters them before the emitter is ever called (`core.py:438-443`), so
  asserting their absence from mirrors is a *different* gate
  (mirror-has-no-orphans) than this one (mirror-is-current), and would need its
  own cleanup pass first — 5 such skills exist. Split to a follow-up issue if
  wanted; out of scope here.
- **Drift is fixed in a preceding change, not this one.** Resolved 2026-08-20 by
  splitting that work out as **ENH-3265**, now this issue's `blocked_by`. It
  lands first; the gate lands second, arriving green.

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

_Consolidated 2026-08-20 from four `/ll:refine-issue` passes; later corrections
applied in place rather than appended._

- `scripts/tests/test_adapters.py:1891-1899` defines `MIRROR_SKILL_EMITTERS: list[tuple[type, str]] = [(QwenEmitter, ".qwen"), (KimiEmitter, ".kimi-code"), (GeminiEmitter, ".gemini"), (OmpEmitter, ".omp")]`, parametrizing `TestMirrorEmitterSkillCompanions` (`:1899-1903`) — the closest existing precedent for a parametrized drift test, but it covers only 4 of the 6 `_EMITTER_MAP` hosts (omits `codex`, `claude-code`) and calls `emitter.emit_skill()` directly rather than driving `main_adapt()` end-to-end. `test_companion_drift_is_repaired` (`:1943-1955`) is the closest existing template for a "call unchanged → skipped, mutate companion → adapted" drift-regression sequence.
- `main_adapt()` (`cli/adapt.py:32`) returns exit-code only (`0`/`1`, `:149`) and never returns/exposes the `(adapted, skipped, errors)` tuples it computes as locals (`:105-146`) — only prints them (`"Done: N adapted, ..."`, `:148`). A test asserting "0 adapted" against `main_adapt()` itself must either call `process_skills`/`process_commands`/`process_agents`/`process_mcp_config` directly (matching the established convention every existing adapter test already follows — see Conventions in Force), or capture and parse stdout, which no existing test does.
- `test_adapt_golden_corpus.py:199-212` (`test_gemini_agent_excluded_from_byte_identity_claim`) is the established pattern for making a *scoping* decision test-visible: a dedicated test whose sole job is to assert a named exclusion's docstring exists, rather than silently omitting a host/path from coverage. Relevant if the new gate carries any host-specific exclusion (e.g. `claude-code` emitting no skill/command/agent artifacts).
- `SKILL_MIRRORS_MUST_MATCH_SOURCE` (`test_wiring_skills_and_commands.py:385-407`) and its test `test_skill_mirror_matches_source` (`:410-419`) — confirmed current failure message: `f"{mirror_rel} is stale relative to {source_rel}. Regenerate with: ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply"` (now three hosts, not two).

- No existing test parametrizes over `_EMITTER_MAP` (`adapters/core.py:53-60`) directly. `test_host_conformance.py:65` (`@pytest.mark.parametrize("host", list(_HOST_RUNNER_REGISTRY.keys()))`) parametrizes a *different* registry (`little_loops.host_runner._HOST_RUNNER_REGISTRY`, the orchestration-CLI registry), not the adapter-emitter registry this issue's gate needs. The two registries' key sets are not guaranteed identical — `adapters/core.py:53-60` carries a comment flagging a `kimi-code` suffix mismatch between them (EPIC-2910). This corrects the earlier Conventions-in-Force citation: `test_host_conformance.py` is precedent for the parametrize-over-registry *shape*, not for `_EMITTER_MAP` specifically — no prior test has iterated `_EMITTER_MAP`'s keys.
- **CORRECTED 2026-08-20** — an earlier pass claimed `process_commands` needs a per-host `output_dir` derived from `HOST_CAPABILITIES`. It does not. `main_adapt()` passes `(commands_dir, skills_dir)` — the plugin `skills/` dir — for **every** host (`adapt.py:112-114`), and `GeminiEmitter.emit_command` ignores the `output_dir` argument entirely, deriving `.gemini/commands/<stem>.toml` from `cmd_path.parent.parent` (`gemini.py:110-111`). Only `CodexEmitter.emit_command` actually consumes it (writing `skills/ll-<stem>/`). A gate that passes `.gemini/commands` here would silently test the wrong tree. Per-host `output_dir` from `HOST_CAPABILITIES.config_dir` **is** required for `process_agents` (`plugin_root/<config_dir>/agents`, `adapt.py:126`) and `process_mcp_config` (`plugin_root/<config_dir>`, `adapt.py:138`).
- Current signatures (`adapters/core.py`): `process_skills(emitter, skills_dir, apply, quiet)` (`:414`); `process_commands(emitter, commands_dir, output_dir, apply, quiet)` (`:471`); `process_agents(emitter, agents_dir, output_dir, apply, quiet, only=None)` (`:544`); `process_mcp_config(emitter, output_dir, apply, quiet)` (`:622`). All four return `(adapted, skipped, errors)`.
- `main_adapt()` (`adapt.py:32`) has no in-repo caller (confirmed via code-graph `callers_of`) — it is a CLI-only entry point that reads `sys.argv` via internal `argparse.parse_args()` and returns only an exit code. A test wanting per-host `(adapted, skipped, errors)` counts must call `process_skills`/`process_commands`/`process_agents`/`process_mcp_config` directly with an emitter from `resolve_emitter(host)` (`core.py:63-81`), not invoke `main_adapt()` and parse its printed summary.
- The `codex` host's `emit_mcp_config` baseline is not uniform with the other five hosts. It ignores the `output_dir` argument entirely and reads/writes `$CODEX_HOME/config.toml` (or `~/.codex/config.toml`) directly, doing an unconditional `read_text()` even under dry-run (`codex.py:446`). Against a freshly isolated, empty `CODEX_HOME`, `_find_ll_mcp_block` finds nothing and `emit_mcp_config` returns `"adapted"` (`codex.py:462-478`) — `adapted == 1` is the *expected* first-run result. **Superseded by the Coverage Matrix**, which excludes `process_mcp_config` from the gate for all hosts; this finding is why. `claude-code` has the same problem for a different reason (repo-root `.mcp.json` is `{"mcpServers": {}}` in this source repo, so it reports `adapted` permanently).
- CODEX_HOME isolation precedent: `TestCodexEmitterEmitMcpConfig._config_path` (`test_adapters.py:658-677`) — `monkeypatch.setenv("CODEX_HOME", str(tmp_path))`, returning `tmp_path / "config.toml"`. The class docstring explains why: "Codex has no project-local MCP config read path (BUG-3178)... `emit_mcp_config` ignores `meta[\"output_dir\"]` entirely and merges into `$CODEX_HOME/config.toml` instead."
- Per-host no-output precedent: `test_skill_mirrors_carry_companions` (`test_wiring_skills_and_commands.py:436-443`) early-`return`s inside the parametrized test body with an inline comment when a host's mirror root doesn't exist for this repo (e.g. `.omp`), rather than a separate test class per host. This is the established shape for handling `claude-code`'s and `omp`'s excluded cases in the new gate, rather than branching test structure per host.
- Idempotency/content-comparison test shape shared across every existing emitter test class (`test_adapters.py`): `test_dry_run_does_not_write`, `test_returns_adapted_on_first_run` (asserts literal `"adapted"`), `test_already_adapted_returns_skipped`/`test_up_to_date_returns_skipped` (asserts `"skipped"` on a second call with unchanged meta), `test_idempotent` (asserts byte-identical content across repeated calls) — e.g. `TestCodexEmitterEmitAgent` (`:576-604`). `TestCodexEmitterEmitCommand` (`:489-501`) currently has the first three but no `test_idempotent`/content-drift case, consistent with `emit_command`'s presence-only check giving nothing to compare — the new content-comparison fix needs this fourth case added. `TestGeminiEmitterEmitCommand` additionally has `test_dry_run_returns_adapted` (`:952-954`), asserting `"adapted"` under dry-run when content differs (dry-run reports what *would* change without writing) — Codex's classes have no equivalent case today since presence-only checks have no drift state to report.
- Stale-mirror failure-message convention: name the offending artifact, then "Regenerate with:" followed by the literal `ll-adapt --host <host> --apply` invocation(s), chained with `&&` when one message covers multiple hosts. Evidence: `test_skill_mirror_matches_source` (`test_wiring_skills_and_commands.py:415-419`, chains three hosts) and the per-host variant `test_skill_mirrors_carry_companions` (`:460-464`, single host via `mirror_root_name.lstrip('.')`).

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `test_wiring_skills_and_commands.py::test_skill_mirror_matches_source` (`SKILL_MIRRORS_MUST_MATCH_SOURCE`) | Hardcoded byte-for-byte comparison of tracked mirror files vs source, for a hand-maintained host/path list | DROPPED | Replaced by the parametrized dry-run gate over `_EMITTER_MAP`; the hardcoded list is what this issue exists to eliminate |
| `adapters/codex.py::CodexEmitter.emit_command` (presence-only `.exists()` check, `:359-370`) | Reports `"skipped"` once `SKILL.md` + `openai.yaml` exist, regardless of content drift; individual per-file `.exists()` write guards mean a stale-but-present file is never rewritten even under `--apply` | CHANGED **by ENH-3265** | Becomes a real content comparison, matching `emit_agent`/`emit_mcp_config`'s existing `existing == new_content` pattern (`codex.py:411`, `:457`). Not this issue's change; listed because the gate is vacuous for host `codex` until it lands |
| `adapters/codex.py::CodexEmitter.emit_skill` openai.yaml companion check (`:309-312`) | Reports `"skipped"` for the companion once it exists, regardless of content drift vs `_make_openai_yaml_content(...)` | CHANGED **by ENH-3265** | Companion gets the same content-comparison treatment |
| `skills/ll-*/SKILL.md` hand-edits, `_extract_skill_short_desc` truncation | See ENH-3265 | MOVED | The Class B data-loss risk and the Class C truncation defect are ENH-3265's AC2/AC1 |

### Files to Modify
- `scripts/tests/test_wiring_skills_and_commands.py` — the `SKILL_MIRRORS_MUST_MATCH_SOURCE` hardcoded-pair test (`:385`, test function `test_skill_mirror_matches_source` `:411`) is the gate this issue replaces; renamed from `WIRE_ISSUE_SKILL_MIRRORS`/`test_wire_issue_skill_mirror_matches_source` since capture.
- ⚠ Superseded by the 2026-08-20 split: `scripts/little_loops/adapters/codex.py` and the 11 drifted `skills/ll-*/` files — **moved to ENH-3265**. Not modified by this issue; the gate only reads them. Retained here as context for why the gate is vacuous for host `codex` until ENH-3265 lands.

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
- ~~Add a new `emit_command` content-drift regression test~~ and ~~a companion-drift test for `agents/openai.yaml`~~ — **moved to ENH-3265** (its AC5/AC6).
- Reuse the `monkeypatch.setenv("CODEX_HOME", str(tmp_path))` pattern from `TestCodexEmitterEmitMcpConfig._config_path` (`test_adapters.py:658-677`) when the new gate's dry-run pass reaches `process_mcp_config` for host `codex`, so it never touches the operator's real `~/.codex/config.toml`.
- No doc, hook, loop, skill, or command consumes `ll-adapt`'s exit code or `"Done: N adapted..."` stdout summary (confirmed via repo-wide grep across `loops/ hooks/ skills/ commands/`) — no gate-consumer updates required.

## Program Design

### Signatures

_Rewritten 2026-08-20 against current HEAD; the prior `adapt_skill(...)` /
bare `main()` entries did not exist and have been deleted rather than
annotated._

- `resolve_emitter(host: str) -> HostEmitter` — existing, `adapters/core.py:63`. How the gate obtains a per-host emitter.
- `process_skills(emitter, skills_dir: Path, apply: bool, quiet: bool) -> tuple[int, int, int]` — existing, `core.py:414`.
- `process_commands(emitter, commands_dir: Path, output_dir: Path, apply: bool, quiet: bool) -> tuple[int, int, int]` — existing, `core.py:471`. `output_dir` is the plugin `skills/` dir for every host; gemini ignores it.
- `process_agents(emitter, agents_dir: Path, output_dir: Path, apply: bool, quiet: bool, only: str | None = None) -> tuple[int, int, int]` — existing, `core.py:544`. `output_dir` is `plugin_root/<config_dir>/agents`.
- `test_host_artifacts_are_not_stale(host: str, kind: str) -> None` — new, parametrized over the Coverage Matrix's gated `(host, artifact-kind)` pairs, in `scripts/tests/test_wiring_skills_and_commands.py`. Note the parametrization is over the matrix, **not** bare `_EMITTER_MAP.keys()`.

### Call Path

`test_skill_mirror_matches_source` (`test_wiring_skills_and_commands.py:411`,
guarding `SKILL_MIRRORS_MUST_MATCH_SOURCE` at `:385`) is the gate being
replaced. The new test calls `resolve_emitter(host)` then the relevant
`process_*(..., apply=False, quiet=True)` directly, asserting `adapted == 0`
and reporting the drifted names on failure. It does **not** drive
`main_adapt()` — that entry point reads `sys.argv` internally and returns only
an exit code, never the counts (`cli/adapt.py:32`, `:148-149`), and no existing
test parses its stdout. `_body_after_frontmatter`
(`test_wiring_skills_and_commands.py:370`) becomes unused if the hardcoded pair
is fully removed — it has 3 references in that file today, all reachable from
the removed test.

### Codebase Research Findings

_Consolidated 2026-08-20 from two `/ll:refine-issue` passes._

- `main_adapt()` delegates to `adapters/core.py`'s `process_skills()` (`:414`), `process_commands()` (`:471`), `process_agents()` (`:544`), `process_mcp_config()` (`:622`) — each returns a real `(adapted, skipped, errors)` int tuple, which is what every existing adapter test asserts on; no test parses `ll-adapt`'s stdout.
- The gate this issue targets is `test_skill_mirror_matches_source` guarding `SKILL_MIRRORS_MUST_MATCH_SOURCE` (`test_wiring_skills_and_commands.py:385`/`:411`), renamed from `WIRE_ISSUE_SKILL_MIRRORS`/`test_wire_issue_skill_mirror_matches_source` since this issue was captured.
- No existing test calls `main_adapt()` directly, in-process or via subprocess. The closest precedent for exercising an `main_adapt_*`-style entry point in-process is `main_adapt_skills_for_codex()`'s test, which patches `sys.argv` and `_find_plugin_root`, then asserts the int return code (`test_adapt_skills_for_codex.py:296-334`).
- Host registry to parametrize over: `_EMITTER_MAP` (`adapters/core.py:53-60`: codex, gemini, omp, kimi-code, claude-code, qwen), mirrored by `HOST_CAPABILITIES` (`adapters/capabilities.py:68-181`, equality-enforced by `test_verify_host_map.py:21`) — not the runtime `_HOST_RUNNER_REGISTRY`, which also carries opencode/pi.

- `main_adapt()` (`cli/adapt.py:32`) is not directly parameterizable by host/apply — it reads args internally via `argparse.parse_args()` against `sys.argv` and returns only an exit code (never the `(adapted, skipped, errors)` counts). A test must call `process_skills`/`process_commands`/`process_agents` directly, using `resolve_emitter(host)` (`core.py:63-81`), rather than driving `main_adapt()` and parsing stdout.
- Confirmed current line numbers for the two presence-only checks this issue's Scope Addition targets: `CodexEmitter.emit_skill`'s openai.yaml companion check is `yaml_exists = openai_yaml.exists()` at `codex.py:310`, gating the skip at `:312`. `CodexEmitter.emit_command`'s presence-only skip is `if out_skill_md.exists() and out_openai_yaml.exists(): ... return "skipped"` at `codex.py:359-362`; the `--apply` branch (`:364-370`) individually guards each write with `if not out_skill_md.exists(): ...` / `if not out_openai_yaml.exists(): ...`, so a stale-but-present file is never rewritten even under `--apply`, not only skipped under dry-run.

## Acceptance Criteria

Scoped to the gate. The generator-fidelity and content-comparison prerequisites
are **ENH-3265**'s AC1–AC7 and are not restated here.

1. **ENH-3265 is `done`.** The gate is not merged against a tree it would fail
   on, and not against a codex emitter that structurally cannot report drift.
2. **The gate exists and is parametrized over the Coverage Matrix**, not a
   hardcoded path list and not bare `_EMITTER_MAP.keys()`. Adding a new command
   or skill is covered the moment it is adapted, with no test-side list to
   update.
3. **Every matrix exclusion is test-visible** — `omp`, `claude-code`, and
   `process_mcp_config` each carry a named constant with a docstring stating
   why, per the `test_adapt_golden_corpus.py:199-212` precedent. A silent
   omission fails review.
4. **`omp`'s guard is presence-based.** The test early-`return`s when the mirror
   root is absent rather than being permanently excluded by name, so the gate
   self-activates if `.omp/` ever becomes tracked. `claude-code` may be
   statically excluded — its emitters are no-op stubs.
5. **Failure messages name the drifted artifacts and the literal fix command**,
   per the established convention (`"<path> is stale. Regenerate with:
   ll-adapt --host <host> --apply"`).
6. **The gate demonstrably catches a present-but-drifted artifact**, not just a
   missing one. A committed test builds a codex bridge fixture that exists on
   disk with stale content and asserts the gate's detection path reports it —
   the false-negative class that motivated this issue. (This replaces the
   earlier "revert the fix and observe red" criterion, which was a manual
   procedure rather than a committable test.)
7. **`process_mcp_config` is never reached with the operator's real config.**
   If the gate touches it at all, `CODEX_HOME` is redirected to a tmp dir per
   `TestCodexEmitterEmitMcpConfig._config_path` (`test_adapters.py:658-677`).
8. `python -m pytest scripts/tests/` exits 0, and
   `SKILL_MIRRORS_MUST_MATCH_SOURCE` (`test_wiring_skills_and_commands.py:385`)
   / `test_skill_mirror_matches_source` (`:411`) are removed, along with
   `_body_after_frontmatter` (`:370`) if it becomes unused — it currently has 3
   references in that file.

## Impact

Silent divergence between what a Claude Code user sees and what a Gemini, Kimi,
or Codex user sees. The mirrors exist specifically so non-Claude hosts get the
same instructions; when they drift, those hosts run older behavior with no
signal to anyone.

The cost is concrete and already paid once: ENH-3046's refine-issue changes had
to be hand-applied to the mirror, and a manual patch proved not to be a reliable
substitute for the generator.

The 2026-08-20 measurement sharpens the priority. The gemini/kimi/qwen mirrors
are clean, so on those hosts this is prophylactic. But codex reports
`0 adapted` while carrying **11 drifted files** — the presence-only check does
not merely fail to catch drift, it actively reports success over it. Anyone
running `ll-adapt --host codex --dry-run` today gets a green light on a
divergent tree. That is worse than having no check, and it is the strongest
argument for doing this now.

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

ENH-2968 independently found the same gap (no test asserts committed `.gemini`/`.kimi-code`/`.codex` mirrors match `ll-adapt` output) and additionally documented a real defect: `CodexEmitter`'s presence-only `.exists()` checks (now around `codex.py:310`, `:359`, `:405`) are not content comparisons, unlike Gemini/Kimi's `out_path.exists() and out_path.read_text() == new_content` pattern.

**Re-split 2026-08-20.** That emitter defect — plus the generator-fidelity work it forces — is now **ENH-3265**, this issue's `blocked_by`. ENH-2968's other half (the gate itself) stays here. The merge was correct in identifying one root cause; the two halves just have different blast radii and deserve separate review.

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

**2026-08-20** (pre-implementation review): Ran all six hosts' dry-runs and
content-compared the codex bridge tree against its generators. Four changes to
this issue's premises:

1. The Motivation's gemini/kimi drift is **repaired** — all of gemini,
   kimi-code, qwen, codex now report `0 adapted, 108 skipped`. Evidence block
   rewritten and marked superseded.
2. codex's `0 adapted` is a **false negative** hiding 11 drifted files. The
   drift the issue wanted to gate against is real, just not where it was
   looking. Recorded in Motivation with a Class A/B/C triage.
3. `adapted == 0` is **wrong for 3 of 6 hosts** (`omp` 55 adapted / untracked
   mirror; `claude-code` 1 adapted / permanent; `codex` mcp_config under
   isolated `CODEX_HOME`). Added the Host / Artifact Coverage Matrix; excluded
   `process_mcp_config` for all hosts.
4. **Data-loss risk found**: 6 bridged SKILL.md files carry hand-added
   `args`/`allowed-tools`/`argument-hint`/Status-enum content that the
   content-comparison change would silently revert on first `--apply`, plus 4
   files where the generator is *worse* than what is on disk (mid-word
   truncation). Both now blocking prerequisites (AC1, AC2).

**2026-08-20** (second pre-implementation review, post-refine): Re-measured all
premises against HEAD — the 11-file drift list reproduces exactly, and every
cited line number is current except two (`_body_after_frontmatter` `:345`→`:370`,
`MIRROR_SKILL_EMITTERS` `:1887`→`:1891`, both corrected). Six changes:

1. **Split.** AC1–AC5 (generator fidelity, content comparison, drift repair)
   moved to **ENH-3265**; this issue is now `blocked_by` it. The prior resolved
   decision already called for a preceding change but had no issue to name.
2. **Class B is mostly source-derivable.** Diffing all 11 files shows every diff
   is purely *additive*, and `allowed-tools:`/`argument-hint:` are already in the
   source `commands/*.md` frontmatter — byte-identical for refine-issue and
   loop-suggester. The fix is pass-through, not "teach the generator to
   preserve." Only `args:` (3 files) and the Status footnote (3 files) are
   genuinely non-derivable. Recorded in ENH-3265 with the `create-sprint`
   allowed-tools asymmetry (source has 3 entries, stub has 1).
3. **AC1's option (a) was vacuous.** Zero of the 29 `commands/*.md` carry
   `metadata.short-description` — it is a field `_synthesized_skill_md` *writes*
   (`codex.py:112`), not one it reads. ENH-3265's AC1 now says to add it.
4. **Factual fix**: `_MAX_SHORT_DESC = 80` (`codex.py:25`), not "~100 chars".
5. **`omp`'s exclusion is now presence-based**, not a hardcoded name, so the
   gate self-activates if `.omp/` ever becomes tracked.
6. **AC9 replaced.** "Revert the fix and observe red" is a manual procedure, not
   a committable test; replaced with a fixture-based detection assertion (now
   AC6).

Also corrected: the claim that `process_commands` needs a per-host `output_dir`
(it does not — every host gets the plugin `skills/` dir, and gemini ignores the
argument). Folded four duplicated `/ll:refine-issue` stanza headers and deleted
the stale `adapt_skill(...)`/`main()` signatures instead of annotating them.
Added an Acceptance Criteria section. Verdict: VALID, implementation-ready.

- 2026-08-16: Core gap still real (no test invokes `ll-adapt --dry-run`); cited code has been refactored to class-based emitters — `adapt_skill(skill_path, apply, quiet)` no longer exists. Updated citations above to `GeminiEmitter.emit_skill`/`emit_command` (`gemini.py:81`/`:117`) and `CodexEmitter.emit_skill`/`emit_command` (`codex.py:~294`/`~333`); presence-only `.exists()` checks in codex.py now sit around lines 310, 359, 405. Verdict: OUTDATED.

## Session Log
- pre-implementation review (2) - 2026-08-20 - re-measured premises; split ENH-3265 out as `blocked_by`; reworked Class B framing, AC1 vacuity, `omp` guard, AC9, and two stale line numbers.
- `/ll:confidence-check` - 2026-08-20T20:33:29 - `1e7934c2-3f73-4b02-90d0-4a6aa50feef9.jsonl`
- pre-implementation review - 2026-08-20 - measured all six host dry-runs, content-compared the codex bridge tree, added the Coverage Matrix / Class A-B-C triage / Acceptance Criteria, folded duplicated research stanzas.
- `/ll:refine-issue` - 2026-08-20T20:15:14 - `d3c778e1-6920-4445-bc39-5861315da162.jsonl`
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
