/*
 * Standalone MPP encoder probe.
 *
 * This links ONLY the RK MPP encoder shim (rk1106_h264_encoder_shim.c built
 * with UYA_RK1106_H264_ENCODER_ENABLE_MPP) against the board's libc — no Uya
 * runtime, no custom libc, no symbol hiding tricks. It simply opens an H264
 * encoder channel (which drives mpp_create + mpp_init -> VCODEC_CHAN_CREATE).
 *
 * If this probe also fails with EFAULT / "vcodec_attr define is diff from
 * user", the problem is a libmpp<->kernel ABI mismatch in the board firmware,
 * independent of our sender binary. If it succeeds, the failure is specific to
 * the Uya sender's process environment.
 */

#include <stdlib.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

int uya_rk1106_h264_encoder_open(
    uint32_t width,
    uint32_t height,
    uint32_t fps,
    uint32_t bitrate,
    uint32_t gop,
    size_t *out_handle);

int uya_rk1106_h264_encoder_close(size_t handle);

int main(int argc, char **argv)
{
    uint32_t width = 320;
    uint32_t height = 180;
    uint32_t fps = 10;
    uint32_t bitrate = 1000000;
    uint32_t gop = 30;
    size_t handle = 0;
    int status;

    if (argc >= 3) {
        width = (uint32_t)atoi(argv[1]);
        height = (uint32_t)atoi(argv[2]);
    }
    if (argc >= 4)
        fps = (uint32_t)atoi(argv[3]);
    if (argc >= 5)
        bitrate = (uint32_t)atoi(argv[4]);
    if (argc >= 6)
        gop = (uint32_t)atoi(argv[5]);

    fprintf(stderr, "mpp_probe: opening encoder %ux%u %ufps %ubps gop=%u\n",
        width, height, fps, bitrate, gop);

    status = uya_rk1106_h264_encoder_open(width, height, fps, bitrate, gop, &handle);
    if (status != 0) {
        fprintf(stderr, "mpp_probe: encoder open FAILED status=%d\n", status);
        return 1;
    }

    fprintf(stderr, "mpp_probe: encoder open OK handle=%zu\n", handle);
    uya_rk1106_h264_encoder_close(handle);
    fprintf(stderr, "mpp_probe: encoder closed OK\n");
    return 0;
}
