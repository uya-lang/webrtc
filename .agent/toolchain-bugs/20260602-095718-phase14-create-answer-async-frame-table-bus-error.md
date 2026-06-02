## Summary

`uya run` 编译 Phase 14 `create_answer` 测试时，在前端类型检查和优化都通过后，于 C99 代码生成阶段触发 `Bus error`。编译器已经写出生成的 C 文件，但文件在 `_uya_async_frame_descriptors` 初始化中被截断，且没有生成 `struct AsyncFrameDescriptorTable` 定义，导致宿主 `cc` 也无法编译该产物。

## Status

Resolved / verified on 2026-06-02.

Re-ran `.agent/toolchain-bugs/repros/20260602-095718-phase14-create-answer-async-frame-table-bus-error.sh` successfully with the current `../uya/bin/uya`. The test printed `PeerConnection create_answer tests passed`; generated C reached a complete `main_main` and `webrtc_peer_connection_peer_connection_create_answer` instead of truncating at `_uya_async_frame_descriptors`.

## Affected Tasks

- `实现 create_answer`
- `实现 add_ice_candidate`
- 后续所有需要运行 `webrtc.peer_connection` Phase 14 测试的任务

## Toolchain Command

`bash .agent/toolchain-bugs/repros/20260602-095718-phase14-create-answer-async-frame-table-bus-error.sh`

## Actual Error

直接运行：

```text
=== 代码生成阶段 ===
模块名: src/webrtc_peer_connection_create_answer_test_main.uya
tests/check_phase14_peer_connection_create_answer.sh: line 13: ... Bus error               ../uya/bin/uya run src/webrtc_peer_connection_create_answer_test_main.uya
```

最近一次生成文件：

```text
/tmp/uya_output_1657984.c
851968 /tmp/uya_output_1657984.c
```

该 C 文件末尾停在：

```text
// Async frame descriptors (for unified AsyncFramePool)
struct AsyncFrameDescriptorTable _uya_async_frame_descriptors = {
```

手动交给宿主编译器后，首批错误为：

```text
/tmp/uya_output_1657984.c:17215:8: error: variable '_uya_async_frame_descriptors' has initializer but incomplete type
/tmp/uya_output_1657984.c:17216:6: error: 'struct AsyncFrameDescriptorTable' has no member named 'entries'
/tmp/uya_output_1657984.c:17216:16: error: extra brace group at end of initializer
```

## Expected Behavior

编译器应稳定完成 C99 代码生成并进入宿主编译/链接阶段。若源代码存在问题，也应返回可诊断的前端或后端错误，而不是在代码生成阶段 `Bus error`，更不应留下截断且结构定义缺失的 C 文件。

## Repro File

`.agent/toolchain-bugs/repros/20260602-095718-phase14-create-answer-async-frame-table-bus-error.sh`

## Repro Code

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"

run_log="$(mktemp)"
trap 'rm -f "$run_log"' EXIT

set +e
../uya/bin/uya run src/webrtc_peer_connection_create_answer_test_main.uya >"$run_log" 2>&1
status="$?"
set -e

cat "$run_log"

generated_c="$(awk '/输出文件:/ { print $2 }' "$run_log" | tail -n 1)"
if [[ -n "$generated_c" && -f "$generated_c" ]]; then
    printf '\nGenerated C evidence:\n'
    wc -c "$generated_c"
    rg -n "AsyncFrameDescriptorTable|// Async frame descriptors|main_main|create_answer" "$generated_c" | head -n 40 || true
    printf '\nHost cc first errors:\n'
    cc -std=c99 -O0 -g -fno-builtin "$generated_c" -o /tmp/webrtc-create-answer-bug-bin 2>&1 | head -n 40 || true
fi

exit "$status"
```

## Notes

- 这不是 `create_answer` 的运行期断言失败：测试主函数尚未执行。
- `src/webrtc_peer_connection_create_answer_test_main.uya` 只导入 `webrtc.peer_connection` 与 `webrtc.runtime`，构造 remote SDP 后调用 `peer_connection_create_answer`，源码类型检查通过。
- 之前的 `peer_connection-import-only` 报告是链接阶段缺少 `main`；本报告是完整 Phase 14 测试在代码生成阶段 `Bus error`，并留下截断/无效 C 产物，二者现象不同。
- `tests/check_phase6_turn.sh` 已经有针对同类 `_uya_async_frame_descriptors` 缺失定义的测试侧 workaround，但这里先按编译器 bug 报告，不把 workaround 混入 Phase 14 验证。
