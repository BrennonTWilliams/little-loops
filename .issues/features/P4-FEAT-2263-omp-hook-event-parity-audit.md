---
id: FEAT-2263
title: omp hook-event parity audit
type: feature
status: done
priority: P4
testable: false
discovered_date: 2026-06-24
discovered_by: planning-assessment
completed_at: '2026-08-30T23:53:58Z'
parent: EPIC-2258
depends_on:
- FEAT-1850
- FEAT-2797
labels:
- host-compat
- omp
- hooks
- parity
relates_to:
- FEAT-2261
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 78
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-2263: omp hook-event parity audit

## Summary

Audit oh-my-pi's hook-event surface against the ll intent set and record which
ll intents (`pre_tool_use`, `post_tool_use`, `user_prompt_submit`, `stop`,
`session_end`, …) omp can fire natively vs. which are absent. Absorbs the intent
of the cancelled vanilla-Pi parity issue FEAT-1715, adapted to omp's richer
event model.

## Current Behavior

omp's hook-event surface has not been audited against the ll intent set. The
omp hook-intent rows in `HOST_COMPATIBILITY.md` are unpopulated/unknown, and
`hooks/adapters/omp/README.md` carries no verified parity matrix. The parity
gap is assumed to be narrower than vanilla pi-mono's (omp exposes more
lifecycle events) but this is unmeasured.

## Expected Behavior

A research doc (`thoughts/research/omp-hook-event-parity.md`) records the omp→ll
event mapping and any gaps (ll intents with no omp equivalent). The
`HOST_COMPATIBILITY.md` omp hook-intent rows are fully populated
(✓ / ✗-linked / N/A) with no unknown cells, and the
`hooks/adapters/omp/README.md` parity matrix matches the audit.

## Motivation

omp's SDK exposes more lifecycle events than vanilla pi-mono, so the parity gap
should be narrower — but it must be measured, not assumed, before
`HOST_COMPATIBILITY.md` claims any omp hook cell. This audit feeds FEAT-2261's
event mapping.

## Use Case

An implementer picking up FEAT-2261 (the omp hook adapter, currently
`blocked_by: FEAT-2263`) needs to know, before writing any adapter code, which
of omp's native lifecycle events correspond to each of the 7 ll intents, and
which ll intents have no omp equivalent. Today they'd have to re-derive this
from the upstream oh-my-pi source/docs themselves. After this audit lands,
they instead read `thoughts/research/omp-hook-event-parity.md` and the omp
column in `HOST_COMPATIBILITY.md`'s Hook intents table, and can start
implementation immediately with a verified event mapping in hand.

## Acceptance Criteria

- `thoughts/research/omp-hook-event-parity.md` records the omp→ll event mapping
  and any gaps (events with no omp equivalent).
- `HOST_COMPATIBILITY.md` omp hook-intent rows are populated (✓ / ✗-linked / N/A)
  — no unknown cells.
- `hooks/adapters/omp/README.md` parity matrix matches the audit (cross-check
  with FEAT-2261).

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis._

### Files to Create (Deliverables)

- `thoughts/research/omp-hook-event-parity.md` — NEW research doc recording the
  omp→ll event mapping. Model structure on `thoughts/research/gemini-cli-surface.md`:
  header block (`Status:` / `Last verified:` / `Research issue: FEAT-2263` / omp
  version pin), Q-sections each opening with a one-line **bolded finding**, an
  "Event inventory and ll intent mapping" table with columns
  `omp event | ll intent | Advisory? | Input extras | ll handler relevance`, a gaps
  list, and a closing "Capability map" code block sketching `OmpRunner`'s
  `HostCapabilities`.

### Files to Modify

- `docs/reference/HOST_COMPATIBILITY.md` — currently has **no omp column at all**
  (only Claude Code, OpenCode, Codex CLI, Gemini CLI). The audit must: (a) add an omp
  column to the `## Hook intents` table; (b) add an omp row to `## Adapter locations`;
  (c) add an `[^omp]` footnote modeled on the existing `[^gemini]` footnote (tracking
  epic EPIC-2258, research-spike FEAT-2263, artifact path, gating statement); and
  (d) add a `## Tracking issues` bullet for FEAT-2263. The existing `[^orch]` footnote
  already records that omp supersedes the frozen Pi column once `OmpRunner` lands.

