#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"

cat > src/_tmp_peer_connection_import_only.uya <<'EOF'
use webrtc.peer_connection;

fn main() i32 {
    return 0i32;
}
EOF

trap 'rm -f src/_tmp_peer_connection_import_only.uya' EXIT

../uya/bin/uya run src/_tmp_peer_connection_import_only.uya
