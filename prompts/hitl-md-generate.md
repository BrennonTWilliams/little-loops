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

**Confidence cue (lightweight trust calibration):**

AI-generated prose is fluent even when it is wrong, so the one calibration signal worth
surfacing is *confidence* — and only where it changes the reader's behavior. This is a
single, always-on cue with no toolbar, no toggle, no click-gate, and no view modes.

- Each `.seg` carries a `data-confidence` attribute (0.0–1.0) populated from segments.json.
- For segments where `data-confidence < 0.5`, apply two subtle markers:
  - A dotted underline in a muted warning color
    (`text-decoration: underline dotted; text-decoration-color: #d97706`). For block-level
    segments, use a `border-bottom: 1px dotted #d97706` instead so the cue reads the same.
  - A small inline badge rendered **before** the segment's text in DOM order (so the
    calibration signal is read before fluency biases judgment), e.g.
    `<span class="conf-badge" aria-label="low confidence">⚠ low confidence</span>`.
    Style it small and unobtrusive: muted amber text, `font-size: 0.75em`, a touch of
    right margin. It must not break the document's reading flow.
- Segments with `data-confidence >= 0.5` get no badge and no underline — absence of the
  cue is itself the signal that the model was confident.
- This is purely presentational. It must not alter selection, the popover, flagging, or
  markdown reconstruction in any way, and it must work under file:// with no server.
