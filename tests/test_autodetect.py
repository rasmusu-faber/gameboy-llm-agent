"""Auto-detect on bump: bumping the bed records it as a landmark (no LLM).

Mirrors agent.py's bump handling: a blocked move -> interact -> if text, store a
landmark -> dismiss the dialog. Uses the bedroom bed (left of spawn), whose prompt
is safe to dismiss here (verified in the design log).
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro  # noqa: E402
from navigation import walk_direction, interact, dismiss_dialog  # noqa: E402
from memory import WorldMap  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    world = WorldMap()
    fp = P.scene_fingerprint(pyboy)
    world.seen_scene(fp, P.player_position(pyboy))

    ptile = P.player_tile(pyboy)
    moved = walk_direction(pyboy, "left", max_tiles=1)   # bump into the bed
    assert moved == 0, "expected the bed to block leftward movement"

    text = interact(pyboy, "left")
    assert "Time" in text, f"expected the bed prompt, got {text!r}"
    nbr = (ptile[0] - 1, ptile[1])
    lid = world.add_landmark(fp, nbr, text)

    assert dismiss_dialog(pyboy), "dialog should close after dismiss"
    assert not P.dialog_open(pyboy)

    lm = world.landmarks_of(fp)
    print(f"recorded {lid} @ {nbr}: {lm[0]['text']!r}")
    assert len(lm) == 1 and lm[0]["id"] == lid
    print("PASS")
    pyboy.stop()


if __name__ == "__main__":
    main()
