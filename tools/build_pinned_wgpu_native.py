"""Build the pinned wgpu-native checkout and stage the library for packaging.

This script assumes the wgpu-native checkout has already been cloned and its
submodules initialized. It verifies that checkout against the header files
bundled in this repository, applies this fork's local native patches, builds the
release library, and copies it to wgpu/resources using the name expected by the
Python backend.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
RESOURCE_DIR = ROOT_DIR / "wgpu" / "resources"
PATCH_SCRIPT = ROOT_DIR / "tools" / "patch_wgpu_native_float32_atomic_workgroup.py"


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None):
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def capture(cmd: list[str], *, cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", default="downloads/wgpu-native")
    parser.add_argument("--os", choices=["linux", "macos", "windows"], required=True)
    parser.add_argument("--target", default="")
    parser.add_argument("--native-version", required=True)
    parser.add_argument("--native-commit", required=True)
    parser.add_argument("--webgpu-headers-commit", required=True)
    args = parser.parse_args()

    checkout = Path(args.checkout).resolve()
    verify_checkout(checkout, args.native_commit, args.webgpu_headers_commit)

    if args.target:
        run(["rustup", "target", "add", args.target])

    run([sys.executable, str(PATCH_SCRIPT), str(checkout)])

    env = os.environ.copy()
    env["WGPU_NATIVE_VERSION"] = args.native_version
    cargo_cmd = [
        "cargo",
        "build",
        "--release",
        "--manifest-path",
        str(checkout / "Cargo.toml"),
    ]
    if args.target:
        cargo_cmd.extend(["--target", args.target])
    run(cargo_cmd, env=env)

    built_lib = built_library_path(checkout, args.os, args.target)
    staged_lib = RESOURCE_DIR / staged_library_name(args.os)
    remove_staged_libraries()
    shutil.copy2(built_lib, staged_lib)
    verify_loaded_version(staged_lib, args.native_version)
    print(f"Staged {built_lib} as {staged_lib}")


def verify_checkout(
    checkout: Path, native_commit: str, webgpu_headers_commit: str
) -> None:
    if not (checkout / "Cargo.toml").is_file():
        raise RuntimeError(f"Not a wgpu-native checkout: {checkout}")

    actual_native_commit = capture(["git", "rev-parse", "HEAD"], cwd=checkout)
    if actual_native_commit != native_commit:
        raise RuntimeError(
            f"wgpu-native checkout is {actual_native_commit}, expected {native_commit}"
        )

    headers_dir = checkout / "ffi" / "webgpu-headers"
    actual_headers_commit = capture(["git", "rev-parse", "HEAD"], cwd=headers_dir)
    if actual_headers_commit != webgpu_headers_commit:
        raise RuntimeError(
            f"webgpu-headers checkout is {actual_headers_commit}, "
            f"expected {webgpu_headers_commit}"
        )

    wgpu_h = checkout / "ffi" / "wgpu.h"
    if "WGPUNativeFeature_ShaderFloat32Atomic = 0x00030027" not in wgpu_h.read_text():
        raise RuntimeError(
            "Pinned wgpu.h does not expose ShaderFloat32Atomic 0x00030027"
        )

    assert_same_file(wgpu_h, RESOURCE_DIR / "wgpu.h")
    assert_same_file(headers_dir / "webgpu.h", RESOURCE_DIR / "webgpu.h")


def assert_same_file(path1: Path, path2: Path) -> None:
    if path1.read_bytes() != path2.read_bytes():
        raise RuntimeError(f"{path1} does not match {path2}")


def remove_staged_libraries() -> None:
    for path in RESOURCE_DIR.iterdir():
        if path.suffix in {".so", ".dll", ".dylib"}:
            path.unlink()


def built_library_path(checkout: Path, os_name: str, target: str) -> Path:
    target_dir = Path(os.environ.get("CARGO_TARGET_DIR", checkout / "target"))
    profile_dir = target_dir / target / "release" if target else target_dir / "release"
    return profile_dir / base_library_name(os_name)


def base_library_name(os_name: str) -> str:
    if os_name == "windows":
        return "wgpu_native.dll"
    if os_name == "macos":
        return "libwgpu_native.dylib"
    return "libwgpu_native.so"


def staged_library_name(os_name: str) -> str:
    if os_name == "windows":
        return "wgpu_native-release.dll"
    if os_name == "macos":
        return "libwgpu_native-release.dylib"
    return "libwgpu_native-release.so"


def verify_loaded_version(path: Path, expected_version: str) -> None:
    expected = tuple(int(part) for part in expected_version.split("."))
    lib = ctypes.CDLL(str(path))
    version = lib.wgpuGetVersion()
    actual = tuple((version >> bits) & 0xFF for bits in (24, 16, 8, 0))
    if actual != expected:
        raise RuntimeError(f"{path} reports version {actual}, expected {expected}")


if __name__ == "__main__":
    main()
