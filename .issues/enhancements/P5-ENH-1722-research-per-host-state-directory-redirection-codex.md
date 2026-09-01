---
id: ENH-1722
title: Research and decide per-host state directory redirection for Codex
type: ENH
priority: P5
status: open
captured_at: '2026-05-26T02:23:05Z'
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1463
labels:
- codex
- host-compat
- research
testable: false
---

# ENH-1722: Research and decide per-host state directory redirection for Codex

## Summary

`LL_STATE_DIR=.codex` currently scopes only the config probe path. All other state surfaces (`.issues/`, `.loops/`, `.loops/tmp/scratch/`, `.ll/ll-continue-prompt.md`) remain at their default paths regardless of host. EPIC-1463 explicitly deferred this decision pending a research note. This issue produces that note and a concrete decision.

## Motivation

The decision is implicit — nobody wrote down whether a Codex user is better served by `.codex/issues/`, `.codex/loops/` etc., or by the current shared-path behavior. Without a written decision, the question recurs in every conversation touching Codex state. A one-time research note closes the loop and either confirms the status quo is correct or opens a concrete implementation path.

## Acceptance Criteria

- A research note (`thoughts/research/codex-state-dir-redirection.md`) enumerating each state surface and the per-surface recommendation:
  - `.issues/` — share (project issues are host-independent) or scope to `.codex/issues/`?
  - `.loops/` — share or scope?
  - `.loops/tmp/scratch/` — share or scope?
  - `.ll/ll-continue-prompt.md` — share or scope?
  - `.ll/history.db` — share or scope?
- An explicit **Decision** section: "leave shared" or "scope per host" with rationale
- If decision is "scope per host" for any surface: a child FEAT/ENH issue filed with the implementation plan, referencing the research note
- `HOST_COMPATIBILITY.md` `[^state]` footnote updated to reference this issue's decision rather than "file a separate issue if needed"

## Integration Map

### Dependent Files (Callers/Importers)

Per-surface resolution sites, confirmed by direct read (not host-aware today — none reads `LL_HOOK_HOST`/`LL_STATE_DIR`):

- **`.issues/`** — `IssuesConfig.base_dir` (`scripts/little_loops/config/features.py`, default `".issues"`) → `BRConfig.get_issue_dir()` (`scripts/little_loops/config/core.py:512-525`) → schema default in `scripts/little_loops/config-schema.json:74-82`
- **`.loops/`** — `LoopsConfig.loops_dir` (`scripts/little_loops/config/features.py:998,1007`, default `".loops"`) → `BRConfig.get_loops_dir()` (`scripts/little_loops/config/core.py:570-572`)
- **`.loops/tmp/scratch/`** — hardcoded literal, not config-driven: `scripts/little_loops/subprocess_utils.py:296-298` (`_list_scratch_files()`), `hooks/scripts/scratch-pad-redirect.sh:105,119`, `hooks/scripts/scratch-cleanup.sh`
- **`.ll/ll-continue-prompt.md`** — hardcoded literal: `CONTINUATION_PROMPT_PATH = Path(".ll/ll-continue-prompt.md")` (`scripts/little_loops/subprocess_utils.py:103`); also built inline as `Path(".ll") / "ll-continue-prompt.md"` in `scripts/little_loops/hooks/pre_compact.py:100,127,180` and `scripts/little_loops/hooks/pre_compact_handoff.py:153,160`
- **`.ll/history.db`** — the one surface with an existing env/config override chain, but the chain itself is host-blind: `_resolve_db_path()` / `resolve_history_db()` (`scripts/little_loops/session_store/db.py:72-132`) precedence is `LL_HISTORY_DB` env → `history.db_path` config key (via `_config_db_path()`, which does route through the host-aware `resolve_config_path()`, so a hand-written host-specific config file *could* redirect it today) → `.ll/history.db` default. Most call sites bypass the resolver entirely with a hardcoded `cwd / ".ll" / "history.db"`: `scripts/little_loops/hooks/session_start.py:135,147`, `hooks/user_prompt_submit.py:113,128,134`, `hooks/subagent_stop.py:43`, `hooks/sweep_stale_refs.py:163,231`, `decisions.py:575`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