### Files Validated Against (owned by FEAT-2261, not created here)

- `hooks/adapters/omp/README.md` — does **not exist yet** (FEAT-2261 creates it). This
  audit's third acceptance criterion is a *cross-check*: the README's "Event → Intent
  Mapping" parity matrix must agree with this audit. Model that README table on
  `hooks/adapters/codex/README.md` (4 columns: `event key | ll intent | Python
  invocation | Status`).

### Reference Templates (read-only)

- `thoughts/research/gemini-cli-surface.md` — structural template for the research doc
  (analogue cited in this issue's Reference section).
- `thoughts/research/hot-path-hook-intents.md` — alt research-decision doc format.
- `hooks/adapters/codex/README.md` — 4-column adapter-README parity table.
- `hooks/adapters/opencode/README.md` — alt 3-column adapter-README format.

### Source of Truth — the Complete ll Hook Intent Set

- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` and the `_USAGE`
  string enumerate the **canonical 7 ll intents** omp must be scored against (this
  issue's body lists them with a trailing "…"; these seven are the complete set):
  `session_start`, `user_prompt_submit`, `pre_tool_use`, `post_tool_use`,
  `pre_compact`, `pre_compact_handoff`, `session_end`. Note `pre_compact_handoff` is
  currently wired only on Claude Code, and only Claude Code maps `Stop` → `session_end`.
- `scripts/little_loops/hooks/types.py` — `LLHookEvent` / `LLHookResult` envelopes
  (host native event → `LLHookEvent` → handler `handle()` → `LLHookResult` → adapter
  relays stdout/stderr/exit-code). `LL_HOOK_HOST` selects the host; absent ⇒
  `claude-code`.

### Cell-Convention Note

The acceptance criteria say "✓ / ✗-linked / N/A", but the established convention in
`HOST_COMPATIBILITY.md` for a *gap with a known native event* is
`(deferred)[^omp] — `OmpEventName`` (native event named inline), not a bare `✗`.
Reserve `✗[^footnote]` for capability tables; use `(deferred)[^omp]` for hook-intent
gaps so the cell still names omp's event and the audit reads as "no current consumer"
rather than "impossible".

### Dependency / Blocker

- `depends_on: FEAT-1850` (OmpRunner) — `OmpRunner` **is now registered** in
  `scripts/little_loops/host_runner.py:_HOST_RUNNER_REGISTRY` (`host_runner.py:1821`),
  since FEAT-1850 (`status: done`) landed. The audit needs omp's native event
  names, which FEAT-1850's runner work surfaces. FEAT-2261 (omp adapter)
  consumes this audit's mapping; the dependency is satisfied and this audit is
  unblocked.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- `_dispatch_table()` (`scripts/little_loops/hooks/__init__.py`) currently wires **11** intents total (`pre_compact`, `pre_compact_handoff`, `session_start`, `session_end`, `drift_check`, `user_prompt_submit`, `post_tool_use`, `pre_tool_use`, `edit_batch_nudge`, `subagent_start`, `subagent_stop`, `pre_done`). The "canonical 7" this issue names is a deliberate audit-scope subset, not the complete registered set — worth stating explicitly so a reader doesn't read "these seven are the complete set" as "all ll intents."
- There is no ll intent literally named `stop`. Claude Code's `Stop` host event maps to the `pre_done` intent, not `session_end` — `session_end` is instead dispatched from the `SessionStart` host event via `sweep_stale_refs.handle` (see the `[^ssend]` inline footnote on Claude Code's own `session_end` cell, `HOST_COMPATIBILITY.md:74`). When writing the omp `session_end` cell, cross-reference `[^ssend]`'s convention rather than assuming a `Stop`-equivalent event is the target.
- `pre_compact_handoff` has **no row at all** in `HOST_COMPATIBILITY.md`'s `## Hook intents` table today, for any host (confirmed by reading the full table, `HOST_COMPATIBILITY.md:67-76` — existing rows are `session_start`, `pre_compact`, `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, `session_end`, `post_compact`, `permission_request`). Populating omp's `pre_compact_handoff` cell requires **adding a new row to the table**, not just a new column cell in an existing row.
- The `[^omp]` footnote already exists (`HOST_COMPATIBILITY.md:252-259`) but is currently anchored only to the "Runner Capabilities" table (its `Streaming` row). It reads in part: "the hook adapter (FEAT-2261) and hook-event parity audit (FEAT-2263) are pending — hook-intent cells for omp are not tracked in the matrix until FEAT-2261 lands." Since this audit (FEAT-2263) is unblocked and populates the Hook-intents omp column *before* FEAT-2261 lands (FEAT-2261 is `blocked_by: FEAT-2263`), that sentence goes stale the moment this issue's edit lands — the footnote must be **extended** (referenced from the new Hook-intents cells too, per the Scope Boundary note shared with FEAT-2797) and that stale sentence corrected, not left standing.
- No reusable script exists in this repo for auditing an upstream host's surface against its source (searched for `contents API`/`raw.githubusercontent`/`api.github.com` — no implementation hits, only issue prose). Three manual methods precede this audit and are all viable for enumerating omp's native hook-event names: reading a locally installed Bun package's TS source directly (`thoughts/research/omp-skill-command-surface.md`'s method, e.g. `src/discovery/builtin.ts`), the GitHub contents API against `can1357/oh-my-pi@main` (FEAT-2797's method), or upstream README/docs (`omp-headless-flags.md`'s method). FEAT-2797's Notes section separately points at `docs/hooks.md` in the upstream oh-my-pi repo as documenting "session, agent/context, tool pre/post" event surfaces plus mutation semantics and ordering — the most direct candidate source for this audit's event enumeration.

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Two existing adapter shapes show what an omp entry in the event-mapping table's "ll handler relevance" column should account for: a Bash-shim shape (`scripts/little_loops/hooks/adapters/codex/session-start.sh` — sets `LL_HOOK_HOST=codex`, pipes stdin JSON to `python -m little_loops.hooks <intent>`) and a TS/Bun-plugin shape (`hooks/adapters/opencode/index.ts` — a `Plugin` object keyed by native event names, each handler calling a local `spawnIntent()` helper that `Bun.spawn`s the same CLI). Both converge on the same `main_hooks()` entry point; only the native-event-name binding and transport differ. Neither exists for omp yet (FEAT-2261 builds it), but the audit's per-event "ll handler relevance" notes are more useful to FEAT-2261 if they flag which shape a given omp event's runtime (in-process JS callback vs. external process hook) would need.
- `HostCapabilities` (`scripts/little_loops/host_runner.py`) has exactly six fields — `streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed` — none hook-event-shaped. This confirms the Integration Map's "Capability map" deliverable (a `HostCapabilities(...)` code block) is illustrative prose modeled on `omp-headless-flags.md`'s existing block, not a change to the dataclass or to `OmpRunner.capabilities` — there is no hook-related field for the audit to populate.
- Gaps-list convention correction: none of the four precedent research docs (`gemini-cli-surface.md`, `omp-headless-flags.md`, `omp-skill-command-surface.md`, `hot-path-hook-intents.md`) has a dedicated `## Gaps` heading. Gaps are instead embedded as sentinel rows inside the event-inventory table itself — `gemini-cli-surface.md` uses the literal string `(no ll intent yet)` in the ll-intent column for an omp/gemini-side event with no ll consumer, `omp-headless-flags.md` uses `**N/A → CapabilityNotSupported**` inline in its flag-translation table. This issue's own Expected Behavior and Implementation Steps wording ("a gaps list") should resolve to this same embedded-sentinel-row convention, not a separate `## Gaps` section, to stay consistent with precedent.
- The `[^omp]` footnote's existing extension mechanism (`docs/reference/HOST_COMPATIBILITY.md:252-259`) already shows the precedent for how this audit should append hook-parity content without disturbing FEAT-2797's structured-output content: FEAT-2797 added its own nested bold sub-heading (`**json_schema/structured_output (FEAT-2797):**`) inside the same footnote rather than editing the existing prose. This audit's hook-parity content should follow the identical shape — a new nested bold sub-heading of its own — when extending `[^omp]`.
- Adapter-README parity-matrix column conventions are split three ways, not two: codex/kimi use a 4-column shape (`event | ll intent | Python invocation | Status`/`Notes`), opencode uses a 3-column shape (no Status column, caveats folded into the invocation cell), and qwen uses a 4th, previously unlisted variant (`Qwen event | Matcher | Shim | ll intent` — a shim-script-filename column, no literal `python -m little_loops.hooks` invocation string at all). This issue's Integration Map already directs `hooks/adapters/omp/README.md` (FEAT-2261's file) to the codex-style 4-column shape, which stays the correct choice — the qwen variant is noted here only so a reader cross-checking the eventual omp README isn't confused by which of three (not two) live conventions the cross-check target should match.
- `thoughts/` is entirely gitignored (`.gitignore:131`) — the deliverable `thoughts/research/omp-hook-event-parity.md` will not show up in `git status`/`git add` and is not part of any commit for this issue, consistent with every other file already present under `thoughts/research/`.
- `scripts/tests/test_wiring_skills_and_commands.py:181-186,415-416` shows a precedented pinning-test mechanism that asserts specific strings exist inside a `thoughts/research/*.md` doc, tagged with the landing issue ID (used for `omp-headless-flags.md` — that pass is credited to a now-`done` issue — and for `codex-command-discovery.md` under `FEAT-1483`). This precedent exists but was skipped for more recent spikes (Gemini FEAT-2179, Kimi FEAT-2911) — both adding and skipping this test are established patterns, so choosing between them for `omp-hook-event-parity.md` is a genuine implementer call, not a gap.

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- `OmpRunner`'s full class body (`scripts/little_loops/host_runner.py:1219-1402` — docstring, `capabilities` block, all `build_*` methods, `describe_capabilities()`) contains **zero** hook/event/lifecycle references. FEAT-1850's runner work does not surface omp's native event names in any form — the audit must derive them from an external source (upstream `oh-my-pi` docs/source), not from anything already in this repo's `OmpRunner`.
- Both existing omp research docs explicitly disclaim hook coverage: `thoughts/research/omp-headless-flags.md` § "Out of scope here" states verbatim "Hook event surfaces — tracked by FEAT-2261/FEAT-2263, not this audit"; `thoughts/research/omp-skill-command-surface.md` § "Out of scope here" likewise does not mention hooks. Confirms no partial hook-event enumeration exists anywhere in the repo today.
- `scripts/little_loops/adapters/omp.py` (`OmpEmitter`) exists as a sibling adapter module for skill/command/agent concerns (FEAT-2787/3104/3105 scope) — not hook-related and out of this audit's scope, but the nearest existing omp-specific Python module for a reader orienting to where hook-adapter code would eventually live (FEAT-2261).
- `[^omp]` footnote full verbatim span is `docs/reference/HOST_COMPATIBILITY.md:252-276` (not 252-259 as previously estimated); the stale sentence to correct is exactly: "the hook adapter (FEAT-2261) and hook-event parity audit (FEAT-2263) are pending — hook-intent cells for omp are not tracked in the matrix until FEAT-2261 lands." The FEAT-2797 nested-subheading precedent this audit should mirror is exactly `**`json_schema`/`structured_output` (FEAT-2797):**` (bold text at the footnote's 4-space continuation indent, not a markdown `###` heading).
- `## Tracking issues` (`HOST_COMPATIBILITY.md:613-650`) already has an **EPIC-2258** bullet (lines 628-630) reading verbatim: "**EPIC-2258** — oh-my-pi (`omp`) host adapter tracking (this matrix's omp column). Runner core (FEAT-1850) and config probe (FEAT-2262) landed; hook adapter (FEAT-2261) and hook-event parity (FEAT-2263) pending." This existing bullet needs updating in place once the audit lands — the convention seen elsewhere in this list (EPIC-2178/FEAT-2179, EPIC-2910/FEAT-2911) is that an epic gets one bullet updated in place across its lifecycle AND its research-spike child can additionally get its own separate bullet citing the artifact path — both shapes are attested, so adding a dedicated FEAT-2263 bullet alongside updating the EPIC-2258 bullet, or just updating the EPIC-2258 bullet alone, are both consistent with precedent.
- `## Adapter locations` (`HOST_COMPATIBILITY.md:565-574`) closing line reads: "Each adapter is a thin transport (`spawn → set env → pipe stdin → exit`); all real logic lives in `scripts/little_loops/hooks/`." — relevant framing for the new omp row this audit adds to that table.
- The `gemini-cli-surface.md` template's header block (cited in this issue's Integration Map) is followed by a `## Sources` bulleted list (exact file paths/URLs consulted) before the first `## Q1: ...` section — the Integration Map's "header block" bullet doesn't currently mention this `## Sources` section as part of the structure to mirror.
- Column-landing precedent for adding a new host to `HOST_COMPATIBILITY.md`: `.issues/enhancements/P3-ENH-2919-kimi-host-compatibility-column-docs.md` and `.issues/enhancements/P2-ENH-3162-host-compatibility-qwen-column-and-docs.md` (both done) are separate final-gate issues that flip cells across *every* per-host table at once (hook intents, discovery, runner capabilities, orchestration CLI, config probe, state directory, installation, env vars) once all implementation children have landed. `.issues/enhancements/P4-ENH-2191-host-compatibility-gemini-column.md` (still open) shows the alternative: a running "Verification Notes" log recording incremental cell flips as children land one at a time. FEAT-2263 is scoped narrower than either (Hook-intents column plus footnote/adapter-locations/tracking-issues only, not the full per-host table set) — noted here as a scope contrast, not a claim that FEAT-2263 should expand to match.
- Adapter-README parity-table precedent quotes (exact rows), confirming the cell-convention already directed in this issue: codex's 4-column table (`hooks/adapters/codex/README.md:27-39`) carries a `Status` column with free-text values like "Deferred — no concrete consumer in ll today"; opencode's 3-column table (`hooks/adapters/opencode/README.md:37-46`) has no Status column and folds the same kind of caveat into prose below the table instead.
- Test-pinning precedent census confirms the issue's "genuine implementer call" framing: `gemini-cli-surface.md` (FEAT-2179), `kimi-cli-surface.md` (FEAT-2911), and `qwen-code-surface.md` (FEAT-3155) all have **zero** entries in `scripts/tests/test_wiring_skills_and_commands.py`'s pinning tuples (`DOC_STRINGS_PRESENT`/`DOC_FILES_MUST_EXIST`) — only `omp-headless-flags.md` (FEAT-2797) and `codex-command-discovery.md` (FEAT-1483) are pinned. Three of the five most recent host-surface research docs skip the pinning test.

