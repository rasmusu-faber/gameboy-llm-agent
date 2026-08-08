"""Intent-driven agent: LLM orchestrator over a library of deterministic skills.

The LLM no longer steers tile-by-tile (a 3B does that unreliably - see the design
log). Instead it picks ONE high-level *intent* per turn - explore, go_to,
interact, remember - and a deterministic skill carries it out to completion. This
is the tool-use / planner-controller split done properly: the LLM makes judgement
calls, code does the reflexes. See docs/action-vocabulary.md.
"""

import argparse
import time
from pathlib import Path

from pyboy import PyBoy

from perception import (
    player_position, player_tile, dialog_open, visible_dialog_text,
    scene_fingerprint, game_day,
)
import navigation
from navigation import (
    press, walk_direction, walk_to, interact, dismiss_dialog, read_dialog,
    advance_cutscene, sweep_for_crossing, TILE,
)
from memory import WorldMap, fp_key
from roommap import RoomMap
import llm

_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

ROM = "roms/Deadeus.gb"
INTENT_ROUNDS = 15                      # one LLM judgement call per round
EXPLORE_BUDGET = 25                     # max tiles a single explore intent walks
SKILLS = ("explore", "go_to", "interact", "remember")
GOAL = ("You are the boy from the intro. You have THREE DAYS before the entity "
        "returns to destroy everyone unless the debt is repaid. Find out what is "
        "happening and how to prevent it WITHOUT harming anyone, and check on the "
        "people who matter to you. Explore, read, talk, and act on what you learn.")
OUT = Path("runs/explore")
WORLD = Path("memory/world.md")   # persistent notebook (git-ignored)

INTENT_SYSTEM = (
    "You are an agent exploring a Game Boy game (a small house). Each turn you "
    "choose ONE high-level action; a deterministic skill then carries it out.\n"
    "Actions:\n"
    "- explore : map more of the CURRENT room (find its exits and objects). Use "
    "while the room is not fully explored.\n"
    "- go_to <id> : walk to a known landmark (l0, l1, …) or a connected room "
    "(s0, s1, …). Use to revisit an object or to leave through a known exit.\n"
    "- interact <id> : read/talk to a landmark, but ONLY one listed under "
    "'Landmarks here'. Those ids live in the CURRENT room. To read something in "
    "another room, go_to that room FIRST - an id from another room will fail.\n"
    "- remember <note> : write down a short conclusion worth keeping.\n"
    "Exploring only DISCOVERS ground; the POINT is to LEARN and ACT on your goal, "
    "not to map the whole house. Each turn, prefer in THIS order:\n"
    "1. If there are UNREAD landmarks here, interact with one - reading and talking "
    "is how you find clues (an object you've already read gives nothing new).\n"
    "2. If your plan names a place or person to reach, go_to it and act on it.\n"
    "3. Otherwise, if this room still has unexplored area, explore it.\n"
    "4. If this room is fully explored AND its landmarks are read, go_to a "
    "PARTIALLY-explored or NOT-visited room (prefer a connected exit).\n"
    "Do NOT explore room after room while unread landmarks or an unmet plan remain. "
    "You are told the current day and how many days remain; time is limited, so "
    "weigh it toward the goal.\n"
    "Keep a running plan toward the goal in 'subgoal' and update it as you learn "
    "(e.g. 'find and talk to my family', 'find out how to repay the debt'). "
    "Use 'note' with the remember action to write down anything important.\n"
    'Respond ONLY as JSON: {"action":"explore|go_to|interact|remember",'
    '"target":"<id or empty>","note":"<for remember>",'
    '"subgoal":"<your current plan>","why":"<short reason>"}'
)


def _reversible_move(pyboy, fwd, back):
    """True if pressing fwd changes the player position and back returns it -
    i.e. real player control, not a cutscene animation."""
    p0 = player_position(pyboy)
    press(pyboy, fwd)
    p1 = player_position(pyboy)
    press(pyboy, back)
    return p1 != p0 and player_position(pyboy) == p0


