# Example FSM Loop Candidate Repos (2025–2026)

Research into currently-active, novel open-source CLI tools that fit the **CLI-Anything shape** — CLI-driven generators of creative/visual/interactive one-off artifacts that benefit from iterative `refine → generate → evaluate` FSM loops.

## Why these repos fit

The strongest candidates share three traits:

1. **One-command invocation:** `tool input.txt -o output.svg` — no GUI, no server required.
2. **Typed output format with a published schema:** SVG, Lottie JSON, GLSL, WAV, PDF — all have validators independent of LLM judgment.
3. **Structured error output:** D2 diagnostics JSON, GLSL compile stderr, khana's `diagnostics.json`, Mermaid parse errors — these are the non-LLM evaluator signals that the FSM meta-loop guidelines (rule MR-1) require to pair with every `check_semantic` state.

## Top-tier fits (strong CLI + structured eval signals)

### 1. charmbracelet/vhs
- **Repo:** https://github.com/charmbracelet/vhs
- **Stars:** ~19.8k | **Last release:** March 2026 (v0.11.0)
- **Artifact:** GIF, MP4, WebM, or PNG frame sequences of terminal sessions
- **FSM fit:** VHS takes a `.tape` file (DSL of keystrokes, timing, settings) and deterministically renders a terminal recording. An LLM generates/mutates the `.tape` file in `do_work`; `exit_code` checks whether `vhs demo.tape` exits 0 and produces a file of expected size/type; `check_semantic` scores whether the animation demonstrates the intended command flow. `convergence` detects when `.tape` output stops changing between iterations.
- **Notable hook:** Ships its own ASCII/text output mode for integration testing — a built-in non-LLM signal. Tape DSL is terse enough for token-efficient iteration.

### 2. charmbracelet/freeze
- **Repo:** https://github.com/charmbracelet/freeze
- **Stars:** ~4.6k | **Last release:** April 2025 (v0.2.2)
- **Artifact:** PNG, SVG, or WebP screenshots of code or terminal output
- **FSM fit:** `freeze --execute "some-command"` captures ANSI terminal output as a styled image. Loop: `do_work` generates a command/snippet → `exit_code` verifies valid PNG → `check_semantic` judges readability/clarity. SVG output is DOM-diffable; pairs naturally with image-diff convergence evaluator.
- **Notable hook:** `--interactive` mode saves JSON config presets reusable across iterations.

### 3. terrastruct/d2
- **Repo:** https://github.com/terrastruct/d2
- **Stars:** ~24k | **Last release:** August 2025 (v0.7.1), Go
- **Artifact:** SVG, PNG, or PDF architecture/flow diagrams
- **FSM fit:** D2's syntax is a clean, declarative text format LLMs write reliably. `d2 in.d2 out.svg` exits non-zero on parse errors → hard objective signal. SVG output is diffable and validatable against schema expectations ("does this diagram contain node 'auth-service'?"). `check_semantic` judges layout clarity. Multiple layout engines (`elk`, `dagre`, `tala`) let refinement vary visual treatment without touching data model.
- **Notable hook:** `d2 --watch` enables live-reload; syntax errors emit structured JSON diagnostics, parseable by a non-LLM evaluator.

### 4. mermaid-js/mermaid-cli
- **Repo:** https://github.com/mermaid-js/mermaid-cli
- **Stars:** ~4k+ | Actively maintained
- **Artifact:** SVG, PNG, or PDF diagrams from Mermaid text definitions
- **FSM fit:** `mmdc -i diagram.mmd -o diagram.svg` — single command, clean exit code. Mermaid syntax is in virtually every LLM training set. `exit_code` validates parse success; SVG node-count evaluator confirms expected entity count; `check_semantic` judges layout/correctness.
- **Notable hook:** Pairs well with Mermaid-MCP server (22+ diagram types) — FSM can drive generation via MCP tool calls rather than raw file I/O.

### 5. mfontanini/presenterm
- **Repo:** https://github.com/mfontanini/presenterm
- **Stars:** ~8.5k | **Last release:** February 2026 (v0.16.1), Rust
- **Artifact:** Terminal slideshow + export to PDF and HTML
- **FSM fit:** Input is plain markdown; output PDF gives objective signals (slide count, embedded code-block syntax highlighting). HTML can be scraped/diffed. Loop: generate `.md` source → `presenterm --export-pdf` as `exit_code` evaluator → `check_semantic` judges narrative flow. Built-in `--watch` hot-reload complements iterative FSM cycles.
- **Notable hook:** Supports embedded mermaid and D2 graphs — diagram quality is a second-order eval signal.

