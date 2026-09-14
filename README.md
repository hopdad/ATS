# ATS

Mods and tooling for **American Truck Simulator**. Python 3, standard library only —
nothing here needs installing.

| Project | What it is |
| --- | --- |
| [**economy-chest/**](economy-chest/) | A money and XP multiplier mod. Default ×10, Workshop-ready. |
| [**mod-doctor/**](mod-doctor/) | Finds broken packages, file conflicts and dead mods in your mod folder. |
| [**cab-deck/**](cab-deck/) | A second-screen telemetry dashboard with truck controls. Phase 1 building. |

## How this repo is laid out

Each project is a self-contained folder with its own README, tests, docs and build output:

```
economy-chest/   build_mod.py  scale_rules.json  pkg/  dist/  docs/  tests/
mod-doctor/      mod_doctor.py                          tests/
cab-deck/        bridge/       run_tests.sh             docs/  tests/
```

There is deliberately **no shared library**. The two mod tools each parse a little SII and
could share that code, but single-file tools are how mod tooling actually gets used — you
lift `mod_doctor.py` out on its own and run it. A shared package would trade that away for
a few dozen deduplicated lines.

## Waiting on a machine with the game installed

All three projects were built in a container with no ATS install, so each carries a handoff
doc listing what is unverified and how to check it:

- [economy-chest/HANDOFF.md](economy-chest/HANDOFF.md) — build against real def files,
  confirm the scaled attribute names, correct the reference defaults, publish.
- [mod-doctor/HANDOFF.md](mod-doctor/HANDOFF.md) — run against a real mod folder, and
  confirm the load-order direction that every conflict verdict rests on.
- [cab-deck/README.md](cab-deck/README.md) — derive the plugin struct layout from its
  header, then record a real run to calibrate the city approach.

## Tests

```bash
bash run_tests.sh
```

Runs all three suites: 52 checks for the Economy Chest builder, 49 for the mod doctor, and
49 unit tests for the Cab Deck bridge.
