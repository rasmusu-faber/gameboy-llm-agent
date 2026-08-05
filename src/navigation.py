"""Deterministic movement controller: walk the player to a target tile.

The "controller" half of a planner/controller split. Tile-by-tile pathing needs
no judgement, so it is plain code (greedy with wall-handling), not the LLM - the
A/B test showed small models mis-handle exactly this. The LLM decides *where* to
go; walk_to() gets there.
"""

from perception import (
    player_position, scene_fingerprint, visible_dialog_text, dialog_open,
)

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


def interact(pyboy, direction) -> str:
    """Face `direction` and press A to examine/talk to the tile there.

    In GB Studio, turning to face a tile + pressing A is how you trigger a sign,
    object, or NPC. Returns the text that appeared (`perception.visible_dialog_text`)
    or '' if nothing did - so a plain wall reads as ''. The reflex behind the
    planner's `interact` intent; the LLM decides *whether* to interact and what to
    make of the text.

    Caveat: pressing `direction` first turns the player to face the target, but if
    that tile is open floor the player will *step* onto it. Only interact toward a
    tile you know is adjacent/blocked (e.g. something you just bumped), so this
    examines rather than wanders.
    """
    press(pyboy, direction)                 # turn to face the target tile
    press(pyboy, "a")                        # trigger it
    for _ in range(30):                      # let the box slide in + text render
        pyboy.tick()
    return "\n".join(_clean_lines(visible_dialog_text(pyboy)))


def _clean_lines(text):
    """Drop lines that are only unknown glyphs ('?') - a read_text artifact
    (a border/blank row), so captured text stays clean."""
    return [ln for ln in text.splitlines() if ln.strip("? ").strip()]


def _stable_dialog(pyboy, tries=6) -> str:
    """Wait for the current dialog page to stop changing (typewriter finished),
    then return it - so we read complete lines, not mid-render fragments."""
    prev = ""
    for _ in range(tries):
        for _ in range(8):
            pyboy.tick()
        cur = visible_dialog_text(pyboy)
        if cur == prev:
            break
        prev = cur
    return prev


def _is_movable(pyboy) -> bool:
    """True if the player can currently walk (real control, not a cutscene)."""
    p0 = player_position(pyboy)
    press(pyboy, "right")
    if player_position(pyboy) != p0:
        press(pyboy, "left")                 # restore
        return True
    return False


def advance_cutscene(pyboy, max_presses=60) -> str:
    """Play a blocking scripted scene through until the player regains control.

    Deadeus locks the player during scenes (e.g. the mother scene on entering
    room 2) - including fragments where a character MOVES with no dialog box up -
    and only A advances them. So we press A until movement works again, collecting
    any dialogue text along the way (it carries hints). Returns that text; empty
    if control was never lost (a normal room needs no advancing).
    """
    lines, seen = [], set()
    for _ in range(max_presses):
        for ln in _clean_lines(visible_dialog_text(pyboy)):
            ln = ln.strip()
            if ln and ln not in seen:
                seen.add(ln)
                lines.append(ln)
        if _is_movable(pyboy):               # control returned -> scene is over
            break
        press(pyboy, "a")
    return " ".join(lines)


def read_dialog(pyboy, max_pages=20) -> str:
    """Advance an open dialog to the end, collecting every page's text.

    For passively-triggered dialogue (an NPC speaking on its own): read it all
    into memory instead of just clicking it away, since hints about places and
    next steps live in this text. Returns the full text (unique lines, in order).
    Same blind-A caveat as dismiss_dialog: fine for narration, not choice-aware.
    """
    lines, seen = [], set()
    for _ in range(max_pages):
        if not dialog_open(pyboy):
            break
        for ln in _clean_lines(_stable_dialog(pyboy)):
            ln = ln.strip()
            if ln and ln not in seen:
                seen.add(ln)
                lines.append(ln)
        press(pyboy, "a")                    # advance to the next page / close
    return " ".join(lines)


def dismiss_dialog(pyboy, max_presses=10) -> bool:
    """Close an open dialog by pressing A until it clears. Returns True if closed.

    This blindly advances - safe for plain text boxes and for the bedroom bed
    prompt (verified: confirming it does not sleep here). KNOWN LIMITATION: a
    *consequential* yes/no choice elsewhere would need choice-aware handling, not
    blind A. Revisit when the agent meets decisions with real consequences.
    """
    for _ in range(max_presses):
        if not dialog_open(pyboy):
            return True
        press(pyboy, "a")
    return not dialog_open(pyboy)


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
