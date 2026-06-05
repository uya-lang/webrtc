#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

#define UYA_RK1106_H264_ENCODER_STATUS_OK 0
#define UYA_RK1106_H264_ENCODER_STATUS_UNAVAILABLE -1
#define UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT -2
#define UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED -3
#define UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED -4
#define UYA_RK1106_H264_ENCODER_STATUS_BUFFER_TOO_SMALL -5

int uya_rk1106_h264_encoder_open(
    uint32_t width,
    uint32_t height,
    uint32_t fps,
    uint32_t bitrate,
    uint32_t gop,
    size_t *out_handle);

int uya_rk1106_h264_encoder_encode_i420(
    size_t handle,
    unsigned char *y_plane,
    size_t y_len,
    unsigned char *u_plane,
    size_t u_len,
    unsigned char *v_plane,
    size_t v_len,
    size_t stride_y,
    size_t stride_u,
    size_t stride_v,
    uint64_t pts_us,
    uint32_t force_idr,
    unsigned char *out_payload,
    size_t out_capacity,
    size_t *out_len,
    uint32_t *out_keyframe);

int uya_rk1106_h264_encoder_close(size_t handle);

#ifndef UYA_RK1106_H264_ENCODER_ENABLE_MPP

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/poll.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define UYA_HOST_H264_ACTIVE_TIMEOUT_MS 5000
#define UYA_HOST_H264_DRAIN_TIMEOUT_MS 25

typedef struct UyaHostFfmpegH264Encoder {
    pid_t pid;
    int stdin_fd;
    int stdout_fd;
    uint32_t width;
    uint32_t height;
    uint32_t fps;
    uint32_t bitrate;
    uint32_t gop;
    uint64_t frame_count;
    unsigned char *raw_frame;
    size_t raw_frame_len;
} UyaHostFfmpegH264Encoder;

static void uya_host_h264_close_fd(int *fd)
{
    if (fd && *fd >= 0) {
        close(*fd);
        *fd = -1;
    }
}

static int uya_host_h264_set_nonblocking(int fd)
{
    int flags;

    flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0)
        return -1;
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

static void uya_host_h264_log_failure(
    const char *reason,
    int status,
    int saved_errno,
    size_t write_cursor,
    size_t raw_frame_len,
    size_t out_len)
{
    fprintf(stderr,
        "rk1106_h264_encoder_shim: %s status=%d errno=%d write=%zu/%zu out=%zu\n",
        reason ? reason : "failed",
        status,
        saved_errno,
        write_cursor,
        raw_frame_len,
        out_len);
}

