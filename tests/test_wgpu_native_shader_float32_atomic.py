import struct

import pytest
import wgpu

from testutils import can_use_wgpu_lib


FEATURE = "shader-float32-atomic"
WORKGROUP_SIZE = 256
WORKGROUPS = 64


if not can_use_wgpu_lib:
    pytest.skip("Skipping tests that need the wgpu lib", allow_module_level=True)


def find_float32_atomic_adapter():
    adapters = wgpu.gpu.enumerate_adapters_sync()
    return next((adapter for adapter in adapters if FEATURE in adapter.features), None)


@pytest.fixture(scope="module")
def float32_atomic_device():
    adapter = find_float32_atomic_adapter()
    if adapter is None:
        pytest.skip(f"No wgpu adapter reports {FEATURE!r}")

    device = adapter.request_device_sync(required_features=[FEATURE])
    assert FEATURE in device.features
    return device


def run_atomic_compute(device, shader_code, output_count, workgroups=WORKGROUPS):
    shader = device.create_shader_module(code=shader_code)
    pipeline = device.create_compute_pipeline(
        layout="auto",
        compute={"module": shader, "entry_point": "main"},
    )

    buffer_size = output_count * 4
    buffer = device.create_buffer(
        size=buffer_size,
        usage=wgpu.BufferUsage.STORAGE
        | wgpu.BufferUsage.COPY_SRC
        | wgpu.BufferUsage.COPY_DST,
    )

    bind_group = device.create_bind_group(
        layout=pipeline.get_bind_group_layout(0),
        entries=[
            {
                "binding": 0,
                "resource": {
                    "buffer": buffer,
                    "offset": 0,
                    "size": buffer_size,
                },
            },
        ],
    )

    encoder = device.create_command_encoder()
    compute_pass = encoder.begin_compute_pass()
    compute_pass.set_pipeline(pipeline)
    compute_pass.set_bind_group(0, bind_group)
    compute_pass.dispatch_workgroups(workgroups)
    compute_pass.end()
    device.queue.submit([encoder.finish()])

    data = device.queue.read_buffer(buffer)
    return struct.unpack(f"{output_count}f", bytes(data))


def test_workgroup_shader_float32_atomic_add(float32_atomic_device):
    shader_code = f"""
        var<workgroup> acc: atomic<f32>;

        @group(0) @binding(0)
        var<storage, read_write> out_values: array<f32, {WORKGROUPS}>;

        @compute @workgroup_size({WORKGROUP_SIZE})
        fn main(
            @builtin(local_invocation_index) local_index: u32,
            @builtin(workgroup_id) workgroup_id: vec3<u32>,
        ) {{
            if (local_index == 0u) {{
                atomicStore(&acc, 0.0);
            }}
            workgroupBarrier();

            _ = atomicAdd(&acc, 1.0);
            workgroupBarrier();

            if (local_index == 0u) {{
                out_values[workgroup_id.x] = atomicLoad(&acc);
            }}
        }}
    """

    values = run_atomic_compute(float32_atomic_device, shader_code, WORKGROUPS)

    expected_value = float(WORKGROUP_SIZE)
    expected_total = float(WORKGROUP_SIZE * WORKGROUPS)
    assert values == (expected_value,) * WORKGROUPS
    assert sum(values) == expected_total


def test_storage_shader_float32_atomic_add(float32_atomic_device):
    shader_code = f"""
        struct Data {{
            acc: atomic<f32>,
        }};

        @group(0) @binding(0)
        var<storage, read_write> data: Data;

        @compute @workgroup_size({WORKGROUP_SIZE})
        fn main() {{
            _ = atomicAdd(&data.acc, 1.0);
        }}
    """

    (value,) = run_atomic_compute(float32_atomic_device, shader_code, 1)

    assert value == float(WORKGROUP_SIZE * WORKGROUPS)


def test_storage_shader_float32_atomic_array_add(float32_atomic_device):
    lanes = 8
    shader_code = f"""
        struct Data {{
            acc: array<atomic<f32>, {lanes}>,
        }};

        @group(0) @binding(0)
        var<storage, read_write> data: Data;

        @compute @workgroup_size({WORKGROUP_SIZE})
        fn main(@builtin(global_invocation_id) gid: vec3<u32>) {{
            let index = gid.x % {lanes}u;
            _ = atomicAdd(&data.acc[index], 1.0);
        }}
    """

    values = run_atomic_compute(float32_atomic_device, shader_code, lanes)

    total_invocations = WORKGROUP_SIZE * WORKGROUPS
    base = total_invocations // lanes
    remainder = total_invocations % lanes
    expected = tuple(float(base + (1 if i < remainder else 0)) for i in range(lanes))
    assert values == expected
    assert sum(values) == float(total_invocations)
