"""Navigation loop with a REAL eye: the agent reads its (x, y) position from
RAM (perception.player_position) and a local LLM chooses moves to reach a target
tile. Fully local, instant, free. First loop driven by real perception.

Success metric: Manhattan distance to the target should shrink over the run.
"""

import json
from pathlib import Path

import ollama
from pyboy import PyBoy

from perception import player_position, dialog_open

ROM = "roms/Deadeus.gb"
MODEL = "llama3.2:3b"
MAX_STEPS = 25
OUT = Path("runs/nav")

VALID = ["up", "down", "left", "right"]

SYSTEM = (
    "You navigate a character on a 2D grid by pressing one button at a time. "
    "Coordinates: x increases to the RIGHT, y increases DOWNWARD. "
    "Controls: 'right' increases x, 'left' decreases x, 'down' increases y, "
    "'up' decreases y. Pick EXACTLY ONE of up/down/left/right to move closer to "
    'the target. Respond ONLY as JSON: {"action": "<up|down|left|right>"}'
)


def press(pyboy, button, times=1, hold=6, wait=16):
    for _ in range(times):
        pyboy.button_press(button)
        for _ in range(hold):
            pyboy.tick()
        pyboy.button_release(button)
        for _ in range(wait):
            pyboy.tick()


def _reversible_move(pyboy, fwd, back):
    """True if pressing fwd changes the player position and back returns it -
    i.e. real player control, not a cutscene animation."""
    p0 = player_position(pyboy)
    press(pyboy, fwd)
    p1 = player_position(pyboy)
    press(pyboy, back)
    return p1 != p0 and player_position(pyboy) == p0


def skip_intro(pyboy, max_steps=600):
    """Autonomously click through the title + intro into the movable game.

    Deterministic (no LLM): press A while a dialog is on-screen, and detect
    arrival with a reversible movement test. Movement tests start only after the
    title menu, so a direction never nudges a menu cursor. Returns the step it
    arrived on, or None if it never became movable.
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


def greedy(dx, dy):
    """Fallback move if the model returns junk: reduce the larger gap."""
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "down" if dy > 0 else "up"


def choose(x, y, tx, ty):
    dx, dy = tx - x, ty - y
    state = (
        f"You are at (x={x}, y={y}). Target is (x={tx}, y={ty}). "
        f"dx={dx} (positive = target is to your right), "
        f"dy={dy} (positive = target is below you). Which single move gets closer?"
    )
    resp = ollama.chat(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": state}],
        format="json",
    )
    try:
        action = str(json.loads(resp["message"]["content"]).get("action", "")).lower()
    except (json.JSONDecodeError, AttributeError):
        action = ""
    if action not in VALID:
        action = greedy(dx, dy)
        return action, True
    return action, False


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    arrived = skip_intro(pyboy)
    print(f"skip_intro: reached the game at step {arrived}")

    x0, y0 = player_position(pyboy)
    # Target: 2 tiles right and 2 tiles up, clamped to the room bounds we found
    tx = min(x0 + 16, 96)
    ty = max(y0 - 16, 64)
    pyboy.screen.image.save(OUT / "start.png")
    print(f"Start (x={x0}, y={y0})  ->  Target (x={tx}, y={ty})")
    start_dist = abs(tx - x0) + abs(ty - y0)

    for step in range(1, MAX_STEPS + 1):
        x, y = player_position(pyboy)
        dist = abs(tx - x) + abs(ty - y)
        if dist == 0:
            print(f"[{step:02d}] reached target at (x={x}, y={y})!")
            break
        action, fb = choose(x, y, tx, ty)
        press(pyboy, action)
        nx, ny = player_position(pyboy)
        tag = " (fallback)" if fb else ""
        print(f"[{step:02d}] at ({x:3d},{y:3d}) dist={dist:3d} -> {action:5s}{tag} "
              f"-> ({nx:3d},{ny:3d})")

    x, y = player_position(pyboy)
    end_dist = abs(tx - x) + abs(ty - y)
    pyboy.screen.image.save(OUT / "end.png")
    pyboy.stop()
    print(f"\nDistance: {start_dist} -> {end_dist}  "
          f"({'reached' if end_dist == 0 else 'closer' if end_dist < start_dist else 'no progress'})")


if __name__ == "__main__":
    main()