static int uya_host_h264_copy_i420_frame(
    UyaHostFfmpegH264Encoder *encoder,
    unsigned char *y_plane,
    size_t y_len,
    unsigned char *u_plane,
    size_t u_len,
    unsigned char *v_plane,
    size_t v_len,
    size_t stride_y,
    size_t stride_u,
    size_t stride_v)
{
    size_t cursor = 0;
    uint32_t row;

    if (!encoder || !encoder->raw_frame || !y_plane || !u_plane || !v_plane)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;
    if (stride_y < encoder->width || stride_u < encoder->width / 2u || stride_v < encoder->width / 2u)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;
    if (y_len < (size_t)stride_y * encoder->height ||
        u_len < (size_t)stride_u * (encoder->height / 2u) ||
        v_len < (size_t)stride_v * (encoder->height / 2u))
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;
    if (encoder->raw_frame_len < (size_t)encoder->width * encoder->height * 3u / 2u)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    for (row = 0; row < encoder->height; row++) {
        memcpy(encoder->raw_frame + cursor, y_plane + (size_t)row * stride_y, encoder->width);
        cursor += encoder->width;
    }
    for (row = 0; row < encoder->height / 2u; row++) {
        memcpy(encoder->raw_frame + cursor, u_plane + (size_t)row * stride_u, encoder->width / 2u);
        cursor += encoder->width / 2u;
    }
    for (row = 0; row < encoder->height / 2u; row++) {
        memcpy(encoder->raw_frame + cursor, v_plane + (size_t)row * stride_v, encoder->width / 2u);
        cursor += encoder->width / 2u;
    }
    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

static int uya_host_h264_write_frame_and_read_packet(
    UyaHostFfmpegH264Encoder *encoder,
    unsigned char *out_payload,
    size_t out_capacity,
    size_t *out_len)
{
    struct pollfd pfds[2];
    size_t write_cursor = 0;
    int saw_bytes = 0;

    if (!encoder || encoder->stdin_fd < 0 || encoder->stdout_fd < 0 ||
        !encoder->raw_frame || encoder->raw_frame_len == 0 ||
        !out_payload || out_capacity == 0 || !out_len)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    *out_len = 0;

    while (1) {
        int timeout_ms = (saw_bytes && write_cursor >= encoder->raw_frame_len) ?
            UYA_HOST_H264_DRAIN_TIMEOUT_MS :
            UYA_HOST_H264_ACTIVE_TIMEOUT_MS;
        int poll_rc;

        pfds[0].fd = encoder->stdout_fd;
        pfds[0].events = POLLIN | POLLHUP | POLLERR;
        pfds[0].revents = 0;
        pfds[1].fd = write_cursor < encoder->raw_frame_len ? encoder->stdin_fd : -1;
        pfds[1].events = POLLOUT | POLLHUP | POLLERR;
        pfds[1].revents = 0;

        poll_rc = poll(pfds, 2, timeout_ms);
        if (poll_rc < 0) {
            if (errno == EINTR)
                continue;
            uya_host_h264_log_failure(
                "poll failed",
                UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED,
                errno,
                write_cursor,
                encoder->raw_frame_len,
                *out_len);
            return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
        }
        if (poll_rc == 0) {
            if (!(saw_bytes && write_cursor >= encoder->raw_frame_len)) {
                uya_host_h264_log_failure(
                    "ffmpeg pipe timed out",
                    UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED,
                    0,
                    write_cursor,
                    encoder->raw_frame_len,
                    *out_len);
            }
            return (saw_bytes && write_cursor >= encoder->raw_frame_len) ?
                UYA_RK1106_H264_ENCODER_STATUS_OK :
                UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
        }
        if (pfds[0].revents & POLLIN) {
            while (1) {
                ssize_t read_count;
                if (*out_len >= out_capacity) {
                    uya_host_h264_log_failure(
                        "encoded output buffer too small",
                        UYA_RK1106_H264_ENCODER_STATUS_BUFFER_TOO_SMALL,
                        0,
                        write_cursor,
                        encoder->raw_frame_len,
                        *out_len);
                    return UYA_RK1106_H264_ENCODER_STATUS_BUFFER_TOO_SMALL;
                }
                read_count = read(
                    encoder->stdout_fd,
                    out_payload + *out_len,
                    out_capacity - *out_len);
                if (read_count < 0) {
                    int saved_errno = errno;
                    if (saved_errno == EINTR)
                        continue;
                    if (saved_errno == EAGAIN || saved_errno == EWOULDBLOCK || (saved_errno == 0 && saw_bytes))
                        break;
                    uya_host_h264_log_failure(
                        "ffmpeg stdout read failed",
                        UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED,
                        saved_errno,
                        write_cursor,
                        encoder->raw_frame_len,
                        *out_len);
                    return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
                }
                if (read_count == 0) {
                    if (!(saw_bytes && write_cursor >= encoder->raw_frame_len)) {
                        uya_host_h264_log_failure(
                            "ffmpeg stdout closed early",
                            UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED,
                            0,
                            write_cursor,
                            encoder->raw_frame_len,
                            *out_len);
                    }
                    return (saw_bytes && write_cursor >= encoder->raw_frame_len) ?
                        UYA_RK1106_H264_ENCODER_STATUS_OK :
                        UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
                }
                *out_len += (size_t)read_count;
                saw_bytes = 1;
            }
        }
        if ((pfds[0].revents & (POLLHUP | POLLERR)) && !saw_bytes) {
            uya_host_h264_log_failure(
                "ffmpeg stdout hangup before output",
                UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED,
                0,
                write_cursor,
                encoder->raw_frame_len,
                *out_len);
            return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
        }
        if ((pfds[0].revents & (POLLHUP | POLLERR)) && saw_bytes && write_cursor >= encoder->raw_frame_len)
            return UYA_RK1106_H264_ENCODER_STATUS_OK;
        if (pfds[1].revents & (POLLHUP | POLLERR)) {
            uya_host_h264_log_failure(
                "ffmpeg stdin hangup",
                UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED,
                0,
                write_cursor,
                encoder->raw_frame_len,
                *out_len);
            return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
        }
        if (pfds[1].revents & POLLOUT) {
            size_t remaining = encoder->raw_frame_len - write_cursor;
            size_t chunk = remaining > 65536u ? 65536u : remaining;
            ssize_t written = write(encoder->stdin_fd, encoder->raw_frame + write_cursor, chunk);
            if (written < 0) {
                if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)
                    continue;
                uya_host_h264_log_failure(
                    "ffmpeg stdin write failed",
                    UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED,
                    errno,
                    write_cursor,
                    encoder->raw_frame_len,
                    *out_len);
                return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
            }
            if (written == 0) {
                uya_host_h264_log_failure(
                    "ffmpeg stdin write returned zero",
                    UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED,
                    0,
                    write_cursor,
                    encoder->raw_frame_len,
                    *out_len);
                return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
            }
            write_cursor += (size_t)written;
        }
    }
}

