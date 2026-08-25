"""Deterministic (savestate fixture): the agent can cross OUT of Urizen Falls back
to the town (issue #10).

Urizen Falls is an open outdoor screen reached by the LEFT exit of the town; the
way back is RIGHT (measured raw: up/down are walls, left goes deeper, right teleports
to the town). Two ways the map can hold that edge, both must reach the town:
  - the CORRECT edge (falls--right-->town): the fast door path presses right and crosses.
  - a WRONG guessed edge (falls--up-->town, as note_crossing would guess from a
    'down' entry): the fast path bumps the wall, then the in-place directional probe
    (_cross_by_sweep -> probe_for_crossing) finds the real right exit anyway.

The old sweep aborted at the first bare fingerprint change and, on this multi-exit
screen, walked off the wrong exit while seeking a corner -> "didn't cross".

Local-only: needs runs/falls_state/screen_<falls>.state (git-ignored, like the day
states). Regenerate by walking town->left into the falls in scratchpad/play.py, which
auto-saves a state per screen. SKIPs cleanly if the fixture is absent.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skill_go_to  # noqa: E402
from memory import WorldMap, fp_key  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")
FALLS_HEX = "dea6a062ec3ae7ea"
TOWN_HEX = "78e83e32b063d8cf"
STATE = ROOT / "runs" / "falls_state" / f"screen_{FALLS_HEX}.state"


def _reach_town(edge_dir, door):
    """Load the falls, seed one falls->town edge, return whether go_to reaches town."""
    pyboy = PyBoy(ROM, window="null")
    with open(STATE, "rb") as f:
        pyboy.load_state(f)
    for _ in range(10):
        pyboy.tick()

    falls_fp = P.scene_fingerprint(pyboy)
    assert fp_key(falls_fp) == FALLS_HEX, f"fixture is not the falls: {fp_key(falls_fp)}"

    world = WorldMap()
    town_fp = int(TOWN_HEX, 16)
    world.seen_scene(town_fp, (2, 17))
    world.seen_scene(falls_fp, P.player_position(pyboy))
    town_id = world.scene_id(town_fp)
    world.connect(falls_fp, edge_dir, town_fp, door)

    _msg, cur = skill_go_to(pyboy, world, falls_fp, town_id)
    landed = world.scene_id(cur)
    pyboy.stop(save=False)
    return landed == town_id, _msg


def main():
    if not STATE.exists():
        print(f"SKIP: fixture {STATE} not present (local-only, git-ignored)")
        return

    ok_right, m1 = _reach_town("right", (18, 17))     # correct edge -> fast path
    assert ok_right, f"correct-edge case did not reach the town: {m1!r}"

    ok_up, m2 = _reach_town("up", (19, 16))           # wrong guess -> probe recovers
    assert ok_up, f"wrong-edge case did not reach the town: {m2!r}"

    print(f"reached town both ways (correct edge: {m1!r}; wrong-guess recovery: {m2!r})")
    print("PASS")


if __name__ == "__main__":
    main()
