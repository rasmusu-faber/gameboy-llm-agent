"""Deterministic: perception.game_day reads the in-game day model-free (no LLM).

Guards the day byte (0xC60F) against a regression to the debunked 0xC4A7. The key
property a day byte must have - and 0xC4A7 lacked - is scene-independence: it reads
the same in every scene of a given day. So on day 1 it must be 1 in BOTH the
bedroom and the hallway. (Advancing to day 2/3 needs sleeping, exercised
separately in the exploration harness; here we keep it fast.)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro, build_state  # noqa: E402
from memory import WorldMap  # noqa: E402
from navigation import sweep_for_crossing, advance_cutscene  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    day_bed = P.game_day(pyboy)
    assert day_bed == 1, f"fresh game should be day 1, got {day_bed}"

    # The day must be surfaced to the LLM in build_state (day-awareness).
    fp0 = P.scene_fingerprint(pyboy)
    world = WorldMap()
    world.seen_scene(fp0, P.player_position(pyboy))
    state = build_state(world, {}, fp0, pyboy, [], "")
    assert "day 1 of 3" in state, f"build_state should surface the day, got:\n{state}"

    fp = P.scene_fingerprint(pyboy)              # cross into the hallway
    assert sweep_for_crossing(pyboy, fp)[0] is not None
    advance_cutscene(pyboy)
    day_hall = P.game_day(pyboy)
    assert day_hall == 1, f"still day 1 in the hallway, got {day_hall}"

    print(f"day in bedroom={day_bed}, in hallway={day_hall} (scene-independent)")
    print("PASS")
    pyboy.stop(save=False)                        # never overwrite the user's .ram


if __name__ == "__main__":
    main()
