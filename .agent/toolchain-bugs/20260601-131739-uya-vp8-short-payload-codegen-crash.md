## Summary
`uya run` 在 C99 代码生成阶段对 VP8 keyframe 短包错误分支测试触发编译器段错误（SIGSEGV）。问题出现在将 `vp8_rtp_payload_is_keyframe(empty_payload[0:0])` 替换为 `vp8_rtp_packet_is_keyframe(short_packet[0:1])` 后，类型检查和优化均通过，但代码生成阶段崩溃。

## Affected Tasks
- 对齐 `../vp8` 的 VP8 RTP malformed 错误、keyframe 检测和 frame boundary 语义。

## Toolchain Command
`bash .agent/toolchain-bugs/repros/20260601-131739-uya-vp8-short-payload-codegen-crash.sh`

## Actual Error
编译输出停在：
- `=== 代码生成阶段 ===`
- `模块名: src/_repro_vp8_codegen_crash_main.uya`
随后 shell 报错：
- `Segmentation fault`（退出码 139）

## Expected Behavior
编译器应稳定完成代码生成并进入宿主编译/链接阶段，或返回可诊断的前端/后端错误，而不是在代码生成阶段崩溃。

## Repro File
`.agent/toolchain-bugs/repros/20260601-131739-uya-vp8-short-payload-codegen-crash.sh`

## Repro Code
```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"

tmp_main="src/_repro_vp8_codegen_crash_main.uya"
trap 'rm -f "$tmp_main"' EXIT

cp src/webrtc_media_vp8_rtp_test_main.uya "$tmp_main"
perl -0777 -i -pe 's/var empty_payload: \[byte: 1\] = \[\];\n    const short_check: !bool = vp8_rtp_payload_is_keyframe\(empty_payload\[0:0\]\);/var short_packet: [byte: 1] = [0x10 as byte];\n    const short_check: !bool = vp8_rtp_packet_is_keyframe(short_packet[0:1]);/s' "$tmp_main"

../uya/bin/uya run "$tmp_main"
```

## Notes
- 当前可行绕过：测试中直接调用 `vp8_rtp_payload_is_keyframe(empty_payload[0:0])` 验证短 payload malformed 分支，避免触发该崩溃路径。
- 该 repro 为最小化到单脚本、可在当前仓库复现的输入；触发依赖当前 `src/webrtc/media/vp8_rtp.uya` 与 `src/webrtc_media_vp8_rtp_test_main.uya`。
