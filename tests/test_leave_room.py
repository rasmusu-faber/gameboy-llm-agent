"""Goal test: can the agent actually LEAVE the starting room?

Room-change signal: the full 32x32 background tilemap is a per-scene fingerprint
(constant while you scroll around a room, changes completely on a scene load).
The agent sweeps each edge, pushing outward, until that fingerprint changes.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro  # noqa: E402
from navigation import press, walk_direction  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")
OUT = ROOT / "runs" / "leave_room"

# (moves to reach a corner, direction to push outward, direction to sweep along)
EDGES = [
    (["up", "left"], "up", "right"),      # top edge, sweep left->right
    (["up", "right"], "right", "down"),   # right edge, sweep top->bottom
    (["down", "left"], "down", "right"),  # bottom edge, sweep left->right
    (["up", "left"], "left", "down"),     # left edge, sweep top->bottom
]


def full_bg_hash(pyboy):
    tm = pyboy.tilemap_background
    return hash(tuple(tm[x, y] for y in range(32) for x in range(32)))


def try_edge(pyboy, ref, corner, push_dir, sweep_dir, sweep_len=16, push=4):
    for m in corner:                      # go to the corner of this edge
        walk_direction(pyboy, m, max_tiles=20)
    for _ in range(sweep_len):
        for _ in range(push):             # push outward at this column/row
            press(pyboy, push_dir)
            if full_bg_hash(pyboy) != ref:
                return True
        if walk_direction(pyboy, sweep_dir, max_tiles=1) == 0:
            break                         # reached the far corner
    return False


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)
    ref = full_bg_hash(pyboy)
    pyboy.screen.image.save(OUT / "before.png")
    print(f"in room, pos={P.player_position(pyboy)}")

    left = False
    for corner, push_dir, sweep_dir in EDGES:
        if try_edge(pyboy, ref, corner, push_dir, sweep_dir):
            print(f"LEFT the room via '{push_dir}' edge! new pos={P.player_position(pyboy)}")
            for _ in range(30):           # let the new scene settle
                pyboy.tick()
            pyboy.screen.image.save(OUT / "after.png")
            left = True
            break
        print(f"  no exit on the '{push_dir}' edge")

    if not left:
        print("could not find an exit on any edge")
        pyboy.screen.image.save(OUT / "after.png")
    print("PASS" if left else "FAIL")
    pyboy.stop()


if __name__ == "__main__":
    main()
