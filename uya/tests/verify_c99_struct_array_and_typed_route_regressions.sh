#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

COMPILER="${UYA_COMPILER:-$ROOT/bin/uya}"
export UYA_ROOT="${ROOT}/lib/"

build_single_c() {
    local rel_src="$1"
    local out_c="$2"

    echo "[probe] build $rel_src"
    "$COMPILER" build "$ROOT/$rel_src" --c99 --no-split-c -O0 -o "$out_c" >/dev/null
}

verify_array_field_copy() {
    local rel_src="tests/repros/c99_struct_array_field_member_copy.uya"
    local out_c="$TMP/array_field_copy.c"
    local cc_log="$TMP/array_field_copy.cc.log"
    local bin_out="$TMP/array_field_copy.bin"

    build_single_c "$rel_src" "$out_c"

    echo "[probe] cc -Werror array field copy"
    if ! cc -std=c99 -O0 -Werror -c "$out_c" -o "$TMP/array_field_copy.o" >"$cc_log" 2>&1; then
        cat "$cc_log"
        echo "error: array field struct literal repro still emits host C diagnostics" >&2
        exit 1
    fi

    echo "[probe] compile+run array field copy"
    cc -std=c99 -O0 "$out_c" -o "$bin_out" >"$cc_log" 2>&1
    if ! "$bin_out"; then
        echo "error: array field struct literal repro exited non-zero" >&2
        exit 1
    fi
}

verify_typed_route() {
    local rel_src="tests/repros/c99_uyagin_typed_route_generic_method.uya"
    local out_c="$TMP/typed_route.c"
    local cc_log="$TMP/typed_route.cc.log"

    build_single_c "$rel_src" "$out_c"

    echo "[probe] cc -c typed route"
    if ! cc -std=c99 -O0 -c "$out_c" -o "$TMP/typed_route.o" >"$cc_log" 2>&1; then
        cat "$cc_log"
        echo "error: typed route generic method repro still fails host C compile" >&2
        exit 1
    fi
}

verify_array_field_copy
verify_typed_route

echo "verify_c99_struct_array_and_typed_route_regressions: ok"
