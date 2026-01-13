---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# FEAT-021: Goals/Vision Ingestion Mechanism

## Summary

Create a lightweight mechanism for users to define their product goals in a format that little-loops agents can parse and use for product-focused issue identification. Goals are auto-discovered from existing project documentation during `/ll:init` and can be refined interactively or manually.

## Motivation

Product-focused analysis requires understanding:
- What the project is trying to achieve (priorities)
- Who benefits from the project (primary persona)

Without structured goals, product analysis agents cannot make meaningful recommendations. This feature provides the "ground truth" that enables goal-driven issue synthesis.

**Design Principle**: Start simple. A minimal goals file that users actually fill out is better than an elaborate template left mostly empty.

## Proposed Implementation

### 1. Simplified Goals Document Schema

Create `.claude/ll-goals.md` with minimal YAML frontmatter + markdown body:

```markdown
---
# Minimal structured metadata for programmatic access
version: "1.0"

# Primary user persona (who benefits most from this project)
persona:
  id: developer
  name: "Developer"
  role: "Software developer using this project"

# Strategic priorities (ordered by importance)
priorities:
  - id: priority-1
    name: "Primary goal description"
  - id: priority-2
    name: "Secondary goal description"
---

# Product Vision

## About This Project

[One-paragraph description of what this project does and why it exists]

## Target User

**[Persona Name]** - [Role description]

**Needs**: [What they need from this project]

**Pain Points**: [Problems they currently face that this project addresses]

## Strategic Priorities

### 1. [Priority 1 Name]
[Brief description of this priority and why it matters]

### 2. [Priority 2 Name]
[Brief description of this priority and why it matters]

## Out of Scope

- [What this project intentionally does NOT do]
```

### 2. Auto-Discovery During `/ll:init`

When product analysis is enabled during init, automatically discover goals from existing documentation:

#### Non-Interactive Mode (`--yes`)

```markdown
### Goal Discovery Process

1. **Scan documentation files** (up to 5 by default):
   - README.md (required, fail if missing)
   - CLAUDE.md or .claude/CLAUDE.md
   - docs/README.md
   - CONTRIBUTING.md
   - Any additional .md files in root

2. **Extract product context using LLM analysis**:
   - Project purpose and vision
   - Target users/audience
   - Key goals or priorities mentioned
   - Explicit non-goals or scope limitations

3. **Generate ll-goals.md**:
   - Populate frontmatter with extracted persona and priorities
   - Fill markdown sections with discovered content
   - Mark uncertain fields with [NEEDS REVIEW] placeholder

4. **Warn if incomplete**:
   ```
   ⚠ Product goals auto-generated from documentation.
   Review and update: .claude/ll-goals.md

   Extracted:
   ✓ Primary persona: Developer
   ✓ Priorities: 2 identified
   ⚠ Pain points: Not found in docs (please add manually)
   ```

5. **Do not fail** - Always create the file, even if sparse
```

#### Interactive Mode (`--interactive`)

```markdown
### Interactive Goal Discovery

1. **Analyze documentation** (same as non-interactive)

2. **Present findings for confirmation**:
   ```
   I analyzed your project documentation and extracted these product goals:

   Primary User: Developer working with Claude Code plugins

   Priorities I identified:
   1. Streamline issue management workflow
   2. Enable automation of repetitive tasks

   Does this look correct?
   [y] Yes, continue
   [n] No, let me provide corrections
   [s] Skip product analysis for now
   ```

3. **Allow refinement via AskUserQuestion**:
   - Confirm or correct persona
   - Add/remove/reorder priorities
   - Clarify any uncertain extractions

4. **Generate final ll-goals.md** with user-confirmed content
```

### 3. Configuration for Discovery

Add to config schema:

```json
{
  "product": {
    "goals_discovery": {
      "max_files": {
        "type": "integer",
        "default": 5,
        "description": "Maximum markdown files to analyze for goal discovery"
      },
      "required_files": {
        "type": "array",
        "default": ["README.md"],
        "description": "Files that must exist for discovery (warning if missing)"
      }
    }
  }
}
```

### 4. Goals Parser Utility

Create `scripts/little_loops/goals_parser.py`:

