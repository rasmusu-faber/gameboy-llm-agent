"""Autonomy: let the agent click through the intro into the game by itself,
using perception instead of a hard-coded A-press count.

Strategy:
  - press A whenever a dialog is visible (dialog_open, WY-gated);
  - when no dialog is up, occasionally check "can I actually move?" via a
    REVERSIBLE movement test (right then left returns to start = real player
    control, not animation noise). Movement tests only start after we are safely
    past the title menu, so directions never nudge a menu cursor.
Stops as soon as the player is movable = we are in the game.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402

ROM = str(pathlib.Path(__file__).resolve().parents[1] / "roms" / "Deadeus.gb")
OUT = pathlib.Path(__file__).resolve().parents[1] / "runs" / "auto_intro"
MAX_STEPS = 600


def press(pyboy, button, hold=6, wait=16):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def reversible_move(pyboy, fwd, back):
    """True if pressing fwd changes the player position and back returns it."""
    p0 = P.player_position(pyboy)
    press(pyboy, fwd)
    p1 = P.player_position(pyboy)
    press(pyboy, back)
    p2 = P.player_position(pyboy)
    return p1 != p0 and p2 == p0


def can_move(pyboy):
    return (reversible_move(pyboy, "right", "left")
            or reversible_move(pyboy, "down", "up"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")          # leave the title menu (New Game)

    streak = 0
    arrived_at = None
    for step in range(1, MAX_STEPS + 1):
        if P.dialog_open(pyboy):
            streak = 0
            press(pyboy, "a")
        else:
            streak += 1
            if step > 20 and streak >= 3 and can_move(pyboy):
                arrived_at = step
                break
            press(pyboy, "a")

    pyboy.screen.image.save(OUT / "arrived.png")
    pos = P.player_position(pyboy)
    print(f"arrived_at step: {arrived_at}")
    print(f"player position: {pos}")
    print(f"dialog_open now: {P.dialog_open(pyboy)}")
    print(f"visible dialog text: {P.visible_dialog_text(pyboy)!r}")
    print("PASS" if arrived_at and not P.dialog_open(pyboy) else "FAIL")
    pyboy.stop()


if __name__ == "__main__":
    main()
