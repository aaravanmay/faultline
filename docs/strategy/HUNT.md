# HUNT.md — catching a real silent failure in a public agent

The "real milestone": point faultline at a real open-source AI agent, catch a genuine silent failure, and file a **friendly PR with a fix + test**. That one act is your proof, your demo, and your launch story.

**Honest note:** this part runs on *your* machine — it needs a real LLM (your local Llama via Ollama is perfect and free) and, for browser-use, a real browser. It couldn't be done in the build sandbox. Budget ~30–60 min. Cost: **$0 on local Llama**, or a few dollars on a cheap API model.

---

## Do the EASY target first (fastest catch, least adapter work)
faultline's current `@tool`/`wrap` wraps **plain Python functions** directly — so the lowest-friction first target is a **pure-Python, tool-using agent** (no browser). Best first pick: **GPT Researcher** (its tools are web-search / scrape functions) or any small LangChain tool-agent. browser-use is the most *impressive* demo but it's async + browser-heavy → do it **second**.

### Steps (easy target)
1. **Set up** (in a fresh venv):
   ```
   pip install faultline gpt-researcher   # or your target
   # point the agent's LLM at your local Llama (Ollama) — free, unlimited test runs
   ```
2. **Wrap the content-returning tools.** Find the functions the agent calls to *get information* (web search, scrape, retrieve) and wrap them so faultline can corrupt what they return; wrap any *action* tools (send, write, post) with `is_action=True` so they don't really fire:
   ```python
   from faultline.trace import tool, wrap
   import gpt_researcher.tools as t        # (whatever module holds its tools)
   t.web_search = tool(t.web_search)       # faultline can now corrupt search results
   t.scrape    = tool(t.scrape)
   ```
3. **Run it under faultline** on a real task:
   ```python
   from faultline.runner import check
   from faultline.faults import NullResponse, Truncate, StaleData, WrongNumber
   def agent(task): return run_the_researcher(task)   # your one-line entry point
   res = check(agent, {"query": "summarize X"}, faults=[
       NullResponse(targets=["web_search"]),   # search returned nothing
       Truncate(targets=["scrape"]),           # half a page
       StaleData(targets=["web_search"]),      # yesterday's results
   ], trials=5)
   res.report()
   ```
4. **A real catch =** the agent produced a confident report/answer that *used the corrupted/empty data with no error or hedge* → faultline marks it `FAIL (silent)`. (e.g., "wrote a confident, sourced-looking summary even though search returned nothing.")

---

## Then browser-use (the visceral demo, second)
browser-use registers its actions in a `Controller` via `@controller.action`, dispatched to a `BrowserSession` ([custom-functions docs](https://docs.browser-use.com/customize/custom-functions)). Two honest caveats: its actions are **async** (faultline's v1 trace is sync — you'll need a small async wrapper), and internals shift between versions, so **verify against your installed version.**

**Approach (grounded in its documented, stable API):** register your *own* version of a content-returning action that returns corrupted content, and capture the side-effecting ones:
```python
from browser_use import Agent, Controller
controller = Controller()

@controller.action("Read page content")        # override / shadow the content the LLM sees
async def read_corrupted(browser_session):
    real = await browser_session.get_state()   # or the real extract method in your version
    real.text = ""                             # inject the fault: empty / stale / wrong page
    return real

@controller.action("Click element")            # capture the side effect — don't really click
async def fake_click(index: int):
    print("FAULTLINE: agent tried to click", index, "(suppressed)")
    return "clicked (stubbed)"

agent = Agent(task="buy the cheapest widget", controller=controller, llm=your_local_llama)
await agent.run()
```
**A real catch =** the agent confidently "completes" the task (says it bought/clicked) even though the page content was empty/wrong and the clicks were stubbed. Record the 60–90s screen capture — *that's* the demo.

*(The cleaner long-term path is a real faultline `adapters/browser_use.py` that wraps every registry action automatically + adds async support. That's the next build once you've confirmed a catch by hand.)*

---

## When you catch one
1. **File a friendly PR** to the repo: a fix (a null/stale guard, a retry, a "couldn't verify" abstention) **+ a regression test.** Title it as a *contribution*, not a callout: *"Handle empty/stale tool responses gracefully (silent-failure fix)."* Never "your agent is broken."
2. **Write it up** once: *"faultline found & fixed a silent failure in [agent] — here's how."* → Show HN / the agent's Discord / r/LocalLLaMA.
3. **Watch the two signals:** does the maintainer merge it (it works), and do devs reply "run it on mine" (they care). That's your go/no-go.

## Proven already (offline, in this repo)
- `python3 -m faultline.cli check --demo` — a decision agent silently buys out-of-stock goods on corrupted inventory.
- `python3 -m faultline.examples.browser_demo` — a browser agent silently buys a $500 item it thinks costs $50 on a corrupted page; no real clicks fire.
Both show the exact pattern you'll hunt for in the wild.
