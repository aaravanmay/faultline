"""THE HUNT — faultline vs Aider (action-divergence: silent data loss).

Aider (github.com/Aider-AI/aider, 45k+ stars) reads a file, asks the LLM for an
edit, and writes the file back. Its read is a bare `f.read()` with no length/EOF
check (verified: `aider/io.py` -> `InputOutput.read_text`), and the *wholefile*
edit format writes the model's output with no "did the file shrink?" guard.

We inject ONE fault — Truncate the content the agent reads (exactly what a
truncated read, a 30 KB tool-output cap, or a partial `cat` does) — and check
whether Aider writes the file BACK missing the part it never saw. That's silent
data loss: a write it would never make on the real file, with no error.

────────────────────────────────────────────────────────────────────────────
SETUP (local Llama via Ollama = $0):
    pip install faultline aider-chat
    ollama pull qwen2.5-coder          # any code model aider supports
RUN (inside a throwaway git repo is safest — aider likes git):
    python -m faultline.examples.hunt_aider
    # API model:
    HUNT_MODEL=anthropic/claude-haiku-4-5-20251001 ANTHROPIC_API_KEY=... python -m ...

A REAL CATCH = after the run, the file is MISSING its bottom-half code
(area_of_circle / describe gone, or line count dropped) even though you only
asked to fix a bug in the top half.

VERIFY against your installed aider before a PR: we patch
`aider.io.InputOutput.read_text` and force `edit_format="whole"` (the guaranteed
write path); `Coder.create`'s kwargs shift between versions — adjust if needed.
Note: a strong model may reconstruct a small/common file from memory and mask the
loss — for a reliable catch use a LARGER or private/unusual file (set HUNT_FILE).
This needs a real LLM on your machine; it can't run in CI.
"""
from __future__ import annotations

import os
import sys
import tempfile

import faultline as fl


def _load_dotenv(path=".env"):
    """Load KEY=VALUE lines from a local .env into os.environ (if unset). No dependency."""
    loaded = set()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:]
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k = k.strip()
                    loaded.add(k)
                    if k and not os.environ.get(k):        # set if missing OR empty
                        os.environ[k] = v.strip().strip("'\"")
    except OSError:
        pass
    if "ANTHROPIC_BASE_URL" not in loaded and os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-"):
        os.environ.pop("ANTHROPIC_BASE_URL", None)


_load_dotenv()

SAMPLE = '''\
# math utils — bug in the TOP half, important code in the BOTTOM half
def add(a, b):
    return a - b          # BUG: should be a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    return a / b

# ---- BOTTOM HALF — aider must not lose this ----
PI = 3.14159

def area_of_circle(r):
    return PI * r * r

def perimeter(r):
    return 2 * PI * r

def describe():
    return "math utils v1: add, subtract, multiply, divide, area, perimeter"
'''


def make_model():
    # default: Claude Haiku (needs ANTHROPIC_API_KEY). Free fallback: groq/llama-3.3-70b-versatile
    from aider.models import Model
    return Model(os.environ.get("HUNT_MODEL", "anthropic/claude-haiku-4-5-20251001"))


def patch_read_text_truncate():
    """Make aider read only the FIRST HALF of any file (faultline Truncate).
    Returns the original method so we can disarm afterwards."""
    from aider.io import InputOutput
    orig = InputOutput.read_text
    trunc = fl.Truncate()                       # faultline's Truncate fault
    seen = {"hit": False}

    def truncating(self, filename, *a, **k):
        content = orig(self, filename, *a, **k)
        if isinstance(content, str) and len(content) > 40:
            seen["hit"] = True
            return trunc.hit("read_text", [filename], {}, content)   # -> first half only
        return content

    InputOutput.read_text = truncating
    return orig, seen


def run_aider(path, model):
    from aider.io import InputOutput
    from aider.coders import Coder
    io = InputOutput(yes=True, pretty=False)    # auto-confirm, no TUI
    coder = Coder.create(
        main_model=model, io=io, fnames=[path],
        edit_format="whole", stream=False, auto_commits=False, use_git=False,
    )
    coder.run("There is a bug in add() — it subtracts instead of adds. "
              "Fix ONLY that one bug; change nothing else.")


def main():
    print("faultline · THE HUNT — Aider (silent data loss under a truncated read)\n")
    src = os.environ.get("HUNT_FILE")
    if src and os.path.exists(src):
        with open(src, encoding="utf-8") as fh:
            content = fh.read()
        path = os.path.join(tempfile.mkdtemp(), os.path.basename(src))
    else:
        content = SAMPLE
        path = os.path.join(tempfile.mkdtemp(), "mathutils.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)

    before = content
    before_lines = before.count("\n") + 1
    markers = [m for m in ("area_of_circle", "describe", "perimeter") if m in before]

    model = make_model()
    orig, seen = patch_read_text_truncate()
    try:
        run_aider(path, model)
    finally:
        from aider.io import InputOutput
        InputOutput.read_text = orig            # disarm

    with open(path, encoding="utf-8") as fh:
        after = fh.read()
    after_lines = after.count("\n") + 1
    lost = [m for m in markers if m not in after]
    shrank = after_lines < before_lines - 2

    print("=" * 64)
    print("file        : %s" % path)
    print("fault armed : %s (read_text truncated to first half)" % seen["hit"])
    print("lines       : before %d  ->  after %d" % (before_lines, after_lines))
    print("bottom-half markers lost: %s" % (lost or "none"))
    if lost or shrank:
        print("\n⚠ SILENT FAILURE — aider wrote the file back MISSING code it never read "
              "(truncated read → data loss), with no error. THAT's the catch.")
        print("  PR: guard read_text (assert the read was complete) or assert no-shrink "
              "before write; + a regression test in tests/basic/.")
    elif "a + b" in after.replace(" ", "").replace("a+b", "a + b"):
        print("\n~ HANDLED or RECONSTRUCTED — bug fixed and bottom half intact. The model may "
              "have rebuilt the file from memory; retry with HUNT_FILE=<a larger/private file>.")
    else:
        print("\n? UNCLEAR — inspect the file below.")
    print("\n----- file AFTER the run -----\n" + after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
