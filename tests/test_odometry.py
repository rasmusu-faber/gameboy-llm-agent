"""Odometer dead-reckoning, unit-tested with no ROM (pure grid logic)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from odometry import Odometer  # noqa: E402


def main():
    od = Odometer()
    assert od.coord == (0, 0)

    # One crossing per direction (y grows downward: up is -y).
    assert od.step("down") == (0, 1)
    assert od.step("right") == (1, 1)
    assert od.step("up") == (1, 0)
    assert od.step("left") == (0, 0)          # back to the start cell

    # Opposite crossings cancel (the core Euclidean property this relies on).
    Odometer().step("up")  # smoke
    od2 = Odometer()
    od2.step("up")
    od2.step("down")
    assert od2.coord == (0, 0)

    # A full loop returns to the start.
    od3 = Odometer((2, 5))
    for d in ("right", "right", "down", "left", "left", "up"):
        od3.step(d)
    assert od3.coord == (2, 5), od3.coord

    # Unknown / empty direction is a no-op, never corrupts the coordinate.
    od4 = Odometer((3, 4))
    assert od4.step("") == (3, 4)
    assert od4.step("nowhere") == (3, 4)

    # set() snaps (loop-closure / house return).
    od5 = Odometer((7, 7))
    od5.step("down")
    assert od5.coord == (7, 8)
    assert od5.set((0, 0)) == (0, 0)
    assert od5.step("right") == (1, 0)        # continues from the snapped cell

    print("PASS")


if __name__ == "__main__":
    main()
