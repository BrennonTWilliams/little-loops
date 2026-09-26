---
target: gemini
date: '2026-09-25'
status: proven
assertions:
- claim: gemini --version prints a bare semver string (X.Y.Z, no v-prefix)
  result: pass
- claim: --output-format accepts exactly the choices text, json, stream-json
  result: pass
- claim: --approval-mode accepts exactly the choices default, auto_edit, yolo, plan
  result: pass
- claim: gemini skills subcommand offers list, enable, disable, install, link, uninstall
  result: pass
- claim: with no auth configured, headless -p exits with code 41 and writes the JSON error envelope to stderr (stdout empty)
  result: pass
- claim: an invalid --output-format value exits with code 1 and prints usage to stderr
  result: pass
- claim: gemini --list-sessions works without auth (exits 0)
  result: fail
raw_output_path: .ll/learning-tests/raw/gemini.txt
---
