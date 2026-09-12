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

    # A crossed doorway is fenced DURABLY. Player at (5,5), boxed by walls on
    # up/down/left; the only way onward is RIGHT, through the doorway (6,5) to the
    # unexplored (7,5). A door blocks BFS traversal, so no frontier is reachable.
    dm = RoomMap()
    dm.mark_floor((5, 5))
    for w in [(5, 4), (5, 6), (4, 5)]:       # up, down, left are solid
        dm.mark_wall(w)
    dm.mark_door((6, 5))                      # right is a crossed doorway
    assert dm.nearest_frontier((5, 5)) is None, "door must block the only frontier"
    assert not dm.has_unexplored(), "a doored-off neighbour is not an open frontier"

    # The reverse crossing drops the player back onto the doorway, and the next
    # explore step calls mark_floor on it. A plain wall would be DISCARDED here
    # (that discard is the bug); a door must SURVIVE, so (7,5) stays unreachable.
    dm.mark_floor((6, 5))                     # re-entry lands on the doorway tile
    assert dm.nearest_frontier((5, 5)) is None, "mark_floor must not reopen a door"

    # Contrast: the exact same geometry with mark_wall IS reopened by mark_floor,
    # letting the frontier route straight back out - the oscillation the fix kills.
    wm = RoomMap()
    wm.mark_floor((5, 5))
    for w in [(5, 4), (5, 6), (4, 5)]:
        wm.mark_wall(w)
    wm.mark_wall((6, 5))
    wm.mark_floor((6, 5))                     # standing on it discards the wall
    assert wm.nearest_frontier((5, 5)) == "right", "mark_wall is (intentionally) not durable"

    # --- find_path (walk_to's real-pathfinding upgrade, see design-log) --------

    # Straight corridor, no obstacles: a direct direction sequence.
    corridor = RoomMap()
    for x in range(0, 4):
        corridor.mark_floor((x, 0))
    assert corridor.find_path((0, 0), (3, 0)) == ["right", "right", "right"]
    assert corridor.find_path((0, 0), (0, 0)) == []          # already there

    # Goal is an OBSTACLE (never marked floor, e.g. a landmark's own tile): the
    # path must stop at a floor tile ADJACENT to it, not attempt to enter it.
    beside = RoomMap()
    beside.mark_floor((0, 0))
    beside.mark_floor((1, 0))                 # floor tile beside the obstacle at (2,0)
    path = beside.find_path((0, 0), (2, 0))
    assert path == ["right"], path            # stops at (1,0), one short of the obstacle

    # Goal IS known floor (a real, already-crossed door) with an EQUALLY CLOSE
    # floor neighbour: the path must land EXACTLY on the door, never settle for
    # the neighbour just because BFS reached it first. This is the live bug: a
    # door's neighbours are also valid floor, so treating them as interchangeable
    # stops made walk_to land one tile short of the threshold, missing the
    # subsequent crossing press entirely (see design-log).
    door_room = RoomMap()
    #   (0,0)-(1,0)-(2,0)   <- (2,0) is the door; (1,0) is its floor neighbour,
    #                          reached by BFS at the SAME distance as (2,0) itself
    #                          would be reached one step later - if find_path ever
    #                          treated (1,0) as an acceptable stop, it would return
    #                          early there instead of continuing to (2,0).
    for t in [(0, 0), (1, 0), (2, 0)]:
        door_room.mark_floor(t)
    path = door_room.find_path((0, 0), (2, 0))
    assert path == ["right", "right"], path   # must reach the door tile itself

    # No route through unknown territory: floor doesn't connect start to goal.
    disconnected = RoomMap()
    disconnected.mark_floor((0, 0))
    disconnected.mark_floor((5, 5))           # an island, never adjacent to (0,0)
    assert disconnected.find_path((0, 0), (5, 5)) is None

    # A fenced doorway blocks BFS traversal, same as nearest_frontier above.
    fenced = RoomMap()
    fenced.mark_floor((0, 0))
    fenced.mark_floor((1, 0))
    fenced.mark_door((1, 0))                  # the only route out is fenced
    fenced.mark_floor((2, 0))
    assert fenced.find_path((0, 0), (2, 0)) is None

    print("PASS")


if __name__ == "__main__":
    main()
