# Design log — pokemon-llm-agent

A running log of the choices behind this project and why they were made, in
**chronological order** — the earliest entries capture early thinking (Pokémon
as the target, a vision-model eye) that later entries deliberately supersede.
That evolution is the point; the log is not rewritten to hide it. Dead-ends stay.

[← back to the README](../README.md)

---

- **Test bed is Deadeus, not Pokémon (yet).** The end goal is Pokémon Red, but
  its ROM is copyrighted and only legal to obtain by dumping a cartridge you
  own. Deadeus is a free, open-source Game Boy homebrew game, so it is a legal
  stand-in for building and testing the machinery.
- **Local-first with Ollama.** Free and unlimited calls for development, which
  matters because a game agent makes very many LLM calls (one per step). A
  swappable cloud backend is planned for higher-quality "real" runs.
- **Model `llama3.2:3b` for text decisions.** Chosen for RAM reasons: only
  ~5 GB was free and `llama2` (7B) needed ~8.4 GB and would not load. A modern
  3B model is also better at following the required JSON format than old 7B
  llama2 — smaller *and* more reliable here.
- **The "eye" is a vision model, not a RAM reader (for now).** A RAM reader
  needs documented memory addresses; Deadeus has none. So perception uses a
  small vision model (`moondream`, ~1.7 GB, fits in RAM). The RAM-reader
  approach is deferred to the Pokémon Red target, where the addresses are
  community-documented.
- **Approach 1 first: one VLM sees *and* decides.** Simplest wiring, RAM-
  friendly, one call per step. The alternative (moondream describes → llama3.2
  decides) is cleaner but swaps two models in tight RAM and is noticeably
  slower. If the tiny VLM proves too weak at navigation, the planned upgrade is
  a cloud vision model (e.g. Gemini Flash, free tier, multimodal) that handles
  perception and decision well without RAM limits.
- **Finding: local vision is too slow here.** Running approach 1 on this
  machine, `moondream` took *several minutes per step* (CPU inference, tight
  RAM). A game agent needs thousands of steps, so local vision is impractical
  on this hardware. The local vision code stays in the repo as a working
  reference, but perception moves to non-LLM methods below.
- **Perception without an LLM: RAM + tilemap.** Two fast, local, free signals:
  (1) a **RAM reader** finds bytes like the player's X/Y position via memory
  scanning (move, diff work RAM, keep the byte that tracks the move); (2) the
  **tilemap** exposes on-screen text. In this GB Studio game the dialog text is
  on the *window* layer and the engine streams glyphs into consecutive tiles,
  so a tile index is not a fixed character — the glyph lives in the tile's 8x8
  bitmap. Reading text therefore means matching each text tile's bitmap against
  the font once (deterministic mini-OCR, no model). The same window tilemap
  also gives a reliable screen-state signal (dialog box border tiles present or
  not), which the agent can use to know when to advance text vs. move.
- **Reaching a movable state is its own step.** Deadeus opens with a long,
  partly unskippable nightmare monologue; ~300 A-presses reliably reach the
  starting room (a movable state), verified by screenshots.
- **Robust dialog detection is deeper than expected.** A first detector keyed on
  the window-layer dialog-box tiles gave false positives: GB Studio leaves the
  box tiles in VRAM and *parks* the window off-screen (via the WX/WY position
  registers) rather than clearing it, and slides it in/out dynamically. So
  "box tiles present" and even "window enabled" are not sufficient - you must
  catch WY in the on-screen range at the right frame. Deferred as its own task;
  for now the intro is cleared with a fixed scripted A-press preamble.
- **Leaning toward Deadeus as the primary target, not just a test bed.** It is
  fully legal and open-source, which makes the project far easier to publish
  and share than anything tied to a Pokémon ROM. The RAM-reader and tilemap
  techniques are the same skills either way; Pokémon Red becomes an optional
  later target rather than the goal.
- **RAM scan works once movement is real.** With the scripted preamble in
  place, moving the character produced clear position candidates. Disambiguation
  rule that emerged: bytes that react to *both* horizontal and vertical movement
  are noise (scroll/animation/shared counters) and are discarded; axis-specific
  bytes that rise-then-return are the real coordinates.
