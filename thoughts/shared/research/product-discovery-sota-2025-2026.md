# SOTA Product/Business Feature Discovery Research (2025-2026)

> Research conducted: 2026-01-06
> Purpose: Inform implementation of Product analysis dimension for little-loops plugin
> Related Issues: FEAT-001, FEAT-002, FEAT-003, FEAT-004, ENH-005

---

## Executive Summary

This research explores state-of-the-art techniques for AI-powered product/business feature discovery and synthesis applicable to Claude Code plugins. The findings challenge several assumptions in the current little-loops approach and identify high-value opportunities in the "reverse discovery" space (code → product opportunities).

**Key Takeaways**:
1. Multi-agent architectures outperform single-agent by ~15% on F1 scores
2. RAG + knowledge graphs are essential for accurate code-to-requirements mapping
3. LLM-as-Judge frameworks achieve 85% alignment with human judgment
4. No existing tool performs "reverse discovery" (code → product opportunities)—this is whitespace
5. Validation frameworks (INVEST, QUS, RaT prompting) are critical for quality

---

## Table of Contents

1. [AI Product Management Tools](#1-ai-product-management-tools)
2. [Goal Document Formats](#2-goal-document-formats)
3. [Code-to-Requirements Mapping](#3-code-to-requirements-mapping)
4. [Claude Code Specific Patterns](#4-claude-code-specific-patterns)
5. [Business Value Frameworks](#5-business-value-frameworks)
6. [User Story Synthesis](#6-user-story-synthesis)
7. [Recommended Architecture](#7-recommended-architecture)
8. [Implementation Priorities](#8-implementation-priorities)
9. [Sources](#9-sources)

---

## 1. AI Product Management Tools

### Leading Commercial Platforms

| Tool | Key Capability | Relevance to ll |
|------|---------------|-----------------|
| **Zeda.io** | Voice-of-customer analysis, 5000+ integrations, "Opportunity Radar" | API integration potential, feedback-to-feature workflow |
| **Chisel.ai** | Auto-captures requests from Zendesk/Intercom/Gong, 50% faster roadmapping | Unstructured conversation analysis |
| **Productboard** | 30% increased feature linking, Jira/GitHub/Azure DevOps push | Developer tool integration patterns |
| **Greptile** | Codebase knowledge graph, context-aware PR reviews, 4x faster merges | Context-aware issue enrichment |

### Codebase Analysis Tools

**Codebase-digest** (GitHub):
- 60+ specialized prompts in 8 categories
- Business analysis prompts: Business Model Canvas, Value Proposition Canvas, SWOT, Porter's Five Forces
- Product opportunity prompts: Competitive positioning, market fit, Blue Ocean Strategy
- **Key insight**: Prompt library architecture is extensible and user-customizable

**Repomix**:
- Packages repositories into single AI-consumable files
- Tree-sitter compression: ~70% token reduction
- 4 output formats: XML, Markdown, JSON, Plain text
- **Key insight**: Single-file consolidation approach reduces context fragmentation

### Feature Discovery Automation

**From Support Tickets (NLP Pipeline)**:
1. Text preprocessing (remove punctuation, normalize, eliminate filler words)
2. Feature extraction (TF-IDF, NMF topic modeling, NER)
3. Classification (rule-based → ML-based for nuanced expressions)
4. Outputs: Recurring issue identification, feature request extraction, sentiment by feature area

**Results**: 80% reduction in manual review time, 340% spike detection in specific issues.

---

## 2. Goal Document Formats

### llms.txt Standard

**Adoption**: 600+ websites including Anthropic, Stripe, Cursor, Hugging Face, Cloudflare

**Design Philosophy**: "LLMs don't need schemas—they need context"

**Structure**:
```markdown
# Project Name

> Brief summary with essential context

Detailed project information and guidance

## Core Documentation
- [Requirements](url): Product requirements and goals
- [Architecture](url): System design

## Optional
- [Technical Details](url): Advanced specifications
```

**Recommendation**: Support llms.txt as primary auto-discovery mechanism.

### YAML Frontmatter + Markdown (Current Industry Standard)

**Best Practice**: Combine machine-readable metadata with human-readable content

```yaml
---
id: GOAL-2025-Q1-001
type: strategic_goal
priority: P1
status: active
measurable:
  - metric: issue_resolution_time
    baseline: 4.5 days
    target: 2.0 days
hierarchy:
  broader: [STRATEGIC-2025-001]
  narrower: [TACTICAL-2025-Q1-003]
links:
  features: [FEAT-001, FEAT-002]
  issues: [BUG-123]
---

# Goal: Improve Developer Experience

## Vision
[Prose content for LLM context...]
```

### Progressive Disclosure Pattern

**Nielsen Norman Group research**: "Typically have low usability beyond 2 disclosure levels"

**Application to Product Goals**:
- Level 1: Vision statement, top-level OKRs
- Level 2: Quarterly goals, key metrics
- Avoid Level 3+: Users get lost, LLMs get confused

### Context Window Optimization

**Key findings**:
- Structured data consumes disproportionately more tokens than prose
- "Lost in the middle" effect: LLMs weigh beginning/end more heavily
- YAML is moderate overhead; JSON higher; XML highest

**Recommendation**: YAML for storage, condensed prose summaries for context injection.

---

## 3. Code-to-Requirements Mapping

### Multi-Agent Systems (SOTA)

**MARE Framework** (Multi-Agents Collaboration for Requirements Engineering):
- 5 specialized agents: Stakeholders, Collector, Modeler, Checker, Documenter
- Shared workspace for artifact exchange
- **Result**: 15.4% F1 improvement over single-agent approaches

**UserTrace** (User-Level Requirements Generation):
- Phase 1: Dual-level dependency graphs (Component + File)
- Phase 2: Topological ordering, component-level IR derivation
- Phase 3: Leiden community detection, Writer/Verifier agents
- **Result**: 36% validation time reduction, 22% accuracy improvement

### RAG-Based Traceability

**Architecture**:
1. Vector-based retrieval of semantically similar requirements
2. Context-aware LLM generation
3. Chain-of-thought prompting for explainability

**Performance**: 99% validation accuracy, 85.5% recovery accuracy

**Limitation**: "Not sufficient to fully automate—requires human validation"

### Heterogeneous Graph Neural Networks (HGNNLink)

**Innovation**: Combines textual similarity AND code dependency relationships

**Key insight**: "High textual similarity doesn't indicate functional relationship—dependency information disambiguates"

**Result**: 13.36% F1 improvement over previous SOTA

### Embedding Model Comparison

| Model | Languages | Context | Performance |
|-------|-----------|---------|-------------|
| CodeBERT | 6 | 512 tokens | Baseline |
| Jina-v3 | 30+ | 8192 tokens | +28.59% F1 |

**Recommendation**: Use Jina embeddings for traceability tasks.

---

## 4. Claude Code Specific Patterns

### Feature-Dev Plugin Architecture

**7-Phase Workflow**:
1. Discovery (problem identification)
2. Codebase Exploration
3. Clarifying Questions
4. Architecture Design
5. Implementation
6. Quality Review
7. Summary

**Agent Roles**:
- `code-explorer`: Traces execution paths
- `code-architect`: Designs from multiple perspectives
- `code-reviewer`: Reviews for bugs, quality, conventions

**Gap**: Assumes feature request pre-defined; no reverse discovery.

### Multi-Agent Orchestration Patterns

**Agentic Primitives (GitHub)**:
- `.instructions.md`: Repository-specific guidance
- `.chatmode.md`: Role-based expertise with tool boundaries
- `.prompt.md`: Orchestrated workflows
- `.spec.md`: Implementation blueprints
- `.memory.md`: Cross-session knowledge retention

**Context Engineering**:
- Session splitting for different development phases
- Modular rules applying only to relevant domains
- Memory-driven development across sessions

### MCP Ecosystem (2025)

**Scale**: 97M+ monthly SDK downloads, ~2000 servers

**Available PM Integrations**:
- Jira MCP: Read/update/create issues
- Linear MCP: Full GraphQL API access
- Notion MCP: PRDs, design specs, technical docs
- Confluence MCP: Documentation search and creation

**Example Workflow**: "Paste a link to an issue, ask Claude Code to complete the ticket"

### Extended Thinking for Complex Analysis

**Capabilities**:
- Step-by-step reasoning transparency
- Budget tokens up to 32k+ for deep analysis
- Interleaved thinking with tools

**Best Use Cases**: "Ambiguous tasks such as scientific research, novel architecture design, and high-stakes financial analysis"

**Application**: Business strategy analysis where codebases are examined through market/competitive/UX lenses.

---

## 5. Business Value Frameworks

### AI-Enhanced Prioritization Models

**1. AI-Enhanced RICE**:
```
Score = (Reach × Impact × Confidence) / Effort
```
- Live customer data for Reach
- NLP analysis of reviews/tickets for Impact
- ML prediction of dev complexity for Effort
- Historical rollout data for Confidence

**2. Predictive WSJF**:
```
Score = (Business Value + Time Criticality + Risk Reduction) / Job Size
```
- Real metrics (churn, conversion, revenue) replace subjective scoring
- Scenario modeling for risk reduction outcomes

**3. AI-Driven Kano Model**:
- Continuous sentiment analysis vs. static surveys
- Real-time classification from reviews, chats, social
- Geographic/demographic pattern detection

### LLM-as-a-Judge Framework

**Scoring Methodologies**:
1. Binary classification (most reliable)
2. Pairwise comparison (>80% agreement with humans)
3. Multi-point Likert (requires explicit level definitions)
4. Reference-based evaluation (compare against answer keys)

**Enhancement Techniques**:
- Chain-of-thought prompting
- Few-shot examples (65% → 77.5% consistency)
- Position swapping for pairwise comparisons
- Token probability normalization

**Key stat**: LLM judges achieve ~85% alignment with human judgment—exceeds human-to-human agreement (81%).

### Explainability Requirements

**SHAP (SHapley Additive exPlanations)**:
- Game theory-based feature attribution
- Both local and global explanations
- Regulatory compliance (FDA, GDPR, EU AI Act)

**LIME (Local Interpretable Model-Agnostic)**:
- Fast local approximations
- Real-time application support

**Application**: Show stakeholders WHY features rank highly or get demoted.

### Customer Effort Score (CES) for Impact Estimation

**Definition**: "Percentage of customers who report a step in their Job-to-be-Done is difficult"

**Data Streams**:
- NLP on support tickets, reviews, survey responses
- Behavioral analytics (rage clicks, abandonment, extended task time)

**Scoring Formula**:
```python
CES = (
    sentiment_negativity * 0.3 +
    fix_frequency * 0.3 +
    error_rate * 0.2 +
    doc_coverage_inverse * 0.2
)
```

### Technical Debt Prioritization

**AI Techniques**:
- ML pattern recognition for best practice deviations
- NLP on commits/PRs for "temporary fix", "hack", "urgent patch"
- Architectural drift detection

**Business Impact**:
- IBM: Enterprises fully accounting for tech debt project **29% higher ROI**
- US tech debt costs: $2.41 trillion/year
- High-debt orgs allocate up to 40% of IT budget to maintenance

---

## 6. User Story Synthesis

### Refine-and-Thought (RaT) Prompting

**Two-Phase Approach**:
1. **Refine**: Filter and clean input (remove redundancy, meaningless tokens)
2. **Thought**: Generate with chain-of-thought reasoning

**Mathematical Expression**: `y ∼ p_θ^RaT(x) = p_θ^thought(p_θ^refine(x))`

**Results**: 1% ambiguous descriptions, 0.5% duplicates, 5% missing technical details

### INVEST Validation Framework

**Six Criteria**:
1. **I**ndependent: Self-contained, minimal overlap
2. **N**egotiable: Details can vary
3. **V**aluable: Delivers tangible value
4. **E**stimable: Sufficient for effort estimation
5. **S**mall: Completable in one sprint
6. **T**estable: Defined acceptance criteria

**AI Integration**: Tools automatically validate against INVEST, suggest improvements.

### Quality User Story (QUS) Framework

**13 Criteria across 3 Dimensions**:
- Syntax: Proper grammatical structure
- Pragmatics: Actionability and clarity
- Semantics: Meaningful and unambiguous

**AQUSA Tool**: Uses NLP to detect defects, suggests remedies.

### Multi-Agent Quality Enhancement (ALAS)

**Architecture**:
- Agent PO (Product Owner): Business value validation
- Agent RE (Requirements Engineer): Clarity, acceptance criteria
- Shared Knowledge Base: Task context, conversation history
- Collaborative Response Generation: Iterative building

**Results** (Austrian Post Group IT):
- Improved clarity and comprehensibility
- Better business alignment
- Satisfaction: 3.71-4.0 on 5-point scale

### Scope Creep Detection

**AI Detection Techniques**:
- Language patterns: "quick addition", "small enhancement", "while we're at it"
- Request frequency monitoring
- Change velocity analysis

**Triple Validation**:
1. Technical debt check
2. Security scanning (OWASP Top 10)
3. Privacy assessment (GDPR/CCPA)

### Acceptance Criteria Generation

**BDD Format (Given-When-Then)**:
```
Given [initial context],
When [action occurs],
Then [expected outcome].
```

**Best Practices**:
- 3-5 specific criteria per story
- Make criteria testable and measurable
- Align with INVEST framework

---

## 7. Recommended Architecture

### High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    Product Discovery Pipeline                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │  Codebase    │     │   Context    │     │   Product    │    │
│  │  Indexer     │────▶│   Store      │◀────│   Goals      │    │
│  │  (Tree-sit)  │     │  (Vectors)   │     │  (llms.txt)  │    │
│  └──────────────┘     └──────────────┘     └──────────────┘    │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Multi-Agent Analysis System                 │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │   │
│  │  │Capability│  │Gap      │  │Business │  │Quality  │    │   │
│  │  │Extractor │  │Detector │  │Analyst  │  │Validator│    │   │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘    │   │
│  │       └───────────┬┴───────────┬┴───────────┬┘          │   │
│  │                   ▼            ▼            ▼           │   │
│  │            [Shared Workspace + Debate Protocol]          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Validation Layer                        │   │
│  │   RaT Prompting → INVEST Check → QUS Framework          │   │
│  │   → Scope Creep Detection → Deduplication               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│                     [Issue Files with                           │
│                      SHAP Explainability]                       │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Specifications

**1. Capability Extractor Agent**
- Reads codebase via RAG
- Extracts "what the code can do" in product terms
- Builds component dependency graph
- Outputs: Capability model

**2. Gap Detector Agent**
- Compares capabilities against product goals
- Uses semantic similarity for matching
- Identifies missing features, partial implementations
- Outputs: Gap analysis with evidence

**3. Business Analyst Agent**
- Scores gaps using LLM-as-Judge
- Applies MCDM (TOPSIS/AHP) for prioritization
- Estimates user impact via CES methodology
- Outputs: Prioritized opportunities with explainability

**4. Quality Validator Agent**
- Applies INVEST framework
- Runs QUS criteria checks
- Detects scope creep patterns
- Deduplicates against existing issues
- Outputs: Validated, refined issues

### Data Flow

```
1. Indexing Phase (async, on codebase change)
   - Tree-sitter parse → AST
   - Jina embeddings → Vector store
   - Dependency graph → Neo4j/NetworkX

2. Discovery Phase (on /ll:scan_product)
   - Load product goals (llms.txt or ll-goals.md)
   - Capability extraction via RAG queries
   - Gap detection via semantic comparison
   - Business value scoring per gap

3. Synthesis Phase
   - RaT prompting for issue generation
   - Multi-agent debate for quality
   - INVEST/QUS validation
   - Scope check and deduplication

4. Output Phase
   - Issue files with product context
   - SHAP-style explainability per score
   - Traceability links (code → issue → goal)
```

---

## 8. Implementation Priorities

### Phase 1: Foundation (Addresses FEAT-001, FEAT-002)

| Task | Rationale |
|------|-----------|
| Support llms.txt format | Industry standard, simpler than current schema |
| Implement progressive disclosure | 2-level max for goals |
| Add YAML frontmatter parsing | Backward compatibility with structured metadata |
| Create goals validation | Warn on incomplete, don't block |

### Phase 2: Context Infrastructure

| Task | Rationale |
|------|-----------|
| Integrate Jina embeddings | 28% improvement over CodeBERT |
| Build vector store (FAISS/local) | Enable semantic search |
| Implement dual-level dependency graph | Component + file level for context |
| Create RAG retrieval pipeline | Reduce hallucination, improve accuracy |

### Phase 3: Multi-Agent System (Replaces FEAT-003)

| Task | Rationale |
|------|-----------|
| Design 4-agent architecture | 15% improvement over single agent |
| Implement shared workspace | Enable agent collaboration |
| Add debate/consensus protocol | Reduce hallucination via agreement |
| Create agent-specific prompts | Specialized expertise per role |

### Phase 4: Validation & Quality (Extends ENH-005)

| Task | Rationale |
|------|-----------|
| Implement RaT prompting | 1% ambiguity, 0.5% duplicates |
| Add INVEST validation | Industry standard quality check |
| Integrate QUS framework | 13 criteria automated check |
| Scope creep detection | Prevent feature bloat |

### Phase 5: Business Value (Extends FEAT-004)

| Task | Rationale |
|------|-----------|
| LLM-as-Judge scoring | 85% human alignment |
| MCDM integration (TOPSIS) | Multi-criteria balance |
| SHAP explainability | Stakeholder trust, compliance |
| CES-based impact estimation | No user research required |

---

## 9. Sources

### AI Product Management Tools
- [LLMs for Product Discovery: 2025 Guide](https://blog.productmanagementsociety.com/llms-for-product-discovery-unlocking-new-opportunities-2025-guide/)
- [Top 21 AI tools for product managers 2025 - Airtable](https://www.airtable.com/articles/best-ai-tools-for-product-managers)
- [Zeda.io - Voice of Customer AI](https://zeda.io)
- [Greptile - AI Code Review](https://www.greptile.com)
- [Codebase-digest](https://github.com/kamilstanuch/codebase-digest)
- [Repomix](https://repomix.com/)

### Goal Document Formats
- [llms.txt Standard](https://llmstxt.org/)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification/2025-06-18)
- [Frontmatter Format](https://github.com/jlevy/frontmatter-format)
- [Progressive Disclosure - Nielsen Norman Group](https://www.nngroup.com/articles/progressive-disclosure/)
- [SKOS Reference - W3C](https://www.w3.org/TR/skos-reference/)

### Code-to-Requirements Mapping
- [MARE: Multi-Agents Collaboration Framework](https://arxiv.org/abs/2405.03256)
- [UserTrace: Requirements Generation and Traceability](https://arxiv.org/abs/2509.11238)
- [HGNNLink: Heterogeneous Graph Neural Networks](https://link.springer.com/article/10.1007/s10515-025-00528-2)
- [RAG for Large-Scale Codebases - Qodo](https://www.qodo.ai/blog/rag-for-large-scale-code-repos/)
- [Requirements Traceability via RAG](https://publikationen.bibliothek.kit.edu/1000178589/156854596)

### Claude Code Patterns
- [Claude Code Plugins Documentation](https://github.com/anthropics/claude-code/blob/main/plugins/README.md)
- [MCP One Year Anniversary](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)
- [Agentic Project Management Framework](https://github.com/sdi2200262/agentic-project-management)
- [GitHub Agentic Primitives](https://github.blog/ai-and-ml/github-copilot/how-to-build-reliable-ai-workflows-with-agentic-primitives-and-context-engineering/)
- [Claude Extended Thinking](https://docs.claude.com/en/docs/build-with-claude/extended-thinking)

### Business Value Frameworks
- [LLM-as-a-Judge Complete Guide - Evidently AI](https://www.evidentlyai.com/llm-guide/llm-as-a-judge)
- [Survey on LLM-as-a-Judge](https://arxiv.org/html/2411.15594v1)
- [AI-Driven Technical Debt Analysis - Milestone](https://mstone.ai/blog/ai-driven-technical-debt-analysis/)
- [SHAP vs LIME Comparison 2025](https://ethicalxai.com/blog/shap-vs-lime-xai-tool-comparison-2025.html)
- [Customer Effort Prioritization - THRV](https://www.thrv.com/blog/ai-feature-prioritization-customer-effort)

### User Story Synthesis
- [Automated User Story Generation - GeneUS](https://arxiv.org/html/2404.01558v1)
- [LLM-based Agents for User Story Quality - ALAS](https://arxiv.org/html/2403.09442v1)
- [Best Practices for PRDs with Claude Code](https://www.chatprd.ai/resources/PRD-for-Claude-Code)
- [INVEST Criteria in SAFe](https://www.leanwisdom.com/blog/crafting-high-quality-user-stories-with-the-invest-criteria-in-safe/)
- [Quality User Story Framework - Springer](https://link.springer.com/article/10.1007/s00766-016-0250-x)

---

## Appendix: Comparison with Current Approach

| Aspect | Current Plan | SOTA Recommendation | Delta |
|--------|--------------|---------------------|-------|
| Goal format | YAML schema-first | llms.txt + optional YAML | Simpler, prose-heavy |
| Agent count | 1 (product-analyzer) | 4 (capability, gap, business, quality) | +15% F1 |
| Context method | Direct reading | RAG + embeddings + graph | +28% traceability |
| Discovery direction | Goals → code | Bidirectional | Whitespace opportunity |
| Value scoring | High/Medium/Low | LLM-as-Judge + MCDM + SHAP | Explainable, 85% human alignment |
| Validation | Implicit | RaT + INVEST + QUS + scope creep | Quality guarantees |
| Tech/product separation | Separate commands | Unified pipeline, multi-perspective | Efficiency gain |
