"""Probe: can we read on-screen text WITHOUT an LLM, straight from the tilemap?

The Game Boy draws text as background/window tiles. PyBoy exposes those tile
indices. This dumps the visible 20x18 tile grid (both background and window)
while a dialog box is on screen, plus a screenshot, so we can correlate tile
indices with the readable letters and derive the font mapping.
"""

from pathlib import Path

from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
OUT = Path("runs/tilemap")
A_PRESSES = 56  # roughly reaches an intro dialog line


def press(pyboy, button, hold=6, wait=20):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def dump_grid(tilemap, label):
    print(f"\n=== {label} (20x18 tile indices) ===")
    for y in range(18):
        row = [f"{tilemap[x, y]:3d}" for x in range(20)]
        print(f"{y:2d}| " + " ".join(row))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")
    press(pyboy, "start")
    for _ in range(A_PRESSES):
        press(pyboy, "a")

    pyboy.screen.image.save(OUT / "dump.png")
    dump_grid(pyboy.tilemap_background, "BACKGROUND")
    dump_grid(pyboy.tilemap_window, "WINDOW")
    pyboy.stop()
    print(f"\nScreenshot saved to {OUT / 'dump.png'}")


if __name__ == "__main__":
    main()
