"""Probe: how many inputs does it take to get from boot through the Deadeus
intro/title/opening cutscene into a movable state? Presses A repeatedly and
saves a screenshot every few presses so we can eyeball where gameplay begins.
"""

from pathlib import Path

from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
OUT = Path("runs/reach")
TOTAL_A = 60
EVERY = 4


def press(pyboy, button, hold=6, wait=20):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")
    press(pyboy, "start")
    pyboy.screen.image.save(OUT / "a_000.png")

    for i in range(1, TOTAL_A + 1):
        press(pyboy, "a")
        if i % EVERY == 0:
            pyboy.screen.image.save(OUT / f"a_{i:03d}.png")

    pyboy.stop()
    print(f"OK - saved {TOTAL_A // EVERY + 1} screenshots along the intro to {OUT}/")


if __name__ == "__main__":
    main()
