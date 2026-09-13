# Economy Chest

A money and XP multiplier mod for **American Truck Simulator**. Default build is
**1000% (×10) money and 1000% (×10) XP** — every job pays ten times stock and awards
ten times stock experience.

This repo is the mod *source*: a small builder that produces a `.scs` package you drop
into your ATS mod folder. Multipliers are arguments, so ×10 is only the default.

```
tools/build_mod.py    builds the .scs
tools/scale_rules.json which economy attributes get scaled, and why
pkg/                  manifest + in-game description templates
dist/                 a prebuilt ×10 package you can use right now
tests/                fixture + smoke test
```

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

## Tests

```bash
bash tests/smoke_test.sh
```

36 checks covering scaling, preservation of unrelated attributes, archive layout,
manifest rendering and the failure paths.
