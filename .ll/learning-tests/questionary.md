---
target: questionary
date: '2026-06-20'
status: proven
assertions:
- claim: Choice(title='Foo').value equals 'Foo' when value is not specified (defaults to title)
  result: pass
- claim: Choice(title='Foo', value='bar').value equals 'bar' (explicit value wins over title)
  result: pass
- claim: Choice(title='X', checked=True).checked equals True
  result: pass
- claim: Choice(title='X', disabled='Coming soon').disabled equals 'Coming soon'
  result: pass
- claim: text().ask() raises EOFError (not returns default) when stdin is exhausted/non-interactive
  result: pass
- claim: confirm().ask() raises EOFError (not returns default=True) when stdin is exhausted/non-interactive
  result: pass
raw_output_path: .ll/learning-tests/raw/questionary.txt
---
