"""Intent skills, driven deterministically (no LLM): go_to, interact, explore."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
import agent  # noqa: E402
from agent import skip_intro, skill_go_to, skill_interact, skill_explore  # noqa: E402
from memory import WorldMap  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def _booted():
    pb = PyBoy(ROM, window="null")
    for _ in range(600):
        pb.tick()
    skip_intro(pb)
    return pb


def test_go_to_and_interact():
    pb = _booted()
    world = WorldMap()
    fp = P.scene_fingerprint(pb)
    world.seen_scene(fp, P.player_position(pb))
    world.add_landmark(fp, (6, 13), "")           # the bed, one tile left of spawn

    res, fp2 = skill_go_to(pb, world, fp, "l0")
    print("go_to:", res)
    assert "l0" in res and fp2 == fp              # reached/next to it, same room

    res, _ = skill_interact(pb, world, fp, "l0")
    print("interact:", res)
    assert "Time" in res                          # read the real bed prompt
    pb.stop()


def test_explore_finds_and_leaves():
    pb = _booted()
    world = WorldMap()
    fp = P.scene_fingerprint(pb)
    world.seen_scene(fp, P.player_position(pb))
    rooms, probed = {}, {}

    left = False
    for _ in range(5):
        res, fp = skill_explore(pb, world, rooms, probed, fp)
        print("explore:", res)
        if "new room" in res:
            left = True
            break

    assert world.landmark_count >= 1, "explore should auto-detect at least one object"
    assert left and world.scene_count == 2, "explore should leave the bedroom"
    pb.stop()


def main():
    test_go_to_and_interact()
    test_explore_finds_and_leaves()
    print("PASS")


if __name__ == "__main__":
    main()
