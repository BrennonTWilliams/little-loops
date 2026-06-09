---
name: simplify-loop
description: Use when asked to simplify a loop, decompose a loop into sub-loops, collapse state chains into flows, or refactor an FSM loop.
disable-model-invocation: true
argument-hint: "[name] [--dry-run] [--auto] [--flows-only] [--subloops-only] [--yes]"
model: sonnet
allowed-tools:
  - Bash(ll-loop:*, git:*, cp:*, test:*, python:*)
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  short-description: "Refactor a loop: collapse linear chains to flows, extract sub-loops"
---

# Simplify Loop

You refactor an existing FSM loop into fewer, more readable, more reusable units
**without changing its behavior**. You apply two transforms the engine already
supports:

1. **Flow collapse** — a linear run of states (each unconditionally `next:`-ing
   the following one) becomes a `flow:` list + `state_defs:` bodies. The
   `resolve_flow()` parser expands it back into an identical `states:` map, so
   the rewrite is provably equivalent.
2. **Sub-loop extraction** — a cohesive region (one entry, clean success/failure
   exits) becomes a separate child loop invoked via `loop:` + `with:` +
   `on_success`/`on_failure`/`on_error`.

The detection algorithms, mapping tables, the behavior-preservation checklist,
the scope-resolution table, and the artifact schema live in
[reference.md](reference.md). Read it before Step 2.

**The non-negotiable invariant: every change is behavior-preserving.** Same
`initial`, same routing semantics, same reachable terminal set. If you cannot
prove a transform preserves behavior, do not propose it.

## Arguments

- `[name]` (optional): Loop to simplify. If omitted, list and prompt.
- `--dry-run`: Detect and report candidates only. Make no changes.
- `--auto` / `--yes`: Skip the per-change approval prompts (still validates).
- `--flows-only`: Only do flow collapse (Step 2a); skip sub-loop extraction.
- `--subloops-only`: Only do sub-loop extraction (Step 2b); skip flow collapse.

---

## Step 0: Resolve Loop and Scope

If no name was given, run `ll-loop list`, then ask via `AskUserQuestion` which
loop to simplify.

Locate the source file in this priority order (same as `rename-loop` Step 2):

1. **Project**: `.loops/<name>.yaml` → `scope = project`
2. **Built-in**: `scripts/little_loops/loops/<name>.yaml` (a `name` like
   `oracles/foo` resolves to `scripts/little_loops/loops/oracles/foo.yaml`) →
   `scope = builtin`

Record `SOURCE` (the resolved path) and the loops dir it resolved from. If
neither exists, abort:

```
Error: Loop '<name>' not found.
  Checked: .loops/<name>.yaml
           scripts/little_loops/loops/<name>.yaml
```

Guard — refuse to rewrite a running loop:

```bash
ls .loops/.running/<name>-*.pid 2>/dev/null | head -1
```

If non-empty, abort with: `Error: Loop '<name>' appears to be running. Stop it first: ll-loop stop <name>`.

---

## Step 1: Load and Baseline

Load two representations:

- **Analysis graph** (post-`from:`/`flow:`/fragment expansion):
  ```bash
  ll-loop show <name> --resolved --json
  ```
  Use this to compute the state graph: nodes, edges, `initial`, and the set of
  terminal states. This is the **behavioral fingerprint** you must preserve.
- **Raw source YAML**: `Read` the `SOURCE` file. You rewrite *this* file, so you
  must preserve its `from:`, `import:`, `parameters:`, `context:`, comments, and
  authored structure. If the source already uses `flow:`, note it — flow
  collapse is a no-op there; only sub-loop extraction may apply.

Record the **baseline**: state count, the full edge list, `initial`, and the
sorted list of reachable terminals. You will diff against this after rewriting.

If the loop has fewer than 4 states and no extractable region, report "Already
minimal — nothing to simplify." and stop.

---

## Step 2: Detect Candidates

Apply the algorithms in [reference.md](reference.md) §"Detection". Respect
`--flows-only` / `--subloops-only`.

### 2a. Flow-collapse candidates (skip if `--subloops-only`)

Find **maximal linear chains**: a run of two or more states where every interior
state has exactly one inbound edge (from its predecessor in the run) and exactly
one outbound `next:` edge to its successor, is referenced by no other state, is
not a retry self-loop, and is not the `initial` mid-chain. A single ternary
branch (`on_yes`/`on_no` to in-run targets) is allowed via the `name?yes:no`
flow form. See reference.md for the exact eligibility predicate and the
worked verbose-`states:` → `flow:`+`state_defs:` transformation.

Only propose flow collapse when the **whole loop** (or a child created by
extraction) reduces to one linear chain — `flow:` and `states:` are mutually
exclusive, so you cannot mix a `flow:` block with leftover `states:` in the same
file. If only part of the loop is linear, prefer extracting that part as a
sub-loop (2b) whose child body is then expressible as `flow:`.

### 2b. Sub-loop-extraction candidates (skip if `--flows-only`)

Find **cohesive regions** per reference.md §"Cohesion rules": a contiguous
subgraph with a single entry state, no edges from outside into its interior
(only into the entry), and exit edges that map cleanly onto child terminals
(success-exit → `done`, failure-exit → `failed`). Honor the min-size threshold
(default ≥3 states) so extraction reduces, not inflates, complexity.

Infer the child's interface: any `${context.*}` the region reads that the parent
supplies becomes a child `parameter:` and a parent `with:` binding (always carry
`run_dir` when present). Guard against verdict laundering — the parent's
`on_success` and `on_failure` for the new `loop:` state must differ (mirrors
`audit-loop-run` Step 8).