def _dedup_fragments(lines):
    """Join lines, dropping typewriter prefixes (a line fully contained at the
    start of a longer captured line, e.g. 'I have given yo' vs '...you')."""
    keep = [ln for ln in lines
            if not any(o != ln and o.startswith(ln) for o in lines)]
    return " ".join(keep)


def skip_intro(pyboy, max_steps=600):
    """Deterministic: click through the title + intro into the movable game,
    CAPTURING the intro text on the way (it holds the premise - 'Three Days', the
    mother's warning). Returns that captured text.

    Press A while a dialog is on-screen; detect arrival with a reversible movement
    test. Movement tests start only after the title menu, so a direction never
    nudges a menu cursor.
    """
    press(pyboy, "start")
    streak = 0
    lines, seen = [], set()
    for step in range(1, max_steps + 1):
        if dialog_open(pyboy):
            for ln in visible_dialog_text(pyboy).splitlines():
                ln = ln.strip()
                if ln.strip("? ").strip() and ln not in seen:
                    seen.add(ln)
                    lines.append(ln)
            streak = 0
            press(pyboy, "a")
        else:
            streak += 1
            if step > 20 and streak >= 3 and (
                _reversible_move(pyboy, "right", "left")
                or _reversible_move(pyboy, "down", "up")
            ):
                break
            press(pyboy, "a")
    return _dedup_fragments(lines)


# --- deterministic skills (the reflex library the LLM orchestrates) ----------

def _auto_detect(pyboy, world, rooms, probed, cur_fp, direction, ptile):
    """A bump may be an object, not a wall: interact once per tile, record any
    text as a landmark, dismiss the dialog. Returns a short note or None."""
    dx, dy = _DELTA[direction]
    nbr = (ptile[0] + dx, ptile[1] + dy)
    seen = probed.setdefault(cur_fp, set())
    if nbr in seen:
        return None
    seen.add(nbr)
    text = interact(pyboy, direction)
    if not text:
        return None
    lid = world.add_landmark(cur_fp, nbr, text)
    dismiss_dialog(pyboy)
    return f"{lid}({text.splitlines()[0][:20]})"


def skill_explore(pyboy, world, rooms, probed, cur_fp):
    """FULLY map the current room before ever leaving it. Walk to the nearest
    unexplored tile, probing bumped objects into landmarks, until every reachable
    tile is covered. Doors are NOT walked through: a discovered exit is recorded,
    its doorway is fenced off, and the agent returns to finish the room. Changing
    rooms is a deliberate `go_to`, not a side effect of exploring. This is what
    makes the agent map room 1 fully (and so find e.g. the bed) instead of bouncing
    out the first door it meets. Returns (summary, current_fp)."""
    room = rooms.setdefault(cur_fp, RoomMap())
    for d, _tid, door in world.exits_detailed(cur_fp):   # fence off known doorways
        if door:
            dx, dy = _DELTA[d]
            room.mark_wall((door[0] + dx, door[1] + dy))
    found = []
    for _ in range(EXPLORE_BUDGET):
        if dialog_open(pyboy):            # a probe may have opened one (e.g. a save
            dismiss_dialog(pyboy)         # point) - drain it so moves aren't wedged
        ptile = player_tile(pyboy)
        room.mark_floor(ptile)
        frontier = room.nearest_frontier(ptile)
        if frontier is None:
            return f"explored; room fully mapped{_join(found)}", cur_fp
        moved = walk_direction(pyboy, frontier, max_tiles=1)

        if scene_fingerprint(pyboy) != cur_fp:            # bumped a door and crossed
            heard = advance_cutscene(pyboy)               # play any entry scene
            new_fp = scene_fingerprint(pyboy)
            nid = world.seen_scene(new_fp, player_position(pyboy))
            world.note_crossing(cur_fp, frontier, new_fp,
                                door_tile=ptile, spawn_tile=player_tile(pyboy))
            if heard:
                world.add_fact(new_fp, heard)             # entry dialogue -> hints
            dx, dy = _DELTA[frontier]
            room.mark_wall((ptile[0] + dx, ptile[1] + dy))  # fence this doorway
            _, back_fp = skill_go_to(pyboy, world, new_fp, world.scene_id(cur_fp))
            if back_fp != cur_fp:                         # couldn't return -> accept it
                note = f" (scene: {heard[:24]!r})" if heard else ""
                return (f"explored; found exit to {nid} but stayed there"
                        f"{_join(found)}{note}"), back_fp
            found.append(f"exit->{nid}")
            continue

        room.observe(ptile, player_tile(pyboy), frontier, moved)
        if moved == 0:                                    # a bump: wall or object?
            note = _auto_detect(pyboy, world, rooms, probed, cur_fp, frontier, ptile)
            if note:
                found.append(note)
    return f"explored; more of the room left to map{_join(found)}", cur_fp


