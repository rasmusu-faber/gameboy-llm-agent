"""Deterministic: navigation.search_for_exit finds the bedroom door (no LLM).

This is the reflex behind the planner's 'find_exit' action - it must reliably
locate the top-edge door and cross into the next scene.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro  # noqa: E402
from navigation import search_for_exit  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    ref = P.scene_fingerprint(pyboy)
    edge_dir = search_for_exit(pyboy, ref)

    assert edge_dir is not None, "search_for_exit should find the bedroom door"
    assert P.scene_fingerprint(pyboy) != ref, "scene should have changed"
    print(f"left via '{edge_dir}' edge -> pos={P.player_position(pyboy)}")
    print("PASS")
    pyboy.stop()


if __name__ == "__main__":
    main()
