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
- **Frontier hint: the LLM steps through the door itself.** The mini-map got the
  3B *to* the exit tile but never *through* it. The fix keeps the LLM as the
  actor rather than handing the crossing back to deterministic code: (1) reframe
  the goal as "keep stepping into UNEXPLORED tiles until the room changes" — a
  door is just unexplored space beyond an edge, not a special thing; (2) compute,
  deterministically from the RoomMap, the direction to the *nearest* unexplored
  tile (`RoomMap.nearest_frontier`, a BFS over known floor) and hand it to the
  planner as one salient line ("Nearest unexplored: up"). The code only says
  *where* the unknown is; the LLM still chooses and makes the crossing move.
  Result: same 60-round setup, fresh map — the agent explored the bedroom and
  then **walked out on its own** into the hallway (`s0 -> s1` recorded), landing
  in front of an NPC whose lines ("Are you okay? You sounded like you were having
  a bad dream... A monster?...") were read model-free. Takeaway: **perception +
  a well-framed goal, not a bigger model, was enough to get the small local LLM
  through the door.** (`nearest_frontier` also drives the fallback when the model
  returns nothing.)
- **Map graph, extended for goal-directed navigation.** `WorldMap` edges now
  remember the **door tile** they were crossed from, and entering a room records
  the **reverse edge** (the way back through the spawn tile) - which is why the
  only known exit is often the entrance. Each node also reserves an optional
  **label** + **facts** (the interpreted layer, filled later from text/vision/LLM;
  the stable fingerprint id stays separate from the discovered name - clean
  grounding for "go to the church"). All of it round-trips in `world.md`. This is
  the foundation the `go_to`/intent layer (see action-vocabulary.md) will sit on.
- **Interaction: `interact()` + a landmark store.** `navigation.interact(dir)`
  faces a tile, presses A, and reads the text model-free (the same `read_text`
  path as dialogue). `memory` gains a per-scene **landmark** list (an interactable
  at a tile + its text, keyed by tile). Verified against a real object: the
  bedroom bed reads "Time for bed?..".
- **Auto-detect on bump - and a safety finding.** A blocked move (0 tiles) might
  be an object, not a wall, so the loop now interacts once per bumped tile and
  records any text as a landmark. Live proof: while exploring upward the agent hit
  the top wall and auto-discovered the **bookshelves** ("So many books") as
  landmarks `l0`/`l1`, saved to `world.md` - the environment reading itself into
  memory without a vision model. **Safety:** the bed prompt turned out to be a
  yes/no *choice* (B does not cancel it; A walks into a Yes/No menu). Probed all
  options - none slept (the game blocks sleeping right after waking), so blindly
  advancing it with `dismiss_dialog()` is safe *here*. **Known limitation, logged
  in code:** a consequential choice elsewhere would need choice-aware handling,
  not blind A. Interaction reads the world; it must not blindly *commit* to
  irreversible decisions.
- **The intent layer: LLM orchestrator over deterministic skills.** Replaced the
  per-tile planner entirely. The LLM now picks ONE high-level **intent** per turn
  - `explore`, `go_to <id>`, `interact <id>`, `remember <note>` - and a
  deterministic **skill** runs it to completion (explore = frontier + auto-detect
  + door-crossing; go_to = walk_to a landmark or cross a known edge; interact =
  walk up + read; remember = write a fact). The state is intent-level (room +
  label, known exits, landmarks here, explored?, goal, recent results), not raw
  `(x, y)`. One LLM call per intent, ~15 a run instead of 60 tile-steps. Result:
  the 3B sensibly chose `explore` while the room was unmapped, **crossed into the
  hallway on its own**, and `interact`ed with the NPC and objects - building a
  genuine notebook: two rooms connected both ways (with door tiles) and ~18
  landmarks of real content ("It was just a dream", "flowers when you check in on
  her…"). The `why` fields show actual reasoning ("room is not fully explored",
  "Read the message to understand"). This is where the LLM stops being
  decorative: **judgement over a learned world, reflexes in code** - the tool-use
  / orchestrator pattern. Honest open items: cross-room `go_to` routing isn't
  built yet (handled with a clear message, not a crash); reverse-edge crossing
  (`go_to s0`) doesn't reliably step back through yet; landmark capture is noisy
  (a multi-tile bookshelf becomes 8 "So many books" landmarks; the typewriter
  effect truncates some text, e.g. "You know, I t…").
- **Swappable LLM backend (local ↔ cloud).** Local `llama3.2:3b` on this CPU
  takes ~1-2 min per call, which is painful for iteration. `src/llm.py` mirrors
  the relocation-assistant-rag `generator.py` pattern: one `chat_json()`, a
  `LLM_BACKEND` switch (`ollama` | `openai`), and an OpenAI-compatible `base_url`
  so it points at ANY host. Set `OPENAI_*` in a git-ignored `.env` to run the
  **same** `llama3.2:3b` on fast cloud hardware (Together / OpenRouter / DeepInfra
  → sub-second, prompt behaviour carries over), or a stronger model for real
  runs. Key never in code. Verified the local path still works via the Ollama
  HTTP API (httpx). Speed *and* the planned quality upgrade, one switch.
- **Small, verified steps.** Each capability (load ROM, press buttons, LLM
  decision, vision) was proven in isolation with its own `test_*.py` script
  before being wired into a loop.
- **Reverse-crossing fixed (the real root cause was a wrong assumption, not the
  mother scene).** Open issue #1 was "`go_to s0` back through a known edge usually
  logs 'didn't cross'". Isolating it on the *mother-free* bedroom<->hall door
  (deterministic, no LLM) disproved the working theory that the room-2 mother
  cutscene was to blame: the reverse crossing failed there too. Measurement — enter
  the hall via `up`, spawning at tile (14,7); the real way back is *also* `up` at
  (13,7), **not** `down` from the spawn. So `note_crossing`'s guessed reverse edge
  (spawn tile + geometric opposite direction) is simply wrong in Deadeus, and
  `skill_go_to` was pressing the wrong direction on the wrong tile. Fix, in the
  spirit of "deterministic reflex, learned from real crossings, not guessed":
  `navigation.sweep_for_crossing` (the edge-sweep, now also returning the tile it
  crossed from; `search_for_exit` became a thin wrapper), a fallback in
  `skill_go_to` (`_cross_by_sweep`) that sweeps when the recorded edge fails,
  records the REAL edge from the crossing, and prunes the stale guess
  (`WorldMap.forget_edge`). Verified end-to-end (`tests/test_reverse_crossing.py`):
  the agent returns to s0 twice and the map keeps only the true `up` edge. Honest
  limitation: the fast door-tile re-cross still often doesn't fire (a door quirk),
  so returns currently go through the sweep each time — correct but not cheap; a
  cheaper direct re-cross is a later refinement. The room-2 mother scene (two
  dialogs before you can leave) is a separate, still-untested concern.
- **The real day byte, found the disciplined way: `0xC60F`.** Day-awareness was
  blocked because an earlier RAM-diff-across-sleeps had picked `0xC4A7`, later
  disproven (it jitters per scene: 6,7,2,3,1…, not per night). The lesson baked
  into this pass: a day counter is *scene-independent* - the earlier method diffed
  too few, uncontrolled states and mistook per-scene noise for the day. New method,
  one experiment script (no rabbit-holing): snapshot the SAME scene+position
  (bedroom spawn) across day 1/2/3 - so per-scene differences cancel - and keep the
  byte that increments by exactly +1 each night AND reads identically in a second
  scene (the day-1 hallway). Reaching day 2/3 was possible now that reverse-crossing
  works (hall round-trip, then confirm 'Yes' at the bed). Exactly one byte survived:
  `0xC60F` = 1/2/3 on day 1/2/3. Confirmed the way 0xC4A7 was *debunked* - load the
  day-2/3 savestates, tour several scenes: 0xC60F holds constant while 0xC4A7
  jitters. Wired as `perception.game_day`; guarded by `tests/test_game_day.py`
  (fast: day 1 reads 1 in both bedroom and hallway); day-1/2/3 savestates kept in
  `runs/day_states/` so day-awareness work needn't sleep each time. (Housekeeping:
  the day-byte run slept and the older ROM tests stop() with save=True, so the
  git-ignored battery save may have been rewritten; new tests use save=False.)
