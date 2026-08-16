---
id: BUG-3193
type: BUG
title: ll-issues create appends a duplicate empty template scaffold whenever body
  is a full sectioned markdown document
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
testable: true
decision_needed: false
depends_on:
- BUG-3202
captured_at: '2026-08-15T18:16:50Z'
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3193: ll-issues create appends a duplicate empty template scaffold whenever body is a full sectioned markdown document

## Summary

`ll-issues create` (and the `issue_capture` MCP tool that wraps it) maps the entire
`--body-file` / `body` payload into a single `content = {"Summary": spec.body}` slot
(`cli/issues/create.py:146`). Every *other* section in the chosen variant is then emitted
with its `creation_template` placeholder text. When a caller supplies a complete,
section-structured markdown body — which is what `capture-issue` and the `/ll:audit-docs`
sweep actually do — the result is the real body nested under `## Summary`, followed by a
full duplicate scaffold of empty placeholder sections. Observed hit rate: 6/6 on the
BUG-3186..3191 audit sweep.

**Scope of the `depends_on: [BUG-3202]` edge — now satisfied (BUG-3202 completed
2026-08-15).** BUG-3202's fix landed `text_utils.fence_spans` (line 64) and
`text_utils.in_fence` (line 97), and made `_section_body_with_offset` fence-aware. Note
what it deliberately did *not* change: section lookup remains **last-occurrence-wins**
(documented in `_section_body_with_offset`'s docstring), so this bug's unfenced trailing
scaffold still wins section resolution and still inverts `format-check` verdicts — the
premise of this issue is unchanged. The full-body detector below reuses
`fence_spans`/`in_fence` directly; no duplicate fence idiom is needed.


## Current Behavior

`_render_issue_content` (`scripts/little_loops/cli/issues/create.py:146`) builds the
section content map as:

```python
content = {"Summary": spec.body} if spec.body else {}
```

`assemble_issue_body` (`scripts/little_loops/issue_template.py:125`) then walks the
variant's `include_common` list and, for every section *not* present in `content`, emits
its `creation_template` placeholder (`_append_section`, `issue_template.py:196`). For the
default `minimal` variant that list is `Summary, Current Behavior, Expected Behavior,
Impact, Status` — exactly the block observed appended to all six sweep issues.

Reproduced verbatim via `render_issue_preview` (dry-run, nothing written) with a body
carrying its own section headings. Rendered output, with the emitted headings shown as
`>>` to keep this quotation from registering as real sections (see BUG-3202
for why that matters):

```
>> # <assigned-at-apply>: Throwaway repro
>>
>> ## Summary
>>
>> ## Summary        <-- caller's own heading, now one level of duplication deep
>>
>> Real summary text.
>> ... caller's real sections, including a real "## Status" ...
>>
>> ## Current Behavior
>>
>> [If applicable - describe what currently happens]
>>
>> ## Expected Behavior
>>
>> [What should happen instead]
>>
>> ## Impact
>>
>> - **Priority**: [P0-P5] - [Justification]
>> ...
>>
>> ## Status
>>
>> **Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
```

Two secondary consequences:

- **The caller's `## Summary` heading is doubled** — `assemble_issue_body` emits the
  heading *and* the body carries its own.
- **The placeholder sections land last**, after the caller's real ones — and section
  lookup is last-occurrence-wins by explicit contract:
  `_section_body_with_offset` (`scripts/little_loops/issue_parser.py:240`) takes
  `matches[-1]` (`:268`).

That second point makes this more than cosmetic. Because the placeholder copy wins,
`ll-issues format-check` reads the *scaffold* as the issue's real content and reports
`boilerplate: Current Behavior`, `boilerplate: Expected Behavior`, and `empty: Summary` on
issues whose real sections are fully written. The linter's verdict on every affected issue
is inverted: a complete issue is reported as unfinished. That is the actual cost of this
bug, and it is why the fix belongs upstream in creation rather than being hand-stripped
per issue.

Frontmatter `status:` remains the source of truth, so the duplicated `## Status` footer is
*not* a status-correctness bug. It does leave `session_log.append_session_log_entry`'s anchor on
`"\n---\n\n## Status"` (`scripts/little_loops/session_log.py:327-330`; the function is
defined at `:273`) ambiguous between two footers.

Both `--body-file` (`docs/reference/CLI.md:1584`, "contents become the `## Summary` body")
and the MCP `body` property (`mcp_server/tools.py:686`, "Summary section body") document
the payload as Summary-only, so a full sectioned body is technically caller misuse. But
there is **no way to express a full body through either surface**, the misuse is silent,
and the observed rate was 6/6 — the API shape invites the error it does not detect.

## Steps to Reproduce

No file is written — this uses the dry-run render path.

```bash
cat > /tmp/body.md <<'BODY'
## Summary

Real summary text.

## Current Behavior

Actual current behavior.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
BODY

python -c "
from pathlib import Path
from little_loops.config import BRConfig
from little_loops.cli.issues.create import IssueSpec, render_issue_preview
spec = IssueSpec(type='BUG', title='Throwaway repro', body=open('/tmp/body.md').read())
print(render_issue_preview(BRConfig(Path('.')), spec)['rendered_body'])
"
```

Observed: a doubled `## Summary` heading, the caller's sections, then a second full set of
placeholder sections (`Current Behavior`, `Expected Behavior`, `Impact`, `Status`).

> **Note for anyone running `format-check` on this issue.** The heredoc above contains
> literal `## Summary`, `## Current Behavior`, and `## Status` lines, so this file has
> duplicate H2s by construction — that block *is* the reproduction and must not be
> "cleaned up". With BUG-3202 landed (2026-08-15), section lookup is fence-aware, so
> these fenced quoted headings no longer override the real sections. The three
> `stale_file_ref` gaps on `.gemini/`, `.kimi-code/`, and `.qwen/` brace-expanded paths
> are BUG-3194's Finding 2 and remain expected until that issue lands.

Expected: the caller's body emitted once, with no placeholder duplicates.

To see the downstream consequence, run `ll-issues format-check <id>` against any issue
created this way before the scaffold is hand-stripped — it reports `boilerplate:` and
`empty:` for sections that are in fact written.

## Program Design

The full-vs-summary decision has exactly one correct home: `_render_issue_content`. Both
entry points (CLI `cmd_create` and MCP `_tool_issue_capture`) and both modes (apply via
`create_issue`, dry-run via `render_issue_preview`) funnel through it, so a single change
fixes every caller at once.

### Signatures

```python
def _render_issue_content(config: BRConfig, spec: IssueSpec, issue_id: str, now: datetime) -> str
def assemble_issue_body(sections_data: dict, issue_type: str, variant: str, issue_id: str, title: str, content: dict | None = None) -> str
def _append_section(parts: list, section_name: str, section_def: dict, content: dict) -> None
```

`_render_issue_content` (`scripts/little_loops/cli/issues/create.py:121`) builds
frontmatter, loads the per-type sections data, and passes
`content={"Summary": spec.body}` — the defect is that one literal.

`assemble_issue_body` (`scripts/little_loops/issue_template.py:125`) walks
`variant_config["include_common"]` and delegates each section to `_append_section`
(`:189`), which falls back to `section_def["creation_template"]` for any section absent
from `content`. A full-body mode needs either a bypass here or a `content` map populated
for every section so no fallback fires.

### Types

`IssueSpec` (`create.py:33`) carries the `body` and `variant` fields; an explicit
full-body mode (Expected Behavior option 2) would add a field here and default it to the
current behavior. `CreatedIssue` (`:47`) is unaffected.

### Call Path

- `cmd_create` — CLI entry, reads `--body-file` into `IssueSpec.body`.
- `_tool_issue_capture` — MCP entry, reads the `body` property into the same field.
- `create_issue` — apply path; calls `_render_issue_content` under the ID-allocation lock.
- `render_issue_preview` — dry-run path; calls `_render_issue_content` directly.
- `_render_issue_content` — the change site.
- `load_issue_sections` — supplies the variant table; `minimal` (the `ll-issues create`
  default) yields exactly the five sections observed in the duplicate block.
- `assemble_issue_body` → `_append_section` — emits the placeholder text.

The per-type sections JSON (`scripts/little_loops/templates/bug-sections.json` and its
`feat`/`enh`/`epic` siblings) defines the `creation_template` strings that leak, but needs
no change — they are correct as scaffold defaults.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/scaffold_epic.py:22,25,94-95,112,120` — `scaffold_epic()` calls `_render_issue_content()` directly (not through `create_issue`/`render_issue_preview`), once for the epic itself (`IssueSpec(type="EPIC", ..., variant="full")`, no body) and once per child (`IssueSpec(..., body=child.summary or None, variant="minimal")`). Confirmed by direct import/call-site grep. A fix placed in `_render_issue_content`/`assemble_issue_body` is picked up here automatically; child summaries are typically short prose today, not full sectioned docs, but any fix touching `IssueSpec`'s shape (e.g. Option 2's `body_mode` field) must confirm this call site's default still matches current behavior. Covered by `scripts/tests/test_ll_issues_scaffold_epic.py` and `scripts/tests/test_scope_epic_skill.py`.
- `scripts/little_loops/mcp_server/tools.py:263` — `_tool_issue_capture()` constructs `IssueSpec` and calls `create_issue`/`render_issue_preview`, already named in Program Design's Call Path but confirmed here as the concrete import site.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (`## little_loops.cli.issues.create` section, `IssueSpec` dataclass block) — reproduces the `IssueSpec` field list verbatim (`type`, `title`, `priority`, `body`, `parent`, `labels`, `stage`, `variant`). If Option 2 (`--body-mode` flag) is chosen and adds a `body_mode` field to `IssueSpec`, this code block needs the new field added.
- `scripts/little_loops/cli/issues/create.py:306-309` — the `--body-file` argparse flag carries its own hardcoded `--help` string ("Path to file with Summary body content, or '-' for stdin"), a separate coupling point from `docs/reference/CLI.md:1584`. Needs rewording under any option that changes the summary-only contract.
- Generated, non-canonical skill mirrors (`.gemini/skills/{capture-issue,scope-epic}/SKILL.md`, `.kimi-code/skills/{capture-issue,scope-epic}/SKILL.md`, `.qwen/skills/{capture-issue,scope-epic}/SKILL.md`) — host-adapter-generated copies of the canonical `skills/capture-issue/SKILL.md` and `skills/scope-epic/SKILL.md` (already in Related Key Documentation). Not hand-edited; once the two canonical files are updated, these regenerate via the adapt/sync tooling, not manual doc edits — flagged so the fix isn't considered complete without a regeneration step if the canonical files' `--body-file` guidance changes.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- No direct test coverage exists for `render_issue_preview()` (the dry-run path) in isolation — the only hit, `scripts/tests/test_feat_3149_mcp_mutation_tools.py::test_ac3a_capture_dry_run_has_no_issue_id_apply_does` (lines 332-364), exercises it transitively through the MCP `issue_capture` tool and only asserts `dry["rendered_body"]` is truthy, no structural assertion. New test to write: model on `test_ll_issues_create.py::TestCreateIssue.test_body_file_content_becomes_summary` (lines 114-119) but call `render_issue_preview` directly with a multi-section body, asserting no duplicate `## <heading>` occurrences and matching `create_issue`'s apply-path output for the same spec.
- `scripts/tests/test_issue_template.py::test_content_overrides` (lines 144-157) is the only existing test exercising the `content` dict at all, and it's single-key (`{"Summary": ...}`). No test passes a multi-key `content` dict and asserts against duplicate headings when combined with placeholder sections for the remaining ones — the direct model for a new `assemble_issue_body`/`assemble_issue_markdown`-level unit test.

### Codebase Research Findings — Program Design

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

- **Test coverage gap**: `scripts/tests/test_ll_issues_create.py::TestCreateIssue.test_body_file_content_becomes_summary` (line 114) and `TestCreateCli.test_create_body_file_stdin` (line 213) only assert substring containment against single-line prose bodies. Neither constructs a body containing embedded `## ` headings, and neither asserts on duplicate-heading counts or on `_section_body`/`_section_body_with_offset` resolution against a `create`-produced file. `scripts/tests/test_issue_template.py` covers `assemble_issue_body()`/`load_issue_sections()` directly but has the same gap. This is the primary uncovered surface for a fix.
- **Blast radius beyond format-check**: `_section_body`/`_section_body_with_offset` (`scripts/little_loops/issue_parser.py:240-278`) is called from more sites than `format-check` alone — `issue_parser.py:1270`, `:1338` (Proposed Solution lookup), `:1347` — and `scripts/little_loops/issues/fold_research_findings.py` also resolves sections by heading. Any of these inherit the same last-occurrence-wins exposure on a duplicate-scaffold issue, not only `format-check`'s reported gaps.
- **Confirmed shared render path**: both `render_issue_preview()` (`create.py:200`) and `create_issue()` (`create.py:254`) call the identical `_render_issue_content()` — a fix placed there (or in `assemble_issue_body`) is picked up by both dry-run and apply with no separate branch needed.

## Expected Behavior

Supplying a complete sectioned body should not produce a duplicate scaffold. Any of:

1. **Detect and route** — if the body is section-structured, treat it as a full body
   rather than as Summary text.

   **Option 1 has an undecided sub-choice, and the obvious implementation loses data.**
   `assemble_issue_body` (`issue_template.py:169-183`) emits *only* the sections named in
   `variant_config["include_common"]` plus the type sections. For the `minimal` default
   that is five names. So the natural-looking implementation — parse the incoming body
   into sections and use them to populate the `content` map, which also kills the doubled
   `## Summary` for free — **silently discards every caller section outside that list**:
   `Steps to Reproduce`, `Program Design`, `Root Cause`, `Related Key Documentation`. Those
   are exactly the sections the audit-sweep bodies carry. Two sub-options:

   - **1a — verbatim passthrough.** Emit the title heading, then the body as-is, no
     scaffold. No loss, but sections the caller *omitted* (`Impact`, `Status`) never
     appear, so the created issue immediately trips `format-check`'s `missing:` gaps.
   - **1b — merge (recommended).** Populate `content` from the parsed body so real
     sections replace their placeholders; keep the `creation_template` placeholder for any
     variant section the caller did *not* supply; and **append the caller's non-variant
     sections** after the variant block, in their original order. No loss, no missing
     sections, no doubled heading.

   1b is the target. The append-non-variant-sections half is the part most likely to be
   dropped during implementation, because 1b looks complete without it and no existing
   test would catch the loss — it is pinned in Acceptance Criteria below.

   The trigger must be stated precisely. "Opens with a `## ` heading" is **too narrow** —
   real sectioned bodies routinely open with prose, a lead paragraph, or a `_Added by …_`
   marker before the first heading, and would fall through to the broken path. Use
   instead: **the body contains any line matching `^##\s` whose heading text matches a
   section name in the resolved variant's `include_common` list.** That is the exact
   condition under which a duplicate is produced, so it neither over- nor under-triggers.
   Matching against variant section names (rather than any `##` line) also means a body
   that merely happens to contain an unrelated `## ` heading still gets its scaffold.

   Fence-awareness caveat: the detector must ignore `##` lines inside fenced code blocks,
   or a body that merely *quotes* a template will be misrouted as a full body. This is the
   same fence-unawareness BUG-3202 fixed in `_section_body_with_offset` — reuse the
   helper that fix exported (`text_utils.fence_spans`/`in_fence`) rather than adding a
   third idiom.

2. **Explicit flag** — add `--body-mode summary|full` (and a matching MCP property),
   defaulting to `summary` to preserve today's behavior.
3. **Reject loudly** — fail with a clear error when the body contains `## ` headings that
   collide with variant section names, pointing the caller at the intended contract.

### Decision (resolved 2026-08-15)

**Option 1b — detect and merge.** Detection uses the variant-section-name trigger stated
above (fence-aware, reusing `text_utils.fence_spans`/`in_fence`, exported by BUG-3202 —
landed 2026-08-15). On a full-body match,
`_render_issue_content` parses the body into sections and:

1. populates `content` so each caller-supplied section replaces its placeholder;
2. leaves the `creation_template` placeholder in place for any variant section the caller
   did **not** supply;
3. **places the caller's non-variant sections at their canonical positions** in the
   sections-data ordering table, with genuinely unknown headings appended before the
   footer in their original relative order. See the correction below — the original
   "append after the variant block" wording put real content after `## Status`.

Rationale, and what was weighed against it:

- 1b is the only option with no failure mode. 1a (verbatim passthrough) is smaller — maybe
  15 lines — but every issue it creates immediately trips `format-check`'s `missing:` gaps
  for `Impact` and `Status`, which trades this bug for a different one on the same
  surface.
- Option 2 (`--body-mode summary|full`) was rejected as a *standalone* fix because it does
  not stand alone: it still needs 1b's merge semantics to define what `full` emits, and it
  additionally forces a decision on whether to widen the MCP tool schema against the
  tier-2 narrowing precedent at `mcp_server/tools.py:319-323`. It remains available as a
  later explicitness layer on top of 1b, and is out of scope here.
- Step 3 is the load-bearing half and the one most likely to be dropped: 1b looks complete
  without it, and no existing test would catch the loss. It is pinned by the "no section is
  dropped" acceptance criterion, which counts H2s rather than checking substrings.

`scaffold_epic`'s child path is unaffected — child summaries are short prose with no `##`
lines, so they never trigger detection and keep taking the scaffold path unchanged.

#### Correction: "append after the variant block" is the wrong placement

Step 3 as originally written — append the caller's non-variant sections *after* the
variant block — produces a document whose `Steps to Reproduce`, `Program Design`,
`Root Cause`, and `Related Key Documentation` land **after** `## Status`. That is wrong on
two counts:

- **Status is the canonical footer.** The common-section ordering table in the sections
  data ends `… Related Key Documentation, Labels, Session Log, Status` (verified against
  `load_issue_sections("BUG")["common_sections"]`). Every hand-written and
  `refine-issue`-produced issue in `.issues/` follows it. Appending after the variant block
  puts real content below the footer and makes `create`-produced issues structurally
  unlike every other issue.
- **`session_log.append_session_log_entry`'s fallback anchors on the footer.** When an issue has no
  `## Session Log` section yet, `session_log.py:327-330` inserts one by replacing
  `"\n---\n\n## Status"`. With caller sections trailing after Status, the Session Log is
  inserted before a Status that now has several sections below it.

**The sections the caller supplies are not unknown headings** — but they do not all live
in one table. `Program Design` and `Related Key Documentation` are in `common_sections`;
`Steps to Reproduce` and `Root Cause` are in `type_sections` (BUG). There is **no single
ordering table containing all four**, so "canonical position" needs an explicit
interleaving rule. Note also that today's `assemble_issue_body` emits type sections
*after* the common loop — i.e. after `## Status` — under any `include_type_sections`
variant (`full`), so the footer-last invariant below is a property of the new merge
output, not of every existing scaffold shape.

Corrected step 3 (pinned interleaving rule): order the merge output by the
`common_sections` table, **inserting caller-supplied type sections (and any genuinely
unknown headings, in their original relative order) immediately before
`Related Key Documentation`/`Labels`/`Session Log`/`Status`** — never after the footer.
In the merge output, `## Status` is always emitted last, and `## Session Log` (when
present) immediately before it. This rule governs full-body merge output for the
`minimal` default; the `full` variant's existing type-sections-after-Status scaffold
placement is out of scope here and unchanged.

#### Four shapes 1b must define, not three

Two were already pinned below; the 2026-08-15 review found two more that the merge
algorithm as written has no answer for. Both are present in real caller payloads and both
fail silently.

- **Preamble — content before the first `##` heading.** The detection trigger above
  explicitly anticipates bodies that "open with prose, a lead paragraph, or a
  `_Added by …_` marker before the first heading" — but 1b's three steps (populate
  `content`, keep placeholders, append non-variant sections) define no destination for that
  text. It is keyed to no section, so the natural implementation drops it. **Decided
  (2026-08-15)**: fold the preamble into the `Summary` section's content ahead of the
  caller's own Summary text. The alternative (emit it verbatim between the title heading
  and the first section) was rejected because it can produce a document whose leading text
  sits outside every section, which is what `_section_body` callers assume away.

