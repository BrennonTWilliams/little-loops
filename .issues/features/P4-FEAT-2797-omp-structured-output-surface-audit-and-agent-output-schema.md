---
id: FEAT-2797
title: "omp structured-output surface \u2014 audit findings, matrix correction, and\
  \ agent `output:` schema wiring"
type: feature
status: done
priority: P4
discovered_date: 2026-07-25
discovered_by: capture-issue
completed_at: '2026-08-30T23:17:02Z'
parent: EPIC-2258
relates_to:
- FEAT-2787
- FEAT-2261
verify_verdict: VALID
labels:
- host-compat
- omp
- structured-output
- docs
- adapters
unproven_mechanism: true
decision_needed: false
learning_tests_required:
- oh-my-pi
confidence_score: 90
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
spike_needed: true
spike_attempted: true
spike_completed: true
---

# FEAT-2797: omp structured-output surface — audit findings, matrix correction, and agent `output:` schema wiring

## Summary

`HOST_COMPATIBILITY.md` reports `✗[^omp]` for `json_schema` and (by dataclass
default) `False` for `structured_output` on omp. Those cells were never
researched — `thoughts/research/omp-headless-flags.md`, the FEAT-1850 audit
artifact the whole omp flag surface was derived from, contains **zero**
mentions of schema or structured output, and `OmpRunner.capabilities`
(`host_runner.py:1197-1201`) sets only four flags, letting
`structured_output` fall through to the `HostCapabilities` default
(`host_runner.py:106`).

An upstream docs audit (2026-07-25, below) found the **cells are correct at
the CLI level** but for a reason the footnote never states, and that omp has
a real structured-output mechanism ll is not using — one that directly
affects FEAT-2787's `emit_agent`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- `host_runner.py:1197-1201`, the citation in this section's opening paragraph, has drifted again since the 2026-08-30 refine pass — the same `HostCapabilities(streaming=True, permission_skip=True, agent_select=False, tool_allowlist=True)` construction (still omitting `structured_output`) is now at `host_runner.py:1248-1253`.

## Audit findings (2026-07-25)

Verified against `can1357/oh-my-pi@main` via the GitHub contents API.

**1. No CLI-level schema flag exists.** `packages/coding-agent/src/cli/args.ts`
(420 lines — the complete flag surface) defines
`export type Mode = "text" | "json" | "rpc" | "acp" | "rpc-ui"` (line 18) and
has no schema/response-format flag of any kind. So:

- `json_schema: ✗` — **correct**, no flag to pass.
- `structured_output: False` — **correct**, since that flag narrowly means
  "honors the inline `--json-schema` the FSM evaluators append" (ENH-2627).
  Only the Anthropic `claude` CLI does.

**2. omp does have structured output, off the CLI path.** Two mechanisms:

- **Task-agent frontmatter `output:`** — a per-agent output schema, passed
  through as opaque schema data (`docs/task-agent-discovery.md:37`). Runtime
  precedence (ibid. 133-139): task item's explicit `outputSchema` → agent
  frontmatter `output` → parent session `outputSchema`. A per-item
  `schemaMode` overrides the session mode; default `permissive`.
- **SDK / RPC** — `createAgentSession({outputSchema, requireYieldTool})`
  (`docs/sdk.md:286`), and `--mode rpc`'s JSON-RPC protocol with a defined
  response schema (`docs/rpc.md:199-207`). Provider-side schema
  normalization is a first-class subsystem (`docs/ai-schema-normalize.md`,
  `@oh-my-pi/pi-ai/utils/schema`) with per-provider strict-mode adapters.

This is a file/tool-mediated path analogous to Codex's `--output-schema`, and
like Codex's, the FSM evaluators do not use it. It is **not** reachable by
adding a flag to `OmpRunner.build_blocking_json`.

**3. Cross-harness agent dirs are deliberately skipped.** `discoverAgents()`
merges OMP-native + Claude *plugin* roots, but explicitly skips
`.claude/agents`, `.codex/agents`, and `.gemini/agents` — their frontmatter
"is not the OMP task-agent contract"; `TASK_AGENT_CONFIG_SOURCE = ".omp"`
filters both dir lists (`docs/task-agent-discovery.md:60`).

## Current Behavior

