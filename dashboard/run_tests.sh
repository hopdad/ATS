#!/usr/bin/env bash
# Bridge test suite. Run from anywhere: bash dashboard/run_tests.sh
set -euo pipefail
cd "$(dirname "$0")"
python3 -m unittest discover -s tests -t . "$@"
