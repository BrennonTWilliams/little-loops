---
  The core problem: the 3 agents discover wiring dynamically via symbol-tracing, but certain coupling categories are invisible to that approach —
  files that don't import anything but are semantically coupled (changelogs, CLAUDE.md listings, API reference docs, CLI registrations in plugin
  manifests).

  Here are the four most effective levers, roughly in order of impact:

  ---
  1. Configurable Wire Targets (your idea) — highest impact, right fit

  Add a wire_targets section (probably under commands) to config-schema.json:

  "wire_targets": {
    "always_check": ["plugin.json", "CLAUDE.md", "docs/reference/API.md"],
    "by_issue_type": {
      "FEAT": ["commands/*.md", "skills/*/SKILL.md", "config-schema.json", "CONTRIBUTING.md"],
      "ENH":  ["docs/**/*.md", "config-schema.json"],
      "BUG":  []
    },
    "coupling_rules": [
      { "if_changed": "scripts/little_loops/**", "then_check": ["docs/reference/API.md"] },
      { "if_changed": "config-schema.json",       "then_check": ["docs/reference/API.md", "CLAUDE.md"] }
    ]
  }

  Wire-issue loads these in Phase 3 and injects them into Agent 2's prompt as an explicit must-audit list, not just search hints. Anything configured
  but not already in the issue gets flagged as missing without needing an agent to discover it.

  Trade-off: the user has to maintain the config, but these targets are stable (plugin manifest, API docs, CLAUDE.md don't move), and the one-time
  setup pays off on every issue.

  ---
  2. Reuse the existing documents config — zero new config cost

  config-schema.json already has a documents.categories section with declared key files. Wire-issue could read that in Phase 3 and treat every files
  entry as a potential wiring target. If the issue's planned symbols appear in those files, add them to the "docs to update" list automatically.

  Trade-off: the documents config is meant for alignment validation, not wiring — it's a good fit for doc coupling but won't capture manifest/CLI
  registration coupling. Use this alongside option 1, not instead of it.

  ---
  3. Phase 3 symbol extraction is the weak link — improve it first

  The current agent prompts are only as good as the key_symbols list extracted in Phase 3. If a symbol is spelled inconsistently in the issue (e.g.,
  handle_request vs. handle-request), agents miss all its callers. A quick improvement: after extracting symbols, grep for them immediately in Phase 3
   rather than delegating entirely to Agent 1, so you get exact hit counts before spawning agents. This makes the diff in Phase 5 much more reliable
  even without new config.

  Trade-off: slightly more work in Phase 3, but it catches the "agent hallucinated zero callers" failure mode that currently produces false "no gaps
  found" results.

  ---
  4. A fourth "Registry Auditor" agent scoped to configured targets

  Instead of stuffing configured targets into Agent 2's already-broad prompt, spawn a fourth agent exclusively for checking configured wire targets.
  It gets the target list from config, the planned change symbols from Phase 3, and just answers: "which of these N files would be affected and how?"
  This keeps the general side-effect tracer focused on structural coupling and gives the config-driven targets their own clean pass.

  Trade-off: more agent cost per run, and only worthwhile if options 1+3 are already in place.

  ---
  My recommendation: options 1 + 3 together. The configurable wire targets solve the "known unknowns" (files you always know you need to update), and
  fixing symbol extraction solves the "unknown unknowns" (callers the agents were missing because the symbol list was thin). Option 2 is a near-free
  win that costs almost nothing to add alongside 1.

  Want me to sketch out the schema addition for option 1 and the Phase 3 grep-first change for option 3?

✻ Baked for 1m 2s

❯ Lets explore more ideas first - what would this look like in the ideal world without any time or resource constraints?

⏺ Good — let's think bigger. Here's what ideal looks like across several orthogonal dimensions:

  ---
  Dimension 1: Persistent Coupling Knowledge

  The current skill is stateless — every run starts from scratch. In the ideal world, it builds and maintains a project coupling graph stored in
  .ll/history.db.

  Git co-change mining — run git log --name-only across history to find files that statistically co-change. If config-schema.json and
  docs/reference/API.md change together in 90% of commits that touch either, they're implicitly hard-coupled. This is a real technique from software
  evolution research and requires no human annotation.

  Gap learning — every time wire-issue finds a gap that wasn't in an issue, record the pattern: "when issue_type=FEAT touched
  scripts/little_loops/loops/, it missed docs/reference/API.md 4/4 times." The next run for a similar issue pre-populates the must-check list from
  learned history rather than relying on agent discovery.

  Wire-issue as convergence loop — instead of one pass with 3 agents, run as an FSM that iterates: discover new files → extract their symbols → find
  callers of those → discover more files → stop when no new files are added. This handles transitive coupling (callers of callers, importers of
  importers) that the current single-pass design misses entirely.

  ---
  Dimension 2: Richer Coupling Categories

  The current 4 categories (callers, docs, tests, config) miss entire classes of coupling that are project-specific. An ideal system knows about:

  - Serialization coupling — if you change a dataclass or schema, what serializes/deserializes it? What migration is needed?
  - Event coupling — if you add a new LLEvent subtype, what transport handlers, subscribers, and SQLite schema need updating?
  - Permission coupling — if you add a new CLI command, are there .claude/settings.json allow-list entries needed?
  - Telemetry/analytics coupling — if you add a feature, are there event emission sites to add?
  - Changelog coupling — does CHANGELOG.md always need an entry for this issue type?
  - Learning test coupling — the existing ll-learning-tests registry tracks asserted API behaviors; wire-issue should consult it to flag tests that
  assert on the thing being changed
  - Extension coupling — if a public event or hook signature changes, what registered extensions break?

  These categories are unknowable to a generic agent but perfectly expressible as configurable coupling rules.

  ---
  Dimension 3: Change Archetype Templates

  Rather than configuring targets at the issue-type level (FEAT/BUG/ENH), the ideal system recognizes change archetypes — patterns of what kind of
  change is being made — and loads a pre-built checklist for each:

  "Add new CLI command"      → check: commands/, skills/, plugin.json, CLAUDE.md, CONTRIBUTING.md, docs/reference/API.md
  "Add new config key"       → check: config-schema.json, docs/reference/API.md, any code that calls config.get()
  "Add new FSM state type"   → check: loop runner, validator, diagram renderer, docs/loops/
  "Rename a public function" → check: all callers (hard), all docs that mention it, all tests that assert on it
  "Add new LLEvent type"     → check: EventBus, all transports, SQLiteTransport schema, ll-generate-schemas
  "Change CLI flag name"     → check: commands that call it, docs that document it, tests that pass it, CLAUDE.md

  The archetype is inferred from the issue title + implementation plan using a lightweight prompt, then the matching template is injected directly
  into Phase 3 as a pre-populated must-check list — no discovery needed.

  ---
  Dimension 4: Declarative Coupling Annotations

  A coupling registry file (.ll/coupling-rules.yaml) that developers maintain explicitly — like CODEOWNERS but for semantic coupling. Pairs of
  coupling rules:

  rules:
    - if_changed: "config-schema.json"
      then_check: ["docs/reference/API.md", "CLAUDE.md", "templates/*.json"]
      tier: hard   # must change together

    - if_changed: "scripts/little_loops/loops/**"
      then_check: ["docs/reference/API.md"]
      tier: soft   # should update

    - if_changed: "skills/*/SKILL.md"
      then_check: ["CLAUDE.md", "commands/help.md"]
      tier: hard

    - if_changed: "scripts/little_loops/events/**"
      then_check: ["docs/reference/schemas/", "ll-generate-schemas"]
      tier: hard
  In-code annotations as a complement — a comment like # ll:wire docs/reference/API.md near a public function signals to wire-issue that any change
  here requires updating that doc. These annotations could be auto-generated by the skill when it first discovers a persistent gap.

  ---
  Dimension 5: LSP-Powered Symbol Resolution

  The current approach uses grep, which misses: renamed symbols, dynamic dispatch, aliases, re-exports. The ideal version uses the Language Server
  Protocol (via pyright --outputjson or jedi) to get exact references to every symbol being changed. This turns "find callers" from a text-matching
  problem into a precise semantic graph traversal — every call site, every type annotation, every re-export, zero false negatives.

  ---
  Dimension 6: Coupling Tiers with Different Handling

  Not all coupling is equally urgent. The ideal system classifies findings:

  ┌──────┬───────────────────────────────────────────┬─────────────────────────────────────────────────┐
  │ Tier │                  Meaning                  │               Wire-issue behavior               │
  ├──────┼───────────────────────────────────────────┼─────────────────────────────────────────────────┤
  │ hard │ Must change together or the system breaks │ Added to Implementation Steps as blocking       │
  ├──────┼───────────────────────────────────────────┼─────────────────────────────────────────────────┤
  │ soft │ Should update for consistency             │ Added to Integration Map with a warning         │
  ├──────┼───────────────────────────────────────────┼─────────────────────────────────────────────────┤
  │ fyi  │ Interesting but not blocking              │ Mentioned in the report, not added to the issue │
  └──────┴───────────────────────────────────────────┴─────────────────────────────────────────────────┘

  Configured wire targets declare their tier; agent discoveries default to soft unless corroborated by co-change evidence.

  ---
  The Synthesis

  In the ideal world, wire-issue is a three-layer system:

  1. Static layer — coupling rules + change archetype templates + co-change mining resolve 60–70% of wiring without any LLM calls
  2. Discovery layer — the current 3-agent pass (iterative, convergent) handles what static analysis can't express
  3. Learning layer — every run feeds back into the coupling graph and gap taxonomy, so the static layer gets smarter over time

  The LLM's job becomes validating and categorizing what the static layer surfaces, not discovering from scratch.

  ---
  What direction feels most worth investing in first? The coupling registry + change archetype templates would give the most immediate payoff for the
  least complexity. The git co-change mining is the most "wow" feature and requires no human maintenance. The LSP integration is the most technically
  elegant but the hardest to ship.