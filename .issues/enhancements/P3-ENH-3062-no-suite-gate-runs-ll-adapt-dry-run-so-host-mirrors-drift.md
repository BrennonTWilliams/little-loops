---
id: ENH-3062
title: No suite gate runs ll-adapt --dry-run, so host mirrors drift undetected
type: ENH
priority: P3
status: open
testable: true
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T16:06:39Z'
relates_to:
- ENH-3046
- FEAT-2274
labels:
- testing
- host-adapters
- drift
supersedes:
- ENH-2968
verify_verdict: VALID
---

# ENH-3062: No suite gate runs ll-adapt --dry-run, so host mirrors drift undetected

## Summary

`ll-adapt` already detects mirror drift — it content-compares generated output
against the on-disk mirror and rewrites only on mismatch — and it already has a
`--dry-run` mode. Nothing in the test suite invokes it, so drift is caught only
when a human happens to look.

ENH-2996 added a drift test, but hardcoded a single source/mirror pair rather
than using the adapter that already knows about all 107.

## Motivation

Drift exists right now, on two hosts:

```
$ ll-adapt --host gemini --dry-run
  DRY    confidence-check
  DRY    scope-epic
  DRY    ll-refine-issue
Done: 3 adapted, 104 skipped, 0 errors

$ ll-adapt --host kimi-code --dry-run
Done: 3 adapted, 104 skipped, 0 errors
```

`--host codex` is clean (0 adapted, 107 skipped).

This was found by hand, in the course of unrelated work, after a stale mirror
caused real rework: `commands/refine-issue.md` gained content during ENH-3046
while `.gemini/commands/refine-issue.toml` did not, and the staleness surfaced
only because someone grepped the mirror directly.

## Current Behavior

**The detection already works.** `adapters/gemini.py:94`:

```python
if out_path.exists() and out_path.read_text() == new_content:
    print(f"  SKIP   {skill_name}: already adapted")
    return "skipped"
```

"already adapted" is a content equality check, not an existence check, and the
same shape appears in `adapters/codex.py:262` and `:309`. Any mirror whose
content differs from freshly-generated output is reported as `DRY` under
`--dry-run` and rewritten under `--apply`.

**Nothing calls it.** `grep -rn "ll-adapt\|ll_adapt" scripts/tests/` finds only
the failure message inside ENH-2996's test, not an invocation.

**The existing test covers 2 of 107 artifacts.**
`scripts/tests/test_wiring_skills_and_commands.py:355-371` hardcodes:

```python
WIRE_ISSUE_SKILL_MIRRORS = [
    ".gemini/skills/wire-issue/SKILL.md",
    ".kimi-code/skills/wire-issue/SKILL.md",
]
```

Uncovered by any test: 28 `.gemini/commands/*.toml`, 17 of 18
`.gemini/skills/`, 9 `.gemini/agents/`, 45 of 46 `.kimi-code/skills/`, 9
`.kimi-code/agents/`, and the whole `.codex/` tree.

## Expected Behavior

The suite fails when any host mirror is stale, naming the drifted artifacts and
the regeneration command. Coverage tracks the adapter's own artifact list, so a
newly added command or skill is covered the moment it is adapted — no test-side
list to keep in sync.

## Proposed Solution

Replace the hardcoded pair with a parametrized test over hosts that runs the
adapter in dry-run mode and asserts nothing would be written.

Per the project's no-hosted-CI policy (`.claude/CLAUDE.md` § Testing & CI
Policy), this is an ordinary pytest test invoking the adapter directly — no
workflow file. `ll-adapt` is Python, so the adapter functions can be called
in-process rather than shelling out; if the CLI's counting logic is the clearer
contract, a subprocess asserting `Done: 0 adapted` is acceptable.

The failure message should carry the drifted artifact names and the exact fix,
matching ENH-2996's existing wording:

```
ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply
```

Decisions to make during implementation:

- Whether `disable-model-invocation: true` artifacts (skipped by the adapter)
  should be asserted absent from mirrors, or left unchecked as they are today.
- Whether to fix the three live drifts in the same change or a preceding one.
  They should land first, or the new gate fails on arrival.

