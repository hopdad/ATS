#!/usr/bin/env python3
"""Build the Economy Chest .scs mod for American Truck Simulator.

Two ways to produce def/economy_data.sii:

  patch mode (recommended, --base)
      Reads the economy_data.sii that your copy of the game actually ships,
      multiplies the money and XP attributes, and writes everything else out
      byte-for-byte. The result matches your game version and leaves every
      unrelated economy setting exactly as SCS tuned it.

  standalone mode (--standalone)
      Emits a small economy_data.sii built from community-reported stock values.
      Convenient, but it is a *whole file replacement*: any attribute the real
      file has and this one does not falls back to the engine default. See
      README.md before shipping a save you care about through it.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
RULES_PATH = PROJECT / "scale_rules.json"

# key, optional [] or [n] index, value, optional trailing # comment
ATTR_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<idx>\[[0-9]*\])?"
    r"\s*:\s*"
    r"(?P<val>[^#\r\n]*?)"
    r"\s*(?P<comment>#.*)?$"
)


class BuildError(Exception):
    pass


def load_rules() -> dict:
    with RULES_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def format_value(new: float, original: str) -> str:
    """Render `new` the way `original` was written (int stays int-ish, float keeps a point)."""
    text = f"{new:.6f}".rstrip("0").rstrip(".")
    if text in ("", "-"):
        text = "0"
    looked_float = "." in original or "e" in original.lower()
    if looked_float and "." not in text:
        text += ".0"
    return text


def scale_sii(
    source: str,
    money_mult: float,
    xp_mult: float,
    rules: dict,
    scale_all_exp: bool,
) -> tuple[str, list[str], list[str]]:
    """Return (patched text, list of 'key: old -> new' changes, list of warnings)."""
    money_fields = set(rules["money_fields"])
    xp_fields = set(rules["xp_fields"])
    never = set(rules["exp_fields_never_scale"])
    exp_pattern = re.compile(rules["exp_field_pattern"])

    changes: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    skipped_exp: set[str] = set()
    out: list[str] = []

    for line in source.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        newline = line[len(stripped):]
        match = ATTR_RE.match(stripped)
        if not match:
            out.append(line)
            continue

        key = match.group("key")
        raw = match.group("val")

        if key in money_fields:
            mult, kind = money_mult, "money"
        elif key in xp_fields and key not in never:
            mult, kind = xp_mult, "xp"
        elif exp_pattern.match(key) and key not in never:
            if not scale_all_exp:
                skipped_exp.add(key)
                out.append(line)
                continue
            mult, kind = xp_mult, "xp"
        else:
            out.append(line)
            continue

        try:
            value = float(raw)
        except ValueError:
            warnings.append(f"{key}: value {raw!r} is not a number, left unchanged")
            out.append(line)
            continue

        seen.add(key)
        if mult == 1.0:
            out.append(line)
            continue

        rendered = format_value(value * mult, raw)
        note = f"  # economy-chest: was {raw} (x{mult:g})"
        rebuilt = (
            f"{match.group('indent')}{key}{match.group('idx') or ''}: {rendered}"
            f"{(' ' + match.group('comment')) if match.group('comment') else ''}{note}"
        )
        out.append(rebuilt + newline)
        changes.append(f"{kind:5s} {key}: {raw} -> {rendered}")

    for key in sorted(money_fields - seen):
        warnings.append(f"expected money attribute {key!r} not found in the base file")
    for key in sorted(xp_fields - seen):
        warnings.append(f"expected XP attribute {key!r} not found in the base file")
    for key in sorted(skipped_exp):
        warnings.append(
            f"exp_* attribute {key!r} left at stock (not in xp_fields); "
            f"use --scale-all-exp to include it"
        )
    return "".join(out), changes, warnings


def read_from_archive(archive: Path) -> str:
    try:
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if name.replace("\\", "/").lower().endswith("def/economy_data.sii"):
                    return zf.read(name).decode("utf-8", errors="replace")
    except zipfile.BadZipFile:
        raise BuildError(
            f"{archive} is not a ZIP archive.\n"
            "  The base game def.scs uses SCS's HashFS format, which this script cannot read.\n"
            "  Unpack it first (SCS Extractor, or any ATS archive extractor), then point\n"
            "  --base at the extracted economy_data.sii or at the folder containing it."
        ) from None
    raise BuildError(f"no def/economy_data.sii inside {archive}")


def resolve_base(base: Path) -> tuple[str, str]:
    """Return (file text, human-readable source description)."""
    if not base.exists():
        raise BuildError(f"--base path does not exist: {base}")

    if base.is_file():
        if base.suffix.lower() in (".scs", ".zip"):
            return read_from_archive(base), str(base)
        return base.read_text(encoding="utf-8", errors="replace"), str(base)

    direct = base / "def" / "economy_data.sii"
    if direct.is_file():
        return direct.read_text(encoding="utf-8", errors="replace"), str(direct)
    for found in sorted(base.rglob("economy_data.sii")):
        return found.read_text(encoding="utf-8", errors="replace"), str(found)
    archive = base / "def.scs"
    if archive.is_file():
        return read_from_archive(archive), str(archive)
    raise BuildError(
        f"could not find economy_data.sii under {base}\n"
        "  Expected <base>/def/economy_data.sii, any economy_data.sii below it, or <base>/def.scs"
    )


def build_standalone(money_mult: float, xp_mult: float, rules: dict) -> tuple[str, list[str]]:
    defaults = rules["reference_defaults"]
    money_fields = rules["money_fields"]
    xp_fields = [k for k in rules["xp_fields"] if k in defaults]

    changes: list[str] = []
    lines = [
        "SiiNunit",
        "{",
        "economy_data : .economy_data",
        "{",
        f"\t# Economy Chest - money x{money_mult:g}, XP x{xp_mult:g}",
        "\t# Standalone build: values below are community-reported stock values scaled by",
        "\t# the multipliers. Attributes absent here fall back to engine defaults. Rebuild",
        "\t# with --base <your extracted economy_data.sii> for a version-exact mod.",
        "",
        "\t# --- money -------------------------------------------------------------",
    ]
    for key in money_fields:
        if key not in defaults:
            continue
        stock = defaults[key]
        rendered = format_value(stock * money_mult, str(stock))
        lines.append(f"\t{key}: {rendered}\t# stock {stock}")
        changes.append(f"money {key}: {stock} -> {rendered}")
    lines += ["", "\t# --- experience --------------------------------------------------------"]
    for key in xp_fields:
        stock = defaults[key]
        rendered = format_value(stock * xp_mult, str(stock))
        lines.append(f"\t{key}: {rendered}\t# stock {stock}")
        changes.append(f"xp    {key}: {stock} -> {rendered}")
    lines += ["}", "}", ""]
    return "\n".join(lines), changes


def render_template(path: Path, values: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{([A-Z_]+)\}\}", text)
    if leftover:
        raise BuildError(f"unfilled placeholders in {path.name}: {sorted(set(leftover))}")
    return text


def image_size(path: Path) -> tuple[int, int] | None:
    """Width and height of a PNG or JPEG, without a third-party imaging library."""
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                return (int.from_bytes(data[i + 7:i + 9], "big"),
                        int.from_bytes(data[i + 5:i + 7], "big"))
            i += 2 + length
    return None


# The SCS Workshop Uploader wants a folder holding versions.sii and one archive per
# game-version package, and nothing else. The preview image is chosen separately in the
# uploader, so it must stay outside that folder or the upload is rejected.
PREVIEW_SIZE = (640, 360)
PREVIEW_MAX_BYTES = 1024 * 1024


def check_preview(path: Path) -> list[str]:
    problems = []
    if not path.is_file():
        return [f"preview not found: {path}"]
    if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        problems.append(f"preview {path.name} should be a .jpg or .png")
    size = image_size(path)
    if size is None:
        problems.append(f"could not read the dimensions of {path.name}")
    elif size != PREVIEW_SIZE:
        problems.append(f"preview is {size[0]}x{size[1]}, Steam wants "
                        f"{PREVIEW_SIZE[0]}x{PREVIEW_SIZE[1]}")
    if path.stat().st_size > PREVIEW_MAX_BYTES:
        problems.append(f"preview is {path.stat().st_size / 1024:.0f} KB, the limit is 1 MB")
    return problems


def write_workshop(stage: Path, out_dir: Path, package: str,
                   compatible: list[str] | None = None) -> Path:
    """Build the folder the SCS Workshop Uploader consumes.

    versions.sii maps a game version to the archive that serves it, and exactly one entry
    must carry no compatible_versions[] -- that entry is the fallback for every version
    not explicitly listed. A single-package upload is therefore always unversioned here,
    whatever the manifest says: pinning the only package to "1.5*" would serve nothing at
    all to a player on any other build.

    The manifest's own compatible_versions[] is a different thing and stays as it is; it
    drives the Mod Manager's compatibility warning, not which archive Steam hands over.
    """
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    pack(stage, out_dir / f"{package}.zip")

    lines = ["SiiNunit", "{", f"package_version_info : .{package}", "{",
             f'\tpackage_name: "{package}"']
    for pattern in (compatible or []):
        lines.append(f'\tcompatible_versions[]: "{pattern}"')
    lines += ["}", "}", ""]
    (out_dir / "versions.sii").write_text("\n".join(lines), encoding="utf-8")
    return out_dir


def pack(stage: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    files = sorted(p for p in stage.rglob("*") if p.is_file())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(stage).as_posix())

    with zipfile.ZipFile(out) as zf:
        if zf.testzip() is not None:
            raise BuildError(f"{out} failed its own CRC check")
        names = set(zf.namelist())
    for required in ("manifest.sii", "def/economy_data.sii"):
        if required not in names:
            raise BuildError(f"{required} missing from {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Economy Chest money/XP mod for American Truck Simulator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 build_mod.py --base ~/ats_def_extracted\n"
            "  python3 build_mod.py --standalone --money 10 --xp 10\n"
            "  python3 build_mod.py --base ./economy_data.sii --money 5 --xp 20\n"
        ),
    )
    parser.add_argument("--base", type=Path,
                        help="extracted economy_data.sii, a folder containing one, or a ZIP-format .scs")
    parser.add_argument("--standalone", action="store_true",
                        help="build without a base file, from the reference stock values")
    parser.add_argument("--money", type=float, default=10.0,
                        help="money multiplier (default: 10 = 1000%%)")
    parser.add_argument("--xp", type=float, default=10.0,
                        help="XP multiplier (default: 10 = 1000%%)")
    parser.add_argument("--scale-all-exp", action="store_true",
                        help="also scale exp_* attributes not listed in scale_rules.json")
    parser.add_argument("--out", type=Path, help="output .scs path")
    parser.add_argument("--name", help="display name shown in the Mod Manager")
    parser.add_argument("--author", default="hopdad", help="author shown in the Mod Manager")
    parser.add_argument("--mod-version", default="1.0", help="package version string")
    parser.add_argument("--game-versions", default="1.5*",
                        help="comma-separated compatible_versions[] entries, or '' to omit")
    parser.add_argument("--icon", type=Path, help="276x162 .jpg to show in the Mod Manager")
    parser.add_argument("--workshop", action="store_true",
                        help="also build the folder the SCS Workshop Uploader consumes")
    parser.add_argument("--workshop-package", default="economy_chest",
                        help="package name inside versions.sii (default: economy_chest)")
    parser.add_argument("--preview", type=Path,
                        help="640x360 Steam preview image to validate (chosen separately in the uploader)")
    args = parser.parse_args(argv)

    if not args.base and not args.standalone:
        parser.error("pass --base <extracted economy_data.sii>, or --standalone to build without one")
    if args.base and args.standalone:
        parser.error("--base and --standalone are mutually exclusive")
    if args.money <= 0 or args.xp <= 0:
        parser.error("--money and --xp must be greater than 0")

    rules = load_rules()

    if args.standalone:
        economy, changes = build_standalone(args.money, args.xp, rules)
        warnings = [
            "standalone build: this economy_data.sii replaces the game's own file wholesale,",
            "so economy attributes it does not list revert to engine defaults. Rebuild with",
            "--base once you have extracted economy_data.sii from your game's def.scs.",
        ]
        source_note = "reference stock values (standalone build)"
    else:
        base_text, source_note = resolve_base(args.base)
        economy, changes, warnings = scale_sii(
            base_text, args.money, args.xp, rules, args.scale_all_exp
        )
        if not changes:
            raise BuildError(
                f"nothing was scaled in {source_note}.\n"
                "  That file does not look like economy_data.sii, or both multipliers are 1."
            )

    name = args.name or f"Economy Chest - Money x{args.money:g} & XP x{args.xp:g}"
    stem = f"economy_chest_money_x{args.money:g}_xp_x{args.xp:g}".replace(".", "_")
    out = args.out or PROJECT / "build" / f"{stem}.scs"
    stage = PROJECT / "build" / stem

    if stage.exists():
        shutil.rmtree(stage)
    (stage / "def").mkdir(parents=True)
    (stage / "def" / "economy_data.sii").write_text(economy, encoding="utf-8")

    icon_line = ""
    if args.icon:
        if not args.icon.is_file():
            raise BuildError(f"--icon file not found: {args.icon}")
        shutil.copyfile(args.icon, stage / "icon.jpg")
        icon_line = '\ticon: "icon.jpg"\n'

    compat = [v.strip() for v in args.game_versions.split(",") if v.strip()]
    compat_lines = "".join(f'\tcompatible_versions[]: "{v}"\n' for v in compat)

    (stage / "manifest.sii").write_text(
        render_template(PROJECT / "pkg" / "manifest.sii.tmpl", {
            "VERSION": args.mod_version,
            "DISPLAY_NAME": name,
            "AUTHOR": args.author,
            "ICON_LINE": icon_line,
            "COMPAT_LINES": compat_lines,
        }),
        encoding="utf-8",
    )
    (stage / "mod_description.txt").write_text(
        render_template(PROJECT / "pkg" / "mod_description.txt.tmpl", {
            "MONEY": f"{args.money:g}",
            "XP": f"{args.xp:g}",
            "MONEY_PCT": f"{args.money * 100:g}%",
            "XP_PCT": f"{args.xp * 100:g}%",
            "SOURCE_NOTE": source_note,
        }),
        encoding="utf-8",
    )

    pack(stage, out)

    workshop_dir = None
    preview_problems: list[str] = []
    if args.workshop:
        workshop_dir = write_workshop(stage, out.parent / "workshop", args.workshop_package)
    if args.preview:
        preview_problems = check_preview(args.preview)
        if not preview_problems and workshop_dir:
            # Deliberately beside the upload folder, never inside it.
            shutil.copyfile(args.preview, out.parent / ("preview" + args.preview.suffix.lower()))

    print(f"source        {source_note}")
    print(f"multipliers   money x{args.money:g}   XP x{args.xp:g}")
    print(f"scaled        {len(changes)} attribute(s)")
    for change in changes:
        print(f"  {change}")
    if warnings:
        print("\nwarnings")
        for warning in warnings:
            print(f"  ! {warning}")
    if preview_problems:
        print("\npreview")
        for problem in preview_problems:
            print(f"  ! {problem}")

    print(f"\nstaged        {stage}")
    print(f"built         {out}")
    print("\nCopy it into your ATS mod folder, then enable it in the Mod Manager:")
    print("  Documents/American Truck Simulator/mod/")

    if workshop_dir:
        print(f"\nworkshop      {workshop_dir}")
        print(f"  {args.workshop_package}.zip + versions.sii, and nothing else -- that is the rule.")
        print("  versions.sii lists no compatible_versions, so this package serves every build.")
        print("  Point the SCS Workshop Uploader's content folder at it.")
        print("  The 640x360 preview is chosen separately in the uploader, so it stays outside.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
