#!/usr/bin/env python3
"""Generate a fake ATS mod folder covering everything mod_doctor.py looks for.

Usage: python3 tests/make_fixture_mods.py <output dir>
"""
import shutil
import sys
import zipfile
from pathlib import Path


def manifest(name, *, author="tester", version="1.0", category="other",
             icon=None, description="mod_description.txt", compatible=None):
    lines = ["SiiNunit", "{", "mod_package : .test_mod", "{",
             f'\tpackage_version:  "{version}"',
             f'\tdisplay_name:     "{name}"',
             f'\tauthor:           "{author}"',
             f'\tcategory[]: "{category}"']
    if description:
        lines.append(f'\tdescription_file: "{description}"')
    if icon:
        lines.append(f'\ticon: "{icon}"')
    for pattern in compatible or []:
        lines.append(f'\tcompatible_versions[]: "{pattern}"')
    lines += ["}", "}", ""]
    return "\n".join(lines)


def write_scs(path: Path, files: dict[str, str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1])
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # A well-formed mod. Shares def/economy_data.sii with realistic_economy.
    write_scs(out / "economy_chest.scs", {
        "manifest.sii": manifest("Economy Chest - Money x10 & XP x10", compatible=["1.5*"]),
        "mod_description.txt": "Money and XP multiplier.\n",
        "def/economy_data.sii": "SiiNunit\n{\neconomy_data : .e\n{\n\trevenue_coef_per_km: 3.0\n}\n}\n",
    })

    # Conflicts with economy_chest on the gameplay-critical file, plus two more.
    write_scs(out / "realistic_economy.scs", {
        "manifest.sii": manifest("Realistic Economy", author="someone", compatible=["1.5*"]),
        "mod_description.txt": "Harder economy.\n",
        "def/economy_data.sii": "SiiNunit\n{\neconomy_data : .e\n{\n\trevenue_coef_per_km: 0.2\n}\n}\n",
        "def/cargo.sii": "# cargo\n",
        "def/company.sii": "# company\n",
    })

    # Every file also shipped by realistic_economy -> shadowed when below it.
    write_scs(out / "tiny_cargo_tweak.scs", {
        "manifest.sii": manifest("Tiny Cargo Tweak", category="cargo_pack"),
        "mod_description.txt": "Small tweak.\n",
        "def/cargo.sii": "# other cargo\n",
    })

    # Contents buried in a subfolder: the game ignores this entirely.
    write_scs(out / "wrongly_packed.scs", {
        "My Cool Mod/manifest.sii": manifest("Wrongly Packed"),
        "My Cool Mod/def/traffic_data.sii": "# traffic\n",
    })

    # No manifest at all.
    write_scs(out / "no_manifest.scs", {
        "def/climate_data.sii": "# weather\n",
    })

    # Manifest referencing files that are not in the archive, a bogus category,
    # and a compatible_versions that excludes a 1.55 game.
    write_scs(out / "dangling_refs.scs", {
        "manifest.sii": manifest("Dangling Refs", category="not_a_category",
                                 icon="icon.png", description="missing.txt",
                                 compatible=["1.43.*"]),
        "ui/hud.sii": "# hud\n",
    })

    # Metadata only: nothing for the game to load.
    write_scs(out / "empty_mod.scs", {
        "manifest.sii": manifest("Empty Mod"),
        "mod_description.txt": "Nothing here.\n",
    })

    # Not a ZIP -- stands in for a HashFS-packed mod.
    (out / "hashfs_mod.scs").write_bytes(b"SCS#\x02\x00\x00\x00binarypayload")

    # An unpacked folder mod, which the game also accepts.
    folder = out / "unpacked_mod"
    (folder / "def").mkdir(parents=True)
    (folder / "manifest.sii").write_text(manifest("Unpacked Mod"))
    (folder / "mod_description.txt").write_text("Folder mod.\n")
    (folder / "def" / "traffic_rules.sii").write_text("# rules\n")

    # A plain-text profile.sii. Index 0 is the highest priority.
    active = [
        "mod|economy_chest.scs|Economy Chest",
        "mod|realistic_economy.scs|Realistic Economy",
        "mod|tiny_cargo_tweak.scs|Tiny Cargo Tweak",
        "mod|dangling_refs.scs|Dangling Refs",
        "mod_workshop_package.2048116145|Some Workshop Mod",
    ]
    profile = ["SiiNunit", "{", "user_profile : _nameless.profile", "{",
               f"\tactive_mods: {len(active)}"]
    profile += [f'\tactive_mods[{i}]: "{entry}"' for i, entry in enumerate(active)]
    profile += ["}", "}", ""]
    (out / "profile.sii").write_text("\n".join(profile))

    # The same order as a hand-written list.
    (out / "order.txt").write_text(
        "# highest priority first\n"
        "economy_chest.scs\n"
        "realistic_economy.scs\n"
        "tiny_cargo_tweak.scs\n"
        "dangling_refs.scs\n"
    )

    # An encrypted profile, to prove the error path is helpful.
    (out / "profile_encrypted.sii").write_bytes(b"ScsC\x01\x00\x00\x00" + b"\x00" * 64)

    print(f"fixture mod folder written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
