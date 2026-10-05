---
id: BUG-3739
type: BUG
title: Frontmatter keys placed after the closing fence are silently ignored, and link-epics
  re-proposes Children-listed and intentionally-parentless issues as orphans
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:54:03Z'
labels:
- issues
- link-epics
- frontmatter
relates_to:
- BUG-3738
verify_verdict: NON_VALID
---

# BUG-3739: Frontmatter keys placed after the closing fence are silently ignored, and link-epics re-proposes Children-listed and intentionally-parentless issues as orphans

## Summary

Frontmatter keys written just below the closing `---` fence (for example `parent: EPIC-NNN`, `epic:`, `parentless_reason:`) are silently treated as body text. Nothing flags them, so a parent decision recorded there is invisible to every tool. `link-epics` then proposes the same issue as an orphan on every run, and it also ignores the intentional-parentless markers even when they sit in the right place.

## Current Behavior

Observed on a downstream project: a triage pass (an agent editing files by hand) linked four orphans to EPICs and marked three as intentionally parentless. All seven `key: value` lines were inserted on the line *after* the closing fence:

```
goals: [3, 7]
---
parent: EPIC-NNN
epic: EPIC-NNN

# FEAT-NNN: ...
```

What happened next:
- `parse_frontmatter()` never sees the keys, so `is_orphan()` reports all seven as orphans.
- The EPICs' `## Children` sections already listed the four linked children. That is exactly category (b) in `ll-issues epic-consistency` ("body-listed, no parent: backref"), but nothing ran that check, and `link-epics` does not consult it.
- Two weeks later, `link-epics --mode assign` proposed the four as orphans again. A follow-up manual review also missed the misplaced `parentless_reason:` lines and linked an issue to the very EPIC its recorded reason called "deliberately the wrong home".
- Separately, `is_orphan()` checks only `parent`/`epic`. It ignores `standalone: true` / `standalone_reason:` / `parentless_reason:` even when they are in the frontmatter, so deliberate "no parent" decisions get proposed again on every run.

## Expected Behavior

- A `key: value` line that matches a known issue frontmatter key and sits directly after the closing fence (before the first H1 or blank-line-separated prose) is reported as an error that names the file and the key, with a fix that moves it into the block.
- `link-epics` does not propose an orphan that an EPIC's `## Children` already lists. It reports it as category-(b) drift, with a suggestion to add the `parent:` backref.
- `is_orphan()` excludes issues marked `standalone: true` or that carry a `parentless_reason:`. Both `--json` modes report how many were skipped as intentional.

## Proposed Solution