### 6. cyberchitta/cad-khana
- **Repo:** https://github.com/cyberchitta/cad-khana
- **Stars:** ~8 (very early) | Apache 2.0, active
- **Artifact:** STL, STEP, glTF, and engineering drawing PNGs from Build123d Python scripts
- **FSM fit:** Purpose-built for LLM-driven iterative CAD. `khana build` runs script and exports geometry; `khana check` emits structured `diagnostics.json` reporting interferences, clearances, wall thickness, overhang violations — each a machine-readable non-LLM evaluator. Scripts can include geometric assertions that produce `exit 1` on violation. `check_semantic` judges rendered engineering drawing PNG. `khana diff` compares diagnostics between versions for a `convergence` state.
- **Notable hook:** `diagnostics.json` is a designed-in non-LLM evaluator channel — built with the exact evaluation structure FSM meta-loop guidelines require.

## Creative-media fits

### 7. affromero/kin3o
- **Repo:** https://github.com/affromero/kin3o
- **Stars:** ~14 (early-stage) | **Last release:** April 2026 (v0.3.0)
- **Artifact:** Lottie JSON animations (`.json`, `.lottie`), exportable to MP4/WebM/GIF
- **FSM fit:** First-class CLI (`npm install -g kin3o`, then `kin3o generate "a bouncing ball"`). Lottie JSON has a published schema → `exit_code` from a Lottie validator gives objective structural signal. `check_semantic` judges motion-vs-prompt match. The `--refine` subcommand is literally the same mental model as a loop state. Video export allows frame-count evaluator.
- **Notable hook:** Ships with `validate` subcommand checking Lottie schema compliance — ready-made non-LLM evaluator.

### 8. kingnobro/Chat2SVG
- **Repo:** https://github.com/kingnobro/Chat2SVG
- **Stars:** ~232 | **CVPR 2025** paper
- **Artifact:** SVG vector graphics from text prompts via three-stage pipeline
- **FSM fit:** Pipeline is already FSM-shaped: Stage 1 generates template SVG; Stage 2 enhances detail; Stage 3 optimizes paths. Each is a shell-script invocation. CLIP and ImageReward are already embedded as non-LLM evaluators for template selection. FSM wraps outer loop: `do_work` calls Stage 1-3 → `exit_code` checks SVG well-formedness → `check_semantic` scores prompt fidelity → `convergence` detects when successive SVG diffs fall below threshold.
- **Notable hook:** Paper-backed CLIP scoring is documented, reproducible non-LLM evaluator — exactly what meta-loop guidelines require.

### 9. OpenVGLab/OmniLottie
- **Repo:** https://github.com/OpenVGLab/OmniLottie
- **Stars:** Newly released (CVPR 2026)
- **Artifact:** Lottie JSON animations from multimodal inputs (text, image, video)
- **FSM fit:** Generates Lottie JSON from natural language — same Lottie-schema validation path as kin3o at research-model fidelity. Multimodal input path (image-to-Lottie) opens a reference-image evaluator: generate animation → render frame to PNG → compute image similarity against reference. FSM refines prompt until frame similarity exceeds threshold.
- **Notable hook:** CVPR 2026 paper with released inference code — evaluator pipeline is documented and reproducible.

### 10. multimodal-art-projection/YuE
- **Repo:** https://github.com/multimodal-art-projection/YuE
- **Stars:** ~6.3k | Apache 2.0, active 2025
- **Artifact:** Full songs (vocal + accompaniment) as audio files from lyric prompts
- **FSM fit:** Accepts structured lyric input via `infer.py`, produces audio files headlessly. Objective signals: file duration (within range?), sample rate validation, silence detection (did generation fail silently?), audio loudness normalization — all scriptable via `ffprobe` or `librosa`. `check_semantic` judges genre match and lyrical coherence. `--batch_size` and `--max_new_tokens` give FSM controllable refinement levers.
- **Notable hook:** CLAP embedding comparison to genre-tagged reference tracks gives quantitative non-LLM evaluator for style fidelity.

