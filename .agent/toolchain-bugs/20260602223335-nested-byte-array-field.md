## Summary

The Uya C99 backend emits invalid C for struct fields typed as nested fixed-size byte arrays, for example `[[byte: 32]: 2]`.

## Affected Tasks

SDP fuzz。

## Toolchain Command

`../uya/bin/uya run .agent/toolchain-bugs/repros/20260602223335-nested-byte-array-field.uya`

## Actual Error

The generated C contains declarations shaped like `uint8_t[32] values[2];`, which the host C compiler rejects with `expected identifier or '(' before '[' token`.

## Expected Behavior

The backend should emit a valid nested C array field, such as `uint8_t values[2][32];`, and allow code using the nested fixed-size byte array field to compile and run.

## Repro File

`.agent/toolchain-bugs/repros/20260602223335-nested-byte-array-field.uya`

## Repro Code

```uya
struct NestedByteArrayField {
    values: [[byte: 32]: 2] = [],
}

fn main() i32 {
    var field: NestedByteArrayField = NestedByteArrayField{};
    field.values[0][0] = 1 as byte;
    return field.values[0][0] as i32;
}
```

## Notes

Compiling `src/webrtc_sdp_fuzz_test_main.uya` hits the same backend issue through `src/webrtc/sdp/model.uya`, whose SDP model stores bundle mids, media format tokens, and ICE candidate extension tokens as nested fixed-size byte arrays.
