---
id: ENH-3636
type: ENH
title: 'll-issues show: annotate resolved blocked_by/depends_on edges with status'
priority: P4
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T17:29:51Z'
reconcile_attempted: true
verify_verdict: NON_VALID
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: '2026-09-28T23:22:38Z'
---

# ENH-3636: ll-issues show: annotate resolved blocked_by/depends_on edges with status

## Summary

`ll-issues show` renders the `Blocked by:` and `Depends on:` relationship rows as raw frontmatter IDs without resolving each target's status, so an already-satisfied blocker reads as a live one. Example: ENH-3623 shows `Blocked by: ENH-3630` even though ENH-3630 is `done`.

## Current Behavior

`ll-issues show ENH-3623` renders `Blocked by: ENH-3630` with no indication that ENH-3630 is `done`. The card gives no way to tell a satisfied edge from a live blocker without running `ll-issues show` on each target. `--json` likewise exposes only the raw comma-joined `blocked_by` / `depends_on` strings.

## Expected Behavior

Resolved edges (target status `done` or `cancelled`) are visibly annotated in the card, e.g. `Blocked by: ENH-3600, ENH-3630 (done)` with the resolved entry dimmed. Live edges (`open`, `in_progress`, `blocked`, `deferred`) and unknown IDs render as plain IDs, listed before any resolved entries. `--json` keeps `blocked_by` / `depends_on` byte-identical and additionally exposes the still-unresolved subset (every ID not resolved as `done`/`cancelled`, including IDs not found on disk).

## Motivation