int uya_rk1106_h264_encoder_open(
    uint32_t width,
    uint32_t height,
    uint32_t fps,
    uint32_t bitrate,
    uint32_t gop,
    size_t *out_handle)
{
    UyaHostFfmpegH264Encoder *encoder;
    int stdin_pipe[2] = {-1, -1};
    int stdout_pipe[2] = {-1, -1};
    char size_arg[32];
    char fps_arg[16];
    char bitrate_arg[32];
    char gop_arg[16];
    pid_t pid;

    if (out_handle)
        *out_handle = 0;
    if (!out_handle || width == 0 || height == 0 || fps == 0 || bitrate == 0 || gop == 0 ||
        (width & 1u) || (height & 1u))
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    encoder = (UyaHostFfmpegH264Encoder *)calloc(1, sizeof(*encoder));
    if (!encoder)
        return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
    encoder->pid = -1;
    encoder->stdin_fd = -1;
    encoder->stdout_fd = -1;
    encoder->width = width;
    encoder->height = height;
    encoder->fps = fps;
    encoder->bitrate = bitrate;
    encoder->gop = gop;
    encoder->raw_frame_len = (size_t)width * height * 3u / 2u;
    encoder->raw_frame = (unsigned char *)malloc(encoder->raw_frame_len);
    if (!encoder->raw_frame)
        goto fail;

    if (pipe(stdin_pipe) != 0 || pipe(stdout_pipe) != 0)
        goto fail;

    snprintf(size_arg, sizeof(size_arg), "%ux%u", width, height);
    snprintf(fps_arg, sizeof(fps_arg), "%u", fps);
    snprintf(bitrate_arg, sizeof(bitrate_arg), "%u", bitrate);
    snprintf(gop_arg, sizeof(gop_arg), "%u", gop);

    pid = fork();
    if (pid < 0)
        goto fail;
    if (pid == 0) {
        int null_fd;
        dup2(stdin_pipe[0], STDIN_FILENO);
        dup2(stdout_pipe[1], STDOUT_FILENO);
        null_fd = open("/dev/null", O_WRONLY);
        if (null_fd >= 0) {
            dup2(null_fd, STDERR_FILENO);
            close(null_fd);
        }
        close(stdin_pipe[0]);
        close(stdin_pipe[1]);
        close(stdout_pipe[0]);
        close(stdout_pipe[1]);
        execlp(
            "ffmpeg",
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "yuv420p",
            "-s:v", size_arg,
            "-r", fps_arg,
            "-i", "pipe:0",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-profile:v", "baseline",
            "-bf", "0",
            "-g", gop_arg,
            "-keyint_min", gop_arg,
            "-b:v", bitrate_arg,
            "-x264-params", "repeat-headers=1:scenecut=0",
            "-flush_packets", "1",
            "-f", "h264",
            "pipe:1",
            (char *)NULL);
        _exit(127);
    }

    encoder->pid = pid;
    encoder->stdin_fd = stdin_pipe[1];
    encoder->stdout_fd = stdout_pipe[0];
    stdin_pipe[1] = -1;
    stdout_pipe[0] = -1;
    close(stdin_pipe[0]);
    close(stdout_pipe[1]);
    stdin_pipe[0] = -1;
    stdout_pipe[1] = -1;

    (void)signal(SIGPIPE, SIG_IGN);
    if (uya_host_h264_set_nonblocking(encoder->stdin_fd) != 0 ||
        uya_host_h264_set_nonblocking(encoder->stdout_fd) != 0)
        goto fail;

    *out_handle = (size_t)encoder;
    return UYA_RK1106_H264_ENCODER_STATUS_OK;

fail:
    uya_host_h264_close_fd(&stdin_pipe[0]);
    uya_host_h264_close_fd(&stdin_pipe[1]);
    uya_host_h264_close_fd(&stdout_pipe[0]);
    uya_host_h264_close_fd(&stdout_pipe[1]);
    if (encoder) {
        if (encoder->pid > 0) {
            kill(encoder->pid, SIGTERM);
            waitpid(encoder->pid, NULL, 0);
        }
        uya_host_h264_close_fd(&encoder->stdin_fd);
        uya_host_h264_close_fd(&encoder->stdout_fd);
        free(encoder->raw_frame);
        free(encoder);
    }
    return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
}

