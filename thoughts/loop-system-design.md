> **Note**: This is historical brainstorming. The canonical loop system design is in [`docs/generalized-fsm-loop.md`](../docs/generalized-fsm-loop.md).

---

Long term goal of this little-loops (`ll`) project is to let developers create and run simple iterative loops for development, or any, tasks.

This system must be generalized enough to express a wide variety of loops, but also simple enough that the user can easily understand and author them quickly.

### Option 1: Imerative loops - iterate until condition met

Loop = sequence of commands + condition + repeat until done

```yaml
Loop: "research-and-merge"
  steps:
    - /web:search "latest React patterns"
    - /analyze "compare against docs/architecture.md"
    - /merge "update architecture docs"
  condition: "file_changed('docs/architecture.md')"
  max_iterations: 10
```

Or more generalized:

```yaml
name: "fix-types"
steps:
  - /ll:check_code types
  - /ll:manage_issue bug fix   # Find highest priority type issue
condition:
  type: "exit_code"
  target: 0
max_iterations: 20
backoff: 2  # seconds between iterations
```

This is a powerful abstraction because:
- Decoupled from issues — any action, any condition
- Composable — nest loops, chain them
- Observable — track iterations, timing, state changes
- Resumable — pick up where you left off
- Cost-efficient — minimal feedback between cycles

-----

### Option 2: Goal-oriented loops

**What are we actually trying to express with one of these loops?**

Not "do X then Y until Z" but rather: **"I want this state to be true, here are tools that might get there."**

That flips it from imperative to **declarative/goal-oriented**:

```yaml
goal: "No type errors in src/"
tools:
  - /ll:check_code types
  - /ll:manage_issue bug fix
```

The system figures out the loop. You declare the end state.

-----

### Option 2: Convergence loops

**Or even simpler — convergence functions:**

A loop is really just: **apply f(x) until f(x) = x** (fixed point)

```
converge:
  check: "ruff check src/ --output-format=json | jq '.count'"
  toward: 0
  using: "/ll:check_code fix"
```

No explicit steps. Just: "keep applying this until that metric stops changing or hits target."

-----

### Option 3: Reactive imperative loops

**Or reactive/event-driven:**

```yaml
watch: "src/**/*.py"
on_change: "/ll:check_code lint"
until: "clean"
```

Not a loop at all — a *reaction* that naturally terminates.

-----

### Option 4: Invariant maintenance loops

**Or constraint satisfaction:**

```yaml
constraints:
  - "pytest exits 0"
  - "ruff check exits 0"
  - "mypy exits 0"
maintain: true
```

"Keep these true. When one breaks, fix it." The system continuously maintains invariants.

-----

### Option 5: Minimalist loops

The most elegant might be **just a predicate + action**:

```
while (type_errors > 0): fix_types
```

One line. The "loop" is implicit in the semantics of "while."

-----

### Option 6: State machine loops

**Explicit state transitions with conditional routing:**

```yaml
name: "lint-fix-cycle"
initial: "check"
states:
  check:
    action: "/ll:check_code lint"
    on_fail: "fix"
    on_pass: "done"
  fix:
    action: "/ll:check_code fix"
    next: "check"
  done:
    terminal: true
```

This allows complex workflows with branching logic — different paths based on outcomes, retry states, error recovery states, etc.

-----
