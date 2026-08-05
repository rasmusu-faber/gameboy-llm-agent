"""Agent memory — Map layer (the code-filled part of the notebook).

Design (see docs/design-log.md): memory is a Markdown notebook the agent reads
and writes as it plays. Writing is split along the architecture principle:
deterministic code writes what it *measures*, the LLM writes what it *interprets*.

The **map** is built from things the code can measure without judgement — the
scene fingerprint (perception.scene_fingerprint) and the player position. A scene
is a node; a move that changes the fingerprint is a directed edge
(from_scene --dir--> to), and each edge remembers the **door tile** it was crossed
from, so navigation can later walk back to that exit (see docs/action-vocabulary).
Entering a room also records the **reverse edge** (the way back), which is why the
only known exit is often the entrance.

Each node also reserves an optional **label** (a human name for the scene, e.g.
"church") and **facts** (things learned there). These are the *interpreted* layer:
code leaves them empty; they get filled from read text, a rare vision glance, or
LLM inference (grounding — see the design doc). Keeping the stable fingerprint id
separate from the discovered label is the clean way to map "go to the church" onto
an anonymous scene id.

Kept deliberately emulator-free: it takes plain fingerprint ints, positions, and
tiles, so it round-trips and unit-tests without a ROM. The agent loop is the glue
that reads perception and feeds this store.

Persisted as a `## Map` block inside world.md, between HTML markers so the code
can rewrite it idempotently without disturbing any other section.
"""

import re
from pathlib import Path

MAP_START = "<!-- MAP:START -->"
MAP_END = "<!-- MAP:END -->"

OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}

_SCENE_RE = re.compile(
    r"- (s\d+)\s+fp=([0-9a-f]+)\s+pos=\((\d+),\s*(\d+)\)(?:\s+label=\"([^\"]*)\")?")
_FACT_RE = re.compile(r"^\s+fact: (.*)$")
_LANDMARK_RE = re.compile(r"^\s+landmark: (l\d+) @ \((-?\d+),\s*(-?\d+)\): (.*)$")
_EDGE_RE = re.compile(
    r"- (s\d+) --(\w+)--> (s\d+)(?:\s+door=\((-?\d+),\s*(-?\d+)\))?")


def fp_key(fp: int) -> str:
    """Canonical, stable text key for a scene fingerprint.

    scene_fingerprint() returns a Python int (possibly negative); normalise it
    to an unsigned 64-bit hex string so the same scene reads identically across
    runs and in the notebook.
    """
    return f"{fp & 0xFFFFFFFFFFFFFFFF:016x}"