- **The caller supplies its own `## Status`.** Under 1b the caller's Status replaces the
  placeholder, so the generated `**Open** | Created: <date> | Priority: <P>` footer is
  **lost** — including the creation date, which nothing else regenerates. Both audit-sweep
  body shapes carry their own `## Status`. **Decided (2026-08-15)**: Status is exempt from
  the merge and always regenerated — it is machine-written metadata, not authored prose,
  and frontmatter is already the source of truth for `status:`. The caller-wins alternative
  was rejected because it silently carries whatever date the caller wrote.

The other two, already identified:

- **The caller supplies its own `## Session Log`.** Same shape as `## Status` and with the
  same resolution: it is machine-written metadata, appended to by
  `session_log.append_session_log_entry`, not authored prose. Exempt it from the merge and always emit the
  generated one, immediately before `## Status`. Without this, a caller body carrying a
  Session Log produces the same duplication this issue is about, on the one section whose
  duplication also confuses `session_log.append_session_log_entry`'s `rfind` anchor.

- **The body carries its own `# BUG-NNNN: title` H1.** `assemble_issue_body` emits its own
  title heading unconditionally (`issue_template.py:167`), so a verbatim or appended body
  doubles it. Strip a leading H1 from the incoming body, or emit no title heading in
  full-body mode — pick one and pin it.