1. Add a check (in `ll-issues verify` / the issue-format lint, with a `--fix` that moves the lines into the block) for known frontmatter keys right after the closing fence.
2. In `link_epics.py`, add the intentional markers to `is_orphan()`, and subtract the IDs listed in any EPIC's `## Children` (reusing `epic_consistency._parse_children_body`) from the candidate set, reporting them separately.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Host for the lint is `ll-issues format-check`** (no `verify` subcommand exists). A new gap kind touches, per the convention all recent kinds follow: a `FormatGaps` field plus its `has_gaps` chain entry and `to_dict()` key (`issue_parser.py`), a detector invoked from `check_format_gaps`, a render loop in `_print_gaps` (`format_check.py`), optionally a `_REPAIR_DISPATCH` entry, the golden JSON assertion in `test_ll_issues_format_check.py::TestFormatCheckJsonOutput`, and doc bullets in `docs/reference/API.md` / `docs/reference/CLI.md`.
- **Detector placement constraint**: `multi_frontmatter` and `invisible_chars` run *before* the template-dependent early returns in `check_format_gaps`, so they still fire when the type or template cannot be resolved. A post-fence detector is a raw-content check of the same kind and should share that property.
- **No known-key registry exists.** `IssueParser.parse_file` hard-codes the keys it reads and `check_format_gaps` reads a few ad hoc; the detector needs its own bounded key set. Prose such as `Note: ...` directly after the fence is legitimate body text, so matching must be limited to known issue keys.
- **Repair constraints**: `update_frontmatter()` round-trips the block through `yaml.dump`, which reformats the whole block; the other body-rewriting fixers preserve unrelated bytes. BUG-3738 (same `apply_assignment` write path) records that a line-level insert inside the closing fence is the safe shape. Body-rewriting fixers are excluded from `--all --fix --apply` via `_SWEEP_SAFE_REPAIRS = {"prose_dep_drift"}`; fence-safety (content inside code fences untouched) and idempotency are asserted for every existing `--fix` class.
- **Children-listed subtraction**: `epic_consistency._parse_children_body` is module-level, stdlib-only imports (no cycle with `link_epics`), and has no other importer. It returns `(real_ids, sub_epic_ids)` with real = BUG/FEAT/ENH only. `epic_consistency._section_bounds(content, "Children")` takes a heading string, while `link_epics._section_bounds(content, heading_re)` takes a compiled regex — two same-named functions with different signatures.
- **Open edge to decide knowingly**: `cmd_link_epics` loads with the default status filter (drops done/cancelled/deferred), while `epic-consistency` uses `_ALL_STATUSES`. Whether an orphan listed in a *closed* EPIC's `## Children` is subtracted is unspecified by the issue.
- **Marker coercion constraint**: `parse_frontmatter` uses `yaml.BaseLoader`, so `standalone: true` arrives as the string `"true"` and `standalone: false` as `"false"`. `program_design.py:_is_true` accepts `true|yes|1`; `behavior_parity_not_applicable` uses plain truthiness, under which `"false"` would count as set. The new check must not repeat the truthiness form.
- **Payload constraint**: `--mode assign --json` is `{"proposals", "applied"}` and `--mode synthesize --json` is `{"clusters", "applied"}` (+ conditional `deep`); `skills/link-epics/SKILL.md` parses these. The existing precedent for new keys is the conditional `deep` key (`test_deep_end_to_end_json_output` asserts it is absent on the normal path). Any new counters must be additive and keep both consumers working.

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Convention — raw-text detectors precede the template early returns**: `check_format_gaps` calls `_invisible_char_gaps(...)` and `has_multiple_frontmatter_blocks(...)` before the `_ISSUE_TYPE_RE` / `load_issue_sections` early returns; gap messages name the offending thing and never reproduce it (`invisible_chars` entries read `U+2028 LINE SEPARATOR at line N`). A post-fence message should follow suit: name file, key, and line.
- **Convention — body-rewriting fixers are a pure transform plus a thin wrapper**: every `_REPAIR_DISPATCH` fixer has the signature `(config, source_id, path, targets, *, apply) -> None`, reads text, runs a separate fence-masked idempotent transform, returns when `updated == content`, then `atomic_write` or prints `[dry-run] would …` (evidence: `duplicate_heading`, `empty_provenance_stub`, `duplicate_session_log`, `template_placeholders`). Only `prose_dep_drift` is in `_SWEEP_SAFE_REPAIRS`.
- **Contested — report-only vs fixer**: `multi_frontmatter` and `invisible_chars` are blocking-by-default gap kinds with *no* `_REPAIR_DISPATCH` entry (`invisible_chars` has `test_fix_apply_leaves_characters` pinning that), while the ~7 body-rewriting kinds above have fixers. The AC requires `--fix` for this kind, so it lands in the second camp; the implementer chooses the write shape knowingly (see next bullet).
- **Contested — frontmatter write shape**: ~30 call sites use `update_frontmatter()` (`yaml.dump` round-trip, reformats the whole block — includes `link_epics.apply_assignment`, `link.py`, `set_status.py`, `set_flags.py`, `normalize.py`); a minority preserve bytes (`remove_frontmatter_keys`, `_set_labels_frontmatter`). The Implementation Steps constraint ("without reformatting the rest of the block") puts this fix with the minority.
- **Contested — boolean coercion under `yaml.BaseLoader`** (values arrive as strings): `program_design._is_true` (`:449`) accepts `true|yes|1` after `strip().lower()`; `IssueParser._coerce_tristate_bool` (`issue_parser.py:4680`) recognises only `"true"`/`"false"` and returns `None` for `yes`/`1`; inline `str(x).lower() == "true"` appears in `preparation_policy._flag`, `next_obligation`, `check_readiness`, `check_gate`, `set_flags`; and `check_format_gaps` uses plain truthiness for `behavior_parity_not_applicable` (`issue_parser.py:1285`), under which `"false"` is truthy. The Decision Rules' `true|yes|1` matches `_is_true`; reusing `_coerce_tristate_bool` for `IssueInfo` plumbing would silently narrow that to `true` only, so the two must be reconciled deliberately.
- **Contested — Children status scope**: `cmd_link_epics` uses `find_issues` with the default status filter (drops done/cancelled/deferred), whereas `cmd_epic_consistency`, `epic_progress.py:53`, and `list_cmd.py:196` use an all-statuses filter (`_ALL_STATUSES` is redefined locally in `epic_consistency.py:16`, `epic_progress.py`, `issue_progress.py`, `workspace_quality.py`). Under the current `link-epics` loading, a closed EPIC is absent from the list entirely, so subtracting its `## Children` requires loading it separately.
- **Convention — additive `--json` keys are conditional**: the base `link-epics` payloads stay fixed and new keys appear only when the feature fired (`payload["deep"]` is set only when `deep_info is not None`; `TestDeepSynthesizeCLI` asserts `"deep" not in out` on the normal path). `skills/link-epics/SKILL.md` (`:61`, `:124`) parses the exact key sets. No "skipped as intentional" counter exists yet, so the counter shape is a new decision, but a key emitted unconditionally would break the golden-style absence assertions' spirit.
- **Consolidation signal (reported, not recommended)**: three modules each implement "append a bullet to `## Children`" independently (`link_epics.apply_assignment`, `epic_consistency.fix_epic`, `create._append_child_to_epic_children`), and two same-named `_section_bounds` helpers differ in signature (`str` heading vs compiled regex). Reusing `_parse_children_body` across modules touches this seam.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `FormatGaps` field + `has_gaps`/`to_dict` entries and a detector called from `check_format_gaps` (post-fence key gap)
- `scripts/little_loops/cli/issues/format_check.py` — `_print_gaps` render loop, `_REPAIR_DISPATCH` entry and fixer, help/docstring gap lists
- `scripts/little_loops/cli/issues/link_epics.py` — `is_orphan()` / `cmd_link_epics` orphan-set construction and both `--json` payloads
- `scripts/little_loops/cli/issues/epic_consistency.py` — `_parse_children_body` is the Children-body parser to reuse (currently private, one caller)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/link_epics.py:651` — sole production caller of `is_orphan()`
- `scripts/little_loops/cli/issues/epic_consistency.py:201` — `compute_drift()` is the sole caller of `_parse_children_body`; `body_without_parent` is category (b)
- `scripts/little_loops/issue_parser.py` — `find_issues()` / `IssueParser.parse_file` feed `IssueInfo` to `cmd_link_epics`; `IssueInfo` has no field for the intentional markers
- `skills/link-epics/SKILL.md` — parses the `{"proposals", "applied"}` / `{"clusters", "applied"}` payloads

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — `main_issues` epilog (~:184) hand-lists format-check gap kinds (already stops at `unapplied_decision`, so non-exhaustive); add the new kind; `link-epics` help line (~:178) and dispatch (~:1146) otherwise unchanged [Agent 1/2 finding]
- `scripts/little_loops/cli/issues/format_check.py` — `add_format_check_parser` has two further kind lists beyond `_print_gaps`: the `help=` CSV (~:68/:73) and the `--fix` help text (lists fixable classes), plus a second copy in the `cmd_format_check` docstring (~:591/:596) [Agent 1/2 finding]
- `scripts/little_loops/cli/issues/link_epics.py` — `add_link_epics_parser` `description=` / `--mode` help / epilog (~:581–615) and the module docstring both define "orphan" as `parent:`/`epic:` unset; update to name the exclusions [Agent 2 finding]
- `scripts/little_loops/issue_parser.py` — `IssueParser.parse_file` / `IssueInfo.from_file` (~:4221–4357) read only `parent`/`epic` (with `parent_issue` alias); if the markers become `IssueInfo` fields, `IssueInfo.to_dict()`/`from_dict()` (~:4111–4158) are hand-listed and need entries. `IssueParser._coerce_tristate_bool` (used for `testable`/`decision_needed`) is a reusable coercion helper for `standalone` [Agent 2 finding]
- `scripts/little_loops/frontmatter.py` — `_iter_frontmatter_blocks` / `_HEADER_BOUNDARY_RE` / `_mask_fenced_code` define the fence geometry the detector must agree with; `has_multiple_frontmatter_blocks` is the raw-content precedent called before the template early returns [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — states `normalize_structure` / `precheck_format` run `ll-issues format-check <id> --fix --apply || true` (single-issue, `sweep=False`) on every refine pass, so a new `_REPAIR_DISPATCH` entry will fire automatically there; exit code ignored, only `directive_gaps` is read [Agent 2 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` — `ensure_formatted` gates on `ll-issues format-check "$ID"` exit code (`on_no`/`on_error` → `format_issue`); a new blocking gap kind routes post-fence issues to the `/ll:format-issue --auto` fallback [Agent 2 finding]
- `skills/format-issue/SKILL.md` — `--check` mode forwards the format-check exit code as the gate result; a new blocking kind changes what exits `1` [Agent 2 finding]
- `scripts/little_loops/cli/issues/normalize.py` — `_REFERENCING_KEYS` (`blocked_by`, `depends_on`, `parent`, `epic`, …) rewrites ID-bearing keys on reassignment; `standalone`/`*_reason` hold no IDs, so no change, but a detector's key set should stay consistent with it for `parent`/`epic` [Agent 2 finding]
- Not consumers (verified, no change): `next_obligation.py`, `run_record.py`, `check_design.py`, `preparation_policy.py` — they import `check_format_gaps` but read derived predicates (`directive_gaps`, `design_gate_failed`), not the field set; `has_blocking_gaps` derives from `dataclasses.fields(self)` so the new field is blocking automatically unless named in `_ADVISORY_GAP_CLASSES`

