Synthesis: 8 Sensemaking Patterns for hitl-md

  **Implementation status (ENH-1770, 2026-05-29):** Patterns 1, 2, 5, 6, 7, and an
  additional calibrated-friction pattern (confidence badges before content,
  click-to-reveal gating, length-normalized credibility markers per Steyvers et al.
  2024 / Kim et al. 2026) are now wired into the `hitl-md` loop YAML's `segment`,
  `generate`, and `score` states. Patterns 3 (bookmark sidebar) and 4 (section-by-
  section mode) and 8 (gist-on-hover) remain proposed. See `scripts/little_loops/
  loops/hitl-md.yaml` and the `TestHitlMdLoop` structural tests for the wiring.

  Tier 1: Add now (CSS/JS changes only, no generation pipeline changes)

  1. Staged dynamic highlighting — HCEye research (Das et al., 2024) shows static highlighting loses effectiveness under cognitive load. Instead of painting all
  segments on load, reveal highlights in waves: top 3-5 most salient segments highlighted immediately, next tier fades in as the user scrolls past the first group.
  Dynamic appearance captures attention better, and it solves the "everything is important" overwhelm. Change: JS timing + CSS transitions in the existing generate
  state.

  2. Adaptive density slider — A control (e.g., "Top 10% / 25% / All") that adjusts what fraction of segments get the background tint. This prevents the flat attention
   landscape where everything highlighted = nothing highlighted. Yang et al. (2025) found this "overgeneration effect" is a real problem in AI-assisted workflows.
  Change: add a slider UI + JS filter in generate.

  3. Bookmark-to-sidebar "shoebox" — Pirolli & Card's foraging loop has a critical "evidence file" stage your current tool skips. The user clicks a bookmark icon on
  any segment; it gets copied to a persistent sidebar. Later they can review just their bookmarked excerpts. This externalizes the "keep this" decision so they don't
  hold candidates in working memory. Change: add a sidebar panel + localStorage persistence.

  4. Section-by-section review mode — Your GP-TSM segments already enable this one. A toggle switches from full-document view to "one segment at a time" card view with
   forward/back navigation and a progress bar. Eliminates the scroll-induced context loss that Reddy's "Keyhole Effect" paper identifies as the primary cognitive
  failure mode of linear review. Change: overlay/different CSS layout in generate — no new data needed.

  Tier 2: Upgrade the segment model (need generation pipeline changes)

  5. Multi-channel highlighting — Your current design has one saliency dimension (importance). The sensemaking literature says that anchors users in a single "frame"
  and actually discourages reframing (Klein's Data/Frame Theory). Add orthogonal channels:
  - Anomaly channel — segments that contradict earlier content or the user's likely expectations
  - Claim-type channel — factual claims vs. assumptions vs. reasoning vs. action items
  - Confidence channel — how certain the generating AI was about each segment

  Each channel gets its own color coding and can be toggled independently. Requires: richer segment schema + LLM work during segmentation.

  6. Schema-switching view toggles — Russell's cost-structure analysis finds that "representational shifts" (changing your mental model) are the most expensive
  cognitive operation in sensemaking. Make them cheap: a toolbar that re-renders the document grouped by different schemas ("By heading," "By saliency," "By claim
  type," "By anomaly"). Each toggle is a one-click reframe instead of a mental reconstruction. Requires: the multi-channel data from #5, plus a JS re-rendering
  function.

  Tier 3: Stretch goals

  7. Minimap + spatial State Rail — A narrow right-side bar showing the full document as proportional colored blocks (section lengths, with color encoding saliency or
  channel). Current viewport position is highlighted; click to jump. Shows a heatmap of where you've spent time. Restores the spatial memory that linear scrolling
  destroys (Reddy's "Keyhole Effect"). Medium effort: IntersectionObserver + Canvas rendering.

  8. Gist-on-hover and anomaly popovers — Pre-computed one-sentence summaries per segment (embedded as data-gist) that appear on hover, not click. Also: an "anomaly
  indicator" in the gutter when a segment contradicts earlier content. Clicking it opens a popover: "This contradicts paragraph 4 which states X." Requires: LLM
  pre-processing during document generation.

  ---
  The unifying win

  The theme across all three reports: embed intelligence at generation time, not runtime. Every summary, confidence score, anomaly flag, reading-time estimate, and
  diff marker can be authored when the AI generates the document and stored as a data-* attribute. The HTML tool stays self-contained (file:// compatible) and the
  reviewer gets a sensemaking environment that doesn't degrade under cognitive load.