- **The body carries its own frontmatter block.** `_render_issue_content` prepends
  `update_frontmatter("", frontmatter)`, so a body opening with `---` produces two
  frontmatter blocks and an unparseable file. Reject loudly rather than silently
  concatenating.

(The `scaffold_epic` child-path safety note above — `IssueSpec(..., body=child.summary,
variant="minimal")`, short prose with no `##` lines, confirmed against
`cli/issues/scaffold_epic.py` — was previously stated twice in this section; the duplicate
has been removed.)

### Codebase Research Findings — Expected Behavior

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

- **Option 2 (explicit flag) has an MCP-narrowing precedent to account for**: `_tool_issue_capture`'s `IssueSpec` construction (`scripts/little_loops/mcp_server/tools.py:253-313`) already omits `stage` and `variant` from the MCP tool schema even though both exist as `IssueSpec` fields the CLI exposes — the sibling `issue_set_status` tool documents this narrowing explicitly (`tools.py:319-323`, "tier 2's brief is four coarse tools, not a full mirror of the CLI's flag surface"). A new `--body-mode` flag following Option 2 would need an explicit decision on whether to extend the MCP schema too or accept the same narrowing.
- **No existing route-decision utility to reuse for Option 1**: the codebase's heading-extraction helpers (`_section_body_with_offset`, `_heading_bodies`, `_iter_h2_sections` in `scripts/little_loops/issues/program_design.py`) are read-only extraction/gap-checking utilities operating on already-written issue files; none of them are invoked from the `create.py` render path, and none decide whether to alter scaffold generation based on the incoming body's own heading structure. Option 1 would be new logic, not a reuse of an existing router.
- **`--variant` is the closest in-file precedent** for a flag that changes template-assembly behavior (`create.py:287-331` argparse → `IssueSpec.variant` field → `cmd_create` constructor kwarg), if Option 2 is chosen.

