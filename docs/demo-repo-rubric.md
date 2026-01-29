# Little-Loops Demo Repository Evaluation Rubric

Rubric for evaluating public GitHub repositories as demo candidates for the `little-loops` Claude Code Plugin and Pip Package.

## Demo Features Showcased

- Issue Discovery
- Issue Refinement
- Issue normalization, verification, and alignment with Key Product/Architectural Documents
- Issue implementation with `ll-parallel`, `ll-auto`, and/or `ll-sprint`
- Issue creation from unit, integration, and e2e tests
- Loop creation with `/ll:create_loop`
- Loop execution with `ll-loop`

## Categories

### 1. Visual / UI Layer (0-10 points)

| Score | Criteria |
|-------|----------|
| 0-2 | No UI; CLI-only or library/backend-only |
| 3-4 | Minimal UI (basic HTML, simple forms) |
| 5-6 | Functional UI with multiple views/pages |
| 7-8 | Polished UI with components, routing, state management |
| 9-10 | Rich interactive UI with animations, dashboards, or data visualization |

**Why it matters**: Loop creation with `ll-loop` shines when you can visually evaluate the app and generate issues from what you see.

### 2. Test Coverage & Variety (0-10 points)

| Score | Criteria |
|-------|----------|
| 0-2 | No tests or only a handful of trivial tests |
| 3-4 | Unit tests only, limited coverage |
| 5-6 | Unit + integration tests with moderate coverage |
| 7-8 | Unit + integration + some e2e tests, good coverage |
| 9-10 | Comprehensive unit/integration/e2e suites with CI passing |

**Why it matters**: Demos issue creation from test failures and validates implementations during `ll-parallel`/`ll-auto` runs.

### 3. Code Quality & Stability (0-10 points)

| Score | Criteria |
|-------|----------|
| 0-2 | Messy, inconsistent style, no linting, frequent breakage |
| 3-4 | Some structure but inconsistent patterns |
| 5-6 | Clean code, consistent style, linter configured |
| 7-8 | Well-structured with clear architecture, type safety, CI/CD |
| 9-10 | Exemplary codebase: typed, linted, documented, robust CI |

**Why it matters**: A stable baseline ensures demo failures come from intentional changes, not pre-existing rot. Issue discovery is more impressive against clean code.

### 4. Feature Expansion Surface Area (0-10 points)

| Score | Criteria |
|-------|----------|
| 0-2 | Feature-complete or extremely narrow scope |
| 3-4 | Limited room; most obvious features already exist |
| 5-6 | Some clear gaps (missing pages, incomplete CRUD, no dark mode, etc.) |
| 7-8 | Multiple obvious feature additions possible (new views, filters, export, settings) |
| 9-10 | Large, clear backlog of reasonable features; extensible architecture invites additions |

**Why it matters**: Core demo flow is discover issues -> refine -> implement. If there's nothing to add, the demo falls flat.

### 5. Documentation & Key Documents (0-10 points)

| Score | Criteria |
|-------|----------|
| 0-2 | No README or docs |
| 3-4 | Basic README only |
| 5-6 | README + some architecture or contributing docs |
| 7-8 | README + architecture doc + API doc or product spec |
| 9-10 | Comprehensive docs: architecture, product vision, contributing guide, ADRs |

**Why it matters**: Issue alignment and verification require Key Product Documents and Key Architectural Documents to align against. More docs = better demo of normalization/verification/alignment.

### 6. Project Size & Complexity (0-10 points)

| Score | Criteria |
|-------|----------|
| 0-2 | Toy project (<500 LOC) or massive monorepo (>100k LOC) |
| 3-4 | Too small to be interesting or too large to navigate in a demo |
| 5-6 | Small-medium (1k-5k LOC), understandable but shallow |
| 7-8 | Medium (5k-15k LOC), multiple modules, clear boundaries |
| 9-10 | Sweet spot (5k-30k LOC): complex enough to be realistic, small enough to demo in real-time |

**Why it matters**: Too small and there's nothing to discover. Too large and `ll-parallel`/`ll-auto` runs take too long for a live demo.

### 7. Build & Run Simplicity (0-10 points)

| Score | Criteria |
|-------|----------|
| 0-2 | Requires complex infra (databases, cloud services, API keys) |
| 3-4 | Multiple dependencies or services needed |
| 5-6 | Standard build, one external dependency (e.g., a DB via Docker) |
| 7-8 | Simple setup: `npm install && npm start` or equivalent |
| 9-10 | Zero-config: clone and run, no external services needed |

**Why it matters**: Live demos fail at setup. The simpler the startup, the more time spent showing `ll` features.

### 8. License & Fork-Friendliness (0-5 points)

| Score | Criteria |
|-------|----------|
| 0-1 | Restrictive license or no license |
| 2-3 | Permissive license (MIT, Apache 2.0, BSD) |
| 4-5 | Permissive license + actively maintained + welcoming to forks/contributions |

**Why it matters**: You need to fork publicly and push changes. License must allow this.

### 9. Language & Ecosystem Fit (0-5 points)

| Score | Criteria |
|-------|----------|
| 0-1 | Niche language/framework with poor tooling |
| 2-3 | Common language but unfamiliar framework |
| 4-5 | Mainstream stack (TypeScript/React, Python/FastAPI, etc.) familiar to demo audience |

**Why it matters**: Audience recognition of the stack increases engagement and perceived applicability.

### 10. Demo Narrative Potential (0-10 points)

| Score | Criteria |
|-------|----------|
| 0-2 | Abstract/technical project hard to explain (compiler, protocol library) |
| 3-4 | Understandable but dry domain |
| 5-6 | Relatable domain (todo app, blog, dashboard) |
| 7-8 | Engaging domain with clear user stories (project tracker, e-commerce, chat app) |
| 9-10 | Immediately compelling: audience understands the app in 10 seconds and can imagine features |

**Why it matters**: The best demo repo tells a story. "Here's an app you recognize. Watch us find issues, refine them, and ship fixes — all automated."

## Scoring Summary

| Category | Max Points |
|----------|-----------|
| Visual / UI Layer | 10 |
| Test Coverage & Variety | 10 |
| Code Quality & Stability | 10 |
| Feature Expansion Surface Area | 10 |
| Documentation & Key Documents | 10 |
| Project Size & Complexity | 10 |
| Build & Run Simplicity | 10 |
| License & Fork-Friendliness | 5 |
| Language & Ecosystem Fit | 5 |
| Demo Narrative Potential | 10 |
| **Total** | **80** |

## Rating Bands

| Range | Verdict |
|-------|---------|
| 65-80 | Excellent candidate — use it |
| 50-64 | Good candidate — minor gaps to work around |
| 35-49 | Acceptable — will need prep work or caveats |
| <35 | Poor fit — keep looking |

## Evaluation Template

```
### [Repository Name](https://github.com/owner/repo)

| Category | Score | Notes |
|----------|-------|-------|
| Visual / UI Layer | /10 | |
| Test Coverage & Variety | /10 | |
| Code Quality & Stability | /10 | |
| Feature Expansion Surface Area | /10 | |
| Documentation & Key Documents | /10 | |
| Project Size & Complexity | /10 | |
| Build & Run Simplicity | /10 | |
| License & Fork-Friendliness | /5 | |
| Language & Ecosystem Fit | /5 | |
| Demo Narrative Potential | /10 | |
| **Total** | **/80** | |

**Verdict**:
```
