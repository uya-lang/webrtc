#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stdint.h>
#include <unistd.h>

#include "rk_common.h"
#include "rk_errno.h"
#include "rk_mpi_sys.h"
#include "rk_mpi_vi.h"
#include "rk_mpi_venc.h"
#include "rk_mpi_mb.h"
#include "rk_comm_vi.h"
#include "rk_comm_venc.h"

#define VI_MAIN_CHANNEL 0
#define VENC_MAIN_CHANNEL 0
#define FASTBOOT_RESERVED_FRAME_NUM 3

typedef struct _rkVENCCHN {
    uint32_t u32Width;
    uint32_t u32Height;
    uint32_t u32Gop;
    uint32_t u32BitRate;
    uint32_t u32StreamBufCnt;
    uint32_t enCodecType;
    VENC_CHN chn_id;
    VENC_CHN_ATTR_S stChnAttr;
    PIXEL_FORMAT_E enPixelFormat;
    VENC_RC_PARAM_S stRcParam;
    VENC_RECV_PIC_PARAM_S stRecvParam;
    VENC_CHN_REF_BUF_SHARE_S stVencChnRefBufShare;
    VENC_CHN_BUF_WRAP_S stVencChnBufWrap;
} VENC_CHN_S;

typedef struct _rkMpiVENCCtx {
    VENC_CHN_S chn[2];
} VENC_CTX_S;

typedef struct _rkVICHN {
    uint32_t chn_id;
    uint32_t width;
    uint32_t height;
    VI_CHN_ATTR_S stChnAttr;
    VI_CHN_BUF_WRAP_S stViWrap;
    VI_SAVE_FILE_INFO_S stDebugFile;
} VI_CHN_S;

typedef struct _rkVIDEV {
    uint32_t dev_id;
    VI_CHN_S chn[5];
    VI_DEV_ATTR_S stDevAttr;
} VI_DEV_S;

typedef struct _rkVIPIPE {
    uint32_t pipe_id;
    uint32_t width;
    uint32_t height;
    VI_PIPE_ATTR_S stPipeAttr;
    VI_DEV_BIND_PIPE_S stBindPipe;
} VI_PIPE_S;

typedef struct _rkMpiVICtx {
    VI_DEV_S dev;
    VI_PIPE_S pipe;
} VI_CTX_S;

typedef struct _rkMpiCtx {
    VI_CTX_S vi;
    VENC_CTX_S venc;
} MPI_CTX_S;

typedef struct HelperMeta {
    uint32_t venc_w;
    uint32_t venc_h;
    uint32_t venc_bitrate;
    uint32_t cam_w;
    uint32_t cam_h;
    uint32_t cam1_max_fps;
} HelperMeta;

static bool g_bWrap = true;
static uint32_t g_u32WrapLine = 0;
static bool quit = false;

static int fail_rc(const char *what, int32_t rc)
{
    fprintf(stderr, "rk1106_h264_capture_helper: %s failed rc=0x%08x\n", what, rc);
    return 1;
}