## Impact

- **Priority**: P3 - Silent and systematic (6/6 on the observed sweep), affects every
  issue created through the path most creation flows use, but the damage is cosmetic
  per-issue and hand-strippable. No data loss and no wrong frontmatter status.
- **Effort**: Small - One function (`_render_issue_content`) plus a template-assembly
  branch; tests already exist at `scripts/tests/test_ll_issues_create.py`.
- **Risk**: Low - Option 1 is additive and only triggers on bodies that open with a
  heading, which today produce the broken output anyway.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] A sectioned body passed through `--body-file` produces exactly one copy of each
      section — no placeholder scaffold appended after the caller's real sections.
- [ ] The caller's `## Summary` heading is not doubled in the full-body case.
- [ ] A plain-prose body (no `##` lines) still produces today's scaffold, unchanged. Pin
      this explicitly — it is `scaffold_epic`'s child path and the `--body-file` contract
      documented at `docs/reference/CLI.md:1584`.
- [ ] A body that merely *quotes* a fenced block containing `##`-shaped lines is treated
      as prose, not misrouted as a full body.
- [ ] **No section is dropped.** A body carrying sections outside the resolved variant's
      `include_common` list (`Steps to Reproduce`, `Program Design`, `Root Cause`,
      `Related Key Documentation`) has all of them present in the rendered output. This is
      the failure mode of the naive `content`-map fill — pin it with a test that counts
      the caller's H2s in the output, not just a substring check.
