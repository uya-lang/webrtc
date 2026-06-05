#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

#define UYA_RK1106_H264_DECODER_STATUS_OK 0
#define UYA_RK1106_H264_DECODER_STATUS_UNAVAILABLE -1
#define UYA_RK1106_H264_DECODER_STATUS_INVALID_ARGUMENT -2
#define UYA_RK1106_H264_DECODER_STATUS_INPUT_OPEN_FAILED -3
#define UYA_RK1106_H264_DECODER_STATUS_OUTPUT_OPEN_FAILED -4
#define UYA_RK1106_H264_DECODER_STATUS_MPP_OPEN_FAILED -5
#define UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED -6
#define UYA_RK1106_H264_DECODER_STATUS_UNSUPPORTED_FORMAT -7
#define UYA_RK1106_H264_DECODER_STATUS_READ_FAILED -8
#define UYA_RK1106_H264_DECODER_STATUS_WRITE_FAILED -9

int uya_rk1106_h264_decode_file(
    unsigned char *input_path,
    unsigned char *output_path,
    size_t chunk_bytes,
    uint32_t max_frames,
    uint32_t split_parse,
    uint32_t *out_frames,
    uint64_t *out_bytes_read,
    uint64_t *out_bytes_written,
    uint32_t *out_width,
    uint32_t *out_height);

int uya_rk1106_h264_write_stderr(unsigned char *message, size_t len)
{
    if (!message || len == 0)
        return 0;
    return fwrite(message, 1, len, stderr) == len ? 0 : -1;
}

#ifndef UYA_RK1106_H264_DECODER_ENABLE_MPP

int uya_rk1106_h264_decode_file(
    unsigned char *input_path,
    unsigned char *output_path,
    size_t chunk_bytes,
    uint32_t max_frames,
    uint32_t split_parse,
    uint32_t *out_frames,
    uint64_t *out_bytes_read,
    uint64_t *out_bytes_written,
    uint32_t *out_width,
    uint32_t *out_height)
{
    (void)input_path;
    (void)output_path;
    (void)chunk_bytes;
    (void)max_frames;
    (void)split_parse;
    if (out_frames)
        *out_frames = 0;
    if (out_bytes_read)
        *out_bytes_read = 0;
    if (out_bytes_written)
        *out_bytes_written = 0;
    if (out_width)
        *out_width = 0;
    if (out_height)
        *out_height = 0;
    return UYA_RK1106_H264_DECODER_STATUS_UNAVAILABLE;
}

#else

#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "rk_mpi.h"
#include "rk_vdec_cfg.h"
#include "mpp_buffer.h"
#include "mpp_frame.h"
#include "mpp_packet.h"

typedef struct UyaRk1106H264Decoder {
    MppCtx ctx;
    MppApi *mpi;
    MppPacket packet;
    MppBufferGroup frame_group;
} UyaRk1106H264Decoder;

typedef struct UyaRk1106H264Stats {
    uint32_t frames;
    uint64_t bytes_read;
    uint64_t bytes_written;
    uint32_t width;
    uint32_t height;
} UyaRk1106H264Stats;

static void uya_rk1106_h264_zero_outputs(
    uint32_t *out_frames,
    uint64_t *out_bytes_read,
    uint64_t *out_bytes_written,
    uint32_t *out_width,
    uint32_t *out_height)
{
    if (out_frames)
        *out_frames = 0;
    if (out_bytes_read)
        *out_bytes_read = 0;
    if (out_bytes_written)
        *out_bytes_written = 0;
    if (out_width)
        *out_width = 0;
    if (out_height)
        *out_height = 0;
}

static void uya_rk1106_h264_store_outputs(
    const UyaRk1106H264Stats *stats,
    uint32_t *out_frames,
    uint64_t *out_bytes_read,
    uint64_t *out_bytes_written,
    uint32_t *out_width,
    uint32_t *out_height)
{
    if (out_frames)
        *out_frames = stats->frames;
    if (out_bytes_read)
        *out_bytes_read = stats->bytes_read;
    if (out_bytes_written)
        *out_bytes_written = stats->bytes_written;
    if (out_width)
        *out_width = stats->width;
    if (out_height)
        *out_height = stats->height;
}

