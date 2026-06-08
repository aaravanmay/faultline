"""Render an asciinema .cast (plain-text, no ANSI) into a watchable animated GIF — no ffmpeg, no downloads.

Usage:  python3 render_gif.py main_demo.cast main_demo.gif
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

CAST = sys.argv[1] if len(sys.argv) > 1 else "main_demo.cast"
OUT = sys.argv[2] if len(sys.argv) > 2 else "main_demo.gif"

# terminal look
BG = (13, 17, 23)
FG = (222, 226, 230)
FONT_SIZE = 17
PAD = 18

HERE = os.path.dirname(os.path.abspath(__file__))
lines = open(os.path.join(HERE, CAST)).read().splitlines()
header = json.loads(lines[0])
W = header.get("width", 90)
H = header.get("height", 30)
events = [json.loads(l) for l in lines[1:] if l.strip()]

# pick a real monospace font
font = None
for path in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf",
             "/System/Library/Fonts/Courier New.ttf"):
    if os.path.exists(path):
        font = ImageFont.truetype(path, FONT_SIZE)
        break
if font is None:
    font = ImageFont.load_default()

# char cell size
bbox = font.getbbox("M")
cw = bbox[2] - bbox[0] + 1
ch = int(FONT_SIZE * 1.35)
IMG_W = PAD * 2 + cw * W
IMG_H = PAD * 2 + ch * H


def render(text):
    img = Image.new("RGB", (IMG_W, IMG_H), BG)
    d = ImageDraw.Draw(img)
    text = text.replace("\r\n", "\n").replace("\r", "")   # drop carriage returns (render as tofu otherwise)
    # expand the cumulative text into screen lines (wrap at width), keep last H
    screen = []
    for ln in text.split("\n"):
        if ln == "":
            screen.append("")
        while len(ln) > W:
            screen.append(ln[:W]); ln = ln[W:]
        if ln != "" or text.endswith("\n"):
            screen.append(ln)
    screen = screen[-H:]
    for i, ln in enumerate(screen):
        d.text((PAD, PAD + i * ch), ln, font=font, fill=FG)
    return img


frames, durations, buf = [], [], ""
for i, ev in enumerate(events):
    buf += ev[2]
    frames.append(render(buf))
    nxt = events[i + 1][0] if i + 1 < len(events) else ev[0] + 2.8
    durations.append(max(400, int((nxt - ev[0]) * 1000)))  # ms, min 0.4s/frame

frames[0].save(os.path.join(HERE, OUT), save_all=True, append_images=frames[1:],
               duration=durations, loop=0, optimize=True)
print("wrote %s  (%d frames, %.1fs, %dx%d)" % (OUT, len(frames), sum(durations) / 1000, IMG_W, IMG_H))
