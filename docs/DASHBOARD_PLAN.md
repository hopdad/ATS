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

### The control set — situational, not routine

The phone is not for the things you do constantly. Lights, cruise and the horn are already
muscle memory on the wheel or the keyboard, and a phone is a worse place for them. The
phone earns its keep on the controls you need **in a specific moment** and can never
remember the key for.

That flips the default layout from the first draft:

**Page 1 — grade and traction.** Retarder, engine brake (Jake), differential lock, lift
axle (tractor and trailer separately), hazards, beacon. The ones you want going down a
grade, at a scale, or backing in a yard.

**Page 2 — cameras.** The game numbers them 1–8 and nobody remembers which is which.
Named instead: Interior, Lean out, Bumper, On wheel, Drive by, Top down, Trailer, Free cam.
One tap each, exclusive selection. This alone may be the most-used page.

**Page 3 — yard.** Park brake, hook/unhook, engine start/stop, wipers, cab light, horns.
Things you do stopped, where a hold-to-fire delay costs nothing.

### Not everything is a toggle

Your examples broke the three-type model from the first draft. The real set is five:

| Type | Behaviour | Examples |
| --- | --- | --- |
| **toggle** | on/off, state confirmed by telemetry | Jake brake, diff lock, hazards, lift axle |
| **stepped** | a stage with − and +, current stage read back | retarder, wipers |
| **exclusive** | one of N, the others clear | cameras |
| **momentary** | fires on press | horn, cruise set, route advisor |
| **hold** | fires after ~800 ms | unhook, engine stop |

**The stepper is where the no-automation rule bites, and it's worth being explicit.**
The game has no "set retarder to stage 2" binding — only increase and decrease. A tidy UI
would let you tap stage 2 and have the bridge send two keypresses to get there. That is a
small burst from one press, which crosses the line I set out above.

So the stepper sends **one keypress per tap** and shows the stage read back from telemetry.
You tap − twice to drop two stages, exactly as you would on the keyboard. Slightly less
slick, and it keeps one press equal to one keypress with nothing to argue about. A
"jump to stage" mode can be a setting you turn on yourself, clearly labelled, off by default.

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

### Pressing without looking — on an iPhone

iOS has no Vibration API. WebKit does not expose `navigator.vibrate`, and Apple's stated
reason is abuse potential, so this is unlikely to change. That removes the obvious
eyes-free confirmation channel and the design has to make it up elsewhere.

**Fewer, bigger targets.** Two columns instead of three, minimum 70 px tall, positionally
distinct. A grid you can hit by position beats a dense one you have to read. This is the
primary mitigation and it costs nothing.

**An audible click** on every press, via Web Audio — a 15 ms tick, volume adjustable, and
switchable off. On iOS the audio context needs a user gesture first, which arming provides.
This is the reliable confirmation channel on iPhone.

**Haptics as a bonus, not a dependency.** There is a known trick: Safari 17.4's
`<input type="checkbox" switch>` fires the system haptic engine when toggled, and libraries
exploit it to get buzz out of an iOS web page. Apple has already patched around some of
these once, so treat it as a nice-to-have that may stop working, never as the only signal.
The Setup view carries a real switch you can tap on your own phone to see whether it buzzes.

**Fixed positions.** A switch never moves between sessions, and the thumb bar never moves at
all. That is what actually makes it operable without looking.

Plus: Screen Wake Lock so the phone doesn't sleep mid-run (supported in recent iOS Safari —
verify on your device), Add to Home Screen for a standalone window with no Safari chrome,
and `env(safe-area-inset-*)` so nothing hides under the home indicator.

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

### Real time, not game time

The question you're actually asking when you glance at the phone is "how much longer is
this run going to take **me**?" — and nothing in the game answers it. Every clock in ATS is
in game time.

**The conversion is not a constant, which is what makes this worth building.** ATS runs
game time about **20× real time on the open road, but about 3× inside a city**, so the map
feels the right size at both scales. The SDK reports the current factor as
`local_scale`, so the bridge doesn't have to guess.

Dividing the whole remaining journey by the current scale is therefore wrong exactly where
it matters most — the last few miles into town, where each game minute suddenly costs you
almost seven times more real time. So the estimate is split: the final approach is costed at
city scale, everything before it at highway scale.

```
real minutes left = highway game-minutes / local_scale
                  + approach game-minutes / city scale
```

The bridge also **measures** the ratio continuously — game-time delta over real-time delta,
smoothed — as a cross-check and a fallback. Measuring costs nothing and means a time-scale
mod, or a plugin that doesn't expose `local_scale`, changes nothing.

Three cases the naive version gets wrong, and what to do:

- **Paused.** Game time stops, the ratio goes to zero, the estimate goes to infinity. Show
  "paused", not a number.
- **Sleeping or a ferry.** Game time fast-forwards; the measured ratio spikes. Discard
  out-of-band samples. There's a pleasant truth hiding here worth surfacing: a nine-hour
  rest costs you about ten real seconds, so **resting is nearly free in your time** and
  only driving is expensive.
