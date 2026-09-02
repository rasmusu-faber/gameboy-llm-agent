"""Deterministic movement controller: walk the player to a target tile.

The "controller" half of a planner/controller split. Tile-by-tile pathing needs
no judgement, so it is plain code (greedy with wall-handling), not the LLM - the
A/B test showed small models mis-handle exactly this. The LLM decides *where* to
go; walk_to() gets there.
"""

from collections import namedtuple

from perception import (
    player_position, player_tile, scene_fingerprint, visible_dialog_text, dialog_open,
)
from dialog import merge_dialog
from crossing import is_crossing_move

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
    # FRAME_HOOK fires on every tick, not just once at the end: PyBoy already
    # computes the full walk-cycle animation across these hold+wait ticks, but a
    # single repaint after all of them turned each tile move into a hard jump-cut
    # in the --watch viewer. Costs nothing headless (FRAME_HOOK is None then).
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
        if FRAME_HOOK is not None:
            FRAME_HOOK(pyboy)
    pyboy.button_release(button)
    for _ in range(wait):
        pyboy.tick()
        if FRAME_HOOK is not None:
            FRAME_HOOK(pyboy)


# One crossing-aware tile-step. `crossed` is a REAL screen crossing caused by THIS
# step; `from_tile` is the tile stepped from (the door side); `new_fp` is the
# settled destination fingerprint.
StepResult = namedtuple("StepResult", "moved crossed from_tile new_fp")

# A Deadeus screen transition fires a tick or two AFTER the boundary tile is
# entered, and mid-transition the RAM player position reads (0,0) for ~1 frame
# while a 1-frame PHANTOM fingerprint shows (both measured, docs/design-log.md).
# So a step must settle past that before trusting position/fp - otherwise the
# delayed crossing lands on a LATER, unrelated press (wrong-direction edges) or a
# read hits the phantom (ghost scenes).
_STEP_SETTLE = 40        # ticks to let the move + any delayed transition finish
_TRANSITION_POS = (0, 0)  # the mid-transition garbage position reading


def step(pyboy, direction, ref_fp) -> StepResult:
    """Issue ONE tile-step in `direction`, then settle so a DELAYED screen crossing
    is caught HERE and attributed to THIS step - never to a later press. Reading
    position/fingerprint only after the settle (and draining the (0,0) transition
    frame) also skips the 1-frame phantom fingerprint. This is the fix for the
    crossing-misattribution family (wrong-direction edges, ghost scenes): detection
    is bound to the causing move by construction, not to whichever press happened to
    be active when the fingerprint change was noticed."""
    before = player_position(pyboy)
    from_tile = player_tile(pyboy)
    pyboy.button_press(direction)
    for _ in range(6):
        pyboy.tick()
        if FRAME_HOOK is not None:
            FRAME_HOOK(pyboy)
    pyboy.button_release(direction)
    for _ in range(_STEP_SETTLE):               # no early break: the RAM position
        pyboy.tick()                            # updates in 8px jumps, so an early
        if FRAME_HOOK is not None:              # "stable" read could catch the tile
            FRAME_HOOK(pyboy)                   # mid-move - just let it settle fully
    drain = 0
    while player_position(pyboy) == _TRANSITION_POS and drain < 20:
        pyboy.tick()                            # still mid-transition - wait for a
        if FRAME_HOOK is not None:              # valid position before reading
            FRAME_HOOK(pyboy)
        drain += 1
    after = player_position(pyboy)
    new_fp = scene_fingerprint(pyboy)
    # A real crossing = the SETTLED fingerprint is a different screen AND the move
    # was not a clean one-tile advance. slack=0 (not the default 1) is essential:
    # some destinations spawn the player at the SAME pixel as the source (e.g. s1's
    # spawn == the s0 doorway), so the position barely moves - a one-tile slack
    # would wrongly read that as "continuous" and miss the crossing. A scroll-tick
    # (fp changes as a screen edge scrolls) DOES advance exactly one tile, so
    # slack=0 still rejects it; only a teleport or a near-zero move counts.
    crossed = new_fp != ref_fp and is_crossing_move(before, after, direction, slack=0)
    return StepResult(after != before, crossed, from_tile, new_fp)


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


