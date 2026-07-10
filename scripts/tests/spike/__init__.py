"""Spike packages: standalone concurrency/plumbing cores proved out in
isolation before their protocol is wired into a loop YAML.

Each subpackage is a self-contained library plus a pytest class that retires a
named set of acceptance criteria. Modules here are NOT collected as tests
(they do not match ``test_*.py``); their AC suites live in the sibling
``test_*.py`` files under ``scripts/tests/``.
"""
