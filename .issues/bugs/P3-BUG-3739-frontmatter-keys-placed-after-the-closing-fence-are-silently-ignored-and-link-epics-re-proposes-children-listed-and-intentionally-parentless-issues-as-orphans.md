---
id: BUG-3739
type: BUG
title: Frontmatter keys placed after the closing fence are silently ignored, and link-epics
  re-proposes Children-listed and intentionally-parentless issues as orphans
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:54:03Z'
completed_at: '2026-10-06T01:39:48Z'
labels:
- issues
- link-epics
- frontmatter
relates_to:
- BUG-3738
verify_verdict: VALID
reconcile_attempted: true
confidence_score: 85
outcome_confidence: 70
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-3739: Frontmatter keys placed after the closing fence are silently ignored, and link-epics re-proposes Children-listed and intentionally-parentless issues as orphans

## Summary

Parenting metadata accidentally written just after a frontmatter closing fence is ignored by readers and has no format diagnostic. Independently, `link-epics` re-proposes issues that have a valid intentional-parentless marker or already appear in an EPIC's Children section without a back-reference.

Add a bounded placement check with conservative single-issue repair, and classify candidates before either assignment scoring or synthesis. Preserve the parser's existing fence boundary: body text must not become metadata merely because a reader encounters a known key.

## Current Behavior

Verified on branch `main` on 2026-10-05:

- `parse_frontmatter()` correctly ignores the following misplaced `parent`/`epic` lines:

```markdown
---
id: FEAT-1
goals: [3, 7]
---
parent: EPIC-1
epic: EPIC-1

# FEAT-1: Child title
```

- `check_format_gaps()` has no post-fence-key diagnostic. The lint surface is `ll-issues format-check`.
- `is_orphan()` checks only BUG/FEAT/ENH type and unset parent/epic. `IssueInfo` has no standalone/reason fields, and the command does not read these markers or EPIC bodies.
- `find_issues()`'s default filter excludes done/cancelled/deferred EPICs. Their Children documentation is therefore unavailable to the current command.
- The existing `_parse_children_body()` recognizes bullet and per-child heading entries but is not fence-aware and lacks an ID end-boundary. Reproductions returned `FEAT-1` from both a fenced example and `FEAT-1suffix`; blindly reusing it would hide genuine orphans.
- The marker vocabulary (now a single key, `parentless_reason`) is new to this repository. Its semantics and output contract must be specified rather than assumed.

## Expected Behavior

- `format-check` reports the key, physical line, and file for misplaced metadata in the bounded post-fence prefix. Safe repairs require `--fix --apply`; preview performs no write, and unsafe cases remain reported.
- Candidates with misplaced parenting metadata or intentional-parentless markers never reach assign/synthesize/deep scoring. Malformed candidates are reported for repair before any new parent is written.
- Candidates genuinely documented as children of a non-terminal EPIC (`open`, `in_progress`, `blocked`, `deferred`) are excluded and reported as body-without-backref drift, including every claiming EPIC. Claims by terminal EPICs (`done`, `cancelled`) are reported as informational drift but do not exclude: an open orphan left in a dead EPIC still needs a home. No parent is inferred or written from body documentation alone.
- Both JSON modes preserve their existing keys and expose deterministic skip counts and actionable drift details. Text mode reports the same facts.

## Steps to Reproduce

1. Create an open child whose `parent: EPIC-1` line is immediately after its frontmatter closing fence, as in the example above.
2. List that child as `- **FEAT-1** — Child title` in EPIC-1's `## Children`.
3. Run `ll-issues format-check FEAT-1`: there is no post-fence-key finding.
4. Run `ll-issues link-epics --mode assign --threshold 0 --json`: the child is proposed again.
5. Create a different orphan with `parentless_reason: Deliberately standalone` inside valid frontmatter: it is still proposed.
6. Repeat with a fenced child example instead of a real entry, and with a child listed only by a cancelled EPIC, to distinguish intended exclusions from false ones.

