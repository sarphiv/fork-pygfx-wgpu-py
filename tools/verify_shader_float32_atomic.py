"""Verify native workgroup float32 shader atomics support for this custom wheel."""

import wgpu


FEATURE = "shader-float32-atomic"

WGSL = """
var<workgroup> acc: atomic<f32>;

@compute @workgroup_size(1)
fn main() {
    atomicStore(&acc, 0.0);
    _ = atomicAdd(&acc, 1.0);
}
"""


def find_float32_atomic_adapter():
    adapters = wgpu.gpu.enumerate_adapters_sync()
    return next((adapter for adapter in adapters if FEATURE in adapter.features), None)


def main():
    adapter = find_float32_atomic_adapter()
    if adapter is None:
        raise RuntimeError(f"No native WebGPU adapter reports {FEATURE!r}.")

    device = adapter.request_device_sync(required_features=[FEATURE])
    assert FEATURE in device.features

    shader = device.create_shader_module(code=WGSL)
    pipeline = device.create_compute_pipeline(
        layout="auto",
        compute={
            "module": shader,
            "entry_point": "main",
        },
    )
    assert pipeline is not None
    print(f"Verified {FEATURE!r} on {adapter.summary}")


if __name__ == "__main__":
    main()
