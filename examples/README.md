# faultline examples

Every example is **runnable and offline** (no API key) unless noted. Run with `python3 examples/<file>`.

## Start here
| Example | What it shows |
|---|---|
| **[vs_eval.py](vs_eval.py)** | The whole thesis, executable: the SAME agent — a plain eval goes **green** on clean data, then faultline breaks the retrieval tool and **catches** the agent fabricating an answer. The best "how is this not just evals?" demo. |
| **[quickstart.ipynb](quickstart.ipynb)** | The 4-step quickstart as a Jupyter notebook: wrap a tool → write the rule → break it → read the verdict. |

## Drop faultline into your project
| Example | What it shows |
|---|---|
| **[rag_pipeline.py](rag_pipeline.py)** | Copy-paste RAG integration template (`retrieve → generate`). A buggy generator fabricates from empty retrieval and is caught; a grounded one (abstains) passes. The GPT-Researcher / STORM / LlamaIndex class. |
| **[multi_tool_agent.py](multi_tool_agent.py)** | A realistic 4-tool chain (stock → price → budget → order) showing a **cascade**: a corrupted price 3 steps upstream flows into an over-budget order, caught. |

## The modes, by example
| Example | Mode |
|---|---|
| **[demo_silent_rag.py](demo_silent_rag.py)** | The empty-retrieval silent failure caught by `abstain_when_context_empty`. |
| **[mine_demo.py](mine_demo.py)** | `mine` — faultline learns the call-ordering rule from good runs, then catches a refactor that skips a step. |
| **[flightlog_loop_demo.py](flightlog_loop_demo.py)** | `replay` — a recorded run on disk becomes a regression test. |

## With a real LLM (needs an API key)
| Example | What it shows |
|---|---|
| **[llm_agent_proof.py](llm_agent_proof.py)** | faultline catching a silent-wrong on a **real Claude tool-calling agent** (uses your `.env` key; cheap — Haiku, a few calls). This is the one to record for a demo. |

---
Packaged examples (ship with `pip install faultline`) live in `faultline/examples/` — e.g. `your_agent.py`
(the `scan` example), `langgraph_catch.py` (a deterministic end-to-end catch on a real `create_react_agent`),
and `whats_new_0_4_2.py` (`python -m faultline.examples.whats_new_0_4_2`). Honest scope of every feature: [../CAPABILITIES.md](../CAPABILITIES.md).