## Root Cause

- **File**: `scripts/little_loops/frontmatter.py`; **anchors**: `_iter_frontmatter_blocks`, `parse_frontmatter`. Reads are intentionally limited to fenced mappings. A misplaced line belongs to no mapping; changing this read contract would promote legitimate prose into metadata.
- **File**: `scripts/little_loops/issue_parser.py`; **anchor**: `check_format_gaps`. No pure-text structural detector covers the post-fence prefix.
- **File**: `scripts/little_loops/cli/issues/link_epics.py`; **anchors**: `is_orphan`, `cmd_link_epics`. Candidate construction does not check explicit opt-outs or documented membership.
- **File**: `scripts/little_loops/cli/issues/epic_consistency.py`; **anchors**: `find_children_section`, `iter_child_entries`, `_parse_children_body`. The shared recognizer (landed by BUG-3738 in `cda52e0eb`) must be verified for fence/whole-ID safety before becoming an exclusion source.

## Proposed Solution

Add `post_fence_keys: list[str]` to `FormatGaps`, its predicates/serialization, and text rendering. Run the raw-text detector before template/type early returns, like the existing invisible-character and multiple-frontmatter checks. Keep it pure text; no subprocess, model, or external schema is needed.

Register a per-issue repair in `_REPAIR_DISPATCH`, excluded from `_SWEEP_SAFE_REPAIRS`. The repair moves raw source entries without YAML-dumping unrelated content. Detection and repair share entry spans; output messages are for humans, not coordinates to be reparsed by the fixer. Unsafe shapes stay blocking and unchanged by this repair.

Keep `is_orphan()` as the structural type/relationship predicate and add command-local classification using raw frontmatter plus a reverse index of documented children. This avoids adding unrelated marker fields and serialization plumbing to the shared `IssueInfo` model. Preserve the present eligible issue/assignment-target statuses; load EPICs separately with all six supported statuses only to build the exclusion index.

### Behavior Parity

Keep `parse_frontmatter`, general orphan status filtering, scoring thresholds, `EpicProposal` fields, synthesis/deep behavior for eligible candidates, and unsupported synthesis apply behavior unchanged. The new exclusions apply before any scoring or model invocation. No EPIC body, back-reference, or marker is automatically invented by `link-epics`.

## Program Design

### Types

Proposed additions for implementation:

```python
# FormatGaps field, blocking by default:
post_fence_keys: list[str]

@dataclass(frozen=True)
class PostFenceEntry:
    key: str
    line: int
    source_span: tuple[int, int]
    # The complete raw entry and its repair eligibility are derived from spans.

@dataclass
class OrphanClassification:
    candidates: list[IssueInfo]
    malformed_ids: set[str]
    intentional_ids: set[str]
    # Every documented claim retains the EPIC ID and status.
    children_claims: dict[str, list[tuple[str, str]]]

```

### Signatures

Proposed helpers (documentation notation); shared IssueInfo serialization stays unchanged:

```python
intentional_parentless(metadata: Mapping[str, Any]) -> bool
classify_orphans(candidates: list[IssueInfo], epics_all_statuses: list[IssueInfo]) -> OrphanClassification
```

### Call Path

`main_issues` → `cmd_format_check` → `check_format_gaps` → raw entry detector → `FormatGaps.post_fence_keys` → `_apply_fix_dispatch` → guarded raw-entry repair → post-fix recheck.

`main_issues` → `cmd_link_epics` → `find_issues` → `is_orphan` → classification with parsed marker metadata and all-status EPIC child index → assign/synthesize/deep → existing result keys plus exclusion report.

### Detection and Repair Rules

