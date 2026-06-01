## Summary
`uya run` 在代码生成阶段导入 `webrtc.peer_connection` 时触发编译器段错误（SIGSEGV / bus error）。即使主程序为空，只要 `use webrtc.peer_connection;` 就会崩溃。

## Affected Tasks
- 实现 `create_answer`。
- 实现 `add_ice_candidate`。

## Toolchain Command
`bash .agent/toolchain-bugs/repros/20260601-211034-peer-connection-import-codegen-crash.sh`

## Actual Error
编译输出停在：
- `=== 代码生成阶段 ===`
- `模块名: src/_repro_peer_connection_import_crash.uya`
随后 shell 报错：
- `Segmentation fault`（退出码 139）

## Expected Behavior
编译器应稳定完成代码生成并进入宿主编译/链接阶段，或返回可诊断的前端/后端错误，而不是在代码生成阶段崩溃。

## Repro File
`.agent/toolchain-bugs/repros/20260601-211034-peer-connection-import-codegen-crash.sh`

## Repro Code
```bash
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
```

## Notes
- 这不是 `peer_connection` 运行逻辑断言失败，而是编译器在代码生成阶段直接崩溃。
- 我已经把 repro 缩到只剩 `use webrtc.peer_connection;` 的空主程序。
- 当前 `create_answer` / `add_ice_candidate` 两项都被这个崩溃挡住，短期内无法继续做真实验证。
