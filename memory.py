"""Agent memory — Map layer (the code-filled part of the notebook).

Design (see README design log): memory is a Markdown notebook the agent reads
and writes as it plays. Writing is split along the architecture principle:
deterministic code writes what it *measures*, the LLM writes what it *interprets*.

This module is only the first, code-filled piece: a **map** built from things
the code can measure without any judgement — the scene fingerprint
(perception.scene_fingerprint) and the player position. A scene is a node; a
move that changes the fingerprint is a directed edge (from_scene --dir--> to).

Kept deliberately emulator-free: it takes plain fingerprint ints and positions,
so it round-trips and unit-tests without a ROM. The agent loop is the glue that
reads perception and feeds this store.

Persisted as a `## Map` block inside world.md, between HTML markers so the code
can rewrite it idempotently without disturbing any other section.
"""

import re
from pathlib import Path

MAP_START = "<!-- MAP:START -->"
MAP_END = "<!-- MAP:END -->"

_SCENE_RE = re.compile(r"- (s\d+)\s+fp=([0-9a-f]+)\s+pos=\((\d+),\s*(\d+)\)")
_EDGE_RE = re.compile(r"- (s\d+) --(\w+)--> (s\d+)")


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
        # fp_key -> {"id": "s0", "pos": (x, y)}   (insertion order = discovery order)
        self._scenes: dict[str, dict] = {}
        # set of (from_key, direction, to_key)
        self._edges: set[tuple[str, str, str]] = set()

    def seen_scene(self, fp: int, pos: tuple[int, int]) -> str:
        """Register the current scene (idempotent). Returns its short id (s0, s1...)."""
        key = fp_key(fp)
        if key not in self._scenes:
            self._scenes[key] = {"id": f"s{len(self._scenes)}", "pos": tuple(pos)}
        return self._scenes[key]["id"]

    @property
    def scene_count(self) -> int:
        return len(self._scenes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def exits_from(self, fp: int) -> list[tuple[str, str]]:
        """Known exits out of scene `fp`: list of (direction, target scene id).

        Empty for an unexplored room; grows as the agent discovers edges.
        """
        fk = fp_key(fp)
        id_of = {k: s["id"] for k, s in self._scenes.items()}
        return sorted((d, id_of[tk]) for (a, d, tk) in self._edges if a == fk)

    def connect(self, from_fp: int, direction: str, to_fp: int) -> None:
        """Record a directed transition from_scene --direction--> to_scene.

        Both scenes must have been seen first (the caller measures both). No-op
        if the edge is already known, so replaying the same path stays clean.
        """
        fk, tk = fp_key(from_fp), fp_key(to_fp)
        if fk not in self._scenes or tk not in self._scenes:
            raise KeyError("connect() needs both scenes registered via seen_scene()")
        self._edges.add((fk, direction, tk))

    # --- rendering / persistence -------------------------------------------

    def render_block(self) -> str:
        """The Map section body (between the markers), deterministically ordered."""
        lines = []
        for key, s in self._scenes.items():
            x, y = s["pos"]
            lines.append(f"- {s['id']}  fp={key}  pos=({x}, {y})")
        if self._edges:
            lines.append("")
            lines.append("Connections:")
            id_of = {k: s["id"] for k, s in self._scenes.items()}
            for fk, d, tk in sorted(self._edges, key=lambda e: (id_of[e[0]], e[1])):
                lines.append(f"- {id_of[fk]} --{d}--> {id_of[tk]}")
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
        m = re.search(rf"{re.escape(MAP_START)}(.*?){re.escape(MAP_END)}", text, re.DOTALL)
        if not m:
            return wm
        block = m.group(1)
        # id -> fingerprint int, so we can rebuild edges after all scenes exist.
        id_to_fp: dict[str, int] = {}
        for sid, key, x, y in _SCENE_RE.findall(block):
            fp = int(key, 16)
            wm._scenes[key] = {"id": sid, "pos": (int(x), int(y))}
            id_to_fp[sid] = fp
        for a, d, b in _EDGE_RE.findall(block):
            wm._edges.add((fp_key(id_to_fp[a]), d, fp_key(id_to_fp[b])))
        return wm
