#!/usr/bin/env python3
"""Stage webrtc + sibling vp8 sources for the RK1106 VP8 direct sender build."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


EC_REPLACEMENTS = {
    "ec_p256.ec_p256_ecdh": "ec_p256_ecdh",
    "ec_p384.ec_p384_ecdh": "ec_p384_ecdh",
    "ec_p256.ec_p256_public_from_private": "ec_p256_public_from_private",
    "ec_p384.ec_p384_public_from_private": "ec_p384_public_from_private",
    "ec_p256.ec_p256_ecdsa_sign_with_k": "ec_p256_ecdsa_sign_with_k",
    "ec_p384.ec_p384_ecdsa_sign_with_k": "ec_p384_ecdsa_sign_with_k",
    "ec_p256.ec_p256_ecdsa_verify": "ec_p256_ecdsa_verify",
    "ec_p384.ec_p384_ecdsa_verify": "ec_p384_ecdsa_verify",
}


def truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise SystemExit(f"missing source tree: {src}")
    shutil.copytree(src, dst, dirs_exist_ok=True)


def patch_tls_ec_calls(stage_lib: Path) -> None:
    ec_path = stage_lib / "tls" / "crypto" / "ec.uya"
    text = ec_path.read_text(encoding="utf-8")
    changed = False
    for old, new in EC_REPLACEMENTS.items():
        if old in text:
            text = text.replace(old, new)
            changed = True
    if changed:
        ec_path.write_text(text, encoding="utf-8")


def patch_pthread_create_for_single_thread_sender(stage_lib: Path) -> None:
    pthread_path = stage_lib / "libc" / "pthread.uya"
    text = pthread_path.read_text(encoding="utf-8")
    start_marker = 'export extern "libc" fn pthread_create('
    end_marker = "\n// pthread_join -"
    start = text.find(start_marker)
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise SystemExit(f"unexpected pthread.uya shape: {pthread_path}")
    replacement = """export extern "libc" fn pthread_create(thread: &pthread_t, attr: &const pthread_attr_t, start_routine: &void, arg: &void) i32 {
    _ = thread;
    _ = attr;
    _ = start_routine;
    _ = arg;
    return 38; // ENOSYS; this RK1106 sender build is single-threaded.
}
"""
    pthread_path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def force_scalar_vp8(stage_src: Path) -> None:
    dispatch_path = stage_src / "vp8" / "kernels" / "dispatch.uya"
    text = dispatch_path.read_text(encoding="utf-8")
    text = text.replace("use vp8.kernels.asm_x86.sad_16x16_x86_asm;\n", "")
    old = """fn forced_sad_16x16_fn(capabilities: &SimdCapabilities) &void {
    if capabilities.cpu.asm_x86 {
        return &sad_16x16_x86_asm;
    }
    return &sad_16x16_u8x16;
}
"""
    new = """fn forced_sad_16x16_fn(capabilities: &SimdCapabilities) &void {
    _ = capabilities;
    return &sad_16x16_u8x16;
}
"""
    old_kernel_branch = """    if table.sad_16x16_fn == (&sad_16x16_x86_asm as &void) {
        return sad_16x16_x86_asm(src, src_stride, reference, reference_stride);
    }
"""
    if old not in text:
        raise SystemExit(f"unexpected VP8 dispatch shape: {dispatch_path}")
    text = text.replace(old, new)
    text = text.replace(old_kernel_branch, "")
    dispatch_path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--vp8-repo", required=True, type=Path)
    parser.add_argument("--uya-lib", required=True, type=Path)
    parser.add_argument("--stage-root", required=True, type=Path)
    parser.add_argument("--force-scalar", default="1")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    vp8_repo = args.vp8_repo.resolve()
    uya_lib = args.uya_lib.resolve()
    stage_root = args.stage_root.resolve()
    stage_src = stage_root / "src"
    stage_lib = stage_root / "lib"

    shutil.rmtree(stage_root, ignore_errors=True)
    stage_src.mkdir(parents=True, exist_ok=True)
    copy_tree(repo_root / "src", stage_src)
    copy_tree(vp8_repo / "src" / "vp8", stage_src / "vp8")
    copy_tree(uya_lib, stage_lib)
    patch_tls_ec_calls(stage_lib)
    patch_pthread_create_for_single_thread_sender(stage_lib)
    if truthy(args.force_scalar):
        force_scalar_vp8(stage_src)
    (stage_root / ".ready").write_text("ready\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
