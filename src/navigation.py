"""Deterministic movement controller: walk the player to a target tile.

The "controller" half of a planner/controller split. Tile-by-tile pathing needs
no judgement, so it is plain code (greedy with wall-handling), not the LLM - the
A/B test showed small models mis-handle exactly this. The LLM decides *where* to
go; walk_to() gets there.
"""

from perception import player_position, scene_fingerprint

TILE = 8

# Edge-sweep for search_for_exit: (moves to reach this edge's corner, direction
# to push outward against the edge, direction to sweep along it).
_EDGES = [
    (["up", "left"], "up", "right"),      # top edge, sweep left->right
    (["up", "right"], "right", "down"),   # right edge, sweep top->bottom
    (["down", "left"], "down", "right"),  # bottom edge, sweep left->right
    (["up", "left"], "left", "down"),     # left edge, sweep top->bottom
]

# Optional live-viewer hook: if set to a callable(pyboy), it is invoked after
# every button press so a watcher window can refresh. None => headless, no cost.
FRAME_HOOK = None


def press(pyboy, button, hold=6, wait=16):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()
    if FRAME_HOOK is not None:
        FRAME_HOOK(pyboy)


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


def search_for_exit(pyboy, ref_fp, sweep_len=16, push=4):
    """Deterministically hunt for a door: sweep each room edge, pushing outward,
    until the scene fingerprint changes (= we crossed into a new scene).

    A reflex, not a judgement call - the LLM chooses to invoke it, this code does
    the systematic sweep (small models can't). `ref_fp` is the current scene's
    fingerprint. Returns the push direction that led out, or None if no edge did.
    """
    for corner, push_dir, sweep_dir in _EDGES:
        for m in corner:                      # go to this edge's corner
            walk_direction(pyboy, m, max_tiles=20)
        for _ in range(sweep_len):
            for _ in range(push):             # push outward at this column/row
                press(pyboy, push_dir)
                if scene_fingerprint(pyboy) != ref_fp:
                    return push_dir
            if walk_direction(pyboy, sweep_dir, max_tiles=1) == 0:
                break                         # reached the far corner of this edge
    return None


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
