## Summary
`uya run` 在代码生成阶段同时导入 `webrtc.binary` 与 `webrtc.peer_connection` 时触发编译器段错误，导致当前 PeerConnection 相关任务无法做真实验证。

## Affected Tasks
- 实现 `create_answer`。
- 实现 `add_ice_candidate`。

## Toolchain Command
`bash .agent/toolchain-bugs/repros/20260601-221430-peer-connection-binary-codegen-segv.sh`

## Actual Error
编译输出停在：
- `=== 代码生成阶段 ===`
- `模块名: src/_repro_peer_connection_binary_codegen_segv.uya`
随后 shell 报错：
- `Segmentation fault`（退出码 139）

## Expected Behavior
编译器应稳定完成代码生成并进入宿主编译/链接阶段，或返回一个可诊断的前端/后端错误，而不是在代码生成阶段崩溃。

## Repro File
`.agent/toolchain-bugs/repros/20260601-221430-peer-connection-binary-codegen-segv.sh`

## Repro Code
```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"

tmp_main="src/_repro_peer_connection_binary_codegen_segv.uya"
trap 'rm -f "$tmp_main"' EXIT

cat > "$tmp_main" <<'EOF'
use webrtc.binary;
use webrtc.peer_connection;

fn main() i32 {
    return 0i32;
}
EOF

../uya/bin/uya run "$tmp_main"
```

## Notes
- 仅导入 `webrtc.peer_connection` 的最小 repro 现在会走到“缺少 `main`”的链接错误，不再是这次的 codegen 段错误。
- 只要再加入 `use webrtc.binary;`，就能稳定复现当前的 codegen 崩溃。
- 这个问题阻止了当前 PeerConnection 相关任务的真实运行验证。
