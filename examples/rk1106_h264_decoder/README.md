# RK1106 hardware H264 decoder

This example builds a small Uya-facing RK1106/RV1103B H264 hardware decoder.
It uses the Rockchip MPP decoder through `src/rk1106_h264_decoder_shim.c` and
exposes the stable Uya wrapper in `src/webrtc/media/rk1106_h264_decoder.uya`.

The output file is tight NV12:

```text
Y plane:  width * height bytes
UV plane: width * height / 2 bytes
```

## Build

```sh
make -C examples/rk1106_h264_decoder package
```

The package is written to:

```sh
examples/rk1106_h264_decoder/build/rk1106-h264-decoder
```

Copy that directory to the board, for example:

```sh
scp -r examples/rk1106_h264_decoder/build/rk1106-h264-decoder root@BOARD_IP:/userdata/
```

## Run on RK1106/RV1103B

```sh
cd /userdata/rk1106-h264-decoder
LD_LIBRARY_PATH="$PWD/lib:${LD_LIBRARY_PATH:-}" \
./webrtc_rk1106_h264_decoder \
    --input /userdata/input.h264 \
    --output /userdata/output.nv12
```

Optional limits:

```sh
./webrtc_rk1106_h264_decoder \
    --input /userdata/input.h264 \
    --output /userdata/output.nv12 \
    --max-frames 30 \
    --chunk-bytes 65536
```

By default the decoder enables MPP `base:split_parse`, so the input can be an
Annex-B elementary stream rather than perfectly frame-split packets. Use
`--no-split-parse` only when the input packets are already frame aligned.

## Host smoke build

Host builds compile the same Uya CLI and the shim fallback, but do not link MPP:

```sh
make -C examples/rk1106_h264_decoder host
examples/rk1106_h264_decoder/build/webrtc_rk1106_h264_decoder_host --help
```

The host binary prints `decoder unavailable in this build` for real decode work.
It exists to catch Uya/C ABI and CLI build regressions without requiring RK
hardware.