- **Player X is at `0xC009`** (low WRAM). Live per-press tracking confirmed it:
  it steps by a fixed amount per horizontal press, returns exactly on the way
  back, and is unaffected by vertical movement. (`0xC00D`/`0xC0B7` track along
  with it - camera/copy; `0xC009` is enough.)
- **Verification matters: the first Y candidates were all noise.** The initial
  scan flagged ~21 vertical "hits" in high WRAM (0xDFxx); live tracking showed
  every one of them jittering and/or reacting to horizontal movement too. Trust
  in those would have produced a broken reader.
- **Player position found: `X=0xC009`, `Y=0xC008`.** A focused rescan of the
  low-WRAM neighborhood found Y right next to X, exactly as expected for an
  actor struct. Both step by 8 px (= 1 tile) per move, are axis-specific, and
  return cleanly. (`0xC00C/0xC00D` and `0xC0B8/0xC0B7` mirror them - camera or
  copies.) Exposed as `player_position()` / `player_tile()` in `perception.py`.
  This is the working, instant, free, local "eye" for position.
- **First navigation with a real eye works.** `agent_nav_loop.py` feeds the
  RAM-read (x, y) to the local model, which picks moves toward a target tile.
  In the first run it reached the target (Manhattan distance 32 -> 0 in 6
  moves), with one suboptimal move along the way - the small model is not
  optimal but recovers. Fully local, instant, free, no rate limits.
- **Text reading (phase A): hash the glyph bitmap, not the tile index.** Pulled
  each window text tile's 8x8 bitmap from PyBoy (`tile.ndarray()` is a method in
  this version), binarized it, and hashed it. The same on-screen letter yields
  the same hash even though GB Studio streams it into different tile indices -
  `a`, `h`, `i`, `v`, `e` and space all matched across positions and across two
  text rows. One dialog already yielded ~13 distinct characters. Confirms the
  deterministic, model-free reader; next is assembling a `{hash: char}` table.
- **Text reading (phase B): a disciplined font table.** Captured several intro
  screens and assembled `deadeus_font.json` (`{glyph-hash: char}`) only from
  double-checked evidence: the visible dialog "I have given you / all thi", plus
  self-validating words like "Continue" and "..." that spell out correctly using
  already-confirmed letters. Off-screen/stale window text (checkpoints where the
  box was parked) was cross-checked against decoded English before being
  trusted. A denser intro sweep then decoded the whole opening monologue with
  the partial table, and the remaining `?` gaps were filled from context (`debt
  be repaid`, `check`, `Nightmare`, ...), each new glyph confirmed by a real
  word. The table now covers ~35 characters (the full intro alphabet), including
  a case distinction found this way: `M` (in "My Child") and `m` (in
  "Nightmare") are different glyphs with different hashes. Unknown glyphs still
  read as `?`. Aside: the "The First Day" card is on the background layer, so the
  window held stale text beneath.
- **Can the font's order fill the gaps? Not from VRAM.** Tested whether the font
  sits in VRAM in ASCII order (so `tile[base + ord(c)]` would yield every glyph).
  It does not: GB Studio streams glyphs on demand, so only the currently-visible
  line's glyphs are resident (17/34 known chars present, exactly the on-screen
  line; the best base explained just 2/34 = noise). Tilemap indices carry no
  pattern either. The ordered font does live in ROM, so decoding the ROM file's
  2bpp tile blocks could crack the whole charmap at once; otherwise the table
  grows organically from captured dialog.
- **...and from ROM it works: the full charmap in one shot.** Decoded every
  2bpp tile in the ROM file and brute-forced the binarization: all 34 known
  glyph hashes reappear at `ink = palette index 0`, and every one lines up at a
  single base tile (22528, offset `0x58000`) — the font *is* stored in ASCII
  order in ROM. That derives the complete printable-ASCII table (95 glyphs:
  space, punctuation, digits, `A-Z`, `a-z`) with zero unknowns left.
  `deadeus_font.json` is now produced deterministically by
  `exploration/test_rom_font.py`, and the earlier dialog-capture probes become a
  cross-check rather than the source of truth.
