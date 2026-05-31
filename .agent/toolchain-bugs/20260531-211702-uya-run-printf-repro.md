## Summary

`../uya/bin/uya run` can emit invalid C for the libc `system()` wrapper even for a minimal program that only imports `libc.printf`, causing the host C compiler to fail before DTLS tests can run.

## Affected Tasks

- 实现 handshake message fragmentation/reassembly。
- 后续依赖 `../uya/bin/uya run` 执行 DTLS Uya 测试主程序的 Phase 8 任务。

## Toolchain Command

`../uya/bin/uya run .agent/toolchain-bugs/repros/20260531-211702-uya-run-printf-repro.uya`

## Actual Error

Host C compilation fails with:

`error: lvalue required as unary '&' operand`

inside generated `system()` wrapper code, for example:

`uint8_t * * envp = (uint8_t * *)(&(uint8_t * *)empty_env[0]);`

## Expected Behavior

The minimal program should compile and run successfully, printing `hello`.

## Repro File

`/media/winger/_dde_data/winger/uya/webrtc/.agent/toolchain-bugs/repros/20260531-211702-uya-run-printf-repro.uya`

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

- The DTLS reassembly work itself type-checks, but `bash tests/check_phase8_dtls.sh` is blocked at host C compilation time by this toolchain issue.
- This is not caused by the DTLS source logic alone: the minimal `printf` repro triggers the same generated `system()` failure.