def sweep_for_crossing(pyboy, ref_fp, sweep_len=16, push=4):
    """Deterministically hunt for a door: sweep each room edge, pushing outward,
    until the player TELEPORTS to a new scene (= a real crossing).

    A reflex, not a judgement call - the LLM chooses to invoke it, this code does
    the systematic sweep (small models can't). `ref_fp` is the current scene's
    fingerprint. Returns `(push_dir, door_tile)` - the direction that led out and
    the tile (in `ref_fp`) we crossed from - or `(None, None)` if no edge did.

    The door_tile is what lets a caller record the *real* edge: a room's spawn tile
    and the geometric opposite of the entry direction are both unreliable in
    Deadeus (a door can be one tile off the spawn, and the way back is not always
    the reverse direction), so edges are best learned from an actual crossing.

    A crossing is a POSITION teleport (`is_crossing_move`), not merely a changed
    fingerprint: on a scrolling outdoor screen (e.g. Urizen Falls / s3) pushing at
    an edge scrolls the background - the fingerprint changes on every step while the
    player just walks one tile. Gating on the bare fp change (issue #10) made the
    sweep stop at the first scroll edge and never reach the edge with the real exit,
    so `go_to` reported "didn't cross". Same discriminator as issue #7's town fix:
    a scroll-tick lands exactly one tile along the press; a crossing jumps.
    """
    for corner, push_dir, sweep_dir in _EDGES:
        for m in corner:                      # go to this edge's corner
            walk_direction(pyboy, m, max_tiles=20)
        for _ in range(sweep_len):
            for _ in range(push):             # push outward at this column/row
                st = step(pyboy, push_dir, ref_fp)   # crossing-aware push
                if st.crossed:
                    return push_dir, st.from_tile
                if st.new_fp != ref_fp:
                    break                     # a scroll-tick, not an exit: this is a
                    # scrolling edge - stop pushing into it and move along the sweep
            if walk_direction(pyboy, sweep_dir, max_tiles=1) == 0:
                break                         # reached the far corner of this edge
    return None, None


_OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


def probe_for_crossing(pyboy, ref_fp, reach=4):
    """Try each direction from the CURRENT position, stepping up to `reach` tiles to
    walk through a nearby door. Returns `(dir, door_tile)` of the first REAL crossing
    (a teleport, per `is_crossing_move`) or `(None, None)`.

    Unlike `sweep_for_crossing`, this never walks off to a screen corner first, so it
    can't fall out of an unrelated exit on an open outdoor screen (issue #10, e.g.
    Urizen Falls, where seeking the top corner walked the sweep out the side exit).
    Continuous (non-crossing) walking is UNDONE so the probe leaves the player where
    it started - ideal for returning through the door you just entered. We TRY each
    direction instead of assuming the reverse is the opposite: in Deadeus the way back
    is irregular (indoors especially), so only an observed crossing is trusted.
    """
    for d in ("right", "left", "up", "down"):
        walked = 0
        for _ in range(reach):
            st = step(pyboy, d, ref_fp)                 # crossing-aware: a delayed
            if st.crossed:                              # teleport is caught here and
                return d, st.from_tile                  # attributed to THIS direction
            if not st.moved:
                break                                   # blocked by a wall
            walked += 1
        for _ in range(walked):                         # no crossing this way: walk back
            back = step(pyboy, _OPPOSITE[d], ref_fp)    # to where we started. step()
            if back.crossed:                            # already settles the transition,
                return d, back.from_tile                # so this rarely fires - defensive:
                                                        # a crossing surfacing now was
                                                        # caused by `d`, not the undo.
    return None, None


def search_for_exit(pyboy, ref_fp, sweep_len=16, push=4):
    """Backwards-compatible wrapper: just the push direction that led out (or None).
    Use `sweep_for_crossing` when you also need the door tile to record the edge."""
    return sweep_for_crossing(pyboy, ref_fp, sweep_len, push)[0]


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


def _dialog_words(pyboy):
    return visible_dialog_text(pyboy).replace("?", " ").split() if dialog_open(pyboy) else []


