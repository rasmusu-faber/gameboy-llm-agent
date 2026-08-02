"""RAM scanner (v2): reach a movable state first, verify the character really
moves, then locate the player's X and Y position bytes by diffing work RAM.

Pipeline:
  1. Scripted intro preamble (~300 A-presses) to reach the starting room.
  2. Verify movement: pressing a direction must visibly change the screen.
  3. Memory-scan: move one way, diff RAM, move back, keep bytes that rose then
     fell and returned close to base (a position byte's signature).
No LLM involved.
"""

from pathlib import Path

import numpy as np
from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
WRAM_START = 0xC000
WRAM_END = 0xE000  # exclusive (8 KB work RAM)
INTRO_A = 300      # A-presses to clear the opening into the room
MOVE = 8           # button presses per direction while scanning
OUT = Path("runs/ram_scan")


def press(pyboy, button, times=1, hold=6, wait=16):
    for _ in range(times):
        pyboy.button_press(button)
        for _ in range(hold):
            pyboy.tick()
        pyboy.button_release(button)
        for _ in range(wait):
            pyboy.tick()


def snapshot(pyboy):
    return bytes(pyboy.memory[WRAM_START:WRAM_END])


def screen_arr(pyboy):
    return np.array(pyboy.screen.ndarray, copy=True).astype(int)


def screen_delta(a, b):
    return int(np.abs(a - b).sum())


def find_axis(base, forward, back):
    """Bytes that rose on the forward move, fell on the way back, and returned
    close to the starting value - the signature of a position coordinate."""
    hits = []
    for i in range(len(base)):
        b, f, k = base[i], forward[i], back[i]
        if f > b and k < f and abs(k - b) <= 3:
            hits.append((WRAM_START + i, b, f, k))
    return hits


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start", times=2)
    press(pyboy, "a", times=INTRO_A)
    pyboy.screen.image.save(OUT / "room.png")

    # --- X axis: right then back left (with screen-change check) ---
    base = snapshot(pyboy)
    img0 = screen_arr(pyboy)
    press(pyboy, "right", times=MOVE)
    right = snapshot(pyboy)
    img_r = screen_arr(pyboy)
    press(pyboy, "left", times=MOVE)
    left = snapshot(pyboy)
    x_hits = find_axis(base, right, left)
    x_moved = screen_delta(img0, img_r)

    # --- Y axis: down then back up ---
    base2 = snapshot(pyboy)
    img1 = screen_arr(pyboy)
    press(pyboy, "down", times=MOVE)
    down = snapshot(pyboy)
    img_d = screen_arr(pyboy)
    press(pyboy, "up", times=MOVE)
    up = snapshot(pyboy)
    y_hits = find_axis(base2, down, up)
    y_moved = screen_delta(img1, img_d)

    pyboy.screen.image.save(OUT / "after_scan.png")
    pyboy.stop()

    print(f"Screen change on RIGHT: {x_moved}   on DOWN: {y_moved}   "
          f"(0 = nothing moved -> still blocked/in dialog)")
    print(f"\nX candidates ({len(x_hits)})  addr: base -> right -> left")
    for addr, b, f, k in x_hits[:30]:
        print(f"  0x{addr:04X}: {b:3d} -> {f:3d} -> {k:3d}")
    print(f"\nY candidates ({len(y_hits)})  addr: base -> down -> up")
    for addr, b, f, k in y_hits[:30]:
        print(f"  0x{addr:04X}: {b:3d} -> {f:3d} -> {k:3d}")


if __name__ == "__main__":
    main()
