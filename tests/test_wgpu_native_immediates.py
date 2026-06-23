import struct

import pytest
import wgpu

from testutils import can_use_wgpu_lib
from wgpu.backends.wgpu_native._mappings import enum_str2int


FEATURE = "immediates"


if not can_use_wgpu_lib:
    pytest.skip("Skipping tests that need the wgpu lib", allow_module_level=True)
elif FEATURE not in enum_str2int["NativeFeature"]:
    pytest.skip(
        "Skipping immediates tests because the pinned wgpu-native headers do not expose this extension",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def immediates_device():
    errors = []
    for adapter in wgpu.gpu.enumerate_adapters_sync():
        if FEATURE not in adapter.features:
            continue
        if adapter.limits.get("max-immediate-size", 0) < 8:
            continue
        try:
            device = adapter.request_device_sync(
                required_features=[FEATURE],
                required_limits={"max-immediate-size": 8},
            )
        except Exception as err:
            errors.append(f"{adapter.summary}: {err}")
        else:
            assert FEATURE in device.features
            assert device.limits["max-immediate-size"] >= 8
            return device

    message = f"No usable wgpu adapter reports {FEATURE!r} with max-immediate-size >= 8"
    if errors:
        message += ". Device request errors: " + "; ".join(errors)
    pytest.skip(message)


def test_compute_pass_set_immediates(immediates_device):
    device = immediates_device
    shader = device.create_shader_module(
        code="""
            @group(0) @binding(0)
            var<storage, read_write> output: array<u32>;

            struct Immediates {
                value: u32,
            }
            var<immediate> immediates: Immediates;

            @compute @workgroup_size(1)
            fn main() {
                output[0] = immediates.value;
            }
        """
    )

    buffer = device.create_buffer(
        size=4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    bind_group_layout = device.create_bind_group_layout(
        entries=[
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {"type": wgpu.BufferBindingType.storage},
            }
        ]
    )
    pipeline_layout = device.create_pipeline_layout(
        bind_group_layouts=[bind_group_layout],
        immediate_size=4,
    )
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={"module": shader, "entry_point": "main"},
    )
    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[{"binding": 0, "resource": {"buffer": buffer}}],
    )

    expected = 0xA1B2C3D4
    encoder = device.create_command_encoder()
    compute_pass = encoder.begin_compute_pass()
    compute_pass.set_pipeline(pipeline)
    compute_pass.set_bind_group(0, bind_group)
    compute_pass.set_immediates(0, struct.pack("I", expected))
    compute_pass.dispatch_workgroups(1)
    compute_pass.end()
    device.queue.submit([encoder.finish()])

    data = device.queue.read_buffer(buffer)
    assert struct.unpack("I", bytes(data))[0] == expected


def test_compute_pass_set_immediates_offset_and_data_slice(immediates_device):
    device = immediates_device
    shader = device.create_shader_module(
        code="""
            @group(0) @binding(0)
            var<storage, read_write> output: array<u32>;

            struct Immediates {
                padding: u32,
                value: u32,
            }
            var<immediate> immediates: Immediates;

            @compute @workgroup_size(1)
            fn main() {
                output[0] = immediates.value;
            }
        """
    )

    buffer = device.create_buffer(
        size=4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    bind_group_layout = device.create_bind_group_layout(
        entries=[
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {"type": wgpu.BufferBindingType.storage},
            }
        ]
    )
    pipeline_layout = device.create_pipeline_layout(
        bind_group_layouts=[bind_group_layout],
        immediate_size=8,
    )
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={"module": shader, "entry_point": "main"},
    )
    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[{"binding": 0, "resource": {"buffer": buffer}}],
    )

    expected = 0xC001D00D
    payload = struct.pack("II", 0, expected)
    encoder = device.create_command_encoder()
    compute_pass = encoder.begin_compute_pass()
    compute_pass.set_pipeline(pipeline)
    compute_pass.set_bind_group(0, bind_group)
    compute_pass.set_immediates(4, payload, size_in_bytes=4, data_offset=4)
    compute_pass.dispatch_workgroups(1)
    compute_pass.end()
    device.queue.submit([encoder.finish()])

    data = device.queue.read_buffer(buffer)
    assert struct.unpack("I", bytes(data))[0] == expected