Before minting a new child, scan `scripts/little_loops/loops/oracles/*.yaml`: if
a region matches an existing oracle's shape and interface, propose calling that
oracle via `loop:` instead of creating a duplicate file.

If no candidates of either kind are found, report "No behavior-preserving
simplifications found." and stop.

---

## Step 3: Present and Approve

Show a summary:

```
Simplify: <name>  [scope: builtin|project]
Baseline: <N> states, <E> edges, terminals: <list>

FLOW COLLAPSE:
  <K> state(s) in the chain <s1> → <s2> → ... collapse to a flow: list
  <preview of the flow: + state_defs: block>

SUB-LOOP EXTRACTION:
  Region <entry>..<exit> (<M> states) → <child-name>  [target: <dir>]
    parent state '<entry>' becomes: loop: <child-name>
      with: { <bindings> }
      on_success: <s>  on_failure: <s>  on_error: <s>
  <or> Region matches existing oracle '<oracle>' → call it directly

After: <N'> states in parent (<delta> fewer), <C> new child file(s)
```

If `--dry-run`, stop here.

Otherwise, unless `--auto`/`--yes`, approve **each** change independently via
`AskUserQuestion` (one question per flow-collapse and per extraction), so the
user can accept a subset. Apply only approved changes.

---

## Step 4: Apply (children first, then parent)

Apply **sub-loop extractions before** rewriting the parent (the parent's new
`loop:` state must reference a file that already validates).

### 4a. Write each extracted child

Target directory **mirrors the parent's scope**:

- `scope = builtin` → `<resolved-loops-dir>/oracles/<child>.yaml` (git-tracked)
- `scope = project` → `.loops/<child>.yaml`

Build the child YAML: top-level `name`, `description`, `initial` (the region's
entry), `parameters:` for inferred inputs, the region's states relocated
verbatim, and `done` / `failed` terminal states the parent routes on. If the
child body is itself a single linear chain, express it with `flow:` +
`state_defs:`. Write it, then:

```bash
ll-loop validate <child>
```

If a child fails validation, do **not** touch the parent — report the error and
stop (no partial rewrites).

### 4b. Rewrite the parent

1. Back up: `cp <SOURCE> <SOURCE>.bak`.
2. Apply approved changes to the parent YAML:
   - Replace each extracted region with a **single** state:
     ```yaml
     <entry>:
       loop: <child-name>
       with: { <bindings> }
       on_success: <region-success-target>
       on_failure: <region-failure-target>
       on_error: <region-failure-target>
     ```
   - Collapse approved linear chains into `flow:` + `state_defs:` (only if the
     resulting parent is a single chain — see 2a).
   - Preserve `initial:`, `import:`, `from:`, `parameters:`, `context:`, `scope:`.
3. Write the parent with `Write`. Then validate:
   ```bash
   ll-loop validate <name>
   ```

**If validation fails**: restore the backup and stop.

```bash
cp <SOURCE>.bak <SOURCE>
```

Report: `Validation failed; original restored. <error>`. Leave the validated
child files in place (they are harmless, unreferenced) and note them.

On success, remove the backup: `rm <SOURCE>.bak`.

---

## Step 5: Equivalence and Regression Guard

Prove behavior preservation against the Step 1 baseline using the checklist in
reference.md §"Behavior-preservation checklist":

1. Re-run `ll-loop show <name> --resolved --json`. Confirm the **resolved**
   graph is equivalent to the baseline: same `initial`, same reachable
   terminals, and — accounting for extracted regions now living behind a
   `loop:` state — every original transition still has a corresponding path. A
   pure flow-collapse must yield a byte-equivalent resolved `states:` graph.
2. Run `ll-loop simulate <name>` and confirm no **new** stall / premature-exit /
   overrun signals versus a baseline simulate (run one before rewriting if you
   want a strict diff).
3. If `scope = builtin`, run the golden test:
   ```bash
   python -m pytest scripts/tests/test_builtin_loops.py -q
   ```
   If a test asserts on specific state names that extraction moved into a child,
   **report it** — do not silently edit the test. Surface the failing assertion
   and recommend the user update or confirm it.

If any equivalence check fails and a backup still exists, restore it.

---

## Step 6: Stage, Report, Persist Artifact

Stage every changed/created file **explicitly** (never a directory sweep):

```bash
git add <SOURCE>
git add <each-new-child-path>
```

(Project-scope `.loops/` files are git-ignored — skip `git add` for those and
say so.)

Print a summary:

```
Simplified: <name>  [scope: builtin|project]
  States: <N> → <N'>  (<delta> fewer in parent)
  Flows collapsed: <K> chain(s)
  Sub-loops extracted: <list of child names + paths>
  Equivalence: resolved-graph ✓  simulate ✓  builtin-tests <✓|n/a|⚠>
```

Persist a report to `.loops/simplifications/<name>-<YYYYMMDD-HHMMSS>.md` using
the schema in reference.md §"Artifact schema" (frontmatter: loop, timestamp,
scope, before/after state count; body: flows collapsed, sub-loops extracted with
paths, equivalence-check results). Create the directory if needed.

---

## Usage Examples

```bash
# Detect candidates without changing anything
/ll:simplify-loop rn-plan --dry-run

# Collapse linear chains only, with per-change approval
/ll:simplify-loop my-pipeline --flows-only

# Extract cohesive phases into sub-loops, no prompts
/ll:simplify-loop deep-research --subloops-only --auto

# Full simplification of a project loop
/ll:simplify-loop my-custom-loop
```
