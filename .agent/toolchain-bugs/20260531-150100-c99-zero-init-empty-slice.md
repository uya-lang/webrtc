## Summary

The C99 backend emits invalid C for zero-value struct initialization and empty slice assignment. Valid Uya source type-checks, but generated C contains statements like `holder.bytes = {0};`, which the host C compiler rejects.

## Affected Tasks

- `实现 controlling / controlled role。`

## Toolchain Command

`../uya/bin/uya build --c99 .agent/toolchain-bugs/repros/20260531-150100-c99-zero-init-empty-slice.uya -o /tmp/uya_zero_init_repro.c`

## Actual Error

`cc -std=c99 -O0 -g -fno-builtin /tmp/uya_zero_init_repro.c -o /tmp/uya_zero_init_repro_bin`

```
/tmp/uya_zero_init_repro.c:1236:20: error: expected expression before '{' token
/tmp/uya_zero_init_repro.c:1237:22: error: expected expression before '{' token
/tmp/uya_zero_init_repro.c:1238:20: error: expected expression before '{' token
```

## Expected Behavior

The C99 backend should lower zero-value structs and empty slices into valid C initializers/assignments so the host toolchain can compile the generated file.

## Repro File

`.agent/toolchain-bugs/repros/20260531-150100-c99-zero-init-empty-slice.uya`

## Repro Code

```uya
export struct Holder {
    bytes: &[byte] = [],
    payload: [byte: 4] = [],
}

export fn main() i32 {
    var holder: Holder = Holder{};
    holder.bytes = [];
    return holder.payload[0] as i32;
}
```

## Notes

- The same `{0}` emission pattern appears throughout `../uya/bin/uya test src/webrtc_ice_test.uya`, including `StunAttributeIterator{}`, `StunMessageBuilder{}`, `IceAgent{}`, and empty-slice arguments like `[]`.
