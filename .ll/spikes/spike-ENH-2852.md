# Spike Plan: ENH-2852 — Program Design specificity validator

## Context

From the issue's `### Outcome Risk Factors` (verbatim):

> - Broad enumeration across 9+ change sites spanning section schema, gate logic, and
>   `autodev.yaml`'s deferral routing — moderate per-site depth since the new
>   content-shape validator (not just heading presence) and the reconcile-before-defer
>   discriminator are genuinely new logic, not uniform mechanical edits.
> - No precedent for the signature/call-path prose parser; mitigate by reusing
>   `resolve_anchor()`/`FallbackProvider.defines()` for the repo-resolution half and
>   scoping the signature-shape half to a narrow regex rather than a general parser.

The second factor is the spikeable one. Both canonical low-confidence drivers apply:

- **(a) zero precedent** — per the issue's own research, "No existing parser validates a
  free-text `name(params) -> ret` or dataclass-field line against nothing"; `anchors.py`'s
  `_ANCHOR_PATTERNS` only match lines inside real source files, never prose in an issue body.
- **(b) no test exercises the risky core** — no gap category in `check_format_gaps()`
  inspects section *content* beyond heading presence and template-equality, so there is no
  existing test of content-shape validation to extend.

Concrete failures this spike must rule out:

1. A narrow signature regex is **too strict** — it rejects legitimately-shaped lines
   (bare `def`-style, methods with `self`, dataclass field lines, generics, `Optional[X]`),
   making the gate unpassable and mass-deferring good issues.
2. A narrow signature regex is **too loose** — ordinary English prose lines
   ("this changes the way the parser handles input (mostly)") parse as signatures, making
   the gate inert and the whole issue worthless.
3. The **new-vs-anchor split is unimplementable in practice**: the issue's own Design
   Notes insist repo-resolution is required *only* of call-path anchors while new
   identifiers need only be shape-valid. If the validator cannot mechanically tell those
   apart from a `## Program Design` body, the gate is either unpassable (AC-3 conflict)
   or inert.

The third failure is the one that would force a redesign after implementation has started
across 9+ files — the expensive kind.

## Approach

Build a standalone `program_design.py` library under `scripts/tests/spike/` that takes a
raw `## Program Design` section body (plain markdown text) plus a resolver callable, and
returns a structured verdict: the signature-shaped lines it found, the call-path anchors it
extracted, which anchors resolved, and a boolean `is_specific`. The signature half is a
narrow regex pair (call-shaped `name(params) -> ret` / `name(params)` and dataclass-field
`name: Type`) with prose-rejection guards; the call-path half extracts backtick-quoted and
`A -> B -> C` chain identifiers from the `Call Path` subsection only, and resolves each via
an injected resolver. The resolver is injected (not imported) so the spike proves the
*algorithm*, with tests supplying both a fake resolver (fast, deterministic, table-driven)
and a real git-grep-backed resolver run against this repo (proving the reuse of the
`defines_scan_for()` shape actually resolves real anchors like `check_format_gaps`). Nothing
about `FormatGaps`, the section JSON schema, the cutover stamp, or `autodev.yaml` routing is
touched — those are mechanical edits whose risk is enumeration, not novelty.

## Critical files

Read-only production references whose contract the spike must honor:

- `scripts/little_loops/issue_parser.py` — `FormatGaps` (~L136) / `check_format_gaps()`
  (~L201); the eventual home of this logic. The spike's verdict must be reducible to a
  `list[str]` gap field.
- `scripts/little_loops/issues/anchors.py` — `_ANCHOR_PATTERNS` / `resolve_anchor()`; the
  regex-family precedent and the return-`None`-on-unresolved convention.
- `scripts/little_loops/codequery/fallback.py` — `FallbackProvider.defines()` /
  `defines_scan_for()` / `CodeRef.confidence`; the resolver shape the real resolver mirrors.

Spike paths to create:

```
scripts/tests/spike/program_design_specificity/
├── __init__.py
├── program_design.py
└── test_program_design.py
```

## Implementation

API sketch:

```python
@dataclass(frozen=True)
class DesignVerdict:
    signatures: list[str]        # signature-shaped lines found
    anchors: list[str]           # call-path anchors extracted
    resolved: list[str]          # anchors that resolved against the repo
    unresolved: list[str]
    is_specific: bool
    reasons: list[str]           # why it failed, empty when specific

Resolver = Callable[[str], bool]

def parse_signature_lines(body: str) -> list[str]: ...
def extract_call_path_anchors(body: str) -> list[str]: ...
def grade_program_design(body: str, resolver: Resolver) -> DesignVerdict: ...
def git_grep_resolver(symbol: str) -> bool: ...   # real, git-grep backed
```

Specificity rule (the contract under test): `is_specific` is True iff at least one
signature-shaped line was found **and** at least one extracted call-path anchor resolved
via the resolver. New identifiers are never required to resolve.

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_accepts_varied_real_signature_shapes` | Risk 1 (too strict): defs, methods with `self`, generics, `Optional`, dataclass fields | behavior |
| `test_rejects_prose_that_merely_contains_parentheses` | Risk 2 (too loose): English prose must not parse as a signature | behavior |
| `test_prose_only_section_is_not_specific` | AC: "fails an issue whose section contains only prose" | behavior |
| `test_missing_or_empty_section_is_not_specific` | AC: "fails an issue with a missing or empty section" | behavior |
| `test_new_identifiers_need_only_be_shape_valid` | Risk 3 + AC: unresolvable new names must not fail the gate | behavior |
| `test_unresolvable_call_path_anchors_fail` | AC: prose with no repo-resolvable anchors fails | behavior |
| `test_real_repo_anchors_resolve_via_git_grep` | Risk 3: the split works against this actual repo, not just a fake | behavior |
| `test_spike_does_not_import_production_core` | isolation guard (AST sniff) | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/program_design_specificity/ -v
python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_ll_issues_format_check.py scripts/tests/test_issues_anchors.py -v
```

## Out of Scope

The `FormatGaps` field addition, the section-schema JSON entries, the
`.ll/program-design-cutover.json` grandfathering/fail-open logic, `DeferReason`, and
`autodev.yaml`'s reconcile-before-defer routing are all deliberately excluded — they are
enumeration risk over existing machinery, not novel mechanism. External-API proving stays
`/ll:explore-api` territory.

## Promotion

On acceptance, promote to `scripts/little_loops/spike/program_design_specificity/` (or
directly into `issue_parser.py` as part of ENH-2852) in a **separate PR**. Not performed by
`/ll:spike`.
