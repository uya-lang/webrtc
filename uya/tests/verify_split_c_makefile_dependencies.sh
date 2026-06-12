#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPILER="${UYA_COMPILER:-$REPO_ROOT/bin/uya}"
TMP_DIR="$(mktemp -d /tmp/uya-split-c-deps.XXXXXX)"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

export UYA_ROOT="$REPO_ROOT/lib/"

"$COMPILER" build "$REPO_ROOT/tests/test_option_struct.uya" \
    --split-c-dir "$TMP_DIR/split" -o "$TMP_DIR/out" --c99 >/dev/null

MAKEFILE="$TMP_DIR/split/Makefile"
if [ ! -f "$MAKEFILE" ]; then
    echo "split-C Makefile was not generated"
    exit 1
fi

if ! grep -q "uya_part1.o: .*uya_part1_types.h.*uya_strings_extern.h" "$MAKEFILE"; then
    echo "uya_part1.o rule is missing generated header dependencies"
    exit 1
fi

if ! grep -q "uya_common.o: .*uya_split_protos.h.*uya_mirror_globals.h.*uya_part1_types.h.*uya_strings_extern.h.*uya_vtable_externs.h" "$MAKEFILE" &&
    ! grep -q "uya_part2.o: .*uya_part1_types.h.*uya_split_protos.h.*uya_mirror_globals.h.*uya_strings_extern.h.*uya_vtable_externs.h" "$MAKEFILE"; then
    echo "split-C secondary object rule is missing generated header dependencies"
    exit 1
fi

"$TMP_DIR/out" >/dev/null

echo "verify_split_c_makefile_dependencies: ok"
