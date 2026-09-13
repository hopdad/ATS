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

## Tests

```bash
bash run_tests.sh
```

Runs all three suites: 52 checks for the Economy Chest builder, 49 for the mod doctor, and
49 unit tests for the Cab Deck bridge.
