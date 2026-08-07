"""Deterministic: the agent can RETURN through a door it came in (no LLM).

The reverse edge that `note_crossing` guesses (spawn tile + opposite direction)
is unreliable in Deadeus - a door can be one tile off the spawn and the way back
is not always the reverse direction. So `skill_go_to` must fall back to a real
sweep and self-correct the map. This test reproduces the bug on the mother-free
bedroom<->hall door and asserts the agent gets back both times.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro, skill_go_to  # noqa: E402
from navigation import sweep_for_crossing, advance_cutscene  # noqa: E402
from memory import WorldMap  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def _cross(pyboy, world, from_fp):
    """Cross out of `from_fp` exactly like skill_explore, recording the (guessed)
    reverse edge. Returns the new fingerprint."""
    out_dir, door_tile = sweep_for_crossing(pyboy, from_fp)
    assert out_dir is not None, "should have found a door out"
    advance_cutscene(pyboy)
    new_fp = P.scene_fingerprint(pyboy)
    spawn = tuple(v // 8 for v in P.player_position(pyboy))
    world.seen_scene(new_fp, P.player_position(pyboy))
    world.note_crossing(from_fp, out_dir, new_fp, door_tile=door_tile, spawn_tile=spawn)
    return new_fp


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    world = WorldMap()
    fp0 = P.scene_fingerprint(pyboy)
    world.seen_scene(fp0, P.player_position(pyboy))

    fp1 = _cross(pyboy, world, fp0)             # s0 -> s1 (guessed reverse edge now stale)
    assert fp1 != fp0

    _, back = skill_go_to(pyboy, world, fp1, world.scene_id(fp0))
    assert back == fp0, "should have returned to s0"

    # The stale opposite-direction guess must be pruned; only the real edge remains.
    exits = world.exits_detailed(fp1)
    assert exits and all(tid == world.scene_id(fp0) for _, tid, _ in exits), exits
    assert len({d for d, _, _ in exits}) == 1, f"stale guess not pruned: {exits}"

    # And a second round-trip still returns cleanly.
    fp1b = _cross(pyboy, world, fp0)
    assert fp1b == fp1
    _, back2 = skill_go_to(pyboy, world, fp1, world.scene_id(fp0))
    assert back2 == fp0, "second return should also reach s0"

    print(f"returned to s0 twice; s1 exits = {world.exits_detailed(fp1)}")
    print("PASS")
    pyboy.stop()


if __name__ == "__main__":
    main()
