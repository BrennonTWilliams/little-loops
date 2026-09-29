---
id: FEAT-3584
type: FEAT
title: Brainstorm ground state with codebase and web evidence probes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
- FEAT-3583
reconcile_attempted: true
---

# FEAT-3584: Brainstorm ground state with codebase and web evidence probes

## Summary

Add a gated `ground` state to the brainstorm engine that attaches evidence to ideas
before shortlisting, with **non-LLM probes** to reject unsupported ideas. Sources:
`none` (artifact/visual default), `codebase` (functional default), `web` (business
default).

## Current Behavior

Brainstorm performs no evidence check: an idea that cites a nonexistent file, symbol, or issue ID, or one that conflicts with an open issue, is ranked the same as a well-supported one.

## Expected Behavior

- `codebase`: each idea declares `extra.touchpoints` (existing anchors it builds on:
  file paths, symbols, issue IDs) and `extra.creates` (new paths it would add). A
  script verifies **only that touchpoints exist** (git-tracked files, `git grep` for
  symbols, `ll-issues show` for IDs) and that each `creates` path does not already
  exist and its parent directory does. New things are therefore never penalized for
  not existing yet. An idea with **zero touchpoints** is `grounded: unknown`
  (flagged `no_anchors`), not `false`. Existence is anchor validation, not proof the
  anchor supports the idea; semantic support and conflicts with open issues are out
  of scope for the gate.
- `web`: an LLM searches for competitors, prior art, and demand signals and cites
  sources with a quoted snippet each; a **non-LLM probe** then fetches every cited
  URL and checks that it loads and that the quoted snippet appears on the page.
  The probe fetches with `curl --proto '=http,https' --max-time 15 --max-filesize 2000000`,
  refuses hosts resolving to loopback/private ranges, and normalizes both page and
  quote before matching (strip tags, decode entities, collapse whitespace,
  case-fold). HTTP 401/403/429, timeouts, and DNS failures are `unknown`; only a
  successfully loaded page lacking the quote is `false`.
  Each idea also carries an explicit assumption list.
- `grounded` is tri-state: `true` (all anchors/sources verified), `false` (an
  anchor or source failed verification), `unknown` (retrieval failed, network
  unavailable, or the host lacks web tools). `false` ideas are excluded from the
  tournament; `unknown` ideas stay eligible and are flagged in the report.
- Web grounding runs on **shortlisted** ideas only (cost). To avoid a back-edge into
  `ground`/`materialize`, the `shortlist` keeps a **reserve** (top 2 per cell when
  `ground=web`) and grounds both; the first grounded candidate per cell becomes
  the finalist. If a cell has no eligible candidate it is dropped, and the
  FEAT-3582 finalist floor is rechecked in `validate_portfolio`.
- Skipped entirely when the resolved `ground` is `none`.

## Use Case

**Who**: A little-loops user brainstorming a functional design (feature, architecture, API) in this repo, or a business opportunity.

**Context**: LLM-generated ideas often cite files, symbols, or issues that do not exist, or duplicate work already tracked.

**Goal**: Have unsupported ideas rejected by deterministic probes before they reach the tournament.

**Outcome**: `ideas.jsonl` records `evidence` and `grounded` per idea; `grounded: false` ideas are excluded from the tournament and `unknown` ideas are flagged.

## Motivation

EPIC-3581 notes that functional designs need codebase grounding and business opportunities need market grounding. Non-LLM probes (git-tracked files, `git grep`, `ll-issues show`) give a cheap, deterministic filter that stops hallucinated anchors from winning a tournament.

## Proposed Solution

Add a gated `ground` state to `scripts/little_loops/loops/brainstorm.yaml`, skipped when the resolved `ground` is `none`:

- Two states, named for their placement: `ground_codebase` (between `dedup` and `shortlist`; cheap, runs on all ideas) and `ground_web` (after `shortlist`; runs on the shortlist reserve only). A script in `ground_codebase` verifies files with `git ls-files`, symbols with `git grep`, issue IDs with `ll-issues show`; `creates` paths are checked for non-collision. Existence only — no semantic-support or open-issue-conflict judgement.
- `codebase` mode also feeds a **bounded repo summary** (top-level `git ls-files` tree, capped ~200 lines) into `diverge` via the profile, so ideas cite real anchors instead of guessing. This is a cheap slice of the pre-ideation context pass; a fuller pass stays a follow-up.
- `web` (`ground_web`): an LLM step searches and emits `{url, quote}` sources plus an assumption list per idea; a non-LLM probe (hardened `curl` fetch + normalized fixed-string match of `quote`, see § Expected Behavior) verifies each source. Retrieval failure or missing web capability yields `grounded: unknown`, never a silent drop.
- `grounded: false` ideas are excluded from the tournament; the shortlist reserve replaces them within the same cell; the finalist floor is rechecked by `validate_portfolio` (FEAT-3582).

Issue-ID probing activates only when `.issues/` / `ll-issues` is available so the core stays decoupled from the Issue system.