- **Text eye complete (phase C).** `perception.read_text()` binarizes and hashes
  each window text tile, looks it up in the font table, and returns the dialog
  string; `dialog_open()` now gates on the window being enabled *and* on-screen
  (WY < 144) instead of the earlier, flaky box-tile check. Verified live: it read
  `I have given you / all this gift of / life` from the intro - and caught a
  third line that manual capture had missed. The agent now has complete
  model-free perception: player position + on-screen text + dialog state.
- **Autonomous intro skip.** Instead of a fixed ~300 A-presses, the agent
  presses A while a dialog is on-screen (WY-gated) and detects arrival with a
  *reversible* movement test (press right, position changes, press left, it
  returns = real player control, not animation). It reaches the movable room on
  its own at ~step 94 - fewer inputs than the hard-coded guess - verified by
  position (56,104) + screenshot + dialog closed. Movement tests are withheld
  until past the title menu so a direction never nudges a menu cursor.
- **The LLM navigation is the flaky part.** With `skip_intro` wired in, a full
  autonomous run reaches the room fine, but the `llama3.2:3b` navigation then
  walked into a corner and got stuck for 20 steps - it chose `down`/`right` when
  it needed `up`/`left` (mis-read the `dy` sign) and never noticed it was pinned
  against walls (distance 32 -> 48). An earlier run *had* reached the target, so
  the 3B model is simply inconsistent at spatial reasoning. The lesson mirrors
  the whole project: deterministic reflex code (`skip_intro`) is rock-solid; the
  model is the weak link. Options: stuck-detection + greedy fallback, a clearer
  prompt, or a stronger (cloud) model for decisions.
- **A/B test: swapping the local model did NOT fix it.** Tried `qwen2.5:3b` (a
  stronger small model) as a drop-in, same task, nothing else changed. It failed
  the same way - went `down` when the target was `up` - and then repeated `down`
  22 times against a wall (distance 32 -> 24, then frozen). Both 3B models make
  the *same* directional error, which points at the **prompt** (the `dy` sign
  convention forces a double-negative) plus the missing **stuck-detection**, not
  the model. Takeaway: fix the prompt + add stuck-detection first; model choice
  is secondary. Reverted to `llama3.2:3b` since the swap wasn't justified.
- **Planner / controller split (deterministic navigation).** The A/B result led
  to moving *pathing* out of the LLM entirely. `navigation.walk_to()` /
  `walk_direction()` move the player tile-by-tile (greedy + wall-handling); the
  LLM only makes the high-level call ("which direction to explore"). `walk_to`
  reaches the exact target (72,88) that both 3B models got stuck at, and the
  explore agent now moves reliably every round - it maps the room's bounds and
  reached a wider strip at the top (x=120, past the earlier room), never
  freezing. The rule: **deterministic code = execution, LLM = judgement.** This
  is also the seam where a real goal + memory will plug in.
- **Confirmed: the agent can leave the room.** A dedicated edge-sweep (push
  outward along each edge until the scene changes) found the door on the *top*
  edge and walked through into a visibly different room (position jumped to a new
  spawn). The reliable room-change signal is the **full 32x32 background tilemap
  hash** - a per-scene fingerprint, constant while scrolling, flipping on a scene
  load. Honest correction: the earlier explore run only *reached* the top strip,
  it had not actually exited - the skepticism was right.
- **Memory, layer 1: a code-filled map notebook.** The agent's memory is a
  Markdown notebook it reads and writes as it plays. Writing is split along the
  architecture principle: **deterministic code writes what it *measures***, the
  **LLM writes what it *interprets***. The first, code-filled piece is a **map**
  — the scene fingerprint (promoted into `perception.scene_fingerprint()`) is a
  node, and a move that flips it is a directed edge. `memory.py`'s `WorldMap`
  (`seen_scene` / `connect` / `exits_from`) is kept deliberately emulator-free —
  it takes plain fingerprint ints and positions, so it unit-tests and round-trips
  without a ROM — and persists as a `## Map` block inside `world.md` between HTML
  markers so the code can rewrite it idempotently and the notebook accumulates
  across runs. Verified three ways: a no-ROM unit test (idempotence, dedup,
  round-trip), a deterministic end-to-end test (a real room change records the
  edge from live emulator fingerprints), and a full run.
