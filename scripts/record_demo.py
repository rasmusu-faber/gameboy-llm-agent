"""Record a GIF of the agent playing, with its reasoning overlaid, for the README.

Drives the real agent loop (src/agent.py:main) exactly like --watch does, but
instead of a Tkinter window, a RecordingViewer (duck-typed to the same
set_overlay/refresh_image/sleep interface as viewer.Viewer) renders each sampled
frame - the game screen plus a text panel of round, day, the LLM's chosen intent,
its stated reasoning ("why"), its running plan ("subgoal"), and the skill's result
- straight to a PNG. agent.plan_intent is monkeypatched (not modified) to capture
why/subgoal, since agent.main() itself only forwards intent/result to the overlay.
Frames are assembled into a GIF with ffmpeg's two-pass palette (palettegen /
paletteuse) - much better quality and a smaller file than Pillow's built-in GIF
encoder for pixel art.

Requires ffmpeg on PATH. Run from the repo root:
    python scripts/record_demo.py --rounds 20 --max-frames 400
"""

import argparse
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import navigation  # noqa: E402
import agent  # noqa: E402
import viewer as viewer_module  # noqa: E402

GB_W, GB_H = 160, 144
FRAME_DIR = ROOT / "runs" / "gif_frames"   # under runs/, already git-ignored
OUT_GIF = ROOT / "docs" / "demo.gif"

# Fixed display order for the overlay panel (missing fields just render blank).
OVERLAY_FIELDS = ["round", "day", "intent", "why", "plan", "result", "scene", "scenes", "edges"]

# ImageFont.load_default() only covers latin-1: the LLM's own text occasionally
# uses smart punctuation (en/em dash, curly quotes, ellipsis) outside that range,
# which renders as a blank tofu box. Normalize the common cases before drawing.
_ASCII_PUNCT = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...",
})


def _to_ascii(text):
    return text.translate(_ASCII_PUNCT).encode("ascii", "replace").decode("ascii")


class RecordingViewer:
    """Stands in for viewer.Viewer so agent.main(watch=True) drives it exactly
    like the live window, but renders straight to PNGs instead of Tk. `why` and
    `subgoal` are read from a dict the caller keeps updated (see plan_intent
    monkeypatch below) - agent.main()'s own set_overlay() calls don't carry them."""

    PANEL_W = 300
    LINE_H = 17

    def __init__(self, out_dir, scale, sample_every, max_frames, live_intent):
        self.out_dir = out_dir
        self.scale = scale
        self.sample_every = sample_every
        self.max_frames = max_frames
        self.live_intent = live_intent
        self.tick = 0
        self.saved = 0
        self._overlay = {}
        self._font = ImageFont.load_default(size=15)

    def set_overlay(self, **fields):
        self._overlay.update(fields)
        if self.live_intent.get("why"):
            self._overlay["why"] = self.live_intent["why"]
        if self.live_intent.get("subgoal"):
            self._overlay["plan"] = self.live_intent["subgoal"]

    def refresh_image(self, pyboy):
        if self.saved >= self.max_frames:          # capped - stop writing, let the run finish
            return
        self.tick += 1
        if self.tick % self.sample_every:
            return
        game = pyboy.screen.image.resize(
            (GB_W * self.scale, GB_H * self.scale), resample=Image.Resampling.NEAREST
        ).convert("RGB")
        canvas = Image.new("RGB", (game.width + self.PANEL_W, game.height), "#111111")
        canvas.paste(game, (0, 0))
        draw = ImageDraw.Draw(canvas)
        y = 10
        for key in OVERLAY_FIELDS:
            value = _to_ascii(str(self._overlay.get(key, ""))[:160])
            for line in textwrap.wrap(f"{key}: {value}", width=36) or [f"{key}:"]:
                draw.text((game.width + 10, y), line, fill="#eeeeee", font=self._font)
                y += self.LINE_H
            y += 5
        canvas.save(self.out_dir / f"f_{self.saved:05d}.png")
        self.saved += 1

    def sleep(self, seconds):
        time.sleep(seconds)

    def wait_close(self):
        pass