1. **Known-key scope**: use an explicit constant containing `parent`, `epic`, `parent_issue`, and `parentless_reason`. This first fix targets parenting metadata; it does not claim to detect every YAML key or establish a full issue schema. `parent_issue` remains deprecated and its existing diagnostic may also fire after repair.
2. **Prefix boundary**: inspect after the last header frontmatter block recognized by the existing parser, outside all block spans and code fences. Allow at most one blank line before the first key, then require contiguous unindented `known_key:` entries. Stop at the first blank line after keys, heading, opening fence, unknown-key/prose line, or other unsupported top-level content. A block ending at EOF has no prefix. Never report lines consumed by another valid frontmatter block, scan arbitrary body lines, or skip prose to resume later. Keys are exact lowercase names; `Parent: ...` prose does not match.
3. **Complete entries**: detect scalar keys and capture any associated indented continuation as part of that entry. A block-scalar, wrapped quoted value, list, mapping, anchor/alias, malformed value, or dangling continuation is reportable but ineligible for automatic movement. Never move only the `key:` line of a multiline value. Report key/line plus the manual remedy; do not echo private reason text into diagnostics.
4. **Repairable run**: require one well-formed frontmatter mapping, distinct misplaced keys, single-line scalar values, and no duplicate/conflicting keys inside the block. On any unsafe entry, repeated key, existing-key collision (including explicit null), multi-block input, or a following `---` marker, this repair leaves the whole file unchanged and the gap remains. An identical existing value is also a collision; automatic deduplication is not part of this fix. A following marker could be an incomplete second block or thematic rule, so do not infer its intended role.
5. **Successful repair**: insert the original raw key lines immediately before the closing fence and remove their original spans. Preserve comments/quotes on those lines, all unrelated bytes, LF/CRLF, final-newline state, and the existing file mode. Parse the candidate mapping before writing to confirm the move is valid and no pre-existing value changes. Use a preserving atomic write only when text changes.
6. **CLI policy**: `--fix` previews, `--fix --apply` repairs a single resolved issue, and `--all --fix --apply` skips this repair. Recheck after an applied fix; remaining unsafe gaps produce the existing nonzero format-check result. Other registered fixers retain their own behavior.

### Marker Rules

- **One convention**: a structural orphan is intentional when `parentless_reason` is a non-empty scalar string (after trimming). The key doubles as the opt-out and its justification, so there is no separate boolean to disagree with it. Empty, null, `~`, whitespace-only, list, and mapping values do not opt out; a non-scalar value emits a key-only warning on stderr. There is no precedence table.
- The earlier `standalone` / `standalone_reason` conventions are dropped: the 3,644-file corpus scan found no existing markers, so there is no compatibility need, and each extra spelling adds a conflict surface. Adding another spelling later is a compatible, separate change.
- Only correctly placed metadata affects readers. Detection does not make post-fence keys effective; applying the safe repair is what makes them visible.

### Candidate Exclusion Rules

Classify all structurally eligible candidates before thresholding/scoring. A candidate with a `post_fence_keys` finding is excluded as `malformed_metadata`, even if its values cannot be repaired automatically. Otherwise explicit opt-out takes precedence over documented membership. Give each excluded candidate one primary reason in the order **malformed metadata → intentional → Children-listed**, so the three counters are disjoint. Children-listed is a primary reason only when at least one claimant is non-terminal; a candidate claimed solely by `done`/`cancelled` EPICs is not excluded and stays proposable (its claims appear as informational drift). Preserve any secondary EPIC claims in the drift details; counts are not inferred from the number of detail rows.

Use the shared pure entry detector directly rather than calling full `check_format_gaps` per candidate. It must not involve unrelated design/reference gates or subprocesses. A malformed candidate's existing body/metadata is never changed by link-epics; repair it first with format-check.

### Children Recognition and Status Rules

