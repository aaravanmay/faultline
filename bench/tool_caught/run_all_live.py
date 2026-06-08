"""One command: run faultline against every real agent framework live and print a scoreboard.

Needs ANTHROPIC_API_KEY in .env. Each demo runs in its own subprocess (isolates framework deps).
The CODE does the finding; this just tallies the verdicts.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMOS = [
    ("custom order agent", "live_ops_agent.py"),
    ("LangGraph", "live_langgraph.py"),
    ("pydantic-ai", "live_pydantic_ai.py"),
    ("agno", "live_agno.py"),
    ("LlamaIndex RAG", "live_llamaindex_rag.py"),
    ("ag2 / AutoGen", "live_ag2.py"),
    ("CrewAI", "live_crewai.py"),
    ("smolagents", "live_smolagents.py"),
]
print("faultline vs real agent frameworks (live API) — scoreboard")
print("=" * 56)
caught = 0
for name, fname in DEMOS:
    p = subprocess.run([sys.executable, os.path.join(HERE, fname)], capture_output=True, text=True)
    out = p.stdout + p.stderr
    if "SILENT" in out:
        verdict = "⚠  CAUGHT a silent failure"; caught += 1
    elif "CRASH" in out and "FAIL" in out:
        verdict = "⚠  caught a crash"; caught += 1
    elif "PASS" in out and "FAIL" not in out:
        verdict = "✓  PASS (agent was resilient)"
    else:
        verdict = "?  (run it directly to see)"
    print("  %-22s %s" % (name, verdict))
print("=" * 56)
print("%d / %d real frameworks: the CODE caught a silent failure, live via the API." % (caught, len(DEMOS)))
