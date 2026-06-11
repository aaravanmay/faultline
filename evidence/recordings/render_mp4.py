"""Render the proof transcript into a real .mp4 (H.264) — smooth typewriter terminal video.

Uses the bundled ffmpeg from the imageio-ffmpeg PyPI package (no system install, no random binaries).
Run with the venv python:  .venv311/bin/python render_mp4.py proof_transcript.txt proof.mp4
"""
import os
import sys

import numpy as np
import imageio.v2 as imageio
from PIL import Image, ImageDraw, ImageFont

SRC = sys.argv[1] if len(sys.argv) > 1 else "proof_transcript.txt"
OUT = sys.argv[2] if len(sys.argv) > 2 else "proof.mp4"
FPS = 30

BG = (13, 17, 23)
FG = (222, 226, 230)
DIM = (120, 130, 140)
GREEN = (110, 220, 140)
RED = (250, 130, 120)
CYAN = (120, 200, 240)
YELLOW = (235, 200, 120)
FONT_SIZE = 18
PAD = 18
ROWS = 22

HERE = os.path.dirname(os.path.abspath(__file__))
text = open(os.path.join(HERE, SRC)).read().rstrip("\n")
COLS = max(len(l) for l in text.split("\n")) + 2

font = None
for p in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf"):
    if os.path.exists(p):
        font = ImageFont.truetype(p, FONT_SIZE); break
font = font or ImageFont.load_default()
bb = font.getbbox("M")
CW = bb[2] - bb[0] + 1
CH = int(FONT_SIZE * 1.45)


def up16(n):
    return (n + 15) // 16 * 16


IMG_W = up16(PAD * 2 + CW * COLS)
IMG_H = up16(PAD * 2 + CH * ROWS)


def color_for(line):
    s = line.strip()
    # tutorial vocabulary
    if s.startswith("$"):
        return CYAN                                  # shell command
    if s.startswith("#"):
        return DIM                                   # narration comment
    if "Successfully installed" in s or "silent failure caught" in s:
        return GREEN
    # 4-bugs demo vocabulary
    if "stars)" in s and "faultline" in s:
        return CYAN                                  # project header line
    if s.startswith("CAUGHT") or "real bugs in famous" in s:
        return GREEN
    if s.startswith("-> PR") or s.startswith("PR #"):
        return YELLOW
    # vs-eval demo vocabulary
    if "WRONG" in s or ("SILENT" in s and "FAIL" in s) or s.startswith("⚠"):
        return RED
    if "PASS" in s or "GREEN" in s or "CAUGHT" in s:
        return GREEN
    if s.startswith("[A]") or s.startswith("[B]") or "SAME AGENT" in s:
        return YELLOW
    # proof (scenarios) demo vocabulary
    if s.startswith("UNSAFE") or "broke the rule" in s or ("ordered" in s and "in stock" in s):
        return RED
    if s.startswith("✓") or "handled correctly" in s or "held the rule" in s or "passed every case" in s:
        return GREEN
    if s.startswith("=") or s.startswith("-") or s.startswith("faultline ·") or s.startswith("label:") or "returned the TRUTH" in s or "No faking" in s:
        return DIM
    return FG


def frame(prefix):
    img = Image.new("RGB", (IMG_W, IMG_H), BG)
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(prefix.split("\n")[-ROWS:]):
        d.text((PAD, PAD + i * CH), ln, font=font, fill=color_for(ln))
    return np.asarray(img)


writer = imageio.get_writer(os.path.join(HERE, OUT), fps=FPS, codec="libx264",
                            quality=8, macro_block_size=None, ffmpeg_log_level="error")

# ~0.5s blank-ish lead, type the body, hold at key beats + end
step = max(2, len(text) // (11 * FPS))          # ~11s of typing
i = 0
writer.append_data(frame(""))
while i < len(text):
    i = min(len(text), i + step)
    f = frame(text[:i])
    writer.append_data(f)
    chunk = text[i - step:i]
    if "DECLINE" in chunk and "decided" in text[:i][-40:]:
        for _ in range(int(FPS * 0.7)): writer.append_data(f)      # beat after the correct refusal
    if "exist." in chunk:
        for _ in range(int(FPS * 0.9)): writer.append_data(f)      # beat after the bad order
    if "CAUGHT." in chunk:
        for _ in range(int(FPS * 1.0)): writer.append_data(f)      # beat on the verdict
    if "shippable." in chunk:
        for _ in range(int(FPS * 0.9)): writer.append_data(f)      # beat on the eval's false green
    if "was raised" in chunk:
        for _ in range(int(FPS * 0.9)): writer.append_data(f)      # beat on the fabricated answer
    if "PR #" in chunk or "-> PR" in chunk:
        for _ in range(int(FPS * 0.8)): writer.append_data(f)      # beat after each project's catch
final = frame(text)
for _ in range(int(FPS * 3.5)):                                     # hold the full proof
    writer.append_data(final)
writer.close()

dur = "?"
print("wrote %s  (%dx%d, %d fps, H.264)" % (OUT, IMG_W, IMG_H, FPS))
