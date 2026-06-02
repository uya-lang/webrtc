#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"

run_log="$(mktemp)"
trap 'rm -f "$run_log"' EXIT

set +e
../uya/bin/uya run src/webrtc_peer_connection_create_answer_test_main.uya >"$run_log" 2>&1
status="$?"
set -e

cat "$run_log"

generated_c="$(awk '/输出文件:/ { print $2 }' "$run_log" | tail -n 1)"
if [[ -n "$generated_c" && -f "$generated_c" ]]; then
    printf '\nGenerated C evidence:\n'
    wc -c "$generated_c"
    rg -n "AsyncFrameDescriptorTable|// Async frame descriptors|main_main|create_answer" "$generated_c" | head -n 40 || true
    printf '\nHost cc first errors:\n'
    cc -std=c99 -O0 -g -fno-builtin "$generated_c" -o /tmp/webrtc-create-answer-bug-bin 2>&1 | head -n 40 || true
fi

exit "$status"
