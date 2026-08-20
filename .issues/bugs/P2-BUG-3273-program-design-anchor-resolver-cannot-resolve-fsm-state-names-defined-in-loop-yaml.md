---
id: BUG-3273
type: BUG
title: Program Design anchor resolver cannot resolve FSM state names defined in loop
  YAML
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T23:14:07Z'
labels:
- bug
- issues
- program-design
- gate
- loops
- resolver
relates_to:
- BUG-3269
- BUG-3270
- BUG-3271
- ENH-3272
completed_at: '2026-08-20T23:21:26Z'
---

# BUG-3273: Program Design anchor resolver cannot resolve FSM state names defined in loop YAML

## Summary

The Program Design gate's anchor resolver (`git_grep_resolver` →
`_resolve_short_symbol`, `scripts/little_loops/issues/program_design.py:316`) recognizes
exactly three definition shapes — `def foo(`, `async def foo(`, `class Foo` — and excludes
`*.md` from its search. An FSM state name defined in a loop YAML (`  final_verify:` under
`states:`) therefore **can never resolve**, no matter how correct the issue is.

The consequence: every loop-authoring issue whose Call Path names FSM states — the natural,
correct anchors for that work — is graded `program_design_nonspecific` unless it happens to
also name an unrelated Python symbol. The gate has teeth (`confidence-check` hard-STOPs on
it; `research-triage` forces `analyzer: covered=false`; `ll-issues check-design` gates
`/ll:manage-issue`), so this silently blocks a whole class of issue on a shape the resolver
never learned to read.

## Current Behavior

`_resolve_short_symbol` (`scripts/little_loops/issues/program_design.py:316-336`) runs a
word-boundary `git grep` with markdown excluded, then filters to lines opening a Python
definition:

```python
openers = (f"def {short}(", f"async def {short}(", f"class {short}")
for line in proc.stdout.splitlines():
    _, _, text = line.partition(":")
    _, _, text = text.partition(":")
    if text.strip().startswith(openers):
        return True
return False
```

A loop-YAML state definition line is `  final_verify:` — it matches the `git grep` (YAML is
not excluded, only `*.md`), but never the opener filter. Verified directly against this
repo:

```
$ python -c "from little_loops.issues.program_design import git_grep_resolver as r; \
    print([(s, r(s)) for s in ['check_baseline_tests','final_verify','run_final_tests', \
                               'count_final','resolve_test_cmd','grade_program_design']])"
[('check_baseline_tests', False), ('final_verify', False), ('run_final_tests', False),
 ('count_final', False), ('resolve_test_cmd', False), ('grade_program_design', True)]
```

All five FSM state / fragment names are real definitions in
`scripts/little_loops/loops/general-task.yaml` and `loops/lib/common.yaml`. Only the Python
function resolves.

### Corpus impact

A sweep of all 283 gate-active issues in `.issues/` (`program_design_gate_active` true, with
a `## Program Design` section) finds 12 graded nonspecific, of which **5 fail specifically
on `no call-path anchor resolves`**. Three of those five are pure FSM-state-name cases that
the fix would flip to resolving:

| Issue | Unresolved anchors | Actually defined at |
|---|---|---|
| P2-BUG-3170 | `check_hedges`, `check_hedge_attempts`, `refine_followup`, `confidence_check` | `loops/refine-to-ready-issue.yaml:369, :380, :213, :496` |
| P3-ENH-2982 | `implement_current`, `clear_inflight_after_impl_failure` | `loops/autodev.yaml:851, :1047` |
| P4-ENH-3199 | `delegate`, `resolve_set` | `loops/sprint-refine-and-implement.yaml:24`, `loops/auto-refine-and-implement.yaml:126` |

The remaining two (BUG-3245, FEAT-3040) fail for unrelated reasons and are out of scope.

This is not a new regression — it has been live since the gate cutover
(`.ll/program-design-cutover.json`, stamped `2026-07-30`). Every loop-authoring issue filed
or re-refined since then has been graded against a resolver that cannot see loop YAML.

### Why it went unnoticed

