#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPILER="${UYA_COMPILER:-$ROOT_DIR/bin/uya-upm-stage2}"
CMD_BOOTSTRAP="${UYA_CMD_BOOTSTRAP_COMPILER:-$ROOT_DIR/bin/uya}"
DISPATCHER="${UYA_DISPATCHER:-$ROOT_DIR/bin/uya-upm-stage2}"
CMD_BIN="$ROOT_DIR/bin/cmd/upm"
TMP_DIR="$(mktemp -d /tmp/uya_cmd_dispatch.XXXXXX)"
DISPATCH_LOG="$TMP_DIR/dispatch.log"
DIRECT_LOG="$TMP_DIR/direct.log"
MISSING_LOG="$TMP_DIR/missing.log"
BACKUP_BIN="$TMP_DIR/upm.backup"

cleanup() {
    if [ -f "$BACKUP_BIN" ]; then
        mv "$BACKUP_BIN" "$CMD_BIN"
    fi
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [ "${UYA_UPM_SUITE_PREBUILT:-0}" != "1" ] && [ ! -x "$ROOT_DIR/bin/cmd/upm" ]; then
    UYA_CMD_BOOTSTRAP_COMPILER="$CMD_BOOTSTRAP" make -C "$ROOT_DIR" cmd-upm >/dev/null
fi

"$DISPATCHER" upm --help >"$DISPATCH_LOG" 2>&1
"$CMD_BIN" --help >"$DIRECT_LOG" 2>&1

grep -q "upm build" "$DISPATCH_LOG"
grep -q "upm build" "$DIRECT_LOG"

mv "$CMD_BIN" "$BACKUP_BIN"
set +e
"$DISPATCHER" upm --help >"$MISSING_LOG" 2>&1
STATUS=$?
set -e

if [ "$STATUS" -eq 0 ]; then
    echo "✗ 缺失 cmd/upm 时 dispatcher 意外成功"
    cat "$MISSING_LOG"
    exit 1
fi

grep -q "cmd/upm" "$MISSING_LOG"
grep -q "make cmds" "$MISSING_LOG"

echo "test_cmd_dispatch: ok"