- [ ] Variant sections the caller did *not* supply still get their `creation_template`
      placeholder, so a full-body issue does not immediately trip `format-check`'s
      `missing:` gaps.
- [ ] A body carrying its own `# <ID>: <title>` H1 does not produce a doubled title
      heading.
- [ ] **Preamble is preserved.** A body whose first `##` heading is preceded by prose (a
      lead paragraph or an `_Added by …_` marker) retains that text in the rendered output.
      Pin the chosen destination — folded into `Summary`, or emitted between the title and
      the first section.
- [ ] **A caller-supplied `## Status` does not lose the generated footer.** Either the
      rendered output carries a regenerated `**Open** | Created: <today> | Priority: <P>`
      line, or the chosen caller-wins behavior is documented explicitly in the
      `--body-file` help text.
- [ ] **Section order follows the pinned interleaving rule** (see the Correction above):
      `common_sections` order, with caller-supplied type sections and unknown headings
      inserted before `Related Key Documentation`/`Labels`/`Session Log`/`Status` — not
      appended after the footer. Scoped to full-body merge output (the `minimal` default
      variant); the `full` variant's existing scaffold placement is unchanged. Assert
      `## Status` is the last H2 in the merge output, and `## Session Log` is the
      second-to-last **when a Session Log section is present** — this is what catches the
      naive "append at end" implementation, which otherwise passes every other criterion
      here.
