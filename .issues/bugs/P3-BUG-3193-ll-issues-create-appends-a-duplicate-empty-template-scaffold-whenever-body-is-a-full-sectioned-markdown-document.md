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
captured_at: '2026-08-15T18:16:50Z'
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
`>>` to keep this quotation from registering as real sections (see Finding 4 of BUG-3194
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
  `_section_body_with_offset` (`scripts/little_loops/issue_parser.py:254`) takes
  `matches[-1]`.

That second point makes this more than cosmetic. Because the placeholder copy wins,
`ll-issues format-check` reads the *scaffold* as the issue's real content and reports
`boilerplate: Current Behavior`, `boilerplate: Expected Behavior`, and `empty: Summary` on
issues whose real sections are fully written. The linter's verdict on every affected issue
is inverted: a complete issue is reported as unfinished. That is the actual cost of this
bug, and it is why the fix belongs upstream in creation rather than being hand-stripped
per issue.

Frontmatter `status:` remains the source of truth, so the duplicated `## Status` footer is
*not* a status-correctness bug. It does leave `session_log.append`'s anchor on
`"\n---\n\n## Status"` (`scripts/little_loops/session_log.py:271`) ambiguous between two
footers.

Both `--body-file` (`docs/reference/CLI.md:1580`, "contents become the `## Summary` body")
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

## Expected Behavior

Supplying a complete sectioned body should not produce a duplicate scaffold. Any of:

1. **Detect and route** — if the body already opens with a `## ` heading, treat it as a
   full body: emit it verbatim after the title heading and skip scaffold generation.
2. **Explicit flag** — add `--body-mode summary|full` (and a matching MCP property),
   defaulting to `summary` to preserve today's behavior.
3. **Reject loudly** — fail with a clear error when the body contains `## ` headings that
   collide with variant section names, pointing the caller at the intended contract.

Option 1 is the smallest change and fixes existing callers without touching
`capture-issue` or `scope-epic`; option 2 is the most explicit. Not decided here.

Whichever is chosen, the doubled `## Summary` heading should go away in the full-body
case.

## Impact

- **Priority**: P3 - Silent and systematic (6/6 on the observed sweep), affects every
  issue created through the path most creation flows use, but the damage is cosmetic
  per-issue and hand-strippable. No data loss and no wrong frontmatter status.
- **Effort**: Small - One function (`_render_issue_content`) plus a template-assembly
  branch; tests already exist at `scripts/tests/test_ll_issues_create.py`.
- **Risk**: Low - Option 1 is additive and only triggers on bodies that open with a
  heading, which today produce the broken output anyway.
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/CLI.md:1569` — `ll-issues create` argument table; `--body-file` row
  needs to reflect whatever contract is chosen.
- `skills/capture-issue/SKILL.md:242` — passes `$ISSUE_SUMMARY` via `--body-file -`.
- `skills/scope-epic/SKILL.md:319` — same path for EPIC and child creation.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
