"""A local occupancy map of the current room, built from the agent's own moves.

No probing (door-safe): a tile the player stands on is floor; a move that gains
0 tiles reveals a wall in that direction. Rendered as a small ASCII mini-map plus
an adjacency summary, to give the planner real spatial grounding instead of bare
(x, y) coordinates. All coordinates are in tile units (perception.player_tile).

This is measured fact (code-filled), one map per scene; kept separate from the
persistent notebook (memory.py) since it is live per-run local geometry.
"""

WALL, FLOOR, PLAYER, UNKNOWN = "#", ".", "@", "?"
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class RoomMap:
    def __init__(self):
        self._floor: set[tuple[int, int]] = set()
        self._walls: set[tuple[int, int]] = set()

    def mark_floor(self, tile: tuple[int, int]) -> None:
        self._floor.add(tuple(tile))
        self._walls.discard(tuple(tile))

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
