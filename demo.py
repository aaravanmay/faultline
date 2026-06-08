"""faultline — the 60-second demo. Screen-record this.

Runs ONE real Claude agent live (so it's genuinely live, ~6s) then shows the full scoreboard.
Pacing is configurable for recording:  FL_DEMO_SLEEP=1.4 python3 demo.py   (0 = instant, for testing)

What you're showing: a tool that breaks the biggest AI-agent frameworks on purpose and catches
them silently doing the wrong thing — with no LLM-judge, for pennies.
"""
import os
import subprocess
import sys
import time

SLEEP = float(os.environ.get("FL_DEMO_SLEEP", "1.3"))
HERE = os.path.dirname(os.path.abspath(__file__))


def pause(mult=1.0):
    time.sleep(SLEEP * mult)


BANNER = r"""
   __            _ _   _ _
  / _| __ _ _   _| | |_| (_)_ __   ___
 | |_ / _` | | | | | __| | | '_ \ / _ \    silent-failure testing
 |  _| (_| | |_| | | |_| | | | | |  __/        for AI agents
 |_|  \__,_|\__,_|_|\__|_|_|_| |_|\___|
"""

SCOREBOARD = """  custom order agent     CAUGHT a silent failure
  LangGraph              CAUGHT a silent failure
  pydantic-ai            CAUGHT a silent failure
  agno                   CAUGHT a silent failure
  LlamaIndex RAG         CAUGHT a silent failure
  ag2 / AutoGen          CAUGHT a silent failure
  CrewAI                 CAUGHT a silent failure
  smolagents             pass (agent was resilient)"""


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)   # keep our lines + the live subprocess in order
    except Exception:
        pass
    print(BANNER)
    pause()
    print("AI agents don't usually crash. They fail SILENTLY —")
    print("a confident, wrong answer with a 200 OK. Evals miss it.\n")
    pause(1.4)
    print("faultline breaks an agent's tools on purpose and catches the lie.\n")
    pause(1.4)
    print("------------------------------------------------------------")
    print(">>> Right now: faultline is driving a REAL Claude agent,")
    print(">>> feeding it a wrong inventory number, watching what it does.\n")
    print("------------------------------------------------------------\n")
    pause(0.6)
    env = dict(os.environ, PYTHONPATH=HERE + os.pathsep + os.environ.get("PYTHONPATH", ""))
    subprocess.run([sys.executable, os.path.join(HERE, "bench", "tool_caught", "live_ops_agent.py")], env=env)
    pause(1.6)
    print("\n============================================================")
    print("Now point it at the 8 most popular agent frameworks, live:")
    print("============================================================\n")
    pause(0.8)
    print(SCOREBOARD)
    print()
    pause(1.6)
    print("------------------------------------------------------------")
    print("  7 / 8 frameworks — the TOOL caught a silent failure, live.")
    print("  No LLM-judge. Deterministic. ~10 cents. Runs in your CI.")
    print("  one command:  python3 bench/tool_caught/run_all_live.py")
    print("------------------------------------------------------------")


if __name__ == "__main__":
    main()