def skill_go_to(pyboy, world, cur_fp, target):
    """Walk to a known landmark (same room) or cross to a connected room.

    `target` may be a landmark id (l#), a room id (s#), or a bare exit direction
    (up/down/left/right) - the LLM tends to name the direction, so resolve it to
    the room that exit leads to.
    """
    if not target:
        return "go_to needs a target (a landmark l#, a room s#, or a direction)", cur_fp
    if target in _DELTA:                        # a direction -> the room it leads to
        match = [tid for d, tid, _ in world.exits_detailed(cur_fp) if d == target]
        if not match:
            return f"go_to: no known exit '{target}' from here", cur_fp
        target = match[0]

    cur_id = world.scene_id(cur_fp)
    lm = world.find_landmark(target)
    if lm:
        if lm["scene"] != cur_id:
            return (f"go_to: {target} is in {lm['scene']}, not here; "
                    "cross-room routing isn't built yet"), cur_fp
        tx, ty = lm["tile"]
        ok = walk_to(pyboy, tx * TILE, ty * TILE)
        return (f"go_to: reached {target}" if ok
                else f"go_to: stopped next to {target}"), cur_fp
    for d, tid, door in world.exits_detailed(cur_fp):
        if tid == target:
            if door and door != (0, 0):         # walk onto the doorway tile
                walk_to(pyboy, door[0] * TILE, door[1] * TILE)
            for _ in range(4):                  # step through (door may be a tile or two on)
                press(pyboy, d)
                if scene_fingerprint(pyboy) != cur_fp:
                    advance_cutscene(pyboy)     # play any entry scene until movable
                    new_fp = scene_fingerprint(pyboy)
                    world.seen_scene(new_fp, player_position(pyboy))
                    return f"go_to: crossed into {target}", new_fp
            # The recorded edge is stale: a room's spawn tile and the geometric
            # opposite of the entry direction are both unreliable in Deadeus, so a
            # reverse edge guessed by note_crossing often doesn't cross. Fall back
            # to a real sweep and learn the true door from the crossing.
            return _cross_by_sweep(pyboy, world, cur_fp, target)
    return f"go_to: '{target}' isn't a known landmark or connected room", cur_fp


def _cross_by_sweep(pyboy, world, cur_fp, target):
    """Recover a failed edge crossing by deterministically sweeping for the door,
    then record the REAL edge (direction + door tile) we observed - self-correcting
    the map. Returns (message, new_fp). If nothing crossed, stays put."""
    real_dir, door_tile = sweep_for_crossing(pyboy, cur_fp)
    if real_dir is None:
        return f"go_to: tried to reach {target} but didn't cross", cur_fp
    advance_cutscene(pyboy)                      # play any entry scene until movable
    new_fp = scene_fingerprint(pyboy)
    world.seen_scene(new_fp, player_position(pyboy))
    world.connect(cur_fp, real_dir, new_fp, door_tile)  # learn the true edge
    landed = world.scene_id(new_fp)
    if landed == target:
        for d, tid, _door in world.exits_detailed(cur_fp):  # prune stale guesses
            if tid == target and d != real_dir:
                world.forget_edge(cur_fp, d, new_fp)
        return f"go_to: crossed into {target} (corrected the map)", new_fp
    return f"go_to: aimed for {target}, the open door led to {landed}", new_fp


