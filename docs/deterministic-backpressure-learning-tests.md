Agentic Workflow Architecture: Designing Deterministic Backpressure Systems

1. The Strategic Shift: From LLM "Vibing" to Deterministic Reliability

In the current landscape of AI-driven development, most organizations are trapped in a cycle of probabilistic "vibing." This occurs when engineering teams rely on a model’s general intuition—or worse, "model-on-model" critiques—to verify technical output. At scale, these workflows collapse because they lack Agentic Backpressure: the architectural requirement of providing a model with observable, deterministic feedback loops that allow it to autonomously correct its own mistakes.

The Slop Code Crisis

The proliferation of "slop code" is the direct result of circular failure. When you use an LLM-as-judge to review a builder model, you are essentially asking the same underlying logic to grade its own exam. If the builder model lacked the context or reasoning to avoid a mistake, a reviewer model—likely operating at a similar temperature and within the same latent space—is fundamentally prone to the same hallucination. This is not engineering; it is subjectivity. Models, like humans, carry incorrect assumptions deep into implementation. Relying on probabilistic feedback to catch these errors is simply "vibing" at two different temperatures.

The Thesis for High-Leverage Environments

Your mandate as an architect is to transition from a reviewer of code to a designer of high-leverage development environments. The goal is to empower the agent to self-correct via non-opinionated feedback. By building deterministic harnesses around the agent, you shift the human role from micro-managing lines of code to architecting the bounds where code can safely write itself.


--------------------------------------------------------------------------------


2. The Core Philosophy: Determinism vs. Opinionated Feedback

The technical bottleneck in autonomy is the distinction between subjective opinion and deterministic truth. An LLM can be "steered" or persuaded by role prompting, but a compiler is indifferent to persuasion. Determinism is the only path to autonomous agentic correction.

Evaluating Feedback Mechanisms

Feedback Type	Source	Determinism Level	Risk of Steering	Impact on Agent Autonomy
Deterministic Backpressure	Type Checkers, Compilers, Unit Tests	100% (Binary)	Zero (You cannot steer a compiler)	High (Autonomous iteration until pass)
Probabilistic Feedback	LLM-as-Judge, Role Prompting	Variable	High (Model-on-model bias)	Low (Requires human verification)

The "No Opinions" Mandate

Strategic value is found in tools that are either 100% right or 100% wrong. When an agent receives an error from a CLI or a type checker, it is receiving an immutable fact, not a suggestion. This "no opinions" mandate forces the model to iterate until the technical reality of the system is satisfied, effectively decoupling the quality of the output from the model's own flawed decision-making. To achieve this, we must formalize how an agent explores unknown system boundaries through "Learning Tests."


--------------------------------------------------------------------------------


3. The Prototyping Engine: Formalizing "Learning Tests"

When an agent interacts with "black-box" systems—closed APIs, legacy binaries, or undocumented SDKs—the traditional research/plan/implement cycle is insufficient. We must adopt Learning Tests, a concept formalized by Michael Feathers, to explore unknown system behaviors before committing to an architecture.

Proof-Based Development

In a high-leverage pipeline, an agent must prove the system works as assumed before writing feature code. This "Proof-Based Development" prevents "assumption leakage," where a faulty premise at 2:00 AM invalidates an entire implementation by dawn.

The Learning Test Lifecycle

1. Ingest: Read external documentation or existing code samples.
2. Hypothesize: Write a "Hello World" or proof script targeting a specific assumption (e.g., API return shapes or session behaviors).
3. Execute: Run the script against the actual black box (the live API or binary).
4. Refine: Capture Standard Out/Standard Error and inject it back into the context window to update assertions.

Case Study: Claude SDK v2 Exploration

Consider an agent exploring the Claude Agent SDK. By executing learning tests, the agent can discover that the fork_session=true flag is required for certain behaviors or that the unstable API flags change the event stream shape from V1. Instead of hallucinating a solution, the agent identifies that a resumed session ID does not equal the previous session ID by asserting against the live output. This deterministic discovery ensures the final implementation is built on proven facts rather than stale documentation.