**Files to Modify (this issue's own deliverables)**
- `thoughts/research/codex-state-dir-redirection.md` — new research note (does not yet exist; confirmed absent by repo-wide search of `thoughts/research/`)
- `docs/reference/HOST_COMPATIBILITY.md:487-514` — update the `[^state]` footnote per AC #4. Current text (confirmed): "FEAT-957 deliberately scopes `LL_STATE_DIR=.codex` to the config probe only. Other state directories remain at their default paths regardless of host. If a future feature needs full per-host state redirection, file a separate issue — do not silently expand `LL_STATE_DIR`'s reach."

**Conventions in Force**
- Per-host path branches key off `host`/`state_dir` params passed down from a single env-read boundary, not raw env reads inside leaf functions — evidence: `_config_candidates()` (`scripts/little_loops/config/core.py:120-154`) takes `project_root`, `host`, and `state_dir` as parameters rather than reading env itself, called from `resolve_config_path()` (`:157-181`), which is the sole `os.environ.get("LL_HOOK_HOST"/"LL_STATE_DIR")` read for config-file scoping.
- Host-specific directories are module-level string constants, extended by adding an `if host == "<x>" or state_dir == <X>_CONFIG_DIR:` branch — evidence: `CODEX_CONFIG_DIR`/`GEMINI_CONFIG_DIR`/`OMP_CONFIG_DIR`/`KIMI_CONFIG_DIR`/`QWEN_CONFIG_DIR` (`core.py:55-59`); docstring states "Future hosts add a new branch here rather than a new code path elsewhere" (`core.py:139`). This is now a 5-host branch, not a Codex-only one.
- A second, structurally different per-host pattern already exists for a related but distinct purpose — *reading* each host's own native session-transcript directory (not a little-loops-owned state surface): `host_layout_for(host)` / `HostLayout` (`scripts/little_loops/session_store/writers.py`), consumed in `user_messages.py` and `cli/session.py`. If the decision is "scope per host," this table-driven pattern is a second precedent to weigh against `_config_candidates()`'s branch-per-host style.
- `HOST_COMPATIBILITY.md` footnotes use two established shapes: an *unresolved* footnote naming the deferring issue and forbidding silent expansion (current `[^state]` text above), and a *resolved* footnote citing the research-note path plus follow-on issue IDs (`[^cmds]`, `:212-219`, e.g. "Research findings: `thoughts/research/codex-command-discovery.md` (FEAT-1483). Adaptation work: FEAT-1486 ... and FEAT-1493 ..."). AC #4's rewrite should follow the resolved shape once the decision lands.
- Existing Codex research notes (`thoughts/research/codex-*.md`) share a fixed metadata block (`**Status:**`, `**Last verified:**`, `**Research issue:**`, plus one domain-specific line) and a `## Sources` list before findings; none use a literal `## Decision` heading — the verdict instead lives in the `**Status:**` line and a closing `## Conclusion`/`## Gating recommendation` section. AC #1 asks for an explicit **Decision** section, which is fine as written, but note it's a slight departure from the sibling notes' own convention.

**Tests**
- `scripts/tests/test_config.py:1488-1762` — the only existing host-state test coverage, and it covers only the config probe (`LL_STATE_DIR` for `.codex`/`.kimi-code`/`.qwen`/`.gemini`/`.omp`). No test exists for `.issues/`, `.loops/`, scratch, continuation-prompt, or `history.db` host-scoping, because none is implemented.

**Documentation**
- `docs/reference/HOST_COMPATIBILITY.md:487-514` — the state-directory table (5 surfaces × 5 hosts, each cell "(same path)[^state]") and footnote this issue's AC #4 must update.
- `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md:226-231` — parent epic's own Integration Map already names the same 4 non-config surfaces plus `_config_candidates()` as the file to touch if redirection is adopted; keep the research note's framing consistent with it.

**Configuration**
- No `state_dir` / per-host keyed sub-object exists anywhere in `scripts/little_loops/config-schema.json` (confirmed by a full-file grep for `host|codex|gemini|kimi|qwen|omp` — 135 hits, all flat `"enum"` string fields or prose). If the decision is "scope per host" for any surface, the schema change is a new surface, not an extension of an existing one.

## Implementation Steps

1. Read `docs/reference/HOST_COMPATIBILITY.md` `[^state]` footnote and EPIC-1463 per-host state section for existing framing
2. For each state surface, consider: does a Codex user sharing `.issues/` with Claude Code create friction? Does scoping help or add complexity?
3. Draft `thoughts/research/codex-state-dir-redirection.md` with per-surface analysis and a Decision section
4. Update `HOST_COMPATIBILITY.md` `[^state]` footnote with decision + link
5. If any surface warrants scoping: capture a child issue with implementation plan

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- Scope check: confirm in the research note whether the recommendation applies uniformly to all 5 hosts now covered by `_config_candidates()` (codex, gemini, omp, kimi-code, qwen), not just Codex — see Scope Boundary finding.
- Footnote template: two existing shapes are available to copy from — the current unresolved `[^state]` text (`docs/reference/HOST_COMPATIBILITY.md:499-503`) and the resolved `[^cmds]` footnote (`:212-219`), which cites the research-note path and follow-on issue IDs. Match the resolved shape once the decision lands.
- Architectural alternative to weigh: `host_layout_for(host)` / `HostLayout` (`scripts/little_loops/session_store/writers.py`) is a table-driven per-host pattern already in the codebase (for session-transcript directories), distinct from `_config_candidates()`'s branch-per-host style — worth a line in the research note if "scope per host" is the decision, since it affects which pattern a follow-on implementation issue should use.

## Notes

- Strong prior: the current EPIC-1463 text says "likely the latter (a project's `.issues/` is host-independent), but worth confirming rather than assuming." The research note may simply confirm this and close the gap by documenting the decision.
- This is a research-only issue; no code change is required unless the decision warrants it.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.MD` | `[^state]` footnote to update |
| `scripts/little_loops/config/core.py` | `_config_candidates()` — existing Codex state-dir scoping for reference |

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-01_

**Verdict: OUTDATED** — Research not yet performed; acceptance criteria unmet:
- `thoughts/research/codex-state-dir-redirection.md` does NOT exist (only 4 other Codex research notes present)
- No decision documented in `docs/reference/HOST_COMPATIBILITY.md`
- Issue remains open as a research task; no progress since capture

2026-06-18 (OUTDATED): `thoughts/research/codex-state-dir-redirection.md` still does not exist. `HOST_COMPATIBILITY.md` `[^state]` footnote still unresolved. No progress since capture (2026-05-26). Research task accurately described; no changes needed to issue body.

## Status

**Open** | Created: 2026-05-26 | Priority: P5

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): This issue scopes its research to Codex as the reference case, but the state-scoping decision applies equally to all future host runners. FEAT-1714 (Pi) and FEAT-1850 (omp) are both P5 and have no state-dir scoping of their own. If the research concludes "scope per host," Pi and omp will each need follow-on child issues. Add a note to the **Decision** section (Acceptance Criterion 2) explicitly stating whether the decision applies to Pi/omp as well, so the Pi/omp implementers have guidance without having to re-research the rationale.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

Confirmed by codebase research: `_config_candidates()` (`scripts/little_loops/config/core.py:120-154`) already generalized config-probe host scoping from Codex-only to 5 hosts — `codex`, `gemini`, `omp`, `kimi-code`, `qwen` — all of which currently share `.issues/`, `.loops/`, scratch, continuation-prompt, and `history.db` unconditionally. This raises (not lowers) the value of a single cross-host decision here: whatever this issue decides for Codex is the de facto answer for all 5 hosts unless the Decision section says otherwise, so the note should explicitly state whether its recommendation generalizes to gemini/omp/kimi-code/qwen (not just Pi/omp as the original 2026-06-09 note anticipated).

## Session Log
- `/ll:refine-issue` - 2026-08-31T23:03:10 - `eae3ec24-820c-436e-95b7-06e3279780e2.jsonl`
- `/ll:verify-issues` - 2026-06-27T19:22:20 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:02 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:35 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:19 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:17 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:23:05Z - `1e210ff4-bcab-4372-9c8c-a0ba98da62d5.jsonl`
