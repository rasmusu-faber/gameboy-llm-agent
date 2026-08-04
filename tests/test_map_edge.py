"""End-to-end: crossing a real room boundary records a map edge.

The explore loop's LLM planner is flaky about finding the door, so we drive the
known top-edge exit deterministically (as test_leave_room does) and assert the
Map layer captured the second scene AND the directed edge from real emulator
fingerprints - the live half the unit test can't cover.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro  # noqa: E402
from navigation import press, walk_direction  # noqa: E402
from memory import WorldMap  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    world = WorldMap()
    cur_fp = P.scene_fingerprint(pyboy)
    world.seen_scene(cur_fp, P.player_position(pyboy))
    assert world.scene_count == 1 and world.edge_count == 0

    # Deterministically leave via the top edge: go to the top-left corner, then
    # sweep left->right pushing 'up' until the scene fingerprint flips.
    walk_direction(pyboy, "up", max_tiles=20)
    walk_direction(pyboy, "left", max_tiles=20)
    changed = False
    for _ in range(16):
        for _ in range(4):
            press(pyboy, "up")
            if P.scene_fingerprint(pyboy) != cur_fp:
                changed = True
                break
        if changed or walk_direction(pyboy, "right", max_tiles=1) == 0:
            break

    assert changed, "expected to leave the bedroom via the top edge"

    # This is exactly the agent.py map-wiring: register new scene + directed edge.
    new_fp = P.scene_fingerprint(pyboy)
    world.seen_scene(new_fp, P.player_position(pyboy))
    world.connect(cur_fp, "up", new_fp)

    assert world.scene_count == 2, world.scene_count
    assert world.edge_count == 1, world.edge_count
    print(world.render_block())
    print("PASS")
    pyboy.stop()


if __name__ == "__main__":
    main()
