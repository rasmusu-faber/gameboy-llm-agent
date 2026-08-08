"""Manual RAM capture: YOU play, the script passively logs WRAM per screen.

Opens a real PyBoy window at 1x speed. Play with the keyboard through the outdoor
area - ESPECIALLY across the screens that look almost identical (the fingerprint
collisions). Every time the screen changes, a new "visit" is recorded with a few
WRAM snapshots at different positions. Close the window when done; the log is
written to runs/manual_scan.pkl for the scene-byte analysis.

Run from the repo root:
    conda run -n pokemon-agents python exploration/manual_scan.py

Default PyBoy keys: arrow keys = d-pad, A = key 'a', B = key 's',
Start = Enter, Select = Backspace. (Tell me if yours differ.)

Does NOT touch your battery save (stops with save=False).
"""
import pickle
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pyboy import PyBoy  # noqa: E402
import perception as P  # noqa: E402
from agent import skip_intro  # noqa: E402

ROM = str(ROOT / "roms" / "Deadeus.gb")
OUT = ROOT / "runs" / "manual_scan.pkl"
WRAM = (0xC000, 0xE000)
MAX_SAMPLES = 6            # WRAM snapshots kept per screen (at distinct positions)


def main():
    pyboy = PyBoy(ROM, window="SDL2")
    pyboy.set_emulation_speed(1)            # real time so it is playable
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)                        # start you in the bedroom, past the intro

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n>>> PLAY NOW. Walk out into the town and cross the look-alike screens.")
    print(f">>> The log is written continuously to {OUT} - just close the window when done.\n")

    visits = []                              # [{fp, samples:[(pos, wram_bytes)]}]
    cur = None
    last_fp = None
    frame = 0

    def dump():                              # persist to disk (survives a hard close)
        with open(OUT, "wb") as f:
            pickle.dump({"wram": WRAM, "visits": visits}, f)

    try:
        while pyboy.tick():
            frame += 1
            if frame % 6:                    # sample ~10x/sec, not every frame
                continue
            fp = P.scene_fingerprint(pyboy)
            pos = P.player_position(pyboy)
            if fp != last_fp:                # screen changed -> a new visit
                cur = {"fp": fp, "samples": []}
                visits.append(cur)
                last_fp = fp
                dump()                       # persist every screen transition
                print(f"  screen {len(visits):2d}: fp={fp & 0xFFFF:04x} (saved)")
            if cur and len(cur["samples"]) < MAX_SAMPLES:
                if not cur["samples"] or cur["samples"][-1][0] != pos:
                    cur["samples"].append((pos, bytes(pyboy.memory[WRAM[0]:WRAM[1]])))
            if frame % 120 == 0:             # and a periodic safety dump
                dump()
    finally:
        dump()
        fps = [f"{v['fp'] & 0xFFFF:04x}" for v in visits]
        print(f"\nsaved {len(visits)} screen-visits to {OUT}")
        print(f"fingerprints in order: {fps}")
        try:
            pyboy.stop(save=False)
        except Exception:
            pass


if __name__ == "__main__":
    main()