# A two-option menu pairs a COMMIT option (cursor starts here, top) with a DECLINE
# option (safe, bottom). Deadeus uses more than one such pair: the bed/monster
# prompts are Yes/No, but the SAVE BOOK is 'Save Game?' / 'Cancel'. Recognizing
# only Yes/No meant the save menu fell through to a plain-text A-press, which
# confirmed the default 'Save Game?' and saved on every touch. Case-sensitive so
# lowercase 'yes'/'no'/'save'/'cancel' in prose never trigger a menu.
_MENU_COMMIT = ("Yes", "Save")      # top option, where the cursor defaults
_MENU_DECLINE = ("No", "Cancel")    # bottom option, what DOWN+A selects


def _is_choice(pyboy) -> bool:
    """True once a two-option menu is FULLY loaded (both options visible). The
    bottom (decline) option loads last, so its presence means the menu is ready.
    Deadeus's cursor starts on the top (commit) option and B does nothing - to
    decline you must move DOWN to the bottom option and press A. Covers Yes/No AND
    the save book's 'Save Game?'/'Cancel'."""
    words = _dialog_words(pyboy)
    top = any(w in words for w in _MENU_COMMIT)
    bottom = any(w in words for w in _MENU_DECLINE)
    return top and bottom


def _menu_forming(pyboy) -> bool:
    """The choice menu is appearing (top option up, bottom not yet) - do NOT press
    A now (it would confirm the default commit option); wait for it to finish
    loading."""
    words = _dialog_words(pyboy)
    top = any(w in words for w in _MENU_COMMIT)
    bottom = any(w in words for w in _MENU_DECLINE)
    return top and not bottom


def _decline(pyboy):
    """Pick the safe (bottom) option of a two-option menu: No on a Yes/No prompt,
    Cancel on the save book. The cursor defaults to the top (commit) option and B
    does nothing, and the menu isn't interactive the instant both options render -
    so settle first, then move DOWN to the bottom option and press A."""
    for _ in range(20):
        pyboy.tick()
    press(pyboy, "down")                     # commit (default) -> decline
    press(pyboy, "a")                        # confirm the safe option


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
    return merge_dialog(lines)


def read_dialog(pyboy, max_pages=20) -> str:
    """Advance an open dialog to the end, collecting every page's text.

    For passively-triggered dialogue (an NPC speaking on its own): read it all
    into memory instead of just clicking it away, since hints about places and
    next steps live in this text. Returns the full text (unique lines, in order).
    A Yes/No choice is DECLINED by default (move down to No, press A - the menu
    defaults to Yes and B does nothing), never auto-confirmed - a deliberate
    decision will handle those later.
    """
    lines, seen = [], set()
    for _ in range(max_pages):
        if not dialog_open(pyboy):
            break
        real = _clean_lines(_stable_dialog(pyboy))
        for ln in real:
            ln = ln.strip()
            if ln and ln not in seen:
                seen.add(ln)
                lines.append(ln)
        if _is_choice(pyboy):                # Yes/No loaded -> decline it
            _decline(pyboy)
            break
        if not real or _menu_forming(pyboy):  # empty or menu still loading -> wait,
            for _ in range(15):               # DON'T press A (it would confirm Yes)
                pyboy.tick()
            continue
        press(pyboy, "a")                    # advance normal text to the next page
    return merge_dialog(lines)


def dismiss_dialog(pyboy, max_presses=10) -> bool:
    """Close an open dialog. Advances plain text with A, but DECLINES a Yes/No
    choice with B - so automatic paths never accidentally confirm a consequential
    decision (e.g. sleeping at the bed). Returns True if closed."""
    for _ in range(max_presses):
        if not dialog_open(pyboy):
            return True
        if _is_choice(pyboy):                # Yes/No loaded -> decline (No)
            _decline(pyboy)
        elif _menu_forming(pyboy) or not _clean_lines(visible_dialog_text(pyboy)):
            for _ in range(15):              # menu loading or empty -> wait, no A
                pyboy.tick()                 # (an A now would confirm the default Yes)
        else:
            press(pyboy, "a")                # advance real text
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
