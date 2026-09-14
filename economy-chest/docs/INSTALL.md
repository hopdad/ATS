# Installing and building

## Where the mod folder is

| Platform | Path |
| --- | --- |
| Windows | `%USERPROFILE%\Documents\American Truck Simulator\mod\` |
| Linux | `~/.local/share/American Truck Simulator/mod/` |
| macOS | `~/Library/Application Support/American Truck Simulator/mod/` |

Drop the `.scs` file straight in — do not unpack it, do not put it in a subfolder.
Then launch ATS, open **Mod Manager** from the profile screen, and move
*Economy Chest* into the active list.

## Load order

Mod Manager applies mods top to bottom, and only one mod's `def/economy_data.sii`
can win. If you run any other economy, money, XP or "realistic economy" mod, put
Economy Chest **above** it — otherwise the other mod's file loads and this one does
nothing. Symptom of a load-order problem: the mod is enabled but payouts look stock.

## Extracting economy_data.sii for a patch-mode build

Patch mode needs the `economy_data.sii` your game ships. It lives inside `def.scs`
in the game install directory:

| Platform | Path |
| --- | --- |
| Windows | `C:\Program Files (x86)\Steam\steamapps\common\American Truck Simulator\def.scs` |
| Linux | `~/.steam/steam/steamapps/common/American Truck Simulator/def.scs` |
| macOS | `~/Library/Application Support/Steam/steamapps/common/American Truck Simulator/def.scs` |

`def.scs` is not a ZIP — modern game archives use SCS's own HashFS format, so a normal
unzip tool will not open it. Unpack it with one of:

- **SCS Extractor** — the official command line tool from SCS Software's modding
  downloads page: `scs_extractor.exe def.scs`
- Any community ATS/ETS2 archive extractor that advertises HashFS v2 support.

Extract somewhere scratch, then point the builder at it:

```bash
python3 tools/build_mod.py --base ~/ats_def_extracted
# or directly at the file
python3 tools/build_mod.py --base ~/ats_def_extracted/def/economy_data.sii
```

The builder also accepts a ZIP-format `.scs` (`--base some_mod.scs`), which is useful
for rebasing on top of another economy mod's file rather than the stock one.

Copy your game's `def.scs` somewhere else before extracting; never unpack over the
original or edit it in place. Verifying game files in Steam restores it if you do.

## Checking it worked

1. Start a new job from the freight market after enabling the mod.
2. The offered payout should be about ten times what the same run pays with the mod off.

If payouts look unchanged:

- Offers generated *before* you enabled the mod keep their old price. Sleep, or skip a
  few hours, and look at fresh offers.
- Check the load order above.
- Check the Mod Manager did not flag the mod as incompatible with your game version.
  Rebuild with `--game-versions "1.5*"` or with your exact version, e.g.
  `--game-versions "1.55.*"`.

## Adding an icon

Mod Manager shows a **276x162 pixel .jpg**. The builder includes one if you pass it:

```bash
python3 tools/build_mod.py --base ./economy_data.sii --icon my_icon.jpg
```

Without `--icon` the manifest simply omits the entry and the Mod Manager shows its
default placeholder.

## Uninstalling

Disable it in Mod Manager, or delete the `.scs` from the mod folder. Rates return to
stock immediately. Money and levels you already earned stay — the mod changes the rate
jobs are priced and scored at, nothing retroactive.