static void mpi_params_init(MPI_CTX_S *ctx, const HelperMeta *meta)
{
    int vi_buf_cnt = 1;
    uint32_t fps = meta->cam1_max_fps ? meta->cam1_max_fps : 30;
    uint32_t gop = fps * 2;
    int video_width = (int)meta->venc_w;
    int video_height = (int)meta->venc_h;

    memset(ctx, 0, sizeof(*ctx));

    if (g_bWrap) {
        if (meta->cam1_max_fps == 60)
            g_u32WrapLine = meta->venc_h;
        else
            g_u32WrapLine = meta->venc_h / 16;
        ctx->vi.dev.chn[VI_MAIN_CHANNEL].stViWrap.bEnable = g_bWrap;
        ctx->vi.dev.chn[VI_MAIN_CHANNEL].stViWrap.u32BufLine = g_u32WrapLine;
        ctx->vi.dev.chn[VI_MAIN_CHANNEL].stViWrap.u32WrapBufferSize =
            g_u32WrapLine * meta->cam_w * 3 / 2;
        ctx->venc.chn[VENC_MAIN_CHANNEL].stVencChnBufWrap.bEnable = g_bWrap;
        ctx->venc.chn[VENC_MAIN_CHANNEL].stVencChnBufWrap.u32BufLine = g_u32WrapLine;
    }

    ctx->vi.dev.dev_id = 0;
    ctx->vi.pipe.pipe_id = 0;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].chn_id = VI_MAIN_CHANNEL;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.stSize.u32Width = meta->venc_w;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.stSize.u32Height = meta->venc_h;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.stIspOpt.u32BufCount = vi_buf_cnt;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.stIspOpt.enMemoryType = VI_V4L2_MEMORY_TYPE_DMABUF;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.stIspOpt.stMaxSize.u32Width = meta->cam_w;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.stIspOpt.stMaxSize.u32Height = meta->cam_h;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.enPixelFormat = RK_FMT_YUV420SP;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.enCompressMode = COMPRESS_MODE_NONE;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.u32Depth = 0;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.stFrameRate.s32SrcFrameRate = -1;
    ctx->vi.dev.chn[VI_MAIN_CHANNEL].stChnAttr.stFrameRate.s32DstFrameRate = -1;

    ctx->venc.chn[VENC_MAIN_CHANNEL].chn_id = VENC_MAIN_CHANNEL;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.enType = RK_VIDEO_ID_AVC;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stRcAttr.enRcMode = VENC_RC_MODE_H264VBR;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stRcAttr.stH264Vbr.u32BitRate = meta->venc_bitrate;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stRcAttr.stH264Vbr.u32MaxBitRate = meta->venc_bitrate;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stRcAttr.stH264Vbr.u32MinBitRate = 200;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stRcAttr.stH264Vbr.u32Gop = gop;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stRcAttr.stH264Vbr.u32SrcFrameRateNum = fps;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stRcAttr.stH264Vbr.u32SrcFrameRateDen = 1;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stRcAttr.stH264Vbr.fr32DstFrameRateNum = fps;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stRcAttr.stH264Vbr.fr32DstFrameRateDen = 1;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.enPixelFormat = RK_FMT_YUV420SP;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.u32Profile = H264E_PROFILE_BASELINE;
    fprintf(stderr, "rk1106_h264_capture_helper: H264 profile=baseline\n");
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.u32PicWidth = video_width;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.u32VirWidth = video_width;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.u32PicHeight = video_height;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.u32VirHeight = video_height;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.u32MaxPicWidth = video_width;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.u32MaxPicHeight = video_height;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.u32BufSize = video_width * video_height / 3;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.u32StreamBufCnt = 4;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stChnAttr.stVencAttr.enMirror = MIRROR_NONE;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stVencChnRefBufShare.bEnable = true;
    memset(&ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam, 0, sizeof(VENC_RC_PARAM_S));
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam.s32FirstFrameStartQp = 28;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam.stParamH264.u32MinQp = 10;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam.stParamH264.u32MaxQp = 51;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam.stParamH264.u32MinIQp = 10;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam.stParamH264.u32MaxIQp = 51;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam.stParamH264.u32FrmMinQp = 25;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam.stParamH264.u32FrmMinIQp = 24;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam.stParamH264.u32FrmMaxQp = 41;
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRcParam.stParamH264.u32FrmMaxIQp = 35;
    memset(&ctx->venc.chn[VENC_MAIN_CHANNEL].stRecvParam, 0, sizeof(VENC_RECV_PIC_PARAM_S));
    ctx->venc.chn[VENC_MAIN_CHANNEL].stRecvParam.s32RecvPicNum = -1;
}

