"""Diagnostic: dump the window tilemap in the OVERWORLD (no dialog) so we can
compare it to the dialog layout and find a robust dialog signature.
"""

from pathlib import Path

from pyboy import PyBoy

# This probe lives in exploration/; make the repo root importable for perception
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from perception import window_enabled

ROM = "roms/Deadeus.gb"
OUT = Path("runs/window_dump")


def press(pyboy, button, hold=6, wait=20):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def dump(pyboy, label):
    tm = pyboy.tilemap_window
    print(f"\n=== WINDOW in {label} (enabled={window_enabled(pyboy)}) ===")
    for y in range(18):
        print(f"{y:2d}| " + " ".join(f"{tm[x, y]:3d}" for x in range(20)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")
    press(pyboy, "start")
    for _ in range(280):   # click through the intro into the room
        press(pyboy, "a")
    pyboy.screen.image.save(OUT / "overworld.png")
    dump(pyboy, "OVERWORLD")
    pyboy.stop()


if __name__ == "__main__":
    main()
