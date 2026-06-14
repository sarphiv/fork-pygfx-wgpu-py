from textwrap import dedent

from codegen.hparser import HParser


def test_parse_enum_with_braces_in_c_comment():
    source = dedent(
        """
        typedef enum WGPUNativeFeature {
            WGPUNativeFeature_ShaderInt64 = 0x00030026,
            /*
             * WGSL examples in header comments can contain braces:
             * fn main() { if (true) { } }
             */
            WGPUNativeFeature_ShaderFloat32Atomic = 0x00030027,
            WGPUNativeFeature_Force32 = 0x7FFFFFFF
        } WGPUNativeFeature;

        typedef struct WGPUExample {
            /* Comments can also mention { and } near struct fields. */
            int value;
        } WGPUExample;
        """
    )
    parser = HParser(source)
    parser.flags = {}
    parser.enums = {}
    parser.structs = {}
    parser.functions = {}

    parser._parse_from_h()

    assert parser.enums["NativeFeature"]["ShaderFloat32Atomic"] == 0x00030027
    assert parser.structs["WGPUExample"] == {"value": "int"}
