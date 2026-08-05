# Action vocabulary — design sketch (not yet implemented)

Forward-looking design for the agent's decision layer. It supersedes the current
per-tile planner. Nothing here is built yet; this is the agreed target so a build
can proceed in tiny, verified steps. Rationale and the experiments that led here
are in [`design-log.md`](design-log.md).

## The shift: one LLM call per *intent*, not per tile

Today: 1 LLM call → 1 button press. Measured result: a 3B model steering
tile-by-tile is **unreliable** (it turned back at the door as often as it made
it through). So the LLM stops driving movement and becomes an **orchestrator over
a library of deterministic skills**:

    1 LLM call → 1 intent → deterministic code runs it to completion (many tiles)

Fewer calls, each a real judgement. The flaky tile-navigation disappears. This is
the standard modern LLM-agent pattern (tool use / function calling).

## The vocabulary

| Intent            | When the LLM picks it (judgement)                     | Deterministic execution (reflex)                                             |
| ----------------- | ----------------------------------------------------- | --------------------------------------------------------------------------- |
| `explore`         | "I don't yet know all exits / objects here"           | frontier-driven walk until something new (exit / object / fully mapped); adds nodes+edges to the graph |
| `go_to <id>`      | "I want to reach this *known* room / exit / landmark" | BFS over the map graph → walk the route (`walk_to` door tile → step through) |
| `interact`        | "examine what I'm facing"                             | face (press direction) + press A + `read_text` → a fact                     |
| `remember <note>` | "this matters / this scene is X"                      | write the LLM's interpretation (or a scene label) into the notebook         |

Notes:
- **No `leave_room`.** It was ambiguous and its default was wrong: the only known
  exit is usually the *entrance*, so "leave" sent the agent back the way it came.
  "Leaving" is just `go_to <some exit>` (known) or `explore` (to discover a new
  one). The choice of *which* exit is exactly the judgement the LLM should make.
- **`talk` folds into `interact`** (pressing A at an NPC). Advancing an open dialog
  stays automatic in the controller (no LLM call).
- The LLM references **ids from the state** (`s2`, `exit_north`, `book`), never
  raw coordinates it invents — it can't ground those. Code resolves id → tile/route.

## JSON contract (one intent per turn)

```json
{
  "action": "explore | go_to | interact | remember",
  "target": "<id, for go_to/interact>",
  "note":   "<text, for remember>",
  "why":    "<one short sentence>"
}
```

`why` is for the log/overlay — it makes the agent's reasoning visible (nice to
watch, good for the portfolio).

## What the LLM sees each turn (intent-level state, not (x,y))

```
Current room: s1 (hallway)            # label shown if known, else just the id
Known exits:  down -> s0 (bedroom, where you came from)
Landmarks here:
  - book  @ table   (read: "It was just a…")
  - npc_1 @ door    (not talked to)
Unexplored:   yes — this room isn't fully mapped
Goal:         reach a non-violent ending
Recent:       explore -> mapped room; interact(book) -> got text
```

This turns "which exit / explore / read the book / talk" into a real choice among
discovered options — instead of four arrow keys.

## Control loop (sketch)

```
loop:
    if dialog_open: press A                       # deterministic, no LLM
    else:
        state  = build_state(memory, roommap, world)
        intent = llm.plan(state)                  # ONE judgement call
        result = SKILLS[intent.action](intent)    # runs to completion, step-budgeted
        memory.update(result)                     # facts, edges, landmarks, labels
```

## What the map graph must store (the first build piece)

`WorldMap` today stores edges as `(from, direction, to)`. For goal-directed
navigation it needs:

1. **Door tile per edge** — the tile in the *source* scene you cross from (today
   `search_for_exit` discards it). Needed so `go_to <exit>` = `walk_to(door) +
   step through`.
2. **Reverse edge on arrival** — entering s1 from s0 via `up` means the way back
   (s1→s0) is at the spawn tile, direction `down`; record it immediately. This is
   why "the only known exit is the entrance" — modelled honestly.
3. **Optional `label` + `facts` per node** — empty until evidence arrives (see
   grounding). Costs almost nothing to reserve now.
4. **(Later) BFS routing** across multiple rooms — only once ≥3 rooms connect.

## Grounding: semantic names ↔ anonymous scene ids

A hint like "go to the church" references a *place*; the graph has anonymous ids
`s1..s5`. Resolution:

- **Id is the stable key; the semantic label is a discovered *attribute*** of a
  node (`s3: label="church"`). Routing works on ids; hints/goals work on labels; a
  resolver maps label → id **when the label exists**.
- **Labels come from evidence:** `read_text` on entry (a sign / spoken name), the
  planned rare **VLM glance** ("this looks like a church interior"), or the LLM's
  inference from accumulated facts — written via `remember`.
- **Unknown place → an exploration goal, not a route.** If no scene is labelled
  "church", "go to the church" becomes "find the church": `explore` until a scene
  earns that label. You can only navigate to somewhere you've already located.
- **Guardrail:** labels must be evidence-based, and the LLM may only route to
  labels present in the state. An unknown target → "find it first", never a guess
  onto a random scene. (This is the known "semantic mapping / language grounding"
  problem; keeping id≠meaning separate is the clean handling.)

## Reused vs. new

- **Reused:** `search_for_exit`, `walk_to`, `walk_direction`, `RoomMap` + frontier,
  `scene_fingerprint`, `read_text`, `WorldMap.exits_from`. The skills exist; they
  gain an intent wrapper.
- **New, small:** `interact()` (face + A + read); the per-scene **landmark +
  label + facts** store in `memory`; the intent planner + `SKILLS` dispatch.

## Incremental scope (don't overbuild)

1. **First piece:** extend `WorldMap` — door tile per edge, reverse edge on
   arrival, optional `label`/`facts` per node. Unit-testable without a ROM.
2. Then `interact()` + the landmark/facts store (the NPC/facts memory layer).
3. Then the intent planner + `SKILLS` dispatch (`explore`, `go_to`, `interact`,
   `remember`), replacing the per-tile planner.
4. Multi-room BFS routing only once several rooms connect.

The LLM's judgement only becomes load-bearing once ≥3 competing intents exist
(`go_to` several places, `interact`, pursue a goal). So the intent layer is worth
building *together with* the content it chooses among — not before.
