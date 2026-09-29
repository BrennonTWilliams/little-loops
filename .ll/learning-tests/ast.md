---
target: ast
date: '2026-09-29'
status: proven
assertions:
- claim: ast.parse returns an ast.Module whose body is a list of statements
  result: pass
- claim: ast.parse raises SyntaxError with a lineno on invalid source
  result: pass
- claim: FunctionDef nodes carry name and lineno, and end_lineno is populated
  result: pass
- claim: ast.walk yields nodes breadth-first, including nested ones
  result: pass
- claim: ast.literal_eval evaluates literals but raises ValueError on a call expression
  result: pass
- claim: ast.unparse round-trips a parsed expression to source text
  result: pass
- claim: ast.get_docstring returns the docstring of a function node
  result: pass
raw_output_path: .ll/learning-tests/raw/ast.txt
---
