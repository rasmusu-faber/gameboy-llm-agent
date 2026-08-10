"""is_crossing_move(): tell a real screen crossing from a scroll-tick (issue #7,
Baustein 1), unit-tested with no ROM. Positions are in pixels; a tile is 8 px."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from crossing import is_crossing_move  # noqa: E402


def main():
    # Scroll-tick: walked one tile in `direction`, landed where a normal step lands
    # -> NOT a crossing (this is what used to invent a node per tile).
    assert not is_crossing_move((80, 64), (88, 64), "right")
    assert not is_crossing_move((80, 64), (80, 72), "down")
    assert not is_crossing_move((80, 64), (72, 64), "left")
    assert not is_crossing_move((80, 64), (80, 56), "up")

    # A slightly noisy scroll-tick (sub-tile settling) is still within slack.
    assert not is_crossing_move((80, 64), (90, 66), "right")

    # Edge crossing: walked into the edge, wrapped to the far side -> a crossing.
    assert is_crossing_move((152, 64), (16, 64), "right")
    assert is_crossing_move((64, 0), (64, 136), "up")
    assert is_crossing_move((0, 64), (144, 64), "left")

    # Door crossing: teleported to a spawn far from the expected step -> a crossing.
    assert is_crossing_move((56, 16), (112, 56), "up")

    # An unknown direction has no expected step; any real displacement reads as a
    # crossing (defensive - callers pass a real direction).
    assert is_crossing_move((10, 10), (120, 120), "")

    print("PASS")


if __name__ == "__main__":
    main()