Explicitly out of scope: changing what the adapters generate, adding new hosts,
and the `.gemini`/`.kimi-code`/`.codex` tree layouts.

## Scope Boundaries

**In scope**: a suite gate invoking the existing adapters in dry-run mode across
all configured hosts, replacing the ENH-2996 hardcoded pair.

**Out of scope**: adapter output format, host onboarding, and the unrelated
`commands/*.md` → `.gemini/commands/*.toml` count mismatch (29 sources vs 28
mirrors), which may be a legitimate `disable-model-invocation` exclusion and
should be confirmed rather than assumed to be a bug.

## Program Design

### Signatures

- `adapt_skill(skill_path: Path, apply: bool, quiet: bool) -> str` — existing, `adapters/gemini.py:88`; returns `"skipped"` on content match, the drift signal this gate consumes.
- `main() -> int` — existing `ll-adapt` entry point; already supports `--host`, `--dry-run`, `--only`, `--quiet`.
- `test_host_mirrors_are_not_stale(host: str) -> None` — new, parametrized over hosts, in `scripts/tests/test_wiring_skills_and_commands.py`.

### Call Path

`test_wire_issue_skill_mirror_matches_source` (`scripts/tests/test_wiring_skills_and_commands.py:362`) is the gate being replaced. The new test drives `main()` (`ll-adapt`) -> per-host adapter -> `adapt_skill` (`adapters/gemini.py:88`) / the codex equivalents (`adapters/codex.py:262`, `:309`), asserting the adapted count is zero. `_body_after_frontmatter` (`scripts/tests/test_wiring_skills_and_commands.py:345`) becomes unused if the hardcoded pair is fully removed.

## Impact

Silent divergence between what a Claude Code user sees and what a Gemini, Kimi,
or Codex user sees. The mirrors exist specifically so non-Claude hosts get the
same instructions; when they drift, those hosts run older behavior with no
signal to anyone.

The cost is concrete and already paid once: ENH-3046's refine-issue changes had
to be hand-applied to the mirror, and the hand-applied version is itself still
reported as drifted — meaning a manual patch is not a reliable substitute for the
generator.

Low-to-moderate priority because the blast radius is limited to non-Claude hosts,
but the fix is small and the detection machinery already exists unused.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § Testing & CI Policy | Requires the gate live in the local pytest suite, not a workflow |
| `docs/reference/HOST_COMPATIBILITY.md` | Which hosts have mirrors and why |
| `docs/reference/CLI.md` § ll-adapt | Adapter flags including `--dry-run` |

## Status

**Open**

---

## Scope Addition

**Source**: Merged from [ENH-2968] during `/ll:audit-issue-conflicts` conflict resolution.

ENH-2968 independently found the same gap (no test asserts committed `.gemini`/`.kimi-code`/`.codex` mirrors match `ll-adapt` output) and additionally documented a real defect: `CodexEmitter.emit_command`'s skip check (`adapters/codex.py:307`) and `emit_skill`'s sidecar check (`codex.py:260`) are presence-only, not content comparisons, unlike Gemini/Kimi's `out_path.exists() and out_path.read_text() == new_content` pattern. Fix these two content-comparison checks as part of implementing this issue's gate, so a fully-drifted Codex tree can't report false success.

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: core gap still
real — no test invokes `ll-adapt --dry-run`; codex.py presence-only checks
confirmed near lines 258-260/307-309, closely matching prior citations.
However: (1) the hardcoded-pair test has grown from 2 to 6 entries and was
renamed to SKILL_MIRRORS_MUST_MATCH_SOURCE (from WIRE_ISSUE_SKILL_MIRRORS),
now around line 368, not 355-371; (2) this issue's `relates_to: ENH-2996` was
a BROKEN/MISLINKED reference — ENH-2996 actually resolves to an unrelated P4
issue about wire-issue phase numbering. Removed that `relates_to` entry from
the frontmatter.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:10 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:28 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-06T05:57:00 - `b806aadf-1033-4656-b34d-bd948c43350c.jsonl`
- `/ll:capture-issue` - 2026-08-05T16:14:07 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- `/ll:capture-issue` - 2026-08-05 - Captured from the ENH-3046 run forensics
  session, after a stale mirror required hand-patching.
