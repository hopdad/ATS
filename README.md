# ATS mods and tooling

Mods and utilities for **American Truck Simulator**. Everything here is Python 3.8+ with
no dependencies.

| | |
| --- | --- |
| [**Economy Chest**](#economy-chest) | A money and XP multiplier mod. Default ×10. |
| [**Mod doctor**](#mod-doctor) | Finds broken packages, file conflicts and dead mods in your mod folder. |
| [**Cab Deck**](docs/DASHBOARD_PLAN.md) | Planned: a second-screen telemetry dashboard with truck controls. Plan and UI mockup only. |

```
tools/build_mod.py     builds the Economy Chest .scs
tools/scale_rules.json which economy attributes get scaled, and why
tools/mod_doctor.py    inspects a mod folder
pkg/                   manifest + in-game description templates
dist/                  a prebuilt ×10 package you can use right now
docs/                  install guide, mod doctor reference, dashboard plan
tests/                 fixtures and smoke tests
```

# Economy Chest

**1000% (×10) money and 1000% (×10) XP** — every job pays ten times stock and awards ten
times stock experience. Multipliers are arguments, so ×10 is only the default.

## Quick start

A ready-made ×10 package is checked in:

```
dist/economy_chest_money_x10_xp_x10.scs
```

Copy it to `Documents/American Truck Simulator/mod/` and enable it in the Mod Manager.
That build is *standalone* — see [the caveat](#the-standalone-caveat) below, then build
it properly from your own game files with two commands.

## Building it properly

Patch mode reads the `economy_data.sii` your copy of the game actually ships, scales the
money and XP attributes, and copies everything else through untouched. It matches your
game version exactly and cannot disturb an unrelated economy setting.

1. Unpack `def.scs` from your ATS install (see [docs/INSTALL.md](docs/INSTALL.md)) and
   find `def/economy_data.sii` in it.
2. Build:

```bash
python3 tools/build_mod.py --base /path/to/economy_data.sii
```

The `.scs` lands in `build/`. Python 3.8+, no dependencies.

```bash
# other multipliers
python3 tools/build_mod.py --base ./economy_data.sii --money 10 --xp 10
python3 tools/build_mod.py --base ./economy_data.sii --money 5  --xp 20
python3 tools/build_mod.py --base ./economy_data.sii --money 11 --xp 11   # if you meant +1000%

# point it at the extracted folder instead of the file
python3 tools/build_mod.py --base ~/ats_def_extracted

# metadata
python3 tools/build_mod.py --base ./economy_data.sii \
    --name "My Economy" --author "me" --mod-version 1.2 \
    --game-versions "1.54,1.55" --icon my_icon.jpg

python3 tools/build_mod.py --help
```

The build prints every attribute it changed, with old and new values, and warns about
anything it expected to find and didn't.

## What it changes

Job payout in ATS is roughly `revenue_per_km_base × <coefficient for that job type> ×
distance × cargo and urgency modifiers`. The mod scales the four per-km coefficients:

| Attribute | Affects |
| --- | --- |
| `revenue_coef_per_km` | freight market jobs |
| `cargo_market_revenue_coef_per_km` | cargo market jobs |
| `driver_revenue_coef_per_km` | quick jobs and your AI drivers |
| `driver_cargo_market_revenue_coef_per_km` | AI drivers on cargo market jobs |

Scaling the coefficients rather than `revenue_per_km_base` keeps the relative balance
between job types intact — quick jobs stay worse than owned-trailer runs, they all just
pay ×10. `revenue_per_km_base` is deliberately left alone so the two don't compound.

XP scales `exp_cargo_delivery`, `exp_free_roam`, `exp_road_discovery` and the parking
bonuses. `exp_resolution` and friends are thresholds, not XP amounts, so they are never
touched. An `exp_*` attribute the builder doesn't recognise is reported and left at
stock; `--scale-all-exp` opts in to scaling it too.

Nothing else moves: cargo prices, fines, loans, garage and truck prices, damage costs
and AI driver wages all stay stock. Edit `tools/scale_rules.json` to change that.

## The standalone caveat

`--standalone` (and the prebuilt `dist/` package) builds without reading your game files,
using community-reported stock values. It is convenient and it works, but be aware of
what it is: a mod's `def/economy_data.sii` **replaces** the game's file rather than
merging into it, so every economy attribute the standalone file does not list falls back
to an engine default instead of SCS's tuned value. The stock values it starts from are
also version- and game-dependent — ATS and ETS2 differ, and SCS retunes between patches.

That is why patch mode exists, and why it is worth the one-time extraction. Use
standalone to try the mod out; use `--base` on a profile you care about.

## Notes

- Single player. Don't use it in Convoy with players who don't have it.
- Only one money/XP economy mod can be active at a time — put this at the top of the
  Mod Manager load order.
- Jobs are priced when generated. Offers already in the freight market keep their old
  payout; sleep or skip a few hours for new ones.
- Removing the mod returns rates to stock and does not claw back what you earned.

# Mod doctor

Answers "why isn't my mod doing anything?" without launching the game.

```bash
python3 tools/mod_doctor.py --mods ~/ats/mod --profile ./profile.sii --game-version 1.55
```

With no `--mods` it uses this platform's ATS mod folder; `--game ets2` switches the
default to Euro Truck Simulator 2. Three things it reports:

**Packaging problems** — a mod the game quietly ignores. The big one is contents buried in
a subfolder inside the `.scs`, which makes a mod load absolutely nothing while still
looking fine in the Mod Manager. Also dangling icon and description references, unknown
categories, and a `compatible_versions[]` that excludes your build.

**File conflicts** — two mods shipping the same path. Only one wins, and load order decides
which. Conflicts are grouped by the mods involved, so two map mods sharing 4,000 files are
one line rather than 4,000, and paths that change how the game *plays* are listed first.

**Mods doing nothing** — a mod whose every file is overridden by something above it. It is
enabled, it looks healthy, and it has no effect at all. This is the most common cause of
"my mod isn't working" and it is invisible in-game.

```
CONFLICTS  (2 group(s), 2 file(s) provided by more than one mod)

  1 shared file:
    WINS   economy_chest.scs
    loses  realistic_economy.scs
    gameplay-affecting:
      def/economy_data.sii

DOING NOTHING  (every file this mod provides is overridden by something above it)
  tiny_cargo_tweak.scs
    fully overridden by: realistic_economy.scs
    move it higher in the Mod Manager, or remove it
```

Load order comes from a decrypted `profile.sii` (`--profile`) or a hand-typed list
(`--order`); position 1 is the top of the Mod Manager list. Without one it still reports
conflicts but declines to name a winner. `--json` for machine-readable output, `--strict`
to exit non-zero on findings.

Two limits worth knowing: HashFS-packed mods can't be opened, so conflicts involving them
are invisible; and detection is file-level, so two mods editing different attributes of the
same `.sii` still count as a conflict — which is accurate, since the loser's whole file is
discarded either way.

Full reference: [docs/MOD_DOCTOR.md](docs/MOD_DOCTOR.md).

# Tests

```bash
bash tests/smoke_test.sh         # Economy Chest builder  - 36 checks
bash tests/doctor_smoke_test.sh  # mod doctor             - 49 checks
```

The doctor suite generates a fixture mod folder (`tests/make_fixture_mods.py`) containing
a well-formed mod, a conflicting one, a fully shadowed one, a wrongly-packed one, one with
no manifest, one with dangling references, a HashFS package, an unpacked folder mod, and
both a plain-text and an encrypted profile.