- [ ] **A caller-supplied `## Session Log` does not duplicate the generated one**, and
      `session_log.append_session_log_entry` on the resulting file inserts into the real section.
- [ ] A body opening with a `---` frontmatter block is rejected with a clear error rather
      than concatenated into a two-frontmatter file.
- [ ] `render_issue_preview()` and `create_issue()` produce identical bodies for the same
      `IssueSpec` — the dry-run and apply paths must not diverge.
- [ ] `ll-issues format-check` on an issue created from a full sectioned body reports no
      `empty:`/`boilerplate:` gaps for sections the caller actually wrote.
- [ ] `--body-file`'s argparse help string (`cli/issues/create.py:306-309`) and
      `docs/reference/CLI.md:1584` describe the chosen contract; if Option 2 is taken,
      `IssueSpec`'s field list in `docs/reference/API.md` gains `body_mode` and the
      generated skill mirrors (`.gemini/`, `.kimi-code/`, `.qwen/`) are regenerated.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

- `docs/reference/CLI.md:1584` — `ll-issues create` argument table; `--body-file` row
  needs to reflect whatever contract is chosen.
- `skills/capture-issue/SKILL.md:242` — passes `$ISSUE_SUMMARY` via `--body-file -`.
- `skills/scope-epic/SKILL.md:319` — same path for EPIC and child creation.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-15_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- _Resolved 2026-08-15_: the sole concern was `depends_on: [BUG-3202]` being unresolved,
  which docked readiness from 95 to 85. BUG-3202 is now **Completed** and its exported
  helper (`text_utils.fence_spans`/`in_fence`) exists on main, so the dependency is
  satisfied and the effective readiness is back at the prior pass's 95. Retained for the
  record: the mechanized Phase 1.7 check only reads `blocked_by`, not `depends_on`, which
  is why the two passes scored Criterion 5 differently.

