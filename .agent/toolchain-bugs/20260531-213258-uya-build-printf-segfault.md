## Summary

`../uya/bin/uya build` crashes with a segmentation fault on a minimal program that only imports `libc.printf`, so DTLS test binaries cannot currently be built through the normal toolchain path.

## Affected Tasks

- 实现 handshake message fragmentation/reassembly。
- 后续所有依赖 `../uya/bin/uya build` / `../uya/bin/uya run` 构建执行 DTLS test main 的 Phase 8 任务。

## Toolchain Command

`../uya/bin/uya build .agent/toolchain-bugs/repros/20260531-213258-uya-build-printf-segfault.uya -o /tmp/repro_bin`

## Actual Error

The compiler process exits with signal 11 / status 139:

`Segmentation fault`

The same crash also reproduces with:

`../uya/bin/uya build .agent/toolchain-bugs/repros/20260531-213258-uya-build-printf-segfault.uya -o /tmp/repro.c --c99`

## Expected Behavior

The minimal program should compile successfully to either a binary or a C file.

## Repro File

`/media/winger/_dde_data/winger/uya/webrtc/.agent/toolchain-bugs/repros/20260531-213258-uya-build-printf-segfault.uya`

## Repro Code

```uya
use libc.printf;

export extern fn main(argc: i32, argv: & &byte) i32 {
    _ = argc;
    _ = argv;
    _ = printf("hello\n");
    return 0;
}
```

## Notes

- This is distinct from the already-recorded `uya run` host C codegen issue: here `uya build` itself segfaults before producing output.
- During DTLS handshake reassembly work, `bash tests/check_phase8_dtls.sh` can only be validated if the toolchain can build the test executable; this crash blocks that path.