int uya_rk1106_h264_encoder_encode_i420(
    size_t handle,
    unsigned char *y_plane,
    size_t y_len,
    unsigned char *u_plane,
    size_t u_len,
    unsigned char *v_plane,
    size_t v_len,
    size_t stride_y,
    size_t stride_u,
    size_t stride_v,
    uint64_t pts_us,
    uint32_t force_idr,
    unsigned char *out_payload,
    size_t out_capacity,
    size_t *out_len,
    uint32_t *out_keyframe)
{
    UyaHostFfmpegH264Encoder *encoder = (UyaHostFfmpegH264Encoder *)handle;
    int status;

    (void)pts_us;
    if (out_len)
        *out_len = 0;
    if (out_keyframe)
        *out_keyframe = 0;
    if (!encoder || encoder->stdin_fd < 0 || encoder->stdout_fd < 0 || !out_payload || out_capacity == 0 || !out_len || !out_keyframe)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    status = uya_host_h264_copy_i420_frame(
        encoder,
        y_plane,
        y_len,
        u_plane,
        u_len,
        v_plane,
        v_len,
        stride_y,
        stride_u,
        stride_v);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return status;

    status = uya_host_h264_write_frame_and_read_packet(encoder, out_payload, out_capacity, out_len);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) {
        uya_host_h264_log_failure(
            "host ffmpeg h264 encode/read failed",
            status,
            0,
            0,
            encoder->raw_frame_len,
            out_len ? *out_len : 0);
        return status;
    }
    if (*out_len == 0) {
        uya_host_h264_log_failure(
            "host ffmpeg returned empty h264 payload",
            UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED,
            0,
            encoder->raw_frame_len,
            encoder->raw_frame_len,
            0);
        return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
    }

    *out_keyframe = (force_idr || encoder->frame_count == 0 ||
        (encoder->gop && (encoder->frame_count % encoder->gop) == 0)) ? 1u : 0u;
    encoder->frame_count++;
    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

