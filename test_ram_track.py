"""Live tracking: watch a shortlist of candidate bytes change one press at a
time. The true player X/Y coordinate rises smoothly and consistently with each
step in its axis, returns on the way back, and does NOT react to the other axis.
Everything else jitters.
"""

from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
INTRO_A = 300
STEPS = 6

X_CANDS = [0xC009, 0xC00D, 0xC0B7, 0xC00A, 0xC00E]
Y_CANDS = [0xDFA5, 0xDFA6, 0xDFA7, 0xDFC4]
ALL = X_CANDS + Y_CANDS


def press(pyboy, button, times=1, hold=6, wait=16):
    for _ in range(times):
        pyboy.button_press(button)
        for _ in range(hold):
            pyboy.tick()
        pyboy.button_release(button)
        for _ in range(wait):
            pyboy.tick()


def row(pyboy, label):
    vals = "  ".join(f"{pyboy.memory[a]:3d}" for a in ALL)
    print(f"{label:12s} | {vals}")


def phase(pyboy, button):
    for i in range(1, STEPS + 1):
        press(pyboy, button)
        row(pyboy, f"{button} #{i}")


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start", times=2)
    press(pyboy, "a", times=INTRO_A)

    header = "  ".join(f"{a:04X}" for a in ALL)
    print(f"{'':12s} | {header}")
    print(f"{'(X cands)':12s} | " + "  ".join("X" if a in X_CANDS else " " for a in ALL))
    row(pyboy, "start")
    phase(pyboy, "right")
    phase(pyboy, "left")
    phase(pyboy, "down")
    phase(pyboy, "up")
    pyboy.stop()


if __name__ == "__main__":
    main()
