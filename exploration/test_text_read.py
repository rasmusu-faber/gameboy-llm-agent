"""Phase A of text reading: can we pull the 8x8 pixel bitmap of each window text
tile out of PyBoy, and are the patterns clean/stable?

Reaches a dialog, then for the text rows of the window layer:
  - grabs each tile's 8x8 bitmap,
  - renders it as ASCII art (so we can literally read the word back), and
  - prints a short hash per cell (same glyph -> same hash proves stability).
No font table yet - this only verifies the raw material.
"""

import hashlib
from pathlib import Path

import numpy as np
from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
OUT = Path("runs/text_read")
A_PRESSES = 56          # reach an intro dialog line
TEXT_ROWS = (1, 2)      # window rows that hold dialog text (from earlier dumps)
COLS = range(0, 20)


def press(pyboy, button, hold=6, wait=20):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def tile_bitmap(pyboy, tm, x, y):
    """Return the tile's 8x8 grayscale array, trying both PyBoy APIs."""
    try:
        tile = tm.tile(x, y)
    except (AttributeError, TypeError):
        tile = pyboy.get_tile(tm[x, y])
    nd = tile.ndarray
    if callable(nd):          # some PyBoy versions expose ndarray() as a method
        nd = nd()
    a = np.array(nd)
    if a.ndim == 3:           # RGBA -> take one channel
        a = a[..., 0]
    return a


def to_bits(a):
    """Binarize: bright pixel (ink) = 1."""
    return (a > 128).astype(np.uint8)


def ascii_art(bits):
    return ["".join("#" if v else "." for v in row) for row in bits]


def short_hash(bits):
    return hashlib.md5(bits.tobytes()).hexdigest()[:6]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")
    press(pyboy, "start")
    for _ in range(A_PRESSES):
        press(pyboy, "a")
    pyboy.screen.image.save(OUT / "dialog.png")

    tm = pyboy.tilemap_window
    for row in TEXT_ROWS:
        cells = [(x, tile_bitmap(pyboy, tm, x, row)) for x in COLS]
        print(f"\n=== window row {row}: stitched glyphs ===")
        arts = [ascii_art(to_bits(a)) for _, a in cells]
        for line in range(8):                       # 8 pixel rows tall
            print("  " + " ".join(art[line] for art in arts))
        print(f"--- row {row}: per-cell tile id + hash ---")
        for x, a in cells:
            print(f"  col {x:2d}: id={tm[x, row]:3d}  hash={short_hash(to_bits(a))}")
    pyboy.stop()
    print(f"\nScreenshot: {OUT / 'dialog.png'}")


if __name__ == "__main__":
    main()
