# improve-claude-md Algorithm Reference

Condition examples, decision criteria, and step-by-step guidance for the 9-step CLAUDE.md
rewrite algorithm. Used by `SKILL.md` as the reference library.

---

## Core Principle: Narrow vs. Broad Conditions

Conditions must be **narrow and specific**, not broad and general.

| Too Broad (avoid) | Narrow and Specific (use) |
|---|---|
| `you are writing code` | `you are adding new imports or changing module structure` |
| `you are working on the project` | `you are implementing authentication or authorization` |
| `you are making changes` | `you are writing or running tests` |
| `you need context` | `you are setting up the project or installing dependencies` |
| `you are coding` | `you are defining new data models or classes` |

The goal: Claude should reach for the block only when that instruction is literally needed.
A block about testing patterns should not activate when Claude is writing a SQL migration.

---

## Step 1 — Project Identity (Leave Bare)

**What belongs here**: Project name, one-sentence description, primary purpose.

**Decision**: Always bare. Relevant to 90%+ of all tasks.

**Example (keep as-is)**:
```
# my-project — Deployment automation toolkit for Kubernetes clusters
```

---

## Step 2 — Directory Map (Leave Bare)

**What belongs here**: Key directory listing — where to find things.

**Decision**: Always bare. Relevant whenever Claude reads or writes any file.

**Condense guidance**: Remove directories that are noise (dist/, __pycache__/, .git/).
Keep the 5–10 directories that matter for understanding the project.

**Example**:
```
src/           # Application source
tests/         # Test suite
config/        # Configuration files
docs/          # Documentation
```

---

## Step 3 — Tech Stack (Leave Bare, Condense)

**What belongs here**: Language, major frameworks, test runner, primary dependencies.

**Decision**: Always bare. Condense to a single short list — no prose.

**Example (condensed)**:
```
Python 3.11+, FastAPI, SQLAlchemy, pytest, ruff
```

---

## Step 4 — Commands (One Block, All Commands)

**Hard constraint**: Never drop any command. Preserve the exact table structure.

**Condition template**:
```xml
<important if="you need to run commands, build, test, lint, format, or start the project">
| Command | Purpose |
|---------|---------|
| `npm run dev` | Start development server |
| `npm test` | Run test suite |
| `npm run lint` | Run linter |
| `npm run build` | Build for production |
</important>
```

**Do not split** the commands table into multiple blocks. One block, all commands.

---

## Step 5 — Rules and Conventions (One Block Per Rule)

Each rule or convention gets its own `<important if>` block. Never bundle multiple rules together.

### Condition Examples by Rule Type

**Import/module rules**:
```xml
<important if="you are adding imports, reorganizing modules, or changing file structure">
Import order: stdlib → third-party → local. No wildcard imports.
</important>
```

**Naming conventions**:
```xml
<important if="you are naming functions, classes, variables, or files">
Use snake_case for functions/variables, PascalCase for classes, SCREAMING_SNAKE for constants.
</important>
```

**Error handling**:
```xml
<important if="you are writing error handling, try/except blocks, or raising exceptions">
Raise specific exception types. Never swallow exceptions silently. Log before re-raising.
</important>
```

**Type annotations**:
```xml
<important if="you are writing new functions or modifying function signatures">
All public functions must have type annotations. Use `from __future__ import annotations`.
</important>
```

**Docstrings**:
```xml
<important if="you are writing or modifying public classes or functions">
Add docstrings to all public classes and functions. Use Google-style format.
</important>
```

**Commit messages**:
```xml
<important if="you are creating a git commit or pull request">
Use conventional commits: type(scope): description. Types: feat, fix, chore, docs, refactor.
</important>
```

**Dataclasses**:
```xml
<important if="you are defining new data models or classes">
Use dataclasses for data structures. Prefer immutable (frozen=True) unless mutation is required.
</important>
```

---

## Step 6 — Domain Sections (One Block Per Domain)

### Testing Patterns
```xml
<important if="you are writing, modifying, or running tests">
[testing conventions, fixture patterns, mock guidance]
</important>
```

### API Endpoints / HTTP Handlers
```xml
<important if="you are working on API endpoints, HTTP handlers, or route definitions">
[request/response patterns, validation, status codes]
</important>
```

### Database / Queries
```xml
<important if="you are writing database queries, migrations, or ORM models">
[query patterns, transaction handling, migration conventions]
</important>
```

### Authentication / Authorization
```xml
<important if="you are implementing authentication, authorization, or permission checks">
[auth patterns, token handling, role conventions]
</important>
```

### UI Components (frontend)
```xml
<important if="you are building UI components, pages, or frontend logic">
[component patterns, state management, styling conventions]
</important>
```

### Automation / Background Jobs
```xml
<important if="you are implementing background jobs, scheduled tasks, or automation">
[job patterns, retry logic, idempotency requirements]
</important>
```

### Deployment / Infrastructure
```xml
<important if="you are working on deployment, CI/CD, or infrastructure configuration">
[deploy conventions, environment variable handling, secrets management]
</important>
```

---

## Step 7 — Delete Linter-Territory

**Delete** these types of rules (the linter enforces them; the instruction is noise):

- Line length limits (`max-line-length: 88`)
- Indentation style (4 spaces vs tabs)
- Import ordering (isort/ruff handles this)
- Trailing whitespace
- Quote style (single vs double quotes)
- Semicolon usage
- Bracket spacing

**Keep** if the rule specifies project-specific behavior the linter cannot enforce:
- "Use `# noqa: E501` sparingly — prefer refactoring" (project judgment, not linter rule)
- "Do not use `type: ignore` without an explanatory comment" (project judgment)

---

## Step 8 — Delete Code Snippets

**Replace** multi-line code examples with file path references:

| Before | After |
|--------|-------|
| 10-line dataclass example | "See `src/models/user.py` for the dataclass pattern" |
| 20-line test fixture | "See `tests/conftest.py` for fixture setup" |
| Error handling example | "See `src/utils/errors.py` for error handling patterns" |

**Keep** code snippets only if:
- The snippet is a non-obvious one-liner
- No file in the codebase demonstrates the pattern
- The snippet encodes a critical decision that isn't obvious from reading code

---

## Step 9 — Delete Vague Instructions

**Delete** these patterns:

| Vague (delete) | Specific alternative (keep if present) |
|----------------|---------------------------------------|
| "Write clean code" | "Keep functions under 30 lines" |
| "Be careful" | "Never modify X without running Y" |
| "Follow best practices" | "Use the repository pattern for database access" |
| "Write good tests" | "Each new function must have at least one happy-path test" |
| "Be consistent" | "Match the style of the file you're editing" |
| "Think before coding" | (delete — no actionable behavior) |

A rule is worth keeping if it specifies a concrete, verifiable behavior. If you can't write a
test that checks whether the instruction was followed, delete it.

---

## Output Format Reference

Use `-/+` line prefix convention (from `audit-claude-config` report style):

```
+ wrapped: "Commands table" → <important if="you need to run commands...">
+ wrapped: "Rule: use dataclasses" → <important if="you are defining new data models...">
- deleted: "Use 4-space indentation" (linter enforces — Step 7)
- deleted: "Write clean code" (vague — Step 9)
~ bare:    Project identity, directory map, tech stack
```
