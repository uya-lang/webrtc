#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -x tests/constant_time_audit.py
rg -Fq "constant_time_bytes_equal" tests/constant_time_audit.py
rg -Fq "stun_verify_message_integrity" tests/constant_time_audit.py
rg -Fq "dtls_certificate_fingerprint_verify" tests/constant_time_audit.py
rg -Fq "memcmp" tests/constant_time_audit.py

python3 -m py_compile tests/constant_time_audit.py
python3 tests/constant_time_audit.py
bash tests/check_phase7_crypto.sh
bash tests/check_phase9_srtp.sh
