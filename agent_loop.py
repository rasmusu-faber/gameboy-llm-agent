"""First real agent loop: eye + hand + brain wired together.

Per step:
  1. Build the state as text (goal + recent actions = mini memory)
  2. LLM picks EXACTLY ONE valid action (JSON)
  3. Execute the action in the emulator
  4. Write a screenshot to runs/, log the decision

NOTE: The "eye" is still a placeholder here. Deadeus has no documented RAM map,
so the model does not yet receive real screen content - only goal and history.
This proves the wiring; real perception comes with the Pokemon RAM hookup.
"""

import json
from pathlib import Path

import ollama
from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
MODEL = "llama3.2:3b"
STEPS = 10
RUN_DIR = Path("runs/run_01")

VALID_ACTIONS = ["up", "down", "left", "right", "a", "b", "start", "select"]
GOAL = "Get through the title/intro screens into the game, then explore the surroundings."

SYSTEM = (
    "You control a character in a Game Boy RPG. "
    f"Allowed actions: {', '.join(VALID_ACTIONS)}. "
    "Choose EXACTLY ONE action that serves the goal. Do not repeat yourself blindly. "
    "Respond ONLY with JSON: "
    '{"action": "<action>", "reasoning": "<short>"}'
)


def press(pyboy, button, hold=6, wait=10):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def build_state_text(step, history):
    last = ", ".join(history[-5:]) if history else "(none yet)"
    return f"Goal: {GOAL}\nStep: {step}/{STEPS}\nYour recent actions: {last}"


def choose_action(state_text):
    resp = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": state_text},
        ],
        format="json",
    )
    return json.loads(resp["message"]["content"])


def main():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):  # wait for boot
        pyboy.tick()

    history = []
    for step in range(1, STEPS + 1):
        state_text = build_state_text(step, history)
        decision = choose_action(state_text)
        action = decision.get("action")

        if action not in VALID_ACTIONS:
            print(f"[{step:02d}] invalid ({action}) -> fallback 'a'")
            action = "a"

        press(pyboy, action)
        history.append(action)
        pyboy.screen.image.save(RUN_DIR / f"step_{step:02d}_{action}.png")
        print(f"[{step:02d}] {action:6s} | {decision.get('reasoning', '')[:70]}")

    pyboy.stop()
    print(f"\nOK - ran {STEPS} steps, screenshots in {RUN_DIR}/")
    print("Action history:", " -> ".join(history))


if __name__ == "__main__":
    main()
