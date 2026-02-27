# ENH-515: Add text_utils module to API Reference

## Overview
Add documentation for `little_loops.text_utils` to `docs/reference/API.md`.

## Changes

### 1. Module Overview Table (`docs/reference/API.md:41`)
Insert `text_utils` row after `session_log`, before `cli` (utility grouping).

### 2. Module Section (`docs/reference/API.md` — append after `link_checker`)
Add `## little_loops.text_utils` section following Pattern 3 (functions-only module):
- Module description
- Public Constants table (SOURCE_EXTENSIONS)
- Public Functions table (extract_file_paths)
- Constant documentation section
- Function documentation section with signature, parameters, returns, example

## Success Criteria
- [ ] `text_utils` appears in Module Overview table
- [ ] Module section documents `SOURCE_EXTENSIONS` constant
- [ ] Module section documents `extract_file_paths` function
- [ ] Format matches existing patterns (frontmatter, doc_counts)