```python
"""Parser for ll-goals.md product goals document."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class Persona:
    """Primary user persona."""
    id: str
    name: str
    role: str


@dataclass
class Priority:
    """Strategic priority."""
    id: str
    name: str


@dataclass
class ProductGoals:
    """Parsed product goals from ll-goals.md."""
    version: str
    persona: Optional[Persona]
    priorities: list[Priority]
    raw_content: str  # Full markdown for LLM context

    @classmethod
    def from_file(cls, path: Path) -> Optional["ProductGoals"]:
        """Parse goals from ll-goals.md file."""
        if not path.exists():
            return None

        content = path.read_text()
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            frontmatter = yaml.safe_load(parts[1])
        except yaml.YAMLError:
            return None

        persona_data = frontmatter.get("persona")
        persona = None
        if persona_data:
            persona = Persona(
                id=persona_data.get("id", "user"),
                name=persona_data.get("name", "User"),
                role=persona_data.get("role", ""),
            )

        priorities = [
            Priority(id=p.get("id", f"priority-{i}"), name=p.get("name", ""))
            for i, p in enumerate(frontmatter.get("priorities", []), 1)
        ]

        return cls(
            version=frontmatter.get("version", "1.0"),
            persona=persona,
            priorities=priorities,
            raw_content=content,
        )

    def is_valid(self) -> bool:
        """Check if goals have minimum required content."""
        return self.persona is not None and len(self.priorities) > 0
```

### 5. Goals Validation

Add validation to `/ll:init` and as standalone check:

```python
def validate_goals(goals: ProductGoals) -> list[str]:
    """Return list of validation warnings."""
    warnings = []

    if not goals.persona:
        warnings.append("No persona defined - product analysis may be less effective")

    if not goals.priorities:
        warnings.append("No priorities defined - cannot assess goal alignment")
    elif len(goals.priorities) > 5:
        warnings.append("More than 5 priorities - consider focusing on top priorities")

    if "[NEEDS REVIEW]" in goals.raw_content:
        warnings.append("File contains [NEEDS REVIEW] placeholders - please update")

    return warnings
```

### 6. Integration Points

Goals are consumed by:
- **Product analyzer agent** (FEAT-022): Uses goals for feature gap analysis
- **Product scanning** (FEAT-023): Creates issues aligned with priorities
- **Issue templates** (ENH-024): Populates product impact fields

## Location

- **New File**: `.claude/ll-goals.md` (user project, auto-generated)
- **New Module**: `scripts/little_loops/goals_parser.py`
- **Modified**: `commands/init.md` (goal discovery integration)
- **Template**: `templates/ll-goals-template.md`

## Current Behavior

No mechanism exists for capturing product goals. All analysis is purely technical.

## Expected Behavior

When product analysis is enabled during `/ll:init`:

1. **Non-interactive**: Analyze README.md and other docs, generate `ll-goals.md` with extracted content, warn about missing/uncertain sections

2. **Interactive**: Analyze docs, present findings for confirmation, refine via questions, generate confirmed `ll-goals.md`

3. **Validation**: Warn if goals file is incomplete but don't block initialization

## Acceptance Criteria

- [ ] `goals_parser.py` module created with `ProductGoals.from_file()` method
- [ ] Unit tests for `goals_parser.py`:
  - [ ] Parse valid ll-goals.md with all fields
  - [ ] Parse minimal ll-goals.md (only required fields)
  - [ ] Handle missing file gracefully (return None)
  - [ ] Handle malformed YAML frontmatter
  - [ ] Handle missing frontmatter
- [ ] `validate_goals()` function returns appropriate warnings
- [ ] Template file `templates/ll-goals-template.md` created
- [ ] `/ll:init` creates goals file when product enabled (interactive mode)
- [ ] Auto-discovery extracts persona and priorities from README.md

## Impact

- **Severity**: High - Core data structure for Product dimension
- **Effort**: Medium - Parser, discovery logic, init integration
- **Risk**: Low - Purely additive feature, graceful degradation if docs sparse

## Dependencies

- FEAT-020: Product Analysis Opt-In Configuration (must be enabled)

## Blocked By

- FEAT-020

## Blocks

- FEAT-022: Product Analyzer Agent
- FEAT-023: Product Scanning Integration
- ENH-024: Product Impact Fields in Issue Templates

## Labels

`feature`, `product-dimension`, `configuration`, `parser`, `init`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2
