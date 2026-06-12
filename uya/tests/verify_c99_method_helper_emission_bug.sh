#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

COMPILER="${UYA_COMPILER:-$ROOT/bin/uya}"
export UYA_ROOT="${ROOT}/lib/"
EXPECT_REPRO="${UYA_EXPECT_REPRO:-0}"

run_case() {
    local rel_src="$1"
    local expected_symbol="$2"
    local base
    base="$(basename "$rel_src" .uya)"
    local out_c="$TMP/${base}.c"
    local cc_log="$TMP/${base}.cc.log"

    echo "[probe] build $rel_src"
    "$COMPILER" build "$ROOT/$rel_src" --c99 --no-split-c -O0 -o "$out_c" >/dev/null

    echo "[probe] cc -c $base"
    if cc -std=c99 -c "$out_c" -o "$TMP/${base}.o" >"$cc_log" 2>&1; then
        echo "[probe] $rel_src: host C compile succeeded"
        if [ "$EXPECT_REPRO" = "1" ]; then
            echo "error: expected historical repro for $rel_src, but current compiler succeeded" >&2
            exit 1
        fi
        return 0
    fi

    echo "[probe] $rel_src: host C compile failed"
    cat "$cc_log"
    if [ "$EXPECT_REPRO" != "1" ]; then
        return 0
    fi

    if ! grep -q "$expected_symbol" "$cc_log"; then
        echo "error: expected failure log for $rel_src to mention $expected_symbol" >&2
        exit 1
    fi

    if ! grep -q "implicit declaration" "$cc_log"; then
        echo "error: expected failure log for $rel_src to contain 'implicit declaration'" >&2
        exit 1
    fi

    if ! grep -q "invalid initializer" "$cc_log"; then
        echo "error: expected failure log for $rel_src to contain 'invalid initializer'" >&2
        exit 1
    fi
}

run_case "tests/repros/c99_method_helper_struct_return.uya" "pair_copy"
run_case "tests/repros/c99_method_helper_err_union_void.uya" "helper_ok"

if [ "$EXPECT_REPRO" = "1" ]; then
    echo "verify_c99_method_helper_emission_bug: reproduced"
else
    echo "verify_c99_method_helper_emission_bug: probe completed"
fi