`grade_program_design` requires only **one** anchor to resolve. An issue whose Call Path
mixes FSM states with any Python symbol passes anyway. BUG-3269 through ENH-3272 (the batch
that surfaced this) initially failed, then passed once each gained one incidental Python
anchor — e.g. BUG-3271's `load_and_validate`. The gate was satisfied by the anchor least
relevant to the work, which is precisely the failure mode: it rewards naming an unrelated
symbol over naming the states the change actually touches.

## Expected Behavior

An FSM state name that is genuinely defined in a loop YAML resolves, exactly as a Python
`def` does. Specifically:

- A key at 2-space indent that is a **direct child of a top-level `states:` block** in a
  `.yaml`/`.yml` file resolves.
- A key at 2-space indent that is a direct child of a top-level `fragments:` block resolves
  too — `loops/lib/*.yaml` fragments are reusable state definitions and are the target of
  BUG-3269's proposed `resolve_test_cmd`.
- **Nothing else in YAML resolves.** An arbitrary mapping key (`context:` children, `scope:`,
  `description:`, `action:`) must not. Generic words are everywhere in loop YAML; accepting
  any key would weaken the gate far more than the current gap costs.
- The existing anti-self-resolution property is preserved: an issue must never resolve a
  symbol it merely *proposes*. This holds for free — `*.md` is already excluded from the
  grep, so a state name written only inside the issue's own text still returns `False`.

## Motivation

The gate exists to force issues to name real, verifiable integration points instead of
gesturing at prose. For loop work, the real integration points *are* FSM state names — there
is no Python symbol to name. The resolver's blindness inverts the gate's intent: it pushes an
author to either pad the Call Path with an unrelated Python symbol (which passes and teaches
nothing) or set `program_design_not_applicable: true` (which is a false claim — loop work is
not trivial, and the flag is explicitly a human decision refine skills must never make).

Both escapes are worse than the fix. Three real issues are sitting nonspecific today for no
defect of their own, and every future loop issue joins them.

## Proposed Solution

Teach `_resolve_short_symbol` a second definition shape alongside the Python openers.

The `git grep` already returns `path:line:text` for candidate hits. Filter those hits to
`.yaml`/`.yml` paths, then confirm the match is a real state/fragment definition by a
structural check on the file rather than a line-shape regex — a bare `^  name:` regex would
match any 2-space key in any YAML, which is exactly the over-resolution to avoid.

The structural check is a single forward pass over the candidate file:

```python
_YAML_DEF_PARENTS = ("states:", "fragments:")

def _yaml_defines(path: Path, short: str) -> bool:
    """True when *short* is a direct child key of a top-level states:/fragments: block."""
    inside = False
    for line in path.read_text(...).splitlines():
        stripped = line.strip()
        if line[:1] not in (" ", "\t", "", "#"):        # a top-level key
            inside = stripped in _YAML_DEF_PARENTS
            continue
        if inside and line.startswith("  ") and not line.startswith("   "):
            if stripped.split(":", 1)[0].strip() == short and ":" in stripped:
                return True
    return False
```

Only files that already produced a `git grep` hit are read, so the added I/O is bounded by
the match set — typically one or two files — and the existing `@lru_cache` on
`_resolve_short_symbol` amortizes it across the corpus sweep.

**Rejected alternative**: parsing candidate YAML with the loop loader. It is far heavier,
would fail on `lib/` fragments that are not standalone loops, and pulls the issue-gate module
into a dependency on the FSM package for what is a lexical question.