- Build `child_id → sorted unique (EPIC ID, status)` claims from EPICs with statuses `open`, `in_progress`, `blocked`, `deferred`, `done`, or `cancelled`. Active candidates and assignment targets still use the existing default status filter. A claim from a **non-terminal** EPIC (`open`, `in_progress`, `blocked`, `deferred`) excludes the candidate. A claim from a **terminal** EPIC (`done`, `cancelled`) is reported as informational drift and does **not** exclude: the candidate stays proposable, and if it is later assigned elsewhere the stale listing remains as category-(b) drift on the terminal EPIC (informational; link-epics never edits it). Membership is never silently discarded or automatically adopted.
- Select the first non-fenced exact Children H2, permitting horizontal whitespace only, and stop at the next non-fenced H1/H2. Aliases/suffixed headings are outside this fix. Align this section rule with BUG-3738 without requiring that issue's writer to exist first.
- Recognize non-fenced whole BUG/FEAT/ENH IDs in optional-bold `-`/`*` child bullets or per-child H3–H6 headings. Retain the existing parser's indented-bullet support. Ignore EPIC advisory IDs, prose mentions, references in other sections, fenced examples, and malformed/prefix tokens such as `FEAT-1suffix`.
- **Shared recognizer (coordinate with BUG-3738).** The section selection, entry recognition, fence handling, and whole-ID matching are one pure grammar that BUG-3738's writer also needs; do not implement it twice. Whichever issue lands first creates it in `epic_consistency.py` as public `find_children_section(content) -> tuple[int, int] | None` and `iter_child_entries(section_text) -> list[ChildEntry]` (ID, kind, source span), and repoints `_section_bounds`/`_parse_children_body` at them; the other adopts them. Run consistency-reader regressions when changing shared recognition. The consistency fixer's placeholder/EOF write policy is separate work. Land the two issues serially, not under parallel workers: both edit `link_epics.py`, `epic_consistency.py`, `docs/reference/CLI.md`, `COMMANDS.md`, and `skills/link-epics/SKILL.md`.
- An orphan claimed by several EPICs is excluded once (when any claimant is non-terminal) and reported with every claimant and its status; link-epics does not choose an owner or write a back-reference. Secondary claims remain visible even when malformed metadata or intentional status is the primary exclusion. Exact issue IDs remain distinct; do not normalize padded IDs into another issue.
- Unreadable candidate/EPIC files must surface a path-specific nonzero command error; do not interpret a failed read as an empty marker/index and apply proposals based on incomplete evidence.

### Output Contract

Keep the original `proposals`/`applied` or `clusters`/`applied` keys and any existing conditional `deep` key. Both modes always add these report keys, with zero/empty defaults:

```json
{
  "skipped_malformed_metadata": 0,
  "skipped_intentional": 0,
  "skipped_children_listed": 1,
  "malformed_metadata": [],
  "children_listed_drift": [
    {
      "orphan_id": "FEAT-1",
      "excluded_reason": "children_listed",
      "epics": [
        {"epic_id": "EPIC-1", "status": "open", "blocks_proposal": true},
        {"epic_id": "EPIC-2", "status": "done", "blocks_proposal": false}
      ]
    }
  ]
}
```

Counters count unique structural candidates by their primary reason, independent of threshold, and add up to the total excluded candidates. Malformed details are sorted entries containing `orphan_id` and sorted `keys`, without private reason values. Drift entries include every claiming EPIC/status, sorted by orphan ID then EPIC ID, including secondary claims on candidates whose `excluded_reason` is `malformed_metadata` or `intentional`. Each claim carries `blocks_proposal` (`true` for non-terminal claimants, `false` for `done`/`cancelled`). A candidate claimed only by terminal EPICs has `excluded_reason: null`, is not counted in any skip counter, and still appears in `proposals` (assign mode) or `clusters` (synthesize mode). Therefore the number of drift rows may exceed `skipped_children_listed`. Always-present report fields make zero/all-excluded cases straightforward for consumers; existing payload fields are unchanged.

