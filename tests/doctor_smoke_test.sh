#!/usr/bin/env bash
# Smoke test for tools/mod_doctor.py. Run from the repo root: bash tests/doctor_smoke_test.sh
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
TMP="$REPO/tests/.tmp-doctor"
rm -rf "$TMP"; mkdir -p "$TMP"
MODS="$TMP/mod"
python3 tests/make_fixture_mods.py "$MODS" >/dev/null
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); echo "  PASS  $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL  $1"; }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (expected '$3', got '$2')"; fi; }
has()  { if grep -qF "$2" "$TMP/out.txt"; then ok "$1"; else bad "$1 (missing: $2)"; fi; }
hasnt(){ if grep -qF "$2" "$TMP/out.txt"; then bad "$1 (unexpected: $2)"; else ok "$1"; fi; }

run() { python3 tools/mod_doctor.py "$@" >"$TMP/out.txt" 2>"$TMP/err.txt"; echo $?; }

echo "scan with profile order"
RC=$(run --mods "$MODS" --profile "$MODS/profile.sii" --game-version 1.55)
check "exits 0" "$RC" "0"
check "found every package" "$(grep -c '^packages      9$' "$TMP/out.txt")" "1"
has "folder mod manifest is read"     "Unpacked Mod  [unpacked folder]"
has "hashfs mod flagged"              "[HashFS, contents not readable]"
has "nested manifest is an error"     "ERROR wrongly_packed.scs"
has "nested manifest names the folder" "'My Cool Mod/'"
has "missing manifest is a warning"   "warn  no_manifest.scs"
hasnt "missing manifest is not fatal" "ERROR no_manifest.scs"
has "dangling description"            "description_file 'missing.txt'"
has "dangling icon"                   "icon 'icon.png'"
has "bad category"                    "unknown category 'not_a_category'"
has "version mismatch"                "does not cover game version 1.55"
hasnt "compatible mod not flagged"    "economy_chest.scs: compatible_versions"
has "metadata-only mod"               "contains metadata only"
has "workshop entry noted"            "Workshop subscription?"
has "inactive mods listed"            "installed but not in the active list"

echo "conflicts and winners"
has "conflict section"        "CONFLICTS  (2 group(s), 2 file(s)"
has "economy_data conflict"   "def/economy_data.sii"
has "gameplay impact called out" "gameplay-affecting:"
check "economy_chest wins"    "$(grep -c 'WINS   economy_chest.scs' "$TMP/out.txt")" "1"
check "realistic_economy loses once, wins once" \
      "$(grep -c 'loses  realistic_economy.scs' "$TMP/out.txt")" "1"
has "shadowed mod found"      "tiny_cargo_tweak.scs"
has "shadowed section"        "DOING NOTHING"
has "shadow attribution"      "fully overridden by: realistic_economy.scs"
hasnt "metadata never counts as a conflict" "manifest.sii shared"

echo "order file matches profile"
RC=$(run --mods "$MODS" --order "$MODS/order.txt" --game-version 1.55)
check "exits 0" "$RC" "0"
has "same winner from --order" "WINS   economy_chest.scs"

echo "reversed order flips the winner"
RC=$(run --mods "$MODS" --order "$MODS/order.txt" --reverse-order)
check "exits 0" "$RC" "0"
has "economy_data winner flips" "WINS   realistic_economy.scs"
has "cargo winner flips"        "WINS   tiny_cargo_tweak.scs"
check "economy_chest now loses" "$(grep -c 'loses  economy_chest.scs' "$TMP/out.txt")" "1"
check "shadowed mod flips too" \
      "$(sed -n '/DOING NOTHING/,$p' "$TMP/out.txt" | sed -n '2p' | tr -d ' ')" "economy_chest.scs"

echo "without a load order"
RC=$(run --mods "$MODS")
check "exits 0" "$RC" "0"
has "says order is unknown"      "LOAD ORDER    unknown"
has "conflicts still reported"   "def/economy_data.sii"
has "declines to pick a winner"  "cannot say which one the game uses"
has "suggests the fix"           "rerun with --profile or --order"
check "nothing marked shadowed without an order" "$(grep -c 'DOING NOTHING' "$TMP/out.txt")" "0"

echo "json output"
RC=$(run --mods "$MODS" --profile "$MODS/profile.sii" --json)
check "exits 0" "$RC" "0"
python3 - "$TMP/out.txt" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert len(d["packages"]) == 9, d["packages"]
assert d["load_order"][0] == "economy_chest.scs", d["load_order"]
assert len(d["conflicts"]) == 2, d["conflicts"]
assert d["shadowed"][0]["mod"] == "tiny_cargo_tweak.scs", d["shadowed"]
assert any(c["high_impact"] for c in d["conflicts"])
assert d["unmatched_active_entries"], d["unmatched_active_entries"]
names = {p["file"]: p for p in d["packages"]}
assert names["economy_chest.scs"]["version"] == "1.0"
assert names["realistic_economy.scs"]["author"] == "someone"
assert names["unpacked_mod"]["kind"] == "folder"
assert names["hashfs_mod.scs"]["kind"] == "hashfs"
print("json ok")
PY
check "json shape" "$?" "0"

echo "version matching"
python3 - <<'PY'
import sys; sys.path.insert(0, "tools")
from mod_doctor import version_matches as m
assert m("1.5*", "1.55")
assert m("1.55.*", "1.55.1")
assert m("1.55", "1.55")
assert m("1.55", "1.55.1.2s")
assert not m("1.43.*", "1.55")
assert not m("1.4*", "1.55")
print("version ok")
PY
check "version patterns" "$?" "0"

echo "failure modes"
RC=$(run --mods "$MODS" --profile "$MODS/profile.sii" --strict)
check "--strict fails on conflicts" "$RC" "1"
RC=$(run --mods "$MODS" --profile "$MODS/profile_encrypted.sii")
check "encrypted profile exits 2" "$RC" "2"
check "encrypted profile explains" "$(grep -c 'Decrypt it first' "$TMP/err.txt")" "1"
RC=$(run --mods "$TMP/does_not_exist")
check "missing mod folder exits 2" "$RC" "2"
check "missing folder suggests --game" "$(grep -c 'game ets2' "$TMP/err.txt")" "1"
RC=$(run --mods "$MODS" --profile "$MODS/profile.sii" --order "$MODS/order.txt")
check "profile+order rejected" "$RC" "2"
mkdir -p "$TMP/empty"
RC=$(run --mods "$TMP/empty")
check "empty folder exits 0" "$RC" "0"
has "empty folder message" "no mods found"

echo
echo "passed $PASS, failed $FAIL"
rm -rf "$TMP"
[ "$FAIL" -eq 0 ]
