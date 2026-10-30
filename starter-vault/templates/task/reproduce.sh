#!/usr/bin/env bash
# reproduce.sh — re-verify this task's claims with one command.
# Keep it read-only where possible; print PASS/FAIL per check.
set -uo pipefail
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== 1. artifacts exist =="
ls "$D/output/report.md" "$D/output/negative-results.md"

echo "== 2. claims re-run =="
# <the exact command(s) whose output the report cites>
# e.g. grep -c "expected-pattern" "$D/output/files/result.txt"

echo "== 3. environment prerequisites =="
# e.g. curl -sf -o /dev/null --max-time 3 "${NEXUS_XDR_URL:-http://127.0.0.1:19998}/health" && echo "bus OK"
