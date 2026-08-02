"""Agent loop, vision variant (approach 1): a single vision-language model
(moondream) both SEES the screen and DECIDES the next action in one call.

Per step:
  1. Screenshot the current screen
  2. moondream looks at it and returns ONE action as JSON
  3. Execute the action, save a screenshot, log it

This collapses "eye" and "brain" into one model. Simple and RAM-friendly, but
the small model is weak at strict formatting and planning - this run is meant to
show honestly how far a tiny local VLM gets before we consider cloud vision.
"""

import json
from pathlib import Path

import ollama
from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
MODEL = "moondream"
STEPS = 12
RUN_DIR = Path("runs/run_vision_01")
SHOT = RUN_DIR / "_current.png"

VALID_ACTIONS = ["up", "down", "left", "right", "a", "b", "start"]

PROMPT = (
    "You are playing a Game Boy game. Look at the screen. "
    "Choose ONE button to press to make progress or explore. "
    f"Valid buttons: {', '.join(VALID_ACTIONS)}. "
    'Answer ONLY as JSON: {"action": "<button>"}'
)


def press(pyboy, button, hold=6, wait=10):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def choose_action_vision(pyboy):
    """Ask the vision model for one action based on the current screen.

    Returns (action, raw_response). action is "" if nothing usable was parsed.
    """
    pyboy.screen.image.save(SHOT)
    resp = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT, "images": [str(SHOT)]}],
        format="json",
    )
    raw = resp["message"]["content"].strip()

    action = ""
    try:
        action = str(json.loads(raw).get("action", "")).lower()
    except (json.JSONDecodeError, AttributeError):
        pass
    # Fallback: fish any valid action word out of the raw text
    if action not in VALID_ACTIONS:
        for a in VALID_ACTIONS:
            if a in raw.lower():
                action = a
                break
    return action, raw


def main():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):  # boot
        pyboy.tick()
    for _ in range(10):   # skip intro/title screens into the game
        press(pyboy, "start")
        press(pyboy, "a")

    history = []
    for step in range(1, STEPS + 1):
        action, raw = choose_action_vision(pyboy)
        if action not in VALID_ACTIONS:
            action = "a"  # last-resort fallback so the loop keeps moving
            note = f"(fallback, raw={raw[:40]!r})"
        else:
            note = ""
        press(pyboy, action)
        history.append(action)
        pyboy.screen.image.save(RUN_DIR / f"step_{step:02d}_{action}.png")
        print(f"[{step:02d}] {action:6s} {note}")

    pyboy.stop()
    print(f"\nOK - vision loop done, screenshots in {RUN_DIR}/")
    print("Action history:", " -> ".join(history))


if __name__ == "__main__":
    main()
