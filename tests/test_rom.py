"""First smoke test: boot the ROM headless, run a few frames, save a
screenshot. No agent, no logic - just proof that PyBoy + ROM work together.
"""

from pyboy import PyBoy

ROM = "roms/Deadeus.gb"

pyboy = PyBoy(ROM, window="null")  # headless, no window
for _ in range(600):               # run frames (boot + title screen)
    pyboy.tick()
pyboy.screen.image.save("test_frame.png")
pyboy.stop()
print("OK - test_frame.png written")
