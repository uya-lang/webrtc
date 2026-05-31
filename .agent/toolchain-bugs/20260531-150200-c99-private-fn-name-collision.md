## Summary

The C99 backend does not uniquify private function names across modules. Two distinct modules can each define the same internal helper name, and the generated single C file then contains duplicate `static` function definitions that fail to compile.

## Affected Tasks

- `实现 controlling / controlled role。`

## Toolchain Command

`../uya/bin/uya test .agent/toolchain-bugs/repros/20260531-150200-c99-private-fn-name-collision/main.uya`

## Actual Error

```
/tmp/uya_output_1796179.c:1191:35: error: redefinition of 'same_name'
/tmp/uya_output_1796179.c:1169:35: note: previous definition of 'same_name' with type 'bool(int32_t, int32_t)'
```

## Expected Behavior

Private helper functions from different modules should be mangled or otherwise uniquified so they can coexist in the generated C translation unit.

## Repro File

`.agent/toolchain-bugs/repros/20260531-150200-c99-private-fn-name-collision/main.uya`

## Repro Code

```uya
use moda;
use modb;

export fn main() i32 {
    return moda_value() + modb_value();
}
```

## Notes

- This matches the `ice_bytes_equal` / `ice_transport_address_copy` redefinition failures seen when compiling `src/webrtc_ice_test.uya`.
