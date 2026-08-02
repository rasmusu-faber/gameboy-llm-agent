"""Phase C check: perception.read_text() decodes a real dialog, model-free."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402

ROM = str(pathlib.Path(__file__).resolve().parents[1] / "roms" / "Deadeus.gb")


def press(pyboy, button, hold=6, wait=20):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")
    for _ in range(58):          # reach the "I have given you / all this gift of" line
        press(pyboy, "a")

    print("screen_state:", P.screen_state(pyboy))
    print("\nread_text():")
    print(P.read_text(pyboy))

    txt = P.visible_dialog_text(pyboy)
    ok = "I have given you" in txt and "all this gift of" in txt
    print("\nExpected 'I have given you' + 'all this gift of':", "PASS" if ok else "FAIL")
    pyboy.stop()


if __name__ == "__main__":
    main()
