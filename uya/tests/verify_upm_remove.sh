#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CMD_BOOTSTRAP="${UYA_CMD_BOOTSTRAP_COMPILER:-$ROOT_DIR/bin/uya}"
TMP_DIR="$(mktemp -d /tmp/uya_upm_remove.XXXXXX)"
APP_DIR="$TMP_DIR/app"
DEP_DIR="$TMP_DIR/dep"
LOG_FILE="$TMP_DIR/remove.log"

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

[dependencies]
dep_pkg = { path = "../dep" }

[dev-dependencies]
dev_pkg = { path = "../dep" }
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

"$ROOT_DIR/bin/cmd/upm" remove dep_pkg --manifest-path "$APP_DIR/uya.toml" >"$LOG_FILE" 2>&1
! grep -q '^dep_pkg = ' "$APP_DIR/uya.toml"
grep -q '^dev_pkg = ' "$APP_DIR/uya.toml"
test -f "$APP_DIR/uya.lock"

set +e
"$ROOT_DIR/bin/cmd/upm" remove dev_pkg --dep --manifest-path "$APP_DIR/uya.toml" >"$LOG_FILE" 2>&1
STATUS=$?
set -e

if [ "$STATUS" -eq 0 ]; then
    echo "✗ remove --dep unexpectedly removed dev-only alias"
    cat "$LOG_FILE"
    exit 1
fi

grep -q '未找到依赖 alias' "$LOG_FILE"

"$ROOT_DIR/bin/cmd/upm" remove dev_pkg --dev --manifest-path "$APP_DIR/uya.toml" >"$LOG_FILE" 2>&1
! grep -q '^dev_pkg = ' "$APP_DIR/uya.toml"

echo "verify_upm_remove: ok"