The matrix asserts `json_schema: ✗` and `structured_output: False` for omp
with no supporting research, and the `[^omp]` footnote is silent on both.
A reader — human or automation reconciling the epic — concludes omp cannot do
structured output at all. `OmpRunner` inherits the `False` by default rather
than declaring it. FEAT-2787's `emit_agent` has no guidance on omp's agent
frontmatter contract and would plausibly emit Claude-shaped agents into a
directory omp deliberately ignores.

## Expected Behavior

The two cells stay `✗` but become *audited* claims with a stated reason, the
research artifact carries the structured-output findings, `OmpRunner` declares
the flag explicitly, and FEAT-2787 emits `.omp/agents/` files that populate
`output:` where a schema exists.

## Use Case

A maintainer closing EPIC-2258 needs the omp column to mean what it says. Two
of its cells currently encode an unexamined dataclass default as a researched
finding — the same class of error the epic's "no unknown cells" acceptance
criterion exists to prevent. Separately, whoever implements FEAT-2787 needs
omp's agent-frontmatter contract up front; discovering `.omp/`-only agent
discovery after writing the emitter means rewriting it.

## Acceptance Criteria

- `HOST_COMPATIBILITY.md`'s `[^omp]` footnote states *why* `json_schema` /
  `structured_output` are `✗` (no CLI flag exists; `--mode` is
  `text|json|rpc|acp|rpc-ui`) and records the agent-frontmatter `output:` /
  SDK `outputSchema` path as a real-but-unused capability, so the cells stop
  reading as "omp can't do structured output."
  > ⚠ Superseded — `structured_output`'s omp cell links `[^struct]`, not `[^omp]`
- `thoughts/research/omp-headless-flags.md` gains a "Structured output"
  section carrying these findings, so the next reader of the audit artifact
  isn't left with the same silent gap.
- `OmpRunner.capabilities` passes `structured_output=False` **explicitly**
  with a comment citing the absent flag, rather than inheriting the default —
  the value is unchanged; the point is that it becomes an audited claim.
- FEAT-2787's `emit_agent` writes to `.omp/agents/` (not a reused
  `.claude/agents` path) and populates frontmatter `output:` where the ll
  agent definition has a schema to express.
- A decision is recorded on whether to pursue the RPC/`outputSchema` path for
  FSM evaluators under omp, or to stay on prompt-and-parse with the BUG-2626
  `<StructuredOutput>` tag fallback. Recording "no, prompt-and-parse" with a
  rationale satisfies this.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- No existing usage site exercises the combination AC4 depends on — no `agents/*.md` file in this repo defines a schema-shaped frontmatter field, and no adapter's `emit_agent` (including omp's) has ever populated an output-schema frontmatter key from one. `_select_frontmatter_fields()` passes unrecognized keys through untouched regardless of `frontmatter_fields_read` contents, so the `omp.py` docstring's "carries `output:` through unmodified" claim is asserted but has never been exercised end-to-end — there is no direct precedent confirming the combination (a real ll agent schema flowing through `emit_agent` into `.omp/agents/<name>.md` frontmatter) works.
  > ⚠ Unproven mechanism — no ll agent definition has a schema to test with

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Sharper framing of the unproven-mechanism finding above: `_select_frontmatter_fields()` (`scripts/little_loops/adapters/core.py:119-182`) only branches on two literal keys — `"name"` and `"metadata.short-description"`. It never inspects `frontmatter_fields_read` to decide whether to pass a given key through; every key it does not explicitly recognize (including a hypothetical `output`) passes through untouched purely because the function never touches it. So `omp.py`'s docstring claim that `frontmatter_fields_read` is *why* `output:` "carries through unmodified" mischaracterizes the mechanism: the passthrough is a byproduct of the function's narrow (name/short-description-only) scope, not a dedicated `output`-handling path gated by that tuple's contents. This affects how Implementation Step 5's docstring correction should be worded — the fix is not just "add `output` to the tuple" (which would change nothing, since the tuple is never consulted for unrecognized keys) but correcting the causal claim itself.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis._

### Files to Modify

- `scripts/little_loops/host_runner.py` — `OmpRunner.capabilities` (the
  `HostCapabilities(...)` construction block, currently omitting
  `structured_output` entirely so it falls through to the dataclass default
  `False`) gains an explicit `structured_output=False,  # <comment>` line. The
  correct reasoning text already exists one method away, in
  `OmpRunner.describe_capabilities()`'s own `CapabilityEntry("structured_output",
  "unsupported", "omp has no inline --json-schema flag; FSM evaluators fall back
  to prompt-and-parse")` — reuse that wording rather than inventing new text.
  **No other host's `capabilities = HostCapabilities(...)` construction site
  sets any flag to `False` explicitly with a comment today** (every unsupported
  flag is achieved by omitting the kwarg) — this AC establishes a new
  convention at that specific call site, not an existing one to copy.
