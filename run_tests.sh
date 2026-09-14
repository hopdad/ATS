#!/usr/bin/env bash
# Every project's tests. Run from anywhere: bash run_tests.sh
set -uo pipefail
cd "$(dirname "$0")"
FAILED=0

run() {
  echo
  echo "=== $1 ==="
  shift
  if "$@"; then :; else FAILED=1; fi
}

run "economy-chest" bash economy-chest/tests/smoke_test.sh
run "mod-doctor"    bash mod-doctor/tests/doctor_smoke_test.sh
run "cab-deck"      bash cab-deck/run_tests.sh

echo
if [ "$FAILED" -eq 0 ]; then echo "all suites passed"; else echo "SUITE FAILURES"; fi
exit "$FAILED"