**Out of scope (follow-up candidate):** a bounded pre-ideation context-gathering pass that feeds repo or market context into `diverge`. Post-generation grounding only filters; it cannot inform generation.

## Program Design

### Types

- `Source`: `{url: str, quote: str, verified: bool | null}` — `null` = retrieval failed
- `Evidence`: `{anchors: [str], sources: [Source], assumptions: [str]}`
- `IdeaRecord.extra` gains `touchpoints: [str]`, `creates: [str]`, `evidence: Evidence` and `grounded: true | false | "unknown"`

### Signatures

- `probe_anchor(anchor: str) -> bool` — file/symbol/issue-ID existence check, no LLM
- `probe_source(url: str, quote: str) -> bool | None` — fetch + fixed-string match, no LLM; `None` on retrieval failure
- `ground_idea(idea: IdeaRecord, source: str) -> IdeaRecord` — attaches evidence and sets `grounded`

### Call Path

`dedup` -> `ground` (codebase) -> `probe_anchor` -> `ll-issues show`; `shortlist` -> `ground` (web) -> `probe_source` -> `tournament`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add gated `ground` state and probe script; extend idea schema with `evidence`/`grounded`

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)
- `ll-issues show` CLI (`scripts/little_loops/cli/issues/`) — issue-ID probe

### Similar Patterns
- Inline `action_type: shell` state with an `exit_code` evaluator (`dedup_novelty`, `saturation_gate` in the pre-3582 `brainstorm.yaml`) — the in-repo convention for non-LLM checks

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New tests: probe pass/fail for missing file, missing symbol, unknown issue ID, using fixture ideas

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions

### Configuration
- Context key: `ground` (none|codebase|web), normally resolved from the profile (FEAT-3583)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Stale state names in this issue**: `brainstorm.yaml` (459 lines) has no `shortlist` or `tournament` state today. The live flow is `init → frame → pop_lens ⇄ diverge → dedup_novelty → saturation_gate → (pop_lens | cluster) → rank → converge → route_sink`. `ideas.jsonl` is appended per lens round inside `dedup_novelty`, so a `ground` pass can only see the complete set after the lens loop drains. Placement "between `dedup` and `shortlist`" is therefore only meaningful relative to FEAT-3582's restructure (blocked_by); until it lands, the natural seam is immediately before `cluster`.
- **Routing constraint**: three edges currently target `cluster` — `pop_lens.on_no`, `saturation_gate.on_no`, and `saturation_gate.on_error` (plus `dedup_novelty.on_no`). A gated `ground` state must intercept all of them, or ungrounded ideas reach `cluster`/`rank` via the unintercepted edge. `test_brainstorm.py::TestBrainstormShellStates` asserts routing of `pop_lens`, `saturation_gate`, `dedup_novelty`, and `cluster`/`rank` `on_error`; those contracts must keep passing or be updated deliberately.
- **Idea schema today is `{text, rationale}` only** (`diverge` prompt and `dedup_novelty` parser); no `IdeaRecord` class exists in `scripts/little_loops/` — the `Program Design` type is a JSONL row shape, not a Python dataclass. `dedup_novelty` writes rows verbatim (`json.dumps(idea)`), so added `evidence`/`grounded` keys survive downstream states that read `ideas.jsonl` (`cluster`, `rank`, `converge` all read it via prompt and would need to be told to exclude `grounded: false`).
- **Exit-code contract to inherit**: `dedup_novelty` documents (BUG-2468) that exit 2 = crash → `on_error: finalize_failed`, and a crash must never look like "nothing to do". A probe script must likewise separate "anchor not found" (a normal grounding result, exit 0 with `grounded: false`) from script failure (exit 2). LLM payloads reach Python only via a quoted heredoc file, never interpolated into source.
- **`ll-issues show <ID>`** exits 0 on found, 1 with `Error: Issue '<id>' not found.` on stdout when absent (`cli/issues/show.py:cmd_show`) — exit 1 is "unknown ID", so an unavailable/absent `ll-issues` binary (exit 127) or missing `.issues/` must be distinguished from exit 1 to keep the Issue-system decoupling AC honest.
- **`.loops/probes/` is not a matching precedent**: its contents are `.mjs` browser/DOM probes (`feat-3488-browser-probes.mjs`, etc.), not shell/Python existence probes. The in-repo convention for non-LLM checks is an inline `action_type: shell` state with an `exit_code` evaluator (`dedup_novelty`, `saturation_gate`); Similar Patterns updated accordingly.
- **Loop-authoring constraints**: `test_required_states_exist` lists required states (adding `ground` is safe; renaming existing ones is not); `max_steps: 60` bounds the run; bash `${...}` inside FSM shell actions must be escaped `$${...}`; `${captured.run_dir.output}` uses in new states need the same `mr11-ok` handling or a `${context.run_dir}` path as `dedup_novelty` does; `ll-loop validate` enforces MR-1..MR-14, and `test_builtin_loops.py` (~line 20421 onward) carries per-loop interpolation-site allowlists that a new state referencing `${context.*}` may trip.
- **Dependency on FEAT-3583** (now `blocked_by`): the `ground` value is read from the resolved `profile.json`. The context key defaults to `""` (inherit from profile) per FEAT-3583; the earlier standalone-`none` default is superseded.

