#!/usr/bin/env python3
"""Patch generated ARM C when the unused pthread_create inline asm is too tight.

The RK1106 sender does not create threads, but the monolithic generated C still
contains the libc pthread_create implementation. Some arm-uclibc gcc builds fail
to allocate registers for that inline clone syscall. Keep the function present
and make it report failure instead.
"""

import pathlib
import re
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_arm_pthread_create_stub.py <generated.c>", file=sys.stderr)
        return 2

    path = pathlib.Path(sys.argv[1])
    text = path.read_text()
    pattern = re.compile(
        r'__asm__ volatile \("mov r7, #120\\n\\t.*?'
        r'\n\s*: "memory", "r0", "r1", "r2", "r3", "r4", "r7", "r12", "lr"\n'
        r'\s*\);\n',
        re.S,
    )
    replacement = "    /* RK1106 sender does not use pthread_create; avoid ARM inline asm register pressure. */\n    tid = -1;\n"
    new_text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        print("patch_arm_pthread_create_stub.py: pthread_create asm block not found", file=sys.stderr)
        return 1
    path.write_text(new_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
