"""Intent-driven agent: LLM orchestrator over a library of deterministic skills.

The LLM no longer steers tile-by-tile (a 3B does that unreliably - see the design
log). Instead it picks ONE high-level *intent* per turn - explore, go_to,
interact, remember - and a deterministic skill carries it out to completion. This
is the tool-use / planner-controller split done properly: the LLM makes judgement
calls, code does the reflexes. See docs/action-vocabulary.md.
"""

import argparse
from pathlib import Path

from pyboy import PyBoy

from perception import (
    player_position, player_tile, dialog_open, scene_fingerprint,
)
import navigation
from navigation import (
    press, walk_direction, walk_to, interact, dismiss_dialog, read_dialog,
    advance_cutscene, TILE,
)
from memory import WorldMap
from roommap import RoomMap
import llm

_DELTA = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

ROM = "roms/Deadeus.gb"
INTENT_ROUNDS = 15                      # one LLM judgement call per round
EXPLORE_BUDGET = 25                     # max tiles a single explore intent walks
SKILLS = ("explore", "go_to", "interact", "remember")
GOAL = ("Explore as MUCH of the house as possible: fully map every room, read "
        "every object and person you find, and once a room is fully explored move "
        "on through a known exit to discover NEW rooms. Maximise what you uncover.")
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
    "- interact <id> : examine or talk to a known landmark (read its text).\n"
    "- remember <note> : write down a short conclusion worth keeping.\n"
    "Decide from the state you are given (known exits, landmarks, whether the "
    "room is fully explored, your goal). Prefer explore while the room is not "
    "fully mapped; interact with landmarks you have not read. IMPORTANT: if the "
    "room is ALREADY fully explored, do NOT keep choosing explore (it does "
    "nothing) - go_to a connected room to explore somewhere new.\n"
    'Respond ONLY as JSON: {"action":"explore|go_to|interact|remember",'
    '"target":"<id or empty>","note":"<for remember>","why":"<short reason>"}'
)


def _reversible_move(pyboy, fwd, back):
    """True if pressing fwd changes the player position and back returns it -
    i.e. real player control, not a cutscene animation."""
    p0 = player_position(pyboy)
    press(pyboy, fwd)
    p1 = player_position(pyboy)
    press(pyboy, back)
    return p1 != p0 and player_position(pyboy) == p0


def skip_intro(pyboy, max_steps=600):
    """Deterministic: click through the title + intro into the movable game.

    Press A while a dialog is on-screen; detect arrival with a reversible
    movement test. Movement tests start only after the title menu, so a direction
    never nudges a menu cursor. Returns the step it arrived on, or None.
    """
    press(pyboy, "start")
    streak = 0
    for step in range(1, max_steps + 1):
        if dialog_open(pyboy):
            streak = 0
            press(pyboy, "a")
        else:
            streak += 1
            if step > 20 and streak >= 3 and (
                _reversible_move(pyboy, "right", "left")
                or _reversible_move(pyboy, "down", "up")
            ):
                return step
            press(pyboy, "a")
    return None


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
    """Walk toward the nearest unexplored tile until a new room is entered, an
    area is fully mapped, or the budget runs out. Objects bumped along the way
    are auto-detected as landmarks. Returns (summary, current_fp)."""
    room = rooms.setdefault(cur_fp, RoomMap())
    found = []
    for _ in range(EXPLORE_BUDGET):
        ptile = player_tile(pyboy)
        room.mark_floor(ptile)
        frontier = room.nearest_frontier(ptile)
        if frontier is None:
            return f"explored; room fully mapped{_join(found)}", cur_fp
        moved = walk_direction(pyboy, frontier, max_tiles=1)
        room.observe(ptile, player_tile(pyboy), frontier, moved)
        if moved == 0:
            note = _auto_detect(pyboy, world, rooms, probed, cur_fp, frontier, ptile)
            if note:
                found.append(note)
        if scene_fingerprint(pyboy) != cur_fp:
            heard = advance_cutscene(pyboy)   # play any entry scene until movable
            new_fp = scene_fingerprint(pyboy)  # read the SETTLED room now
            nid = world.seen_scene(new_fp, player_position(pyboy))
            world.note_crossing(cur_fp, frontier, new_fp,
                                door_tile=ptile, spawn_tile=player_tile(pyboy))
            if heard:
                world.add_fact(new_fp, heard)  # the entry dialogue -> hints
            note = f" (scene: {heard[:24]!r})" if heard else ""
            return f"explored; entered a new room ({nid}){_join(found)}{note}", new_fp
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
            return f"go_to: tried to reach {target} but didn't cross", cur_fp
    return f"go_to: '{target}' isn't a known landmark or connected room", cur_fp


