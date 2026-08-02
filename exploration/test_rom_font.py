"""Option 1: decode the font straight from the ROM file.

GB tiles are 16 bytes (2bpp, 8x8). We decode every 16-byte block of Deadeus.gb
into an 8x8 value grid, then:
  1. brute-force all 16 ways to binarize {0,1,2,3}->ink so ROM glyph hashes match
     our known VRAM glyph hashes (this auto-solves palette/polarity),
  2. with the best binarization, locate our known chars' ROM tile indices,
  3. test the ASCII-order hypothesis (constant base), and
  4. if it holds, derive the FULL printable-ASCII charmap in one shot.
"""

import hashlib
import json
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ROMFILE = ROOT / "roms" / "Deadeus.gb"
FONT = json.loads((ROOT / "deadeus_font.json").read_text(encoding="utf-8"))


def decode_all_tiles(data):
    n = len(data) // 16
    tiles = np.zeros((n, 8, 8), dtype=np.uint8)
    b = np.frombuffer(data[: n * 16], dtype=np.uint8).reshape(n, 8, 2)
    for col in range(8):
        bit = 7 - col
        lo = (b[:, :, 0] >> bit) & 1
        hi = (b[:, :, 1] >> bit) & 1
        tiles[:, :, col] = (hi << 1) | lo
    return tiles  # (n, 8, 8) values 0..3


def hashes_for(tiles, ink_set):
    ink = np.isin(tiles, list(ink_set)).astype(np.uint8)  # (n,8,8)
    return [hashlib.md5(t.tobytes()).hexdigest()[:6] for t in ink]


def all_mappings():
    for r in range(1, 4):
        for combo in combinations((0, 1, 2, 3), r):
            yield set(combo)


def main():
    data = ROMFILE.read_bytes()
    tiles = decode_all_tiles(data)
    n = len(tiles)
    print(f"ROM: {len(data)} bytes -> {n} tiles")

    known = {c: h for h, c in FONT.items() if h != "_comment" and c != " "}
    known_hashes = set(known.values())

    # 1) pick the binarization that reproduces the most known glyph hashes
    best = None
    for ink in all_mappings():
        hs = hashes_for(tiles, ink)
        found = known_hashes & set(hs)
        if best is None or len(found) > best[0]:
            best = (len(found), ink, hs)
    nfound, ink, hs = best
    print(f"best binarization: ink={sorted(ink)} -> {nfound}/{len(known)} known glyphs found in ROM\n")

    hash_to_idxs = {}
    for i, h in enumerate(hs):
        hash_to_idxs.setdefault(h, []).append(i)

    # 2) known chars -> ROM tile indices
    char_idxs = {c: hash_to_idxs.get(h, []) for c, h in known.items()}

    # 3) ASCII-order test: tile[base + ord(c) - 0x20] == glyph(c)
    scores = {}
    for c, idxs in char_idxs.items():
        for i in idxs:
            base = i - (ord(c) - 0x20)
            scores[base] = scores.get(base, 0) + 1
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:5]
    print("ASCII-order test (base: how many known chars line up):")
    for base, cnt in top:
        print(f"  base={base}: {cnt}/{len(known)}")

    if not top or top[0][1] < max(5, len(known) // 2):
        print("\nNo strong constant base -> font not simply ASCII-ordered in ROM.")
        return

    base = top[0][0]
    print(f"\n>>> Font block found at base tile {base}. Deriving full charmap:\n")
    derived = {}
    for a in range(0x20, 0x7F):
        idx = base + (a - 0x20)
        if 0 <= idx < n:
            derived[hs[idx]] = chr(a)
    for a in range(0x20, 0x7F):
        idx = base + (a - 0x20)
        if 0 <= idx < n:
            c = chr(a)
            mark = "" if hs[idx] in FONT else "  <-- NEW"
            print(f"  {c!r:5} ascii={a:3d} tile={idx:5d} hash={hs[idx]}{mark}")

    # Write the complete, ROM-derived font table.
    out = {"_comment": (
        f"Deadeus font map: md5(binarized 8x8 glyph, ink=palette index {sorted(ink)})"
        f"[:6] -> character. Derived directly from the ROM's ASCII-ordered font block "
        f"at tile {base} (offset {base * 16:#x}); see exploration/test_rom_font.py. "
        f"Covers printable ASCII 0x20-0x7E.")}
    for a in range(0x20, 0x7F):
        idx = base + (a - 0x20)
        if 0 <= idx < n and hs[idx] not in out:
            out[hs[idx]] = chr(a)
    (ROOT / "deadeus_font.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {len(out) - 1} glyphs to deadeus_font.json")


if __name__ == "__main__":
    main()
