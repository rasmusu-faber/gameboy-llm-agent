"""Test 2: the "hand". Proves we can press buttons from code.
Boots, takes a screenshot BEFORE input, presses Start/A a few times, takes a
screenshot AFTER. If the image changes, the input got through.
"""

from pyboy import PyBoy

ROM = "roms/Deadeus.gb"


def press(pyboy, button, hold=6, wait=10):
    """Press, hold and release a button, then wait briefly (for animations)."""
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


pyboy = PyBoy(ROM, window="null")

# Wait for boot and capture the state BEFORE input
for _ in range(600):
    pyboy.tick()
pyboy.screen.image.save("before.png")

# Confirm a few times to get through the warning/title into the game
for _ in range(8):
    press(pyboy, "start")
    press(pyboy, "a")

pyboy.screen.image.save("after.png")
pyboy.stop()
print("OK - before.png and after.png written")
