"""Optional live viewer: watch the agent play, with a perception/decision overlay.

Off by default (the agent runs headless for speed). When enabled it opens a
Tkinter window showing the upscaled Game Boy screen plus live overlay text -
position, current scene, the planner's last decision, and map growth - so you
follow not just WHERE the agent is but WHAT it perceives and decides.

Uses only tkinter (stdlib) + Pillow's ImageTk (Pillow is already a dependency).
The image refreshes on every button press via navigation.FRAME_HOOK (smooth
motion); the overlay facts are pushed by the agent loop once per decision.
"""

import time
import tkinter as tk

from PIL import ImageTk

GB_W, GB_H = 160, 144
SCALE = 3  # 3x -> 480x432, comfortable to watch


class Viewer:
    def __init__(self, title="gameboy-llm-agent — live"):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.resizable(False, False)

        self._img_label = tk.Label(self.root, bd=0)
        self._img_label.pack(side="left")

        self._info = tk.Label(
            self.root, justify="left", anchor="nw", font=("Consolas", 11),
            width=30, padx=10, pady=10, bg="#111", fg="#eee",
        )
        self._info.pack(side="right", fill="both", expand=True)

        self._photo = None          # keep a ref so Tk doesn't GC the image
        self._overlay: dict = {}

    def set_overlay(self, **fields) -> None:
        """Merge overlay facts (e.g. round, pos, scene, plan, scenes, edges)."""
        self._overlay.update(fields)
        self._render_info()

    def refresh_image(self, pyboy) -> None:
        """Grab the current frame and repaint. Safe to call very often."""
        img = pyboy.screen.image.resize((GB_W * SCALE, GB_H * SCALE))
        self._photo = ImageTk.PhotoImage(img)
        self._img_label.configure(image=self._photo)
        self.root.update()          # process events without blocking (no mainloop)

    def _render_info(self) -> None:
        text = "\n".join(f"{k:>7}: {v}" for k, v in self._overlay.items())
        self._info.configure(text=text)
        self.root.update_idletasks()

    def sleep(self, seconds: float) -> None:
        """Sleep while keeping the window responsive. A plain time.sleep on the
        main thread would freeze Tk and Windows paints the frozen window WHITE - so
        during any wait (the 429 backoff, or --delay pacing) pump the event loop in
        small slices instead of blocking."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                self.root.update()
            except tk.TclError:
                return
            time.sleep(0.03)

    def wait_close(self) -> None:
        """Keep the window open until the user closes it (call at run end)."""
        try:
            self.root.mainloop()
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass
