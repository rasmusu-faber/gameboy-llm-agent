"""Grid odometry: track which screen you are on by counting screen crossings.

Issue #7 - outdoors, many screens share a background tilemap, so the scene
fingerprint collides and cannot identify a screen (see the design log). Outdoor
movement is a Euclidean grid, though: crossing a screen edge in a direction moves
you exactly one cell that way, and opposite crossings cancel. So a coordinate
advanced by the crossing direction is a stable, entry-independent screen id
*where the fingerprint is not*. The fingerprint stays the crossing **detector**;
this is the **identity**.

Deliberately emulator-free - plain directions in, a coordinate out - so it
unit-tests without a ROM. The reconciliation with the fingerprint (loop-closure
for the quirky indoor doors, and restoring the entry cell when stepping back out
of a house) lives in the agent, not here; this class only does the dead-reckoning,
plus a `set()` the agent uses to snap on a loop-closure or a house return.
"""

# Same axis convention as the rest of the code (perception/agent): y grows
# downward, matching tile coordinates, so "up" is -y.
_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class Odometer:
    """Dead-reckoning position on the screen grid, in screen-cells."""

    def __init__(self, start=(0, 0)):
        self._coord = (int(start[0]), int(start[1]))

    @property
    def coord(self) -> tuple[int, int]:
        return self._coord

    def step(self, direction: str) -> tuple[int, int]:
        """Advance one cell in `direction` (one screen crossing) and return the new
        coordinate. An unknown direction is a deliberate no-op, so a stray value
        can never corrupt the coordinate."""
        dx, dy = _DELTA.get(direction, (0, 0))
        self._coord = (self._coord[0] + dx, self._coord[1] + dy)
        return self._coord

    def set(self, coord) -> tuple[int, int]:
        """Snap to a known coordinate. The agent uses this for loop-closure (the
        fingerprint uniquely matched a known node, so trust it over dead-reckoning)
        and to restore the entry cell when stepping back out of a house."""
        self._coord = (int(coord[0]), int(coord[1]))
        return self._coord
