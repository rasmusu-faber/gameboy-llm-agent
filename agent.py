"""Planner/controller agent.

The LLM decides WHERE to go next (a high-level judgement call); deterministic
code (navigation.walk_*) does the reliable tile-by-tile moving. This replaces the
earlier tile-by-tile LLM navigation, which small models handled unreliably - the
A/B test showed both 3B models mis-stepping and getting stuck (see the README
design log). The planner is intentionally simple for now (open exploration); it
is the seam where a real goal + memory will plug in later.
"""

import argparse
import json
from pathlib import Path

import ollama
from pyboy import PyBoy

from perception import (
    player_position, player_tile, dialog_open, visible_dialog_text,
    scene_fingerprint,
)
import navigation
from navigation import press, walk_direction
from memory import WorldMap
from roommap import RoomMap

ROM = "roms/Deadeus.gb"
MODEL = "llama3.2:3b"
DIRECTIONS = ["up", "down", "left", "right"]
STEP_TILES = 1                          # walk this far per move (small => visits
                                        # the room interior, not just the edges)
ROUNDS = 60
OUT = Path("runs/explore")
WORLD = Path("memory/world.md")   # persistent notebook (git-ignored)

PLAN_SYSTEM = (
    "You control a boy in a Game Boy game. GOAL: find the way out of the room you "
    "are in and leave it. Doors are gaps on the EDGES of the room, never in the "
    "middle.\n"
    "Each turn you get a local map (up = north):\n"
    "  @ = you   . = floor you have seen   # = wall   ? = not explored yet\n"
    "STRATEGY:\n"
    "1. Move toward '?' unknown tiles to explore, and toward the room's walls "
    "(#) - the door is a gap in a wall.\n"
    "2. When you reach a wall, move ALONG it one step at a time and try stepping "
    "THROUGH it; the door is the spot where you pass instead of being blocked.\n"
    "3. Avoid pacing back and forth over '.' tiles you have already seen.\n"
    "Each turn pick ONE direction: up, down, left, right.\n"
    "'tiles moved' = 0 means a WALL that way; if a known exit is listed, walk it.\n"
    'Respond ONLY as JSON: {"direction": "<up|down|left|right>"}'
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


def _recent_str(recent):
    """Render recent (direction, tiles_moved) pairs, flagging walls."""
    if not recent:
        return "none yet"
    return ", ".join(f"{d}->{m} tiles{' (WALL)' if m == 0 else ''}"
                     for d, m in recent)


def plan_direction(recent, exits, minimap, adjacent):
    """Planner (LLM): choose a direction toward the exit. Returns a valid
    direction, or None if the model didn't produce one.

    recent:   list of (direction, tiles_moved) for the last few moves.
    exits:    known (direction, target) exits from the current room (may be empty).
    minimap:  ASCII local occupancy map (RoomMap.render).
    adjacent: dict direction -> 'wall'|'floor'|'unknown' around the player.
    """
    exits_str = (", ".join(f"{d} -> room {t}" for d, t in exits)
                 if exits else "none discovered yet - you must find one")
    adj_str = ", ".join(f"{d}={s}" for d, s in adjacent.items())
    state = (f"Local map:\n{minimap}\n"
             f"Adjacent tiles: {adj_str}.\n"
             f"Recent moves (direction -> tiles moved): {_recent_str(recent)}.\n"
             f"Known exits from this room: {exits_str}.")
    resp = ollama.chat(
        model=MODEL,
        messages=[{"role": "system", "content": PLAN_SYSTEM},
                  {"role": "user", "content": state}],
        format="json",
    )
    try:
        content = json.loads(resp["message"]["content"])
        d = str(content.get("direction", "")).lower()
    except (json.JSONDecodeError, AttributeError):
        d = ""
    return d if d in DIRECTIONS else None


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

    recent = []
    for r in range(1, ROUNDS + 1):
        # If a dialog interrupts, read it and advance - deterministic.
        if dialog_open(pyboy):
            text = visible_dialog_text(pyboy).replace("\n", " / ")
            print(f"[{r:02d}] dialog: {text!r} -> A")
            if viewer:
                viewer.set_overlay(round=r, dialog=text[:40] or "(…)")
            press(pyboy, "a")
            continue

        x, y = player_position(pyboy)
        room = rooms.setdefault(cur_fp, RoomMap())
        ptile = player_tile(pyboy)
        room.mark_floor(ptile)
        exits = world.exits_from(cur_fp)
        if viewer:
            viewer.set_overlay(round=r, pos=f"({x},{y})", dialog="",
                               exits=len(exits))
        d = plan_direction(recent[-4:], exits, room.render(ptile),
                           room.adjacent(ptile))
        if d is None:                       # planner failed -> pick an untried dir
            tried = [rd for rd, _ in recent[-2:]]
            d = next((c for c in DIRECTIONS if c not in tried), "up")
            note = " (fallback)"
        else:
            note = ""

        moved = walk_direction(pyboy, d, max_tiles=STEP_TILES)  # controller
        recent.append((d, moved))
        room.observe(ptile, player_tile(pyboy), d, moved)   # learn floor/wall
        nx, ny = player_position(pyboy)
        pyboy.screen.image.save(OUT / f"round_{r:02d}_{d}.png")

        # Map layer (code-filled): if the scene fingerprint changed, this move
        # crossed into another room - record the node and the directed edge.
        new_fp = scene_fingerprint(pyboy)
        scene_note = ""
        cur_id = None
        if new_fp != cur_fp:
            cur_id = world.seen_scene(new_fp, (nx, ny))
            world.connect(cur_fp, d, new_fp)
            cur_fp = new_fp
            scene_note = " [entered a new room]"
        print(f"[{r:02d}] at ({x:3d},{y:3d}) plan={d:5s}{note} "
              f"walked {moved:2d} -> ({nx:3d},{ny:3d}){scene_note}")
        if viewer:
            viewer.set_overlay(pos=f"({nx},{ny})", plan=d,
                               scenes=world.scene_count, edges=world.edge_count,
                               **({"scene": cur_id} if cur_id else {}))

    world.save(WORLD)
    print(f"\nScreenshots in {OUT}/")
    print(f"map: {world.scene_count} scene(s), {world.edge_count} connection(s) "
          f"-> {WORLD}")
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
