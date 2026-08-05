"""interact(): facing a tile + pressing A reads a real interaction (no LLM).

At the bedroom start the boy stands by the bed; interacting with it triggers the
"Time for bed?..." prompt (sleeping ends the day - a core Deadeus mechanic). This
proves the mechanic reads genuine object text model-free and doesn't move the
player. (Discovered here: pressing A near spawn is the bed interaction, not an
empty wall - the earlier assumption was wrong.)
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro  # noqa: E402
from navigation import interact  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    # Bedroom start is (56, 104); the bed is to the left. Interact with it.
    before = P.player_position(pyboy)
    text = interact(pyboy, "left")
    after = P.player_position(pyboy)

    print(f"interact(left) at {before}: text={text!r}, now at {after}")
    assert "Time" in text, f"expected the bed prompt ('Time for bed?...'), got {text!r}"
    assert after == before, "interacting must not move the player"
    print("PASS")
    pyboy.stop()


if __name__ == "__main__":
    main()
