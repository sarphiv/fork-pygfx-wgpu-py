# Project

- This repository is a fork of `pygfx/wgpu-py`, a Python binding around native WebGPU implementations.
- Keep changes focused on the requested `wgpu-py` behavior, generated bindings, native resources, packaging, and verification.

# Environment

- Work only inside the project directory. In the devcontainer, the project is mounted at `/workspace`.
- Use the project-local Python environment in `.venv`; prefer `uv run`, `uv venv`, and `uv pip` over global Python installs.
- Rust 1.87.0 is installed for `wgpu-native` builds. Keep Cargo build artifacts in the configured cache, not in unrelated host paths.
- Use GitHub releases for custom wheel assets when asked. Do not publish custom wheels to PyPI unless the human explicitly changes that requirement.

# Workflow

- Inspect real manifests, generated files, headers, and local scripts before adding abstractions or fallback systems.
- For native `wgpu` work, keep `wgpu/resources/webgpu.h`, `wgpu/resources/wgpu.h`, regenerated Python mappings, backend metadata, and `libwgpu_native` from matching sources.
- Do not mix old generated bindings with a new native library. If upstream `wgpu-native` changes a feature name or numeric value, stop and report the exact observed state.
- For complex or high-risk changes, leave a short plan, explicit assumptions, validation commands, and release handoff notes.

# Validation

- Use targeted checks first, such as `uv run python codegen`, focused `uv run pytest ...`, and `uv run python -m build --wheel`.
- For native GPU validation inside the container, check `nvidia-smi -L` and `vulkaninfo --summary` when available. Treat `llvmpipe`, software rasterizers, or CPU Vulkan adapters as failed hardware acceleration.
- Keep release notes precise: include exact native/header commits, platform tag, feature spelling, numeric IDs, and tested hardware/backend when available.
