---
description: Search for and score public GitHub repositories as demo candidates for little-loops
allowed-tools:
  - Read
  - Write
  - Bash(git:*, gh:*)
  - WebSearch
  - mcp__web-search-prime__webSearchPrime
  - mcp__web_reader__webReader
arguments:
  - name: query
    description: GitHub search query (e.g., "language:typescript stars:>1000")
    required: false
  - name: limit
    description: Number of repos to search and score (default: 5)
    required: false
  - name: min_score
    description: Minimum score to include in catalog (default: 35)
    required: false
---

# Find Demo Repositories

Search for public GitHub repositories suitable as demo candidates for the little-loops plugin, score them against the evaluation rubric, and maintain a master catalog.

## Configuration

- **Catalog file**: `.demo/catalog.yaml`
- **Summaries directory**: `.demo/summaries/`
- **Rubric**: `docs/demo-repo-rubric.md`
- **Default limit**: 5 repositories
- **Default min_score**: 35 (Acceptable threshold)

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `query` | GitHub search query | searches for starter templates/boilerplates |
| `limit` | Number of repos to evaluate | 5 |
| `min_score` | Minimum score (0-80) to include | 35 |

## Process

### 1. Parse Arguments and Initialize

```
query = arg1 if provided else default search strategy
limit = parseInt(arg2) if provided else 5
min_score = parseInt(arg3) if provided else 35
```

Create progress tracking with TaskCreate:
- Searching for repositories
- Evaluating repositories against rubric
- Generating catalog entries
- Creating summary report

### 2. Search for Repositories

Use web search to find public GitHub repositories. Try multiple search strategies:

**Default queries (when no query provided):**
- `site:github.com "starter template" OR "boilerplate" OR "example project"`
- `site:github.com "awesome list" curated repositories`
- `site:github.com stars:>500 pushed:>2024-01-01`

**User query (when provided):**
- Prefix with `site:github.com` if not present
- Add filters like `stars:>100`, `language:typescript` etc.

**Alternative: Use GitHub CLI (gh) if available:**
```bash
gh search repos --limit {limit} --json name,owner,description,url,stargazersCount,language,licenseInfo,defaultBranchRef "{query}"
```

Extract repository URLs from search results. Aim to get `limit` unique repositories.

### 3. Load Existing Catalog

Check if `.demo/catalog.yaml` exists:
```bash
if [ -f .demo/catalog.yaml ]; then
  # Load existing catalog to check for duplicates
  # Track repo keys that already exist
fi
```

### 4. Evaluate Each Repository

For each discovered repository:

#### 4.1. Fetch Repository Metadata

Use `gh` CLI or web reader to gather:
- Repository name and owner
- Description
- Star count
- Primary language
- License
- Default branch
- Clone URL

Example using gh CLI:
```bash
gh repo view {owner}/{repo} --json name,owner,description,url,stargazersCount,language,licenseInfo,defaultBranchRef,repositoryTopics
```

#### 4.2. Analyze Repository Contents

Use `mcp__web_reader__webReader` to fetch key files:
- README.md (or README.rst, README.adoc)
- package.json, pyproject.toml, or Cargo.toml
- LICENSE file
- Test directories (tests/, __tests__, test/)
- CI config (.github/workflows/, .gitlab-ci.yml)
- Documentation (docs/, CONTRIBUTING.md, ARCHITECTURE.md)

#### 4.3. Score Against Rubric Categories

Apply the 10-category rubric from `docs/demo-repo-rubric.md`:

1. **Visual / UI Layer (0-10)**: Check for frontend framework, components, routing
2. **Test Coverage & Variety (0-10)**: Look for test files, test types, CI config
3. **Code Quality & Stability (0-10)**: Check for linting, type safety, CI/CD
4. **Feature Expansion Surface Area (0-10)**: Identify gaps, TODOs, incomplete features
5. **Documentation & Key Documents (0-10)**: Check README, architecture docs, API docs
6. **Project Size & Complexity (0-10)**: Estimate LOC, file count, module count
7. **Build & Run Simplicity (0-10)**: Check dependencies, setup complexity
8. **License & Fork-Friendliness (0-5)**: Verify permissive license
9. **Language & Ecosystem Fit (0-5)**: Assess mainstream familiarity
10. **Demo Narrative Potential (0-10)**: Evaluate relatable domain

For each category, provide:
- Score (within max points)
- Justification (brief explanation)

#### 4.4. Calculate Total and Verdict

```
total_score = sum of all category scores
verdict = rating band based on total:
  - 65-80: "Excellent candidate — use it"
  - 50-64: "Good candidate — minor gaps to work around"
  - 35-49: "Acceptable — will need prep work or caveats"
  - <35: "Poor fit — keep looking"
```

