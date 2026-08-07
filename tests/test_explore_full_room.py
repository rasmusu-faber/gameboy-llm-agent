"""Deterministic (no LLM): explore FULLY maps the bedroom before leaving it.

Regression for the bouncing bug (issue #4): explore must not walk out the first
door it meets. Instead it covers the whole room - which is how the bed (a blocked
tile left of the spawn) gets discovered as a landmark WITHOUT seeding it by hand.
So we run explore repeatedly and assert: it stays in s0, it finds the bed, and it
eventually reports the room fully mapped.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro, skill_explore  # noqa: E402
from memory import WorldMap  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    world = WorldMap()
    s0 = P.scene_fingerprint(pyboy)
    world.seen_scene(s0, P.player_position(pyboy))
    rooms, probed = {}, {}

    fully = False
    for _ in range(15):
        summary, cur = skill_explore(pyboy, world, rooms, probed, s0)
        assert cur == s0, f"explore left the bedroom (now {world.scene_id(cur)}): {summary}"
        if "fully mapped" in summary:
            fully = True
            break
    assert fully, "bedroom never reported fully mapped within the call budget"

    # The bed (a blocked tile left of the spawn) must have been discovered by
    # bumping, not seeded: its first-contact text is the "Time for bed?..." prompt.
    beds = [lm for lm in world.landmarks_of(s0) if "Time for bed" in lm["text"]]
    assert beds, f"bed never discovered; s0 landmarks: {world.landmarks_of(s0)}"
    # And it stayed in the bedroom the whole time (crossing is a deliberate go_to).
    assert world.scene_id(P.scene_fingerprint(pyboy)) == "s0"

    print(f"bedroom fully mapped; bed found as {beds[0]['id']} @ {beds[0]['tile']}")
    print(f"s0 landmarks: {len(world.landmarks_of(s0))}, exits: {world.exits_from(s0)}")
    print("PASS")
    pyboy.stop(save=False)


if __name__ == "__main__":
    main()