def skill_interact(pyboy, world, cur_fp, target, read=None):
    """Walk up to a known landmark, face it, and read its FULL dialogue.

    Two-stream model: the conversation goes to the scene's facts (the "heard"
    stream), never overwriting the landmark's first-contact descriptor - so an
    NPC's unfolding lines don't get baked into its identity, only into memory.
    `read` (if given) records the id so the state can stop offering it again."""
    lm = world.find_landmark(target) if target else None
    if not lm:
        return f"interact: '{target}' isn't a known landmark", cur_fp
    if lm["scene"] != world.scene_id(cur_fp):
        return (f"interact: {target} is in room {lm['scene']}, not here - "
                f"go_to {lm['scene']} first"), cur_fp
    if read is not None:
        # Mark this landmark - and its identical-text clones in this room (multi-
        # tile objects, or 8 duplicate bookshelves) - as done, so the state stops
        # re-offering it. Done up front so an UNREACHABLE landmark is also retired
        # (otherwise "unread + can't reach" loops forever).
        same = [o["id"] for o in world.landmarks_of(cur_fp)
                if lm["text"] and o["text"] == lm["text"]]
        read.update(same or [target])
    tx, ty = lm["tile"]
    walk_to(pyboy, tx * TILE, ty * TILE)        # stops adjacent (object blocks)
    face = _dir_to(player_tile(pyboy), (tx, ty))
    if face is None:
        return f"interact: couldn't get beside {target}", cur_fp
    press(pyboy, face)                           # turn to face it
    press(pyboy, "a")                            # trigger
    heard = read_dialog(pyboy)                   # full conversation, then closes
    if heard:
        world.add_fact(cur_fp, heard)            # dialogue -> the heard stream
        if not lm["text"]:                       # give it a short descriptor if none
            world.add_landmark(cur_fp, (tx, ty), heard[:24])
        return f"interact {target}: {heard[:40]!r}", cur_fp
    return f"interact {target}: nothing happened", cur_fp


def skill_remember(world, cur_fp, note):
    if not note:
        return "remember needs a note"
    world.add_fact(cur_fp, note)
    return f"remembered: {note[:40]!r}"


def _join(found):
    return f"; found {', '.join(found)}" if found else ""


def _dir_to(a, b):
    """Cardinal direction from tile a to adjacent tile b, or None if not adjacent."""
    delta = (b[0] - a[0], b[1] - a[1])
    for d, dxy in _DELTA.items():
        if dxy == delta:
            return d
    return None


# --- the LLM planner (judgement) ---------------------------------------------

def _house_overview(world, rooms, cur_id):
    """All known rooms and whether each is fully explored (from its RoomMap)."""
    by_key = {fp_key(fp): rm for fp, rm in rooms.items()}
    lines = []
    for s in world.scene_list():
        rm = by_key.get(s["key"])
        if rm is None:
            status = "not visited yet"
        elif rm.has_unexplored():
            status = "PARTIALLY explored - unexplored area remains"
        else:
            status = "fully explored"
        here = " (you are here)" if s["id"] == cur_id else ""
        name = s["id"] + (f" [{s['label']}]" if s["label"] else "")
        lines.append(f"  {name}: {status}, {s['landmarks']} landmarks{here}")
    return "\n".join(lines)