**Rejected alternative**: adding `  {short}:` to the `openers` tuple. It cannot distinguish
a state key from `  timeout:` and would let `run`, `plan`, `done`, `description` resolve
against every loop in the repo.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/program_design.py:316-336` — `_resolve_short_symbol` gains the
  YAML branch and a `_yaml_defines` helper
- `scripts/little_loops/issues/program_design.py:287-312` — `git_grep_resolver` docstring
  states the two accepted definition shapes

### Dependent Files (Callers/Importers)
- `grade_issue_section` (`program_design.py:489`) — the only production caller; passes
  `git_grep_resolver` bound to the issue's project root
- `check_format_gaps` → `grade_program_design` → resolver — the `ll-issues format-check`
  path that emits `program_design_nonspecific`
- `ll-issues check-design` — the exit-code gate `/ll:manage-issue` and `confidence-check`
  consume
- `research_triage` — forces `analyzer: covered=false` on a nonspecific verdict

### Similar Patterns
- The `*.md` exclusion in the same function — the established precedent for scoping the
  search to keep an issue from resolving its own proposals
- `little_loops.codequery.fallback.FallbackProvider.defines_scan_for` — the opener-filter
  idiom `_resolve_short_symbol` mirrors; note it stays Python-only, and this change is
  deliberately local to the issue gate rather than pushed down into codequery

### Tests
- `scripts/tests/test_program_design_gate.py::TestRealRepoResolution` — the fixture-repo
  class to extend; it already builds a scratch git repo and asserts both positive
  (`check_format_gaps`) and negative (`proposed_helper` in markdown) resolution

### Documentation
- `docs/reference/API.md` — `git_grep_resolver` entry, if it documents the accepted shapes
- No user-facing behavior change beyond issues that were failing beginning to pass

### Configuration
- N/A

## Program Design

### Signatures

- `_resolve_short_symbol(short: str, cwd: Path) -> bool` — unchanged signature; the body
  gains a YAML branch after the Python opener loop fails.
- `_yaml_defines(path: Path, short: str) -> bool` — new module-private helper; true when
  *short* is a direct child key of a top-level `states:` or `fragments:` block in *path*.
- `git_grep_resolver(symbol: str, root: Path | None = None) -> bool` — unchanged signature
  and semantics; its docstring gains the second accepted definition shape.
- `reset_resolver_cache() -> None` — unchanged; still the escape hatch for a long-lived
  process that writes definitions between evaluations, and now covers YAML edits too.

### Call Path

- `check_format_gaps` → `grade_issue_section`
  (`scripts/little_loops/issues/program_design.py:489`) → `grade_program_design`
  (`:348`) → `git_grep_resolver` (`:287`) → `_resolve_short_symbol` (`:316`) — the single
  production path from `ll-issues format-check` to the resolver being changed.
- `_resolve_short_symbol` → `subprocess.run(["git", "grep", ...])` — the existing
  word-boundary search; unchanged, and already returns YAML hits today. Only the filter
  downstream of it is blind.
- `_resolve_short_symbol` → Python opener filter (`:330-335`) — tried first, returns early;
  the new branch runs only on its miss, so no existing resolution changes.
- `_resolve_short_symbol` → `_yaml_defines` — new edge, reached only for `.yaml`/`.yml` hit
  paths.
- `program_design_gate_active` (`:460`) → `read_cutover_stamp` — unchanged; determines
  whether the gate applies at all, and is why this defect dates to the `2026-07-30` stamp.
- `final_verify` (`scripts/little_loops/loops/general-task.yaml:520`) and `retry_counter`
  (`scripts/little_loops/loops/lib/common.yaml:38`) — the two definition shapes the fix must
  make resolvable, and the fixtures the new tests assert against.

### Invariant

**Invariant**: `_resolve_short_symbol` returns `True` for a symbol iff the repo contains a
line that *opens a definition* of it — Python `def`/`async def`/`class`, or a direct child
key of a top-level `states:`/`fragments:` block in a YAML file — and `False` for every
merely-referential occurrence.

Three properties this must preserve, each already load-bearing:

1. **No self-resolution.** A symbol appearing only in markdown never resolves. Preserved
   structurally: `*.md` is excluded at the `git grep` layer, upstream of both filters, so the
   new branch cannot see an issue's own text.
2. **No reference-resolution.** A transition target (`on_yes: final_verify`) is a reference,
   not a definition, and must not resolve — otherwise a typo'd or deleted state resolves off
   the dangling edge that points at it. Enforced by the indent-and-parent structural check:
   `on_yes: final_verify` is neither at 2-space indent nor a child of `states:`.
3. **No generic-key resolution.** `  timeout:`, `  action:`, `  description:` appear at
   2-space indent throughout loop YAML but under `context:`/`scope:`/a state body, never as
   a direct child of top-level `states:`/`fragments:`. The parent-key requirement is what
   makes the rule narrow enough to be safe; a bare indent regex would not be.

The Python branch runs first and returns early, so this change is **monotone**: no symbol
that resolves today stops resolving. The only behavior change is `False → True` for genuine
FSM definitions.

## Implementation Steps

1. **Pin the gap in a failing test.** Extend `TestRealRepoResolution` with a fixture repo
   containing a loop YAML (`states:` with a `final_verify:` child) and assert
   `git_grep_resolver("final_verify", tmp_path) is True`. It fails today.
2. **Add the negative cases in the same test pass**, so the narrowing is pinned before the
   widening lands: a 2-space key under `context:` must not resolve; a transition reference
   (`on_yes: final_verify`) with no matching definition must not resolve; a state name
   written only in a markdown file must not resolve.
3. **Implement `_yaml_defines`** and wire the branch into `_resolve_short_symbol` after the
   Python opener loop.
4. **Add the `fragments:` case** — a `lib/`-style fragment file with no `states:` block at
   all, asserting a fragment name resolves.
5. **Update the `git_grep_resolver` docstring** to state both accepted shapes and why the
   YAML rule is parent-scoped.
6. **Re-run the corpus sweep** and confirm the `no call-path anchor resolves` reason clears
   on BUG-3170, ENH-2982, and ENH-3199, with no issue moving the other way.

   **Measured after the fix**: anchor-unresolved drops 5 → 2 (the two survivors, BUG-3245 and
   FEAT-3040, fail for unrelated reasons and are out of scope). Only ENH-3199 becomes fully
   specific; BUG-3170 and ENH-2982 still fail on `no signature-shaped line`, a genuine
   authoring gap in those issues that this fix neither causes nor should mask. Gate-active
   nonspecific therefore goes 12 → 11, not 12 → 9 — the resolver reason cleared on all three
   as intended.
7. **Verify.** `python -m pytest scripts/tests/` exits 0; `ruff check scripts/` and
   `python -m mypy scripts/little_loops/` clean.

## Impact

- **Severity**: P2. Not a data-loss or runtime defect, but it hard-blocks `/ll:manage-issue`
  on a whole issue class via `confidence-check`, and has done so silently since 2026-07-30.
- **Scope**: one function plus one helper in `program_design.py`; one test class extended.
- **Risk**: low, and one-directional. The Python branch is untouched and returns first, so
  the change can only turn `False` into `True`. The bounded risk is over-resolution, which
  the parent-key requirement addresses and step 2 pins with explicit negative tests.
- **Blast radius on the corpus**: the resolver reason clears on 3 issues; 1 of them becomes
  fully specific, the other 2 remain nonspecific on a separate authoring gap. No issue can
  flip the other way.

## Steps to Reproduce

1. From this repo root:

```
$ python -c "from little_loops.issues.program_design import git_grep_resolver as r; \
    print(r('final_verify'), r('resolve_test_cmd'))"
False False
```

2. Confirm both are real definitions:

```
$ grep -rn '^  final_verify:' scripts/little_loops/loops/general-task.yaml
520:  final_verify:
$ grep -n '^  retry_counter:' scripts/little_loops/loops/lib/common.yaml
38:  retry_counter:
```

3. Write an issue whose `## Program Design` → `### Call Path` names only FSM states, and run
   `ll-issues format-check <ID>`. It reports `program_design_nonspecific` with
   `no call-path anchor resolves against the repo`.

**Frequency**: deterministic; every loop-authoring issue with FSM-state-only anchors.

## Related Key Documentation

- `.ll/program-design-cutover.json` — the `2026-07-30` stamp from which the gate, and this
  gap, have been live
- BUG-3269 / BUG-3270 / BUG-3271 / ENH-3272 — the loop-authoring batch that surfaced this;
  each initially failed the gate on FSM-state-only anchors
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop authoring, the work this gate currently
  penalizes

## Status

**Open** | Created: 2026-08-20 | Priority: P2
