#!/usr/bin/env python3
"""Inspect an American Truck Simulator / Euro Truck Simulator 2 mod folder.

Reports three things:

  packaging problems   a mod the game will quietly ignore -- no manifest at the
                       archive root, contents buried in a subfolder, a manifest
                       pointing at an icon or description that isn't there,
                       compatible_versions that excludes your game build.

  file conflicts       two or more mods shipping the same path. Only one wins,
                       and which one is decided entirely by load order.

  shadowed mods        a mod whose every file is overridden by something above
                       it. It is enabled, it looks fine in the Mod Manager, and
                       it is doing nothing at all.

Load order comes from your profile.sii when you point --profile at one, or from
a plain text list via --order. Position 1 is the highest priority, matching the
top of the Mod Manager's active list.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Files every package carries at its root. Two mods both having a manifest is
# not a conflict, so these never count as one.
METADATA_FILES = {
    "manifest.sii",
    "mod_description.txt",
    "description.txt",
    "icon.jpg",
    "mod_icon.jpg",
}

VALID_CATEGORIES = {
    "truck", "trailer", "ui", "weather_setup", "graphics", "models", "walkers",
    "prefabs", "tuning_parts", "paint_job", "cargo_pack", "interior",
    "ai_traffic", "sound", "physics", "map", "other",
}

# Paths where a silent override changes how the game plays, not how it looks.
HIGH_IMPACT = re.compile(
    r"^def/(economy_data|climate_data|traffic_data|traffic_rules|game_data)\.sii$"
    r"|^def/(cargo|company|city|country)\.sii$"
    r"|^def/vehicle/truck/[^/]+\.sii$"
)

ATTR_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<idx>\[[0-9]*\])?"
    r"\s*:\s*(?P<val>[^#\r\n]*?)\s*(?:#.*)?$"
)

DEFAULT_DIRS = {
    "ats": {
        "win32": "~/Documents/American Truck Simulator/mod",
        "linux": "~/.local/share/American Truck Simulator/mod",
        "darwin": "~/Library/Application Support/American Truck Simulator/mod",
    },
    "ets2": {
        "win32": "~/Documents/Euro Truck Simulator 2/mod",
        "linux": "~/.local/share/Euro Truck Simulator 2/mod",
        "darwin": "~/Library/Application Support/Euro Truck Simulator 2/mod",
    },
}


class DoctorError(Exception):
    pass


@dataclass
class Issue:
    level: str       # "error" | "warning" | "info"
    mod: str
    message: str


@dataclass
class ModPackage:
    path: Path
    kind: str                                   # "zip" | "hashfs" | "folder"
    files: set[str] = field(default_factory=set)
    manifest: dict = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    readable: bool = True

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def display_name(self) -> str:
        return self.manifest.get("display_name") or "(no display_name)"

    @property
    def content_files(self) -> set[str]:
        return {f for f in self.files if f not in METADATA_FILES}


def parse_sii_attrs(text: str) -> dict:
    """Flat attribute dump of a small .sii file. `key[]` entries collect into a list."""
    out: dict = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped in ("{", "}"):
            continue
        match = ATTR_RE.match(line)
        if not match:
            continue
        key, value = match.group("key"), match.group("val").strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]
        if match.group("idx") is not None:
            out.setdefault(key, []).append(value)
        else:
            out[key] = value
    return out


def normalise(name: str) -> str:
    return name.replace("\\", "/").lstrip("./")


def read_package(path: Path) -> ModPackage:
    if path.is_dir():
        pkg = ModPackage(path=path, kind="folder")
        for item in path.rglob("*"):
            if item.is_file():
                pkg.files.add(item.relative_to(path).as_posix())
        manifest = path / "manifest.sii"
        if manifest.is_file():
            pkg.manifest = parse_sii_attrs(manifest.read_text(encoding="utf-8", errors="replace"))
        return pkg

    pkg = ModPackage(path=path, kind="zip")
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                pkg.files.add(normalise(info.filename))
            if "manifest.sii" in pkg.files:
                raw = zf.read("manifest.sii").decode("utf-8", errors="replace")
                pkg.manifest = parse_sii_attrs(raw)
    except zipfile.BadZipFile:
        pkg.kind = "hashfs"
        pkg.readable = False
    except (OSError, KeyError) as exc:
        pkg.readable = False
        pkg.issues.append(Issue("error", path.name, f"could not be read: {exc}"))
        return pkg

    return pkg


def check_package(pkg: ModPackage, game_version: str | None) -> None:
    """Packaging problems that make the game ignore or mis-handle a mod."""
    name = pkg.name

    if pkg.kind == "hashfs":
        pkg.issues.append(Issue(
            "info", name,
            "packed in SCS HashFS format, so its contents can't be listed here "
            "(conflicts involving it won't be detected)"))
        return

    if not pkg.files:
        pkg.issues.append(Issue("error", name, "archive is empty"))
        return

    if "manifest.sii" not in pkg.files:
        nested = [f for f in pkg.files if f.endswith("/manifest.sii")]
        if nested:
            folder = nested[0].rsplit("/", 1)[0]
            pkg.issues.append(Issue(
                "error", name,
                f"manifest.sii is inside '{folder}/' instead of the archive root -- "
                f"the game will not see this mod. Repack with the contents at the top level"))
        else:
            pkg.issues.append(Issue(
                "warning", name,
                "no manifest.sii -- the Mod Manager shows it without a name, author or "
                "version, and newer game builds may reject it"))
        return

    description = pkg.manifest.get("description_file")
    if description and normalise(description) not in pkg.files:
        pkg.issues.append(Issue(
            "warning", name, f"manifest points at description_file '{description}', which is not in the archive"))

    icon = pkg.manifest.get("icon")
    if icon:
        if normalise(icon) not in pkg.files:
            pkg.issues.append(Issue(
                "warning", name, f"manifest points at icon '{icon}', which is not in the archive"))
        elif not icon.lower().endswith((".jpg", ".jpeg")):
            pkg.issues.append(Issue(
                "warning", name, f"icon '{icon}' is not a .jpg (the Mod Manager wants a 276x162 jpg)"))

    for category in pkg.manifest.get("category", []):
        if category not in VALID_CATEGORIES:
            pkg.issues.append(Issue("warning", name, f"unknown category '{category}'"))

    if not pkg.manifest.get("display_name"):
        pkg.issues.append(Issue("warning", name, "manifest has no display_name"))

    compatible = pkg.manifest.get("compatible_versions", [])
    if game_version and compatible:
        if not any(version_matches(pattern, game_version) for pattern in compatible):
            pkg.issues.append(Issue(
                "warning", name,
                f"compatible_versions {compatible} does not cover game version {game_version} -- "
                f"the Mod Manager will flag it as incompatible"))

    if not pkg.content_files:
        pkg.issues.append(Issue(
            "warning", name, "contains metadata only -- no def/, ui/ or other content files"))


def version_matches(pattern: str, version: str) -> bool:
    """SCS compatible_versions patterns: '1.55', '1.55.*', '1.5*'."""
    regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    if re.match(regex, version):
        return True
    # '1.55' should also accept a '1.55.1.2s' style build string
    return version.startswith(pattern + ".")


def read_order_file(path: Path) -> list[str]:
    if not path.is_file():
        raise DoctorError(f"--order file not found: {path}")
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


def read_profile_order(path: Path) -> list[str]:
    if not path.is_file():
        raise DoctorError(f"--profile file not found: {path}")
    head = path.read_bytes()[:4]
    if head != b"SiiN":
        raise DoctorError(
            f"{path} is not a plain text profile.sii (starts with {head!r}).\n"
            "  Profiles are usually saved encrypted. Decrypt it first (SII_Decrypt or\n"
            "  similar), or list your Mod Manager order by hand and pass it with --order."
        )

    text = path.read_text(encoding="utf-8", errors="replace")
    indexed: list[tuple[int, str]] = []
    for match in re.finditer(r"^\s*active_mods\[(\d*)\]\s*:\s*\"?([^\"\r\n]*)\"?", text, re.M):
        index = int(match.group(1)) if match.group(1) else len(indexed)
        indexed.append((index, match.group(2).strip()))
    if not indexed:
        raise DoctorError(f"no active_mods[] entries found in {path}")
    return [value for _, value in sorted(indexed, key=lambda pair: pair[0])]


def match_order(order: list[str], packages: list[ModPackage]) -> tuple[list[str], list[str]]:
    """Map profile entries onto installed packages. Returns (ordered names, unmatched entries)."""
    by_name = {pkg.name: pkg for pkg in packages}
    by_stem = {pkg.path.stem: pkg for pkg in packages}
    ordered: list[str] = []
    unmatched: list[str] = []

    for entry in order:
        # Entries look like "mod|economy_chest.scs|Economy Chest" or a bare filename.
        hit = None
        for part in [entry] + [p.strip() for p in entry.split("|")]:
            if part in by_name:
                hit = by_name[part]
                break
            if part in by_stem:
                hit = by_stem[part]
                break
            candidate = part if part.endswith(".scs") else part + ".scs"
            if candidate in by_name:
                hit = by_name[candidate]
                break
        if hit and hit.name not in ordered:
            ordered.append(hit.name)
        elif not hit:
            unmatched.append(entry)
    return ordered, unmatched


def build_index(packages: list[ModPackage]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for pkg in packages:
        for path in pkg.content_files:
            index.setdefault(path, []).append(pkg.name)
    return index


def cluster_conflicts(index: dict[str, list[str]]) -> list[dict]:
    """Group conflicting paths by the exact set of mods that provide them."""
    clusters: dict[tuple[str, ...], list[str]] = {}
    for path, mods in index.items():
        if len(mods) > 1:
            clusters.setdefault(tuple(sorted(mods)), []).append(path)
    out = []
    for mods, paths in clusters.items():
        paths.sort()
        out.append({
            "mods": list(mods),
            "files": paths,
            "count": len(paths),
            "high_impact": [p for p in paths if HIGH_IMPACT.match(p)],
        })
    out.sort(key=lambda c: (-len(c["high_impact"]), -c["count"]))
    return out


def priority_sort(mods: list[str], order: list[str]) -> tuple[list[str], list[str]]:
    """Split mods into (ranked by load order, unknown position)."""
    ranked = [m for m in order if m in mods]
    unknown = sorted(set(mods) - set(ranked))
    return ranked, unknown


def find_shadowed(packages: list[ModPackage], order: list[str], index: dict[str, list[str]]) -> list[dict]:
    """Mods whose every content file is provided by something higher in the load order."""
    rank = {name: position for position, name in enumerate(order)}
    shadowed = []
    for pkg in packages:
        if pkg.name not in rank or not pkg.content_files:
            continue
        mine = rank[pkg.name]
        covering: set[str] = set()
        for path in pkg.content_files:
            winners = [m for m in index[path] if m in rank and rank[m] < mine]
            if not winners:
                covering.clear()
                break
            covering.add(winners[0])
        if covering:
            shadowed.append({"mod": pkg.name, "overridden_by": sorted(covering)})
    return shadowed


def default_mod_dir(game: str) -> Path:
    platform = "win32" if sys.platform.startswith("win") else (
        "darwin" if sys.platform == "darwin" else "linux")
    return Path(os.path.expanduser(DEFAULT_DIRS[game][platform]))


def scan(mods_dir: Path) -> list[ModPackage]:
    if not mods_dir.is_dir():
        raise DoctorError(
            f"mod folder not found: {mods_dir}\n"
            "  Pass --mods <path>, or --game ets2 if you meant Euro Truck Simulator 2."
        )
    candidates = sorted(
        [p for p in mods_dir.iterdir() if p.is_file() and p.suffix.lower() in (".scs", ".zip")]
        + [p for p in mods_dir.iterdir() if p.is_dir() and (p / "manifest.sii").is_file()],
        key=lambda p: p.name.lower(),
    )
    return [read_package(path) for path in candidates]


def render(packages, order, unmatched, clusters, shadowed, mods_dir, examples) -> tuple[str, int, int]:
    lines: list[str] = []
    errors = sum(1 for p in packages for i in p.issues if i.level == "error")
    warnings = sum(1 for p in packages for i in p.issues if i.level == "warning")

    lines.append(f"mod folder    {mods_dir}")
    lines.append(f"packages      {len(packages)}")
    lines.append("")

    lines.append("PACKAGES")
    width = max((len(p.name) for p in packages), default=4)
    for pkg in packages:
        tag = {"zip": "", "hashfs": "  [HashFS, contents not readable]", "folder": "  [unpacked folder]"}[pkg.kind]
        if pkg.readable:
            total = len(pkg.content_files)
            count = f"{total:>5} " + ("file " if total == 1 else "files")
            label = pkg.display_name
        else:
            count = "    ? files"
            label = ""
        lines.append(f"  {pkg.name:<{width}}  {count}  {label}{tag}".rstrip())
    lines.append("")

    if order:
        lines.append("LOAD ORDER  (1 = highest priority = top of the Mod Manager list)")
        for position, name in enumerate(order, 1):
            lines.append(f"  {position:>2}  {name}")
        inactive = [p.name for p in packages if p.name not in order]
        for name in inactive:
            lines.append(f"   -  {name}   (installed but not in the active list)")
        for entry in unmatched:
            lines.append(f"   ?  {entry}   (active but not in the mod folder -- Workshop subscription?)")
        lines.append("")
    else:
        lines.append("LOAD ORDER    unknown -- pass --profile or --order to see which mod wins each conflict")
        lines.append("")

    issues = [i for p in packages for i in p.issues]
    if issues:
        lines.append("PACKAGING")
        for issue in sorted(issues, key=lambda i: {"error": 0, "warning": 1, "info": 2}[i.level]):
            marker = {"error": "ERROR ", "warning": "warn  ", "info": "note  "}[issue.level]
            lines.append(f"  {marker}{issue.mod}: {issue.message}")
        lines.append("")

    if clusters:
        total = sum(c["count"] for c in clusters)
        lines.append(f"CONFLICTS  ({len(clusters)} group(s), {total} file(s) provided by more than one mod)")
        for cluster in clusters:
            ranked, unknown = priority_sort(cluster["mods"], order)
            lines.append("")
            total = cluster["count"]
            lines.append(f"  {total} shared file{'' if total == 1 else 's'}:")
            for position, name in enumerate(ranked):
                verdict = "WINS " if position == 0 else "loses"
                lines.append(f"    {verdict}  {name}")
            for name in unknown:
                lines.append(f"    ?      {name}   (position unknown)")
            if not ranked:
                lines.append("           load order unknown -- cannot say which one the game uses")
            if cluster["high_impact"]:
                lines.append("    gameplay-affecting:")
                for path in cluster["high_impact"][:examples]:
                    lines.append(f"      {path}")
            shown = [p for p in cluster["files"] if p not in cluster["high_impact"]][:examples]
            for path in shown:
                lines.append(f"      {path}")
            remaining = cluster["count"] - len(shown) - len(cluster["high_impact"][:examples])
            if remaining > 0:
                lines.append(f"      ... and {remaining} more")
        lines.append("")

    if shadowed:
        lines.append("DOING NOTHING  (every file this mod provides is overridden by something above it)")
        for entry in shadowed:
            lines.append(f"  {entry['mod']}")
            lines.append(f"    fully overridden by: {', '.join(entry['overridden_by'])}")
            lines.append("    move it higher in the Mod Manager, or remove it")
        lines.append("")

    verdict = []
    verdict.append(f"{errors} error(s)")
    verdict.append(f"{warnings} warning(s)")
    verdict.append(f"{len(clusters)} conflict group(s)")
    verdict.append(f"{len(shadowed)} mod(s) doing nothing")
    lines.append("SUMMARY       " + ", ".join(verdict))
    if not order and clusters:
        lines.append("              rerun with --profile or --order to resolve the conflicts above")
    if not errors and not clusters and not shadowed:
        lines.append("              nothing to fix")

    return "\n".join(lines), errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check an ATS/ETS2 mod folder for packaging problems, file conflicts and dead mods.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 tools/mod_doctor.py\n"
            "  python3 tools/mod_doctor.py --mods ~/ats/mod --profile ~/ats/profiles/xxx/profile.sii\n"
            "  python3 tools/mod_doctor.py --order my_order.txt --game-version 1.55 --strict\n"
        ),
    )
    parser.add_argument("--mods", type=Path, help="mod folder (default: this platform's ATS mod folder)")
    parser.add_argument("--game", choices=("ats", "ets2"), default="ats", help="which game's default mod folder to use")
    parser.add_argument("--profile", type=Path, help="a decrypted profile.sii to read the active mod order from")
    parser.add_argument("--order", type=Path, help="text file listing mods top-to-bottom, highest priority first")
    parser.add_argument("--reverse-order", action="store_true",
                        help="treat the supplied order as lowest-priority-first")
    parser.add_argument("--game-version", help="your game build, e.g. 1.55, to check compatible_versions against")
    parser.add_argument("--examples", type=int, default=5, help="conflicting paths to list per group (default: 5)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of a report")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any error or conflict was found")
    args = parser.parse_args(argv)

    if args.profile and args.order:
        parser.error("--profile and --order are mutually exclusive")

    mods_dir = args.mods or default_mod_dir(args.game)
    packages = scan(mods_dir)
    if not packages:
        print(f"no mods found in {mods_dir}")
        return 0

    for pkg in packages:
        check_package(pkg, args.game_version)

    raw_order: list[str] = []
    unmatched: list[str] = []
    if args.profile:
        raw_order = read_profile_order(args.profile)
    elif args.order:
        raw_order = read_order_file(args.order)
    if raw_order and args.reverse_order:
        raw_order = list(reversed(raw_order))
    order, unmatched = match_order(raw_order, packages) if raw_order else ([], [])

    index = build_index(packages)
    clusters = cluster_conflicts(index)
    shadowed = find_shadowed(packages, order, index) if order else []

    if args.json:
        print(json.dumps({
            "mod_folder": str(mods_dir),
            "packages": [{
                "file": p.name,
                "kind": p.kind,
                "display_name": p.manifest.get("display_name"),
                "author": p.manifest.get("author"),
                "version": p.manifest.get("package_version"),
                "categories": p.manifest.get("category", []),
                "compatible_versions": p.manifest.get("compatible_versions", []),
                "file_count": len(p.content_files),
                "issues": [{"level": i.level, "message": i.message} for i in p.issues],
            } for p in packages],
            "load_order": order,
            "unmatched_active_entries": unmatched,
            "conflicts": clusters,
            "shadowed": shadowed,
        }, indent=2))
        errors = sum(1 for p in packages for i in p.issues if i.level == "error")
    else:
        report, errors, _ = render(
            packages, order, unmatched, clusters, shadowed, mods_dir, args.examples)
        print(report)

    if args.strict and (errors or clusters):
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DoctorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