## Program Design

_Added by `/ll:refine-issue` — based on codebase analysis._

### Types

- `LLHookEvent` (`scripts/little_loops/hooks/types.py:21`) — fields: `host`, `intent`, `timestamp`, `payload`, `session_id`, `cwd`. The audit's event-inventory table must stay consistent with this envelope: every `ll intent` cell the audit records is a value this `intent` field would carry, and any "Input extras" the audit notes per event should map onto `payload`'s host-supplied dict.
- `LLHookResult` (`scripts/little_loops/hooks/types.py:85`) — fields: `exit_code`, `feedback`, `decision`, `data`, `stdout`. Relevant to the audit's "Advisory?" column: `exit_code == 2` is the block-and-inject-feedback convention a blocking omp event would need to honor; an advisory-only omp event has no way to produce that effect.
- `HostCapabilities` (`scripts/little_loops/host_runner.py`) — six fields (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`); none is hook-event-shaped. The audit's closing "Capability map" block is therefore illustrative prose modeled on `omp-headless-flags.md`'s existing block, not a dataclass or `OmpRunner.capabilities` change — there is no field on this type for the audit to populate.

### Signatures

- `_dispatch_table()` (`scripts/little_loops/hooks/__init__.py:137-170`) — existing intent→handler map; the audit's 7-intent scope (`session_start`, `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, `pre_compact`, `pre_compact_handoff`, `session_end`) is a deliberate subset of the 11 intents this function actually wires.
- `main_hooks()` (`scripts/little_loops/hooks/__init__.py`) — existing CLI entry point (`python -m little_loops.hooks <intent>`) that every host adapter, including omp's future one (FEAT-2261), pipes stdin JSON into. This audit does not call or modify it, but the omp→ll event mapping it produces is the input contract a future omp adapter would satisfy against this same signature.

