#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CMD_BOOTSTRAP="${UYA_CMD_BOOTSTRAP_COMPILER:-$ROOT_DIR/bin/uya}"
TMP_DIR="$(mktemp -d /tmp/uya_upm_add_path.XXXXXX)"
APP_DIR="$TMP_DIR/app"
DEP_DIR="$TMP_DIR/dep"
HELP_LOG="$TMP_DIR/help.log"
INSTALL_LOG="$TMP_DIR/install.log"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [ "${UYA_UPM_SUITE_PREBUILT:-0}" != "1" ] && [ ! -x "$ROOT_DIR/bin/cmd/upm" ]; then
    UYA_CMD_BOOTSTRAP_COMPILER="$CMD_BOOTSTRAP" make -C "$ROOT_DIR" cmd-upm >/dev/null
fi

mkdir -p "$APP_DIR/src" "$DEP_DIR/src"
cat > "$APP_DIR/uya.toml" <<'EOF_MANIFEST'
[package]
name = "app"
version = "0.1.0"
source-dir = "src"
EOF_MANIFEST
cat > "$APP_DIR/src/main.uya" <<'EOF_MAIN'
export fn main() i32 {
    return 0;
}
EOF_MAIN
cat > "$DEP_DIR/uya.toml" <<'EOF_DEP_MANIFEST'
[package]
name = "dep_pkg"
version = "0.1.0"
source-dir = "src"
EOF_DEP_MANIFEST
cat > "$DEP_DIR/src/lib.uya" <<'EOF_DEP'
export fn hello() &byte {
    return "ok" as &byte;
}
EOF_DEP

"$ROOT_DIR/bin/cmd/upm" add dep_pkg --path "$DEP_DIR" --manifest-path "$APP_DIR/uya.toml" >"$INSTALL_LOG" 2>&1

grep -q '\[dependencies\]' "$APP_DIR/uya.toml"
grep -q 'dep_pkg = { path = "' "$APP_DIR/uya.toml"
test -f "$APP_DIR/uya.lock"

set +e
"$ROOT_DIR/bin/cmd/upm" add dep_pkg --path "$DEP_DIR" --manifest-path "$APP_DIR/uya.toml" >"$HELP_LOG" 2>&1
STATUS=$?
set -e

if [ "$STATUS" -eq 0 ]; then
    echo "✗ duplicate alias unexpectedly succeeded"
    cat "$HELP_LOG"
    exit 1
fi

grep -q 'alias 已存在' "$HELP_LOG"

echo "verify_upm_add_path: ok"
