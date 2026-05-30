# CUA Repos as Example FSM Loop Use-Cases

**Date:** 2026-05-30
**Author:** Research synthesis for little-loops
**Status:** Recommendation report

## TL;DR

[HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) is the gold-standard exemplar for little-loops' generator-evaluator FSM harnesses because it wraps creative software (Blender, GIMP, ComfyUI, Inkscape, Audacity, LibreOffice, OBS, Stable Diffusion, …) into agent-native CLIs that produce **evaluable, concrete, visual/interactive artifacts** — the exact workload the existing `html-anything.yaml`, `svg-image-generator.yaml`, and `cli-anything-bootstrap.yaml` loops are optimized for. Adjacent open-source CUA repos that slot into the same pattern fall into four tiers:

- **Tier 1 (Desktop/Browser CUA infrastructure):** trycua/cua, browser-use, Skyvern, Stagehand.
- **Tier 2 (Creative-tool MCP servers):** Blender MCP, Figma MCP, ComfyUI MCP.
- **Tier 3 (Single-domain artifact generators):** abi/screenshot-to-code, Mrxyy/screenshot-to-page, OpenKombai.
- **Tier 4 (Research-grade evaluators):** xlang-ai/OpenCUA, OpenGVLab/ScaleCUA.

**Top three to ship as new example loops:** `browser-anything.yaml` (browser-use/stagehand), `blender-anything.yaml` (Blender MCP), `screenshot-to-code-loop.yaml` (abi/screenshot-to-code). Each pairs LLM judgment with an external scorer (Playwright render diff, MCP result, exit code) — satisfying the MR-1 rule for meta-loops.

---

## 1. What Makes a CLI/Skill "FSM-Loop-Friendly"

Five properties, derived from CLI-Anything and little-loops' loop schema (`scripts/little_loops/fsm/schema.py`, `loops/*.yaml`):

| Property | Why it matters | Maps to schema |
|---|---|---|
| **Evaluable artifact output** | Loops need something to score, not chat text | `exit_code`, `mcp_result`, `output_json`, screenshot rubric via `llm_structured` |
| **Structured output mode** (`--json`) | Cheap downstream parsing, reliable composition | `output_json` evaluator |
| **Non-destructive / additive refinement** | Repeated loop runs must be safe; refinement should never destroy user work | Enables `on_partial` routing with diff-stall guards |
| **Cheap-first evaluation chain** | Fast inner loop = practical iteration | `check_concrete → check_mcp → check_skill → check_semantic` |
| **Composable / emits downstream artifacts** | One loop produces inputs for the next | Hash-cached state, `.loops/generated/*.yaml` emission (cf. `cli-anything-bootstrap.yaml`) |

A repo is recommended below only if it satisfies **at least 3 of 5**.

---

## 2. Why CLI-Anything Is the Gold Standard

- **Breadth of creative artifacts.** Ships pre-built CLIs for 30+ apps including Blender (3D), GIMP, Krita, Inkscape (raster/vector), Audacity (audio), OBS Studio (capture), LibreOffice (docs/PDF), Draw.io (diagrams), ComfyUI, InvokeAI, Stable Diffusion (image gen). Every one is a candidate generator-evaluator loop.
- **Real-software backends.** LibreOffice writes a real PDF; sox produces real audio; Blender renders real PNGs. The evaluator always has a concrete artifact to score — never a hallucinated success report.
- **Agent-native by design.** Every command has `--help` (discoverable) and `--json` (parseable). Zero text-parsing hacks needed for loop composition.
- **Bootstrap pipeline is itself a meta-loop.** Its 7 phases (Analyze → Design → Implement → Plan Tests → Write Tests → Document → Publish) are already wrapped in [`loops/cli-anything-bootstrap.yaml`](../scripts/little_loops/loops/cli-anything-bootstrap.yaml) with MR-1-compliant external evaluators (`pip install` exit code, `--help` walker, pytest pass-rate) — no LLM self-grade.
- **Trust-preserving refinement.** Gap-analysis mode inventories existing coverage and proposes only additive changes (per ENH-1782), so the outer FSM can re-enter the refinement state safely.

In short: CLI-Anything proves a CLI becomes "FSM-loop-friendly" when it produces evaluable concrete artifacts, supports additive refinement, exposes fast non-LLM evaluators, and is composable via structured output.

---

## 3. Recommended CUA Repos by Tier

### Tier 1 — Desktop & Browser CUA Infrastructure
The closest fit: tools that give an agent the *entire computer*, where each iteration is a screenshot → action → new screenshot.

