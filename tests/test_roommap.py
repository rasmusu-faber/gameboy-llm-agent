"""RoomMap occupancy logic, unit-tested with synthetic moves (no ROM)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from roommap import RoomMap  # noqa: E402


def main():
    rm = RoomMap()

    # Player at (7, 13). Walk right one tile successfully: (7,13)->(8,13).
    rm.observe((7, 13), (8, 13), "right", moved=1)
    # From (8,13) push up but a wall blocks it (0 tiles): (8,12) is a wall.
    rm.observe((8, 13), (8, 13), "up", moved=0)

    adj = rm.adjacent((8, 13))
    assert adj["up"] == "wall", adj
    assert adj["left"] == "floor", adj      # (7,13) was walked
    assert adj["right"] == "unknown", adj   # never seen (9,13)

    grid = rm.render((8, 13), radius=2)
    print(grid)
    # Center row: left neighbour floor '.', player '@', and up-row has a '#'.
    assert "@" in grid and "#" in grid and "." in grid

    # A wall tile later turning out to be floor (stepped onto it) is corrected.
    rm.observe((8, 13), (8, 12), "up", moved=1)   # now we DID move up
    assert rm.adjacent((8, 13))["up"] == "floor"

    # Frontier: from (8,13) up/left are floor, down/right are unexplored -> the
    # nearest unknown is one step down (BFS, up preferred but up is now floor).
    assert rm.nearest_frontier((8, 13)) == "down", rm.nearest_frontier((8, 13))
    # rm still borders unknown tiles -> not fully explored.
    assert rm.has_unexplored()

    # Fully-known 1-tile pocket has no frontier and counts as fully explored.
    solo = RoomMap()
    for t in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]:
        solo.mark_floor(t)
    for w in [(2, 0), (-2, 0), (0, 2), (0, -2), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
        solo._walls.add(w)
    assert solo.nearest_frontier((0, 0)) is None
    assert not solo.has_unexplored()

    print("PASS")


if __name__ == "__main__":
    main()