def skill_interact(pyboy, world, cur_fp, target):
    """Walk up to a known landmark, face it, and read its FULL dialogue.

    Two-stream model: the conversation goes to the scene's facts (the "heard"
    stream), never overwriting the landmark's first-contact descriptor - so an
    NPC's unfolding lines don't get baked into its identity, only into memory.
    """
    lm = world.find_landmark(target) if target else None
    if not lm:
        return f"interact: '{target}' isn't a known landmark", cur_fp
    if lm["scene"] != world.scene_id(cur_fp):
        return f"interact: {target} is in another room", cur_fp
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

def build_state(world, rooms, cur_fp, pyboy, log):
    """The intent-level state the LLM chooses from (not raw (x, y))."""
    cur_id = world.scene_id(cur_fp)
    label = world.label_of(cur_fp)
    room_name = cur_id + (f" ({label})" if label else "")
    exits = world.exits_detailed(cur_fp)
    exits_str = "; ".join(f"{d} -> {tid}" for d, tid, _ in exits) or "none known yet"
    lms = world.landmarks_of(cur_fp)
    lm_str = "; ".join(f'{lm["id"]} @ {lm["tile"]}: "{lm["text"]}"'
                       for lm in lms) or "none yet"
    facts = world.facts_of(cur_fp)
    facts_str = " | ".join(facts) or "none yet"
    room = rooms.get(cur_fp)
    if room is None:
        explored = "not yet (just arrived)"
    else:
        explored = ("partially - unexplored tiles remain"
                    if room.nearest_frontier(player_tile(pyboy)) else "fully")
    recent = "; ".join(f"{a} -> {res}" for a, res in log[-4:]) or "nothing yet"
    return (f"Current room: {room_name}\n"
            f"Known exits: {exits_str}\n"
            f"Landmarks here (things you've read): {lm_str}\n"
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
            "why": str(c.get("why", "")).strip()}


def main(watch=False):
    OUT.mkdir(parents=True, exist_ok=True)
    pyboy = PyBoy(ROM, window="null")

    # Optional live viewer: open a window and refresh it on every button press
    # (via navigation's frame hook) so you can watch the agent play.
    viewer = None
    if watch:
        from viewer import Viewer
        viewer = Viewer()
        navigation.FRAME_HOOK = viewer.refresh_image

    print(f"LLM backend: {llm.BACKEND} ({llm.model_name()})")
    for _ in range(600):
        pyboy.tick()
    print(f"skip_intro: reached the game at step {skip_intro(pyboy)}")

    # Map layer: load the notebook (accumulates across runs), register the
    # starting scene, and track the current scene fingerprint so a change after
    # a move becomes a directed edge.
    world = WorldMap.load(WORLD)
    cur_fp = scene_fingerprint(pyboy)
    start_id = world.seen_scene(cur_fp, player_position(pyboy))
    if viewer:
        viewer.set_overlay(scene=start_id, scenes=world.scene_count,
                           edges=world.edge_count)

    # Mini-map perception: one local occupancy map per scene, built from moves.
    rooms = {}
    probed = {}   # cur_fp -> set of tiles already interact-probed on a bump
    log = []      # recent (intent-label, result) for the state

    for r in range(1, INTENT_ROUNDS + 1):
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
        state = build_state(world, rooms, cur_fp, pyboy, log)
        intent = plan_intent(state)
        if intent is None:                      # planner failed -> just explore
            intent = {"action": "explore", "target": "", "note": "",
                      "why": "fallback"}

        action, target = intent["action"], intent["target"]
        if action == "explore":
            result, cur_fp = skill_explore(pyboy, world, rooms, probed, cur_fp)
        elif action == "go_to":
            result, cur_fp = skill_go_to(pyboy, world, cur_fp, target)
        elif action == "interact":
            result, cur_fp = skill_interact(pyboy, world, cur_fp, target)
        else:  # remember
            result = skill_remember(world, cur_fp, intent["note"])

        label = action + (f" {target}" if target else "")
        log.append((label, result))
        pyboy.screen.image.save(OUT / f"intent_{r:02d}_{action}.png")
        print(f"[{r:02d}] {label:14s} why={intent['why'][:36]!r} -> {result}")
        if viewer:
            viewer.set_overlay(round=r, intent=label, result=result[:38],
                               scene=world.scene_id(cur_fp),
                               scenes=world.scene_count, edges=world.edge_count)

    world.save(WORLD)
    print(f"\nScreenshots in {OUT}/")
    print(f"map: {world.scene_count} scene(s), {world.edge_count} connection(s), "
          f"{world.landmark_count} landmark(s) -> {WORLD}")
    if viewer:
        print("Close the viewer window to exit.")
        viewer.wait_close()
    pyboy.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Explore Deadeus with the agent.")
    parser.add_argument("--watch", action="store_true",
                        help="open a live window with a perception/decision overlay")
    args = parser.parse_args()
    main(watch=args.watch)
