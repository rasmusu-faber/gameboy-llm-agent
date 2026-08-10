"""Deterministic (no LLM): exploring the first town screen records NO self-loop.

Regression for issue #7. At a town edge the background fingerprint briefly flickers
and the player shifts a tile while STAYING on the same screen; the crossing detector
plus is_crossing_move were fooled into recording s2 --dir--> s2 (a self-loop) that
broke go_to navigation. A crossing must land on a DIFFERENT fingerprint - this drives
to the town and asserts the first town screen has no edge back to itself.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro, explore_to_completion, skill_go_to  # noqa: E402
from memory import WorldMap  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    world = WorldMap()
    cur = P.scene_fingerprint(pyboy)
    world.seen_scene(cur, P.player_position(pyboy))
    rooms, probed = {}, {}

    # bedroom (s0) -> living room (s1) -> town (s2)
    _r, cur = explore_to_completion(pyboy, world, rooms, probed, cur)
    if world.scene_id(cur) != "s1":
        _r, cur = skill_go_to(pyboy, world, cur, "s1")
    _r, cur = explore_to_completion(pyboy, world, rooms, probed, cur)   # reaches s2
    if world.scene_id(cur) != "s2":
        _r, cur = skill_go_to(pyboy, world, cur, "s2")
    assert world.scene_id(cur) == "s2", f"expected to reach the town s2, in {world.scene_id(cur)}"

    town_fp, town_id = cur, world.scene_id(cur)

    # explore the town a few passes (this is where the self-loops used to appear)
    for _ in range(4):
        _r, cur = explore_to_completion(pyboy, world, rooms, probed, cur)
        if world.scene_id(cur) != town_id:
            _r, cur = skill_go_to(pyboy, world, cur, town_id)

    exits = world.exits_detailed(town_fp)
    selfloops = [(d, tid) for d, tid, _ in exits if tid == town_id]
    assert not selfloops, f"town screen {town_id} has self-loops: {selfloops} (all exits: {exits})"

    print(f"town {town_id} exits (no self-loops): {[(d, tid) for d, tid, _ in exits]}")
    print("PASS")
    pyboy.stop(save=False)


if __name__ == "__main__":
    main()
