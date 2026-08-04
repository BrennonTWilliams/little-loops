---
id: FEAT-3048
title: 'Verify symbol and CLI-flag claims in issue bodies (extend prose-claim gap taxonomy)'
type: FEAT
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: "2026-08-04T20:47:11Z"
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- FEAT-2846
- ENH-2970
- ENH-2951
labels:
- cli
- issues
- gates
---

# FEAT-3048: Verify symbol and CLI-flag claims in issue bodies

## Summary

Issue bodies assert things about the codebase in backticks — that a function exists, that a
module owns a write path, that a CLI subcommand accepts a flag — and nothing checks them.
The FEAT-2846/2849/2850 series already built claim-extraction-and-verification for **one**
claim class (prose dependency claims: `extract_prose_deps` in
`scripts/little_loops/issues/prose_deps.py`, the `prose_dep_drift`/`stale_prose_dep` gap kinds
in `check_format_gaps()`, and a repo-wide pytest sweep). This issue generalizes that same
architecture to **symbol** and **CLI-flag** claims.

Scope note: **file-path claims are already covered** by the existing `stale_file_ref` gap kind
(`issue_parser.py` `FormatGaps.stale_file_ref`, populated in `check_format_gaps`). This issue
adds the two claim classes layered on top of a file path — the symbol inside it, and the flag
on a CLI subcommand.

## Current Behavior

No gate verifies a symbol or CLI-flag claim in an issue body. The only instruction that covers
it is prose: `skills/confidence-check/SKILL.md` Criterion 3, detection bullet 5 — *"Verify
claims in the issue against actual code (do referenced files/functions exist? do they behave as
described?)"* — with no CLI behind it. It is the sole prose-only gate in that skill; every other
check there has a CLI (`ll-issues check-design`, `check-open-questions`, the Phase 1.6
Program Design pre-fetch).

Concrete failure that motivated this issue — FEAT-2942 asserts:

> Reuse `ll-issues link` / `frontmatter.update_frontmatter` for writes

but `scripts/little_loops/cli/issues/link.py` defines
`_FIELD_FLAGS = ("blocked_by", "depends_on", "relates_to")` and has no `parent`/`epic` branch,
so `ll-issues link` **cannot** set `parent:` — the field the whole feature is about. The claim
was authored in that file's first commit (`2225b414`) and survived `/ll:refine-issue`,
`/ll:wire-issue`, and `/ll:confidence-check` untouched. `/ll:wire-issue` even edited the
adjacent sentence and hedged on top of the bad premise rather than checking `link.py`.

## Expected Behavior

`check_format_gaps()` grows two gap kinds, reported through the existing `format-check` surface
and swept repo-wide in pytest:

- `stale_symbol_ref` — a backticked `symbol` attributed to a cited file that does not resolve
  in that file (function, class, or module-level constant).
- `stale_cli_flag` — a backticked CLI invocation (`ll-issues link --parent`, `ll-loop run
  --foo`) naming a subcommand or flag that the argparse parser does not accept.

Both follow the `prose_dep_drift`/`stale_file_ref` precedent: extractor in
`little_loops/issues/`, gap-kind fields on `FormatGaps`, printed by `format_check.py`, gated by
a repo-wide pytest sweep per FEAT-2850.

## Motivation

Three review passes and a 93/76 confidence score did not catch a false claim about the core
write path of the feature being specified. Claim verification is mechanical — file, symbol, and
argparse introspection are all deterministic lookups — which makes it exactly the kind of work
EPIC-2938 exists to move out of prose and into a tested CLI. It is also the highest-leverage of
the review-quality fixes: it catches the defect class that survives the most passes, because
existing passes are additive and never re-examine text already in the issue.

## Proposed Solution

Extend, don't scaffold. The pieces already exist:

- **Extractor** — new module beside `little_loops/issues/prose_deps.py`, same shape:
  regex over the body, fence-aware (`_in_fence`), returning structured claims.
- **Gap kinds** — add `stale_symbol_ref` and `stale_cli_flag` to `FormatGaps`
  (`issue_parser.py`), populated in `check_format_gaps()` alongside `stale_file_ref`.
- **Reporting** — add the two kinds to `format_check.py`'s printer and its
  `--kinds` help string (currently lists
  `missing/renamed/empty/boilerplate/malformed_id/prose_dep_drift/stale_prose_dep/program_design_nonspecific/deprecated_key/...`).