### Call Path

`<omp native event>` (enumerated by this audit; not implemented here) -> future omp adapter shim (FEAT-2261, out of scope for this issue) -> `main_hooks()` (`scripts/little_loops/hooks/__init__.py`) -> `_dispatch_table()[intent]` -> intent handler -> `LLHookResult` -> adapter relay (stdout/stderr/exit-code back to the host). Everything from "future omp adapter shim" onward already exists and is unmodified by this issue; this audit produces only the left-hand mapping (native omp event name -> ll intent name) that a future adapter would need to bridge into this existing pipeline.

### Decision Rules

N/A — no new decision logic. This issue documents an existing external surface (omp's native events) against an existing, unmodified dispatch table; it introduces no new gate, threshold, or classification rule.

## Implementation Steps

_Added by `/ll:refine-issue` — concrete steps grounded in actual file references._

1. **Enumerate omp's native hook events** (FEAT-1850's omp runner has landed). Inspect the oh-my-pi
   SDK/plugin surface for its lifecycle event names and advisory/blocking semantics,
   mirroring how `gemini-cli-surface.md` § Q2 enumerated Gemini's 11 events.
2. **Map omp events → the 7 ll intents** from
   `scripts/little_loops/hooks/__init__.py:_dispatch_table()`. For each ll intent,
   record the omp equivalent (or "none"), whether it is advisory-only vs. can block,
   and any matcher/scoping needed.