## Status

**Open** | Created: 2026-08-15 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-16T00:17:02 - `64e9e21e-d2d6-44cd-97cd-d980a3cc037d.jsonl`
- Pre-implementation review - 2026-08-15 - Verified all claims against main and reproduced the bug via `render_issue_preview` (dry-run). Refreshed four drifted line cites (issue_parser.py `_section_body_with_offset` now :240-278 with `matches[-1]` at :268; call sites :1270/:1338/:1347; session_log.py footer anchor at :327-330, function def :273; issue_template.py title heading :167). Corrected the false "single ordering table" claim — `Steps to Reproduce`/`Root Cause` live in `type_sections`, not `common_sections` — and pinned the interleaving rule (common order, type/unknown sections inserted before Related Key Documentation/Labels/Session Log/Status), scoped the Status-last AC to the merge output/`minimal` variant, and scoped the Session Log second-to-last assertion to "when present".
- Pre-implementation review (batch) - 2026-08-15 - BUG-3202 dependency now satisfied (completed; `fence_spans`/`in_fence` verified on main); refreshed stale "until BUG-3202 lands" text; promoted the preamble (fold into Summary) and Status/Session Log (always regenerate) decide-and-pin items to decisions; marked the confidence-check dependency concern resolved.
- `/ll:confidence-check` - 2026-08-15T20:37:35 - `3bed080b-17e6-4060-904f-398efef7735c.jsonl`
- `/ll:confidence-check` - 2026-08-15T20:01:26 - `4eb27027-e6df-4ea9-a6cc-2ca5e6e40c15.jsonl`
- `/ll:wire-issue` - 2026-08-15T18:50:54 - `fbae9292-fc5e-470b-b261-173e14415c63.jsonl`
- `/ll:refine-issue` - 2026-08-15T18:31:06 - `705a3268-face-42d3-8ebd-956f7b640ea6.jsonl`
