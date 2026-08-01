"""Test the tilemap screen-state detector and use it to auto-advance dialog.

Steps:
  1. Report state at the title screen (expect dialog_open=False).
  2. Enter the opening dialog and report (expect dialog_open=True).
  3. Press A while a dialog box is detected - tolerating short gaps between
     boxes during the cutscene - to see how far the detector drives us and
     where we end up. Screenshots saved at checkpoints.
"""

from pathlib import Path

from pyboy import PyBoy

from perception import screen_state, dialog_open

ROM = "roms/Deadeus.gb"
OUT = Path("runs/screen_state")
GAP_TOLERANCE = 30   # consecutive non-dialog frames before we assume intro over
MAX_PRESSES = 600


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

    print("1) After boot (title)      :", screen_state(pyboy))
    pyboy.screen.image.save(OUT / "01_title.png")

    press(pyboy, "start")
    press(pyboy, "start")
    for _ in range(20):
        press(pyboy, "a")
    print("2) After entering intro    :", screen_state(pyboy))
    pyboy.screen.image.save(OUT / "02_intro.png")

    # 3) Auto-advance: keep pressing A while dialog is up; bridge short gaps.
    presses = 0
    no_dialog_streak = 0
    while presses < MAX_PRESSES:
        if dialog_open(pyboy):
            no_dialog_streak = 0
        else:
            no_dialog_streak += 1
            if no_dialog_streak >= GAP_TOLERANCE:
                break
        press(pyboy, "a")
        presses += 1
        if presses % 50 == 0:
            pyboy.screen.image.save(OUT / f"03_advancing_{presses:03d}.png")

    print(f"3) Stopped after {presses} A-presses (no-dialog streak "
          f"{no_dialog_streak}). Final:", screen_state(pyboy))
    pyboy.screen.image.save(OUT / "04_final.png")
    pyboy.stop()
    print(f"\nScreenshots in {OUT}/")


if __name__ == "__main__":
    main()