int uya_rk1106_h264_encoder_close(size_t handle)
{
    UyaHostFfmpegH264Encoder *encoder = (UyaHostFfmpegH264Encoder *)handle;

    if (!encoder)
        return UYA_RK1106_H264_ENCODER_STATUS_OK;

    uya_host_h264_close_fd(&encoder->stdin_fd);
    uya_host_h264_close_fd(&encoder->stdout_fd);
    if (encoder->pid > 0)
        waitpid(encoder->pid, NULL, 0);
    free(encoder->raw_frame);
    memset(encoder, 0, sizeof(*encoder));
    free(encoder);
    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

#else

#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "rk_mpi.h"
#include "rk_mpi_cmd.h"
#include "rk_venc_cfg.h"
#include "rk_venc_rc.h"
#include "mpp_buffer.h"
#include "mpp_frame.h"
#include "mpp_packet.h"

typedef struct UyaRk1106H264Encoder {
    MppCtx ctx;
    MppApi *mpi;
    MppEncCfg cfg;
    MppBufferGroup buffer_group;
    MppBuffer frame_buffer;
    unsigned char *frame_ptr;
    uint32_t width;
    uint32_t height;
    uint32_t hor_stride;
    uint32_t ver_stride;
    uint32_t fps;
    uint32_t bitrate;
    uint32_t gop;
    uint64_t frame_count;
    size_t frame_size;
} UyaRk1106H264Encoder;

static uint32_t uya_rk1106_h264_align16(uint32_t value)
{
    return (value + 15u) & ~15u;
}

static int uya_rk1106_h264_copy_packet(
    MppPacket packet,
    unsigned char *out_payload,
    size_t out_capacity,
    size_t *cursor)
{
    void *pos;
    size_t len;

    if (!packet || !out_payload || !cursor)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    pos = mpp_packet_get_pos(packet);
    if (!pos)
        pos = mpp_packet_get_data(packet);
    len = mpp_packet_get_length(packet);
    if (len == 0)
        return UYA_RK1106_H264_ENCODER_STATUS_OK;
    if (*cursor > out_capacity || len > out_capacity - *cursor)
        return UYA_RK1106_H264_ENCODER_STATUS_BUFFER_TOO_SMALL;
    memcpy(out_payload + *cursor, pos, len);
    *cursor += len;
    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

static int uya_rk1106_h264_set_s32(MppEncCfg cfg, const char *name, int32_t value)
{
    return mpp_enc_cfg_set_s32(cfg, name, value) == MPP_OK ?
        UYA_RK1106_H264_ENCODER_STATUS_OK :
        UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
}

static int uya_rk1106_h264_encoder_apply_cfg(UyaRk1106H264Encoder *encoder)
{
    uint32_t bps_min;
    uint32_t bps_max;
    int status;

    if (!encoder || !encoder->cfg)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    bps_min = encoder->bitrate * 15u / 16u;
    bps_max = encoder->bitrate * 17u / 16u;
    if (bps_min == 0)
        bps_min = encoder->bitrate;
    if (bps_max < encoder->bitrate)
        bps_max = encoder->bitrate;

    status = uya_rk1106_h264_set_s32(encoder->cfg, "prep:width", (int32_t)encoder->width);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "prep:height", (int32_t)encoder->height);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "prep:hor_stride", (int32_t)encoder->hor_stride);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "prep:ver_stride", (int32_t)encoder->ver_stride);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "prep:format", MPP_FMT_YUV420SP);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;

    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:mode", MPP_ENC_RC_MODE_CBR);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:bps_target", (int32_t)encoder->bitrate);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:bps_min", (int32_t)bps_min);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:bps_max", (int32_t)bps_max);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:fps_in_flex", 0);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:fps_in_num", (int32_t)encoder->fps);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:fps_in_denorm", 1);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:fps_out_flex", 0);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:fps_out_num", (int32_t)encoder->fps);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:fps_out_denorm", 1);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "rc:gop", (int32_t)encoder->gop);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;

    status = uya_rk1106_h264_set_s32(encoder->cfg, "codec:type", MPP_VIDEO_CodingAVC);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "h264:profile", 66);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "h264:level", 31);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "h264:cabac_en", 0);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;
    status = uya_rk1106_h264_set_s32(encoder->cfg, "h264:cabac_idc", 0);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) return status;

    return encoder->mpi->control(encoder->ctx, MPP_ENC_SET_CFG, encoder->cfg) == MPP_OK ?
        UYA_RK1106_H264_ENCODER_STATUS_OK :
        UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
}

