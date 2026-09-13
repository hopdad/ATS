# Second-screen dashboard — plan

A live truck dashboard served from your gaming PC to a phone, tablet or second monitor,
with buttons that operate the truck.

Status: plan only. Nothing is built yet.

---

## The constraint that shapes everything

**The SCS telemetry SDK is read-only.** It streams data out of the game and accepts
nothing back — there is no supported way to tell ATS "turn on the beacon" through it.
SCS's own SDK notes say additional APIs *might* come later; today there are none.

So this is not one system, it is two, and they are independent:

| | Reading | Controlling |
| --- | --- | --- |
| Mechanism | SDK plugin → shared memory | synthetic keyboard or gamepad input |
| Reliability | solid, documented, stable | works, with a focus caveat (below) |
| Risk if it breaks | dashboard goes stale | buttons do nothing |

That split is good news for sequencing: the dashboard is worth having on its own, and it
ships first. Control lands on top of a system that already works, and if the input spike
in Phase 3 goes badly, you still have the dashboard.

### The focus caveat, stated honestly

Synthetic keystrokes generally go to the *focused* window. If ATS is focused, injected
input lands. If you alt-tab to a browser on a second monitor, the game is no longer
focused and keystrokes may go nowhere.

This mostly resolves itself, because the intended use is a **separate device**: the
dashboard lives on a phone or tablet beside the wheel, your PC never loses focus, and
injection works. The second-monitor case is the one at risk.

I could not confirm from documentation whether ATS reads input while unfocused. **Phase 3
opens with a 20-minute spike to answer it empirically**, before any control UI is built.
Two mechanisms are on the table and the spike picks one:

1. **Scancode keystrokes** (`SendInput` via `ctypes`, no dependencies). Games that read
   DirectInput want hardware scancodes, not virtual key codes — a detail that silently
   breaks naive implementations.
2. **Virtual gamepad** (ViGEmBus driver + `vgamepad`). Presents as a real controller at
   the device layer, which is likelier to be read when unfocused. Costs a driver install
   and a dependency.

Start with 1. Fall back to 2 if the spike says focus is a problem.

### TruckersMP — a calibrated answer

An earlier draft of this plan said flatly "don't use control on TruckersMP." That was
stronger than the evidence supports, so here is the actual position.

**Reading telemetry is uncontroversial.** Telemetry apps are everywhere in that community
and TruckersMP publishes an API of its own. No concern.

**One tap sending one keypress is, functionally, a button box.** TruckersMP's published
rules cover approved mods and make you responsible for your equipment — "keyboards, game
controllers, mice, steering wheels and similar." The only automation prohibition I could
find concerns scraping their website, not in-game input. People run Stream Decks and
button boxes there routinely, and a tap on this dashboard is the same event.

**What would actually be a problem** is automation that plays for you: timed macros,
sequences that fire on their own, anything reacting to telemetry without a human press, or
anything touching game memory or the TruckersMP client. That line is worth respecting
whatever the rules say, and it is a design constraint here — **every command originates
from a press, and the bridge never synthesises a sequence.** No "auto" anything.

Two caveats I can't remove. I could not retrieve the full current rules text, only
summaries, so I have not read a clause that explicitly blesses external input. And rules
change and enforcement is at admin discretion. Check the current rules yourself before
using the control half there. The safe line, and the one this design holds to, is
**one press equals one keypress**.

---

## Architecture

```
gaming PC                                          your phone / tablet
┌──────────────────────────────────────┐
│  American Truck Simulator            │
│    └─ scs-sdk-plugin (3rd party)     │
│         writes Local\SCSTelemetry    │
│                  │                   │
│                  ▼                   │           ┌────────────────┐
│  bridge (Python, stdlib only)        │           │  dashboard     │
│    reads shared memory @ 20 Hz  ─────┼── SSE ───▶│  (static web)  │
│    serves the web app           ◀────┼── POST ───│  control taps  │
│    injects input into the game  ◀────┘           └────────────────┘
└──────────────────────────────────────┘
```

**Transport.** Telemetry is one-way and high-frequency; control is low-frequency
request/response. That maps exactly onto **Server-Sent Events** for data and **HTTP POST**
for commands — which means no WebSocket library, no dependencies, and browser-native
reconnect via `EventSource`. If we later need sub-frame latency or client→server streaming,
WebSocket is a contained swap behind one module.

**Language.** Python 3, standard library only, matching the rest of this repo. No build
step, no `npm install`, no bundler. The web app is hand-written HTML/CSS/JS served as
static files.

