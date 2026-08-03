"""Planner/controller agent.

The LLM decides WHERE to go next (a high-level judgement call); deterministic
code (navigation.walk_*) does the reliable tile-by-tile moving. This replaces the
earlier tile-by-tile LLM navigation, which small models handled unreliably - the
A/B test showed both 3B models mis-stepping and getting stuck (see the README
design log). The planner is intentionally simple for now (open exploration); it
is the seam where a real goal + memory will plug in later.
"""

import json
from pathlib import Path

import ollama
from pyboy import PyBoy

from perception import player_position, dialog_open, visible_dialog_text
from navigation import press, walk_direction

ROM = "roms/Deadeus.gb"
MODEL = "llama3.2:3b"
DIRECTIONS = ["up", "down", "left", "right"]
ROUNDS = 8
OUT = Path("runs/explore")

PLAN_SYSTEM = (
    "You explore a room in a Game Boy game, one move at a time. Each turn you "
    "choose ONE direction to walk next. You are given your (x, y) position and "
    "the directions you most recently walked; prefer a direction you did not "
    'just try. Respond ONLY as JSON: {"direction": "<up|down|left|right>"}'
)


def _reversible_move(pyboy, fwd, back):
    """True if pressing fwd changes the player position and back returns it -
    i.e. real player control, not a cutscene animation."""
    p0 = player_position(pyboy)
    press(pyboy, fwd)
    p1 = player_position(pyboy)
    press(pyboy, back)
    return p1 != p0 and player_position(pyboy) == p0


def skip_intro(pyboy, max_steps=600):
    """Deterministic: click through the title + intro into the movable game.

    Press A while a dialog is on-screen; detect arrival with a reversible
    movement test. Movement tests start only after the title menu, so a direction
    never nudges a menu cursor. Returns the step it arrived on, or None.
    """
    press(pyboy, "start")
    streak = 0
    for step in range(1, max_steps + 1):
        if dialog_open(pyboy):
            streak = 0
            press(pyboy, "a")
        else:
            streak += 1
            if step > 20 and streak >= 3 and (
                _reversible_move(pyboy, "right", "left")
                or _reversible_move(pyboy, "down", "up")
            ):
                return step
            press(pyboy, "a")
    return None


def plan_direction(pyboy, x, y, recent):
    """Planner (LLM): choose a direction to explore. Returns a valid direction
    or None if the model didn't produce one."""
    state = (f"You are at (x={x}, y={y}). Recently walked: "
             f"{', '.join(recent) if recent else 'nothing yet'}.")
    resp = ollama.chat(
        model=MODEL,
        messages=[{"role": "system", "content": PLAN_SYSTEM},
                  {"role": "user", "content": state}],
        format="json",
    )
    try:
        d = str(json.loads(resp["message"]["content"]).get("direction", "")).lower()
    except (json.JSONDecodeError, AttributeError):
        d = ""
    return d if d in DIRECTIONS else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    print(f"skip_intro: reached the game at step {skip_intro(pyboy)}")

    recent = []
    for r in range(1, ROUNDS + 1):
        # If a dialog interrupts, read it and advance - deterministic.
        if dialog_open(pyboy):
            text = visible_dialog_text(pyboy).replace("\n", " / ")
            print(f"[{r:02d}] dialog: {text!r} -> A")
            press(pyboy, "a")
            continue

        x, y = player_position(pyboy)
        d = plan_direction(pyboy, x, y, recent[-3:])
        if d is None:                       # planner failed -> pick an untried dir
            d = next((c for c in DIRECTIONS if c not in recent[-2:]), "up")
            note = " (fallback)"
        else:
            note = ""
        moved = walk_direction(pyboy, d, max_tiles=12)   # controller: reliable
        recent.append(d)
        nx, ny = player_position(pyboy)
        pyboy.screen.image.save(OUT / f"round_{r:02d}_{d}.png")
        print(f"[{r:02d}] at ({x:3d},{y:3d}) plan={d:5s}{note} "
              f"walked {moved:2d} tiles -> ({nx:3d},{ny:3d})")

    pyboy.stop()
    print(f"\nScreenshots in {OUT}/")


if __name__ == "__main__":
    main()