Exclusions/drift alone exit 0 and do not write. Text mode names primary counts and claimant statuses, and suggests repairing metadata or reviewing the back-reference/listing with epic-consistency. JSON stdout remains one JSON document; read/error/invalid-marker diagnostics go to stderr. Update the skill to display these reports before empty-result early returns.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — new `FormatGaps` field/predicates/JSON entry and raw detector before early returns. Add its docstring entry; leave metadata reads bounded by real frontmatter.
- `scripts/little_loops/frontmatter.py` — house raw post-fence entry/span analysis beside existing block geometry if useful; do not change `parse_frontmatter` precedence.
- `scripts/little_loops/cli/issues/format_check.py` — render loop, per-issue repair dispatch, and parser/help/docstring gap/fix lists; do not add the repair to sweep-safe kinds.
- `scripts/little_loops/cli/issues/link_epics.py` — misplaced-metadata exclusion, local marker classification, all-status EPIC exclusion index, deterministic text/JSON reporting in both modes, and accurate orphan help.
- `scripts/little_loops/cli/issues/epic_consistency.py` — no recognizer is created here: BUG-3738 (done) landed the public `find_children_section`/`iter_child_entries`/`ChildEntry` recognizer in `cda52e0eb`, and `_parse_children_body` now delegates to it. Consume it; touch this file only if the landed grammar lacks a fence or whole-ID safeguard this issue's exclusion index needs. Retain `compute_drift` category-(b) meaning and the separate fix policy.
- `scripts/little_loops/cli/issues/__init__.py` — update the manually maintained format-check help summary.

