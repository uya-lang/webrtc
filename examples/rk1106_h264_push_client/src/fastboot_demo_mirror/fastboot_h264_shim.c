#define _GNU_SOURCE
#define FASTBOOT_H264_STATUS_OK 0
#define FASTBOOT_H264_STATUS_INVALID_ARGUMENT -1
#define FASTBOOT_H264_STATUS_OPEN_FAILED -2
#define FASTBOOT_H264_STATUS_READ_FAILED -3
#define FASTBOOT_H264_STATUS_BUFFER_TOO_SMALL -4
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define main uya_fastboot_demo_unused_main
#include "fastboot_demo.c"
#undef main

typedef struct UyaFastbootPacketNode {
    uint8_t *data;
    size_t len;
    uint64_t pts_us;
    uint32_t keyframe;
    struct UyaFastbootPacketNode *next;
} UyaFastbootPacketNode;

typedef struct UyaFastbootContext {
    MPI_CTX_S mpi_ctx;
    pthread_t venc_thread;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    UyaFastbootPacketNode *head;
    UyaFastbootPacketNode *tail;
    int stop;
    int started;
    uint32_t width;
    uint32_t height;
    uint32_t fps;
    uint32_t bitrate;
    uint32_t gop;
} UyaFastbootContext;

static void uya_fastboot_queue_push(UyaFastbootContext *ctx, const uint8_t *data, size_t len, uint64_t pts_us, uint32_t keyframe) {
    UyaFastbootPacketNode *node = (UyaFastbootPacketNode *)malloc(sizeof(*node));
    if (!node) return;
    node->data = (uint8_t *)malloc(len);
    if (!node->data) { free(node); return; }
    memcpy(node->data, data, len);
    node->len = len;
    node->pts_us = pts_us;
    node->keyframe = keyframe;
    node->next = NULL;
    pthread_mutex_lock(&ctx->mutex);
    if (ctx->tail) ctx->tail->next = node; else ctx->head = node;
    ctx->tail = node;
    pthread_cond_signal(&ctx->cond);
    pthread_mutex_unlock(&ctx->mutex);
}

static int uya_fastboot_queue_pop(UyaFastbootContext *ctx, uint8_t *out, size_t out_cap, size_t *out_len, uint64_t *out_pts_us, uint32_t *out_keyframe) {
    pthread_mutex_lock(&ctx->mutex);
    while (!ctx->stop && ctx->head == NULL) pthread_cond_wait(&ctx->cond, &ctx->mutex);
    if (ctx->head == NULL) {
        pthread_mutex_unlock(&ctx->mutex);
        return FASTBOOT_H264_STATUS_READ_FAILED;
    }
    UyaFastbootPacketNode *node = ctx->head;
    ctx->head = node->next;
    if (ctx->head == NULL) ctx->tail = NULL;
    pthread_mutex_unlock(&ctx->mutex);
    if (node->len > out_cap) {
        free(node->data); free(node);
        return FASTBOOT_H264_STATUS_BUFFER_TOO_SMALL;
    }
    memcpy(out, node->data, node->len);
    *out_len = node->len;
    *out_pts_us = node->pts_us;
    *out_keyframe = node->keyframe;
    free(node->data);
    free(node);
    return FASTBOOT_H264_STATUS_OK;
}

static void *uya_fastboot_venc_thread(void *arg) {
    UyaFastbootContext *ctx = (UyaFastbootContext *)arg;
    VENC_STREAM_S stFrame;
    memset(&stFrame, 0, sizeof(stFrame));
    stFrame.pstPack = malloc(sizeof(VENC_PACK_S));
    if (!stFrame.pstPack) return NULL;
    while (!ctx->stop) {
        int ret = RK_MPI_VENC_GetStream(VENC_MAIN_CHANNEL, &stFrame, 1000);
        if (ret != RK_SUCCESS) continue;
        void *pData = RK_MPI_MB_Handle2VirAddr(stFrame.pstPack->pMbBlk);
        uint32_t key = 0;
        if ((stFrame.pstPack->DataType.enH264EType == H264E_NALU_IDRSLICE) || (stFrame.pstPack->DataType.enH264EType == H264E_NALU_ISLICE)) key = 1;
        uya_fastboot_queue_push(ctx, (const uint8_t *)pData, stFrame.pstPack->u32Len, stFrame.pstPack->u64PTS / 1000ULL, key);
        RK_MPI_VENC_ReleaseStream(VENC_MAIN_CHANNEL, &stFrame);
    }
    free(stFrame.pstPack);
    return NULL;
}

