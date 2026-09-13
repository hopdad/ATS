# Mod doctor

Answers "why isn't my mod doing anything?" without launching the game. Finds packages the
game quietly ignores, files two mods both claim, and mods that are enabled but completely
overridden.

Single file, no dependencies — copy `mod_doctor.py` anywhere and run it.

```bash
python3 mod_doctor.py --mods ~/ats/mod --profile ./profile.sii --game-version 1.55
```

Python 3.8+, no dependencies. With no `--mods` it uses this platform's ATS mod folder;
`--game ets2` switches the default to Euro Truck Simulator 2.

## What it checks

### Packaging

| Finding | Why it matters |
| --- | --- |
| `manifest.sii` inside a subfolder | **Error.** The game reads paths from the archive root, so `My Mod/def/…` is not `def/…`. The mod loads nothing. Repack with the contents at the top level. |
| No `manifest.sii` | Warning. It still loads, but the Mod Manager shows no name, author or version, and newer builds may reject it. |
| `description_file` / `icon` not in the archive | Warning. The Mod Manager falls back to placeholders. |
| Icon that isn't a `.jpg` | Warning. It wants a 276x162 jpg. |
| Unknown `category[]` | Warning. Valid values are the 17 SCS categories. |
| `compatible_versions[]` excludes your build | Warning, and the reason a mod shows as incompatible. Needs `--game-version`. |
| Metadata only | Warning. Nothing for the game to load. |
| HashFS packing | Note. Contents can't be listed, so conflicts involving it are invisible here. Base-game archives and some encrypted mods are packed this way. |

### Conflicts

Two mods shipping the same path. Only one wins; load order decides which. Conflicts are
grouped by the set of mods involved, so a pair of map mods sharing 4,000 files is one
group, not 4,000 lines. Paths that change how the game *plays* rather than how it looks —
`def/economy_data.sii`, `def/cargo.sii`, truck defs and similar — are listed first under
`gameplay-affecting:`.

`manifest.sii`, `mod_description.txt` and `icon.jpg` are excluded. Every mod has those and
sharing them is not a conflict.

### Mods doing nothing

A mod whose every file is also provided by something above it in the load order. It is
enabled, it looks healthy in the Mod Manager, and it has no effect whatsoever. This is the
most common "why isn't my mod working" cause and it is invisible in-game.

Needs a load order to detect — without one the section is skipped rather than guessed at.

## Getting your load order

Position 1 is the highest priority, matching the **top** of the Mod Manager's active list.
A mod higher in the list overrides the ones below it.

**From a profile.** Profiles live next to the mod folder under `profiles/<hex name>/`, and
the active mod list is in `profile.sii`:

```bash
python3 mod_doctor.py --profile ~/.local/share/American\ Truck\ Simulator/profiles/*/profile.sii
```

Profiles are normally saved encrypted — the file starts with `ScsC` rather than `SiiN`.
The tool says so and stops rather than guessing. Decrypt it with SII_Decrypt or a similar
community tool first, or use the manual route below. (Decrypt a *copy*.)

**By hand.** Type your Mod Manager list into a text file, highest first:

```
# highest priority first
economy_chest.scs
realistic_economy.scs
traffic_tweaks.scs
```

```bash
python3 mod_doctor.py --order my_order.txt
```

If the resulting `LOAD ORDER` block reads upside down compared to your Mod Manager, pass
`--reverse-order`. Comparing that block against the game is a worthwhile sanity check —
every winner in the report depends on getting this direction right.

Workshop subscriptions are not files in the mod folder, so they show as
`active but not in the mod folder`. They still occupy a position in the order and can still
win a conflict; the tool can't see inside them.

## Reading the output

```
CONFLICTS  (2 group(s), 2 file(s) provided by more than one mod)

  1 shared file:
    WINS   economy_chest.scs
    loses  realistic_economy.scs
    gameplay-affecting:
      def/economy_data.sii
```

`realistic_economy.scs` ships an `economy_data.sii` that the game never reads. To flip it,
move that mod above `economy_chest.scs` in the Mod Manager.

```
DOING NOTHING
  tiny_cargo_tweak.scs
    fully overridden by: realistic_economy.scs
```

Move it up or uninstall it.

## Other flags

```bash
--json           machine-readable output: packages, order, conflict groups, shadowed mods
--strict         exit 1 if any error or conflict was found
--examples N     conflicting paths to list per group (default 5)
```

## Limits

- HashFS-packed mods are opaque. Their conflicts don't appear.
- File-level only. Two mods editing *different* attributes inside the same `.sii` still
  show as a conflict, because at the file level that is exactly what it is — the whole
  file from the loser is discarded, including the parts that did not overlap.
- No opinion on load-order *convention* (fixes above trucks above maps). It reports what
  actually collides in your folder; ordering beyond that is your call.

## Tests

```bash
bash tests/doctor_smoke_test.sh
```

49 checks against a generated fixture mod folder (`tests/make_fixture_mods.py`) containing
a well-formed mod, a conflicting one, a fully shadowed one, a wrongly-packed one, one with
no manifest, one with dangling references, a HashFS package, an unpacked folder mod, and
both a plain-text and an encrypted profile.
