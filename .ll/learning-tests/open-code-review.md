---
target: open-code-review
date: '2026-09-15'
status: proven
assertions:
- claim: '.opencodereview/rule.json in the repository root is resolved by `ocr
    rules check` as the priority-2 "Project" layer (Source: Project (.opencodereview/rule.json))'
  result: pass
- claim: when multiple rules[] entries match the same path, the first one in declaration
    order wins even if a later entry has a more specific glob
  result: pass
- claim: when no project rule.json entry matches a path, ~/.opencodereview/rule.json
    (the global layer) is used if it has a matching entry
  result: pass
- claim: when neither project nor global rule.json matches a path, resolution falls
    back to the embedded system rule set (e.g. .py files resolve via **/*.{py,pyi,ipynb}
    to the python.md system rule body)
  result: pass
- claim: the --rule <file> CLI flag (priority 1) outranks the project layer, even
    when the project rule.json also matches the same path
  result: pass
- claim: a project-level "exclude" glob does NOT affect `ocr rules check`'s rule-resolution
    lookup -- an excluded path still resolves a matching rule
  result: pass
- claim: the same "exclude" glob IS enforced by `ocr review --preview`'s file-selection
    gate, where the excluded file is labeled user_exclude under "Excluded from review"
  result: pass
raw_output_path: .ll/learning-tests/raw/open-code-review.txt
---
