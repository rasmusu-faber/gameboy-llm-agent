"""Diagnostic: read the window position registers (WY=0xFF4A, WX=0xFF4B) in a
state WITH a visible dialog vs. in the room (box parked off-screen). This tells
us the real signal for "dialog visible".
"""

from pyboy import PyBoy

ROM = "roms/Deadeus.gb"
WY, WX = 0xFF4A, 0xFF4B


def press(pyboy, button, hold=6, wait=20):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def report(pyboy, label):
    print(f"{label:28s} WY=0x{pyboy.memory[WY]:02X} ({pyboy.memory[WY]:3d})  "
          f"WX=0x{pyboy.memory[WX]:02X} ({pyboy.memory[WX]:3d})")


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")
    press(pyboy, "start")
    for _ in range(20):
        press(pyboy, "a")
    report(pyboy, "intro dialog (box visible)")

    for _ in range(260):
        press(pyboy, "a")
    report(pyboy, "room (box parked/hidden)")
    pyboy.stop()


if __name__ == "__main__":
    main()
