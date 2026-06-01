#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"

tmp_main="src/_repro_peer_connection_import_crash.uya"
trap 'rm -f "$tmp_main"' EXIT

cat > "$tmp_main" <<'EOF'
use webrtc.peer_connection;

fn main() i32 {
    return 0i32;
}
EOF

../uya/bin/uya run "$tmp_main"
