---
id: ENH-3319
type: ENH
title: Rewrite baked-in design-token literals to var() references in templatize output
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-25'
captured_at: '2026-08-25T16:04:10Z'
parent: EPIC-3299
labels:
- artifact
- ll-artifact
- templatize
---

# ENH-3319: Rewrite baked-in design-token literals to var() references in templatize output

## Summary

`ll-artifact templatize`'s `_report_unlifted_tokens` (`templatize.py:717-740`)
only *reports* baked-in color literals matching known design tokens
(`unlifted-tokens.json`) — it never rewrites the spliced template body to
reference `var(--...)` / the artifact template kit's stamping unit
(`artifact_template_kit.themed_css_vars`, ENH-3035). File real
literal→`var(--...)` rewriting as its own feature.

## Current Behavior

`ll-artifact templatize` produces a spliced `.j2` template body via
`apply_regions` (`scripts/little_loops/cli/artifact/templatize.py:474`),
writes it to disk, and verifies it round-trips byte-for-byte against the
original artifact via `verify_round_trip` (`templatize.py:545`). Only after
that verification succeeds does `cmd_templatize` call
`_report_unlifted_tokens` (`templatize.py:717`, invoked at `templatize.py:923`),
which decodes the already-final `spliced` bytes and calls
`report_token_literals` (`templatize.py:662`) to scan for `#`-hex /
`rgb()`/`rgba()`/`hsl()`/`hsla()` literals whose normalized value matches a
resolved design token (`DesignTokens.resolved`). Matches are written to
`unlifted-tokens.json` as `{"literal", "candidate_names", "occurrences"}`
entries — no byte offsets are captured; the regex match spans are read for
`.group(0)` only and discarded — and logged as a warning. The template body
on disk is never modified. `_report_unlifted_tokens`'s entire body is wrapped
in a bare `except Exception` (`templatize.py:717-740`) specifically so
nothing in this step can affect `cmd_templatize`'s exit code or block
`promote()`.

## Expected Behavior

A baked-in literal matching a resolved design token gets rewritten, in the
spliced template body, to a `var(--...)` reference (or another substitution
compatible with `artifact_template_kit.themed_css_vars`/`stamp_page_shell`,
ENH-3035) at the literal's own byte span, instead of only being reported.
`verify_round_trip` (`templatize.py:545`) must still pass: it diffs
`render_template`'s output against the *original pre-splice* artifact bytes,
so a rewritten template has to render back to the exact original literal —
today's Jinja rendering path (`ArtifactTemplate`/`render_template` in
`little_loops/artifact_templates.py`) has no design-token-aware substitution
step to do that (see Program Design below).

## Motivation

ENH-3035's Decisions (2026-08-25) explicitly rejected doing this as part of
the template-kit extraction: setting `manifest["theme"] = "design-tokens"`
whenever `_report_unlifted_tokens` finds matching literals would stamp
`theme_css` vars into a body that still carries the literals — unreferenced
vars *and* unlifted literals, not token lifting. Real lifting requires
locating each literal's span in the template body and splicing in a
`var(--...)` reference (or an `[[= ll.theme_css =]]`-style stamp point),
which is new feature work, not the extraction ENH-3035 scoped.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` — `report_token_literals` (`:662`) must expose byte-span data per match (today's `UnliftedToken` shape carries only `literal`/`candidate_names`/`occurrences`); any rewrite must compose into `apply_regions`'s (`:474`) existing sorted, non-overlapping span model rather than a second pass over already-spliced bytes.
- `scripts/little_loops/artifact_template_kit.py` — `themed_css_vars`/`stamp_page_shell` (`:18`, `:52`) is the existing stamping unit; it only fires against a hardcoded `/*__THEMED_CSS_VARS__*/` placeholder and `data-theme="light"` attribute today, and is a silent no-op on a body carrying neither.
- `scripts/little_loops/design_tokens.py` — `tokens.resolved` is the shared source of both the literal-matching inversion in `report_token_literals` and the `--name-with-dashes: value;` declarations `render_as_css_vars_themed` emits; the `var(--...)` naming convention already exists on this path even though nothing wires the two together today.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/templatize.py:923` — `cmd_templatize` calls `_report_unlifted_tokens` after `verify_round_trip` succeeds and before `promote()`.
- `scripts/little_loops/cli/artifact/templatize.py:731` — `_report_unlifted_tokens` calls `report_token_literals`.
- `scripts/little_loops/cli/artifact/policy_builder.py:61,68` — the one existing consumer of `themed_css_vars`/`stamp_page_shell`, for reference on how the stamp point is currently invoked.

### Conventions in Force
- This module's one span-splicing pass (`apply_regions`, `templatize.py:474-511`) sorts `(start, end, kind, obj)` tuples and hard-errors via `SpliceError` on overlap/out-of-bounds rather than best-effort merging — any literal-rewrite span must compose into this same list, not a second independent rewrite over already-spliced bytes.
- Splice/round-trip tests assert exact byte equality and error paths via `pytest.raises(SpliceError, match=...)` — evidence: `test_artifact_templatize.py::TestApplyRegions` (`:208-325`).
- Literal matching in this codebase is regex-based over rendered text plus a normalization step (`_normalize_color_value`/`_normalize_hex`), not AST/CSS parsing — evidence: `templatize.py:622-695`.
- A report-only feature graduating to an active rewrite is filed as a separate issue rather than gated behind a flag on the existing function — evidence: ENH-3035's Decisions (2026-08-25) explicitly deferred this rewrite to a new ENH (this issue), rejecting a `manifest["theme"]`-stamping shortcut as "dead weight, not token lifting."