def build_state(world, rooms, cur_fp, pyboy, log, subgoal, read=None):
    """The intent-level state the LLM chooses from (not raw (x, y)). `read` is the
    set of landmark ids already interacted with this run - used to surface which
    landmarks are still worth reading, so the agent acts instead of re-reading or
    mapping endlessly."""
    read = read or set()
    cur_id = world.scene_id(cur_fp)
    label = world.label_of(cur_fp)
    room_name = cur_id + (f" ({label})" if label else "")
    exits = world.exits_detailed(cur_fp)
    exits_str = "; ".join(f"{d} -> {tid}" for d, tid, _ in exits) or "none known yet"
    lms = world.landmarks_of(cur_fp)
    lm_str = "; ".join(f'{lm["id"]} @ {lm["tile"]}: "{lm["text"]}"'
                       for lm in lms) or "none yet"
    here_ids = ", ".join(lm["id"] for lm in lms) or "none"
    # Unread landmarks, de-duplicated by text (multi-tile objects create clones):
    # show one representative id per distinct text so the agent doesn't re-read.
    unread, seen_txt = [], set()
    for lm in lms:
        if lm["id"] not in read and lm["text"] not in seen_txt:
            seen_txt.add(lm["text"])
            unread.append(f'{lm["id"]} "{lm["text"]}"')
    unread_str = "; ".join(unread) or "none - all read here"
    facts = world.facts_of(cur_fp)
    facts_str = " | ".join(facts) or "none yet"
    room = rooms.get(cur_fp)
    if room is None:
        explored = "not yet (just arrived)"
    else:
        explored = ("partially - unexplored tiles remain"
                    if room.nearest_frontier(player_tile(pyboy)) else "fully")
    # Drop the "; found lN(...)" landmark dump from past results: those ids belong
    # to whatever room they were found in, and dangling them here tempted models to
    # interact with landmarks that aren't in the current room. The interactable set
    # is 'Landmarks here' only.
    recent = "; ".join(f"{a} -> {res.split('; found ')[0]}"
                       for a, res in log[-4:]) or "nothing yet"
    premise = " | ".join(world.knowledge()) or "unknown"
    house = _house_overview(world, rooms, cur_id)
    day = game_day(pyboy)
    left = max(0, 3 - day)
    time_line = (f"day {day} of 3 - {left} day(s) left before the entity returns. "
                 "Sleeping in a bed ends the current day.")
    return (f"Premise (what you know about the game): {premise}\n"
            f"Time: {time_line}\n"
            f"Your current plan: {subgoal or 'none yet - decide one from the goal'}\n"
            f"House so far (all known rooms):\n{house}\n"
            f"Current room: {room_name}\n"
            f"Known exits: {exits_str}\n"
            f"Landmarks here (the ONLY ids you can interact with now): {here_ids}\n"
            f"UNREAD landmarks here (worth interacting with): {unread_str}\n"
            f"  details: {lm_str}\n"
            f"Dialogue heard here: {facts_str}\n"
            f"Room explored: {explored}\n"
            f"Goal: {GOAL}\n"
            f"Recent actions: {recent}")


def plan_intent(state):
    """LLM: pick one intent. Returns a dict, or None if it produced nothing valid."""
    c = llm.chat_json(INTENT_SYSTEM, state)
    action = str(c.get("action", "")).lower().strip()
    if action not in SKILLS:
        return None
    return {"action": action,
            "target": str(c.get("target", "")).strip(),
            "note": str(c.get("note", "")).strip(),
            "subgoal": str(c.get("subgoal", "")).strip(),
            "why": str(c.get("why", "")).strip()}