`blocked_by` / `depends_on` edges are durable by design — nothing prunes them when the target completes (`set_status.py:268` documents that these association edges never cascade). Resolution is computed at read time: `DependencyGraph.get_blocking_issues()` returns `blockers - completed` (`dependency_graph.py:295`), so schedulers (`next-issue`, sprints, autodev) already treat ENH-3623 as unblocked. Only the display disagrees, which prompted a false "is refine-to-ready-issue broken?" investigation on 2026-09-27 after a refine-to-ready-issue run on ENH-3623 (the run's `gate_unmet` failure was unrelated).

## Program Design

### Types

- No new types — annotated fields stay `str | None`, same as the existing `blocked_by` / `depends_on` keys.

### Signatures

- `_parse_card_fields(path: Path, config: BRConfig) -> dict[str, str | None]` (`show.py:63`, unchanged signature) — return dict gains four keys: `blocked_by_display`, `depends_on_display`, `unresolved_blocked_by`, `unresolved_depends_on`.
- `_id_matches(candidate: str, pattern: str) -> bool` (`cli_args.py:408`) — reused as-is to resolve bare-numeric edge IDs against loaded issue IDs.
- `_render_relationships_block(fields: dict[str, str | None]) -> list[tuple[str, str]]` (`show.py:535`, unchanged signature) — reads `_RELATIONSHIP_KEYS` (repointed to the `*_display` keys) and applies `_dim(text: str) -> str` (`show.py:401`) to resolved entries.

### Call Path

`ll-issues show` CLI entry -> `_parse_card_fields` -> `_id_matches` (per edge ID, against `_all = find_issues(...)`) -> `_render_relationships_block` -> `_dim`

## Proposed Solution

Display-side only — do not mutate frontmatter, and do not change the existing `blocked_by` / `depends_on` field values.

Design decisions (settled):

- **Inline annotation, not a separate row.** Annotate only resolved IDs as `ID (done)` / `ID (cancelled)`, dimmed in the text card only. Live IDs stay plain — card values clip with an ellipsis (`_truncate_to_width`), not wrap, so tagging every ID would push long rows into truncation.
- **Resolved = `done` / `cancelled` only.** `deferred` is non-terminal for dependency edges and renders as a live blocker.
- **Live entries first, resolved entries last in the `*_display` string.** Card values are clipped by `_truncate_to_width` (ellipsis, and it strips all color on a clipped row), so an annotated early item would push later live IDs off the edge and hide a real blocker. Ordering live-first means clipping eats resolved entries instead. Relative order within each group follows the raw frontmatter order; raw `blocked_by` / `depends_on` keep their original order. Dimming is best-effort — it is lost on any clipped row, but the plain-text `(done)` / `(cancelled)` tag survives.
- **Unknown / unresolvable IDs render unchanged** — no `(missing)` tag.
- **`unresolved_*` = "not resolved as `done`/`cancelled`", not "actually blocking the scheduler".** Unknown IDs (not on disk) stay in `unresolved_*` — the conservative choice, matching the card row, which renders them plain. This deliberately diverges from `DependencyGraph.from_issues`, which drops missing blockers with a warning (`dependency_graph.py:~108-116`) and so never blocks on them. Document this wording in `CLI.md` / `API.md`.
- **New display keys, mirroring `parent_display`.** Add `blocked_by_display` / `depends_on_display` to the fields dict and point `_RELATIONSHIP_KEYS` at them; raw `blocked_by` / `depends_on` stay untouched.
- **New machine-readable JSON keys:** `unresolved_blocked_by` / `unresolved_depends_on`, comma-joined strings in the same shape as the existing fields (`None` when empty). Purely additive.
- **Fail-open:** if the issue scan raises, the display keys fall back to the raw joined IDs (no annotation) and the `unresolved_*` keys fall back to the full raw lists.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- Segment-level dimming (splitting a comma-joined relationship value and conditionally applying `_dim` to individual comma-separated items while leaving others plain) has no precedent anywhere in this codebase — searched every `colorize(`/`_dim(` call site under `scripts/little_loops/cli/issues/`. Existing `_dim` usage is always whole-label or whole-value (e.g. `_render_row` dims the row label via `_dim(key_text)`, not the value, at `show.py:679`). Implementation Steps item 4's "dimming each comma-separated item ending in ` (done)` / ` (cancelled)`" is new territory for this helper, not an established convention being followed.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/show.py`:
  - `_parse_card_fields` (~261-392): inside the existing `try` block (line 280), reuse the already-loaded `_all = find_issues(config, status_filter=set(_ALL_STATUSES))` (line 284) to build an ID → raw status map, mirroring the existing `parent_display` ID→title resolution (BUG-3392 pattern, same function). Compute `blocked_by_display`, `depends_on_display`, `unresolved_blocked_by`, `unresolved_depends_on`; defaults set before the `try` so the `except` path yields the unannotated fallback.
  - `_RELATIONSHIP_KEYS` (521-532): swap `"blocked_by"` → `"blocked_by_display"` and `"depends_on"` → `"depends_on_display"` (same labels).

### Dependent Files (Callers/Importers)
- `skills/confidence-check/SKILL.md:162` — parses `blocked_by` from `ll-issues show --json` by splitting on commas. **The `blocked_by` value must stay byte-identical** (raw IDs, no annotation). A later follow-up could switch this skill to `unresolved_blocked_by` and drop its per-blocker `ll-issues show` calls — out of scope here. That follow-up must first decide how to handle IDs not found on disk: `unresolved_blocked_by` includes them, but the scheduler ignores them.
- `scripts/little_loops/mcp_server/tools.py:138` (`issue_get`) and `scripts/little_loops/mcp_server/resources.py:264` — return `_parse_card_fields` output verbatim; they pick up the new keys automatically (additive, no code change).
- `dep_graph.get_blocking_issues()` scheduler callers (`issue_manager.py:1882,1972`) — untouched.

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/skills/confidence-check/SKILL.md:161`, `.qwen/skills/confidence-check/SKILL.md:161`, `.kimi-code/skills/confidence-check/SKILL.md:161` — generated host mirrors of the same `d.get('blocked_by')` snippet in `Phase 1.7: Pre-Fetch Dependencies Gate`; no edit (raw `blocked_by` stays byte-identical), but they re-split the value on commas, so an annotated `ENH-3630 (done)` in that key would break them too [Agent 1 finding]
- `scripts/little_loops/loops/rn-remediate.yaml:174,353,755` — whole-dict `ll-issues show --json` snapshots (`pre_scores_<ID>.json` / `post_scores_<ID>.json`) in `rn-remediate` states; new keys land in the snapshot files, read by key only, so additive and harmless [Agent 1 finding]
- `scripts/little_loops/loops/rn-decompose.yaml:63` — whole-dict `size_review_snap_<ID>.json` snapshot; additive keys harmless [Agent 1 finding]
- `scripts/little_loops/mcp_server/tools.py:146` — returns the dict verbatim in `_tool_issue_get`; `types.Tool(name="issue_get")` (~`tools.py:861`) declares only an `input_schema`, so no descriptor change [Agent 2 finding]
- `scripts/little_loops/mcp_server/resources.py:267` — `json.dumps(fields)` verbatim in `_read_issue_body`; picks up new keys with no change [Agent 2 finding]
- `scripts/little_loops/loops/rn-implement.yaml:428` — `check_blocked_by` deliberately reads frontmatter, not `show --json` (ENH-2535 rationale); unaffected as long as raw `blocked_by` is unchanged [Agent 1 finding]

### Similar Patterns
- `parent_display` resolution at `show.py:270-292` (BUG-3392) — same "resolve ID via already-loaded issue list" shape; follow it rather than adding a new lookup helper.
- **ID matching:** unlike `parent_display`'s exact `i.issue_id == parent_str`, match with `_id_matches` (`cli_args.py:408`, already imported by `issue_parser`) so a bare-numeric frontmatter ID (`blocked_by: [3630]`) still resolves — the numeric ID is the canonical key.

### Tests
- Model new tests after `test_relationships_fields_extracted` (`test_show.py:509`) and `test_parent_display_resolves_title_when_parent_is_done` (`test_show.py:559`).
- Edit four existing hand-built-`fields` tests to also set `blocked_by_display` (they stop rendering their `Blocked by:` row once `_RELATIONSHIP_KEYS` is repointed): `test_relationships_block_renders_blocked_by` (802-811), `test_blocked_status_includes_blocked_by_name` (813-823), `test_column_alignment_with_four_plus_rows` (974-992), `test_no_column_alignment_below_four_rows` (994-1004).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_show.py:296` — `TestParseCardFields._write_issue(tmp_path, content, filename)` builds an ENH-only config; write sibling target issues straight into `.issues/enhancements/` (pattern in `test_parent_display_resolves_title_when_parent_is_done`) for new tests in `TestParseCardFields`; add `bugs`/`features` categories to `_make_config` if targets aren't ENH [Agent 3 finding]
- `scripts/tests/test_show.py:531` — `test_superseded_by_derived_from_reverse_edge` (and `test_superseded_by_derived_when_superseder_is_deferred`) use the same `find_issues` scan with `cancelled`/`deferred` siblings; nearest fixture model for done/cancelled/deferred/open/in_progress/blocked targets in `TestParseCardFields` [Agent 3 finding]
- `scripts/tests/test_show.py:645` — `test_regression_no_new_fields_renders_identically` asserts raw `blocked_by`/`depends_on` are `None` for a baseline issue; still passes if raw keys keep their `_join_ids` result — extend it to assert the four new keys are `None` when no edges, in `TestParseCardFields` [Agent 3 finding]
- `scripts/tests/test_show.py:924` — `test_status_colors_applied_per_state` is the only test that sets `_USE_COLOR=True` (`monkeypatch.setattr("little_loops.cli.output._USE_COLOR", True, raising=False)`) and asserts SGR codes; model for asserting `_dim` on resolved entries only, in `TestRenderCard` [Agent 3 finding]
- `scripts/tests/test_show.py` — new fail-open test in `TestParseCardFields`: no existing test exercises the `except Exception` branch of the scan; patch `little_loops.issue_parser.find_issues` (imported lazily inside `_parse_card_fields`) with `side_effect=RuntimeError`, modeled on `scripts/tests/test_issue_parser.py:~1504` (`patch("little_loops.dependency_mapper.gather_all_issue_ids", side_effect=RuntimeError("boom"))`), asserting display keys equal raw joins and `unresolved_*` equals the full raw lists [Agent 3 finding]
- `scripts/tests/test_issues_cli.py:3064` — `test_show_json_output` / `test_show_json_no_color_codes` (~3093, asserts `"\033[" not in captured.out`) drive `main_issues()` with `sys.argv` patched; none set `blocked_by`/`depends_on` frontmatter. Add a `show --json` test with a `done` and an `open` target asserting raw `blocked_by` byte-identical, `unresolved_blocked_by` correct, and no ANSI in any annotated field; add a text-card test asserting `(done)` in `capsys` output [Agent 3 finding]
- `scripts/tests/test_mcp_server.py:184` — `test_issue_get_tool_resolves_and_reports_not_found` asserts only `payload["issue_id"]`; no key-set assertion, so it won't break. Optional: assert new keys in `issue_get` / `ll://issues/<ID>` payloads (see `test_read_resource_issue_returns_card_fields` ~391) [Agent 3 finding]
- `scripts/tests/test_confidence_check_skill.py:463` — asserts Phase 1.7 prose ("must resolve each blocked_by ID via ll-issues show --json (BUG-3051)"); unaffected unless the skill is edited (out of scope) [Agent 2 finding]
- `scripts/tests/test_rn_implement.py:1101` — `test_check_blocked_by_parses_frontmatter_not_show_json` asserts the gate reads frontmatter, not `show --json`; unaffected while raw `blocked_by` is unchanged [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md:1672` (Relationships bullet under `ll-issues show`) — note that resolved `blocked_by` / `depends_on` targets are annotated `(done)` / `(cancelled)`.
- `docs/reference/CLI.md` `--json` row (line 1678, `| `--json` / `-j` | Output issue fields as JSON (includes `source`, `norm`, `fmt` keys) |`) — list the new `unresolved_blocked_by` / `unresolved_depends_on` keys, defined as "targets not resolved as `done`/`cancelled`, including IDs not found in the project" (the scheduler ignores missing IDs; `show` does not). Also note in the Relationships bullet that live entries list before resolved ones.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4871` — enumerates the `--json` output fields incl. `blocked_by`, `depends_on`, `parent_display`, under `#### show`; add `blocked_by_display`, `depends_on_display`, `unresolved_blocked_by`, `unresolved_depends_on` in `show` [Agent 2 finding]
- `docs/reference/OUTPUT_STYLING.md:291` — table row for `Blocks` / `Blocked by` / `Depends on` / … says "Comma-joined IDs (ENH-2535)"; the only doc describing the rendered row value — note resolved entries render `ID (done|cancelled)`, dimmed, in `Relationship rows` [Agent 2 finding]
- `docs/reference/CLI.md:2000` — `ll-issues show FEAT-518 --json` example; no edit needed, but re-read if the `--json` description changes wording, in `ll-issues show` examples [Agent 1 finding]
- `docs/reference/CLI.md` audience gate — new prose must use reader-facing wording (no `scripts/tests/` paths, no "this repo"); `scripts/tests/test_docs_audience_gate.py` scans `docs/reference/`. Optionally pin the new keys with a `("docs/reference/CLI.md", "unresolved_blocked_by", "ENH-3636")` tuple in `scripts/tests/test_wiring_reference_docs.py` (pattern: `"unproven_mechanism"`, ENH-3350) [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- Four existing tests in `scripts/tests/test_show.py` hand-build a `fields` dict bypassing `_parse_card_fields` and set a raw `"blocked_by"` key directly, not `blocked_by_display`: `test_relationships_block_renders_blocked_by` (802-811), `test_blocked_status_includes_blocked_by_name` (813-823), `test_column_alignment_with_four_plus_rows` (974-992), `test_no_column_alignment_below_four_rows` (994-1004). Repointing `_RELATIONSHIP_KEYS` to `blocked_by_display`/`depends_on_display` means these four fixtures stop rendering their `"Blocked by: ..."` row unless each is updated to also set the corresponding `*_display` key — this is beyond the three tests already cited under Tests as models to follow; those three demonstrate the pattern, these four require an actual edit.

## Implementation Steps

1. In `_parse_card_fields`, initialize `blocked_by_display = _join_ids(blocked_by_raw)`, `depends_on_display = _join_ids(depends_on_raw)`, and `unresolved_* = ` the same raw joins, before the `try` block.
2. Inside the `try` (after `_all` is loaded), build an `{issue_id: status}` dict once; resolve each edge ID by exact dict lookup and fall back to `_id_matches` (scan) only for bare-numeric edge IDs. Resolved = status in `{"done", "cancelled"}` — **do not reuse `show.py`'s local `_TERMINAL_STATUSES` (line 455, `{"done", "cancelled", "deferred", "closed"}`)**; that set is for closure-note rendering and treats `deferred` as terminal. Import `issue_progress._TERMINAL_STATUSES` (`issue_progress.py:14`) under an alias (`as _RESOLVED_EDGE_STATUSES`) to avoid shadowing the local set; this is consistent with `dependency_graph.py:295`.
3. Build the display strings as **plain text** (no ANSI — the fields dict is emitted verbatim by `--json` and MCP): resolved IDs → `f"{id} ({status})"`, others unchanged; emit live (incl. unknown) IDs first, then resolved entries, each group in raw order. Build `unresolved_*` from the non-resolved IDs (including unknown IDs, in raw order), `None` if empty.
4. Add the four keys to the returned dict; repoint `_RELATIONSHIP_KEYS` at the `*_display` keys. Apply the gray `_dim` to resolved entries in `_render_relationships_block` (text card only), e.g. by dimming each comma-separated item ending in ` (done)` / ` (cancelled)`.
5. Update `docs/reference/CLI.md`, `docs/reference/API.md` (`#### show` `--json` fields) and `docs/reference/OUTPUT_STYLING.md` (Relationship rows table) — see Documentation.
6. Tests: edit the four hand-built `fields` fixtures in `test_show.py` to set `blocked_by_display`, then add the new tests listed under Tests / Wiring Phase.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Import the terminal set under an alias — `show.py` already defines a module-level `_TERMINAL_STATUSES` (`{"done","cancelled","deferred","closed"}`, used by `_render_closure_block`); a bare function-local `from little_loops.issue_progress import _TERMINAL_STATUSES` inside `_parse_card_fields` would shadow it only within that function but is easy to misread. Use `from little_loops.issue_progress import _TERMINAL_STATUSES as _RESOLVED_EDGE_STATUSES` (no import cycle: `issue_progress` imports only stdlib at module level; `_ALL_STATUSES` is already imported from it at the top of the `try`)
- Compare against `IssueInfo.status` (raw lowercase frontmatter, canonicalized by `parse_frontmatter`), not the card's display-cased `status`; note `IssueParser.parse_file` maps `status: open` + `completed_at` to `done`, so a target can annotate as `(done)` while its own `show` card reads Open — acceptable, consistent with the scan the scheduler uses
- Note for the bare-numeric AC: `ll-issues format-check` flags bare-numeric edges as `malformed_dep_id` (BUG-3059) and `DependencyGraph` drops them on exact-string membership, so the annotation will resolve an edge the scheduler ignores — keep the `_id_matches` resolution (per the design decision) but the test for it should assert display behavior only
- Update `scripts/tests/test_show.py` — set `blocked_by_display` alongside `blocked_by` in the four hand-built `fields` fixtures (`test_relationships_block_renders_blocked_by`, `test_blocked_status_includes_blocked_by_name`, `test_column_alignment_with_four_plus_rows`, `test_no_column_alignment_below_four_rows`) once `_RELATIONSHIP_KEYS` is repointed; extend `test_regression_no_new_fields_renders_identically` for the four new keys
- Add new tests — `TestParseCardFields` (done/cancelled/deferred/open/in_progress/blocked/unknown targets; list and comma-string frontmatter forms; bare-numeric ID; live-first ordering with a resolved ID listed first in raw frontmatter; unknown ID present in `unresolved_*`; fail-open via patched `find_issues`), `TestRenderCard` (`_dim` on resolved entries only with `_USE_COLOR=True`; plain text with `stable_snapshot_env`; a long mixed live/resolved list that gets clipped still shows the live IDs and the clipped row carries no ANSI), and `scripts/tests/test_issues_cli.py` (`show --json` raw-preserved/no-ANSI; text card annotation)
- Update `docs/reference/API.md` (`#### show` `--json` fields, line 4871) and `docs/reference/OUTPUT_STYLING.md` (Relationship rows table, line 291) alongside `docs/reference/CLI.md`
- No edit to `skills/confidence-check/SKILL.md` or its `.gemini/.qwen/.kimi-code` mirrors (out of scope; if edited later, run `ll-adapt --host <gemini|kimi-code|qwen> --apply`)

## Scope Boundaries

- **In scope**: Annotating `blocked_by` / `depends_on` display in `ll-issues show` (text card and `--json`) with resolved status; adding the additive `unresolved_blocked_by` / `unresolved_depends_on` JSON keys.
- **Out of scope**: Migrating `skills/confidence-check/SKILL.md` to consume `unresolved_blocked_by` instead of parsing raw `blocked_by` (noted as a follow-up in Integration Map); changing `DependencyGraph.get_blocking_issues()` or any scheduler logic — resolution computation is untouched, only the `show` display; annotating `parent` or other relationship fields beyond `blocked_by` / `depends_on`.

## Impact

- **Priority**: P4 - Cosmetic/diagnostic; schedulers already compute resolution correctly, but the misleading display has already caused one false investigation.
- **Effort**: Small - One function plus a keys-table change in `show.py`, following an existing in-function pattern.
- **Risk**: Low - Display-only and additive JSON keys; the one JSON consumer's field is preserved byte-identically.
- **Breaking Change**: No

## Acceptance Criteria

- `ll-issues show ENH-3623` makes it visible that ENH-3630 is resolved.
- A `deferred`, `open`, or unknown blocker renders without a resolved annotation.
- `--json` `blocked_by` / `depends_on` values are byte-identical to pre-change output when a target is `done`.
- `--json` exposes `unresolved_blocked_by` / `unresolved_depends_on` containing only non-`done`/`cancelled` targets, including IDs not found on disk.
- In the text card, live and unknown IDs are listed before resolved (annotated) ones, so a clipped row loses resolved entries first; an unknown ID is never hidden behind a resolved one.
- A bare-numeric frontmatter ID (e.g. `blocked_by: [3630]`) resolves to its target's status.
- If the issue scan raises, edges render unannotated (no crash, no `(missing)`), and `unresolved_*` equals the raw lists.
- No frontmatter is modified by `show`.
- No `--json` value contains ANSI escape codes.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-28. Graph: provider `codegraph`, freshness `stale` (results used as leads only; every anchor confirmed by direct grep/read). `ll-verify-evidence`: clean (0 findings)._

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date except for the `Remaining:` item — this section is a record of what was wrong and fixed, not an outstanding action item)

Corrected in place (line-anchor drift only):
- Integration Map: `_parse_card_fields` `try` block at line 280 (was 282)
- Integration Map: `skills/confidence-check/SKILL.md:162` (was 163)
- Documentation: `docs/reference/CLI.md` Relationships bullet at line 1672 (was 1659); `--json` row at line 1678 (was "~1665")
- Codebase Research Findings: `show.py:679` is `_render_row`'s `_dim(key_text)`, not a literal `_dim('Blocked by:')` call (whole-label dimming claim itself holds)

Remaining (out of correctable scope — Motivation is not auto-rewritten):
- Motivation: `set_status.py:268` should be `set_status.py:222-224` (the "never cascade" comment)
- Motivation: `dependency_graph.py:283` should be `dependency_graph.py:295` (`return blockers - completed`; line 283 is the `def`)

Verified accurate: `_parse_card_fields` (`show.py:63`), `_dim` (401), `_TERMINAL_STATUSES` (455, includes `deferred`), `_RELATIONSHIP_KEYS` (521), `_render_relationships_block` (535), `_id_matches` (`cli_args.py:408`), `issue_progress._TERMINAL_STATUSES` (`{"done","cancelled"}`, line 14), `issue_parser` `open`+`completed_at` → `done` mapping (line 4198), scheduler call sites `issue_manager.py:1882,1972`, MCP `tools.py:138/146` and `resources.py:264/267`, all four hand-built-fixture test names, host-mirror lines (`.gemini/.qwen/.kimi-code` `:161`), `rn-remediate`/`rn-decompose` snapshot lines, and the Proposed Solution's consequences (no exception-handler, fixture-invalidation, or AC-coverage defects found).

## Resolution

**Completed** | 2026-09-28

- `_parse_card_fields` now emits `blocked_by_display` / `depends_on_display` (live IDs first, resolved as `ID (done|cancelled)`) and `unresolved_blocked_by` / `unresolved_depends_on`; raw `blocked_by` / `depends_on` unchanged; fail-open on scan error.
- `_render_relationships_block` dims resolved entries in the text card only.
- Docs updated: `CLI.md`, `API.md`, `OUTPUT_STYLING.md`. Tests added in `test_show.py` and `test_issues_cli.py`.

## Status

**Open** | Created: 2026-09-27 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-09-28T23:27:32 - `5eea9021-caa4-4916-aa6c-efbbceceb090.jsonl`
- `/ll:ready-issue` - 2026-09-28T23:19:42 - `2c45ed8b-f353-4c87-9fd0-38be39917609.jsonl`
- `/ll:confidence-check` - 2026-09-28T21:57:00 - `5d91eb51-54e9-48f2-8c6c-bd0f06305c43.jsonl`
- `/ll:verify-issues` - 2026-09-28T21:55:40 - `a1acb612-8e7a-4230-9d9e-0d5963f5dea9.jsonl`
- `/ll:ready-issue` - 2026-09-28T21:46:09 - `d5d8a3f8-64b9-4c39-8b6b-ecd85fd5da80.jsonl`
- `/ll:confidence-check` - 2026-09-28T21:33:25 - `fc46e001-34dd-4cf2-a47b-15cce154c9f8.jsonl`
- `/ll:verify-issues` - 2026-09-28T21:32:04 - `b7a753bd-68cc-4e0d-bf56-7f0d8928b4c8.jsonl`
- `/ll:reconcile-issue` - 2026-09-28T21:29:53 - `956f68f6-16fd-4fa7-bab1-84da262f93fa.jsonl`
- `/ll:verify-issues` - 2026-09-28T21:28:56 - `b58a9121-a812-45d8-b49b-221ab6658b55.jsonl`
- `/ll:wire-issue` - 2026-09-28T21:26:33 - `d4971c9c-ee27-4874-a1a2-075b46811c65.jsonl`
- `/ll:refine-issue` - 2026-09-28T21:19:20 - `a2d602b9-9ee6-419b-908e-b9e97b6db4d2.jsonl`
- `/ll:format-issue` - 2026-09-28T21:10:25 - `98bade11-bd68-4a4b-be5c-a80038f306cd.jsonl`
- `/ll:capture-issue` - 2026-09-27T17:29:56 - `4759cc5d-e905-4259-b830-49d49c1712bf.jsonl`
