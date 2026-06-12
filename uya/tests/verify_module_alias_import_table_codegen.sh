#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPILER="${UYA_COMPILER:-$ROOT_DIR/bin/uya}"

TMP_DIR="$(mktemp -d /tmp/uya_module_alias_codegen.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

SRC_DIR="$TMP_DIR/src"
mkdir -p "$SRC_DIR/fixture"

cat > "$SRC_DIR/fixture/noop.uya" <<'UYA'
export fn value() i32 {
    return 0;
}
UYA

cat > "$SRC_DIR/fixture/target.uya" <<'UYA'
export fn value() i32 {
    return 123;
}
UYA

MAIN="$SRC_DIR/main.uya"
{
    i=0
    while [ "$i" -lt 520 ]; do
        printf 'use fixture.noop as filler_%03d;\n' "$i"
        i=$((i + 1))
    done
    cat <<'UYA'
use fixture.target as late_target;

fn main() i32 {
    if late_target.value() != 123 {
        return 1;
    }
    return 0;
}
UYA
} > "$MAIN"

OUT_C="$TMP_DIR/module_alias_import_table.c"
COMPILE_LOG="$TMP_DIR/compile.log"
RUN_LOG="$TMP_DIR/run.log"
export UYA_ROOT="$ROOT_DIR/lib/"

if ! "$COMPILER" --c99 "$MAIN" -o "$OUT_C" > "$COMPILE_LOG" 2>&1; then
    echo "module alias import-table C99 compile failed" >&2
    cat "$COMPILE_LOG" >&2
    exit 1
fi

if grep -n 'unknown(' "$OUT_C" > "$TMP_DIR/unknown.log"; then
    echo "module alias call emitted unknown(...) in generated C" >&2
    cat "$TMP_DIR/unknown.log" >&2
    exit 1
fi

if ! "$COMPILER" run "$MAIN" > "$RUN_LOG" 2>&1; then
    echo "module alias import-table runtime check failed" >&2
    cat "$RUN_LOG" >&2
    exit 1
fi

TYPE_PRIORITY_MAIN="$SRC_DIR/type_namespace_priority.uya"
cat > "$TYPE_PRIORITY_MAIN" <<'UYA'
use std.runtime.entry;
use std.json.value.JsonValue;

export fn main() i32 {
    const v: JsonValue = JsonValue.json_null();
    match v {
        .json_null(_) => { return 0; },
        _ => { return 1; },
    }
}
UYA

TYPE_PRIORITY_C="$TMP_DIR/type_namespace_priority.c"
if ! "$COMPILER" --c99 "$TYPE_PRIORITY_MAIN" -o "$TYPE_PRIORITY_C" > "$COMPILE_LOG" 2>&1; then
    echo "type namespace priority C99 compile failed" >&2
    cat "$COMPILE_LOG" >&2
    exit 1
fi

if grep -n 'std_json_value_JsonValue_' "$TYPE_PRIORITY_C" > "$TMP_DIR/type_namespace_prefix.log"; then
    echo "type namespace union constructor was emitted as a module function call" >&2
    cat "$TMP_DIR/type_namespace_prefix.log" >&2
    exit 1
fi

if ! "$COMPILER" run "$TYPE_PRIORITY_MAIN" > "$RUN_LOG" 2>&1; then
    echo "type namespace priority runtime check failed" >&2
    cat "$RUN_LOG" >&2
    exit 1
fi

echo "verify_module_alias_import_table_codegen: ok"