int uya_rk1106_h264_encoder_close(size_t handle)
{
    UyaRk1106H264Encoder *encoder = (UyaRk1106H264Encoder *)handle;

    if (!encoder)
        return UYA_RK1106_H264_ENCODER_STATUS_OK;

    if (encoder->mpi && encoder->ctx)
        encoder->mpi->reset(encoder->ctx);
    if (encoder->frame_buffer)
        mpp_buffer_put(encoder->frame_buffer);
    if (encoder->buffer_group)
        mpp_buffer_group_put(encoder->buffer_group);
    if (encoder->cfg)
        mpp_enc_cfg_deinit(encoder->cfg);
    if (encoder->ctx)
        mpp_destroy(encoder->ctx);
    memset(encoder, 0, sizeof(*encoder));
    free(encoder);
    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

int uya_rk1106_h264_encoder_open(
    uint32_t width,
    uint32_t height,
    uint32_t fps,
    uint32_t bitrate,
    uint32_t gop,
    size_t *out_handle)
{
    UyaRk1106H264Encoder *encoder;
    int64_t timeout_ms = 1000;
    int status;

    if (out_handle)
        *out_handle = 0;
    if (!out_handle || width == 0 || height == 0 || fps == 0 || bitrate == 0 || gop == 0 ||
        (width & 1u) || (height & 1u))
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    encoder = (UyaRk1106H264Encoder *)calloc(1, sizeof(*encoder));
    if (!encoder)
        return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;

    encoder->width = width;
    encoder->height = height;
    encoder->hor_stride = uya_rk1106_h264_align16(width);
    encoder->ver_stride = uya_rk1106_h264_align16(height);
    encoder->fps = fps;
    encoder->bitrate = bitrate;
    encoder->gop = gop;
    encoder->frame_size = (size_t)encoder->hor_stride * encoder->ver_stride * 3u / 2u;

    if (mpp_create(&encoder->ctx, &encoder->mpi) != MPP_OK || !encoder->ctx || !encoder->mpi)
        goto fail;
    if (mpp_init(encoder->ctx, MPP_CTX_ENC, MPP_VIDEO_CodingAVC) != MPP_OK)
        goto fail;
    (void)encoder->mpi->control(encoder->ctx, MPP_SET_OUTPUT_TIMEOUT, &timeout_ms);

    if (mpp_enc_cfg_init(&encoder->cfg) != MPP_OK || !encoder->cfg)
        goto fail;
    if (encoder->mpi->control(encoder->ctx, MPP_ENC_GET_CFG, encoder->cfg) != MPP_OK)
        goto fail;
    status = uya_rk1106_h264_encoder_apply_cfg(encoder);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK)
        goto fail;

    if (mpp_buffer_group_get_internal(&encoder->buffer_group, MPP_BUFFER_TYPE_DRM) != MPP_OK)
        goto fail;
    if (mpp_buffer_get(encoder->buffer_group, &encoder->frame_buffer, encoder->frame_size) != MPP_OK)
        goto fail;
    encoder->frame_ptr = (unsigned char *)mpp_buffer_get_ptr(encoder->frame_buffer);
    if (!encoder->frame_ptr)
        goto fail;

    *out_handle = (size_t)encoder;
    return UYA_RK1106_H264_ENCODER_STATUS_OK;

fail:
    uya_rk1106_h264_encoder_close((size_t)encoder);
    return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
}

