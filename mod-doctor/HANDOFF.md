# Handoff — Mod doctor

The tool is complete and its 49 checks pass, but every one of them runs against a mod
folder this repo *generates* (`tests/make_fixture_mods.py`). It has never seen a real mod
folder, a real profile, or a real Workshop subscription. This is the list of things that
can only be confirmed on your machine.

Branch: `claude/ats-economy-chest-mod-h4nl49`. Start with `bash tests/doctor_smoke_test.sh`.

---

## 1. Run it against your actual mod folder

```
python mod_doctor.py --game-version 1.55
```

With no `--mods` it uses this platform's ATS mod folder. Read the whole report, but the
part to scrutinise is **PACKAGES**: does the list match what your Mod Manager shows, with
the same names and roughly the right file counts? If a mod you have is missing from the
list, that is a bug in discovery, not in your install.

Expect some `[HashFS, contents not readable]` notes. That is correct behaviour — encrypted
or SCS-packed mods cannot be opened, and the tool says so rather than reporting a clean
bill of health it cannot support.

## 2. Confirm the load-order direction — do this before trusting any verdict

**Every "WINS" in the report depends on one assumption: position 1 is the top of the Mod
Manager's active list and beats everything below it.** Two independent sources agree, but
I could not verify it against a running game, and if it is backwards then every conflict
verdict in the tool is exactly wrong.

The check takes a minute:

```
python mod_doctor.py --order my_order.txt
```

where `my_order.txt` is your Mod Manager list typed top-first. Then compare the printed
`LOAD ORDER` block against the Mod Manager on screen. If the report reads upside down,
pass `--reverse-order` — and tell me, because the default should change.

A stronger test if you have two mods that genuinely collide: let the tool name a winner,
then check in game which one's change actually took effect.

## 3. Profile parsing against a real profile.sii

The `active_mods[]` parser was written against a **synthetic plaintext profile** I wrote
myself. Real profiles are normally saved encrypted — the file starts with `ScsC` instead
of `SiiN`, and the tool stops with an explanation rather than parsing garbage.

```
1. Copy  Documents\American Truck Simulator\profiles\<hex>\profile.sii  somewhere scratch.
2. Decrypt the copy with SII_Decrypt or similar.
3. python mod_doctor.py --profile <decrypted copy>
```

What to check:

- Does it find the `active_mods[]` entries at all?
- **Do the entries match your installed mods?** My parser splits on `|` and tries each
  part against filenames and stems, assuming entries look like
  `mod|economy_chest.scs|Economy Chest`. Real entries may be shaped differently. If mods
  you have active show up under `active but not in the mod folder`, the matcher needs
  widening — paste a few real lines and it is a small fix.
- Workshop subscriptions *should* appear as unmatched active entries, since they are not
  files in the mod folder. That is expected, not a failure.

## 4. Confirm the interesting findings are real

If the report flags any of these, verify before believing:

- **A mod "doing nothing"** — every file overridden by something above it. Check the named
  overriding mod really does ship those paths. This is the tool's most valuable output and
  the one most worth a false-positive check.
- **A wrongly-packed mod** (`manifest.sii` inside a subfolder). Open the `.scs` as a zip
  and confirm. If real, that mod has never done anything for you.
- **A version-compatibility warning.** Compare against what the Mod Manager itself says
  about that mod.

## 5. Then use it on the Economy Chest problem

Once trusted, this is the first thing to run if Economy Chest looks like it is not working:

```
python mod_doctor.py --order my_order.txt --strict
```

If anything else ships `def/economy_data.sii`, one of them is losing and the report says
which. `--strict` exits non-zero when there are findings, which is handy before launching.

## Open questions only a real run answers

1. Is the load-order direction right? Everything else is downstream of this.
2. Does the `active_mods[]` matcher handle real profile entries?
3. Are there real-world package shapes the scanner mishandles — nested archives, mods with
   no `def/` at all, extremely large map mods where the conflict grouping gets unwieldy?
