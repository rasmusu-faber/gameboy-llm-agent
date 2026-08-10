"""Tell a real screen crossing from a scroll-tick - pure geometry, no emulator.

Issue #7: the town has a few screens that scroll, and they tick the background
fingerprint every step; a naive "any fingerprint change is a crossing" then invents
a new screen per tile. A scroll-tick leaves the player EXACTLY one tile along the
walked direction (positions are tile-aligned, so it lands where a normal step
lands), while a real crossing TELEPORTS them to a spawn - a discontinuous jump,
often against the pressed direction (press up at a door, land a tile below on the
far side). The agent pairs this with a `new_fp != cur_fp` check (a crossing must
also land on a different fingerprint), which together kill the outdoor self-loops.

Kept emulator-free so it unit-tests with nothing installed (see test_crossing.py).
"""

# Same axis convention as the rest of the code: y grows downward, so "up" is -y.
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def is_crossing_move(prev_pos, new_pos, direction, tile: int = 8, slack: int = 1) -> bool:
    """True if moving from `prev_pos` to `new_pos` while walking `direction` is a
    real screen crossing rather than a scroll-tick.

    Compares the new position to the expected continuous one-tile step; any mismatch
    beyond `slack` tiles is a crossing (a teleport to a spawn). A scroll-tick lands
    exactly on the expected step (mismatch 0). Positions are in pixels.
    """
    dx, dy = _DELTA.get(direction, (0, 0))
    ex, ey = prev_pos[0] + dx * tile, prev_pos[1] + dy * tile
    return abs(new_pos[0] - ex) + abs(new_pos[1] - ey) > slack * tile