### Dependent Files

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` runs single-issue format repair automatically. The guarded fixer must be idempotent and leave ambiguous input alone; no loop edit is required here.
- `scripts/little_loops/loops/rn-remediate.yaml` and `skills/format-issue/SKILL.md` consume the format-check exit result; the new kind remains blocking.
- `skills/confidence-check/SKILL.md` documents which structure gaps have automatic remedies; synchronize that statement and its pinned test if updated.
- `skills/link-epics/SKILL.md` parses both payloads. Show exclusion/drift reports before its early return on empty proposals/clusters, otherwise a run consisting entirely of exclusions hides the result.
- BUG-3738 (done) already updated the same command's writes/result bookkeeping (one-winner apply, an additive `rejected` list, a per-pair lock, exit code 1 on rejection) and landed the shared Children recognizer (`cda52e0eb`). Keep this issue's additive exclusion keys compatible with those; no serial-landing constraint remains. Note the interaction: BUG-3738 writes the orphan first, so its partial write (orphan parented, EPIC bullet missing) removes the issue from the orphan set and never reaches this classifier; it is repaired by `epic-consistency --fix`. Children-listed drift here arises only from manual or pre-existing listings without a back-reference.

### Tests

- `scripts/tests/test_issue_parser.py` — pure detector, blocking predicates/serialization, raw-line locations, unknown template/type, horizontal-rule/fenced-YAML false positives, scalar/multiline/duplicate/collision/multi-block prefix cases.
- `scripts/tests/test_ll_issues_format_check.py` — golden JSON and every-field-rendered guard; safe apply and reapply; preview; unsafe no-op; sweep exclusion; LF/CRLF/final newline/mode; dispatcher membership. Use `_REPAIR_DISPATCH` and `_SWEEP_SAFE_REPAIRS` invariants.
- `scripts/tests/test_frontmatter.py` — header-block and fence geometry regression net if helpers are added there.
- `scripts/tests/test_link_epics_cli.py` — misplaced metadata excluded before apply (even with no EPIC claims), `parentless_reason` cases (non-empty string opts out; empty/null/whitespace/list/mapping do not; non-scalar warns on stderr), bullet/H3 styles, non-terminal EPIC claims excluding versus `done`/`cancelled` claims reported with `blocks_proposal: false` while the candidate stays proposable (both modes), exact-ID/fence negatives, several claimants, primary-reason precedence with retained secondary claims, both modes, zero-candidate output/default fields, control orphan, pure JSON, unreadable-file errors, and filtered candidates never reaching deep/model calls.
- `scripts/tests/test_epic_consistency.py` — preserve category-(b), sub-EPIC, and existing child styles when shared recognition gains safety.
- `scripts/tests/test_link_epics_skill.py`, `scripts/tests/test_confidence_check_skill.py`, and `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py` — skill/report contract, remedy wording, and the existing no-subprocess detector gate.

### Documentation

Update `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/ISSUE_TEMPLATE.md`, `docs/reference/COMMANDS.md`, and `skills/link-epics/SKILL.md` with the bounded keys, unsafe-repair policy, the single `parentless_reason` marker convention (recommended wording for new entries), terminal-versus-non-terminal EPIC claim semantics and the `blocks_proposal` flag, always-present report fields/primary-reason precedence, and informational drift status. Keep counts of gap kinds derived from the actual fields when updating prose.

Regenerate affected host mirrors with `ll-adapt` and run the repository's mirror/doc-audience gates after skill/documentation changes. Do not add developer-only test/package paths to product-facing instructions.

### Configuration

No setting, third-party dependency, model call, or broad issue-schema migration.

## Implementation Steps

1. Add detector/fixer regressions, including conflict/multiline refusals and valid-multiple-block/fenced/body false positives. Run the raw detector over the local issue corpus and inspect hits before enabling the blocking gap; repair only verified safe records. Then wire the blocking gap and conservative per-issue repair.
2. Consume the existing shared Children recognizer (`find_children_section`, `iter_child_entries`, `ChildEntry` in `epic_consistency.py`, landed by BUG-3738 in `cda52e0eb`) — no prerequisite commit. Add malformed-metadata exclusion, local `parentless_reason` classification, and the all-status documented-child index (non-terminal claims exclude; terminal claims report only) on top of it. Filter before assign, synthesize, apply, and deep paths.
3. Emit the defined skip/drift reports in both output modes, including no remaining candidates and multiple/overlapping claims; update skill early-return handling.
4. Synchronize help/API/template/skill contracts and affected mirrors.
5. Run focused parser/format/link/consistency/skill regression suites and changed-code lint/types, then the authoritative `python -m pytest scripts/tests/`.

## Acceptance Criteria

- [ ] The four bounded parenting keys in the immediate prefix after the last recognized block produce blocking file/key/line findings, even with an unresolved template/type; valid consumed frontmatter blocks, normal prose, body horizontal rules, other sections, and fenced YAML stay unflagged. Corpus hits are inspected before rollout.
- [ ] Safe single-line, absent-key runs move inside one valid block without unrelated byte/newline/mode changes; preview and sweep mode do not write, successful apply is idempotent, and duplicate/colliding/multiline/malformed/multi-block runs stay reported without partial movement.
- [ ] Misplaced parenting metadata excludes candidates before any new assignment, including unsafe repair shapes; a correctly placed non-empty `parentless_reason` opts out, and null/empty/whitespace/non-scalar values still qualify as orphans.
- [ ] Real child entries in non-terminal EPICs exclude candidates before scoring/deep calls; claims from `done`/`cancelled` EPICs are reported (`blocks_proposal: false`) without excluding; fenced/prose/partial-ID entries do not count. Several claimants and overlapping opt-out/membership reasons remain visible without any automatic reparenting.
- [ ] The Children recognizer stays single-sourced: the exclusion index calls the public `find_children_section`/`iter_child_entries` landed by BUG-3738 (shared with its writer and the consistency checker), and this issue adds no second implementation of section selection, fence handling, or whole-ID matching.
- [ ] Both modes always emit the defined counters/detail lists, including zero/all-excluded runs; primary counts are disjoint and secondary EPIC claims/statuses remain visible. JSON stdout stays clean, exclusions/drift alone exit 0, and file-read failures produce explicit nonzero errors.
- [ ] Parser/model compatibility and consistency-reader regression tests pass; docs, help, and skill consumers describe and display the final contract; focused and full local suites pass.

## Impact

- **Priority**: P3 — recorded organization decisions are lost to tooling, causing recurring wrong-parent proposals and unreliable EPIC organization.
- **Effort**: Medium — one bounded structural check/repair and one candidate-classification pass, with focused CLI/consumer integration.
- **Risk**: Medium — automatic metadata movement and broader exclusion evidence need strict false-positive/conflict controls; report-only ambiguous cases and no inferred parent limit unintended changes.
- **Breaking Change**: No payload removals or parser read-contract changes. Candidate exclusions intentionally change results, and misplaced parenting metadata now fails the format gate.

## Review Notes

**Review verdict: CORRECTED — ready for implementation.** Format, concrete program design, and unresolved-decision gates pass. No open dependency is required between these issues.

2026-10-05: Reconciled refine/wire/verification findings, removed the obsolete lint command reference, bounded the key vocabulary, and resolved marker/status/output/repair decisions. Temporary reproductions confirmed ignored post-fence parent metadata and unsafe fenced/partial-ID matches in the existing child parser. The shared surrounding regression suites passed **235 tests**; proposed behavior still requires implementation and the new tests above. A review scan of **3,644 local issue files** found no immediate post-fence parenting-key runs and no existing intentional-parentless frontmatter markers. This supports introducing the bounded convention without a local metadata migration; consuming projects still require their own hit review.

Used `/ll:advise --signal user_requested --host claude-code --model opus` for critique (confidence **0.76**). Adopted its last-block boundary, malformed-candidate exclusion, explicit-false marker precedence, all-status claimant reporting, and disjoint always-present counters. Kept the requested repair with a stricter all-or-nothing/absent-key contract. Advisor dissent concerned splitting the repair, introducing a dependency on BUG-3738, and output compatibility: retain this bounded repair and use existing parser/block utilities so either issue can land independently. Do not adopt numeric-ID equivalence or automatic deletion of colliding keys.

2026-10-05 (second pre-implementation review, with `/ll:advise --signal user_requested --host claude-code --model fable`, confidence **0.82**): the corpus scan found zero post-fence runs and zero existing markers, which drove these changes. **Adopted:** one marker convention (`parentless_reason`) with no precedence table; terminal-EPIC (`done`/`cancelled`) claims are informational and no longer exclude, with a per-claim `blocks_proposal` flag; one shared Children recognizer landed by whichever of this issue/BUG-3738 goes first, with serial landing; the interaction with BUG-3738's partial-write case is documented. **Decision (owner): the post-fence mover is kept** in this issue. The advisor's alternative was to defer the mover (and its CLI policy and docs) while keeping the detector and `FormatGaps` field, since blocking gaps without a fixer already exist (`multi_frontmatter`, `malformed_id`, `deprecated_key`) and the corpus has no hits; the dissent in favor of keeping it is that the contract is already all-or-nothing and single-issue, and a blocking gap with no fixer forces a hand edit in consuming projects. If implementation pressure appears, the mover is the first piece to cut, and the detector, exclusion, and report stay valuable on their own. Decided (owner, 2026-10-05): `deferred` EPIC claims still exclude, because deferred is non-terminal per the repository's dependency convention. The advisor questioned this. Flipping it to informational later is a one-line status-set change, so revisit only if orphans are reported stuck behind deferred EPICs. Follow-up not in scope: a parent-assignment option for `ll-issues link`, which would give children-listed drift a real remedy. Confidence/outcome scores predate these edits; re-run `/ll:confidence-check` before implementation.

## Resolution

- **Action**: fix
- **Completed**: 2026-10-05
- **Status**: Completed

### Changes Made
- `scripts/little_loops/frontmatter.py`: `find_post_fence_entries()` (bounded post-fence prefix detector) and `move_post_fence_entries()` (all-or-nothing raw-line mover); `parse_frontmatter` read contract unchanged.
- `scripts/little_loops/issue_parser.py`, `scripts/little_loops/cli/issues/format_check.py`: blocking `FormatGaps.post_fence_keys` (key/line/file, no values), render loop, and single-issue-only `post_fence_keys` repair (not in `_SWEEP_SAFE_REPAIRS`).
- `scripts/little_loops/cli/issues/link_epics.py`: `classify_orphans()`/`intentional_parentless()`/`OrphanClassification` run before assign/synthesize/apply/deep; primary-reason precedence malformed → intentional → Children-listed; terminal-EPIC claims are informational (`blocks_proposal: false`); always-present report keys in both JSON modes plus text rendering; unreadable files exit 1.
- Docs/skill: CLI.md, API.md, COMMANDS.md, ISSUE_TEMPLATE.md, `skills/link-epics/SKILL.md` (report shown before empty-result returns).
- Tests: detector/mover, gap class, format-check CLI (preview/apply/idempotent/CRLF+mode/unsafe/sweep), link-epics exclusions (both modes, precedence, deep, unreadable file), skill contract.

### Verification Results
- Tests: PASS for all touched suites; full `python -m pytest scripts/tests/` = 28485 passed, 1 failed (`test_verify_evidence` corpus gate on untouched ENH-3700) and 8 errors (`test_libsql_integration` live endpoint) — both unrelated to this change
- Lint: PASS (`ruff check scripts/`)
- Types: PASS for touched files (repo-wide mypy has pre-existing `ruamel` stub errors)

## Status

**Open** | Created: 2026-10-05 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-05_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- Criterion 4 is capped at 10/20 by that claim gap only; no other readiness gap found. Program Design gate, dependencies (`relates_to: BUG-3738` is done), and unproven-mechanism flag are all clear.

## Resolved Concerns

- [resolved 2026-10-05 by /ll:reconcile-issue] Stale claim (`stale_symbol_ref`): `_section_bounds` in `epic_consistency.py` no longer exists; BUG-3738 landed the shared recognizer in `cda52e0eb` — the "created here if this issue lands first" wording in Files to Modify and Implementation Step 2's "check whether BUG-3738 has landed" prerequisite were out of date — rewrote Files to Modify, Dependent Files, Implementation Step 2 and the recognizer Acceptance Criterion to consume the existing public recognizer (the Root Cause bullet sits outside the rewrite scope and was left as-is).

## Session Log
- `/ll:manage-issue` - 2026-10-06T01:39:47 - `5f7c42ab-446e-47b2-9e17-3b5098ecdbf9.jsonl`
- `/ll:ready-issue` - 2026-10-06T01:25:19 - `3d3dcfff-5dd7-4a32-a7b0-814ea79e2aaa.jsonl`
- `/ll:confidence-check` - 2026-10-06T01:02:04 - `7ce14b43-677b-479f-b1f1-2aec6e7467fb.jsonl`
- `/ll:reconcile-issue` - 2026-10-06T00:58:23 - `25f9ee70-9553-4942-b494-3226cac87846.jsonl`
- `/ll:confidence-check` - 2026-10-06T00:13:52 - `c9f2014b-1e92-4dc8-a5a8-e4b3f5742389.jsonl`
- `/ll:confidence-check` - 2026-10-05T23:26:54 - `dfedb32a-de04-4382-86b8-3c6cab5d9da5.jsonl`
- `/ll:confidence-check` - 2026-10-05T21:03:07 - `275ebb58-903a-4210-9cb0-e88316d19a35.jsonl`
- `/ll:ready-issue` - 2026-10-05T20:18:56 - `c6ed73f5-2103-48a0-bfaa-97a8901cbedc.jsonl`
- `/ll:verify-issues` - 2026-10-05T19:59:00 - `82de079c-5cd6-4104-ba4d-1ae5be5a2a7d.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T19:56:33 - `028b082b-4804-4e7c-9920-43f4adff3a93.jsonl`
- `/ll:wire-issue` - 2026-10-05T19:48:40 - `cca3c87c-937f-4367-b92b-642516bd4f0e.jsonl`
- `/ll:refine-issue` - 2026-10-05T19:39:52 - `84fa6018-8b93-4b53-8e45-1f0de0127b76.jsonl`
