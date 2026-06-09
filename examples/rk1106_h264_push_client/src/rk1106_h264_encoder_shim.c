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
        pfds[1].events = write_cursor < encoder->raw_frame_len ? POLLOUT | POLLERR | POLLHUP : 0;
        pfds[1].revents = 0;

        poll_rc = poll(pfds, 2, timeout_ms);
        if (poll_rc < 0) {
            uya_host_h264_log_failure("poll failed", poll_rc, errno, write_cursor, encoder->raw_frame_len, *out_len);
            return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
        }
        if (poll_rc == 0) {
            uya_host_h264_log_failure("poll timeout", poll_rc, 0, write_cursor, encoder->raw_frame_len, *out_len);
            return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
        }

        if (pfds[1].fd >= 0 && (pfds[1].revents & POLLOUT)) {
            ssize_t wrote = write(encoder->stdin_fd, encoder->raw_frame + write_cursor, encoder->raw_frame_len - write_cursor);
            if (wrote > 0) {
                write_cursor += (size_t)wrote;
            } else if (wrote < 0 && errno != EAGAIN && errno != EINTR) {
                uya_host_h264_log_failure("write failed", (int)wrote, errno, write_cursor, encoder->raw_frame_len, *out_len);
                return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
            }
        }

        if (pfds[0].revents & POLLIN) {
            ssize_t got = read(encoder->stdout_fd, out_payload + *out_len, out_capacity - *out_len);
            if (got > 0) {
                *out_len += (size_t)got;
                saw_bytes = 1;
                if (*out_len >= out_capacity)
                    return UYA_RK1106_H264_ENCODER_STATUS_BUFFER_TOO_SMALL;
                continue;
            }
            if (got < 0 && errno != EAGAIN && errno != EINTR) {
                uya_host_h264_log_failure("read failed", (int)got, errno, write_cursor, encoder->raw_frame_len, *out_len);
                return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
            }
        }

        if ((pfds[0].revents & (POLLHUP | POLLERR)) && saw_bytes)
            break;
        if (saw_bytes && write_cursor >= encoder->raw_frame_len)
            break;
    }

    return *out_len > 0 ? UYA_RK1106_H264_ENCODER_STATUS_OK : UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
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
    pid_t pid;
    char size_arg[64];
    char fps_arg[32];
    char bitrate_arg[32];
    char gop_arg[32];

    if (out_handle)
        *out_handle = 0;
    if (!out_handle || width == 0 || height == 0 || fps == 0 || bitrate == 0 || gop == 0)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    encoder = (UyaHostFfmpegH264Encoder *)calloc(1, sizeof(*encoder));
    if (!encoder)
        return UYA_RK1106_H264_ENCODER_STATUS_UNAVAILABLE;

    encoder->width = width;
    encoder->height = height;
    encoder->fps = fps;
    encoder->bitrate = bitrate;
    encoder->gop = gop;
    encoder->stdin_fd = -1;
    encoder->stdout_fd = -1;
    encoder->raw_frame_len = (size_t)width * height * 3u / 2u;
    encoder->raw_frame = (unsigned char *)malloc(encoder->raw_frame_len);
    if (!encoder->raw_frame) {
        free(encoder);
        return UYA_RK1106_H264_ENCODER_STATUS_UNAVAILABLE;
    }

    if (pipe(stdin_pipe) != 0 || pipe(stdout_pipe) != 0) {
        uya_host_h264_close_fd(&stdin_pipe[0]);
        uya_host_h264_close_fd(&stdin_pipe[1]);
        uya_host_h264_close_fd(&stdout_pipe[0]);
        uya_host_h264_close_fd(&stdout_pipe[1]);
        free(encoder->raw_frame);
        free(encoder);
        return UYA_RK1106_H264_ENCODER_STATUS_UNAVAILABLE;
    }

    snprintf(size_arg, sizeof(size_arg), "%ux%u", width, height);
    snprintf(fps_arg, sizeof(fps_arg), "%u", fps);
    snprintf(bitrate_arg, sizeof(bitrate_arg), "%u", bitrate);
    snprintf(gop_arg, sizeof(gop_arg), "%u", gop);

    pid = fork();
    if (pid < 0) {
        uya_host_h264_close_fd(&stdin_pipe[0]);
        uya_host_h264_close_fd(&stdin_pipe[1]);
        uya_host_h264_close_fd(&stdout_pipe[0]);
        uya_host_h264_close_fd(&stdout_pipe[1]);
        free(encoder->raw_frame);
        free(encoder);
        return UYA_RK1106_H264_ENCODER_STATUS_UNAVAILABLE;
    }

    if (pid == 0) {
        dup2(stdin_pipe[0], STDIN_FILENO);
        dup2(stdout_pipe[1], STDOUT_FILENO);
        close(stdin_pipe[0]);
        close(stdin_pipe[1]);
        close(stdout_pipe[0]);
        close(stdout_pipe[1]);
        execlp("ffmpeg", "ffmpeg",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "yuv420p",
            "-s", size_arg,
            "-r", fps_arg,
            "-i", "pipe:0",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-g", gop_arg,
            "-keyint_min", gop_arg,
            "-x264-params", "repeat-headers=1:scenecut=0",
            "-b:v", bitrate_arg,
            "-f", "h264",
            "pipe:1",
            (char *)NULL);
        _exit(127);
    }

    close(stdin_pipe[0]);
    close(stdout_pipe[1]);
    encoder->pid = pid;
    encoder->stdin_fd = stdin_pipe[1];
    encoder->stdout_fd = stdout_pipe[0];
    uya_host_h264_set_nonblocking(encoder->stdin_fd);
    uya_host_h264_set_nonblocking(encoder->stdout_fd);
    *out_handle = (size_t)encoder;
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
    UyaHostFfmpegH264Encoder *encoder = (UyaHostFfmpegH264Encoder *)handle;
    int status;
    (void)pts_us;
    (void)force_idr;

    if (out_len)
        *out_len = 0;
    if (out_keyframe)
        *out_keyframe = 0;
    if (!encoder || !out_payload || !out_len || !out_keyframe)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    status = uya_host_h264_copy_i420_frame(encoder, y_plane, y_len, u_plane, u_len, v_plane, v_len, stride_y, stride_u, stride_v);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return status;
    status = uya_host_h264_write_frame_and_read_packet(encoder, out_payload, out_capacity, out_len);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return status;
    *out_keyframe = encoder->frame_count == 0 ? 1u : 0u;
    encoder->frame_count++;
    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

