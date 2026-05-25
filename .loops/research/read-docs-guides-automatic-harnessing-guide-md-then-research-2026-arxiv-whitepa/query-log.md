## Iteration 1 — Initial Queries

**Research Topic**: Read @docs/guides/AUTOMATIC_HARNESSING_GUIDE.md then research 2026 arxiv whitepapers to find relevant whitepapers with applicability to our little-loops toolkit, focusing especially on coding agent eval harnesses. Synthesize findings into a final markdown report in a new .md file in docs/research/

**Facets and Queries**:
1. LLM-as-judge for coding agents: arxiv 2026 "LLM-as-a-judge" code generation evaluation reliability bias multi-criteria rubric
2. Coding agent eval harnesses & benchmarks: arxiv 2026 SWE-bench coding agent evaluation harness benchmark reproducibility execution-based
3. Multi-stage / layered evaluation pipelines for agents: arxiv 2026 agent evaluation pipeline staged verification gates test-judge-invariant cascade
4. Iterative self-refinement & retry loops in code agents: arxiv 2026 self-refine iterative repair coding agent feedback loop convergence retries
5. Agent stall detection, no-op convergence, and budget control: arxiv 2026 LLM agent stall detection no-op termination iteration budget early stopping

## Iteration 2 — Gap-Filling Queries

**Coverage gaps addressed**:
- LLM-as-judge for coding agents (score: 4/5): missing cost/latency of multi-judge ensembles, adversarial robustness (prompt-injection against the judge), and large-scale judge-vs-human calibration data
- Coding agent eval harnesses & benchmarks (score: 4/5): missing container/sandbox reproducibility issues, dataset contamination detection methods, and harness-induced variance (seed/temperature/system-prompt sensitivity)
- Multi-stage / layered evaluation pipelines for agents (score: 4/5): missing gate-calibration failure modes (false rejection of good outputs), compounding cost of cascaded stages, and dependency-aware gate ordering
- Iterative self-refinement & retry loops in code agents (score: 4/5): missing negative results where refinement degrades quality, oscillation between two bad solutions, and diminishing-returns curves across model-capability tiers
- Agent stall detection, no-op convergence, and budget control (score: 4/5): missing false-positive stall detection (premature termination of slow-but-progressing agents), budget allocation across parallel sub-agents, and stall patterns in tool-heavy / multi-agent settings

**Queries**:
1. LLM-as-judge for coding agents: arxiv 2026 LLM judge ensemble cost latency tradeoff prompt-injection adversarial robustness code evaluation
2. LLM-as-judge for coding agents: arxiv 2026 LLM-as-judge calibration human ground truth code review large-scale agreement disagreement
3. Coding agent eval harnesses & benchmarks: arxiv 2026 SWE-bench reproducibility container sandbox variance seed temperature contamination detection
4. Coding agent eval harnesses & benchmarks: arxiv 2026 coding benchmark data leakage memorization test-set contamination detection 2026
5. Multi-stage / layered evaluation pipelines for agents: arxiv 2026 cascade evaluation false rejection gate calibration cost compounding agent pipeline
6. Multi-stage / layered evaluation pipelines for agents: arxiv 2026 staged verification dependency-aware routing gate ordering agent failure modes
7. Iterative self-refinement & retry loops in code agents: arxiv 2026 self-refine negative results degradation oscillation code repair diminishing returns
8. Iterative self-refinement & retry loops in code agents: arxiv 2026 LLM self-correction failure modes overfitting test feedback repair loop harm
9. Agent stall detection, no-op convergence, and budget control: arxiv 2026 false positive stall premature termination LLM agent slow progress budget allocation parallel
10. Agent stall detection, no-op convergence, and budget control: arxiv 2026 multi-agent tool-use stall detection deadlock convergence budget orchestration
11. Cross-cutting: arxiv 2026 LLM-judge as stopping criterion vs heuristic stall signal agreement disagreement termination
12. Cross-cutting: arxiv 2026 execution-based eval interaction with self-repair loop overfitting test signal reward hacking coding agent

## Iteration 3 — Gap-Filling Queries

**Coverage gaps addressed**:
- No facet has score < 4. All facets meet or exceed the threshold; average coverage is 4.8/5 (96%), above the 85% target.
- Multi-stage / layered evaluation pipelines for agents (score: 4/5, relative lowest): residual gaps around empirical comparisons of cascaded-gate harnesses vs single-judge baselines on real coding workloads, and around adaptive / learned gate ordering (vs hand-tuned).

**Queries**:
1. Multi-stage / layered evaluation pipelines for agents: arxiv 2026 cascaded verification harness vs single judge empirical comparison coding agent throughput precision
2. Multi-stage / layered evaluation pipelines for agents: arxiv 2026 learned adaptive gate ordering evaluation pipeline reinforcement bandit agent verifier routing
3. Cross-cutting: arxiv 2026 unified framework eval harness retry loop stall detector judge feedback signal coding agent end-to-end
4. Cross-cutting: arxiv 2026 reward hacking gaming verifier loop refinement judge collusion execution-based test coding agent

