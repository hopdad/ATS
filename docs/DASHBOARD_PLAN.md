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

### Where this must not be used

Injecting synthetic input is a single-player and Convoy-with-friends thing. **Do not use
the control half on TruckersMP** — external input automation is the kind of thing their
rules exist to cover. The read-only dashboard is unobjectionable anywhere.

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

The design brief, since this is the part that matters most:

**It is read at a glance, at arm's length, while driving.** That is closer to an instrument
panel than a web page. Big numerics, high contrast, no scrolling mid-drive, touch targets
sized for a bumpy tap rather than a mouse.

**One synthesized line beats six gauges.** The in-game route advisor already shows raw
numbers. What it doesn't tell you is *which constraint bites first* — fuel range, the rest
timer, or the delivery deadline. The dashboard computes all three and says which one is
about to be your problem. This is the single strongest reason for a second screen to exist.

**Speed limit is a first-class element,** not a small icon. Going over is the most common
avoidable cost in the game, so over-limit is a state change you cannot miss.

**Stale data is loud.** If telemetry stops — game paused, alt-tabbed, plugin crashed — the
numbers visibly go dead and a banner says so. A dashboard that shows a confident 65 mph
while disconnected is worse than a blank screen.

**Dark by default, with a real day mode.** Night driving is the common case; a day palette
is a toggle, not an afterthought.

**Three layouts:** landscape tablet (primary), phone portrait (control rail becomes a
bottom sheet), wide second monitor.

---

## Phases

Each phase is independently useful. Stop after any of them and you still have something.

**Phase 1 — See the data.** Shared-memory reader, struct decode, version check, recorder
and simulator, a deliberately ugly HTML page dumping every field. Success: numbers move
when the truck moves. This is where the unknowns are; get them out of the way first.

**Phase 2 — The dashboard.** SSE transport, derived metrics, the real UI from the mockup,
three responsive layouts, stale/disconnect handling, day–night. Success: usable on a
tablet for a full run without touching it. **This is the milestone worth having.**

**Phase 3 — Control.** The focus spike first, then keybind discovery from `controls.sii`,
the injector, the control rail, arm/disarm and hold-to-fire, closed-loop state. Success:
the beacon comes on from the tablet and the button agrees with the game.

**Phase 4 — Polish.** Multi-client, per-device layout persistence, trip history from
recordings, button macros ("night driving": low beam on, interior off).

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
- TruckersMP. Read-only is fine there; control is not.
- Replacing the in-game route advisor. This complements it.
- A cloud service. It runs on your machine, on your network, and nowhere else.

## Open questions for you

1. **Primary device** — phone, tablet, or second monitor? It changes which layout gets the
   design attention first.
2. **Windows or Linux/Proton** for the game? Both are workable; the plugin and the
   injection path differ.
3. **How far into control?** The full switchgear set above, or a small set you actually
   reach for while driving?
