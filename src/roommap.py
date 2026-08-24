"""A local occupancy map of the current room, built from the agent's own moves.

No probing (door-safe): a tile the player stands on is floor; a move that gains
0 tiles reveals a wall in that direction. Rendered as a small ASCII mini-map plus
an adjacency summary, to give the planner real spatial grounding instead of bare
(x, y) coordinates. All coordinates are in tile units (perception.player_tile).

This is measured fact (code-filled), one map per scene; kept separate from the
persistent notebook (memory.py) since it is live per-run local geometry.
"""

from collections import deque

WALL, FLOOR, PLAYER, UNKNOWN = "#", ".", "@", "?"
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class RoomMap:
    def __init__(self):
        self._floor: set[tuple[int, int]] = set()
        self._walls: set[tuple[int, int]] = set()
        # Crossed doorways: impassable for exploration AND immune to mark_floor.
        # A plain wall (`_walls`) is cleared the moment the player stands on it
        # (mark_floor discards it) and cannot be re-set over floor - so a re-entry
        # onto a doorway silently reopens it, and nearest_frontier sends the agent
        # straight back out through that one tile (the outdoor edge oscillation).
        # Doorways live here instead, where standing on them can't reopen them.
        self._doors: set[tuple[int, int]] = set()

    def mark_floor(self, tile: tuple[int, int]) -> None:
        self._floor.add(tuple(tile))
        self._walls.discard(tuple(tile))

    def mark_wall(self, tile: tuple[int, int]) -> None:
        """Force a tile to count as an impassable boundary for exploration - used
        to fence off a known doorway so `nearest_frontier` stops routing back out
        of the room (crossing is a deliberate go_to, not a side effect of explore).
        Never overrides a tile already known to be floor."""
        tile = tuple(tile)
        if tile not in self._floor:
            self._walls.add(tile)

    def mark_door(self, tile: tuple[int, int]) -> None:
        """Fence off a crossed doorway durably. Unlike `mark_wall`, this survives
        the player later standing on the tile (mark_floor never clears `_doors`),
        so exploration cannot re-route back out through an exit it already found -
        which is what makes the agent ping-pong on a single tile at an outdoor
        screen edge, where the reverse crossing reliably drops it back on the
        doorway. Deliberate room changes use go_to, which ignores this map."""
        self._doors.add(tuple(tile))

    def observe(self, from_tile, to_tile, direction: str, moved: int) -> None:
        """Record one move's outcome. moved == 0 => the neighbour in `direction`
        is a wall; moved > 0 => the tile we landed on is floor."""
        self.mark_floor(from_tile)
        if moved == 0:
            dx, dy = _DELTA[direction]
            nbr = (from_tile[0] + dx, from_tile[1] + dy)
            if nbr not in self._floor:      # don't overwrite known floor
                self._walls.add(nbr)
        else:
            self.mark_floor(to_tile)

    def adjacent(self, tile) -> dict[str, str]:
        """For each direction: 'wall', 'floor', or 'unknown'."""
        out = {}
        for d, (dx, dy) in _DELTA.items():
            n = (tile[0] + dx, tile[1] + dy)
            out[d] = ("wall" if n in self._walls else
                      "floor" if n in self._floor else "unknown")
        return out

    def nearest_frontier(self, start) -> str | None:
        """Direction of the first step toward the nearest UNEXPLORED ('?') tile.

        BFS over known floor tiles from `start`; the goal is stepping off floor
        into an unknown tile (a frontier). Walls are impassable. Returns the
        cardinal direction to head, or None if nothing unexplored is reachable
        (e.g. the local area is fully mapped). This is how the door gets crossed:
        the unexplored tile beyond an edge IS the way out, and the LLM is told
        exactly which way it lies.
        """
        start = tuple(start)
        seen = {start}
        q = deque((n, d) for d, (dx, dy) in _DELTA.items()
                  for n in [(start[0] + dx, start[1] + dy)])
        while q:
            tile, first_dir = q.popleft()
            if tile in self._walls or tile in self._doors:
                continue
            if tile not in self._floor:      # unknown tile reached -> frontier
                return first_dir
            if tile in seen:
                continue
            seen.add(tile)
            for dx, dy in _DELTA.values():
                q.append(((tile[0] + dx, tile[1] + dy), first_dir))
        return None

    def has_unexplored(self) -> bool:
        """True if any known floor tile still borders an unexplored ('?') tile -
        i.e. the room is not fully mapped. Needs no start point, so it works for
        rooms the player isn't currently standing in (for the house overview)."""
        for tile in self._floor:
            for dx, dy in _DELTA.values():
                n = (tile[0] + dx, tile[1] + dy)
                if n not in self._floor and n not in self._walls and n not in self._doors:
                    return True
        return False

    def render(self, player, radius: int = 3) -> str:
        """ASCII mini-map centred on the player (up = north)."""
        px, py = player
        lines = []
        for y in range(py - radius, py + radius + 1):
            row = []
            for x in range(px - radius, px + radius + 1):
                cell = (x, y)
                if cell == tuple(player):
                    row.append(PLAYER)
                elif cell in self._walls:
                    row.append(WALL)
                elif cell in self._floor:
                    row.append(FLOOR)
                else:
                    row.append(UNKNOWN)
            lines.append("".join(row))
        return "\n".join(lines)
