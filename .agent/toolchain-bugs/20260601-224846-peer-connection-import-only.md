## Summary
Importing `webrtc.peer_connection` is enough to break code generation for the root `main` entry. The compiler finishes C emission but the generated C file has no `main`, so linking fails with an undefined reference to `main`.

## Status

Resolved / verified on 2026-06-02.

Re-ran `.agent/toolchain-bugs/repros/20260601-224846-peer-connection-import-only.sh` successfully with the current `../uya/bin/uya`. The previous missing-`main` link failure no longer reproduces; the compiler emitted `/tmp/uya_output_163644.c` and linked `/tmp/uya_out_163644`.

## Affected Tasks
- `实现 create_answer`
- `实现 add_ice_candidate`
- `实现 transceiver`
- `实现 sender/receiver`
- `实现 track`
- `实现 DataChannel 事件`
- `实现 connection state 聚合`

## Toolchain Command
`../uya/bin/uya run src/_tmp_peer_connection_import_only.uya`

## Actual Error
`/usr/bin/ld: ... undefined reference to 'main'`

## Expected Behavior
The file should compile and link successfully, then exit with status `0`.

## Repro File
`.agent/toolchain-bugs/repros/20260601-224846-peer-connection-import-only.sh`

## Repro Code
```bash
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
```

## Notes
This repro does not call `peer_connection_new`, `peer_connection_create_answer`, or `peer_connection_add_ice_candidate`. Simply importing the module is enough to trigger the broken codegen/link path.