- `thoughts/research/omp-headless-flags.md` — gains a new "Structured output"
  section (the file's `## HostCapabilities values` code block currently lists
  only `streaming`/`permission_skip`/`agent_select`/`tool_allowlist`, no
  `structured_output` line, and the file has zero mentions of schema/structured
  output anywhere — confirmed by direct search).
- `docs/reference/HOST_COMPATIBILITY.md` — the `[^omp]` footnote (currently
  anchored only to the "Runner Capabilities" table's `Streaming` row) must be
  *extended* to also explain the `json_schema`/`structured_output` `✗` cells
  and the agent-frontmatter/`SDK outputSchema` path. Per this issue's own Scope
  Boundary note, FEAT-2263 wants to extend the same footnote for hook-intent
  tracking — whichever issue lands first must append to it, not overwrite.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` — a **second, independent** citation
  site beyond the `[^omp]` footnote: the "Adapter/Emitter Behavior" table's
  `omp` row prose (~line 349-354) already states "FEAT-2797 established that
  omp discovers agents via a native `.omp/agents/` scan dir ... with a
  frontmatter `output:` key for an optional per-agent output schema" —
  unqualified, asserting the same passthrough claim this issue's own
  Codebase Research Findings calls untested/unproven in `omp.py`'s docstring.
  If only the docstring and footnote are corrected, this paragraph is left
  contradicting them in the same file. [Agent 2 finding]

### Files Requiring Correction, Not Just Extension

- `scripts/little_loops/adapters/omp.py` — the module docstring's claim that
  `frontmatter_fields_read` "carries `output:` through unmodified when a source
  agent defines one" is not backed by any `output`-specific code path.
  `_select_frontmatter_fields()` (`scripts/little_loops/adapters/core.py:119-182`)
  only has explicit handling for `"name"` and `"metadata.short-description"`;
  any other key (including a hypothetical `output:`) passes through untouched
  regardless of whether it appears in `frontmatter_fields_read` at all. The
  docstring's causal claim is currently untested and inaccurate — no source
  agent file has an `output:` key, so this behavior has never actually been
  exercised.
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES["omp"].frontmatter_fields_read`
  is `("description", "name")` (line 120); it does not literally include
  `"output"`, contradicting the `omp.py` docstring's claim.

### No Existing Precedent for Schema-Driven Frontmatter Emission

- Zero `agents/*.md` files in this repo define a schema-shaped frontmatter
  field of any kind (searched directly — no hits).
- No other adapter's `emit_agent` (`codex.py`, `gemini.py`, `kimi.py`, `qwen.py`)
  populates an output-schema-like frontmatter field either — Codex's own
  `emit_agent` derives `sandbox_mode`/`mcp_servers` from `tools`, not a schema.
- Consequence: AC4 ("populates frontmatter `output:` where the ll agent
  definition has a schema to express") currently has no schema source to draw
  from anywhere in this codebase — no ll agent definition format has a schema
  field, so there is nothing yet for `emit_agent` to read and forward. The
  omp.py docstring's own parenthetical already concedes this ("none currently
  do; ll agent definitions have no schema to express yet").

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/verify_host_map.py` — reads `HOST_CAPABILITIES.get("omp")` (`agents`, `subagents`, `agent_output_format`) in its consistency check; if Implementation Step 5's "if desired" `frontmatter_fields_read` addition of `"output"` is taken, this is the mechanical check that would need a matching assertion. [Agent 1 finding]
- `scripts/little_loops/cli/issues/decisions.py:802,841,848-849` — has its own independent copy of the `getattr(invocation.capabilities, "structured_output", False)` gate, parallel to `_structured_output_args()` (`host_runner.py:2056`) but not calling it. omp's value is unchanged by this issue, so this call site's behavior is unaffected, but it is a second real consumer of the same capability contract this issue documents. [Agent 2 finding]
- `scripts/little_loops/advisor.py` — passes `json_schema=` into `resolve_host().build_blocking_json(...)`; for omp this flows into `build_blocking_json()`'s existing silent-discard path (`_ = json_schema`, `host_runner.py:1313-1333`) the issue's own research already cites. No change needed, but it is another omp-reachable consumer of the capability this issue makes explicit. [Agent 2 finding]

### BUG-2626 Tag-Fallback Coverage Is Partial

- `_extract_tagged_structured_output()` (`host_runner.py:2066-2111`) is invoked
  only from `run_blocking_json()`'s `JSONDecodeError` branch, which backs
  `evaluate_llm_structured()` (`fsm/evaluators.py`). `evaluate_blind_comparator`
  and `evaluate_contract` build their own `subprocess.run` calls and parse with
  a bare `json.loads()` — no tag-recovery fallback at those two sites. Relevant
  context for AC5's "stay on prompt-and-parse" framing: the fallback safety net
  is narrower than "every FSM evaluator," should that matter to the recorded
  rationale.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- `thoughts/research/omp-headless-flags.md` — cited by AC2 as the file that "gains a new Structured output section," and referenced elsewhere in this repo as an existing FEAT-1850 audit artifact (`host_runner.py:1222`, `scripts/tests/test_host_runner.py:1433`, `docs/reference/HOST_COMPATIBILITY.md:259`, `docs/reference/API.md:9856`, plus prose in FEAT-2262/FEAT-2787/FEAT-3103/FEAT-2263) — does not exist anywhere in this repository. `git log --all -- thoughts/research/omp-headless-flags.md` returns zero commits, and the path is absent from the working tree. FEAT-1850, whose Implementation Steps directed "record findings in `thoughts/research/omp-headless-flags.md`," is marked `done`. AC2 as written ("gains a ... section") presumes an existing file to extend; the actual gap is that the file was never created at all, so satisfying AC2 means authoring the whole artifact, not adding a section to one.
- `scripts/little_loops/host_runner.py` — `build_blocking_json()` (lines 1313-1333) accepts a `json_schema` parameter and silently discards it (`_ = json_schema`, line 1327, with an inline comment) for any host lacking `structured_output`. This differs from `build_streaming()` (lines 1273-1288), which raises `CapabilityNotSupported` for unsupported `agent`/`workspace_root` capabilities rather than silently dropping them. Relevant to this issue's "make the False explicit" framing: the capability is already silently un-enforced at the call site regardless of whether `OmpRunner.capabilities` declares `structured_output` explicitly or by omission.

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- `thoughts/research/omp-headless-flags.md` has no local template of its own (it does not exist — see the earlier finding under Acceptance Criteria), but `thoughts/research/codex-command-discovery.md` and `thoughts/research/omp-skill-command-surface.md` establish this repo's audit-artifact shape: a `Status`/`Last verified`/`Research issue`/`<Host> version` header block, a `## Sources` list of exact files/commands consulted, topic-specific findings sections, and a closing `## Capability map` section showing a `HostCapabilities(...)` Python snippet with inline comments on deferred flags. Implementation Step 2's new "Structured output" section can follow this existing shape rather than inventing one.
- The `workspace_sandboxed` field on `HostCapabilities` (`host_runner.py`, adjacent to `structured_output`) carries its own comment stating the default is left implicit at all six per-host construction sites, "mirroring how structured_output (ENH-2627) was added" — direct precedent that documenting-at-the-field-definition, not at each construction site, has been this codebase's convention up to now. Confirms (rather than merely asserts) this issue's own "Files to Modify" framing that an explicit `structured_output=False,  # comment` at `OmpRunner`'s construction site is a genuinely new pattern, not an extension of an existing one. A repo-wide regex search (`=False,\s*#|=False\)\s*#`) across every `HostCapabilities(...)` construction site in `host_runner.py` confirms zero existing matches.
- No existing adapter module docstring under `scripts/little_loops/adapters/` uses "untested/unproven/never exercised"-style correction language (searched repo-wide, zero hits). The closest in-codebase precedent for correcting a stale claim next to the corrected code is a `# BUG-2759: corrected to agree with structured_output — ...` comment directly above the corrected `CapabilityEntry(...)` call in `ClaudeCodeRunner.describe_capabilities()` (`host_runner.py:504-514`), which names the prior wrong claim, states the correction, and keeps a caveat about what remains true — a usable shape for Implementation Step 5's `omp.py` docstring correction, though it corrects a runtime string literal there, not a module docstring block.
- The `[^schema]` footnote in `HOST_COMPATIBILITY.md` already documents its own in-place correction inline ("(BUG-2759 corrected this row to agree with `structured_output` below)") rather than spawning a new footnote. Relevant precedent for the Wiring Phase's `[^struct]` vs `[^omp]` footnote-reference-mismatch bullet: resolving it can follow this same self-annotating shape instead of repointing the cell.

## Proposed Solution

_Added by `/ll:refine-issue` — decision point for AC5, formatted per the
Decision-Point Formatting convention._

**Option A**: Wire the RPC/`outputSchema` path — implement `--mode rpc`'s
`createAgentSession({outputSchema, requireYieldTool})` (or the per-item
`schemaMode` override) so FSM evaluators get native structured output on omp,
closing the gap `structured_output: False` currently encodes as "omp can't do
it" when it in fact can, just not via the `--mode json` CLI path evaluators use
today. This is a structurally new mechanism — no other host's `structured_output`
support works via an RPC protocol rather than an inline CLI flag — so it would
need its own design, not a fold-in to `OmpRunner.build_blocking_json`.

**Option B**: Stay on prompt-and-parse — keep `structured_output=False` for
omp's CLI path (`--mode json`), rely on prompt text plus the existing BUG-2626
`<StructuredOutput>` tag-fallback (`_extract_tagged_structured_output`,
`host_runner.py:2066`) as the safety net, same as every non-Anthropic/non-qwen
host today. Zero new runner code.

> **Selected:** Option B — stays on prompt-and-parse, reusing the existing,
> already-tested BUG-2626 tag fallback and `HostCapabilities.structured_output`
> convention with zero new runner code (score 12/12 vs. Option A's 2/12; see
> Decision Rationale below).

**Recommended**: Option B for now — this issue's own Impact section already
scopes the RPC-path work as "should be its own issue," the fallback in Option B
already exists and is exercised for `evaluate_llm_structured` (see the coverage
caveat above), and no host besides `claude`/`qwen` gets inline schema support
today — omp would be the first to get it through a structurally different
mechanism (RPC vs. CLI flag), which warrants dedicated design rather than a
correction-scoped issue like this one.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-30.

**Selected**: Option B — Stay on prompt-and-parse

**Reasoning**: Option B changes zero runtime behavior — `OmpRunner().capabilities.structured_output is False` is already pinned by `test_host_runner.py:1752` — and reuses `_extract_tagged_structured_output`, `run_blocking_json`, and `_structured_output_args` verbatim, matching the "omit the kwarg" convention already followed by 4 of 6 registered hosts (codex, gemini, omp, kimi). Option A would require a session-based RPC client with no precedent in `HostRunner`/`HostInvocation` (both are structurally one-shot-argv, per `host_runner.py:155-173` and `2120-2134`), and would touch three FSM evaluators, two of which (`evaluate_blind_comparator`, `evaluate_contract`) don't even share the `run_blocking_json()` helper today — high complexity and risk for a mechanism the issue's own Impact section already scopes as "should be its own issue."

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A (RPC/outputSchema) | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |
| Option B (prompt-and-parse) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- The rejected RPC approach's only reusable precedent is `mcp_call.py`'s JSON-RPC-over-subprocess client (transport shell only, MCP-protocol-specific, not omp's RPC schema); `HostRunner`/`HostInvocation` has no session concept anywhere in the codebase.
- The selected prompt-and-parse approach's `_extract_tagged_structured_output` (`host_runner.py:2066-2111`) is an already-implemented, already-tested (`test_host_runner.py:2003-2019`) fallback that 4 of 6 hosts already rely on via the identical construction-site convention this AC makes explicit for omp.

## Program Design

_Added by `/ll:refine-issue` — populated from analyzer findings._

### Types

N/A — no new data shape; `HostCapabilities.structured_output` already exists as
a `bool` field (`host_runner.py`), and this issue only makes an existing
implicit `False` explicit at one construction site.

### Signatures

- `HostCapabilities(..., structured_output: bool = False, ...)` (`host_runner.py`)
  — existing dataclass; `OmpRunner.capabilities` gains an explicit
  `structured_output=False` argument to this existing constructor, no signature
  change.
- `OmpRunner.describe_capabilities()` (`host_runner.py`, ~line 1351) — existing
  method already correctly reports the `structured_output` reason string; no
  change needed, only reuse of its wording at the `capabilities=` site.

### Call Path

`OmpRunner.capabilities` (a class attribute built at class-definition time from
`HostCapabilities(...)`) -> read by `_structured_output_args()` (`host_runner.py:2045`)
via `getattr(invocation.capabilities, "structured_output", False)` -> gates
whether `run_blocking_json()` appends `--json-schema` before invoking `omp`.
Making the `False` explicit at the `HostCapabilities(...)` call site changes
no runtime behavior in this path — the value read is identical either way.

### Decision Rules

- AC5's decision point (RPC/`outputSchema` path — ⚠ Superseded, rejected and
  not implemented — vs. prompt-and-parse) is resolved: Option B
  (prompt-and-parse) selected — see the `### Decision Rationale` subsection
  under `## Proposed Solution` above.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_FILES_MUST_EXIST` (line 397+) and `DOC_STRINGS_PRESENT` (line 27+) have no entry for `thoughts/research/omp-headless-flags.md`, despite the file being cited by `host_runner.py:1222`, `test_host_runner.py:1433`, and 6+ `.issues/` files. Add an existence entry (following the `("thoughts/research/codex-command-discovery.md", "FEAT-1483")` pattern at line 412) and a content-citation entry for the new "Structured output" section (following the 3-tuple pattern at lines 181-183), so this file's creation (Implementation Step 2) is test-gated the same way every other `thoughts/research/*.md` audit artifact is. [Agent 3 finding]

## Implementation Steps

_Added by `/ll:refine-issue` — outcome-phrased, concrete references._

1. `OmpRunner.capabilities` (`host_runner.py`) explicitly states
   `structured_output=False` with a comment reusing the reasoning already
   present in `OmpRunner.describe_capabilities()`.
2. `thoughts/research/omp-headless-flags.md` carries a "Structured output"
   section stating the audit findings above (no CLI schema flag; the
   agent-frontmatter/SDK `outputSchema`/`--mode rpc` path — ⚠ Superseded,
   rejected and not implemented — exists but is unused).
3. `docs/reference/HOST_COMPATIBILITY.md`'s `[^omp]` footnote is extended (not
   overwritten — coordinate with FEAT-2263's own edit to the same footnote) to
   explain the `json_schema`/`structured_output` `✗` cells and name the unused
   `output:`/`outputSchema` path.
4. The RPC-vs-prompt-and-parse decision is applied: Option B (prompt-and-parse)
   was selected — no RPC/`outputSchema` implementation work (rejected — not
   implemented) is in scope for this issue; `decision_needed` is set to `false`.
5. Given the Unproven Mechanism finding above (no ll agent definition has a
   schema to test AC4's `output:` passthrough against), AC4 should be
   satisfied by making the passthrough mechanism correct and documented for
   when a schema does appear (correcting `omp.py`'s docstring and, if desired,
   adding `"output"` to `HOST_CAPABILITIES["omp"].frontmatter_fields_read`),
   rather than by fabricating a schema to test against.
6. Verify: `python -m pytest scripts/tests/test_host_runner.py scripts/tests/test_adapters.py -v` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/HOST_COMPATIBILITY.md` — correct the "Adapter/Emitter Behavior" table's `omp` row prose (~line 349-354), which independently asserts the unqualified `output:` passthrough claim, alongside the `[^omp]` footnote and `omp.py` docstring fixes — otherwise the doc contradicts itself in two places instead of one.
- Resolve the footnote-reference mismatch: the `structured_output` row's omp cell (`HOST_COMPATIBILITY.md:246`) links `[^struct]` (a footnote shared across codex/gemini/omp/kimi), not `[^omp]` — decide whether to add omp-specific reasoning to `[^struct]` or repoint the cell to `[^omp]`, so AC1's stated footnote actually carries the reasoning for both cells.
- Add `scripts/tests/test_wiring_skills_and_commands.py` entries to `DOC_FILES_MUST_EXIST` and `DOC_STRINGS_PRESENT` gating `thoughts/research/omp-headless-flags.md`'s existence and its new "Structured output" section content, once the file is authored (Implementation Step 2).
- No change required at `scripts/little_loops/cli/verify_host_map.py`, `scripts/little_loops/cli/issues/decisions.py`, or `scripts/little_loops/advisor.py` — noted in Dependent Files as consumers of the same capability contract, but this issue changes no runtime value they read.

## Impact

- **Priority**: P4 — same tier as the parent epic.
- **Effort**: Small for the doc/capability corrections; the RPC-path decision
  is a scoping call, and implementing it (if chosen) should be its own issue.
- **Risk**: Low — corrections are additive; no runner behavior changes.
- **Breaking Change**: No.

## Notes

- Blocked on nothing. Unlike FEAT-2261 / FEAT-2263, this is docs-level
  verification and does not need a working `omp` binary — relevant because
  `.ll/learning-tests/oh-my-pi.md` records `omp --version` and `omp -p` as
  **fail** in this environment (Bun 1.3.9 < the required 1.3.14).
- `docs/hooks.md` upstream documents omp's event surfaces (session,
  agent/context, tool pre/post) plus mutation semantics and ordering —
  direct input for FEAT-2261 / FEAT-2263, noted here so the pointer isn't
  lost.

## Status

**Open** | Created: 2026-07-25 | Priority: P4

## Related Key Documentation

- `.claude/CLAUDE.md` — the Host CLI Abstraction section governs `host_runner.py`/`OmpRunner.capabilities`, which this issue changes to explicitly declare `structured_output=False`.
- `docs/reference/API.md` — directly touches the documented `host_runner` module (`OmpRunner.capabilities`) and the adapters' `emit_agent` surface.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and FEAT-2263 both specify content requirements for the same `HOST_COMPATIBILITY.md` `[^omp]` footnote — FEAT-2263 wants it to carry hook-intent tracking info (epic/research-spike/artifact path/gating statement); this issue wants it to state why `json_schema`/`structured_output` are `✗` and describe the frontmatter `output:` path. The footnote is a single shared definition — whichever issue lands first must extend it, not overwrite it, to preserve both requirements.

## Verification Notes

### 2026-08-10 (`/ll:verify-issues`)

Verified 2026-08-10: this issue's core acceptance criterion (`emit_agent` writing to `.omp/agents/` instead of `.claude/agents`) is ALREADY IMPLEMENTED — see `scripts/little_loops/adapters/omp.py`, commit `efc6a6c0`, part of the now-done FEAT-3104/FEAT-2787 work. Cited line `host_runner.py:1071-1075` is stale (content now at 1196-1201, unchanged). Remaining real gaps: the `[^omp]` footnote still doesn't explain why `json_schema`/`structured_output` show ✗; `omp-headless-flags.md` still has no "Structured output" section; `OmpRunner.capabilities` still omits an explicit `structured_output=False`; and omp's `frontmatter_fields_read` tuple is `('description','name')` which doesn't literally include `'output'`, contradicting the `omp.py` docstring's claim that `output:` is carried through unmodified — worth a follow-up bug/enh split off from this issue's narrower remaining scope.

### 2026-08-12 (`/ll:verify-issues`)

NEEDS_UPDATE. Confirmed the cited `host_runner.py:1071-1075` reference had
drifted further, to `1197-1201` (same `HostCapabilities(...)` block,
content unchanged) — corrected in the Summary section above. Remaining
gaps from the 2026-08-10 pass are unchanged and still outstanding.

- 2026-08-16: Remaining gaps still live (no explanation of why `json_schema`/`structured_output` are ✗ for omp in HOST_COMPATIBILITY.md, no structured-output mention in `thoughts/research/omp-headless-flags.md`). Per this issue's own 2026-08-10 note, the `emit_agent` → `.omp/agents/` acceptance criterion is already implemented (`scripts/little_loops/adapters/omp.py`) — that AC should be checked off and the issue's scope trimmed to the remaining unimplemented ACs. Verdict: NEEDS_UPDATE.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-30_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE (capped from raw 71 — see below)

### Outcome Risk Factors
- `unproven_mechanism: true` with no `spike_attempted`/`spike_completed` flag hard-caps outcome confidence at `outcome_threshold − 1` (64, per this project's `commands.confidence_gate.outcome_threshold: 65`) regardless of the raw Criteria A-D sum (71) — AC4's `output:` passthrough has no schema source anywhere in the repo to test against (Implementation Step 5 already scopes this as documentation-only rather than fabricating a test schema); this is expected for the acknowledged unproven mechanism, not a new gap.
- `unapplied_decision` fired 3 times (`format-check`), capping Criterion C (Ambiguity) at 10: the rejected Option A identifiers `outputSchema` / `--mode rpc` still appear, unmarked, in the Program Design and Implementation Steps sections — even though contextually they read as explanatory ("this path exists but is out of scope"), not as live directives. Worth a pass to add explicit "(rejected — not implemented)" qualifiers at those two mentions so the mechanical gate clears, though it does not block PROCEED here.
- `HOST_COMPATIBILITY.md`'s footnote/table corrections (2 of the ~6 change sites) have no automated content assertion — only the new `omp-headless-flags.md` research doc gets `DOC_FILES_MUST_EXIST`/`DOC_STRINGS_PRESENT` coverage per the Wiring Phase notes — so a wording regression there wouldn't be caught by `pytest`.

## Spike Results

_Added by `/ll:spike` on 2026-08-30_

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|----------------------------------|-----------|--------|
| AC4's `output:` passthrough has no schema source to test against — no precedent that a schema-shaped `output:` frontmatter key survives `_select_frontmatter_fields`/`OmpEmitter.emit_agent` unmodified | `TestOutputFrontmatterPassthrough::test_output_block_survives_name_injection`, `::test_output_block_survives_short_description_strip`, `::test_output_block_survives_metadata_block_adjacency`, `::test_output_block_survives_metadata_without_short_description`, `::test_emit_agent_round_trip_preserves_schema_value` | ✓ pass — the `output:` value survives byte-for-byte-equivalent (re-parses identically) through every branch omp's construction site actually takes, including the real end-to-end `OmpEmitter.emit_agent()` write |

**Incidental finding (not a retired risk, not fixed here)**: when a
`metadata:` block (holding `short-description:`) sits directly adjacent to
another frontmatter key with no blank line between them — as it would if an
`output:` block immediately followed — `_select_frontmatter_fields`'s
`metadata:` header-removal regex (`^metadata:[ \t]*\n(?=\n|\Z)`) doesn't
match, leaving a dangling `metadata:` key (parses as `None`). The `output:`
value itself is unaffected. Production code is read-only in this skill;
recorded here rather than fixed. Worth a small follow-up BUG if a future
consumer of `metadata:` cares about the dangling key.

**Spike location**: `scripts/tests/spike/omp_agent_output_frontmatter_passthrough/`
**Verification**: 6 tests pass across 2 commands (spike suite + `test_adapters.py` regression, 223 tests).
**Promotion**: no new production code to promote — this spike exercises existing production code. On acceptance, promote `test_output_passthrough.py`'s cases into `scripts/tests/test_adapters.py` as permanent regression coverage (same synthetic fixture, since no real ll agent output schema exists yet) in a separate PR.

## Session Log
- `/ll:manage-issue` - 2026-08-30T23:16:53 - `d705b2ec-0d4e-4122-9ccc-d551a82dc791.jsonl`
- `/ll:ready-issue` - 2026-08-30T23:03:41 - `575fc1f0-6d9d-403c-8a5e-95c1f8cf0946.jsonl`
- `/ll:confidence-check` - 2026-08-30T23:00:36 - `38cd9a3c-c1f2-40bf-b9ca-d438cb22f2e9.jsonl`
- `/ll:spike` - 2026-08-30T22:58:26 - `0a859a28-07e4-4c21-8f00-7cf2d8e0d8da.jsonl`
- `/ll:confidence-check` - 2026-08-30T22:54:13 - `8703b9e2-9d3e-496a-bdae-a425ce8a0dd5.jsonl`
- `/ll:verify-issues` - 2026-08-30T22:51:41 - `5ad58b30-e1f7-455b-9895-5130494ba40f.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-08-30T22:49:13 - `92eb8750-9b69-44a7-a847-c81d6833d752.jsonl`
- `/ll:verify-issues` - 2026-08-30T22:43:45 - `85bcd0bf-1cc5-4008-bd57-e4cf7c2b68ae.jsonl`
- `/ll:wire-issue` - 2026-08-30T22:40:54 - `c5e1bfd9-0a2d-4918-a20c-1e018efa23ec.jsonl`
- `/ll:refine-issue` - 2026-08-30T22:32:47 - `7c3d278b-977c-4cf7-8462-b4736e6d248d.jsonl`
- `/ll:decide-issue` - 2026-08-30T17:40:37 - `7e67aae2-54d5-4a0a-8c77-37f505746bdf.jsonl`
- `/ll:refine-issue` - 2026-08-30T17:33:54 - `1854d5ae-85d4-485b-ae33-828a3400cc7b.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:24 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:25 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:45 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
