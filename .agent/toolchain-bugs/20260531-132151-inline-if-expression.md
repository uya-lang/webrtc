## Summary

The available Uya compilers in this environment reject documented expression-level `if ... else` syntax during parsing. This blocks `src/webrtc_ice_test.uya` before any Phase 5 ICE role tests can run because `src/webrtc/ice/checklist.uya` already uses the same syntax.

## Affected Tasks

- `实现 controlling / controlled role。`

## Toolchain Command

`../uya/bin/uya check .agent/toolchain-bugs/repros/20260531-132151-inline-if-expression.uya`

## Actual Error

`错误: 语法分析失败 (.agent/toolchain-bugs/repros/20260531-132151-inline-if-expression.uya:2:24): 意外的 token 'if'`

## Expected Behavior

The compiler should accept expression-level `if ... else` syntax, consistent with the language documentation and the existing project sources that already use it.

## Repro File
`.agent/toolchain-bugs/repros/20260531-132151-inline-if-expression.uya`

## Repro Code

```uya
export fn main() i32 {
    const value: i32 = if true { 1 } else { 2 };
    return value;
}
```

## Notes

- `src/webrtc/ice/checklist.uya:102` uses the same expression-level `if` form and is the first parser blocker when running `../uya/bin/uya test src/webrtc_ice_test.uya`.
- `../uya/docs/uya.md:6544` documents the same syntax form (`const new_cap = if ... else ...;`), so the parser rejection contradicts the documented language behavior.
