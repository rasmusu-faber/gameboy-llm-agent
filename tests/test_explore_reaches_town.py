"""Deterministic (no LLM): explore-to-completion breaks out of the house.

Regression for the "2-room local optimum": a single explore pass (or explores
interrupted by other intents) never reached the living room's bottom door, so the
agent oscillated between the bedroom and the living room forever. explore_to_
completion loops the deterministic pass until the room is fully mapped or a new
room appears - which reliably discovers that far exit. This test proves the agent
gets from the bedroom (s0), through the living room (s1), to a THIRD scene: the
town outside. No LLM involved, so it is stable.
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

    # Explore the bedroom to completion -> it discovers the living room (s1).
    _res, cur = explore_to_completion(pyboy, world, rooms, probed, cur)
    assert world.scene_count >= 2, "explore should discover the living room (s1)"

    # Move into the living room (explore may have already ended there).
    if world.scene_id(cur) != "s1":
        _res, cur = skill_go_to(pyboy, world, cur, "s1")
    assert world.scene_id(cur) == "s1", f"expected to be in s1, got {world.scene_id(cur)}"

    # Explore the living room to completion -> it must reach a THIRD scene (the
    # town), which is exactly what the old single-pass explore failed to do.
    before = world.scene_count
    _res, cur = explore_to_completion(pyboy, world, rooms, probed, cur)
    assert world.scene_count > before, (
        "explore of the living room should discover a further room (the town); "
        f"scenes={world.scene_count}, s1 exits={world.exits_detailed(P.scene_fingerprint(pyboy))}")

    # The living room now has an exit to a scene that is neither itself nor s0.
    s1_targets = {tid for _d, tid, _door in world.exits_detailed(cur)} if world.scene_id(cur) == "s1" else set()
    print(f"reached {world.scene_count} scenes; s1 exits -> {sorted(s1_targets)}")
    print("PASS")
    pyboy.stop(save=False)


if __name__ == "__main__":
    main()