static int uya_rk1106_h264_decoder_close(UyaRk1106H264Decoder *decoder)
{
    if (!decoder)
        return UYA_RK1106_H264_DECODER_STATUS_OK;

    if (decoder->mpi && decoder->ctx)
        decoder->mpi->reset(decoder->ctx);
    if (decoder->packet)
        mpp_packet_deinit(&decoder->packet);
    if (decoder->ctx)
        mpp_destroy(decoder->ctx);
    if (decoder->frame_group)
        mpp_buffer_group_put(decoder->frame_group);

    memset(decoder, 0, sizeof(*decoder));
    return UYA_RK1106_H264_DECODER_STATUS_OK;
}

static int uya_rk1106_h264_decoder_open(UyaRk1106H264Decoder *decoder, uint32_t split_parse)
{
    MPP_RET ret;
    MppDecCfg cfg = NULL;
    MppFrameFormat output_fmt = MPP_FMT_YUV420SP;

    if (!decoder)
        return UYA_RK1106_H264_DECODER_STATUS_INVALID_ARGUMENT;
    memset(decoder, 0, sizeof(*decoder));

    ret = mpp_packet_init(&decoder->packet, NULL, 0);
    if (ret != MPP_OK)
        goto fail;

    ret = mpp_create(&decoder->ctx, &decoder->mpi);
    if (ret != MPP_OK || !decoder->ctx || !decoder->mpi)
        goto fail;

    ret = mpp_init(decoder->ctx, MPP_CTX_DEC, MPP_VIDEO_CodingAVC);
    if (ret != MPP_OK)
        goto fail;

    ret = mpp_dec_cfg_init(&cfg);
    if (ret == MPP_OK) {
        ret = decoder->mpi->control(decoder->ctx, MPP_DEC_GET_CFG, cfg);
        if (ret == MPP_OK)
            ret = mpp_dec_cfg_set_u32(cfg, "base:split_parse", split_parse ? 1 : 0);
        if (ret == MPP_OK)
            ret = decoder->mpi->control(decoder->ctx, MPP_DEC_SET_CFG, cfg);
        mpp_dec_cfg_deinit(cfg);
        cfg = NULL;
        if (ret != MPP_OK)
            goto fail;
    }

    (void)decoder->mpi->control(decoder->ctx, MPP_DEC_SET_OUTPUT_FORMAT, &output_fmt);
    return UYA_RK1106_H264_DECODER_STATUS_OK;

fail:
    if (cfg)
        mpp_dec_cfg_deinit(cfg);
    uya_rk1106_h264_decoder_close(decoder);
    return UYA_RK1106_H264_DECODER_STATUS_MPP_OPEN_FAILED;
}

static int uya_rk1106_h264_write_rows(
    FILE *output,
    const uint8_t *base,
    uint32_t stride,
    uint32_t row_bytes,
    uint32_t rows,
    uint64_t *bytes_written)
{
    uint32_t row;

    if (!output || !base || row_bytes == 0)
        return UYA_RK1106_H264_DECODER_STATUS_INVALID_ARGUMENT;

    for (row = 0; row < rows; row++) {
        if (fwrite(base + (size_t)row * stride, 1, row_bytes, output) != row_bytes)
            return UYA_RK1106_H264_DECODER_STATUS_WRITE_FAILED;
        *bytes_written += row_bytes;
    }
    return UYA_RK1106_H264_DECODER_STATUS_OK;
}

static int uya_rk1106_h264_write_i420_as_nv12(
    FILE *output,
    const uint8_t *base_u,
    const uint8_t *base_v,
    uint32_t uv_stride,
    uint32_t width,
    uint32_t height,
    uint64_t *bytes_written)
{
    uint32_t row;
    uint8_t *tmp = (uint8_t *)malloc(width);

    if (!tmp)
        return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;

    for (row = 0; row < height / 2; row++) {
        uint32_t col;
        for (col = 0; col < width / 2; col++) {
            tmp[col * 2 + 0] = base_u[(size_t)row * uv_stride + col];
            tmp[col * 2 + 1] = base_v[(size_t)row * uv_stride + col];
        }
        if (fwrite(tmp, 1, width, output) != width) {
            free(tmp);
            return UYA_RK1106_H264_DECODER_STATUS_WRITE_FAILED;
        }
        *bytes_written += width;
    }

    free(tmp);
    return UYA_RK1106_H264_DECODER_STATUS_OK;
}