### Tests
- `scripts/tests/test_artifact_templatize.py` — `TestReportTokenLiterals` (`:995`), `TestCmdTemplatizeTokenReport` (`:1057`), `TestApplyRegions` (`:208-325`), and `TestCmdTemplatizeEndToEnd.test_end_to_end_round_trip` (`:403-440`) — the only existing byte-identical round-trip regression test in this codebase.
- `scripts/tests/test_enh3035_artifact_template_kit.py` — covers `themed_css_vars`/`stamp_page_shell`.
- `scripts/tests/test_design_tokens.py` — covers `DesignTokens`/`.resolved`.

### Documentation
- `docs/reference/CLI.md` (`## ll-artifact templatize`, ~`:4545`) documents today's report-only `unlifted-tokens.json` behavior; needs updating once rewriting lands.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

### Types
- `UnliftedToken` (TypedDict, `templatize.py:616`): `{"literal": str, "candidate_names": list[str], "occurrences": int}` — carries no byte-offset/span data today; a rewrite needs positional data this type does not currently hold.

### Signatures
- `report_token_literals(template_text: str, tokens: DesignTokens) -> list[UnliftedToken]` (`templatize.py:662`) — regex match objects (which carry `.start()`/`.end()`) are read for `.group(0)` only and discarded; no span-returning variant exists.
- `apply_regions(artifact: bytes, result: DiscoveryResult) -> bytes` (`templatize.py:474`) — the only span-splicing entry point in this module; consumes `Region`/`RegionGroup` spans, not literal-match spans.
- `themed_css_vars(config: object) -> str` (`artifact_template_kit.py:18`); `stamp_page_shell(template_text: str, *, active_theme: str, css_vars: str) -> str` (`artifact_template_kit.py:52`) — stamps only against a hardcoded `/*__THEMED_CSS_VARS__*/` placeholder and `data-theme="light"` attribute; a no-op on text without them.
- `verify_round_trip(template_dir: Path, data: dict[str, Any], original: bytes, config: object) -> str | None` (`templatize.py:545`) — diffs `render_template`'s output against the pre-splice `artifact_bytes`, never against `spliced`.

### Call Path
`cmd_templatize` -> `apply_regions` (produces `spliced`, written to disk) -> `verify_round_trip` (must still pass against the original pre-splice bytes) -> `_report_unlifted_tokens` -> `report_token_literals` -> [new rewrite step, not yet implemented] -> `promote`.

### Decision Rules
- **Ambiguous literal-to-token mapping**: `report_token_literals`'s `value_to_names` inversion is one-to-many — multiple token names can normalize to the same literal value. A rewrite must resolve one `candidate_name` per occurrence (or otherwise handle the ambiguity); no rule for this exists today, and `report_token_literals`'s current output does not privilege any one candidate.
- **Round-trip compatibility**: because `verify_round_trip` compares `render_template`'s output to the original literal bytes, a `var(--...)` substitution is only viable if it is reversible back to the exact original literal at render/verify time — e.g. via a render-time, design-token-aware substitution step that does not exist in `ArtifactTemplate`/`render_template` today. Absent that mechanism, a rewritten template fails `verify_round_trip` and lands in the `rejected_dir`/exit-code-2 path rather than reaching `_report_unlifted_tokens`.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

1. `report_token_literals` (or a sibling function) exposes byte-span data per matched literal — today's `UnliftedToken` shape (`literal`, `candidate_names`, `occurrences`) has none, even though the underlying regex matches carry `.start()`/`.end()`.
2. Any rewrite composes into `apply_regions`'s existing sorted, non-overlapping span model (`templatize.py:474-511`) rather than a second pass over already-spliced bytes, preserving the `SpliceError` overlap/out-of-bounds guarantees `TestApplyRegions` already asserts.
3. `verify_round_trip` continues to pass for a template containing a rewritten reference — i.e., rendering resolves the reference back to the exact original literal bytes — covered by extending `TestCmdTemplatizeEndToEnd.test_end_to_end_round_trip` (or an equivalent new byte-identical round-trip test).
4. `python -m pytest scripts/tests/test_artifact_templatize.py -v` passes.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Scope

- Design how a baked-in literal is matched back to its owning design-token
  name reliably (today's report only checks value equality against resolved
  tokens, per `report_token_literals()`).
- Splice a reference in place of the literal span, using the same
  span-splicing machinery `templatize.py` already has for extracted-data
  regions (`apply_regions`/`_splice_group`).
- Preserve the byte-exact round-trip guarantee `templatize` promotes under
  today for non-token regions.

## Status

**Open** | Created: 2026-08-25 | Priority: P4

## Acceptance Criteria

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- Given a spliced template body containing a color literal matching a resolved design token, `templatize` rewrites that literal's byte span to a `var(--...)` reference (or another stamp-compatible substitution) instead of only reporting it in `unlifted-tokens.json`.
- `unlifted-tokens.json`'s `unlifted` list reflects which literals were successfully rewritten versus left unlifted (rather than staying purely report-only for entries that were in fact rewritten).
- `verify_round_trip` continues to pass end-to-end for a template containing a rewritten literal (a `TestCmdTemplatizeEndToEnd`-style byte-identical assertion).
- An ambiguous literal-to-token-name match (`value_to_names` has more than one candidate) has a defined, tested resolution rule rather than silently picking an arbitrary candidate.


## Session Log
- `/ll:refine-issue` - 2026-08-25T20:20:19 - `c8f2587f-3ca1-4ca9-b1e5-e2886b741049.jsonl`