### Conventions in Force
- A format-check gap kind is a `list[str]` `FormatGaps` field, rendered by `_print_gaps`, and covered by a structural guard that fails if a field is not rendered — evidence: `test_every_format_gaps_field_is_rendered` in `scripts/tests/test_ll_issues_format_check.py`, `TestAdvisoryGapClasses` in `scripts/tests/test_issue_parser.py`
- Gap kinds are blocking unless named in `_ADVISORY_GAP_CLASSES`; blocking drives the exit code — evidence: `FormatGaps.has_blocking_gaps`
- Body-rewriting `--fix` repairs preview without `--apply`, are idempotent, are fence-safe, and are excluded from `--all` sweeps — evidence: `TestFormatCheckDuplicateHeadingFix`, `test_sweep_mode_does_not_write_body`
- Opt-out frontmatter flags are human-set and read from `parse_frontmatter` output — evidence: `program_design_not_applicable` in `issues/program_design.py`, `behavior_parity_not_applicable` in `check_format_gaps`
- New `--json` keys on link-epics are conditional/additive — evidence: the `deep` key in `cmd_link_epics`, `test_deep_end_to_end_json_output`

### Tests
- `scripts/tests/test_link_epics_cli.py` — `TestLinkEpicsCLI` (`_run` patches `sys.argv`, calls `main_issues()`), `TestProposeAssignments`; the AC's orphan/skip cases land here
- `scripts/tests/test_ll_issues_format_check.py` — per-kind `TestFormatCheck<Kind>` classes, golden `TestFormatCheckJsonOutput.test_clean_issue_json_output` (must gain the new key)
- `scripts/tests/test_issue_parser.py` — detector-level `check_format_gaps(path).<field>` tests
- `scripts/tests/test_link_epics_skill.py` — string-presence tests on `SKILL.md`; `test_issue_without_parent_is_orphan` exercises `parse_frontmatter`, not `is_orphan`
- `scripts/tests/test_epic_consistency.py` — `TestEpicConsistencyCategoryB` holds the category-(b) contract

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py` — `TestFormatCheckTestableRendering::test_every_format_gaps_field_is_rendered` builds `FormatGaps(**{name: [f"sentinel-{name}"]})`, so the new field must be `list[str]`, counted in `has_gaps`, and rendered in `_print_gaps` (or listed in `_TEXT_RENDER_EXEMPT`); `TestFormatCheckJsonOutput::test_gapped_issue_json_output` is a sibling of the golden test [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py` — new `TestFormatCheckPostFenceKeys` modelled on `TestFormatCheckDuplicateHeadingFix` (private writer helper; `test_detected_…`, `test_fix_without_apply_previews_and_does_not_write`, `test_fix_apply_…_is_idempotent`, `test_sweep_mode_does_not_write_body`, `test_fence_safety_leaves_file_byte_identical`); also add `_REPAIR_DISPATCH` membership and not-in-`_SWEEP_SAFE_REPAIRS` pins (model: `TestDirectiveGapsAndStatusFixer::test_missing_status_not_sweep_safe`, `TestTemplatePlaceholderFixableAllowlistInvariant`) and a `json.loads(out)[<key>]` test (model: `TestFormatCheckInvisibleChars::test_json_key`) [Agent 3 finding]
- `scripts/tests/test_issue_parser.py` — new detector-level class beside `TestInvisibleCharDetection` (~:7016): keys after fence flagged; clean file, `Note: …` prose, `---` horizontal rule, and fenced yaml in body not flagged; fires when template/type unresolved [Agent 3 finding]
- `scripts/tests/test_frontmatter.py` — `TestMultiFrontmatterBlocks` (`_DOUBLE_BLOCK`, `test_fenced_yaml_block_in_body_not_treated_as_second_block`, `test_body_horizontal_rule_pair_not_treated_as_second_block`) are the false-positive guards to mirror; the `multi_frontmatter` fixtures put a block after `# Title`, so confirm the new detector does not double-fire on `TestFormatCheckMultiFrontmatter::test_double_frontmatter_block_exits_one` [Agent 3 finding]
- `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py` — `test_check_format_gaps_spawns_no_subprocess` forbids subprocess use inside `check_format_gaps`; the detector must be pure text [Agent 3 finding]
- `scripts/tests/test_bug3708_verify_issues_b8.py` — imports `_ADVISORY_GAP_CLASSES` and asserts none of those keys appear in a doc/command text; if the new kind is made advisory it enters that assertion's scope [Agent 2/3 finding]
- `scripts/tests/test_confidence_check_skill.py` — `TestConfidenceCheckStructGapPrefetch::test_phase_1_8_documents_remedy_split` (~:698) pins the literal `` `--fix --apply` repairs only a `` and `` frontmatter-derivable `template_placeholders` `` in `skills/confidence-check/SKILL.md` Phase 1.8; rewording that sentence for the new fixer requires updating the test in the same change [Agent 2/3 finding]
- `scripts/tests/test_link_epics_cli.py` — new cases via `TestLinkEpicsCLI._run` + `json.loads(capsys.readouterr().out)`: `standalone: true` skipped, `standalone: false` still proposed, `parentless_reason` skipped, Children-listed skipped (bullet and `### FEAT-NNN —` heading forms), counters present in assign and synthesize payloads, control orphan still proposed. Existing fixtures (~L162/182/229/266) have empty `## Children` so none break; assertions are key-by-key so additive counters are safe, and `test_deep_end_to_end_json_output` (`"deep" not in out`) is the conditional-key precedent [Agent 3 finding]
- `scripts/tests/test_link_epics_cli.py` — no test calls `is_orphan` directly (`test_link_epics_skill.py::TestParentlessIssueDetection` tests `parse_frontmatter` only); add a direct `is_orphan` / skip-helper unit test [Agent 3 finding]
- `scripts/tests/test_link_epics_skill.py` — if `skills/link-epics/SKILL.md` prose is edited, it must avoid the banned terms (`--min-score`, `--min-cluster`, `Jaccard`, `union-find`, `words1 & words2`, `intersection`) and keep `argument-hint:` with `--mode`/`--threshold` [Agent 3 finding]
- `scripts/tests/test_docs_audience_gate.py` — scans `README.md`, `docs/guides`, `docs/reference`, `skills/**/*.md`; new doc text must not cite `scripts/tests/`, `scripts/little_loops/`, or "this repo" [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — `ll-issues link-epics` JSON shape (~3237) and `format-check` fix-kind list (~2894–3004)
- `docs/reference/API.md` — per-gap-kind bullets (~905–935) and link-epics orphan/skip description (~1479, ~1553)
- `skills/link-epics/SKILL.md` — edits here trip the mirror gates (`ll-adapt --host <gemini|kimi-code|qwen> --apply`, README copy sync)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — beyond the known ranges: `format-check` intro paragraph ("twenty-eight classes", re-derive from `fields(FormatGaps)`), the Examples `--format json` key list and the `format-check ENH-2426 --fix --apply` line listing repaired classes, and the `link-epics` intro ("orphan issues (open BUG/FEAT/ENH with no `parent:`/`epic:`)") [Agent 2 finding]
- `docs/reference/API.md` — `## little_loops.cli.issues.link_epics` header sentence defining "orphan", `propose_assignments`/`synthesize_clusters` parameter tables ("Candidate orphan issues"), and the `#### check_format_gaps` intro ("twenty-eight gap classes", count to be re-derived) [Agent 2 finding]
- `docs/reference/ISSUE_TEMPLATE.md` — frontmatter-fields table has a `parent` row but no `epic`/`standalone`/`standalone_reason`/`parentless_reason` rows; the natural home for the new marker vocabulary, currently documented nowhere [Agent 2 finding]
- `docs/reference/COMMANDS.md` — `### /ll:link-epics` (~:460–469) describes discovery of "parentless open issues"; add the skip/drift reporting [Agent 2 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — sample frontmatter block (`parent: ENH-040`) and the `link-epics ← wire unparented issues` pipeline line (~:82, ~:229) [Agent 2 finding]
- `skills/confidence-check/SKILL.md` — Phase 1.8 `STRUCT_GAP` paragraph says `--fix --apply` repairs only a missing `Status` and frontmatter-derivable `template_placeholders`; inaccurate once a new `_REPAIR_DISPATCH` entry lands (coupled to the pinned test above) [Agent 2 finding]
- `commands/verify-issues.md` — Check B8 reads the format-check JSON blocking-gap lists; new key becomes visible in that payload (additive, no edit required) [Agent 2 finding]

### Configuration
- None; `issues.link_epics.min_score` is unaffected.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Anchor correction**: the sole caller of `_parse_children_body` is `epic_consistency.py:193` inside `compute_drift` (defined `:141`), not `:201` as the Dependent Files bullet above states; `compute_drift` itself is called at `:326` and `:341` (both inside `cmd_epic_consistency`). `is_orphan` is defined at `link_epics.py:164`, sole caller `:651` — both confirmed against the code graph (codegraph, fresh).
- **Other readers of `parent:`/`epic:` that are equally blind to post-fence keys** (not orphan consumers, so no change required; they bound the blast radius of a misplaced key): `issue_progress.py:95-106` (parent chain walk), `parallel/worker_pool.py:1950`/`:1984` (parent walk, `parent_map`), `cli/sprint/run.py:305`, `cli/issues/list_cmd.py:56`/`:164`, `cli/issues/clusters.py:544`/`:733`, `cli/issues/search.py:442`, `mcp_server/tools.py:124`. A misplaced `parent:` is therefore invisible to sprint EPIC resolution and progress rollups as well as `link-epics`.
- **Nearest key-set precedents** (the "no known-key registry exists" finding above holds for *issue keys generally*, but two relationship-key sets exist): `frontmatter.py:54` `DEPRECATED_FRONTMATTER_KEYS` (`superseded_by`, `parent_issue`, `target_branch`, `related`) and `normalize.py` `_REFERENCING_KEYS`; a third hand-written set is `dependency_mapper/analysis.py:487` `_DEPRECATED_RELATIONSHIP_KEYS`. The detector's bounded set must stay consistent with these three, since each already names `parent`/`epic`/`parent_issue`.
- **Byte-preserving frontmatter edit helpers**: `frontmatter.py:474` `remove_frontmatter_keys()` (span-bounded by `_iter_frontmatter_blocks`, preserves surviving keys byte-for-byte) and `cli/migrate_labels.py:26` `_set_labels_frontmatter()` (regex replace or insert at the closing-fence position). No shared "insert a key line" helper exists; both are single-purpose.
- **Fence-masking has two implementations**: `frontmatter._mask_fenced_code` (blanks fences to same-length whitespace) and `text_utils.py:64` `fence_spans` / `:97` `in_fence` (span lists, BUG-3202). `_parse_children_body` / both `_section_bounds` are *not* fence-aware; `issue_parser._section_body_with_offset` is.
- **Additional doc/config surfaces using the "orphan"/"parentless" wording** (wording only, no behavior): `scripts/little_loops/config-schema.json:168-174` (`link_epics` description), `scripts/little_loops/config/features.py` `LinkEpicsConfig` (~:156, :348, :389), `docs/reference/CONFIGURATION.md:341`, `skills/link-epics/agents/openai.yaml:3` (`short_description`), `skills/review-epic/SKILL.md:101`, `skills/capture-issue/SKILL.md:495`, `skills/issue-workflow/SKILL.md:77`/`:164`, and the `link-epics` listing in `.claude/CLAUDE.md:89` / `AGENTS.md:89`.
- **Regression net for fence geometry**: `scripts/tests/test_migrate_relationships.py:12` imports `_iter_frontmatter_blocks` directly; any change to `frontmatter.py` fence handling is covered there.
- **Overlap with BUG-3738**: it shares the `apply_assignment` write path with this issue's `link-epics` half, but this issue's orphan-set changes sit upstream of `apply_assignment` (in `cmd_link_epics`), so neither fix depends on the other landing first. Ordering check: if BUG-3738 changes `cmd_link_epics`'s proposal/`applied` bookkeeping, the new skip counters here must be re-checked against it.
- **Marker vocabulary confirmed new**: repo-wide search for `standalone_reason`, `parentless_reason`, and a `standalone:` frontmatter key finds hits only in this issue file (and built `site/` output). The `worker_pool.py:206`/`:1335` "standalone issues" comments mean "issue with no EPIC branch" — a different concept from the `standalone: true` marker.

## Program Design

### Types
- `FormatGaps.multi_frontmatter: list[str]` — the shape a post-fence gap field mirrors (`list[str]`, one message per finding)
- `IssueInfo.parent: str | None`, `IssueInfo.epic: str | None` — the only relationship fields `is_orphan` can see today
- `EpicProposal` — `to_dict()` returns `{"orphan_id","epic_id","score","tier"}`; unchanged by this fix

### Signatures
- `check_format_gaps(issue_path, templates_dir=None, issue_statuses=None, ref_index=None, symbol_index=None, cli_index=None, *, examined_refs=None, project_root=None) -> FormatGaps` — hosts the new detector
- `is_orphan(info: IssueInfo) -> bool` — body today is `return prefix in _ORPHAN_TYPE_PREFIXES and info.parent is None and info.epic is None`
- `cmd_link_epics(config: BRConfig, args: argparse.Namespace) -> int` — builds `orphans` from `find_issues(...)` and emits both payloads
- `compute_drift(epic_id: str, all_issues: list[IssueInfo]) -> EpicDrift | None` — category (b) is `body_real_ids - parent_children`
- `parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]` — values are strings under `BaseLoader`

### Call Path
`main_issues` -> `cmd_format_check` -> `check_format_gaps` -> `FormatGaps` -> `_apply_fix_dispatch`

`main_issues` -> `cmd_link_epics` -> `find_issues` -> `is_orphan` -> `propose_assignments` -> `apply_assignment`

### Decision Rules
- **Post-fence key gap**: input is raw file text; trigger is a `key: value` line, with `key` in a bounded set that includes `parent`, `epic`, `standalone`, `standalone_reason`, `parentless_reason`, located contiguously after the closing fence of the first block and before the first blank line or heading; any other line shape (e.g. `Note: ...` prose) does not trigger. Blocking by default; escape hatch is moving the key inside the block.
- **Intentional-parentless skip**: an orphan candidate is skipped when `standalone` coerces true (`true|yes|1`, case-insensitive; `"false"` is not true) or `parentless_reason` is non-empty; skipped issues are counted, not proposed.
- **Children-listed skip**: an orphan candidate whose ID is in `real_ids` of any considered EPIC's `## Children` body is excluded from proposals and reported separately as category-(b) drift; EPIC-prefixed IDs are not candidates. Whether closed EPICs are considered is an open choice (see Proposed Solution findings).

## Impact

- **Priority**: P3 - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Steps to Reproduce

1. In any issue, move `parent: EPIC-NNN` to the line after the closing `---`.
2. Make sure that EPIC's `## Children` lists the issue.
3. Run `ll-issues link-epics --mode assign --json`: the issue appears as an orphan.
4. Add `parentless_reason: ...` inside the frontmatter of a different orphan and run again: it is still proposed.

## Root Cause

The frontmatter parser rightly stops at the closing fence, but there is no lint for frontmatter-shaped lines that land just past it. `link-epics` builds its orphan set only from frontmatter `parent`/`epic` and does not cross-check EPIC bodies or the intentional-parentless markers.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **File**: `scripts/little_loops/frontmatter.py` — **Anchor**: `_iter_frontmatter_blocks()` parses only each fence pair's `body_span`, and the header region ends at the first `^##[ \t]` line (`_HEADER_BOUNDARY_RE`). A `key: value` line directly after the closing `---` is outside every block, so `parse_frontmatter()` never returns it and `IssueParser.parse_file` (`issue_parser.py`) leaves `IssueInfo.parent`/`.epic` as `None`.
- **File**: `scripts/little_loops/cli/issues/link_epics.py` — **Anchor**: `is_orphan(info: IssueInfo) -> bool` reads only `info.issue_id`, `info.parent`, `info.epic`. `IssueInfo` carries no field for `standalone`, `standalone_reason`, or `parentless_reason`, and no raw frontmatter dict, so the intentional markers are unreachable from `is_orphan` even when correctly placed. `cmd_link_epics` builds `orphans = [i for i in all_issues if is_orphan(i)]` and never reads any EPIC's `## Children` body.
- **Lint gap**: `check_format_gaps()` (`issue_parser.py`) has no detector for frontmatter-shaped lines past the fence. The nearest existing frontmatter-structure gap is `multi_frontmatter` (`has_multiple_frontmatter_blocks`), which is report-only and does not see this shape.
- **Corpus state**: a scan of this repo's `.issues/` found 0 files whose line after the closing fence is a known frontmatter key, so a new blocking gap kind would not fail `format-check --all` here on day one. Downstream projects are the affected population.
- **Naming**: `ll-issues verify` named in the issue does not exist; `ll-issues format-check` is the only issue-format lint surface.
- **Marker vocabulary is new**: `standalone`, `standalone_reason`, and `parentless_reason` have zero readers, templates, schema entries, or docs outside this issue — the convention is defined by this fix, not inherited.

## Implementation Steps

1. `format-check` reports post-fence known keys as a blocking gap naming file and key, firing even when the issue's template cannot be resolved; `test_every_format_gaps_field_is_rendered` and the golden JSON test in `test_ll_issues_format_check.py` still pass with the new field.
2. `format-check --fix --apply` moves the lines inside the closing fence without reformatting the rest of the block, is idempotent, leaves fenced code untouched, previews without `--apply`, and does not write under `--all`.
3. `link-epics` excludes intentional-parentless issues (coercion per Decision Rules) and Children-listed issues from the orphan set in both modes, reporting each count in `--json` additively, with `skills/link-epics/SKILL.md` still parsing the payloads.
4. Coverage exists in `test_link_epics_cli.py` (each skip case plus a control orphan still proposed) and in the format-check/detector test modules; `python -m pytest scripts/tests/test_link_epics_cli.py scripts/tests/test_ll_issues_format_check.py scripts/tests/test_issue_parser.py scripts/tests/test_link_epics_skill.py` passes.
5. `docs/reference/CLI.md` and `docs/reference/API.md` describe the new gap kind and payload keys; mirror gates pass after any `skills/link-epics/SKILL.md` edit.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/issues/__init__.py` — add the new kind to the `main_issues` epilog's `format-check` line (~:184)
- Update `scripts/little_loops/cli/issues/format_check.py` — add the kind to the `add_format_check_parser` `help=` CSV, the `--fix` help text, and the `cmd_format_check` docstring list, alongside the `_print_gaps` loop
- Update `scripts/little_loops/cli/issues/link_epics.py` — reword the parser `description=`/epilog and module docstring "orphan" definition to name the standalone/parentless/Children-listed exclusions
- Decide marker plumbing — either add `IssueInfo` fields (then extend `IssueInfo.to_dict()`/`from_dict()` and `IssueInfo.from_file`) or read markers from raw frontmatter in `cmd_link_epics`; coerce `standalone` via `IssueParser._coerce_tristate_bool` or `_is_true`-style `true|yes|1`, never plain truthiness
- Keep the new `_REPAIR_DISPATCH` fixer out of `_SWEEP_SAFE_REPAIRS`; note `refine-to-ready-issue.yaml` (`normalize_structure`, `precheck_format`) runs `format-check --fix --apply` per issue and will invoke it, so the fixer must be idempotent and byte-preserving outside the moved lines
- Keep the detector pure text (no subprocess; `test_check_format_gaps_spawns_no_subprocess`) and mirror `TestMultiFrontmatterBlocks` false-positive guards (`---` rules, fenced yaml)
- Update `scripts/tests/test_ll_issues_format_check.py` — extend `test_clean_issue_json_output` (and sibling `test_gapped_issue_json_output`), satisfy `test_every_format_gaps_field_is_rendered`, add `TestFormatCheckPostFenceKeys` modelled on `TestFormatCheckDuplicateHeadingFix`
- Update `scripts/tests/test_issue_parser.py`, `scripts/tests/test_link_epics_cli.py`, `scripts/tests/test_epic_consistency.py` (regression net if `_parse_children_body` is made public/renamed)
- Update `scripts/tests/test_confidence_check_skill.py::test_phase_1_8_documents_remedy_split` together with `skills/confidence-check/SKILL.md` Phase 1.8 if the `--fix --apply` sentence is reworded
- Update `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/ISSUE_TEMPLATE.md` (new marker keys), `docs/reference/COMMANDS.md` (`/ll:link-epics`), `skills/link-epics/SKILL.md`; run mirror gates (`ll-adapt --host <gemini|kimi-code|qwen> --apply`) after any skill edit

## Acceptance Criteria

- [ ] The lint flags `parent:` / `epic:` / `parentless_reason:` / `standalone:` placed after the closing fence, and `--fix` moves them inside.
- [ ] `link-epics` skips issues with `standalone: true` or `parentless_reason:` and reports a skipped-intentional count.
- [ ] `link-epics` reports a Children-listed-but-no-backref issue as drift instead of proposing it as an orphan.
- [ ] Tests cover each case in `test_link_epics_cli.py` and the lint's test module.

## Status

**Open** | Created: 2026-10-05 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-10-05T19:59:00 - `82de079c-5cd6-4104-ba4d-1ae5be5a2a7d.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T19:56:33 - `028b082b-4804-4e7c-9920-43f4adff3a93.jsonl`
- `/ll:wire-issue` - 2026-10-05T19:48:40 - `cca3c87c-937f-4367-b92b-642516bd4f0e.jsonl`
- `/ll:refine-issue` - 2026-10-05T19:39:52 - `84fa6018-8b93-4b53-8e45-1f0de0127b76.jsonl`