--------------------------------------------------------------------------------


4. The Deterministic Stack: Compilers, Type Systems, and CLI Hooks

To achieve autonomy, you must repurpose standard development tools as Agentic Guardrails. The compiler is no longer a build tool; it is the primary feedback provider for the agent.

Integrating the Backpressure Loop

A sophisticated architecture forces the model to respect data ergonomics through three integrated layers:

* Type Systems as Backpressure (The BAML Case): In complex systems like BAML, architects must handle recursive types, nested classes, and multiple aliases across three distinct type systems: streaming, non-streaming, and compiler-read. By architecting a type system that enforces these mappings, you provide the deterministic pressure the agent needs to navigate complex data shapes. If a model attempts to map a "tag union" incorrectly, the type system provides the "token-in" feedback loop necessary for autonomous repair.
* The Global Stop Hook: Implement a deterministic gatekeeper. Before an agent is "allowed" to finalize a task, its output is passed through a global hook (linters, type checkers, or cargo check). If the hook fails, the error is automatically injected back into the model's context window. The agent is trapped in an autonomous loop until the deterministic checks pass.
* CLI-to-SDK Wrapping: Interfacing with complex binaries (like the Claude CLI) is error-prone for agents. Wrapping these in a typed TypeScript SDK provides a "typed, observable surface." This reduces the agent’s cognitive load by turning fuzzy CLI interactions into deterministic function calls with clear error states.


--------------------------------------------------------------------------------


5. Visualizing Integrity: Dependency Mapping as Human Backpressure

Even with automated tests, architectural "leakage"—such as boundary violations—requires high-leverage human oversight. Visualization makes these errors observable at a glance.

The Dependency Matrix

Utilize tools like Cargo-Sto to auto-generate dependency diagrams from the codebase. This allows a human architect to spot "illegal" dependencies that a linter might miss. For example, a visual map might reveal that a Bridge CFFI module is importing directly from a Compiler Emit module—a violation of the system's core integrity.

Human Backpressure Optimization

The goal of visualization is to reduce the time a human spends identifying where a problem is. By making the architecture observable, you provide "Human Backpressure." You aren't reading 20,000 lines of code; you are verifying a 100-line structural matrix. This tightens the loop between your design intent and the agent’s execution.


--------------------------------------------------------------------------------


6. Implementation Strategy: The "Harness-First" Methodology

Elite AI engineering follows a "Goat-level" strategy: spend 80% of your time designing the backpressure harness and 20% letting the agent run.

The Blueprint for Leverage

1. Define the Bounds: Enumerate all test cases and expectations in plain text before code exists.
2. Design the Harness: Build the scripts, type definitions, and assertions the model will use to check its own work.
3. Execute the Loop: Feed the harness to the model. Allow it to iterate autonomously until all deterministic checks pass.

The Binary Search of Planning

Architects must "binary search" the ideal level of planning. Avoid the stagnation of "too much planning" and the "slop code" of "not enough." Find the ideal range by "making the other mistake": deliberately over-planning one day and under-planning the next to develop the 10-dimensional instincts required for agentic orchestration.

The Final Directive: Aim for the ultimate leverage ratio—a 20,000-line implementation generated autonomously from a perfectly designed 100-line backpressure harness.


--------------------------------------------------------------------------------


7. Conclusion: The Profession of Agentic Architecture

The role of the software engineer has shifted. You are no longer a "writer of code" but an "architect of environments." This new reality requires a commitment to the "20-Hour Rule"—the professional obligation to spend significant time outside of delivery hours honing your craft, much like a doctor or lawyer.

Agentic coding is "variatic." You cannot rely on a single technique; you must develop a multidimensional set of instincts to know when to "vibe" and when to build a rigorous harness. The future of our profession belongs to those who design the deterministic systems where code can safely, and autonomously, write itself.
