---
target: questionary
date: '2026-08-08'
status: proven
assertions:
- claim: select().ask() raises EOFError (not returns default) when stdin is exhausted/non-interactive
  result: pass
- claim: checkbox().ask() raises EOFError (not returns default) when stdin is exhausted/non-interactive
  result: pass
- claim: questionary.prompt([...]) returns partial answers (not raising) when a question's
    .ask() would EOF
  result: fail
- claim: checkbox() choices built from Choice(title=..., value=...) yield .value (not
    .title) in the answer dict
  result: untested
- claim: Separator() is not a valid instance of Choice (isinstance(Separator(), Choice)
    is False)
  result: fail
raw_output_path: .ll/learning-tests/raw/questionary.txt
proven_package: questionary
proven_version: 2.1.1
---