- **Watching the agent: an optional live viewer.** `viewer.py` (Tkinter +
  Pillow's `ImageTk`, no new dependency) behind a `--watch` flag opens a window
  with the upscaled Game Boy screen *plus an overlay of what the agent perceives
  and decides* — position, current scene, the planner's action, map growth. It
  refreshes on every button press via a `navigation.FRAME_HOOK`, so motion is
  smooth; the hook is `None` by default, so headless runs stay fast and
  unchanged. For a learning project the point is seeing the perception + decision,
  not just the sprite.
- **Why it wandered: no goal + a blind planner.** Watching live made the problem
  obvious. The explore loop had **no goal** (the prompt literally said "choose
  ONE direction"), and the LLM saw only `(x, y)` + its last few directions — not
  walls, not the map (which was being *written* but never *read back* into the
  prompt). So it paced into walls. Fix (step 1): give the planner a **goal**
  ("find the exit") and **real perception** — which directions are walls, derived
  from tiles-moved (`0 = wall`, so no extra button-probing that could
  accidentally step through a door), plus the **known exits** from the map. This
  made movement directed (it now went straight to an edge) but it still could not
  find the one-tile door *gap* by itself.
- **`find_exit`: a high-level action backed by a deterministic sweep.**
  Systematically sweeping an edge for a door gap is a **reflex**, and a 3B model
  does it unreliably — it paced the top wall left/right without ever pushing up
  at the door column. So the planner got a new action, `find_exit`: the **LLM
  decides *to* search**, and `navigation.search_for_exit()` does the
  **deterministic edge-sweep** (promoted from `test_leave_room`). Paired with
  **finer steps** — `walk_direction` capped at a small `STEP_TILES` instead of
  walking until a wall, which was the real reason the agent always ended up
  pinned to an edge and never visited the room interior. Result: in a full run
  the LLM chose `find_exit`, the sweep found the top door, the agent entered the
  next room, the map recorded `s0 --up--> s1`, and an NPC then spoke in the new
  room. Honest scope note: the sweep finds **edge** doors; a trigger in the
  *middle* of a room would be an interaction (press A), a separate later step.
  The recurring rule holds: **LLM judgement, deterministic reflex.**
- **Experiment: can the LLM find the exit itself? (`find_exit` removed).**
  Deliberately removed the deterministic `find_exit` action and instead described
  the door-finding *strategy* in the prompt (go to an edge, sweep along it, try
  stepping through), to see how far the LLM gets on its own. With `llama3.2:3b`:
  not far. Over 30 single-tile moves it **never even reached a wall** — it never
  committed to one direction long enough — and stayed in the room's interior.
  Adding a **local occupancy mini-map** to the prompt (`roommap.py`: floor from
  tiles it has stood on, walls inferred from 0-tile moves; door-safe, built from
  the agent's own moves, no probing) helped **dramatically**. Given 60 steps it
  navigated purposefully from the start (56,104) all the way up-right to
  **(112,56) — the exit tile itself** — a huge improvement over the raw-`(x,y)`
  run that never left the room's interior. But then the almost comic failure:
  standing on the door tile, it never pushed *up* the one final time to step
  through. It spent the next ~30 rounds oscillating along the top edge, returning
  to the exit tile again and again without crossing. Two clean data points:
  **perception is a huge lever** (the mini-map got the LLM to the door), and yet
  **the final "try the outward step at each edge tile" is a reflex the 3B won't
  reliably execute** (exactly what the removed `search_for_exit` did in one call).
  The next variable to isolate is **model strength** (a swappable cloud backend,
  same task, local-3B vs. cloud A/B). `navigation.search_for_exit()` stays as a
  tested, reusable deterministic skill even though the planner no longer calls it.
- **Repo structure pass.** Application source moved into `src/`; the long design
  log moved out of the README into `docs/design-log.md` so the README can read as
  a story; internal working notes live in `docs/HANDOFF.md` (git-ignored). No
  behaviour change — imports and run commands adjusted accordingly.
- **Small, verified steps.** Each capability (load ROM, press buttons, LLM
  decision, vision) was proven in isolation with its own `test_*.py` script
  before being wired into a loop.
