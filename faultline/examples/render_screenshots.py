"""Render the REAL trace (trace.txt) into terminal-style PNG screenshots.

Not a mockup — it renders the exact stdout captured from the live agent run.

Run:  .venv311/bin/python -m faultline.examples.render_screenshots
"""
from __future__ import annotations

import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHOTS = os.path.join(HERE, "evidence", "screenshots")
TRACE = os.path.join(SHOTS, "trace.txt")

BG = (11, 14, 20)
DIM = (90, 99, 110)
FG = (200, 207, 213)
RED = (255, 110, 95)
ORANGE = (210, 153, 34)
GREEN = (63, 185, 80)
CYAN = (88, 166, 255)
YELLOW = (240, 200, 90)
WHITE = (240, 246, 252)

WRAP = 104
SIZE = 22
PAD = 28
LH = 30


def _font(size):
    for p in ("/System/Library/Fonts/Menlo.ttc",
              "/System/Library/Fonts/Monaco.ttf",
              "/System/Library/Fonts/SFNSMono.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def color_for(line):
    s = line.strip()
    if "WRONG" in line or "CRASHED" in line:
        return RED
    if "FAULT" in line:
        return ORANGE
    if "correct (declined)" in line:
        return GREEN
    if "ACTION CAPTURED" in line:
        return YELLOW
    if "RAISED" in line:
        return ORANGE
    if s.startswith("[") and "]" in s:
        return CYAN
    if "DECISION:" in line:
        return WHITE
    if set(s) <= set("=-") and s:
        return DIM
    if s.startswith("agent's own words"):
        return (158, 180, 201)
    return FG


def wrap_lines(raw):
    out = []
    for ln in raw.split("\n"):
        if len(ln) <= WRAP:
            out.append((ln, color_for(ln)))
        else:
            col = color_for(ln)
            indent = "      " if ln.startswith("   ") else ""
            chunks = textwrap.wrap(ln, WRAP, subsequent_indent=indent,
                                   break_long_words=True, break_on_hyphens=False)
            for c in chunks:
                out.append((c, col))
    return out


def render(lines, path, title):
    font = _font(SIZE)
    tfont = _font(SIZE - 4)
    cw = font.getbbox("M")[2]
    width = PAD * 2 + cw * (WRAP + 2)
    height = PAD * 2 + LH * (len(lines) + 2) + 14
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    # title bar dots
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((PAD + i * 22, 16, PAD + i * 22 + 13, 29), fill=c)
    d.text((PAD + 80, 14), title, font=tfont, fill=DIM)
    y = PAD + 20
    for text, col in lines:
        d.text((PAD, y), text, font=font, fill=col)
        y += LH
    img.save(path)
    return path, width, height


def main():
    with open(TRACE) as f:
        raw = f.read().rstrip("\n")
    lines = wrap_lines(raw)
    p, w, h = render(lines, os.path.join(SHOTS, "01_caught_in_the_act.png"),
                     "faultline -- live smolagents run")
    print("wrote %s (%dx%d)" % (p, w, h))

    # focused screenshot: just the wrong-number case
    block = raw.split("[2] WRONG-NUMBER")[1].split("====")[0]
    block = "[2] WRONG-NUMBER" + block
    p2, w2, h2 = render(wrap_lines(block.rstrip()),
                        os.path.join(SHOTS, "02_the_silent_failure.png"),
                        "faultline -- the silent failure")
    print("wrote %s (%dx%d)" % (p2, w2, h2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
