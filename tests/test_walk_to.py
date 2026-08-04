"""Weg B check: the deterministic controller reaches the exact target (72,88)
where the LLM navigation got stuck."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro  # noqa: E402
from navigation import walk_to  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")
OUT = ROOT / "runs" / "walk_to"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    x0, y0 = P.player_position(pyboy)
    tx, ty = min(x0 + 16, 96), max(y0 - 16, 64)   # same target the LLM failed at
    print(f"start ({x0},{y0}) -> target ({tx},{ty})")

    reached = walk_to(pyboy, tx, ty)
    x, y = P.player_position(pyboy)
    pyboy.screen.image.save(OUT / "walk_to.png")
    print(f"final ({x},{y})  reached={reached}")
    print("PASS" if reached and (x, y) == (tx, ty) else "FAIL")
    pyboy.stop()


if __name__ == "__main__":
    main()
