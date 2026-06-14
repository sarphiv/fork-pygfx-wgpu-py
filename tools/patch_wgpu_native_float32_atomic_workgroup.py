"""Patch a wgpu-native checkout to support workgroup float32 atomics.

Usage:
    python tools/patch_wgpu_native_float32_atomic_workgroup.py downloads/wgpu-native

The pinned wgpu-native commit exposes WGPUNativeFeature_ShaderFloat32Atomic,
but its resolved naga/wgpu-hal 29.0.3 crates only validate and enable the
storage-buffer side of Vulkan float32 atomics. This helper copies those crates
from Cargo's registry into the checkout, applies the small workgroup/shared
atomic changes, and adds [patch.crates-io] entries so the native build uses
the patched local crates.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


CRATES = {
    "naga": "29.0.3",
    "wgpu-hal": "29.0.3",
}

NAGA_OLD = """\
                // `Capabilities::SHADER_FLOAT32_ATOMIC` allows 32-bit floating-point
                // atomic operations `Add`, `Subtract`, and `Exchange`
                // in the `Storage` address space.
"""

NAGA_NEW = """\
                // `Capabilities::SHADER_FLOAT32_ATOMIC` allows 32-bit floating-point
                // atomic operations `Add`, `Subtract`, and `Exchange`
                // in the `Storage` and `WorkGroup` address spaces.
"""

NAGA_SPACE_OLD = """\
                if !matches!(pointer_space, crate::AddressSpace::Storage { .. }) {
                    log::error!(
                        "Float32 atomic operations are only supported in the Storage address space"
                    );
"""

NAGA_SPACE_NEW = """\
                if !matches!(
                    pointer_space,
                    crate::AddressSpace::Storage { .. } | crate::AddressSpace::WorkGroup
                ) {
                    log::error!(
                        "Float32 atomic operations are only supported in the Storage and WorkGroup address spaces"
                    );
"""

HAL_ENABLE_OLD = """\
                    vk::PhysicalDeviceShaderAtomicFloatFeaturesEXT::default()
                        .shader_buffer_float32_atomics(needed)
                        .shader_buffer_float32_atomic_add(needed),
"""

HAL_ENABLE_NEW = """\
                    vk::PhysicalDeviceShaderAtomicFloatFeaturesEXT::default()
                        .shader_buffer_float32_atomics(needed)
                        .shader_buffer_float32_atomic_add(needed)
                        .shader_shared_float32_atomics(needed)
                        .shader_shared_float32_atomic_add(needed),
"""

HAL_FEATURE_OLD = """\
                shader_atomic_float.shader_buffer_float32_atomics != 0
                    && shader_atomic_float.shader_buffer_float32_atomic_add != 0,
"""

HAL_FEATURE_NEW = """\
                shader_atomic_float.shader_buffer_float32_atomics != 0
                    && shader_atomic_float.shader_buffer_float32_atomic_add != 0
                    && shader_atomic_float.shader_shared_float32_atomics != 0
                    && shader_atomic_float.shader_shared_float32_atomic_add != 0,
"""


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)

    checkout = Path(sys.argv[1]).resolve()
    cargo_toml = checkout / "Cargo.toml"
    if not cargo_toml.is_file():
        raise SystemExit(f"Not a wgpu-native checkout: {checkout}")

    subprocess.run(["cargo", "fetch"], cwd=checkout, check=True)

    patch_root = checkout / "patched-crates"
    patch_root.mkdir(exist_ok=True)
    for crate, version in CRATES.items():
        src = find_registry_crate(crate, version)
        dst = patch_root / crate
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    replace_in_file(
        patch_root / "naga" / "src" / "valid" / "function.rs",
        [(NAGA_OLD, NAGA_NEW), (NAGA_SPACE_OLD, NAGA_SPACE_NEW)],
    )
    replace_in_file(
        patch_root / "wgpu-hal" / "src" / "vulkan" / "adapter.rs",
        [(HAL_ENABLE_OLD, HAL_ENABLE_NEW), (HAL_FEATURE_OLD, HAL_FEATURE_NEW)],
    )
    ensure_cargo_patch(cargo_toml)
    print(f"Patched {checkout} for workgroup float32 shader atomics.")


def find_registry_crate(crate: str, version: str) -> Path:
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo"))
    registry_src = cargo_home / "registry" / "src"
    matches = sorted(registry_src.glob(f"*/{crate}-{version}"))
    if not matches:
        raise RuntimeError(
            f"Could not find {crate} {version} in {registry_src}. "
            "Run cargo fetch for the wgpu-native checkout first."
        )
    return matches[-1]


def replace_in_file(path: Path, replacements: list[tuple[str, str]]) -> None:
    text = path.read_text()
    for old, new in replacements:
        if new in text:
            continue
        if old not in text:
            raise RuntimeError(f"Expected patch context was not found in {path}")
        text = text.replace(old, new, 1)
    path.write_text(text)


def ensure_cargo_patch(path: Path) -> None:
    text = path.read_text()
    lines = [
        "[patch.crates-io]",
        'naga = { path = "patched-crates/naga" }',
        'wgpu-hal = { path = "patched-crates/wgpu-hal" }',
    ]
    if all(line in text for line in lines):
        return
    if "[patch.crates-io]" in text:
        raise RuntimeError(
            f"{path} already has [patch.crates-io]; update the patch manually."
        )
    path.write_text(text.rstrip() + "\n\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
