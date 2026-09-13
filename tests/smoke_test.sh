#!/usr/bin/env bash
# Smoke test for tools/build_mod.py. Run from the repo root: bash tests/smoke_test.sh
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
BUILD="$REPO/tests/.tmp"
rm -rf "$BUILD"; mkdir -p "$BUILD"
FIX="$REPO/tests/fixtures/economy_data.sample.sii"
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); echo "  PASS  $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL  $1"; }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (expected '$3', got '$2')"; fi; }

build() { python3 tools/build_mod.py "$@" >"$BUILD/out.txt" 2>"$BUILD/err.txt"; }

echo "patch mode, 10x/10x"
build --base "$FIX" --money 10 --xp 10 --out "$BUILD/a.scs"
check "exits 0" "$?" "0"
unzip -o -q "$BUILD/a.scs" -d "$BUILD/a"
check "money coef scaled"      "$(grep -c 'revenue_coef_per_km: 3.0' "$BUILD/a/def/economy_data.sii")" "1"
check "xp delivery scaled"     "$(grep -c 'exp_cargo_delivery: 12.5' "$BUILD/a/def/economy_data.sii")" "1"
check "base per-km untouched"  "$(grep -c '^	revenue_per_km_base: 15$' "$BUILD/a/def/economy_data.sii")" "1"
check "loans untouched"        "$(grep -c '^	bank_loan_count: 3$' "$BUILD/a/def/economy_data.sii")" "1"
check "fines untouched"        "$(grep -c '^	fine_speeding: 250$' "$BUILD/a/def/economy_data.sii")" "1"
check "garage array untouched" "$(grep -c 'garage_price\[\]: 200000' "$BUILD/a/def/economy_data.sii")" "1"
check "string attr untouched"  "$(grep -c 'name: \"economy\"' "$BUILD/a/def/economy_data.sii")" "1"
check "threshold untouched"    "$(grep -c '^	exp_resolution: 100$' "$BUILD/a/def/economy_data.sii")" "1"
check "unknown exp untouched"  "$(grep -c '^	exp_some_future_field: 2.5$' "$BUILD/a/def/economy_data.sii")" "1"
check "line count preserved"   "$(wc -l < "$BUILD/a/def/economy_data.sii")" "$(wc -l < "$FIX")"
check "manifest in archive"    "$(unzip -l "$BUILD/a.scs" | grep -c 'manifest.sii')" "1"
check "display name"           "$(grep -c 'Money x10 & XP x10' "$BUILD/a/manifest.sii")" "1"
check "no icon line"           "$(grep -c 'icon:' "$BUILD/a/manifest.sii")" "0"

echo "independent multipliers, 5x money / 1x xp"
build --base "$FIX" --money 5 --xp 1 --out "$BUILD/b.scs"
check "exits 0" "$?" "0"
unzip -o -q "$BUILD/b.scs" -d "$BUILD/b"
check "money scaled 5x"  "$(grep -c 'revenue_coef_per_km: 1.5' "$BUILD/b/def/economy_data.sii")" "1"
check "xp left alone"    "$(grep -c '^	exp_cargo_delivery: 1.25$' "$BUILD/b/def/economy_data.sii")" "1"

echo "--scale-all-exp"
build --base "$FIX" --money 10 --xp 10 --scale-all-exp --out "$BUILD/c.scs"
unzip -o -q "$BUILD/c.scs" -d "$BUILD/c"
check "unknown exp scaled"  "$(grep -c 'exp_some_future_field: 25.0' "$BUILD/c/def/economy_data.sii")" "1"
check "threshold still safe" "$(grep -c '^	exp_resolution: 100$' "$BUILD/c/def/economy_data.sii")" "1"

echo "standalone mode"
build --standalone --money 10 --xp 10 --out "$BUILD/d.scs"
check "exits 0" "$?" "0"
unzip -o -q "$BUILD/d.scs" -d "$BUILD/d"
check "standalone money" "$(grep -c 'revenue_coef_per_km: 3.0' "$BUILD/d/def/economy_data.sii")" "1"
check "warns about replacement" "$(grep -c 'wholesale' "$BUILD/out.txt")" "1"

echo "zip-format .scs as base"
( cd "$BUILD/a" && zip -q -r "$BUILD/base.scs" def manifest.sii )
build --base "$BUILD/base.scs" --money 1 --xp 2 --out "$BUILD/e.scs"
check "reads sii out of a zip archive" "$?" "0"

echo "custom metadata"
build --base "$FIX" --name "Chest" --author "me" --mod-version "2.3" --game-versions "1.54,1.55" --out "$BUILD/f.scs"
unzip -o -q "$BUILD/f.scs" -d "$BUILD/f"
check "custom name"    "$(grep -c 'display_name:     \"Chest\"' "$BUILD/f/manifest.sii")" "1"
check "custom author"  "$(grep -c 'author:           \"me\"' "$BUILD/f/manifest.sii")" "1"
check "custom version" "$(grep -c 'package_version:  \"2.3\"' "$BUILD/f/manifest.sii")" "1"
check "two compat lines" "$(grep -c 'compatible_versions' "$BUILD/f/manifest.sii")" "2"
build --base "$FIX" --game-versions "" --out "$BUILD/g.scs"
unzip -o -q "$BUILD/g.scs" -d "$BUILD/g"
check "compat omitted" "$(grep -c 'compatible_versions' "$BUILD/g/manifest.sii")" "0"

echo "failure modes"
build --money 10; check "no --base and no --standalone fails" "$?" "2"
build --base "$FIX" --standalone; check "--base with --standalone fails" "$?" "2"
build --base "$FIX" --money 0; check "zero multiplier fails" "$?" "2"
build --base "$BUILD/nope.sii"; check "missing base fails" "$?" "1"
echo "not a sii" > "$BUILD/junk.sii"
build --base "$BUILD/junk.sii"
check "unrecognised base fails" "$?" "1"
check "explains why" "$(grep -c 'nothing was scaled' "$BUILD/err.txt")" "1"
printf 'not a zip' > "$BUILD/fake.scs"
build --base "$BUILD/fake.scs"
check "HashFS .scs fails with guidance" "$(grep -c 'HashFS' "$BUILD/err.txt")" "1"
build --base "$BUILD/empty_dir_xyz"; check "missing dir fails" "$?" "1"

echo
echo "passed $PASS, failed $FAIL"
rm -rf "$BUILD"
[ "$FAIL" -eq 0 ]
