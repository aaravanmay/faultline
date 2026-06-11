---
name: Bug report
about: faultline did the wrong thing (a false positive, a false negative, or a crash)
title: ''
labels: bug
---

**What happened**
A clear description. If it's a detector verdict you disagree with, say whether you expected PASS / FAIL / CRASH.

**Minimal repro**
A small agent + the faultline call. Ideally runnable with no API key.

```python
import faultline as fl
# ...
```

**Verdict you got vs. expected**
- Got:
- Expected:

**Environment**
- faultline version (`faultline --version`):
- Python version:
- Framework + version, if using an adapter (langgraph / langchain / llamaindex / pydantic-ai / crewai):
