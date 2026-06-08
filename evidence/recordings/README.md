# Recordings

Real recordings of faultline running. Not mockups.

## `main_demo.cast` — the polished hero demo (~29s)
An [asciinema](https://asciinema.org) recording of `python3 demo.py`: faultline drives a **real
Claude-backed order agent** through the API, feeds it a wrong inventory number, and its own detector
catches the agent placing an order it would never place on the true number — then prints the scoreboard.

**What this clip genuinely proves:** the *live* order-agent catch is real (real API calls, real model,
real detection — no human, no LLM-judge).

**What it does NOT prove on its own:** the 8-framework scoreboard shown at the end is a *summary* of the
full live run (`bench/tool_caught/run_all_live.py`), not re-run inside this 29-second clip. Per-framework
live evidence is a separate artifact (needs each framework installed).

### View it
```bash
pip install asciinema           # if not already
asciinema play main_demo.cast   # plays in your terminal at real speed
```

### Share it (easiest → a real video)
```bash
asciinema upload main_demo.cast        # → a shareable asciinema.org player link (embeds anywhere)
```
Or screen-record the playback with QuickTime / Cmd-Shift-5 for an MP4.

### Turn it into a GIF (for HN / Twitter / README)
Needs [`agg`](https://github.com/asciinema/agg) (standalone, no ffmpeg):
```bash
agg main_demo.cast main_demo.gif
```

## `main_demo_transcript.txt`
The full plain-text output of the same run — text evidence you can paste anywhere, no player needed.
