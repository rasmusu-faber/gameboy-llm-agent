"""Test 3: the "brain". Proves that Python -> Ollama works and the model
returns a valid action in a fixed JSON format. No game yet - just a made-up
situation as text.
"""

import json
import ollama

MODEL = "llama3.2:3b"
VALID_ACTIONS = ["up", "down", "left", "right", "a", "b", "start", "select"]

SYSTEM = (
    "You control a character in a Game Boy RPG. "
    "You are given the game state as text and choose EXACTLY ONE action. "
    f"Allowed actions: {', '.join(VALID_ACTIONS)}. "
    "Respond ONLY with JSON in exactly this format: "
    '{"action": "<one allowed action>", "reasoning": "<short reason>"}'
)

STATE = (
    "You are standing at the bottom edge of a room. The exit is a door at the "
    "top center. The path ahead (upward) is clear."
)


def choose_action(state_text: str) -> dict:
    resp = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": state_text},
        ],
        format="json",  # Ollama enforces valid JSON
    )
    return json.loads(resp["message"]["content"])


if __name__ == "__main__":
    decision = choose_action(STATE)
    action = decision.get("action")
    print("Model response:", decision)
    if action in VALID_ACTIONS:
        print(f"OK - valid action: {action}")
    else:
        print(f"PROBLEM - invalid action: {action}")