### 11. gabotechs/MusicGPT
- **Repo:** https://github.com/gabotechs/MusicGPT
- **Stars:** ~1.4k | **Last release:** February 2025 (v0.3.28), Rust
- **Artifact:** WAV from natural language music prompt
- **FSM fit:** `musicgpt "Create a relaxing LoFi song" --secs 30 --model medium`. Simplest possible FSM `do_work`: one command, one output file. `exit_code` checks WAV exists with correct duration. `check_semantic` judges mood/genre. Rust binary (no Python/ML framework) means fast iteration. `--model` parameter escalates to larger model when smaller models fail semantic eval.
- **Notable hook:** Rust binary with no Python dependency means zero environment drift between FSM iterations.

### 12. patriciogonzalezvivo/glslViewer
- **Repo:** https://github.com/patriciogonzalezvivo/glslViewer
- **Stars:** ~3.5k | Last active 2025 (v3.2.3)
- **Artifact:** Rendered GLSL shader output — headless PNG/EXR frames via `--headless`
- **FSM fit:** `glslViewer shader.frag --headless -s 0 -o frame.png` renders fragment shader to PNG in one command. LLM generates `.frag` in `do_work`; `exit_code` checks compile/render success (non-zero on shader compile failure); `check_semantic` judges visual quality. LYGIA integration lets LLM reference battle-tested shader library, reducing hallucination of nonexistent GLSL functions. Convergence state compares successive PNG frames via perceptual hash distance.
- **Notable hook:** GLSL compile errors emit as structured stderr — free, deterministic non-LLM evaluator signal.

### 13. marp-team/marp-cli
- **Repo:** https://github.com/marp-team/marp-cli
- **Stars:** ~4k+ | Actively maintained
- **Artifact:** HTML slide deck or PDF from Markdown with CSS themes
- **FSM fit:** Standalone HTML/PDF output adds browser-renderable artifact with richer eval options: slide count (objective), link validity, accessibility audit via axe-core (a11y signal), screenshot-diff between iterations. `check_semantic` judges visual design and content clarity. Particularly interesting for a "design system compliance" loop: does the generated deck match the brand's Marp theme?
- **Notable hook:** HTML output supports automated accessibility evaluation as non-LLM evaluator — an underexplored FSM signal type.

## Recommended Picks for Catalog Diversity

If covering distinct artifact shapes with minimal overlap:

| Shape | Pick | Rationale |
|---|---|---|
| Terminal demo | **`vhs`** | Closest spiritual sibling to CLI-Anything |
| Diagram | **`d2`** | Cleanest DSL + best structured diagnostics |
| Animation | **`kin3o`** | Ships its own validator |
| 3D/engineering | **`cad-khana`** | Purpose-built for this eval shape |
| Shader/visual | **`glslViewer`** | Compile errors are free deterministic signal |
| Audio | **`MusicGPT`** | Rust binary, no env drift |

## Candidates Considered and Excluded

- **wandb/openui / thesysdev/openui** — Web app with no headless CLI path; rendered component lives in browser only.
- **ComfyUI** — Node graph UI; requires running server process, not single-command CLI.
- **YuE forks (YuEGP, ComfyUI_YuE)** — Community wrappers that re-add GUI surfaces; use canonical upstream instead.
- **CQAsk (OpenOrion/CQAsk)** — Web-UI-only invocation; not a CLI, 7 total commits.
- **llm-shader-toy (johnPertoft)** — Browser-only GLSL playground; last commit May 2024, 6 stars.
- **Chat2SVG Stage 3 "automated comparison" script** — Marked "coming soon" in repo.
- **Vizzy (rbren/vizzy)** — Data viz but no CLI; web app with Go backend not exposed as scriptable command.
- **story-to-video / Toonflow** — Cloud-dependent or heavyweight model downloads; latency prohibitive for tight FSM loops.
- **LIDA (microsoft/lida)** — Python library with no CLI entrypoint; notebook/server use.

## Next Steps

Potential starter FSM YAMLs to author, modeled on the existing CLI-Anything example:

- `vhs-refine` — generate `.tape` → render → judge GIF → refine
- `d2-refine` — generate D2 source → render SVG → schema-check + semantic judge → refine
- `kin3o-refine` — generate Lottie prompt → `kin3o generate` → `kin3o validate` + semantic judge → refine
- `cad-khana-refine` — generate Build123d script → `khana build && khana check` → diagnostics-driven refine
- `glsl-refine` — generate `.frag` → headless render → compile-error + semantic judge → refine
- `musicgpt-refine` — generate prompt → `musicgpt` → `ffprobe` + semantic judge → refine

## Source

Research conducted 2026-05-30 via web search across GitHub trending, CVPR 2025-2026 paper releases, and curated 2025 project lists.
