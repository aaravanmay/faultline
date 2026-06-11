# Security policy

## Reporting a vulnerability
faultline is a testing tool that runs in your own CI — no server, no network calls, no secrets. If you
find a security issue (for example, a way the tool could be tricked into running untrusted code), please
report it **privately to aaravgoenka25@gmail.com** rather than opening a public issue. I'll respond as
quickly as I can.

## Supported versions
faultline is pre-1.0 — the latest release on PyPI is the supported version. Please track the latest.

## Scope / threat model
faultline loads your agent and invariants from Python files you point it at (`faultline run suite.py`,
`faultline scan file.py:agent`), so it **executes that code by design** — only run it on suite/agent files
you trust, exactly like any test runner (pytest, tox). The declarative `faultline.json` config uses a
**closed allowlist** of built-in faults (no arbitrary code execution from the config), but it still imports
the agent/invariant modules you reference. faultline makes no network calls and reads no credentials on its
own.
