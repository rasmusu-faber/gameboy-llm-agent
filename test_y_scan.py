"""Focused Y scan: look only at the low-WRAM neighborhood (0xC000-0xC0BF, where
player X = 0xC009 lives) and find the byte that tracks VERTICAL movement cleanly
and does NOT react to horizontal movement - the player's Y coordinate.

Prints, for every byte that moved during the down phase, its full per-press
sequence (baseline -> 6x down -> 6x up), and flags any that also react to
horizontal movement (those are not Y).
"""

from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
INTRO_A = 300
STEPS = 6
RANGE = range(0xC000, 0xC0C0)


def press(pyboy, button, times=1, hold=6, wait=16):
    for _ in range(times):
        pyboy.button_press(button)
        for _ in range(hold):
            pyboy.tick()
        pyboy.button_release(button)
        for _ in range(wait):
            pyboy.tick()


def read(pyboy):
    return {a: pyboy.memory[a] for a in RANGE}


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start", times=2)
    press(pyboy, "a", times=INTRO_A)

    base = read(pyboy)
    down_rows = []
    for _ in range(STEPS):
        press(pyboy, "down")
        down_rows.append(read(pyboy))
    up_rows = []
    for _ in range(STEPS):
        press(pyboy, "up")
        up_rows.append(read(pyboy))

    # Which bytes moved at all during the down phase?
    cands = [a for a in RANGE if any(down_rows[i][a] != base[a] for i in range(STEPS))]

    # Horizontal reactivity check (a real Y must ignore this)
    hbase = read(pyboy)
    press(pyboy, "right", times=4)
    hafter = read(pyboy)
    press(pyboy, "left", times=4)
    x_reactive = {a for a in cands if hafter[a] != hbase[a]}

    print(f"Candidates in 0xC000-0xC0BF that moved on 'down': {len(cands)}\n")
    for a in cands:
        d = " ".join(f"{down_rows[i][a]:3d}" for i in range(STEPS))
        u = " ".join(f"{up_rows[i][a]:3d}" for i in range(STEPS))
        tag = "   <-- also reacts to X (NOT Y)" if a in x_reactive else "   <-- vertical-only"
        print(f"0x{a:04X}: base {base[a]:3d} | down {d} | up {u}{tag}")


if __name__ == "__main__":
    main()
