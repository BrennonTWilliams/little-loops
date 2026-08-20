# Caller Suitability Gate (ENH-3258)

Full procedure for the § 8b gate. A caller hit is evidence that a file *relates* to the change.
It is not evidence that the file *needs editing*. This gate decides which of the two it is, and —
when the answer is "no edit" — where the change actually belongs instead.

## Why it exists

`ll-code callers-of <symbol>` and the Phase 4 agents return call sites. The naive Wiring Phase
rendering turns each one into `Update <path> — adjust call to <symbol>()`. For a change that
threads a new value to a function, that instruction is frequently wrong: the call site may be a
lazy-default fallback that never runs on the production path, or the value may already have a
parameter to arrive through. Emitting `Update` there sends the implementer to edit a line that
should not change, and — worse — draws attention away from the seam that should.

## The two skip conditions

Read the enclosing function of the call site before emitting anything.

**1. The call sits in a guard branch.** Shapes that qualify:

- `if x is None:` / `if not x:` — a lazy default. The call runs only when a caller omitted the
  value, which by definition is not the path a config-sourced value travels.
- `except ...:` — an error fallback.
- A `--dry-run`, `--force`, or capability-probe guard — a branch gated on a mode flag rather than
  on the normal path.

**2. The enclosing function already accepts the value as a parameter.** A signature like
`def f(..., *, index: RefIndex | None = None)` means the seam already exists. Nothing in the
function body needs to change for a caller to supply the value.

The two conditions overlap constantly — the lazy-default idiom *is* a parameter plus a guard —
but either alone is sufficient to skip.

## What to emit instead

Suppression alone is not the deliverable. A gate that only deletes instructions leaves the
Wiring Phase silent about a touchpoint the issue genuinely has, which reads as "nothing to do
here" rather than "do something different here."

**Always emit both halves:**

1. **Record the path under `### Dependent Files (Callers/Importers)`** with the guard line or the
   parameter signature quoted, and one clause saying why no edit is needed.

2. **When condition 2 holds (a parameter is the seam), emit a Wiring Phase bullet naming it** —
   `Inject at <path>` rather than `Update <path>` — so the touchpoint is redirected, not dropped.
   Identify the *caller of the enclosing function* that sits on the production path; that is where
   the value has to be supplied. If condition 1 holds but condition 2 does not, there is no
   parameter seam to name; the Dependent Files entry alone is the complete output.

## Worked example

Issue: thread a config-sourced `exclude_patterns` list into `get_untracked_files()`.

`ll-code` returns one production caller, `scripts/little_loops/git_operations.py:413`:

```python
def suggest_gitignore_patterns(
    untracked_files: list[str] | None = None,     # <- condition 2: the seam already exists
    repo_root: Path | str = ".",
    ...
) -> GitignoreSuggestion:
    ...
    if untracked_files is None:                   # <- condition 1: guard branch
        untracked_files = get_untracked_files(repo_root)
```

Both conditions fire. Correct output:

```markdown
### Dependent Files (Callers/Importers)

- `scripts/little_loops/git_operations.py:413` — `suggest_gitignore_patterns()` calls
  `get_untracked_files(repo_root)` inside the guard `if untracked_files is None:` (`:412`), and
  already accepts the value via `untracked_files: list[str] | None = None`. No edit needed here.

### Wiring Phase (added by `/ll:wire-issue`)

- Inject at `suggest_gitignore_patterns()`'s existing `untracked_files=` parameter — the
  production callers of *that* function are where the filtered list must be supplied; the
  in-function fallback keeps the empty-tuple default for library callers
```

The failure this prevents: `- Update scripts/little_loops/git_operations.py:413 — adjust call to
get_untracked_files()`, an edit to a line that should not change.

The failure the second half prevents: emitting only the Dependent Files entry, leaving the
implementer with an Implementation Step that says "thread the list from production call paths"
and a Wiring Phase that names no path at all.

## Scope

This gate governs *suitability* — does this hit need editing, and where does the change belong?
It is separate from the three graph-discovery safety rules in
[graph-discovery-layer.md](graph-discovery-layer.md), which govern *trust* — is this hit real?
Run those first; a hit that fails confirmation never reaches this gate.