static int32_t vi_init(VI_CTX_S *ctx)
{
    int32_t ret;
    fprintf(stderr, "helper: vi_init start dev=%u pipe=%u chn=%u\n", ctx->dev.dev_id, ctx->pipe.pipe_id, ctx->dev.chn[0].chn_id);

    ctx->dev.stDevAttr.u32BufCount = 1;
    ret = RK_MPI_VI_GetDevAttr(ctx->dev.dev_id, &ctx->dev.stDevAttr);
    fprintf(stderr, "helper: RK_MPI_VI_GetDevAttr rc=0x%08x\n", ret);
    if (ret == RK_ERR_VI_NOT_CONFIG) {
        ret = RK_MPI_VI_SetDevAttr(ctx->dev.dev_id, &ctx->dev.stDevAttr);
        fprintf(stderr, "helper: RK_MPI_VI_SetDevAttr rc=0x%08x\n", ret);
        if (ret != RK_SUCCESS)
            return ret;
    } else if (ret != RK_SUCCESS) {
        return ret;
    }

    ret = RK_MPI_VI_GetDevIsEnable(ctx->dev.dev_id);
    fprintf(stderr, "helper: RK_MPI_VI_GetDevIsEnable rc=0x%08x\n", ret);
    if (ret != RK_SUCCESS) {
        ret = RK_MPI_VI_EnableDev(ctx->dev.dev_id);
        fprintf(stderr, "helper: RK_MPI_VI_EnableDev rc=0x%08x\n", ret);
        if (ret != RK_SUCCESS)
            return ret;
        ctx->pipe.stBindPipe.u32Num = 1;
        ctx->pipe.stBindPipe.PipeId[0] = ctx->pipe.pipe_id;
        ctx->pipe.stBindPipe.bUserStartPipe[0] = true;
        ret = RK_MPI_VI_SetDevBindPipe(ctx->dev.dev_id, &ctx->pipe.stBindPipe);
        fprintf(stderr, "helper: RK_MPI_VI_SetDevBindPipe rc=0x%08x\n", ret);
        if (ret != 0)
            return ret;
    } else {
        return ret;
    }

    ret = RK_MPI_VI_SetChnAttr(ctx->dev.dev_id, ctx->dev.chn[0].chn_id, &ctx->dev.chn[0].stChnAttr);
    fprintf(stderr, "helper: RK_MPI_VI_SetChnAttr rc=0x%08x size=%ux%u depth=%u mem=%d max=%ux%u\n", ret, ctx->dev.chn[0].stChnAttr.stSize.u32Width, ctx->dev.chn[0].stChnAttr.stSize.u32Height, ctx->dev.chn[0].stChnAttr.u32Depth, ctx->dev.chn[0].stChnAttr.stIspOpt.enMemoryType, ctx->dev.chn[0].stChnAttr.stIspOpt.stMaxSize.u32Width, ctx->dev.chn[0].stChnAttr.stIspOpt.stMaxSize.u32Height);
    if (ret)
        return ret;

    if (g_bWrap) {
        ret = RK_MPI_VI_SetChnWrapBufAttr(ctx->dev.dev_id, ctx->dev.chn[0].chn_id, &ctx->dev.chn[0].stViWrap);
        fprintf(stderr, "helper: RK_MPI_VI_SetChnWrapBufAttr rc=0x%08x wrapLine=%u wrapSize=%u\n", ret, ctx->dev.chn[0].stViWrap.u32BufLine, ctx->dev.chn[0].stViWrap.u32WrapBufferSize);
        if (ret)
            return ret;
    }

    ret = RK_MPI_VI_EnableChn(ctx->dev.dev_id, ctx->dev.chn[0].chn_id);
    fprintf(stderr, "helper: RK_MPI_VI_EnableChn rc=0x%08x\n", ret);
    return ret;
}