static int uya_fastboot_bootstrap(UyaFastbootContext *ctx) {
    memset(&ctx->mpi_ctx, 0, sizeof(ctx->mpi_ctx));
    ctx->mpi_ctx.vi.dev.dev_id = 0;
    ctx->mpi_ctx.vi.pipe.pipe_id = 0;
    if (ctx->width == 0) ctx->width = 1920;
    if (ctx->height == 0) ctx->height = 1080;
    if (ctx->fps == 0) ctx->fps = 30;
    if (ctx->bitrate == 0) ctx->bitrate = 1000000;
    if (ctx->gop == 0) ctx->gop = 30;
    g_bWrap = true;
    g_u32WrapLine = ctx->height;
    if (isp_init(0, 0, ctx->fps, RK_TRUE, NULL) != 0) return -1;
    vi_chn_init(&ctx->mpi_ctx, ctx->width, ctx->height);
    venc_chn_init(&ctx->mpi_ctx, ctx->width, ctx->height, ctx->fps, ctx->gop);
    if (RK_MPI_SYS_Bind(&(MPP_CHN_S){RK_ID_VI,0,0}, &(MPP_CHN_S){RK_ID_VENC,0,VENC_MAIN_CHANNEL}) != RK_SUCCESS) return -1;
    return 0;
}

int uya_fastboot_h264_open(uint32_t width, uint32_t height, uint32_t fps, uint32_t bitrate, uint32_t gop, size_t *out_handle) {
    if (!out_handle || width == 0 || height == 0 || fps == 0 || bitrate == 0 || gop == 0) return FASTBOOT_H264_STATUS_INVALID_ARGUMENT;
    UyaFastbootContext *ctx = (UyaFastbootContext *)calloc(1, sizeof(*ctx));
    if (!ctx) return FASTBOOT_H264_STATUS_OPEN_FAILED;
    ctx->width = width; ctx->height = height; ctx->fps = fps; ctx->bitrate = bitrate; ctx->gop = gop;
    pthread_mutex_init(&ctx->mutex, NULL);
    pthread_cond_init(&ctx->cond, NULL);
    quit = false;
    if (uya_fastboot_bootstrap(ctx) != 0) { free(ctx); return FASTBOOT_H264_STATUS_OPEN_FAILED; }
    if (pthread_create(&ctx->venc_thread, NULL, uya_fastboot_venc_thread, ctx) != 0) { free(ctx); return FASTBOOT_H264_STATUS_OPEN_FAILED; }
    ctx->started = 1;
    *out_handle = (size_t)ctx;
    return FASTBOOT_H264_STATUS_OK;
}

int uya_fastboot_h264_read_packet(size_t handle, uint8_t *out_payload, size_t out_capacity, size_t *out_len, uint64_t *out_pts_us, uint32_t *out_keyframe) {
    if (!handle || !out_payload || !out_len || !out_pts_us || !out_keyframe || out_capacity == 0) return FASTBOOT_H264_STATUS_INVALID_ARGUMENT;
    return uya_fastboot_queue_pop((UyaFastbootContext *)handle, out_payload, out_capacity, out_len, out_pts_us, out_keyframe);
}

int uya_fastboot_h264_close(size_t handle) {
    if (!handle) return FASTBOOT_H264_STATUS_OK;
    UyaFastbootContext *ctx = (UyaFastbootContext *)handle;
    ctx->stop = 1;
    pthread_mutex_lock(&ctx->mutex);
    pthread_cond_broadcast(&ctx->cond);
    pthread_mutex_unlock(&ctx->mutex);
    if (ctx->started) pthread_join(ctx->venc_thread, NULL);
    isp_deinit(0);
    pthread_mutex_destroy(&ctx->mutex);
    pthread_cond_destroy(&ctx->cond);
    while (ctx->head) {
        UyaFastbootPacketNode *node = ctx->head;
        ctx->head = node->next;
        free(node->data);
        free(node);
    }
    free(ctx);
    return FASTBOOT_H264_STATUS_OK;
}