static int uya_rk1106_h264_copy_i420_to_nv12(
    UyaRk1106H264Encoder *encoder,
    unsigned char *y_plane,
    size_t y_len,
    unsigned char *u_plane,
    size_t u_len,
    unsigned char *v_plane,
    size_t v_len,
    size_t stride_y,
    size_t stride_u,
    size_t stride_v)
{
    uint32_t row;
    uint32_t col;
    unsigned char *dst_y;
    unsigned char *dst_uv;

    if (!encoder || !encoder->frame_ptr || !y_plane || !u_plane || !v_plane)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;
    if (stride_y < encoder->width || stride_u < encoder->width / 2u || stride_v < encoder->width / 2u)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;
    if (y_len < (size_t)stride_y * encoder->height ||
        u_len < (size_t)stride_u * (encoder->height / 2u) ||
        v_len < (size_t)stride_v * (encoder->height / 2u))
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    memset(encoder->frame_ptr, 0, encoder->frame_size);
    dst_y = encoder->frame_ptr;
    dst_uv = encoder->frame_ptr + (size_t)encoder->hor_stride * encoder->ver_stride;

    for (row = 0; row < encoder->height; row++)
        memcpy(dst_y + (size_t)row * encoder->hor_stride,
               y_plane + (size_t)row * stride_y,
               encoder->width);

    for (row = 0; row < encoder->height / 2u; row++) {
        unsigned char *dst = dst_uv + (size_t)row * encoder->hor_stride;
        unsigned char *src_u = u_plane + (size_t)row * stride_u;
        unsigned char *src_v = v_plane + (size_t)row * stride_v;
        for (col = 0; col < encoder->width / 2u; col++) {
            dst[col * 2u] = src_u[col];
            dst[col * 2u + 1u] = src_v[col];
        }
    }

    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

int uya_rk1106_h264_encoder_encode_i420(
    size_t handle,
    unsigned char *y_plane,
    size_t y_len,
    unsigned char *u_plane,
    size_t u_len,
    unsigned char *v_plane,
    size_t v_len,
    size_t stride_y,
    size_t stride_u,
    size_t stride_v,
    uint64_t pts_us,
    uint32_t force_idr,
    unsigned char *out_payload,
    size_t out_capacity,
    size_t *out_len,
    uint32_t *out_keyframe)
{
    UyaRk1106H264Encoder *encoder = (UyaRk1106H264Encoder *)handle;
    MppFrame frame = NULL;
    MppPacket packet = NULL;
    size_t cursor = 0;
    uint32_t keyframe;
    int status;
    int tries;

    if (out_len)
        *out_len = 0;
    if (out_keyframe)
        *out_keyframe = 0;
    if (!encoder || !encoder->ctx || !encoder->mpi || !out_payload || out_capacity == 0 || !out_len || !out_keyframe)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    status = uya_rk1106_h264_copy_i420_to_nv12(
        encoder,
        y_plane,
        y_len,
        u_plane,
        u_len,
        v_plane,
        v_len,
        stride_y,
        stride_u,
        stride_v);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return status;

    keyframe = force_idr || encoder->frame_count == 0 || (encoder->gop && (encoder->frame_count % encoder->gop) == 0);
    if (keyframe)
        (void)encoder->mpi->control(encoder->ctx, MPP_ENC_SET_IDR_FRAME, NULL);

    if (mpp_frame_init(&frame) != MPP_OK || !frame)
        return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
    mpp_frame_set_width(frame, encoder->width);
    mpp_frame_set_height(frame, encoder->height);
    mpp_frame_set_hor_stride(frame, encoder->hor_stride);
    mpp_frame_set_ver_stride(frame, encoder->ver_stride);
    mpp_frame_set_fmt(frame, MPP_FMT_YUV420SP);
    mpp_frame_set_pts(frame, (int64_t)pts_us);
    mpp_frame_set_buffer(frame, encoder->frame_buffer);

    if (encoder->mpi->encode_put_frame(encoder->ctx, frame) != MPP_OK) {
        mpp_frame_deinit(&frame);
        return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
    }
    mpp_frame_deinit(&frame);

    for (tries = 0; tries < 20 && !packet; tries++) {
        if (encoder->mpi->encode_get_packet(encoder->ctx, &packet) != MPP_OK)
            return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
        if (!packet)
            usleep(1000);
    }
    if (!packet)
        return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;

    if (keyframe) {
        MppPacket header = NULL;
        if (encoder->mpi->control(encoder->ctx, MPP_ENC_GET_HDR_SYNC, &header) == MPP_OK && header) {
            status = uya_rk1106_h264_copy_packet(header, out_payload, out_capacity, &cursor);
            mpp_packet_deinit(&header);
            if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) {
                mpp_packet_deinit(&packet);
                return status;
            }
        }
    }

    status = uya_rk1106_h264_copy_packet(packet, out_payload, out_capacity, &cursor);
    mpp_packet_deinit(&packet);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return status;
    if (cursor == 0)
        return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;

    encoder->frame_count++;
    *out_len = cursor;
    *out_keyframe = keyframe ? 1u : 0u;
    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

#endif