int uya_rk1106_h264_encoder_close(size_t handle)
{
    UyaHostFfmpegH264Encoder *encoder = (UyaHostFfmpegH264Encoder *)handle;
    int status;

    if (!encoder)
        return UYA_RK1106_H264_ENCODER_STATUS_OK;

    uya_host_h264_close_fd(&encoder->stdin_fd);
    uya_host_h264_close_fd(&encoder->stdout_fd);
    if (encoder->pid > 0) {
        kill(encoder->pid, SIGTERM);
        waitpid(encoder->pid, &status, 0);
    }
    free(encoder->raw_frame);
    free(encoder);
    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

#else

#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/time.h>

#include "rk_common.h"
#include "rk_errno.h"
#include "rk_mpi_sys.h"
#include "rk_mpi_vi.h"
#include "rk_mpi_venc.h"
#include "rk_mpi_mb.h"
#include "rk_comm_vi.h"
#include "rk_comm_venc.h"

typedef struct UyaRk1106H264Encoder {
    VI_DEV vi_dev;
    VI_PIPE vi_pipe;
    VI_CHN vi_chn;
    VENC_CHN venc_chn;
    uint32_t width;
    uint32_t height;
    uint32_t fps;
    uint32_t bitrate;
    uint32_t gop;
    uint64_t frame_count;
    RK_BOOL vi_enabled;
    RK_BOOL venc_enabled;
} UyaRk1106H264Encoder;

static int uya_rk1106_check(int rc, const char *what)
{
    if (rc == RK_SUCCESS)
        return UYA_RK1106_H264_ENCODER_STATUS_OK;
    fprintf(stderr, "rk1106_h264_encoder_shim: %s failed rc=0x%08x\n", what, rc);
    return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
}

static void uya_rk1106_fill_vi_attr(VI_CHN_ATTR_S *attr, uint32_t width, uint32_t height)
{
    memset(attr, 0, sizeof(*attr));
    attr->stIspOpt.u32BufCount = 3;
    attr->stIspOpt.enMemoryType = VI_V4L2_MEMORY_TYPE_DMABUF;
    attr->u32Depth = 1;
    attr->enPixelFormat = RK_FMT_YUV420SP;
    attr->enCompressMode = COMPRESS_MODE_NONE;
    attr->stFrameRate.s32SrcFrameRate = -1;
    attr->stFrameRate.s32DstFrameRate = -1;
    attr->stSize.u32Width = width;
    attr->stSize.u32Height = height;
}

static void uya_rk1106_fill_venc_attr(VENC_CHN_ATTR_S *attr, VENC_RC_PARAM_S *rc_param, VENC_RECV_PIC_PARAM_S *recv_param,
    uint32_t width, uint32_t height, uint32_t fps, uint32_t bitrate, uint32_t gop)
{
    memset(attr, 0, sizeof(*attr));
    memset(rc_param, 0, sizeof(*rc_param));
    memset(recv_param, 0, sizeof(*recv_param));

    attr->stVencAttr.enType = RK_VIDEO_ID_AVC;
    attr->stVencAttr.enPixelFormat = RK_FMT_YUV420SP;
    attr->stVencAttr.u32Profile = H264E_PROFILE_BASELINE;
    fprintf(stderr, "rk1106_h264_encoder_shim: H264 profile=baseline\n");
    attr->stVencAttr.u32PicWidth = width;
    attr->stVencAttr.u32PicHeight = height;
    attr->stVencAttr.u32VirWidth = width;
    attr->stVencAttr.u32VirHeight = height;
    attr->stVencAttr.u32MaxPicWidth = width;
    attr->stVencAttr.u32MaxPicHeight = height;
    attr->stVencAttr.u32StreamBufCnt = 4;
    attr->stVencAttr.u32BufSize = width * height / 2u;

    attr->stRcAttr.enRcMode = VENC_RC_MODE_H264VBR;
    attr->stRcAttr.stH264Vbr.u32Gop = gop;
    attr->stRcAttr.stH264Vbr.u32BitRate = bitrate;
    attr->stRcAttr.stH264Vbr.u32MaxBitRate = bitrate;
    attr->stRcAttr.stH264Vbr.u32MinBitRate = bitrate > 200u ? 200u : bitrate;
    attr->stRcAttr.stH264Vbr.u32SrcFrameRateNum = fps;
    attr->stRcAttr.stH264Vbr.u32SrcFrameRateDen = 1;
    attr->stRcAttr.stH264Vbr.fr32DstFrameRateNum = fps;
    attr->stRcAttr.stH264Vbr.fr32DstFrameRateDen = 1;

    rc_param->s32FirstFrameStartQp = 28;
    rc_param->stParamH264.u32MinQp = 10;
    rc_param->stParamH264.u32MaxQp = 51;
    rc_param->stParamH264.u32MinIQp = 10;
    rc_param->stParamH264.u32MaxIQp = 51;

    recv_param->s32RecvPicNum = -1;
}

static int uya_rk1106_h264_encoder_init(UyaRk1106H264Encoder *encoder)
{
    int rc;
    VI_DEV_ATTR_S dev_attr;
    VI_DEV_BIND_PIPE_S bind_pipe;
    VI_CHN_ATTR_S chn_attr;
    VENC_CHN_ATTR_S venc_attr;
    VENC_RC_PARAM_S rc_param;
    VENC_RECV_PIC_PARAM_S recv_param;
    VENC_CHN_REF_BUF_SHARE_S ref_buf_share;

    rc = RK_MPI_SYS_Init();
    if (uya_rk1106_check(rc, "RK_MPI_SYS_Init") != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;

    memset(&dev_attr, 0, sizeof(dev_attr));
    dev_attr.u32BufCount = 3;
    rc = RK_MPI_VI_GetDevAttr(encoder->vi_dev, &dev_attr);
    if (rc == RK_ERR_VI_NOT_CONFIG) {
        rc = RK_MPI_VI_SetDevAttr(encoder->vi_dev, &dev_attr);
        if (uya_rk1106_check(rc, "RK_MPI_VI_SetDevAttr") != UYA_RK1106_H264_ENCODER_STATUS_OK)
            return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
    } else if (rc != RK_SUCCESS) {
        return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
    }

    rc = RK_MPI_VI_GetDevIsEnable(encoder->vi_dev);
    if (rc != RK_SUCCESS) {
        rc = RK_MPI_VI_EnableDev(encoder->vi_dev);
        if (uya_rk1106_check(rc, "RK_MPI_VI_EnableDev") != UYA_RK1106_H264_ENCODER_STATUS_OK)
            return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
        memset(&bind_pipe, 0, sizeof(bind_pipe));
        bind_pipe.u32Num = 1;
        bind_pipe.PipeId[0] = encoder->vi_pipe;
        bind_pipe.bUserStartPipe[0] = RK_TRUE;
        rc = RK_MPI_VI_SetDevBindPipe(encoder->vi_dev, &bind_pipe);
        if (uya_rk1106_check(rc, "RK_MPI_VI_SetDevBindPipe") != UYA_RK1106_H264_ENCODER_STATUS_OK)
            return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
    }
    encoder->vi_enabled = RK_TRUE;

    uya_rk1106_fill_vi_attr(&chn_attr, encoder->width, encoder->height);
    rc = RK_MPI_VI_SetChnAttr(encoder->vi_dev, encoder->vi_chn, &chn_attr);
    if (uya_rk1106_check(rc, "RK_MPI_VI_SetChnAttr") != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
    rc = RK_MPI_VI_EnableChn(encoder->vi_dev, encoder->vi_chn);
    if (uya_rk1106_check(rc, "RK_MPI_VI_EnableChn") != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;

    uya_rk1106_fill_venc_attr(&venc_attr, &rc_param, &recv_param, encoder->width, encoder->height, encoder->fps, encoder->bitrate, encoder->gop);
    rc = RK_MPI_VENC_CreateChn(encoder->venc_chn, &venc_attr);
    if (uya_rk1106_check(rc, "RK_MPI_VENC_CreateChn") != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
    memset(&ref_buf_share, 0, sizeof(ref_buf_share));
    ref_buf_share.bEnable = RK_TRUE;
    (void)RK_MPI_VENC_SetChnRefBufShareAttr(encoder->venc_chn, &ref_buf_share);
    rc = RK_MPI_VENC_SetRcParam(encoder->venc_chn, &rc_param);
    if (uya_rk1106_check(rc, "RK_MPI_VENC_SetRcParam") != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
    (void)RK_MPI_VENC_EnableSvc(encoder->venc_chn, RK_TRUE);
    rc = RK_MPI_VENC_StartRecvFrame(encoder->venc_chn, &recv_param);
    if (uya_rk1106_check(rc, "RK_MPI_VENC_StartRecvFrame") != UYA_RK1106_H264_ENCODER_STATUS_OK)
        return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
    encoder->venc_enabled = RK_TRUE;

    {
        MPP_CHN_S src;
        MPP_CHN_S dst;
        memset(&src, 0, sizeof(src));
        memset(&dst, 0, sizeof(dst));
        src.enModId = RK_ID_VI;
        src.s32DevId = encoder->vi_dev;
        src.s32ChnId = encoder->vi_chn;
        dst.enModId = RK_ID_VENC;
        dst.s32DevId = 0;
        dst.s32ChnId = encoder->venc_chn;
        rc = RK_MPI_SYS_Bind(&src, &dst);
        if (uya_rk1106_check(rc, "RK_MPI_SYS_Bind") != UYA_RK1106_H264_ENCODER_STATUS_OK)
            return UYA_RK1106_H264_ENCODER_STATUS_MPP_OPEN_FAILED;
    }

    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

int uya_rk1106_h264_encoder_close(size_t handle)
{
    UyaRk1106H264Encoder *encoder = (UyaRk1106H264Encoder *)handle;
    if (!encoder)
        return UYA_RK1106_H264_ENCODER_STATUS_OK;

    if (encoder->venc_enabled) {
        RK_MPI_VENC_StopRecvFrame(encoder->venc_chn);
        RK_MPI_VENC_DestroyChn(encoder->venc_chn);
    }
    if (encoder->vi_enabled) {
        RK_MPI_VI_DisableChn(encoder->vi_dev, encoder->vi_chn);
        RK_MPI_VI_DisableDev(encoder->vi_dev);
    }
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
    int status;

    if (out_handle)
        *out_handle = 0;
    if (!out_handle || width == 0 || height == 0 || fps == 0 || bitrate == 0 || gop == 0)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    encoder = (UyaRk1106H264Encoder *)calloc(1, sizeof(*encoder));
    if (!encoder)
        return UYA_RK1106_H264_ENCODER_STATUS_UNAVAILABLE;
    encoder->vi_dev = 0;
    encoder->vi_pipe = 0;
    encoder->vi_chn = 0;
    encoder->venc_chn = 0;
    encoder->width = width;
    encoder->height = height;
    encoder->fps = fps;
    encoder->bitrate = bitrate;
    encoder->gop = gop;

    status = uya_rk1106_h264_encoder_init(encoder);
    if (status != UYA_RK1106_H264_ENCODER_STATUS_OK) {
        uya_rk1106_h264_encoder_close((size_t)encoder);
        return status;
    }
    *out_handle = (size_t)encoder;
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
    VENC_STREAM_S stream;
    VENC_PACK_S pack;
    void *payload;
    size_t copy_len;
    int rc;
    (void)y_plane; (void)y_len; (void)u_plane; (void)u_len; (void)v_plane; (void)v_len;
    (void)stride_y; (void)stride_u; (void)stride_v; (void)pts_us;

    if (out_len)
        *out_len = 0;
    if (out_keyframe)
        *out_keyframe = 0;
    if (!encoder || !out_payload || !out_len || !out_keyframe)
        return UYA_RK1106_H264_ENCODER_STATUS_INVALID_ARGUMENT;

    if (force_idr)
        (void)RK_MPI_VENC_RequestIDR(encoder->venc_chn, RK_FALSE);

    memset(&stream, 0, sizeof(stream));
    memset(&pack, 0, sizeof(pack));
    stream.pstPack = &pack;
    rc = RK_MPI_VENC_GetStream(encoder->venc_chn, &stream, 1000);
    if (rc != RK_SUCCESS) {
        fprintf(stderr, "rk1106_h264_encoder_shim: RK_MPI_VENC_GetStream failed rc=0x%08x\n", rc);
        return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
    }

    payload = RK_MPI_MB_Handle2VirAddr(stream.pstPack->pMbBlk);
    if (!payload || stream.pstPack->u32Len == 0) {
        RK_MPI_VENC_ReleaseStream(encoder->venc_chn, &stream);
        return UYA_RK1106_H264_ENCODER_STATUS_ENCODE_FAILED;
    }
    copy_len = stream.pstPack->u32Len;
    if (copy_len > out_capacity) {
        RK_MPI_VENC_ReleaseStream(encoder->venc_chn, &stream);
        return UYA_RK1106_H264_ENCODER_STATUS_BUFFER_TOO_SMALL;
    }
    memcpy(out_payload, payload, copy_len);
    *out_len = copy_len;
    *out_keyframe = stream.pstPack->DataType.enH264EType == H264E_NALU_IDRSLICE ? 1u : 0u;
    encoder->frame_count++;
    RK_MPI_VENC_ReleaseStream(encoder->venc_chn, &stream);
    return UYA_RK1106_H264_ENCODER_STATUS_OK;
}

#endif