static int uya_rk1106_h264_write_nv21_as_nv12(
    FILE *output,
    const uint8_t *base_vu,
    uint32_t stride,
    uint32_t width,
    uint32_t height,
    uint64_t *bytes_written)
{
    uint32_t row;
    uint8_t *tmp = (uint8_t *)malloc(width);

    if (!tmp)
        return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;

    for (row = 0; row < height / 2; row++) {
        uint32_t col;
        const uint8_t *src = base_vu + (size_t)row * stride;
        for (col = 0; col < width / 2; col++) {
            tmp[col * 2 + 0] = src[col * 2 + 1];
            tmp[col * 2 + 1] = src[col * 2 + 0];
        }
        if (fwrite(tmp, 1, width, output) != width) {
            free(tmp);
            return UYA_RK1106_H264_DECODER_STATUS_WRITE_FAILED;
        }
        *bytes_written += width;
    }

    free(tmp);
    return UYA_RK1106_H264_DECODER_STATUS_OK;
}

static int uya_rk1106_h264_write_frame_nv12(FILE *output, MppFrame frame, UyaRk1106H264Stats *stats)
{
    MppBuffer buffer;
    MppFrameFormat fmt;
    uint8_t *base;
    uint32_t width;
    uint32_t height;
    uint32_t h_stride;
    uint32_t v_stride;
    int status;

    if (!output || !frame || !stats)
        return UYA_RK1106_H264_DECODER_STATUS_INVALID_ARGUMENT;

    buffer = mpp_frame_get_buffer(frame);
    if (!buffer)
        return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;

    fmt = mpp_frame_get_fmt(frame);
    if (MPP_FRAME_FMT_IS_FBC(fmt))
        return UYA_RK1106_H264_DECODER_STATUS_UNSUPPORTED_FORMAT;
    fmt &= MPP_FRAME_FMT_MASK;

    width = mpp_frame_get_width(frame);
    height = mpp_frame_get_height(frame);
    h_stride = mpp_frame_get_hor_stride(frame);
    v_stride = mpp_frame_get_ver_stride(frame);
    base = (uint8_t *)mpp_buffer_get_ptr(buffer);

    if (!base || width == 0 || height == 0 ||
        (width & 1) || (height & 1) ||
        h_stride < width || v_stride < height)
        return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;

    status = uya_rk1106_h264_write_rows(output, base, h_stride, width, height, &stats->bytes_written);
    if (status != UYA_RK1106_H264_DECODER_STATUS_OK)
        return status;

    if (fmt == MPP_FMT_YUV420SP) {
        const uint8_t *base_uv = base + (size_t)h_stride * v_stride;
        status = uya_rk1106_h264_write_rows(output, base_uv, h_stride, width, height / 2, &stats->bytes_written);
    } else if (fmt == MPP_FMT_YUV420SP_VU) {
        const uint8_t *base_vu = base + (size_t)h_stride * v_stride;
        status = uya_rk1106_h264_write_nv21_as_nv12(output, base_vu, h_stride, width, height, &stats->bytes_written);
    } else if (fmt == MPP_FMT_YUV420P) {
        const uint8_t *base_u = base + (size_t)h_stride * v_stride;
        const uint8_t *base_v = base_u + (size_t)(h_stride / 2) * (v_stride / 2);
        if ((h_stride & 1) || (v_stride & 1))
            return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;
        status = uya_rk1106_h264_write_i420_as_nv12(output, base_u, base_v, h_stride / 2, width, height, &stats->bytes_written);
    } else {
        return UYA_RK1106_H264_DECODER_STATUS_UNSUPPORTED_FORMAT;
    }

    if (status != UYA_RK1106_H264_DECODER_STATUS_OK)
        return status;

    stats->frames++;
    stats->width = width;
    stats->height = height;
    return UYA_RK1106_H264_DECODER_STATUS_OK;
}