def test_render_pass_set_immediates(immediates_device):
    result = run_render_immediates(immediates_device, use_bundle=False)
    assert result == 0x1234ABCD


def test_render_bundle_set_immediates(immediates_device):
    result = run_render_immediates(immediates_device, use_bundle=True)
    assert result == 0x1234ABCD


def test_bad_set_immediates(immediates_device):
    device = immediates_device
    encoder = device.create_command_encoder()
    compute_pass = encoder.begin_compute_pass()

    with pytest.raises(ValueError, match="offset"):
        compute_pass.set_immediates(-1, b"\x00\x00\x00\x00")

    with pytest.raises(ValueError, match="data_offset"):
        compute_pass.set_immediates(0, b"\x00\x00\x00\x00", data_offset=5)

    with pytest.raises(ValueError, match="size_in_bytes"):
        compute_pass.set_immediates(0, b"\x00\x00\x00\x00", size_in_bytes=5)

    with pytest.raises(ValueError, match="not contiguous"):
        compute_pass.set_immediates(0, memoryview(bytearray(8))[::2])

    compute_pass.end()


def run_render_immediates(device, *, use_bundle):
    shader = device.create_shader_module(
        code="""
            @group(0) @binding(0)
            var<storage, read_write> output: array<u32>;

            struct Immediates {
                value: u32,
            }
            var<immediate> immediates: Immediates;

            @vertex
            fn vs_main() -> @builtin(position) vec4f {
                return vec4f(0.0, 0.0, 0.0, 1.0);
            }

            @fragment
            fn fs_main() -> @location(0) vec4f {
                output[0] = immediates.value;
                return vec4f(0.0, 0.0, 0.0, 1.0);
            }
        """
    )

    texture = device.create_texture(
        size=(1, 1, 1),
        format=wgpu.TextureFormat.rgba8unorm,
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
    )
    buffer = device.create_buffer(
        size=4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    bind_group_layout = device.create_bind_group_layout(
        entries=[
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.FRAGMENT,
                "buffer": {"type": wgpu.BufferBindingType.storage},
            }
        ]
    )
    pipeline_layout = device.create_pipeline_layout(
        bind_group_layouts=[bind_group_layout],
        immediate_size=4,
    )
    pipeline = device.create_render_pipeline(
        layout=pipeline_layout,
        vertex={"module": shader, "entry_point": "vs_main"},
        fragment={
            "module": shader,
            "entry_point": "fs_main",
            "targets": [{"format": texture.format}],
        },
        primitive={"topology": "point-list"},
    )
    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[{"binding": 0, "resource": {"buffer": buffer}}],
    )
    render_pass_descriptor = {
        "color_attachments": [
            {
                "view": texture.create_view(),
                "clear_value": (0, 0, 0, 0),
                "load_op": "clear",
                "store_op": "store",
            }
        ]
    }

    expected = 0x1234ABCD
    if use_bundle:
        bundle_encoder = device.create_render_bundle_encoder(
            color_formats=[texture.format],
        )
        bundle_encoder.set_pipeline(pipeline)
        bundle_encoder.set_bind_group(0, bind_group)
        bundle_encoder.set_immediates(0, struct.pack("I", expected))
        bundle_encoder.draw(1)
        bundle = bundle_encoder.finish()

    encoder = device.create_command_encoder()
    render_pass = encoder.begin_render_pass(**render_pass_descriptor)
    if use_bundle:
        render_pass.execute_bundles([bundle])
    else:
        render_pass.set_pipeline(pipeline)
        render_pass.set_bind_group(0, bind_group)
        render_pass.set_immediates(0, struct.pack("I", expected))
        render_pass.draw(1)
    render_pass.end()
    device.queue.submit([encoder.finish()])

    data = device.queue.read_buffer(buffer)
    return struct.unpack("I", bytes(data))[0]