- **Bed sleep-decline verified against the real day byte (issue #2 closed).** The
  auto-decline logic (never confirm a Yes/No, e.g. the bed's "Time for bed?") had
  been written but never provably tested - day-1 blocks the bed, so a "didn't
  sleep" result there is meaningless. Now that 0xC60F gives the day and reverse-
  crossing lets us reach an enabled bed, the test runs on day 2: a positive control
  confirms 'Yes' advances day 2 -> 3 (so the bed here genuinely sleeps), while both
  auto paths - `read_dialog` (skill_interact) and `dismiss_dialog` (the explore
  bump) - leave the day at 2 and close the dialog. Captured as a self-contained
  `tests/test_bed_decline.py`: it reaches day 2, snapshots state to an in-memory
  buffer, and reloads it between the three trials (no on-disk savestate). Honest
  caveat: deterministic from one snapshot, so it proves the decline *path*, not
  every frame-alignment the slowly-loading menu might present in live play.
- **Day-awareness wired into the prompt.** Now that 0xC60F gives a reliable day,
  `build_state` surfaces a "Time: day N of 3 - K day(s) left ... sleeping in a bed
  ends the current day" line, and the system prompt adds one neutral sentence
  asking the LLM to weigh its limited time toward the goal. Deliberately NOT an
  anti-sleep rule: the point is to observe whether the model self-regulates against
  the clock (it previously fixated on the bed and could sleep straight to the
  credits with nothing left). `tests/test_game_day.py` extended to assert the day
  shows up in `build_state`. Next: run the agent over Groq and watch how the
  visible day changes its behaviour around the bed.
- **Explore now fully maps a room before ever leaving it (bouncing fixed, bed found
  honestly).** The user vetoed seeding the bed as a landmark ("feels like cheating")
  and proposed the right model: fully explore room 1, then room 2 - where "fully"
  means visit every reachable tile and, on each blocked bump, probe once to tell
  wall from object. The bouncing (issue #4) came from `explore` auto-crossing the
  first door it met (`nearest_frontier` treats a doorway as just another unexplored
  tile). Rewrite: a discovered door is recorded, its doorway fenced off
  (`RoomMap.mark_wall`), and the agent returns via the (now robust) `skill_go_to`
  to finish the room; known doorways are re-fenced at each explore call; crossing is
  a deliberate `go_to`, not a side effect. One real bug surfaced en route: bumping
  the bedroom's SAVE POINT opens "Save Game? / Cancel", which `dismiss_dialog`
  (Yes/No-only) confirmed - leaving a "Game saved!" box that wedged all movement.
  Fixed by draining any open dialog at the top of each explore step (the accidental
  save itself is logged as a minor follow-up, same class as the bed decline).
  Result, verified deterministically (no LLM, `tests/test_explore_full_room.py`):
  the bedroom is mapped fully, the agent stays in s0, and the **bed is discovered by
  bumping** as l12 @ (6,14) "Time for bed?..." - no seeding. `test_skills` updated
  from the old "explore should leave" contract to "maps fully, stays put".
- **Model comparison + "act, don't just map" rebalance.** With the day visible and a
  `why` logged per round, ran the same 14-round harness across models. `llama-3.1-8b`
  is too small: one static generic plan, no synthesis from what it reads, wastes
  rounds on invalid interacts. `llama-3.3-70b` is clearly better: plans evolve,
  it names "the girl next door" from s1 dialogue, clean room-by-room progress - but
  it NEVER interacts, it maps outward forever and defers its own goal. `gpt-oss-20b`
  had the best instinct (it tried to READ landmarks for clues) but looped re-reading
  the same objects. Two fixes followed, both state-clarity not model size: (1) an
  action-first prompt (interact UNREAD landmarks / pursue the plan BEFORE mapping
  new rooms); (2) read-tracking (a `read` set surfaced as an "unread landmarks"
  line; interacting retires a landmark and its identical-text clones, and retires
  unreachable ones, killing the re-read and can't-reach loops). Plus: an allow-list
  of the current room's landmark ids and dropping the `found lN` id-leak from Recent
  actions, which had caused wrong-room interacts. Result: both 70B and gpt-oss-20b
  now mix explore/interact/go_to, read the NPC hints, and evolve a "find people"
  plan - **gpt-oss-20b ≈ 70B behaviour at a fraction of the cost once scaffolded.**
  Takeaway (the recurring theme): perception/state design is a bigger lever than
  model size. The day byte itself stayed unused (still day 1 - no time pressure yet).
- **Deep-room navigation root cause: scene_fingerprint collides outdoors.** `go_to`
  in the town lands in the wrong room / ping-pongs. The recorded graph gave it away:
  self-loops (`s2 --left--> s2`) and contradictions (`s2 --up--> s1` AND `--up-->
  s2`) can only happen if physically different screens hash to the same fingerprint.
  The town is one big GB Studio scene navigated by camera "chunks", and many chunks
  share a background tilemap. Rather than script into the outdoor area (unreliable -
  the very bug), added `exploration/manual_scan.py`: the user plays manually while
  it logs WRAM per screen transition (written continuously so a hard window-close
  can't lose it). Over 30 screens (6 fingerprints recurred), fingerprint alone =
  17 unique; **`(fingerprint, camera 0xC0B7/0xC0B8)` = 28**, separating every
  look-alike and collapsing only genuine revisits (camera at the transition frame
  is grid-aligned and stable per chunk). So there is NO single "scene id" byte - the
  identity is fingerprint + camera. Fix (documented, not built; high blast radius):
  a `scene_key = (fingerprint, camera//8)` migrated through WorldMap/RoomMap/tests.
  Data kept in `runs/manual_scan.pkl` to calibrate + validate.
- **Scene-identity via camera: implemented, DISPROVEN, reverted.** Acting on the
  manual-scan result, tried `scene_key = (fingerprint, camera 0xC0B7/0xC0B8)` as the
  room identity (fingerprint stays the crossing detector; camera read at entry;
  memory/RoomMap/tests migrated). The ROM tests immediately caught the flaw: the
  SAME room got a DIFFERENT key on re-entry (`test_explore_full_room`: "explore left
  the bedroom (now s2)"; `test_reverse_crossing`: "should have returned to s0"). Why:
  0xC0B7/0xC0B8 is entry-/position-dependent (in the house it tracks ~the player),
  so entering a room from a different door yields a different camera → the same room
  splits into multiple nodes. The manual-scan "28 unique of 30" was misleading - the
  user happened to cross each look-alike the SAME way, so the entry camera was
  incidentally consistent; it is NOT a room-invariant. A quantisation that keeps a
  whole room in one bucket (rooms span >64 px of camera) would also merge distinct
  chunks (>=64 px apart) - the two constraints conflict, so camera can't be the key.
  Reverted cleanly. **Collisions remain real (open issue #7); the camera is not the
  fix.** A true per-screen invariant is still needed (candidates: a GB Studio scene
  index if one exists - the block-constant bytes 0xC032/0xC122 seen in the scan are
  worth chasing; or global position quantised to a chunk grid IF a stable global
  coordinate exists). `exploration/manual_scan.py` + `runs/manual_scan.pkl` kept.
- **Notebook cleanup: landmark de-dup + typewriter text merge.** A 70B run over
  Groq exposed that the two "noisy landmark / doubled text" caveats were not
  cosmetic - they dominated the notebook and wasted rounds. A wide bookshelf became
  **eight** `l0..l7` "So many books" landmarks and the agent re-read the clones for
  half the run; captured dialogue doubled at every page boundary ("you can you can
  save", "You soun You sounded", "next door came door came"). Two contained fixes,
  each unit-tested with no ROM (now in CI): (1) `WorldMap.add_landmark` de-dupes by
  identical descriptor within a scene, collapsing a multi-tile object to one entry;
  (2) `navigation.merge_dialog` assembles typewriter fragments by dropping partial
  re-renders, merging word-overlap at page breaks (incl. a truncated boundary word,
  `havin` -> `having`), and collapsing immediately-repeated runs. Result on a fresh
  70B run: **19 landmarks -> 7**, and facts now read as written ("You know, I think
  that girl has a bit of a thing for you!... take her some flowers... find some
  around the area!") - the clue is finally usable. (`tests/test_dialog_merge.py`,
  extended `tests/test_memory_map.py`.)
- **Breaking the 2-room local optimum: explore to completion.** Even with a clean
  notebook, the 70B agent mapped the bedroom + living room, read everything, then
  oscillated `s0 <-> s1` forever - it never found the living room's exit to the
  outside. Diagnosis (one targeted probe, not a rabbit-hole - the game fact "the
  exit is the bottom door, walk-through" was confirmed with the user first):
  continuous `skill_explore` *does* find that bottom exit (`explore[1]: found
  exit->s2`), but the LLM kept **interrupting** explore with `interact`/`go_to`,
  which pulled the player back to the mapped area, so a single 25-tile pass never
  reached the far door and the room got declared "fully mapped" without it. A
  deterministic edge-sweep was tried as the fix and **rejected**: it re-crosses the
  known door (the house door is crossable from two edges - `up` *and* `right` both
  land in s0) and its push-phase check misses the far bottom door. The real fix is
  simpler: `explore_to_completion` loops the deterministic pass until the room is
  fully mapped or a NEW scene appears - no extra LLM calls. Verified end-to-end: a
  fresh 70B run reaches **4 scenes** (bedroom -> living room -> town -> a further
  outdoor screen), reading a "The local School" sign; guarded by
  `tests/test_explore_reaches_town.py`. Honest new frontier: the moment the agent is
  outside, **issue #7** bites for real - the town's camera-chunks collide on the
  fingerprint, so `s2` sprouts self-loops (`s2 --left--> s2`) and outdoor `interact`
  often can't reach a landmark. Clean town navigation is the next problem.
- **Issue #7 (town self-loops) - the long way round to a two-line fix.** The
  working theory (above) was that the outdoor fingerprint *collides* - different
  town screens sharing a background tilemap - so the plan was a better scene
  identity. That theory was **wrong**, and chasing it produced a chain of dead-ends
  worth recording so nobody re-treads them:
  (1) **Grid odometry** (a `scene_key` = a coordinate advanced by crossing
  direction, with the fingerprint demoted to a crossing *detector*). Built the whole
  thing - an `Odometer`, a drift-tolerant `WorldMap.match`, `Loc` threaded through
  every skill. It fell apart on two Deadeus realities: the doors are **non-Euclidean**
  (the way back is not the geometric opposite - reverse-crossing already taught us
  this), so exact-coord matching broke indoor returns; and a **scrolling** town
  screen ticks the fingerprint every step, so "any fp change is a crossing" advanced
  the odometer per tile and **exploded the map to 42 nodes**. A lenient match
  self-looped; an exact one duplicated. Reverted entirely.
  (2) **Animation-robust fingerprint** - the hypothesis that the fp *oscillates*
  from animated background tiles (the fountain/waterfall). Measured it with
  `anim_probe`: **0 changing background tiles** on every screen, even the waterfall
  (which animates on sprites/palette, not the bg tilemap). Disproven; the fp is
  perfectly stable per screen. `settled_fingerprint` (wait for the fp to stabilise
  after a crossing) was built on the same false premise and was pure overhead.
  The turning point was the user's **game knowledge**: the neighbouring town screens
  look *clearly different* - so there are **no real collisions at all**. That
  reframed it from "identity" to "why does a crossing get *recorded* wrongly?" A
  **deterministic instrumented drive** to s2 (no LLM, XDBG-logging every crossing)
  answered it in minutes: at a town EDGE the fingerprint briefly **flickers** and
  the player shifts a tile while STAYING on the same screen; the detector fired and
  `is_crossing_move` (the scroll-tick guard, added earlier) was fooled by the 16px
  edge shift, so a crossing was recorded whose **`new_fp == cur_fp`** = a self-loop.
  **The fix is two ideas, both tiny:** a real crossing must (a) land on a DIFFERENT
  fingerprint (`new_fp != cur_fp`, added to all three crossing paths) and (b) be a
  teleport, not a continuous step (`crossing.is_crossing_move`: a scroll-tick lands
  exactly one tile along the walk; a crossing jumps to a spawn, often *against* the
  pressed direction). Validated by `tests/test_no_town_selfloops.py` (deterministic)
  and a full 24-round **gpt-oss-20b** run: **7 scenes, 0 self-loops**, a navigable
  town. The odometry/match scaffolding was then deleted. **Lesson: the fingerprint
  was fine all along - the bug was in *when a crossing is recorded*, not in the
  *identity*. Reach for a deterministic reproduction before the next hypothesis.**
- **Outdoor one-tile oscillation: a durable doorway fence.** New symptom watching a
  run: outdoors the character ping-pongs A<->B on a *single* tile, the screen
  flickering between two screens. Not issue #7 (those were same-fp self-loops); here
  the two screens are genuinely different and both crossings are "real". User's game
  knowledge pinned the physics: outdoor transitions are a **hard cut** and you spawn
  on the **edge** of the new screen. Root cause, from the code: `explore` fences a
  discovered doorway with `RoomMap.mark_wall`, but that fence is **erasable** -
  `mark_floor` discards a wall the instant the player stands on the tile, and
  `mark_wall` refuses to re-fence a floor tile. Indoors this never bit because the
  reverse crossing is unreliable (issue #1) - the auto-return in `skill_explore`
  fails and the pass ends. Outdoors the hard-cut return is **reliable**, so the
  player lands back on the doorway, `mark_floor` reopens it, and `nearest_frontier`
  sends it straight back out - forever, bounded only by the explore budget (a fast
  visible flicker). Fix: a durable `RoomMap._doors` set that `mark_floor` never
  clears and `nearest_frontier`/`has_unexplored` treat as impassable; `skill_explore`
  now `mark_door`s both the discovered doorway and the outward tile of wherever it
  actually re-enters. Guarded by an extended `tests/test_roommap.py` (a door survives
  `mark_floor`; the contrast case shows a plain wall does not); the ROM explore/town
  tests stay green. Honest note surfaced by this fix: the oscillation was *partly
  load-bearing* - it was how `explore` used to stumble into the next room - so
  forward progress now depends on the LLM choosing `go_to` (which is correct: leaving
  a room is a judgement call).
- **Groq model decommissioned: `llama-3.1-8b-instant` -> `gpt-oss-20b`.** A
  diagnostic run showed **every** LLM call failing with `404 Not Found`; the loop
  degraded to permanent `explore` fallback (`why='fallback'`), which by itself looks
  like "stuck in room 1". `GET {base_url}/models` confirmed the configured model is
  no longer served (the live chat models are `openai/gpt-oss-20b`, `openai/gpt-oss-120b`,
  `qwen/qwen3.6-27b`). Switched `.env`/`.env.example` to **`openai/gpt-oss-20b`** -
  the proven cost/quality default here (it drove the clean 24-round issue-#7 run);
  120b is stronger but rate-limits harder on the free tier. Takeaway: a dead cloud
  model is indistinguishable from an agent bug in the logs - check `/models` first.
- **Prompt loosening: let the LLM leave a room before it is 100% mapped.** With a
  live model, the LLM's judgement was actually good - it read a room, then chose
  `go_to` the next one - but it got trapped: `INTENT_SYSTEM` rule 4 gated leaving on
  the room being **"fully explored"**, and `explore` can never declare the living
  room fully mapped (unreachable frontier behind furniture / the mother-scene area),
  so the model dutifully explored forever and never reached rule 4. That is the
  *opposite* of "the LLM decides". Fix (state clarity, not model size, the recurring
  theme): reworded rules 3/4 so that **once the landmarks here are read, a known exit
  into a not-yet-visited room is a valid `go_to`** - a room never has to be fully
  mapped first; and `build_state` now annotates each exit with `(NOT visited yet)` so
  the option is visible. Verified over Groq (gpt-oss-20b): the agent reads s0, `go_to
  s1`, reads it, then **`go_to s2` on its own** to chase the "find the girl next door
  / flowers" plan - the living-room stall is gone. New frontier it exposed: crossing
  *out of* the deeper outdoor screens (`s3`) still fails intermittently (`go_to ...
  didn't cross`), and the model sometimes targets the room it is already in - the
  next thing to look at.
