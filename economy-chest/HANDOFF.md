# Handoff — Economy Chest

What this project still needs from a machine with the game on it, and why each item is
open. Everything here was built and tested in a Linux container with no ATS install, so
the gaps are all "unverified", not "unwritten".

Branch: `claude/ats-economy-chest-mod-h4nl49`. Run `bash tests/smoke_test.sh` first — 52
checks, all green, and they cover the packaging logic that does not need the game.

---

## 1. Build in patch mode against your real def files

**This is the one that matters.** The committed `dist/*.scs` is a *standalone* build: it
was assembled from community-reported stock values, and a mod's `def/economy_data.sii`
**replaces** the game's file rather than merging into it. Every economy attribute the
standalone file does not list therefore falls back to an engine default rather than SCS's
tuned value — loan terms, fine amounts, garage prices, AI driver wages. It works, and it
is how most workshop money mods are built, but it is not what you want on a profile you
care about.

Patch mode reads what your game actually ships and rewrites only the targeted lines.

```
1. Copy def.scs out of the game folder. Never unpack over the original.
     C:\Program Files (x86)\Steam\steamapps\common\American Truck Simulator\def.scs
2. Unpack it. It is HashFS, not a zip — a normal unzip tool will not open it.
     scs_extractor.exe def.scs
3. python build_mod.py --base <extracted>\def\economy_data.sii --money 10 --xp 10
```

See `docs/INSTALL.md` for the full extraction walkthrough.

## 2. Check the build's warnings — they are the real test

Patch mode prints every attribute it scaled with old and new values, and warns about any
it expected and did not find. **That warning list is how you find out whether my field
names are right for ATS.** They came from community sources, not from SCS documentation,
and some are ETS2-derived.

Scaled for money — if any of these is reported missing, the name is wrong for your build:

- `revenue_coef_per_km` (freight market)
- `cargo_market_revenue_coef_per_km`
- `driver_revenue_coef_per_km` (quick jobs and AI drivers)
- `driver_cargo_market_revenue_coef_per_km`

Scaled for XP: `exp_cargo_delivery`, `exp_free_roam`, `exp_road_discovery`,
`exp_park_load_bonus`, `exp_park_double_bonus`, `exp_park_bonus`. The last three are the
least certain — I would not be surprised if the parking bonuses are named differently.

Also worth reading: any `exp_*` attribute the builder saw but did not touch gets reported.
If one of those looks like an XP amount rather than a threshold, add it to `xp_fields` in
`scale_rules.json`.

`revenue_per_km_base` is deliberately **not** scaled — it would compound with the
coefficients and give you ×100 instead of ×10. Confirm it is present but unchanged in the
built file.

## 3. Correct the reference defaults

`scale_rules.json` carries stock values used only by `--standalone`:

| attribute | assumed stock |
| --- | --- |
| `revenue_coef_per_km` | 0.3 |
| `cargo_market_revenue_coef_per_km` | 1.0 |
| `driver_revenue_coef_per_km` | 0.67 |
| `driver_cargo_market_revenue_coef_per_km` | 0.7 |
| `exp_cargo_delivery` | 1.25 |
| `exp_free_roam` | 0.45 |
| `exp_road_discovery` | 0.75 |

These are community numbers, largely ETS2-era. Once you have the real file, replace them
with your game's actual values and note the game version in the JSON's comment block. That
makes standalone builds correct for ATS instead of approximately right for ETS2.

## 4. Verify in game

1. Enable the mod, top of the Mod Manager load order.
2. Start a new job from the freight market. Payout should be about ten times the same run
   with the mod off.
3. **Offers generated before you enabled it keep their old price.** Sleep or skip a few
   hours and look at fresh offers before concluding it does not work.
4. Check XP on delivery, and that the level bar moves about ten times as fast.

If payouts look unchanged, run `mod-doctor` against your mod folder before debugging the
mod — a second economy mod winning the load order looks exactly like this.

## 5. Workshop publishing

```
python build_mod.py --base <...> --workshop --preview preview.png
```

Then point the **SCS Workshop Uploader** (`bin/win_x64` in the game folder) at
`dist/workshop/`. The build enforces the three rules that break uploads silently — folder
contents, `package_name` matching the archive, and the single package carrying no
`compatible_versions[]` — so the part left to you is the artwork:

- **Steam preview: 640×360, under 1 MB.** `--preview` validates it and places it *beside*
  the upload folder, because the uploader takes it separately and a stray file in the
  upload folder gets the item rejected.
- **Mod Manager icon: 276×162 .jpg**, passed with `--icon`, and it goes *inside* the
  package. Different image, different job — the validator exists because these get mixed up.

Neither image can be generated here; no imaging library in the container, and a flat
colour rectangle would not be worth committing.

## Open questions only a real run answers

1. Are all ten scaled attribute names correct for current ATS?
2. Are the reference defaults right for ATS, or are they ETS2 values?
3. Does ×10 actually feel right, or is the interesting build ×5 with ×20 XP? The
   multipliers are arguments, so this is a matter of taste once it works.
