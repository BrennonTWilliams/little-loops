---
target: Claude Code skill and agent frontmatter model_hint tolerance
date: '2026-09-28'
status: proven
assertions:
- claim: Claude Code's official SKILL.md frontmatter schema has no model_hint field; only a literal 'model' field is recognized
  result: pass
- claim: Claude Code's official subagent frontmatter schema has no model_hint field; 'model' accepts family aliases, full model IDs, or 'inherit' only
  result: pass
- claim: Claude Code silently ignores unrecognized frontmatter keys (no error, no warning) rather than rejecting the file
  result: pass
- claim: Claude Code has no native capability-hint mechanism (e.g. coding/reasoning/burst); only exact model specification is honored, and 'effort' tunes reasoning depth, not model selection
  result: pass
- claim: ll-verify-skills (the only skill-frontmatter gate in this repo) validates line count only, not frontmatter field names
  result: pass
- claim: CodexAdapter.emit_agent currently copies the frontmatter 'model' field verbatim into generated .codex/agents/*.toml, with no model_hint resolution logic yet
  result: pass
raw_output_path: .ll/learning-tests/raw/claude-code-skill-and-agent-frontmatter-model_hint-tolerance.txt
---
