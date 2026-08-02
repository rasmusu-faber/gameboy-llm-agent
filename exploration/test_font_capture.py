"""Phase B: capture several dialog screens across the intro and dump each text
tile's glyph (as ASCII) + hash, so a {hash: char} font table can be assembled by
reading the glyphs. Also saves a screenshot per checkpoint for cross-checking.
"""

import hashlib
from pathlib import Path

import numpy as np
from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
OUT = Path("runs/font_capture")
CHECKPOINTS = [40, 56, 100, 150, 200, 260]  # cumulative A-presses
TEXT_ROWS = (1, 2)
TEXT_COLS = range(1, 18)   # skip the vertical border at col 0 and cols 18-19


def press(pyboy, button, hold=6, wait=20):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def tile_bits(pyboy, tm, x, y):
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
    return (a > 128).astype(np.uint8)


def short_hash(bits):
    return hashlib.md5(bits.tobytes()).hexdigest()[:6]


def capture(pyboy, cp):
    tm = pyboy.tilemap_window
    pyboy.screen.image.save(OUT / f"cp_{cp:03d}.png")
    print(f"\n########## checkpoint: {cp} A-presses  (see cp_{cp:03d}.png) ##########")
    for row in TEXT_ROWS:
        cells = [(x, tile_bits(pyboy, tm, x, row)) for x in TEXT_COLS]
        print(f"\n-- row {row} glyphs --")
        for line in range(8):
            print("  " + " ".join("".join("#" if v else "." for v in b[line]) for _, b in cells))
        print("  hashes: " + " ".join(short_hash(b) for _, b in cells))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")
    press(pyboy, "start")

    pressed = 0
    for cp in CHECKPOINTS:
        while pressed < cp:
            press(pyboy, "a")
            pressed += 1
        capture(pyboy, cp)
    pyboy.stop()
    print(f"\nScreenshots in {OUT}/")


if __name__ == "__main__":
    main()