static int32_t venc_init(VENC_CTX_S *ctx)
{
    int32_t ret;
    fprintf(stderr, "helper: venc_init start chn=%d\n", ctx->chn[0].chn_id);

    ret = RK_MPI_VENC_CreateChn(ctx->chn[0].chn_id, &ctx->chn[0].stChnAttr);
    fprintf(stderr, "helper: RK_MPI_VENC_CreateChn rc=0x%08x bitrate=%u gop=%u buf=%u\n", ret, ctx->chn[0].stChnAttr.stRcAttr.stH264Vbr.u32BitRate, ctx->chn[0].stChnAttr.stRcAttr.stH264Vbr.u32Gop, ctx->chn[0].stChnAttr.stVencAttr.u32BufSize);
    if (ret != 0)
        return ret;

    if (g_bWrap) {
        ret = RK_MPI_VENC_SetChnBufWrapAttr(ctx->chn[0].chn_id, &ctx->chn[0].stVencChnBufWrap);
        if (ret != 0)
            return ret;
    }

    ret = RK_MPI_VENC_SetChnRefBufShareAttr(ctx->chn[0].chn_id, &ctx->chn[0].stVencChnRefBufShare);
    if (ret != 0)
        return ret;

    ret = RK_MPI_VENC_SetRcParam(ctx->chn[0].chn_id, &ctx->chn[0].stRcParam);
    if (ret != 0)
        return ret;

    ret = RK_MPI_VENC_EnableSvc(ctx->chn[0].chn_id, RK_TRUE);
    if (ret != 0)
        return ret;

    ret = RK_MPI_VENC_StartRecvFrame(ctx->chn[0].chn_id, &ctx->chn[0].stRecvParam);
    return ret;
}

static int stream_stdout(VENC_CHN chn)
{
    VENC_STREAM_S stFrame;
    int loopCount = 0;
    int s32Ret;

    memset(&stFrame, 0, sizeof(stFrame));
    stFrame.pstPack = malloc(sizeof(VENC_PACK_S));
    if (!stFrame.pstPack)
        return 1;

    while (!quit) {
        void *pData;
        s32Ret = RK_MPI_VENC_GetStream(chn, &stFrame, 1000);
        if (s32Ret == RK_SUCCESS) {
            pData = (void *)RK_MPI_MB_Handle2VirAddr(stFrame.pstPack->pMbBlk);
            if (pData && stFrame.pstPack->u32Len > 0) {
                if (fwrite(pData, 1, stFrame.pstPack->u32Len, stdout) != stFrame.pstPack->u32Len) {
                    RK_MPI_VENC_ReleaseStream(chn, &stFrame);
                    break;
                }
                fflush(stdout);
            }
            RK_MPI_VENC_ReleaseStream(chn, &stFrame);
            loopCount++;
        } else {
            fprintf(stderr, "rk1106_h264_capture_helper: RK_MPI_VENC_GetStream failed rc=0x%08x\n", s32Ret);
            free(stFrame.pstPack);
            return 1;
        }
    }
    free(stFrame.pstPack);
    return 0;
}

int main(int argc, char **argv)
{
    MPI_CTX_S ctx;
    HelperMeta meta;
    int32_t ret;

    if (argc < 6) {
        fprintf(stderr, "usage: %s <width> <height> <fps> <bitrate> <gop>\n", argv[0]);
        return 2;
    }

    memset(&meta, 0, sizeof(meta));
    meta.venc_w = (uint32_t)strtoul(argv[1], NULL, 10);
    meta.venc_h = (uint32_t)strtoul(argv[2], NULL, 10);
    meta.cam_w = meta.venc_w;
    meta.cam_h = meta.venc_h;
    meta.cam1_max_fps = (uint32_t)strtoul(argv[3], NULL, 10);
    meta.venc_bitrate = (uint32_t)strtoul(argv[4], NULL, 10);
    (void)argv[5];

    mpi_params_init(&ctx, &meta);
    ret = vi_init(&ctx.vi);
    if (ret != 0)
        return fail_rc("vi_init", ret);
    ret = venc_init(&ctx.venc);
    if (ret != 0)
        return fail_rc("venc_init", ret);
    return stream_stdout(VENC_MAIN_CHANNEL);
}
