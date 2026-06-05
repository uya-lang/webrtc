#!/usr/bin/env python3
"""Small post-process step for Uya single-file C99 on RK uclibc toolchains."""

from __future__ import annotations

import argparse
from pathlib import Path


MATH_UNDEF_BLOCK = """#ifdef isnan
#undef isnan
#endif
#ifdef isinf
#undef isinf
#endif
#ifdef isfinite
#undef isfinite
#endif
#ifdef signbit
#undef signbit
#endif
"""


def patch_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("typedef int32_t wchar_t;\n", "")
    needle = "int32_t isnan(double x);"
    if needle in text and "#undef isnan" not in text:
        text = text.replace(needle, MATH_UNDEF_BLOCK + needle, 1)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    patch_file(args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