#### 4.5. Filter by min_score

Skip repository if `total_score < min_score`.

### 5. Generate Catalog Entry

Create/update `.demo/catalog.yaml` with new entries:

```yaml
catalog:
  - repo: "owner/repo-name"
    url: "https://github.com/owner/repo"
    added_date: "2026-01-27"
    scores:
      visual_ui_layer: 7
      test_coverage: 6
      code_quality: 8
      feature_expansion: 9
      documentation: 5
      project_size: 7
      build_simplicity: 6
      license_fork: 4
      ecosystem_fit: 5
      demo_narrative: 8
    total_score: 65
    verdict: "Excellent candidate — use it"
    notes: |
      Polished React dashboard with good test coverage. Missing architecture docs
      but has clear feature expansion opportunities.
    tags:
      - react
      - typescript
      - dashboard
    language: TypeScript
    stars: 2500
    license: MIT
metadata:
  last_updated: "2026-01-27T12:00:00Z"
  total_evaluated: 42
  total_in_catalog: 38
  average_score: 52.3
```

**Important:** Never overwrite existing entries. Append new entries and sort by `total_score` descending.

### 6. Generate Summary Report

Create `.demo/summaries/summary-{timestamp}.md`:

```markdown
# Demo Repository Search Summary

**Date**: 2026-01-27
**Query**: {search_query}
**Limit**: {limit}
**Min Score**: {min_score}

## Results

- **Repositories searched**: {searched_count}
- **Repositories scored**: {scored_count}
- **Added to catalog**: {added_count}
- **Below threshold**: {skipped_count}

## Top Candidates

| Repo | Score | Verdict | Language | Stars |
|------|-------|---------|----------|-------|
| owner/repo1 | 72 | Excellent candidate | TypeScript | 3500 |
| owner/repo2 | 58 | Good candidate | Python | 1200 |

## Category Breakdown

### Visual / UI Layer
- Best: owner/repo1 (9/10) — Rich interactive dashboard
- Worst: owner/repo5 (2/10) — CLI tool only

[Continue for other categories...]

## Recommendations

1. **Best overall**: [owner/repo1] — Balanced scores across all categories
2. **Easiest setup**: [owner/repo3] — Zero-config, runs immediately
3. **Most expandable**: [owner/repo2] — Large feature gap, clear additions

## New Entries Added

[Detailed notes for each new entry]
```

### 7. Update Progress and Output

Update TaskCreate items as completed. Display summary to user with:
- Number of repos evaluated
- Top 3 candidates
- Link to catalog file
- Link to summary report

---

## Example Usage

```bash
# Search with default criteria (5 repos, min score 35)
/ll:find_demo_repos

# Custom query for React dashboards
/ll:find_demo_repos "react dashboard admin template" 10

# High threshold for excellent candidates only
/ll:find_demo_repos --min_score 60

# Find Python FastAPI projects
/ll:find_demo_repos "language:python framework:fastapi stars:>500" 5 40
```

---

## Scoring Guidelines

When evaluating repositories, be objective and consistent:

1. **Visual / UI Layer**: Actually look at the repo. Check for screenshots, demo links, or component structure.
2. **Test Coverage**: Count test files vs source files. Look for CI badges.
3. **Code Quality**: Check for .eslintrc, pyproject.toml with ruff/mypy, similar tooling.
4. **Feature Expansion**: Read issues, TODO comments, and project README for "roadmap" sections.
5. **Documentation**: Look beyond README. Check for docs/ folder, ARCHITECTURE.md, API.md.
6. **Project Size**: Use `gh` to get file counts, or estimate from directory structure.
7. **Build Simplicity**: Check README's "Getting Started" section. Count prerequisites.
8. **License**: Use `gh` to get license info. MIT/Apache-2.0/BSD are permissive.
9. **Ecosystem**: TypeScript/React, Python/FastAPI, Go are mainstream. Haskell/Erlang are niche.
10. **Demo Narrative**: Can you explain the app in one sentence? Todo/blogging apps score high.

---

## Output Files

| File | Description |
|------|-------------|
| `.demo/catalog.yaml` | Master catalog of all scored repositories |
| `.demo/summaries/summary-{timestamp}.md` | Human-readable summary of this run |

---

## Integration

After finding repositories:
1. Review top candidates in `.demo/catalog.yaml`
2. Fork and clone a high-scoring repository
3. Run `/ll:scan_codebase` to discover issues
4. Run `/ll:manage_issue` to process issues
