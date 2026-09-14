# Cab Deck bridge

Phase 1 of [the plan](docs/PLAN.md): read telemetry, derive the
things the game does not tell you, and make all of it developable without the game running.

Python 3.10+, standard library only.

```bash
python3 -m bridge simulate                    # watch the pipeline with no game installed
python3 -m bridge record -o runs/i15.jsonl    # capture a run
python3 -m bridge replay runs/i15.jsonl       # play it back through the pipeline
bash run_tests.sh                             # 49 tests
```

`simulate` prints a line per quarter second:

```
 54.0 / 55 mph | scale 20.0x |  127.3 mi | real   10m | $  26239/h | first: arrive  10m | -
 51.0!/ 45 mph | scale 20.0x |  112.3 mi | real    9m | $  28154/h | first: arrive   9m | air
```

`!` marks over the limit, `real` is minutes of your life, `$/h` is pay per real hour, and
the last column is the alert strip — empty almost always, by design.

## What's here

| | |
| --- | --- |
| `bridge/model.py` | The normalised frame. SI units in, display units at the edge. |
| `bridge/scale.py` | Measuring game time against real time, and the three ways that goes wrong. |
| `bridge/derive.py` | Real time left, what bites first, pay per real hour, alerts. |
| `bridge/sources.py` | Simulator, replay, and the real shared-memory source. |
| `bridge/record.py` | JSONL recorder — the test fixture and the calibration data. |

## Why a simulator came first

Everything above is written against a `Telemetry` frame, not against the game. That means
the interesting logic — the time conversion especially — is testable on any machine, and
two bugs were caught this way before a single byte of real telemetry was read:

- **A nine-hour sleep looked like a save reload.** Both are large forward jumps in game
  time; the fix is that a backwards jump means a different session while a forward one
  means fast-forward, and either way the measurement window spanning the gap has to be
  dropped rather than averaged across.
- **Driving through a town 110 miles out tripled the estimate.** Costing the whole
  remaining journey at the scale you happen to be in is right on the final approach and
  badly wrong anywhere else. Road not yet reached is now costed at remembered open-road
  pace. `test_passing_through_a_town_does_not_blow_up_the_estimate` holds that line.

## What still needs the gaming PC

**The struct layout.** The plugin publishes a C struct into a memory-mapped file, and the
field offsets are not safe to guess — a wrong offset decodes to a plausible number rather
than an error, which is the worst possible failure. So `SharedMemorySource` refuses to run
without a layout instead of inventing one. The layout comes from the plugin's own header.

**Input injection**, which is Windows-only and Phase 3 anyway. It opens with the focus
spike described in the plan.

Neither blocks anything else: `simulate` and `replay` exercise the entire pipeline.

## Calibrating the city approach

The real-time estimate assumes the last 4 miles run at city scale. That number is an
estimate, not a measurement. Record a few real runs and it becomes one — which is the
other reason the recorder exists.
