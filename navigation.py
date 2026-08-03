"""Deterministic movement controller: walk the player to a target tile.

The "controller" half of a planner/controller split. Tile-by-tile pathing needs
no judgement, so it is plain code (greedy with wall-handling), not the LLM - the
A/B test showed small models mis-handle exactly this. The LLM decides *where* to
go; walk_to() gets there.
"""

from perception import player_position

TILE = 8


def press(pyboy, button, hold=6, wait=16):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()


def _moves_toward(x, y, tx, ty):
    """Directions that reduce the gap, larger axis first (then the other)."""
    horiz = "right" if tx > x else "left"
    vert = "down" if ty > y else "up"
    moves = []
    if abs(tx - x) >= abs(ty - y):
        if tx != x:
            moves.append(horiz)
        if ty != y:
            moves.append(vert)
    else:
        if ty != y:
            moves.append(vert)
        if tx != x:
            moves.append(horiz)
    return moves


def walk_direction(pyboy, direction, max_tiles=12) -> int:
    """Walk in one cardinal direction until blocked (a wall) or max_tiles moved.
    Returns the number of tiles actually moved."""
    moved = 0
    for _ in range(max_tiles):
        before = player_position(pyboy)
        press(pyboy, direction)
        if player_position(pyboy) == before:
            break
        moved += 1
    return moved


def walk_to(pyboy, tx, ty, max_steps=80) -> bool:
    """Greedy-walk the player to pixel coords (tx, ty).

    Returns True if reached, False if blocked (no gap-reducing move changed the
    position - e.g. a wall or obstacle on every useful direction).
    """
    for _ in range(max_steps):
        x, y = player_position(pyboy)
        if (x, y) == (tx, ty):
            return True
        progressed = False
        for move in _moves_toward(x, y, tx, ty):
            before = player_position(pyboy)
            press(pyboy, move)
            if player_position(pyboy) != before:
                progressed = True
                break
        if not progressed:
            return False
    return False
