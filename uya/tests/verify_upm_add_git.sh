#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CMD_BOOTSTRAP="${UYA_CMD_BOOTSTRAP_COMPILER:-$ROOT_DIR/bin/uya}"
TMP_DIR="$(mktemp -d /tmp/uya_upm_add_git.XXXXXX)"
APP_DIR="$TMP_DIR/app"
REPO_DIR="$TMP_DIR/repo.git"
REPO_WORK_DIR="$TMP_DIR/repo-work"
INSTALL_LOG="$TMP_DIR/install.log"
PARAM_LOG="$TMP_DIR/param.log"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [ "${UYA_UPM_SUITE_PREBUILT:-0}" != "1" ] && [ ! -x "$ROOT_DIR/bin/cmd/upm" ]; then
    UYA_CMD_BOOTSTRAP_COMPILER="$CMD_BOOTSTRAP" make -C "$ROOT_DIR" cmd-upm >/dev/null
fi

mkdir -p "$APP_DIR/src"
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

git init --bare "$REPO_DIR" >/dev/null
git clone "$REPO_DIR" "$REPO_WORK_DIR" >/dev/null
git -C "$REPO_WORK_DIR" config user.email codex@example.com
git -C "$REPO_WORK_DIR" config user.name Codex
cat > "$REPO_WORK_DIR/uya.toml" <<'EOF_DEP_MANIFEST'
[package]
name = "gui_uya"
version = "0.1.0"
source-dir = "src"
EOF_DEP_MANIFEST
mkdir -p "$REPO_WORK_DIR/src"
cat > "$REPO_WORK_DIR/src/file.uya" <<'EOF_DEP'
export fn hello() &byte {
    return "git" as &byte;
}
EOF_DEP
git -C "$REPO_WORK_DIR" add uya.toml src/file.uya
git -C "$REPO_WORK_DIR" commit -m "init" >/dev/null
git -C "$REPO_WORK_DIR" branch -M main
git -C "$REPO_WORK_DIR" push origin main >/dev/null
git --git-dir="$REPO_DIR" symbolic-ref HEAD refs/heads/main

"$ROOT_DIR/bin/cmd/upm" add gui_uya --git "$REPO_DIR" --branch main --manifest-path "$APP_DIR/uya.toml" >"$INSTALL_LOG" 2>&1

grep -q 'gui_uya = { git = "' "$APP_DIR/uya.toml"
grep -q 'branch = "main"' "$APP_DIR/uya.toml"
test -f "$APP_DIR/uya.lock"
grep -q 'source_kind = "git"' "$APP_DIR/uya.lock"

set +e
"$ROOT_DIR/bin/cmd/upm" add bad_dep --git "$REPO_DIR" --branch main --tag v1 --manifest-path "$APP_DIR/uya.toml" >"$PARAM_LOG" 2>&1
STATUS=$?
set -e

if [ "$STATUS" -eq 0 ]; then
    echo "✗ conflicting git ref args unexpectedly succeeded"
    cat "$PARAM_LOG"
    exit 1
fi

grep -q 'upm add 参数无效' "$PARAM_LOG"

set +e
"$ROOT_DIR/bin/cmd/upm" add dev_dep --dev --path "$REPO_DIR" --manifest-path "$APP_DIR/uya.toml" >"$PARAM_LOG" 2>&1
STATUS=$?
set -e

if [ "$STATUS" -ne 0 ]; then
    echo "✗ supported --dev unexpectedly failed"
    cat "$PARAM_LOG"
    exit 1
fi

grep -q '\[dev-dependencies\]' "$APP_DIR/uya.toml"
grep -q 'dev_dep = { path = "' "$APP_DIR/uya.toml"

echo "verify_upm_add_git: ok"
