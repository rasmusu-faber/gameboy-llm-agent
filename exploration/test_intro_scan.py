"""Sweep the intro in small steps to find more VISIBLE dialog text (to extend
the font table). At each step: save a screenshot, read the window text tiles,
and decode them with the current deadeus_font.json (unknown glyph -> '?').

Lines with '?' contain glyphs not yet in the table: open those screenshots,
read the real letters, and extend the font map.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from pyboy import PyBoy

ROOT = Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")
FONT = json.loads((ROOT / "deadeus_font.json").read_text(encoding="utf-8"))
OUT = ROOT / "runs" / "intro_scan"
WY_ADDR = 0xFF4A

START, STOP, STEP = 40, 136, 6
TEXT_ROWS = (1, 2)
TEXT_COLS = range(1, 18)
BORDER = {"92056e", "06135a"}   # window box left/right border tiles -> ignore


def press(pyboy, hold=6, wait=20):
    pyboy.button_press("a")
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release("a")
    for _ in range(wait):
        pyboy.tick()


def tile_hash(pyboy, tm, x, y):
    try:
        tile = tm.tile(x, y)
    except (AttributeError, TypeError):
        tile = pyboy.get_tile(tm[x, y])
    nd = tile.ndarray
    if callable(nd):
        nd = nd()
    a = np.array(nd)
    if a.ndim == 3:
        a = a[..., 0]
    bits = (a > 128).astype(np.uint8)
    return hashlib.md5(bits.tobytes()).hexdigest()[:6]


def decode_row(pyboy, tm, row):
    chars, hashes = [], []
    for x in TEXT_COLS:
        h = tile_hash(pyboy, tm, x, row)
        hashes.append(h)
        chars.append("|" if h in BORDER else FONT.get(h, "?"))
    return "".join(chars).rstrip(), hashes


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy)  # start is 'a' here too? no - need start; press start twice
    # (the intro needs Start first; do it explicitly)
    pyboy.button_press("start")
    for _ in range(6):
        pyboy.tick()
    pyboy.button_release("start")
    for _ in range(20):
        pyboy.tick()

    pressed = 1
    for cp in range(START, STOP + 1, STEP):
        while pressed < cp:
            press(pyboy)
            pressed += 1
        pyboy.screen.image.save(OUT / f"cp_{cp:03d}.png")
        tm = pyboy.tilemap_window
        wy = pyboy.memory[WY_ADDR]
        r1, h1 = decode_row(pyboy, tm, 1)
        r2, h2 = decode_row(pyboy, tm, 2)
        vis = "on-screen" if wy < 144 else "parked"
        print(f"A={cp:3d}  WY={wy:3d} ({vis:9s}) | r1={r1!r}  r2={r2!r}")
        print("   h1: " + " ".join(h1))
        print("   h2: " + " ".join(h2))
    pyboy.stop()
    print(f"\nScreenshots in {OUT}/  (open the ones with '?' to read new letters)")


if __name__ == "__main__":
    main()