def record(rounds, sample_every, scale, fps, max_frames, out_gif=OUT_GIF):
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH - install it (or add it to PATH) and retry.")

    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    for f in FRAME_DIR.glob("*.png"):
        f.unlink()

    # Capture the LLM's per-round reasoning: agent.main() only ever forwards the
    # action label + result to set_overlay, never why/subgoal, so intercept the
    # planner call itself rather than touching agent.py.
    live_intent = {}
    real_plan_intent = agent.plan_intent

    def plan_intent_capture(state):
        intent = real_plan_intent(state)
        if intent:
            live_intent.clear()
            live_intent.update(intent)
        return intent

    agent.plan_intent = plan_intent_capture

    rv = RecordingViewer(FRAME_DIR, scale, sample_every, max_frames, live_intent)
    viewer_module.Viewer = lambda *a, **kw: rv     # agent.main() calls Viewer() with no args

    # Don't burn the frame budget on skip_intro's long click-through-text marathon -
    # suspend whichever hook is active (here: rv.refresh_image) until real play starts.
    real_skip_intro = agent.skip_intro

    def skip_intro_then_arm(pyboy, *a, **kw):
        saved_hook = navigation.FRAME_HOOK
        navigation.FRAME_HOOK = None
        intro = real_skip_intro(pyboy, *a, **kw)
        navigation.FRAME_HOOK = saved_hook
        return intro

    agent.skip_intro = skip_intro_then_arm

    print(f"Running the agent for {rounds} rounds, capturing every {sample_every}th "
          f"tick after the intro (capped at {max_frames} frames ~= {max_frames / fps:.0f}s)...")
    try:
        agent.main(watch=True, rounds=rounds)      # watch=True routes FRAME_HOOK to rv
    finally:
        navigation.FRAME_HOOK = None
        agent.plan_intent = real_plan_intent
        agent.skip_intro = real_skip_intro

    saved = rv.saved
    print(f"Captured {saved} frames ({saved / fps:.1f}s of GIF at {fps} fps).")
    if saved == 0:
        sys.exit("No frames captured - the agent never pressed a button?")
    if saved >= max_frames:
        print("Hit --max-frames before the run finished - the GIF only covers the "
              "start of this run. Raise --max-frames, or lower --sample-every/--rounds "
              "for a shorter session, to cover more.")

    print("Encoding GIF with ffmpeg (two-pass palette)...")
    out_gif = Path(out_gif)
    out_gif.parent.mkdir(parents=True, exist_ok=True)
    palette = FRAME_DIR / "palette.png"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(FRAME_DIR / "f_%05d.png"),
         "-vf", "palettegen=stats_mode=diff", "-update", "1", str(palette)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(FRAME_DIR / "f_%05d.png"),
         "-i", str(palette), "-lavfi", "paletteuse=dither=bayer", str(out_gif)],
        check=True,
    )

    shutil.rmtree(FRAME_DIR)
    size_kb = out_gif.stat().st_size / 1024
    print(f"Wrote {out_gif} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=10,
                         help="intent rounds to run (default 10)")
    parser.add_argument("--sample-every", type=int, default=4,
                         help="capture every Nth engine tick - lower is smoother "
                              "but bigger (default 4)")
    parser.add_argument("--scale", type=int, default=3,
                         help="upscale factor, GB screen is 160x144 (default 3)")
    parser.add_argument("--fps", type=int, default=12,
                         help="output GIF frame rate (default 12)")
    parser.add_argument("--max-frames", type=int, default=200,
                         help="cap on captured frames, bounds GIF length regardless "
                              "of --rounds (default 200, ~17s at 12fps)")
    parser.add_argument("--out", type=Path, default=OUT_GIF,
                         help=f"output GIF path (default {OUT_GIF})")
    args = parser.parse_args()
    record(args.rounds, args.sample_every, args.scale, args.fps, args.max_frames, args.out)
