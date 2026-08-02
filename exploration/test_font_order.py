"""Hypothesis test: is the font stored in VRAM in a fixed (ASCII) order?

If so, tile[base + (ord(c) - 0x20)] holds the glyph for character c, for a single
constant `base`. We know ~35 (hash -> char) pairs, so we can test it: dump all
384 VRAM tiles, hash them, and search for a base at which our known characters
line up. If one base explains most known chars, the font is ordered and we can
read every remaining character straight from VRAM - no more dialog hunting.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from pyboy import PyBoy

ROOT = Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")
FONT = json.loads((ROOT / "deadeus_font.json").read_text(encoding="utf-8"))
N_TILES = 384  # VRAM tile-data slots (0x8000-0x97FF)


def press(pyboy, button, hold=6, wait=20):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def hash_of(tile):
    nd = tile.ndarray
    if callable(nd):
        nd = nd()
    a = np.array(nd)
    if a.ndim == 3:
        a = a[..., 0]
    return hashlib.md5((a > 128).astype(np.uint8).tobytes()).hexdigest()[:6]


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")
    for _ in range(58):          # reach a dialog so glyphs are loaded
        press(pyboy, "a")

    # Dump + hash every VRAM tile
    vram = {}
    for i in range(N_TILES):
        try:
            vram[i] = hash_of(pyboy.get_tile(i))
        except Exception as e:  # noqa: BLE001
            print(f"get_tile({i}) failed: {e}")
            break
    pyboy.stop()

    # known char -> its glyph hash (skip meta/space)
    known = {c: h for h, c in FONT.items() if h != "_comment" and c != " "}
    hash_to_idxs = {}
    for i, h in vram.items():
        hash_to_idxs.setdefault(h, []).append(i)

    print(f"Dumped {len(vram)} VRAM tiles. Known chars: {len(known)}")
    print("Which known glyphs are present in VRAM right now:")
    present = 0
    for c, h in sorted(known.items()):
        idxs = hash_to_idxs.get(h, [])
        if idxs:
            present += 1
        print(f"  {c!r:4} hash={h}  at tiles={idxs}")
    print(f"-> {present}/{len(known)} known glyphs currently resident in VRAM\n")

    # Search for a constant base assuming ASCII order: tile[base + ord(c) - 0x20]
    print("Testing ASCII-order hypothesis (best base by matches):")
    best = []
    for base in range(-0x20, N_TILES):
        matches = 0
        for c, h in known.items():
            idx = base + (ord(c) - 0x20)
            if 0 <= idx < N_TILES and vram.get(idx) == h:
                matches += 1
        best.append((matches, base))
    best.sort(reverse=True)
    for matches, base in best[:5]:
        print(f"  base={base:4d}: {matches}/{len(known)} known chars line up")


if __name__ == "__main__":
    main()