**What we depend on.** Exactly one third-party binary: the community `scs-sdk-plugin`
(RenCloud's is the reference implementation; a Linux mmap fork exists). We pin a version,
document the install, and verify the struct version at startup so a plugin update fails
loudly instead of rendering plausible garbage.

---

## Reading telemetry

The plugin publishes a C struct into a memory-mapped file named `Local\SCSTelemetry`.
Python opens it with `mmap` and decodes with `struct` — no C, no compilation.

- **Versioning is not optional.** The struct carries a version field. Read it, compare
  against the layout we were built for, and refuse to decode on mismatch. Silently
  misparsed telemetry is worse than no telemetry.
- **Field map lives in one file** (`schema.py`) as offsets and types, so a plugin update
  is a data change, not a code change.
- **Poll at 20 Hz.** The game updates as fast as it can; 20 Hz is smooth for a glance
  display and trivial bandwidth on a LAN.
- **Derive, don't just relay.** The raw fields are not the interesting part. Fuel range,
  time to next rest, ETA against the delivery deadline, over-limit state, distance
  remaining — these get computed once in the bridge so every client agrees.

### Dev without the game

A recorder writes the decoded stream to a file; a simulator replays it. That means the UI
can be built and tested on any machine with no ATS install, which is how most of this work
will actually get done. It also gives tests deterministic input — a recorded run through a
speed-limit change, a low-fuel warning and a job completion becomes a fixture.

---

## Control

### Discovering your actual keybinds

Hardcoding "the lights key is L" is wrong for anyone who has remapped anything. The game
stores bindings in `controls.sii` in the profile folder — the same SII format this repo
already parses in two other tools. The bridge reads it and maps each dashboard button to
the key *you* actually use.

If the file is unreadable or a binding is absent, that button renders as unavailable and
says why. It never guesses.

### The control set

Grouped by what they do, not by keyboard layout:

- **Lights** — park, low beam, high beam, beacon, hazards, indicators L/R, interior
- **Wipers** — cycle
- **Signals** — horn, air horn (momentary: held, not toggled)
- **Drivetrain** — engine start/stop, parking brake, retarder, differential lock
- **Cruise** — set, resume, +, −, off
- **Trailer** — hook / unhook
- **View** — route advisor toggle

### Two safety rules, non-negotiable

1. **Destructive actions are hold-to-fire.** Unhooking a trailer or killing the engine at
   60 mph is a ruined run. Those buttons fill a radial over ~800 ms and fire on
   completion. A tap does nothing.
2. **The rail arms and disarms.** A master switch, disarmed by default on connect. A
   phone in a pocket cannot drop a trailer.

### Closed-loop buttons

Where telemetry reports the real state — lights, beacon, parking brake, cruise speed — the
button reflects **the game**, not what we hoped our keystroke did. Press, watch telemetry,
settle into the confirmed state. If the keystroke didn't land, the button visibly snaps
back, which is also how you discover a focus problem without reading logs.

Where telemetry exposes no state, the button is styled as momentary and never fakes a
toggle. The UI must not claim to know something it doesn't.

---

## The UI

Interactive mockup: **https://claude.ai/code/artifact/01f62385-b1f3-4ba0-8a37-ebda4993f27d**
Open it on a phone and it stops being a mockup — it fills the screen and behaves like the app.

**Phone first.** Every sizing decision assumes a mounted phone read at a glance and
operated by thumb, in portrait or landscape. Tablets and second monitors get the same
views, scaled up; they are not the design target.

### Nothing scrolls. Ever.

This is the rule the whole layout answers to, and it is the direct fix for swiping while
driving. Each view is sized to exactly one screen, with `overflow: hidden` while moving.
When content doesn't fit, it moves to **another page** — never below the fold. A bump in
the road cannot slide the dashboard out from under your thumb, because there is nowhere
for it to slide to.

### Views are separate addresses

`/drive` and `/switches` are separate URLs, not panels of one page. That gives the
separation you asked for, three ways at once:

- **One phone**: a fixed thumb bar at the bottom switches views. Same position every time,
  so it becomes muscle memory. Horizontal only — and since nothing scrolls vertically,
  a sideways swipe can never be confused for scrolling content.
- **Phone plus second monitor**: open `/switches` on the phone and `/drive` on the
  monitor. No mode, no setting — just two URLs. Any number of devices can connect at once.
- **Later, a tablet**: it opens a URL like anything else.

This is the split worth designing around: **the phone is a touch surface, the monitor is a
glance surface**. Your eyes are already on the road and the game; your thumb is on the
phone. If you end up running both devices, controls belong where your hand is and data
belongs where your eyes are.

### Pressing without looking

- Fixed grid positions — a switch does not move between sessions.
- `navigator.vibrate` on every press, a double pulse on a completed hold. Android only;
  iOS Safari has no Vibration API, which is worth knowing before choosing a phone for it.
- Screen Wake Lock so the phone doesn't sleep mid-run, and an installable web app so
  there's no browser chrome.
- Touch targets at 64 px minimum, sized up from there as the grid allows.

### Customizable switches

The control set is **data, not markup**:

- The bridge reads `controls.sii` and publishes **every action your game has a binding
  for** as an available action — so "maybe more" needs no code change. If ATS can bind it,
  it's in the catalog. Unbound actions appear greyed with the reason.
- Each action declares its type: **toggle** (closed-loop, state from telemetry),
  **momentary** (fires on press), or **hold** (fires after ~800 ms — for anything costly).
- Layout is a saved config: any number of pages, a grid size you pick, actions placed where
  you want them, labels you can rename. Saved on the bridge, so every device shares it.
- Editing is locked while the truck is moving. You lay it out parked.

### Everything else

Speed limit is a first-class element and over-limit is unmissable. Stale telemetry kills
the display visibly rather than showing a confident number from thirty seconds ago. Dark by
default with a real day mode. And one derived line — **what bites first** — sits above the
raw numbers, because that's the question the in-game advisor doesn't answer.

## Phases

Each phase is independently useful. Stop after any of them and you still have something.

**Phase 1 — See the data.** Shared-memory reader, struct decode, version check, recorder
and simulator, a deliberately ugly HTML page dumping every field. Success: numbers move
when the truck moves. This is where the unknowns are; get them out of the way first.

**Phase 2 — The dashboard.** SSE transport, derived metrics, the real UI from the mockup,
three responsive layouts, stale/disconnect handling, day–night. Success: usable on a
tablet for a full run without touching it. **This is the milestone worth having.**

**Phase 3 — Control.** The focus spike first, then keybind discovery from `controls.sii`,
the injector, a default switch layout, arm/disarm and hold-to-fire, closed-loop state.
Success: the beacon comes on from the phone and the button agrees with the game.

**Phase 4 — Make it yours.** The action catalog from every binding the game exposes, the
layout editor, multiple switch pages, saved server-side so all devices share one layout.
Success: you build a page-one grid of the switches you actually use, without touching code.

**Phase 5 — Polish.** Wake lock and installable web app, trip history from recordings,
per-device view memory.

---

## Risks

| Risk | Handling |
| --- | --- |
| Input ignored when the game is unfocused | Spike before building. Second device is the primary path anyway; virtual gamepad is the fallback. |
| Plugin struct changes on update | Version check at startup, refuse to decode on mismatch, field map isolated in one file. |
| Third-party binary dependency | Pin a version, document the install, degrade to the simulator when absent. |
| Wi-Fi latency or drops | SSE auto-reconnects; UI shows connection state and age of last packet rather than hiding it. |
| Accidental destructive action | Disarmed by default, hold-to-fire on anything costly. |
| Exposure beyond the LAN | Bind to the LAN interface only, optional shared token. Never port-forward it. |

## Non-goals

- Driving the truck. No steering, throttle or brake — buttons operate switchgear only.
- Automation. Every command comes from a press; the bridge never fires a sequence on its
  own, on any server. This is what keeps the control half defensible on TruckersMP.
- Replacing the in-game route advisor. This complements it.
- A cloud service. It runs on your machine, on your network, and nowhere else.

## Decisions made

| | |
| --- | --- |
| Primary device | **Phone.** Portrait and landscape both supported. |
| Platform | **Windows.** Scancode injection via `ctypes`, no dependencies, ViGEm only if the focus spike demands it. |
| Control scope | **Everything bindable**, with a user-editable layout rather than a fixed set. |
| Page separation | **Separate URLs per view**, fixed thumb bar to switch, and no vertical scrolling anywhere. |
| TruckersMP | Telemetry yes. Control is one-press-one-keypress, never automated — see above, and check the current rules yourself. |

## Still open

1. **Which switches do you actually reach for mid-drive?** The catalog will hold
   everything, but page 1 should be the handful you use without thinking. Tell me those
   and they become the default layout.
2. **Landscape or portrait** in the mount? It changes which grid shape is the default.
3. **Android or iPhone?** Only affects whether haptics are available — everything else is
   identical.