- **Symbol resolution** — reuse `little_loops/issues/anchors.py` / `anchor_sweep.py`, which
  already resolve a `file:line` reference to its enclosing function/class; the inverse lookup
  (does symbol X exist in file Y) is the same index.
- **CLI-flag resolution** — argparse introspection: import the parser, walk
  `_subparsers`/`choices` and each action's `option_strings`. **This mechanism does not exist
  yet.** See the ENH-2970 note below.

**ENH-2970 correction (verified 2026-08-04):** ENH-2970 is the right conceptual precedent
(*"assert every documented command resolves"*), but its shipped form is **not** argparse
introspection. `scripts/little_loops/cli/verify_cli_docs.py` does not exist, no
`ll-verify-cli-docs` entry point is registered in `scripts/pyproject.toml`, and
`docs/reference/CLI.md` coverage is enforced by **hardcoded substring assertions** in
`scripts/tests/test_wiring_cli_registry.py` (e.g. `("docs/reference/CLI.md", "ll-doctor",
"FEAT-1504")`) — ENH-2972 appears to have absorbed the work when § CLI Tools moved out of
CLAUDE.md. **This issue must build the argparse-introspection helper itself.** Closest existing
shape is `scripts/little_loops/cli/verify_cli_allowlist.py` (entry-point parsing + drift exit
contract), not a flag-level introspector.

**False-positive control** is the main design risk: issue bodies backtick plenty of things that
are not symbols (`--json`, `P2`, prose nouns, planned-but-unbuilt APIs). Mitigations to decide
during refinement:
- Only verify a symbol claim when it is attributed to a cited file that itself resolves.
- Treat claims inside `## Program Design` / `## Expected Behavior` as *proposed* (not yet
  existing) and exempt them — those sections describe what will be built.
- Reuse the existing `<!-- ll-prose-ok: ... -->` suppression convention from
  `cli/verify_skill_prose.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/` — new claim-extractor module (peer of `prose_deps.py`).
- `scripts/little_loops/issue_parser.py` — `FormatGaps` fields, `to_dict()`, `has_gaps`,
  `check_format_gaps()` population.
- `scripts/little_loops/cli/issues/format_check.py` — printer + `--kinds` help.
- `scripts/tests/` — unit tests per claim class + repo-wide sweep (FEAT-2850 pattern).
- `docs/reference/CLI.md` — document the new gap kinds.

### Similar Patterns
- `FEAT-2849` — shared extractor + gap taxonomy + skill wiring; the direct template.
- `FEAT-2850` — repo-wide sweep gated in pytest.
- `ENH-2946` — precedent for extending `format-check` with new gap kinds.
- `cli/verify_skill_prose.py` — marker/suppression convention.

## Implementation Steps

1. Symbol-claim extractor + `stale_symbol_ref` gap kind + tests.
2. Argparse-introspection helper + `stale_cli_flag` gap kind + tests.
3. `format-check` reporting/`--kinds` wiring.
4. Repo-wide pytest sweep; triage and suppress the existing backlog's false positives.

## Use Case

A maintainer runs `/ll:refine-issue FEAT-2942`; the refine pass now fails the format-check gate
with `stale_cli_flag: ll-issues link --parent (no such flag)`, and the false premise is
corrected before implementation instead of after review.

## Acceptance Criteria

- [ ] `stale_symbol_ref` and `stale_cli_flag` gap kinds populated by `check_format_gaps()`
- [ ] Argparse introspection resolves subcommand + flag for every `ll-*` entry point
- [ ] Reported via `format-check` text and `--format json`; listed in `--kinds` help
- [ ] Repo-wide pytest sweep gates the suite (per FEAT-2850)
- [ ] Documented suppression path for intentional/aspirational claims
- [ ] Verified against FEAT-2942: the `ll-issues link` claim is flagged
- [ ] pytest coverage in `scripts/tests/`

## Impact

- **Priority**: P2 — matches EPIC-2938; catches the defect class that survives the most passes
- **Effort**: Medium — extractor + introspector + sweep triage
- **Risk**: Medium — false-positive rate on the existing backlog is the main unknown

## Related Key Documentation

- `.claude/CLAUDE.md` — adds gap kinds to the `ll-issues format-check` surface
- `docs/reference/CLI.md` — sole home of the documented CLI surface

## Status

**Open** | Created: 2026-08-04 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-04T20:50:26 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
