"""Test 4: the real "eye". Proves a vision model can look at the actual game
screen and describe it. Boots, advances into the game, saves a screenshot,
then asks moondream what it sees. No decision yet - just perception.
"""

import ollama
from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
VISION_MODEL = "moondream"
SHOT = "vision_test.png"


def press(pyboy, button, hold=6, wait=10):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


# Boot and advance past the intro so there is something to look at
pyboy = PyBoy(ROM, window="null")
for _ in range(600):
    pyboy.tick()
for _ in range(8):
    press(pyboy, "start")
    press(pyboy, "a")
pyboy.screen.image.save(SHOT)
pyboy.stop()

# Ask the vision model to describe the screenshot
resp = ollama.chat(
    model=VISION_MODEL,
    messages=[{
        "role": "user",
        "content": "This is a Game Boy screen. Describe what you see in one or two sentences.",
        "images": [SHOT],
    }],
)
print("Screenshot saved to:", SHOT)
print("Vision model says:", resp["message"]["content"].strip())