def main(watch=False, rounds=INTENT_ROUNDS, delay=0.0):
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")

    # Optional live viewer: open a window and refresh it on every button press
    # (via navigation's frame hook) so you can watch the agent play.
    viewer = None
    if watch:
        from viewer import Viewer
        viewer = Viewer()
        navigation.FRAME_HOOK = viewer.refresh_image
        llm.WAIT_HOOK = viewer.sleep      # keep the window alive during 429 backoff

    def pace(seconds):                    # viewer-friendly pause between rounds
        (viewer.sleep if viewer else time.sleep)(seconds)

    print(f"LLM backend: {llm.BACKEND} ({llm.model_name()})")
    for _ in range(600):
        pyboy.tick()
    intro = skip_intro(pyboy)
    print(f"skip_intro: captured {len(intro)} chars of intro premise")

    # Map layer: load the notebook (accumulates across runs), register the
    # starting scene, and keep the intro premise as world knowledge.
    world = WorldMap.load(WORLD)
    cur_fp = scene_fingerprint(pyboy)
    start_id = world.seen_scene(cur_fp, player_position(pyboy))
    if intro:
        world.add_knowledge(intro)
    if viewer:
        viewer.set_overlay(scene=start_id, scenes=world.scene_count,
                           edges=world.edge_count)

    # Mini-map perception: one local occupancy map per scene, built from moves.
    rooms = {}
    probed = {}   # cur_fp -> set of tiles already interact-probed on a bump
    read = set()  # landmark ids already interacted with (so we act, not re-read)
    log = []      # recent (intent-label, result) for the state
    subgoal = ""  # the LLM's running plan toward the goal (it maintains this)

    try:
      for r in range(1, rounds + 1):
        # A dialog is blocking - read it fully into memory (it may hold hints),
        # then it's cleared. Passively-triggered NPC lines land here.
        if dialog_open(pyboy):
            heard = read_dialog(pyboy)
            if heard:
                world.add_fact(cur_fp, heard)
                log.append(("(heard)", heard[:44]))
                print(f"[{r:02d}] (heard) -> {heard[:70]!r}")
            continue

        rooms.setdefault(cur_fp, RoomMap()).mark_floor(player_tile(pyboy))
        state = build_state(world, rooms, cur_fp, pyboy, log, subgoal, read)
        intent = plan_intent(state)
        if intent is None:                      # planner failed -> just explore
            intent = {"action": "explore", "target": "", "note": "",
                      "subgoal": "", "why": "fallback"}
        if intent["subgoal"]:                   # the LLM maintains its own plan
            subgoal = intent["subgoal"]

        action, target = intent["action"], intent["target"]
        if action == "explore":
            result, cur_fp = skill_explore(pyboy, world, rooms, probed, cur_fp)
        elif action == "go_to":
            result, cur_fp = skill_go_to(pyboy, world, cur_fp, target)
        elif action == "interact":
            result, cur_fp = skill_interact(pyboy, world, cur_fp, target, read)
        else:  # remember
            result = skill_remember(world, cur_fp, intent["note"])

        label = action + (f" {target}" if target else "")
        log.append((label, result))
        pyboy.screen.image.save(OUT / f"intent_{r:02d}_{action}.png")
        why = str(intent.get("why", ""))[:48]
        print(f"[{r:02d}] day{game_day(pyboy)} {label:14s} why={why!r}\n"
              f"      plan={subgoal[:48]!r} -> {result}")
        if viewer:
            viewer.set_overlay(round=r, day=game_day(pyboy), intent=label,
                               result=result[:38], scene=world.scene_id(cur_fp),
                               scenes=world.scene_count, edges=world.edge_count)
        if delay:
            pace(delay)                      # slow the loop down so a watcher can follow

    finally:
        world.save(WORLD)                    # persist the notebook even on a crash
    print(f"\nScreenshots in {OUT}/")
    print(f"map: {world.scene_count} scene(s), {world.edge_count} connection(s), "
          f"{world.landmark_count} landmark(s) -> {WORLD}")
    if viewer:
        print("Close the viewer window to exit.")
        viewer.wait_close()
    pyboy.stop(save=False)               # never overwrite the user's battery .ram


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Explore Deadeus with the agent.")
    parser.add_argument("--watch", action="store_true",
                        help="open a live window with a perception/decision overlay")
    parser.add_argument("--rounds", type=int, default=INTENT_ROUNDS,
                        help=f"number of intent rounds to run (default {INTENT_ROUNDS})")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="seconds to pause after each round so a watcher can follow")
    args = parser.parse_args()
    main(watch=args.watch, rounds=args.rounds, delay=args.delay)