static int uya_rk1106_h264_handle_info_change(UyaRk1106H264Decoder *decoder, MppFrame frame)
{
    MPP_RET ret;
    uint32_t buf_size;

    if (!decoder || !frame)
        return UYA_RK1106_H264_DECODER_STATUS_INVALID_ARGUMENT;

    if (!decoder->frame_group) {
        ret = mpp_buffer_group_get_internal(&decoder->frame_group, MPP_BUFFER_TYPE_ION);
        if (ret != MPP_OK)
            return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;
        ret = decoder->mpi->control(decoder->ctx, MPP_DEC_SET_EXT_BUF_GROUP, decoder->frame_group);
        if (ret != MPP_OK)
            return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;
    } else {
        ret = mpp_buffer_group_clear(decoder->frame_group);
        if (ret != MPP_OK)
            return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;
    }

    buf_size = mpp_frame_get_buf_size(frame);
    ret = mpp_buffer_group_limit_config(decoder->frame_group, buf_size, 24);
    if (ret != MPP_OK)
        return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;

    ret = decoder->mpi->control(decoder->ctx, MPP_DEC_SET_INFO_CHANGE_READY, NULL);
    if (ret != MPP_OK)
        return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;

    return UYA_RK1106_H264_DECODER_STATUS_OK;
}

static int uya_rk1106_h264_should_stop(const UyaRk1106H264Stats *stats, uint32_t max_frames)
{
    return max_frames != 0 && stats->frames >= max_frames;
}

static int uya_rk1106_h264_drain(
    UyaRk1106H264Decoder *decoder,
    FILE *output,
    UyaRk1106H264Stats *stats,
    uint32_t max_frames,
    int wait_for_frame,
    int *got_eos)
{
    int idle_count = 0;

    while (!uya_rk1106_h264_should_stop(stats, max_frames)) {
        MppFrame frame = NULL;
        MPP_RET ret = decoder->mpi->decode_get_frame(decoder->ctx, &frame);

        if (ret == MPP_ERR_TIMEOUT) {
            if (wait_for_frame && idle_count < 30) {
                idle_count++;
                usleep(1000);
                continue;
            }
            return UYA_RK1106_H264_DECODER_STATUS_OK;
        }
        if (ret != MPP_OK)
            return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;
        if (!frame)
            return UYA_RK1106_H264_DECODER_STATUS_OK;

        if (mpp_frame_get_info_change(frame)) {
            int status = uya_rk1106_h264_handle_info_change(decoder, frame);
            mpp_frame_deinit(&frame);
            if (status != UYA_RK1106_H264_DECODER_STATUS_OK)
                return status;
            idle_count = 0;
            continue;
        }

        if (!mpp_frame_get_errinfo(frame) && !mpp_frame_get_discard(frame)) {
            int status = uya_rk1106_h264_write_frame_nv12(output, frame, stats);
            if (status != UYA_RK1106_H264_DECODER_STATUS_OK) {
                mpp_frame_deinit(&frame);
                return status;
            }
        }

        if (mpp_frame_get_eos(frame) && got_eos)
            *got_eos = 1;
        mpp_frame_deinit(&frame);
        if (got_eos && *got_eos)
            return UYA_RK1106_H264_DECODER_STATUS_OK;
        idle_count = 0;
    }

    return UYA_RK1106_H264_DECODER_STATUS_OK;
}

static int uya_rk1106_h264_send_packet_and_drain(
    UyaRk1106H264Decoder *decoder,
    FILE *output,
    uint8_t *chunk,
    size_t chunk_len,
    int eos,
    UyaRk1106H264Stats *stats,
    uint32_t max_frames,
    int *got_eos)
{
    int attempts = 0;

    if (!decoder || !decoder->packet || !chunk || !output || !stats)
        return UYA_RK1106_H264_DECODER_STATUS_INVALID_ARGUMENT;

    mpp_packet_set_data(decoder->packet, chunk);
    mpp_packet_set_size(decoder->packet, chunk_len);
    mpp_packet_set_pos(decoder->packet, chunk);
    mpp_packet_set_length(decoder->packet, chunk_len);
    if (eos)
        mpp_packet_set_eos(decoder->packet);
    else
        mpp_packet_clr_eos(decoder->packet);

    while (attempts < 60) {
        MPP_RET ret = decoder->mpi->decode_put_packet(decoder->ctx, decoder->packet);
        if (ret == MPP_OK)
            break;
        if (ret != MPP_ERR_BUFFER_FULL && ret != MPP_ERR_TIMEOUT)
            return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;

        attempts++;
        if (uya_rk1106_h264_drain(decoder, output, stats, max_frames, 1, got_eos) != UYA_RK1106_H264_DECODER_STATUS_OK)
            return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;
        usleep(1000);
    }

    if (attempts >= 60)
        return UYA_RK1106_H264_DECODER_STATUS_DECODE_FAILED;

    return uya_rk1106_h264_drain(decoder, output, stats, max_frames, eos, got_eos);
}

