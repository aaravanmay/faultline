"""Render a text transcript into a SMOOTH typewriter-style terminal GIF — many frames, real-terminal feel.

No ffmpeg, no downloads (Pillow only).  Usage:  python3 render_typewriter_gif.py proof_transcript.txt proof.gif
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SRC = sys.argv[1] if len(sys.argv) > 1 else "proof_transcript.txt"
OUT = sys.argv[2] if len(sys.argv) > 2 else "proof.gif"

BG = (13, 17, 23)
FG = (222, 226, 230)
DIM = (120, 130, 140)
GREEN = (110, 220, 140)
RED = (250, 130, 120)
FONT_SIZE = 16
PAD = 16
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
IMG_W = PAD * 2 + CW * COLS
IMG_H = PAD * 2 + CH * ROWS


def color_for(line):
    s = line.strip()
    if s.startswith("UNSAFE") or "broke the rule" in s or ("ordered" in s and "in stock" in s):
        return RED
    if s.startswith("✓") or "handled correctly" in s or "held the rule" in s or "passed every case" in s:
        return GREEN
    if s.startswith("=") or s.startswith("-") or s.startswith("faultline ·") or s.startswith("label:") or "returned the TRUTH" in s:
        return DIM
    return FG


def render(prefix):
    img = Image.new("RGB", (IMG_W, IMG_H), BG)
    d = ImageDraw.Draw(img)
    lines = prefix.split("\n")[-ROWS:]
    for i, ln in enumerate(lines):
        d.text((PAD, PAD + i * CH), ln, font=font, fill=color_for(ln))
    return img


frames, durations = [], []
step = max(2, len(text) // 300)          # ~300 typing frames
i = 0
while i < len(text):
    i = min(len(text), i + step)
    frames.append(render(text[:i]))
    chunk = text[i - step:i]
    durations.append(420 if ("CAUGHT." in chunk or "ORDER\n" in chunk or "exist." in chunk) else 55)
# hold the final frame
frames.append(render(text)); durations.append(3200)

frames[0].save(os.path.join(HERE, OUT), save_all=True, append_images=frames[1:],
               duration=durations, loop=0, optimize=True)
print("wrote %s  (%d frames, %.1fs, %dx%d)" % (OUT, len(frames), sum(durations) / 1000, IMG_W, IMG_H))
