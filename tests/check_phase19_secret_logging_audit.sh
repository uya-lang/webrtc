#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -x tests/secret_logging_audit.py
rg -Fq "ice[-_]?pwd" tests/secret_logging_audit.py
rg -Fq "private[-_]?key" tests/secret_logging_audit.py
rg -Fq "message[-_]?integrity" tests/secret_logging_audit.py
rg -Fq "printf" tests/secret_logging_audit.py

python3 tests/secret_logging_audit.py