| Repo | What it is | FSM-loop fit | Suggested loop shape |
|---|---|---|---|
| **[trycua/cua](https://github.com/trycua/cua)** (~15k★) | OSS infra: sandboxes, SDKs, benchmarks for desktop CUAs across macOS/Linux/Windows. Ships `cua-driver` MCP server with screenshot/click/type tools. Cloud sandbox option ("Docker for CUAs"). | The MCP server gives `check_mcp` a direct deterministic channel. OSWorld / ScreenSpot / Windows Arena benchmarks plug in as ready-made eval suites. Ephemeral sandboxes make destructive trials safe. | `init → plan_action → execute_in_sandbox → screenshot → check_mcp(state) → check_semantic(rubric) → on_no: replan / on_yes: done` |
| **[browser-use/browser-use](https://github.com/browser-use/browser-use)** (~93k★) | Python VLM screenshot-driven browser loop ("websites accessible for AI agents") | Already *is* an FSM loop conceptually: prompt VLM → action → screenshot → repeat with step cap. Trivial to harness with a Playwright screenshot evaluator. | `plan → act → screenshot → check_semantic(goal_met) → done / iterate` |
| **[Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern)** (~21k★) | Three-phase **Planner → Actor → Validator** browser agent. Validator triggers replanning on failure. WebVoyager: 45 → 86% v1→v2. | The Validator phase is *literally* `check_semantic` with `on_no: replan` routing. Reference architecture for "agent loop inside, FSM loop outside". | `plan → act → validate → on_no: plan / on_yes: done` |
| **[browserbase/stagehand](https://github.com/browserbase/stagehand)** | `act / extract / observe / agent` primitives over Playwright; TS + Python; works with OpenAI/Anthropic/Gemini via Vercel AI SDK. | Four primitives are clean FSM action verbs. `extract` returns structured data → `output_json` evaluator without parsing tricks. | `observe → act → extract → check_concrete(schema) → done / iterate` |

### Tier 2 — Creative-Tool MCP Servers
Complement CLI-Anything by exposing live Python/HTTP scripting alongside the CLI surface. Each is a drop-in target for a generator-evaluator harness.

- **[Blender MCP](https://blender-mcp.org/)** (and Blender MCP Pro with 100+ tools) — agents drive Blender for scene generation, materials, rendering, arbitrary Python. **Loop fit:** prompt → scene build → render PNG → visual-rubric LLM scorer → mutate → iterate. Same shape as `svg-image-generator.yaml`, swap SVG out for rendered PNG. Evaluator stack: `mcp_result` (render succeeded) + `llm_structured` (visual rubric).
- **Figma MCP** (`mcp-server-figma` family + official Figma Dev Mode MCP) — pull design context, generate code, compare. **Loop fit:** Figma component → screenshot-to-code → render → diff vs source. Evaluator: pixel/structure diff (concrete) + semantic rubric.
- **ComfyUI MCP** — image-gen graph control. **Loop fit:** prompt → graph build → render → CLIP-similarity or rubric score → mutate graph → iterate. Natural fan-out target for parallel prompt variants.

### Tier 3 — Single-Domain Artifact Generators
Drop-in replacements for the `html-anything.yaml` / `svg-image-generator.yaml` shape — pure visual refinement loops.

- **[abi/screenshot-to-code](https://github.com/abi/screenshot-to-code)** — screenshot → HTML/Tailwind/React/Vue (Gemini 3, Claude Opus 4.5 supported). **Loop fit:** target screenshot *is* the rubric; evaluator renders generated code in Playwright and visually diffs. Structurally identical to `html-anything.yaml` but image-in instead of prompt-in.
- **[Mrxyy/screenshot-to-page](https://github.com/Mrxyy/screenshot-to-page)** — same niche, supports OSS VLMs (Qwen-VL). Useful for fully-local example loops without API keys.
- **OpenKombai** — local-LLM screenshot-to-React (Llama 3.2 Vision / Qwen 2.5). Demonstrates loops that run end-to-end on local models.

### Tier 4 — Research-Grade CUA Foundations
Too heavy for day-to-day demos, but ideal as *external evaluators* in meta-loops measuring whether a generated CLI/skill genuinely improves agent task success.

- **[xlang-ai/OpenCUA](https://github.com/xlang-ai/OpenCUA)** (NeurIPS 2025 Spotlight) — AgentNet dataset spanning 3 OSes and 200+ apps; OpenCUA-72B is #1 on OSWorld-Verified. **Use as evaluator** in `cli-anything-bootstrap.yaml`–style meta-loops to score "does this generated CLI raise an OpenCUA agent's task success rate on the underlying app?"
- **[OpenGVLab/ScaleCUA](https://github.com/OpenGVLab/ScaleCUA)** (ICLR 2026 Oral) — cross-platform (Windows/macOS/Ubuntu/Android) with an Online Evaluation Suite. Same role as OpenCUA: external, non-LLM-self-grade scorer.
- **[trycua/acu](https://github.com/trycua/acu)** — curated list. Use as a discovery source when expanding the example gallery.

---

## 4. Three Recommended New Example Loops

Following the existing template trio (`html-anything.yaml`, `svg-image-generator.yaml`, `cli-anything-bootstrap.yaml`), ship these three as the next demo gallery additions. Each maps to a known-good YAML shape already in the repo.

### 4.1 `browser-anything.yaml` — wrap browser-use or Stagehand
- **Template parent:** `html-anything.yaml` (generator-evaluator with rendered output).
- **Generator state:** invoke browser-use / Stagehand to execute a user goal in a sandboxed browser, capturing screenshot + extracted JSON.
- **Evaluator chain:** `check_concrete` (extracted JSON validates against goal schema) → `check_semantic` (LLM rubric on screenshot: "was the goal achieved? rate clarity, completeness, side effects").
- **MR-1 compliance:** schema validation is the non-LLM scorer paired with the LLM rubric.

### 4.2 `blender-anything.yaml` — wrap Blender MCP
- **Template parent:** `svg-image-generator.yaml` (visual rubric on a rendered artifact).
- **Generator state:** Blender MCP renders a scene from a prompt; outputs PNG + scene metadata JSON.
- **Evaluator chain:** `mcp_result` (render call returned a file) → `llm_structured` (4-criterion rubric: composition, lighting, prompt adherence, craft).
- **Iteration:** on_partial → mutate Python script / scene graph; on_no → replan from scratch.

### 4.3 `screenshot-to-code-loop.yaml` — wrap abi/screenshot-to-code
- **Template parent:** `html-anything.yaml` inverted (image-in instead of prompt-in).
- **Generator state:** screenshot-to-code emits HTML/Tailwind.
- **Evaluator chain:** `exit_code` (code parses / Tailwind builds) → `check_mcp` (Playwright renders cleanly) → image diff scorer comparing render vs target screenshot → `llm_structured` rubric on residual visual gaps.
- **MR-1 compliance:** image-diff is the deterministic external scorer; LLM rubric only refines.

All three slot into the existing 5-phase pipeline (`check_concrete → check_mcp → check_skill → check_semantic → check_invariants`) and reuse evaluator types already implemented.

---

## 5. Selection Criteria Recap

A repo earned a recommendation only if it satisfies **at least 3 of 5**:

1. Produces a concrete artifact (file / screenshot / render).
2. Has structured output or MCP surface.
3. Supports iterative refinement (additive, not destructive).
4. Has a non-LLM evaluator path (test / render / image-diff / exit-code / MCP result).
5. License compatible with example inclusion (MIT / Apache-2 / similar).

All Tier 1–3 recommendations satisfy ≥4. Tier 4 satisfies (1), (4) only — but uniquely valuable as external evaluators rather than as loop subjects.

---

## 6. Sources

**Core repos:**
- [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) — "Making ALL Software Agent-Native"
- [trycua/cua](https://github.com/trycua/cua) — open-source desktop CUA infrastructure
- [trycua/acu](https://github.com/trycua/acu) — curated CUA resource list
- [xlang-ai/OpenCUA](https://github.com/xlang-ai/OpenCUA) — NeurIPS 2025 Spotlight
- [OpenGVLab/ScaleCUA](https://github.com/OpenGVLab/ScaleCUA) — ICLR 2026 Oral
- [browser-use/browser-use](https://github.com/browser-use/browser-use) — VLM browser agent
- [Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern) — Planner-Actor-Validator browser agent
- [browserbase/stagehand](https://github.com/browserbase/stagehand) — Playwright + AI primitives
- [abi/screenshot-to-code](https://github.com/abi/screenshot-to-code) — screenshot → HTML/React
- [Mrxyy/screenshot-to-page](https://github.com/Mrxyy/screenshot-to-page) — OSS-VLM variant
- [Blender MCP](https://blender-mcp.org/) — Blender ↔ MCP bridge

**Background reading:**
- [VentureBeat: OpenCUA rivals proprietary models](https://venturebeat.com/business/opencuas-open-source-computer-use-agents-rival-proprietary-models-from-openai-and-anthropic)
- [trycua/cua review — andrew.ooo](https://andrew.ooo/posts/trycua-cua-open-source-computer-use-agents/)
- [Stagehand vs Browser Use vs Playwright (NxCode, 2026)](https://www.nxcode.io/resources/news/stagehand-vs-browser-use-vs-playwright-ai-browser-automation-2026)
- [Top AI GitHub Repositories in 2026 (ByteByteGo)](https://blog.bytebytego.com/p/top-ai-github-repositories-in-2026)
- [Best MCP Servers for Creative AI (Fastio, 2026)](https://fast.io/resources/best-mcp-servers-for-creative-ai/)
- [CLI-Anything: Turning Software into Agent-Usable CLI (Knightli, 2026-05)](https://knightli.com/en/2026/05/25/cli-anything-agent-native-cli/)