- **The estimate lengthens as you approach town.** That's correct behaviour, not drift —
  and the display names the scale in use so it reads as an explanation rather than a glitch.

What the dashboard shows:

```
YOUR TIME TO BARSTOW
38 min                    finish  9:42 pm
2h 04m game · 20× highway · incl. 4 mi city at 3×
```

The **finish time on your own wall clock** is the more useful of the two numbers, because
the real question is usually "can I get this done before I have to be somewhere." It needs
no mental arithmetic. The "bites first" line picks up the same treatment — a rest stop
1h 12m away is really only about four minutes of your evening.

### Pay in your time

`$ / real hour` — the job's payout divided by the real minutes it will actually cost you.

This only exists because the time conversion exists, and no screen in the game can show it.
It is the only way to compare a 280-mile haul against three short runs in the currency that
actually matters: your evening. A job paying $4,180 over 38 real minutes is $6,600 an hour
of your life; the same money over two hours is not the same job.

### Room left on purpose

The obvious thing to do with the space left on the screen is fill it with gauges. Don't.
Oil pressure, water temp, battery voltage and air pressure are all in the telemetry and all
boring 99% of the time, and a dashboard crowded with steady numbers reads slower than a
quiet one.

So the remaining space is an **attention strip that is empty in the normal case**:

| Shows | When |
| --- | --- |
| Over the limit, with a duration | over the posted limit for more than ~8 s |
| Air pressure falling | below ~90 psi |
| Fuel under an hour | range below the next hour of driving |
| Damage climbing | a step change since the last sample |
| Engine temp / oil pressure / battery | outside normal band |

Nothing renders when nothing is wrong, and the rest of the screen breathes. This is the
answer to "we have room": reserve it, don't spend it.

### TruckersMP, when you're on it

The public API at `api.truckersmp.com/v2` is open, unauthenticated JSON. Three endpoints
earn a place, and the strip only renders when you're actually on MP:

- **`/servers`** — the server you're on, `players` and `queue`, and two flags that change how
  you drive: `speedlimiter` (whether the server caps you) and `collisions`. Also `promods`
  and whether it's an event server. Poll on the order of a minute.
- **`/events`** — the next convoy or event, with its start time, counted down **in real
  time** next to your own finish estimate. "You finish at 9:42 pm, the convoy starts at
  10:00" is exactly the composition of the two features, and it is the strongest reason to
  bother with the API at all.
- **`/game_time`** — TruckersMP's synchronised clock. Worth noting: on MP the time scale is
  the server's, not the single-player `local_scale`, so the real-time conversion changes
  shape there. The measured-ratio fallback already handles this without special-casing.

`/version` (is MP up for this game build?) is useful before you launch, not while driving.
`/player/{id}` and `/bans` are about your account, not your run.

**What the API cannot do**, so the design shouldn't imply it: it describes *servers*, not
*you*. There is no position, no nearby players, no "who just cut me off." Anything
player-local still comes from the game's own telemetry.

Three caveats. This is the only part of the system that needs internet — everything else is
LAN-only — so it's opt-in and fails quietly to a hidden strip. Published rate limits weren't
something I could confirm, so cache hard regardless (servers ~60 s, events ~15 min) and
never poll per frame. And Economy Chest and TruckersMP are mutually exclusive: MP supports
only ProMods and Grimes' weather, so the two halves of this repo never run at once.

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
| Orientation | **Portrait** to start. Two columns of large targets. |
| Stepper | **Confirmed** — one tap, one keypress, stage read back. No jump-to-stage by default. |
| Eyes-free | **Audio click** is the primary channel on iPhone; haptics are a bonus if the Safari trick holds. |
| Phone | **iPhone.** No Vibration API — click and target size carry eyes-free use; haptics are a bonus. |
| Control scope | **Everything bindable**, with a user-editable layout. Defaults are the situational set, not the routine one. |
| Page separation | **Separate URLs per view**, fixed thumb bar to switch, and no vertical scrolling anywhere. |
| TruckersMP | Telemetry yes. Control is one-press-one-keypress, never automated — see above, and check the current rules yourself. |

## Still open

1. **Does the haptic trick work on your phone?** Tap the switch in the mockup's Setup view.
   If it buzzes, haptics stay in the plan as a secondary channel; if not, the click carries
   eyes-free use alone and I'll spend the effort on target size instead.
2. **How long is the city approach, really?** The real-time estimate assumes the last 4 miles
   run at city scale. That number wants calibrating against a few actual runs — Phase 1's
   recorder makes it measurable rather than guessed.
3. **Anything missing from page 1?** Trailer brake (trolley valve), axle group selection and
   cruise are the obvious candidates I left off.
4. **Landscape later?** Portrait is the start, but a mounted phone often ends up sideways.
   Worth knowing whether that's a Phase 5 item or never.