class WorldMap:
    """Scenes seen and how they connect. Nodes keyed by canonical fingerprint."""

    def __init__(self):
        # fp_key -> {"id", "pos", "label": str|None, "facts": [str], "landmarks": [dict]}
        # (insertion order = discovery order)
        self._scenes: dict[str, dict] = {}
        # (from_key, direction, to_key) -> door tile (x, y) | None
        self._edges: dict[tuple[str, str, str], tuple | None] = {}
        self._next_landmark = 0             # global l0, l1, … id counter

    def seen_scene(self, fp: int, pos: tuple[int, int]) -> str:
        """Register the current scene (idempotent). Returns its short id (s0, s1...)."""
        key = fp_key(fp)
        if key not in self._scenes:
            self._scenes[key] = {"id": f"s{len(self._scenes)}", "pos": tuple(pos),
                                 "label": None, "facts": [], "landmarks": []}
        return self._scenes[key]["id"]

    @property
    def scene_count(self) -> int:
        return len(self._scenes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    @property
    def landmark_count(self) -> int:
        return sum(len(s["landmarks"]) for s in self._scenes.values())

    def scene_id(self, fp: int) -> str:
        return self._scenes[fp_key(fp)]["id"]

    def exits_from(self, fp: int) -> list[tuple[str, str]]:
        """Known exits out of scene `fp`: list of (direction, target scene id).

        Empty for an unexplored room; grows as the agent discovers edges.
        """
        fk = fp_key(fp)
        id_of = {k: s["id"] for k, s in self._scenes.items()}
        return sorted((d, id_of[tk]) for (a, d, tk) in self._edges if a == fk)

    def exits_detailed(self, fp: int) -> list[tuple[str, str, tuple | None]]:
        """Exits out of `fp` as (direction, target scene id, door tile | None)."""
        fk = fp_key(fp)
        id_of = {k: s["id"] for k, s in self._scenes.items()}
        return sorted(((d, id_of[tk], door)
                       for (a, d, tk), door in self._edges.items() if a == fk),
                      key=lambda e: e[0])

    def door_tile(self, from_fp: int, direction: str, to_fp: int):
        """The tile in `from_fp` that this exit was crossed from, or None."""
        return self._edges.get((fp_key(from_fp), direction, fp_key(to_fp)))

    def connect(self, from_fp: int, direction: str, to_fp: int, door_tile=None) -> None:
        """Record a directed transition from_scene --direction--> to_scene.

        Both scenes must have been seen first (the caller measures both). Idempotent
        on the edge; a later call may fill in a door tile a first call lacked.
        """
        fk, tk = fp_key(from_fp), fp_key(to_fp)
        if fk not in self._scenes or tk not in self._scenes:
            raise KeyError("connect() needs both scenes registered via seen_scene()")
        key = (fk, direction, tk)
        door = tuple(door_tile) if door_tile is not None else self._edges.get(key)
        self._edges[key] = door

    def note_crossing(self, from_fp: int, direction: str, to_fp: int,
                      door_tile=None, spawn_tile=None) -> None:
        """Record a room change both ways: the forward exit (from the door tile)
        and the reverse exit (back through the spawn tile, opposite direction).

        Modelling the reverse edge is what makes 'the only known exit is the
        entrance' true, and gives the agent a way home from a fresh room.
        """
        self.connect(from_fp, direction, to_fp, door_tile)
        if direction in OPPOSITE:
            self.connect(to_fp, OPPOSITE[direction], from_fp, spawn_tile)

    # --- semantic (interpreted) layer: filled later, not by geometry -------

    def set_label(self, fp: int, label: str) -> None:
        """Attach a human name to a scene (e.g. 'church'). Evidence-based only."""
        self._scenes[fp_key(fp)]["label"] = label

    def label_of(self, fp: int):
        return self._scenes[fp_key(fp)]["label"]

    def add_fact(self, fp: int, fact: str) -> None:
        """Record a single-line fact learned in this scene (no dedup of meaning)."""
        fact = " ".join(str(fact).split())      # collapse to one clean line
        facts = self._scenes[fp_key(fp)]["facts"]
        if fact and fact not in facts:
            facts.append(fact)

    def facts_of(self, fp: int) -> list[str]:
        return list(self._scenes[fp_key(fp)]["facts"])

    def add_landmark(self, fp: int, tile, text: str = "") -> str:
        """Record an interactable (object/NPC) at `tile` in scene `fp`. The text is
        a **first-contact descriptor** - a short static hint of what is there ("So
        many books", "Are you okay?"). It is set ONCE and never overwritten: a
        character's unfolding dialogue belongs in facts (add_fact), not baked into
        the landmark's identity. Keyed by tile. Returns the landmark id (l0, l1…).
        """
        scene = self._scenes[fp_key(fp)]
        tile = tuple(tile)
        text = " ".join(str(text).split())
        for lm in scene["landmarks"]:
            if lm["tile"] == tile:
                if text and not lm["text"]:     # first descriptor only
                    lm["text"] = text
                return lm["id"]
        lid = f"l{self._next_landmark}"
        self._next_landmark += 1
        scene["landmarks"].append({"id": lid, "tile": tile, "text": text})
        return lid

    def landmarks_of(self, fp: int) -> list[dict]:
        return [dict(lm) for lm in self._scenes[fp_key(fp)]["landmarks"]]

    def find_landmark(self, landmark_id: str):
        """Resolve a landmark id to {'scene', 'tile', 'text'}, or None if unknown."""
        for s in self._scenes.values():
            for lm in s["landmarks"]:
                if lm["id"] == landmark_id:
                    return {"scene": s["id"], "tile": lm["tile"], "text": lm["text"]}
        return None

    def find_by_label(self, label: str):
        """Resolve a name to a scene id (case-insensitive), or None if unknown.

        The grounding resolver: 'go to the church' works only once some scene
        actually carries that label; otherwise it's an exploration goal.
        """
        want = label.strip().lower()
        for s in self._scenes.values():
            if s["label"] and s["label"].lower() == want:
                return s["id"]
        return None

    # --- rendering / persistence -------------------------------------------

    def render_block(self) -> str:
        """The Map section body (between the markers), deterministically ordered."""
        lines = []
        for key, s in self._scenes.items():
            x, y = s["pos"]
            label = f'  label="{s["label"]}"' if s["label"] else ""
            lines.append(f"- {s['id']}  fp={key}  pos=({x}, {y}){label}")
            for fact in s["facts"]:
                lines.append(f"    fact: {fact}")
            for lm in s["landmarks"]:
                lx, ly = lm["tile"]
                lines.append(f"    landmark: {lm['id']} @ ({lx}, {ly}): {lm['text']}")
        if self._edges:
            lines.append("")
            lines.append("Connections:")
            id_of = {k: v["id"] for k, v in self._scenes.items()}
            for (fk, d, tk), door in sorted(
                    self._edges.items(), key=lambda e: (id_of[e[0][0]], e[0][1])):
                door_s = f"  door=({door[0]}, {door[1]})" if door else ""
                lines.append(f"- {id_of[fk]} --{d}--> {id_of[tk]}{door_s}")
        return "\n".join(lines) if lines else "(no scenes yet)"

    def save(self, world_path: Path) -> None:
        """Write the Map block into world.md, leaving any other sections intact."""
        world_path.parent.mkdir(parents=True, exist_ok=True)
        block = (
            "## Map\n\n"
            "Scenes discovered and how they connect (code-filled from position +\n"
            "scene fingerprint). Auto-generated between the markers.\n\n"
            f"{MAP_START}\n{self.render_block()}\n{MAP_END}\n"
        )
        if world_path.exists():
            text = world_path.read_text(encoding="utf-8")
            if MAP_START in text and MAP_END in text:
                text = re.sub(
                    rf"## Map.*?{re.escape(MAP_END)}\n?",
                    block,
                    text,
                    flags=re.DOTALL,
                )
            else:
                text = text.rstrip() + "\n\n" + block
        else:
            text = block
        world_path.write_text(text, encoding="utf-8")

    @classmethod
    def load(cls, world_path: Path) -> "WorldMap":
        """Rebuild the map from a previously saved world.md (empty if none)."""
        wm = cls()
        if not world_path.exists():
            return wm
        text = world_path.read_text(encoding="utf-8")
        m = re.search(rf"{re.escape(MAP_START)}(.*?){re.escape(MAP_END)}",
                      text, re.DOTALL)
        if not m:
            return wm
        id_to_fp: dict[str, int] = {}
        current_key = None
        max_landmark = -1
        for line in m.group(1).splitlines():
            fact = _FACT_RE.match(line)
            if fact and current_key:
                wm._scenes[current_key]["facts"].append(fact.group(1))
                continue
            lm = _LANDMARK_RE.match(line)
            if lm and current_key:
                lid, lx, ly, txt = lm.groups()
                wm._scenes[current_key]["landmarks"].append(
                    {"id": lid, "tile": (int(lx), int(ly)), "text": txt})
                max_landmark = max(max_landmark, int(lid[1:]))
                continue
            scene = _SCENE_RE.search(line)
            if scene and "-->" not in line:
                sid, key, x, y, label = scene.groups()
                wm._scenes[key] = {"id": sid, "pos": (int(x), int(y)),
                                   "label": label or None, "facts": [],
                                   "landmarks": []}
                id_to_fp[sid] = int(key, 16)
                current_key = key
                continue
            edge = _EDGE_RE.search(line)
            if edge:
                a, d, b, dx, dy = edge.groups()
                door = (int(dx), int(dy)) if dx is not None else None
                wm._edges[(fp_key(id_to_fp[a]), d, fp_key(id_to_fp[b]))] = door
        wm._next_landmark = max_landmark + 1
        return wm