3. **Write `thoughts/research/omp-hook-event-parity.md`** following the
   `gemini-cli-surface.md` template (header block, event-inventory table, gaps list,
   `HostCapabilities` capability-map block).
4. **Add the omp column to `docs/reference/HOST_COMPATIBILITY.md` § Hook intents**
   using the cell convention above, plus the `[^omp]` footnote, the `## Adapter
   locations` row, and the `## Tracking issues` FEAT-2263 bullet. No unknown cells.
5. **Cross-check against `hooks/adapters/omp/README.md`** (created by FEAT-2261);
   reconcile any divergence with FEAT-2261 so all three artifacts agree.
6. **Verify**: zero unknown cells in the omp column; research doc, HOST_COMPATIBILITY
   matrix, and adapter README are mutually consistent.

## Reference

- FEAT-1715 (cancelled) — canonical Pi parity-audit framework to mirror.
- `thoughts/research/gemini-cli-surface.md` — analogous host-surface research doc.

## Impact

- **Effort**: S–M (research + matrix update).
- **Risk**: Low — research/docs; may surface upstream oh-my-pi gaps.
- **Breaking Change**: No.


## Blocks

- FEAT-2261

## Status

**Open** | Created: 2026-06-24 | Priority: P4

## Related Key Documentation

- `.claude/CLAUDE.md` — `hooks/adapters/` (the location FEAT-2261 will create for this audit's findings) is documented in CLAUDE.md's Key Directories as the per-host translation layer.
- `docs/reference/API.md` — the audit maps omp events against the documented `hooks` module's `LLHookEvent` intent set (`_dispatch_table()`, the canonical 7 ll intents).

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and FEAT-2797 both specify content requirements for the same `HOST_COMPATIBILITY.md` `[^omp]` footnote — this issue wants it to carry hook-intent tracking info (epic/research-spike/artifact path/gating statement); FEAT-2797 wants it to state why `json_schema`/`structured_output` are `✗` and describe the frontmatter `output:` path. The footnote is a single shared definition — whichever issue lands first must extend it, not overwrite it, to preserve both requirements.

## Verification Notes

### 2026-08-10 (`/ll:verify-issues`)

Verified 2026-08-10: core claim still true (`HOST_COMPATIBILITY.md`'s hook-intents table has no omp column, `hooks/adapters/omp/README.md` doesn't exist). However the "Dependency/Blocker" section's claim that `OmpRunner` is "not yet registered" in `_HOST_RUNNER_REGISTRY` is now FALSE — `OmpRunner` is registered (`host_runner.py:1561`) since its listed dependency FEAT-1850 landed (`status: done`). The blocker has cleared; update the Dependency/Blocker section to reflect this — issue is otherwise still open/valid.

### 2026-08-12 (`/ll:verify-issues`)

NEEDS_UPDATE. Corrected the body's "Dependency / Blocker" section, which
still asserted `OmpRunner` was "not yet registered" despite the 2026-08-10
note above flagging it as stale — `OmpRunner` is registered at
`host_runner.py:1763` (line drifted from the previously-cited 1561). Core
gap remains valid: `HOST_COMPATIBILITY.md` still has no omp column and
`hooks/adapters/omp/README.md` still doesn't exist.

### 2026-08-30 (`/ll:verify-issues`)

OUTDATED (line drift only). `_HOST_RUNNER_REGISTRY`'s `"omp": OmpRunner`
entry has moved again, from the previously-cited `host_runner.py:1763` to
`host_runner.py:1821` — line 1763 now falls inside `QwenRunner`'s
`describe_capabilities`. Corrected the citation in the "Dependency /
Blocker" section. All other claims re-verified and hold: `depends_on`
(FEAT-1850, FEAT-2797) both `Completed`; `HOST_COMPATIBILITY.md`'s Hook
intents table (line 67 header, rows 69-76) still has no omp column and no
`pre_compact_handoff` row; `hooks/adapters/omp/README.md` still doesn't
exist; the `[^omp]` footnote (`HOST_COMPATIBILITY.md:252-259`) still reads
exactly as quoted, with the FEAT-2797 nested sub-heading precedent intact;
`_dispatch_table()` (`hooks/__init__.py:137`) wires the 11 intents listed;
`LLHookEvent`/`LLHookResult` at `types.py:21`/`types.py:85` confirmed;
FEAT-2261's `blocked_by: FEAT-2263` backlink confirmed; decisions log has
no active required rules; `ll-verify-evidence` reports no unverifiable
quotes. Graph: provider=`fallback` freshness=`fresh`.

### 2026-08-30 (`/ll:verify-issues`, re-run post gap-analysis)

VALID. Re-verified after the same-day `/ll:refine-issue:gap-analysis` pass
added a further batch of Codebase Research Findings (the `OmpRunner` class
body / `[^omp]` footnote span / `## Tracking issues` bullet / `## Adapter
locations` block). Re-checked every citation: `OmpRunner` class body
(`host_runner.py:1219-1402`) confirmed to contain zero hook/lifecycle
references; `[^omp]` footnote verbatim span confirmed at
`HOST_COMPATIBILITY.md:252-276`, text matches exactly including the stale
sentence still to be corrected by this issue's implementation; `##
Tracking issues` EPIC-2258 bullet (`HOST_COMPATIBILITY.md:628-630`) matches
verbatim; `## Adapter locations` closing line matches verbatim;
`hooks/adapters/omp/README.md` still absent; Hook-intents table still has
no omp column, no `pre_compact_handoff` row. `depends_on` (FEAT-1850,
FEAT-2797) both `Completed`; FEAT-2261's `blocked_by: FEAT-2263` backlink
confirmed. Decisions log present (`.ll/decisions.yaml` +
`.ll/decisions.d`), no active required rules. `ll-verify-evidence` reports
`{"ok": true, "count": 0}` — no unverifiable quotes. No `## Proposed
Solution` section (Implementation Steps instead) — proposal-consequence
check (B6) not applicable. Graph: provider=`fallback` freshness=`fresh`.

## Session Log
- `/ll:manage-issue` - 2026-08-30T23:53:49 - `ba54f2e2-6e98-431f-bf68-ea4c8aaa638d.jsonl`
- `/ll:ready-issue` - 2026-08-30T23:43:24 - `c2b719f6-6761-466a-8368-ed0a8f5f9f6d.jsonl`
- `/ll:confidence-check` - 2026-08-30T23:41:44 - `1dad5b1b-28c3-41cc-b6d3-2053563af11c.jsonl`
- `/ll:verify-issues` - 2026-08-30T23:40:05 - `de1b1206-5734-458e-9d23-915431276d27.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-08-30T23:37:59 - `3771811d-1c8b-48c5-afb1-b85ef45d5e46.jsonl`
- `/ll:verify-issues` - 2026-08-30T23:31:11 - `c30dbd89-68a3-4415-a803-d2a8a807338e.jsonl`
- `/ll:refine-issue` - 2026-08-30T23:22:33 - `1cd156b9-8c64-4d8a-bedb-d8f8d7a0b76e.jsonl`
- `/ll:refine-issue` - 2026-08-30T17:28:31 - `1854d5ae-85d4-485b-ae33-828a3400cc7b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:59 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:25 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:44 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
- `/ll:refine-issue` - 2026-06-26T23:06:47 - `66288c91-3410-40d5-8af7-af4d0cb1a3f8.jsonl`
- `/ll:format-issue` - 2026-06-26T22:57:21 - `ae5ff08e-cca8-4e62-8e12-44cfb2069975.jsonl`