int uya_rk1106_h264_decode_file(
    unsigned char *input_path,
    unsigned char *output_path,
    size_t chunk_bytes,
    uint32_t max_frames,
    uint32_t split_parse,
    uint32_t *out_frames,
    uint64_t *out_bytes_read,
    uint64_t *out_bytes_written,
    uint32_t *out_width,
    uint32_t *out_height)
{
    FILE *input = NULL;
    FILE *output = NULL;
    uint8_t *chunk = NULL;
    UyaRk1106H264Decoder decoder;
    UyaRk1106H264Stats stats;
    int status = UYA_RK1106_H264_DECODER_STATUS_OK;
    int got_eos = 0;

    uya_rk1106_h264_zero_outputs(out_frames, out_bytes_read, out_bytes_written, out_width, out_height);
    memset(&decoder, 0, sizeof(decoder));
    memset(&stats, 0, sizeof(stats));

    if (!input_path || !output_path || chunk_bytes == 0)
        return UYA_RK1106_H264_DECODER_STATUS_INVALID_ARGUMENT;

    input = fopen((const char *)input_path, "rb");
    if (!input)
        return UYA_RK1106_H264_DECODER_STATUS_INPUT_OPEN_FAILED;

    output = fopen((const char *)output_path, "wb");
    if (!output) {
        fclose(input);
        return UYA_RK1106_H264_DECODER_STATUS_OUTPUT_OPEN_FAILED;
    }

    chunk = (uint8_t *)malloc(chunk_bytes);
    if (!chunk) {
        status = UYA_RK1106_H264_DECODER_STATUS_INVALID_ARGUMENT;
        goto out;
    }

    status = uya_rk1106_h264_decoder_open(&decoder, split_parse);
    if (status != UYA_RK1106_H264_DECODER_STATUS_OK)
        goto out;

    while (!uya_rk1106_h264_should_stop(&stats, max_frames)) {
        size_t read_len = fread(chunk, 1, chunk_bytes, input);
        if (read_len > 0) {
            stats.bytes_read += read_len;
            status = uya_rk1106_h264_send_packet_and_drain(
                &decoder,
                output,
                chunk,
                read_len,
                0,
                &stats,
                max_frames,
                &got_eos);
            if (status != UYA_RK1106_H264_DECODER_STATUS_OK)
                goto out;
        }

        if (read_len < chunk_bytes) {
            if (ferror(input)) {
                status = UYA_RK1106_H264_DECODER_STATUS_READ_FAILED;
                goto out;
            }
            break;
        }
    }

    if (!uya_rk1106_h264_should_stop(&stats, max_frames)) {
        status = uya_rk1106_h264_send_packet_and_drain(
            &decoder,
            output,
            chunk,
            0,
            1,
            &stats,
            max_frames,
            &got_eos);
        if (status != UYA_RK1106_H264_DECODER_STATUS_OK)
            goto out;
    }

out:
    if (output && fflush(output) != 0 && status == UYA_RK1106_H264_DECODER_STATUS_OK)
        status = UYA_RK1106_H264_DECODER_STATUS_WRITE_FAILED;
    if (chunk)
        free(chunk);
    uya_rk1106_h264_decoder_close(&decoder);
    if (output)
        fclose(output);
    if (input)
        fclose(input);

    if (status == UYA_RK1106_H264_DECODER_STATUS_OK)
        uya_rk1106_h264_store_outputs(&stats, out_frames, out_bytes_read, out_bytes_written, out_width, out_height);
    else
        uya_rk1106_h264_zero_outputs(out_frames, out_bytes_read, out_bytes_written, out_width, out_height);

    return status;
}

#endif
