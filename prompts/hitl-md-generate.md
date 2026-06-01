# HITL-MD Generate: HTML Review Page Design Specification

Write a single self-contained HTML file to `${captured.run_dir.output}/index.html` that:
- Embeds ALL CSS and JavaScript inline (no external dependencies, no CDN links, no <link> tags)
- Renders correctly under a file:// URL without an HTTP server
- Has a clean header showing the document source and total segment count
- Includes a sticky "Copy AI prompt (N flagged)" button at the top and a prominent
  "Copy updated markdown" button at the bottom

Core design rule: the document must read as a normal rendered markdown document. Do NOT
render each segment as its own bordered block, do NOT show segment ID labels in the body,
and do NOT fade unselected segments. Saliency and affordances are applied as inline
highlights and overlays only.

**Document rendering (natural markdown flow):**
- Render heading segments as <h1>...<h6> (matching the # count in markdown_source).
- Render prose segments inside <p> paragraphs. Consecutive prose segments that belonged
  to the same paragraph in the source should be wrapped together in one <p>.
- Render bullet segments inside <ul>/<ol>/<li> in the appropriate list nesting; preserve
  the original bullet markers and indentation.
- Render code segments inside <pre><code> with a monospace font and a distinct code
  background.
- Render blockquote segments inside <blockquote>.
- Render separator segments as <hr> (or as the blank-line break they represent).
- Use a clean system font stack, generous line-height (~1.6), comfortable max-width
  (~720px) centered on the page, light page background (#f9fafb).

**Inline segment markers:**
- Wrap each segment with class="seg" plus data-id="sNNN", data-color, data-saliency,
  and data-type attributes:
  - For prose, wrap with an inline <span class="seg" data-id="s001" ...>...</span>
    inside the paragraph. NEVER wrap a prose span in a <div> — keep it inline so the
    paragraph flow is preserved.
  - For block-level segments (heading, list item, code, blockquote, separator), apply
    class="seg" + data-attributes directly to the block element itself
    (e.g., <h2 class="seg" data-id="s003" ...>, <li class="seg" ...>).
- Every segment must be reachable as a single .seg DOM node — the JS uses
  document.querySelectorAll('.seg') to enumerate segments in order.

**Saliency as inline highlight (NOT block borders):**
- Apply a subtle background tint derived from the segment's data-color at ~12–15% alpha
  directly on the .seg element. For inline prose spans, use background-color with
  rounded corners (border-radius: 3px) and small horizontal padding (padding: 0 2px).
  For block elements, apply the same low-alpha background-color to the block.
- Do NOT add left borders, do NOT add per-segment padding/margin that creates a stacked
  block appearance. The visual delta from an un-highlighted document should be color
  wash only.
- Higher-saliency colors will naturally read as "hotter" — don't crank up alpha to
  compensate. Stay at ~12–15% so prose remains readable.

**Segment IDs in the gutter / tooltip, NOT in the body:**
- Do not render segment IDs inline with the text.
- On hover, show the segment ID via a CSS-only tooltip (e.g., title attribute, or
  a ::after pseudo-element revealed on :hover).
- Optionally, when a segment is selected, render a tiny gray segment-ID label
  (position: absolute) in the left or right page margin opposite the segment.

**Selection (subtle, not disruptive):**
- Tab / Shift+Tab and arrow keys (Up/Down) move selection through segments in document
  order. Mouse click on a segment selects it. Escape clears selection.
- The selected segment gets a thin outline (e.g., 1px solid currentColor at 50% alpha)
  or a slightly darker tint of its own color. Do NOT fade other segments. The entire
  document must remain readable at all times.
- Scroll the selected segment into view smoothly (scrollIntoView with block: 'center').

**Affordances as on-demand popover (NOT a permanent toolbar):**
- The five edit controls live inside a single small popover element (position: absolute
  or fixed) that is hidden by default. When a segment is selected, position the popover
  near the segment (anchored to the segment's bounding rect, above or below it depending
  on viewport space) and reveal it.
- The popover overlays the document — it MUST NOT push surrounding content or reflow
  text. Achieve this with position: absolute/fixed + a high z-index.
- Only one popover is visible at a time. Pressing Escape, clicking outside the popover
  and outside the segment, or selecting a different segment dismisses the popover.
- The popover contains exactly five icon buttons, in this order, each keyboard-focusable:
  - 🗑 Delete — toggles a "deleted" state on the segment (strikethrough + low opacity
    inline) and a small "Restore" link appears next to the deleted span/block.
  - ↑+ Insert before — reveals a small inline textarea immediately before the segment
    (still inside the natural flow position) where the user types new content.
  - +↓ Insert after — reveals a small inline textarea immediately after the segment.
  - ✏ Edit — toggles contenteditable="true" on the segment's text content for in-place
    editing. (For block-level segments, edit the block's text; for prose spans, edit
    the span's text.)
  - 🚩 Flag for AI — toggles a flagged state on the segment (small inline 🚩 glyph
    and/or a colored underline visible at a glance).
- Provide accessible labels (aria-label / title) on every button.

**Flagged-state inline marker:**
- Flagged segments must be visible at a glance without entering the popover. Show a
  small 🚩 glyph next to the segment (inline, low-impact) and/or apply a colored
  underline (text-decoration: underline; text-decoration-color: <flag color>).

**Deleted / edited / inserted segments stay inline:**
- Deleted segments: render with text-decoration: line-through and opacity ~0.35 on the
  original .seg node. Place a small "↺ Restore" link immediately adjacent (still
  inline). Do NOT remove the DOM node — the markdown-reconstruction logic skips them
  based on a JS-side `deleted` flag.
- Edited segments: contenteditable="true" toggled on the .seg node. No layout shift.
- Inserted segments: when the user submits the insert textarea, render the new content
  as a new inline node positioned immediately before/after the source segment. Choose
  the element type to match context (a new <p> for prose, a new <li> for list-item
  insertion, etc.).

**Copy AI prompt (sticky top button):**
- Label: "Copy AI prompt (N flagged)" — N updates live as flags toggle. Initially
  N=0 and the button is greyed out / disabled.
- When clicked, copy this snippet to the clipboard. The clipboard payload MUST
  include the segment IDs in brackets and the framing instruction — do not concatenate
  raw segment text only. The format below is mandatory:
  ```
  Please revise the following sections of the document. Each section is marked with its
  segment ID for reference:

  [s003] <segment text>

  [s007] <segment text>

  [s012] <segment text>

  Focus your edits on improving clarity, accuracy, and completeness for these specific spans.
  ```

**Copy updated markdown (prominent bottom button):**
- When clicked, reconstruct the markdown document from the live segment list:
  - Skip segments marked deleted.
  - For inserted segments: use the text entered in the insert textarea (rendered with
    appropriate markdown for context — `\n\n` separator for prose, `- ` prefix for
    list-item insertion, etc.).
  - For edited segments: use the current text content of the (contenteditable) .seg
    node.
  - For unmodified segments: use the original markdown_source from segments.json.
  - Concatenate in document order and copy to clipboard.

**Design constraints:**
- System font stack only (no external fonts, no @import).
- All CSS inline in <style>, all JS inline in <script>.
- No external src= or href= references to anything off-disk.
- Mobile-responsive, desktop-first.

---

**Sensemaking layer (ENH-1770):** the six features below operationalize
Pirolli & Card's foraging-loop, Klein's Data/Frame Theory, Russell et al.'s
Cost Structure of Sensemaking, the HCEye dynamic-appearance finding, the
Keyhole Effect, and the LLM Fallacy / fluency-as-credibility research
(Steyvers et al. 2024, Kim et al. 2026). Each feature is an independently
toggleable module within the same single-file HTML. All visible styles must
source colors, spacing, motion, typography, and radii from the design token
CSS custom properties exposed via `${context.design_tokens_context}`
(e.g., `var(--color-action-primary)`, `var(--space-3)`,
`var(--motion-duration-medium)`, `var(--radius-sm)`). If a needed semantic
token is missing from the active profile, declare a single fallback CSS
custom property at `:root` (e.g., `--hitl-stage-duration: 240ms`) and
reference it via `var()` — never embed raw hex / px / rem literals inside
feature CSS.

**Feature 1 — Staged dynamic highlighting (HCEye / Das et al. 2024):**
- Do NOT paint every `.seg` background on load. Reveal highlights in waves.
- Tier 1 (immediate): the top 3–5 segments by `data-channel-importance`
  receive their saliency tint on `DOMContentLoaded`.
- Tier 2+ (deferred): every other highlighted segment starts with its
  background-color transparent and fades in when it intersects the viewport.
- Implement with `IntersectionObserver` on `.seg` elements. When a tier-2+
  segment intersects, add a `seg--revealed` class and the CSS transition
  animates `background-color` from transparent to the resolved tint.
- Transition uses `var(--motion-duration-medium, --hitl-stage-duration)` and
  `var(--motion-easing-standard, --hitl-stage-easing)` — never a hardcoded
  `200ms ease`.

**Feature 2 — Adaptive highlight-density slider (Yang et al. 2025):**
- Render a fixed toolbar at the top of the page (alongside or below the
  existing "Copy AI prompt" control) containing an `<input type="range">`
  labelled "Density".
- Range maps to a saliency threshold (e.g., 0.0 → "All", 0.5 → "Top 25%",
  0.8 → "Top 10%"). Default the slider to a sparse position (Top 10–25%).
- On `input`, recompute which `.seg` elements receive the highlight tint:
  those with `data-channel-importance >= threshold` get the tint class;
  others have their tint suppressed (text remains fully readable).
- **IMPORTANT — never hide segments:** The density filter MUST NOT use `display:none`,
  `visibility:hidden`, or any other mechanism that removes segments from the document
  flow. Every segment remains visible in the document at all times. Only the
  `background-color` tint is toggled — remove or add a CSS class that sets
  `background-color: transparent`. An implementation that hides any `.seg` element
  from view is a correctness bug, not a style issue.
- Slider track, thumb, focus ring, toolbar surface, label typography, and
  spacing all use semantic tokens — `var(--color-surface-primary)`,
  `var(--color-border-subtle)`, `var(--color-action-primary)`,
  `var(--space-2)`, `var(--space-3)`, `var(--font-size-sm)`,
  `var(--font-family-ui)`. No raw colors, no raw px.

**Feature 3 — Multi-channel saliency (Klein Data/Frame Theory):**
- Each `.seg` element must carry `data-channel-importance`,
  `data-channel-anomaly`, `data-channel-confidence`, and `data-claim-type`
  attributes populated from the `channels` object in segments.json.
- The toolbar exposes four channel toggle controls (importance, anomaly,
  claim_type, confidence). The active channel determines which color
  mapping is applied to all `.seg` backgrounds.
- Each channel maps to a distinct semantic color custom property —
  `var(--color-channel-importance)`, `var(--color-channel-anomaly)`,
  `var(--color-channel-confidence)`, plus a claim-type palette
  (e.g., factual → `var(--color-claim-factual)`, assumption →
  `var(--color-claim-assumption)`, etc.). If the token profile lacks these,
  derive them at `:root` from neutral and action tokens; do NOT embed hex
  literals inline.
- Toggling a channel re-applies the tint via a CSS class swap — pure
  DOM manipulation, no segment re-rendering.

**Feature 4 — Schema-switching toolbar (Russell et al. 1993):**
- The toolbar exposes "View" toggle buttons that re-group the displayed
  content by different schemas: "By document order" (default), "By saliency
  tier", "By claim type", "By anomaly score".
- Schema-switching re-orders `.seg` elements in the DOM (move them between
  wrapper sections) — it does NOT re-fetch or re-generate. Group dividers
  between sections use `var(--color-border-subtle)` and `var(--space-4)`
  separation; group headings use `var(--font-size-sm)` /
  `var(--color-text-secondary)`.
- Active toggle: `var(--color-action-primary)` against
  `var(--color-surface-raised)`. Inactive: `var(--color-text-secondary)`.
- Returning to "By document order" must restore the original DOM order
  bit-for-bit so the "Copy updated markdown" reconstruction stays lossless.

**Feature 5 — Minimap + spatial State Rail (Reddy, Keyhole Effect 2025):**
- Render a fixed-position `<canvas>` on the right edge of the page (width
  from spacing scale, e.g., `var(--space-6)`) showing the full document as
  proportional colored blocks — one block per segment, height proportional
  to its character count.
- Block fill colors mirror the active channel's palette (read at draw-time
  via `getComputedStyle(document.documentElement).getPropertyValue(...)`
  so theme switches take effect on next redraw without reload).
- A viewport-position indicator overlays the minimap, updated on `scroll`
  via `IntersectionObserver` or `requestAnimationFrame`. Indicator color is
  `var(--color-action-primary)` at reduced alpha (via `color-mix()` or a
  pre-resolved `--color-viewport-overlay` token).
- Visit-heatmap: track which segments have entered the viewport in
  `localStorage` (key `hitl-md:visits:${documentHash}`). Re-draw the
  minimap with a neutral-scale intensity ramp (`var(--color-neutral-100)` →
  `var(--color-neutral-400)`) reflecting visit counts.
- Click on the minimap navigates the main viewport (smooth `scrollIntoView`
  of the corresponding `.seg`).

**Feature 6 — Calibrated friction for trust calibration (Kim et al. 2026,
Steyvers et al. 2024):**
- Confidence badges are rendered as small DOM nodes positioned *before*
  each segment's content (DOM order: badge first, then segment text). The
  badge displays the confidence tier and maps to semantic status tokens:
  high (≥0.75) → `var(--color-status-success)`,
  mid (0.4–0.75) → `var(--color-status-warning)`,
  low (<0.4) → `var(--color-status-danger)`.
- Click-to-reveal gate: segments where `data-saliency >= 0.7` AND
  `data-channel-confidence < 0.5` start with their body text hidden
  behind a "Review this claim" button styled with
  `var(--color-action-primary)` (hover: `var(--color-action-primary-hover)`).
  The confidence badge remains visible alongside the gate button. Clicking
  the button reveals the body.
- Length-normalized credibility marker: when `data-length-normalized="true"`,
  render a subtle ruler icon next to the confidence badge using
  `var(--color-text-muted)`. The icon signals "this segment is longer than
  median — adjust your fluency-driven credibility expectation downward".
- A "Trust calibration" toggle in the toolbar gates the friction-heavy
  interventions: the toggle defaults to *passive* mode (badge-before-content
  and length markers only — no click-to-reveal gate). Switching to *active*
  mode enables the click-to-reveal gate for high-saliency low-confidence
  segments.
- Badge padding, gated-segment outline, and the ruler icon all use
  `var(--space-1)` / `var(--space-2)`, `var(--radius-sm)`,
  `var(--border-width-strong)`. This is the highest-stakes wiring —
  friction interventions that look ad-hoc undermine the calibration signal.
- **Init sequence (required):** The JavaScript `init()` function called on
  `DOMContentLoaded` MUST invoke these functions in order: `render()`, `setupStaged()`,
  `applyDensityFilter()`, `applyTrustCal()`, `updateSelectionUI()`, `updateFlagUI()`.
  Omitting `applyTrustCal()` means trust calibration is never applied on page load.

**Cross-feature requirements:**
- All six features live in the same single self-contained HTML; each is a
  separate JS/CSS module. A bug in the minimap must not break highlighting,
  a broken density slider must not affect schema-switching.
- The original behavior (static single-channel highlighting on
  document_readability / inline_highlighting) remains intact — the new
  features layer on top via toolbar toggles. The default initial render
  must still satisfy the original 6 rubric criteria.
- All toolbar controls are keyboard-focusable with visible focus rings
  derived from `var(--color-focus-ring)` (fallback: outline using
  `var(--color-action-primary)` at higher contrast).

All interactive behavior must work under file:// with no server.