### Wiring Additions

_Wiring pass added by `/ll:wire-issue`:_

**Files to Modify**
- `scripts/little_loops/fsm/fence.py` — `FENCE_ROLES` entry for the `web` research prompt state (interpolates `${context.brief}`) [Agent 3]
- `scripts/tests/data/loop_interpolation_baseline.json` — new `ground` shell-state interpolation sites [Agent 2]

**Tests**
- `scripts/tests/test_builtin_loop_hardcode_gate.py` — scans every loop YAML for this-repo hardcodes; codebase probes must take paths/symbols from idea anchors, never name little-loops paths [Agent 3]
- `scripts/tests/test_builtin_loops.py` — `MR11_MARKER_ALLOWLIST` (exact set) and `TestValidatorWarningBudget` apply to the new `ground` heredoc/probe state [Agent 3]
- Probe tests: extract the `ground` action with `_bash` (`test_brainstorm.py` `TestBug2468ErrorRouting._dedup_action` shape) and run against a `tmp_path` git repo fixture for missing file / missing symbol / unknown ID [Agent 3]

**Configuration**
- Validator: MR-10 parse-swallow — probe script must keep exit 2 for crash, exit 0 + `grounded: false` for "not found", with `on_error` routed [Agent 2]
- Adds 1 fixed step to the `max_steps: 60` budget tracked in FEAT-3582 [Agent 2]

## Implementation Steps

1. Add the `ground` state with `none|codebase|web` routing driven by the resolved profile (FEAT-3583).
2. Implement the deterministic `probe_anchor` script (git-tracked file, `git grep` symbol, guarded `ll-issues show`).
3. Add the `web` research step (finalists only) emitting `{url, quote}` sources and an assumption list, plus the non-LLM `probe_source` check.
4. Record `evidence` and tri-state `grounded` per idea in `ideas.jsonl`; exclude `false` ideas from the tournament, backfill from the same cell, flag `unknown` ideas in the report.
5. Add probe pass/fail tests with fixture ideas and run `ll-loop validate brainstorm`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add the `web` research prompt state to `fence.py` `FENCE_ROLES`
- Keep probe script free of little-loops-specific paths (`test_builtin_loop_hardcode_gate.py`)
- Update `loop_interpolation_baseline.json`; check `MR11_MARKER_ALLOWLIST` and warning-budget tests
- Probe pass/fail tests via `_bash` on a `tmp_path` git fixture

## Impact

- **Priority**: P3 - improves idea quality for functional/business modes but the core works without it
- **Effort**: Medium - one gated state plus a small probe script; reuses existing git and `ll-issues` CLIs
- **Risk**: Low - skipped when `ground=none`; probes are read-only
- **Breaking Change**: No

## Acceptance Criteria

- Codebase probes are deterministic and cover: missing touchpoint file, missing
  symbol, unknown issue ID, `creates` path that already exists, `creates` with a
  missing parent dir, and zero-touchpoint idea (`unknown`, not `false`).
- Web source probe is non-LLM and covers: URL loads with quote present (pass, incl.
  after whitespace/entity/case normalization), URL loads without quote (fail),
  retrieval failure and HTTP 401/403/429 (`unknown`), non-http(s) scheme and
  private-range host (rejected → `unknown`), no web capability (`unknown`, not
  dropped).
- Grounding results recorded per idea in `ideas.jsonl` (`evidence`, tri-state
  `grounded`).
- A `grounded: false` finalist is replaced by its cell's reserve candidate (no
  back-edge); if that leaves fewer than 2 eligible finalists, `validate_portfolio` fails the run before any sink.
- Core loop stays decoupled from the Issue system: issue-ID probing is only active
  when `.issues/` / `ll-issues` is available.
- Tests cover probe pass/fail with fixture ideas.

## Review Decisions

_Added 2026-09-28 (EPIC-3581 sub-issue review):_

- `touchpoints` vs `creates` split so functional ideas proposing new files aren't marked ungrounded; zero-touchpoint ideas are `unknown`.
- Bounded repo summary fed to `diverge` in codebase mode (ideas were previously generated with no repo context).
- Web probe hardening: scheme allowlist, private-range block, timeout/size caps, 401/403/429 → `unknown`, quote normalization.
- No backfill back-edge: `shortlist` keeps a top-2 reserve per cell when `ground=web`.
- Two states (`ground_codebase`, `ground_web`) because the insertion points differ.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:reconcile-issue` - 2026-09-25T17:15:17 - `f2fe6fc2-4dc3-4f38-a10c-f2bd8be05a0c.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:45 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:47 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:44 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
