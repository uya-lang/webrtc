#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <libavcodec/avcodec.h>
#include <libavutil/channel_layout.h>
#include <libavutil/frame.h>
#include <libavutil/imgutils.h>
#include <libavutil/mem.h>
#include <libavutil/opt.h>
#include <libavutil/pixfmt.h>
#include <libavutil/samplefmt.h>

#define UYA_MEDIA_KIND_AUDIO 1
#define UYA_MEDIA_KIND_VIDEO 2
#define UYA_CODEC_ID_OPUS 1
#define UYA_CODEC_ID_VP8 2

#define UYA_FFMPEG_STATUS_OK 0
#define UYA_FFMPEG_STATUS_UNAVAILABLE -1
#define UYA_FFMPEG_STATUS_INVALID_ARGUMENT -2
#define UYA_FFMPEG_STATUS_UNSUPPORTED_CODEC -3
#define UYA_FFMPEG_STATUS_ENCODE_FAILED -4
#define UYA_FFMPEG_STATUS_DECODE_FAILED -5
#define UYA_FFMPEG_STATUS_OUTPUT_TOO_SMALL -6

typedef struct UyaFfmpegCodecHandle {
    AVCodecContext *ctx;
    AVFrame *frame;
    AVPacket *packet;
    int media_kind;
    int codec_id;
    int is_encoder;
} UyaFfmpegCodecHandle;

static void uya_ffmpeg_codec_handle_free(UyaFfmpegCodecHandle *handle) {
    if (handle == NULL) {
        return;
    }
    if (handle->packet != NULL) {
        av_packet_free(&handle->packet);
    }
    if (handle->frame != NULL) {
        av_frame_free(&handle->frame);
    }
    if (handle->ctx != NULL) {
        avcodec_free_context(&handle->ctx);
    }
    free(handle);
}

static enum AVSampleFormat choose_sample_fmt(const AVCodec *codec) {
    const enum AVSampleFormat *fmt = codec->sample_fmts;
    int i = 0;
    if (fmt == NULL) {
        return AV_SAMPLE_FMT_S16;
    }
    while (fmt[i] != AV_SAMPLE_FMT_NONE) {
        if (fmt[i] == AV_SAMPLE_FMT_S16) {
            return AV_SAMPLE_FMT_S16;
        }
        i++;
    }
    i = 0;
    while (fmt[i] != AV_SAMPLE_FMT_NONE) {
        if (fmt[i] == AV_SAMPLE_FMT_FLT) {
            return AV_SAMPLE_FMT_FLT;
        }
        i++;
    }
    return fmt[0];
}

static int16_t clamp_float_s16(float value) {
    int scaled;
    if (value >= 1.0f) {
        return 32767;
    }
    if (value <= -1.0f) {
        return -32768;
    }
    scaled = (int)(value * 32767.0f);
    if (scaled > 32767) {
        return 32767;
    }
    if (scaled < -32768) {
        return -32768;
    }
    return (int16_t)scaled;
}

static float s16_to_float(int16_t value) {
    return (float)value / 32768.0f;
}

static int handle_receive_packet(UyaFfmpegCodecHandle *handle, uint8_t *out_packet, size_t out_capacity, size_t *out_len) {
    int rc;
    if (handle == NULL || out_packet == NULL || out_len == NULL) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    *out_len = 0;
    av_packet_unref(handle->packet);
    rc = avcodec_receive_packet(handle->ctx, handle->packet);
    if (rc < 0) {
        return UYA_FFMPEG_STATUS_ENCODE_FAILED;
    }
    if ((size_t)handle->packet->size > out_capacity) {
        av_packet_unref(handle->packet);
        return UYA_FFMPEG_STATUS_OUTPUT_TOO_SMALL;
    }
    memcpy(out_packet, handle->packet->data, (size_t)handle->packet->size);
    *out_len = (size_t)handle->packet->size;
    av_packet_unref(handle->packet);
    return UYA_FFMPEG_STATUS_OK;
}

static int audio_channels(const AVCodecContext *ctx, const AVFrame *frame) {
#if LIBAVUTIL_VERSION_MAJOR >= 57
    if (frame != NULL && frame->ch_layout.nb_channels > 0) {
        return frame->ch_layout.nb_channels;
    }
    if (ctx != NULL && ctx->ch_layout.nb_channels > 0) {
        return ctx->ch_layout.nb_channels;
    }
#else
    if (frame != NULL && frame->channels > 0) {
        return frame->channels;
    }
    if (ctx != NULL && ctx->channels > 0) {
        return ctx->channels;
    }
#endif
    return 0;
}

static int fill_audio_frame_from_s16le(UyaFfmpegCodecHandle *handle, const uint8_t *pcm_s16le, size_t pcm_len) {
    AVCodecContext *ctx;
    AVFrame *frame;
    int channels;
    int samples;
    int rc;
    int sample_index;
    int channel_index;
    const int16_t *input;

    if (handle == NULL || pcm_s16le == NULL || pcm_len == 0) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    ctx = handle->ctx;
    frame = handle->frame;
    channels = audio_channels(ctx, NULL);
    if (channels <= 0 || (pcm_len % (size_t)(channels * 2)) != 0) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    samples = (int)(pcm_len / (size_t)(channels * 2));
    input = (const int16_t *)pcm_s16le;

    av_frame_unref(frame);
    frame->nb_samples = samples;
    frame->format = ctx->sample_fmt;
    frame->sample_rate = ctx->sample_rate;
#if LIBAVUTIL_VERSION_MAJOR >= 57
    if (av_channel_layout_copy(&frame->ch_layout, &ctx->ch_layout) < 0) {
        return UYA_FFMPEG_STATUS_ENCODE_FAILED;
    }
#else
    frame->channels = ctx->channels;
    frame->channel_layout = ctx->channel_layout;
#endif
    rc = av_frame_get_buffer(frame, 0);
    if (rc < 0) {
        return UYA_FFMPEG_STATUS_ENCODE_FAILED;
    }
    rc = av_frame_make_writable(frame);
    if (rc < 0) {
        return UYA_FFMPEG_STATUS_ENCODE_FAILED;
    }

    if (ctx->sample_fmt == AV_SAMPLE_FMT_S16) {
        memcpy(frame->data[0], pcm_s16le, pcm_len);
    } else if (ctx->sample_fmt == AV_SAMPLE_FMT_S16P) {
        for (sample_index = 0; sample_index < samples; sample_index++) {
            for (channel_index = 0; channel_index < channels; channel_index++) {
                ((int16_t *)frame->data[channel_index])[sample_index] = input[sample_index * channels + channel_index];
            }
        }
    } else if (ctx->sample_fmt == AV_SAMPLE_FMT_FLT) {
        float *dst = (float *)frame->data[0];
        for (sample_index = 0; sample_index < samples * channels; sample_index++) {
            dst[sample_index] = s16_to_float(input[sample_index]);
        }
    } else if (ctx->sample_fmt == AV_SAMPLE_FMT_FLTP) {
        for (sample_index = 0; sample_index < samples; sample_index++) {
            for (channel_index = 0; channel_index < channels; channel_index++) {
                ((float *)frame->data[channel_index])[sample_index] = s16_to_float(input[sample_index * channels + channel_index]);
            }
        }
    } else {
        return UYA_FFMPEG_STATUS_UNSUPPORTED_CODEC;
    }
    return UYA_FFMPEG_STATUS_OK;
}

static int fill_video_frame_from_i420(UyaFfmpegCodecHandle *handle, const uint8_t *i420, size_t i420_len) {
    AVCodecContext *ctx;
    AVFrame *frame;
    int width;
    int height;
    size_t y_len;
    size_t uv_len;
    const uint8_t *y;
    const uint8_t *u;
    const uint8_t *v;
    int row;
    int rc;

    if (handle == NULL || i420 == NULL || i420_len == 0) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    ctx = handle->ctx;
    frame = handle->frame;
    width = ctx->width;
    height = ctx->height;
    y_len = (size_t)width * (size_t)height;
    uv_len = y_len / 4;
    if (width <= 0 || height <= 0 || i420_len < y_len + uv_len + uv_len) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    y = i420;
    u = i420 + y_len;
    v = u + uv_len;

    av_frame_unref(frame);
    frame->format = AV_PIX_FMT_YUV420P;
    frame->width = width;
    frame->height = height;
    rc = av_frame_get_buffer(frame, 32);
    if (rc < 0) {
        return UYA_FFMPEG_STATUS_ENCODE_FAILED;
    }
    rc = av_frame_make_writable(frame);
    if (rc < 0) {
        return UYA_FFMPEG_STATUS_ENCODE_FAILED;
    }

    for (row = 0; row < height; row++) {
        memcpy(frame->data[0] + (size_t)row * (size_t)frame->linesize[0], y + (size_t)row * (size_t)width, (size_t)width);
    }
    for (row = 0; row < height / 2; row++) {
        memcpy(frame->data[1] + (size_t)row * (size_t)frame->linesize[1], u + (size_t)row * (size_t)(width / 2), (size_t)(width / 2));
        memcpy(frame->data[2] + (size_t)row * (size_t)frame->linesize[2], v + (size_t)row * (size_t)(width / 2), (size_t)(width / 2));
    }
    return UYA_FFMPEG_STATUS_OK;
}

void *uya_ffmpeg_codec_encoder_open(
    uint8_t media_kind,
    uint16_t codec_id,
    uint32_t sample_rate_hz,
    uint8_t channels,
    uint32_t width,
    uint32_t height,
    uint32_t bitrate_bps,
    uint32_t fps_num,
    uint32_t fps_den
) {
    UyaFfmpegCodecHandle *handle;
    const AVCodec *codec;
    AVCodecContext *ctx;

    codec = NULL;
    if (media_kind == UYA_MEDIA_KIND_AUDIO && codec_id == UYA_CODEC_ID_OPUS) {
        codec = avcodec_find_encoder_by_name("libopus");
        if (codec == NULL) {
            codec = avcodec_find_encoder(AV_CODEC_ID_OPUS);
        }
    } else if (media_kind == UYA_MEDIA_KIND_VIDEO && codec_id == UYA_CODEC_ID_VP8) {
        codec = avcodec_find_encoder_by_name("libvpx");
        if (codec == NULL) {
            codec = avcodec_find_encoder(AV_CODEC_ID_VP8);
        }
    } else {
        return NULL;
    }
    if (codec == NULL) {
        return NULL;
    }

    handle = (UyaFfmpegCodecHandle *)calloc(1, sizeof(UyaFfmpegCodecHandle));
    if (handle == NULL) {
        return NULL;
    }
    ctx = avcodec_alloc_context3(codec);
    handle->ctx = ctx;
    handle->frame = av_frame_alloc();
    handle->packet = av_packet_alloc();
    handle->media_kind = media_kind;
    handle->codec_id = codec_id;
    handle->is_encoder = 1;
    if (ctx == NULL || handle->frame == NULL || handle->packet == NULL) {
        uya_ffmpeg_codec_handle_free(handle);
        return NULL;
    }

    if (media_kind == UYA_MEDIA_KIND_AUDIO) {
        ctx->sample_rate = (int)sample_rate_hz;
        ctx->sample_fmt = choose_sample_fmt(codec);
        ctx->bit_rate = bitrate_bps == 0 ? 96000 : (int64_t)bitrate_bps;
        ctx->time_base.num = 1;
        ctx->time_base.den = (int)sample_rate_hz;
#if LIBAVUTIL_VERSION_MAJOR >= 57
        av_channel_layout_default(&ctx->ch_layout, channels);
#else
        ctx->channels = channels;
        ctx->channel_layout = av_get_default_channel_layout(channels);
#endif
        if (ctx->priv_data != NULL) {
            av_opt_set(ctx->priv_data, "application", "audio", 0);
            av_opt_set_int(ctx->priv_data, "frame_duration", 20, 0);
            av_opt_set(ctx->priv_data, "vbr", "off", 0);
        }
    } else {
        if (fps_num == 0 || fps_den == 0 || width == 0 || height == 0) {
            uya_ffmpeg_codec_handle_free(handle);
            return NULL;
        }
        ctx->width = (int)width;
        ctx->height = (int)height;
        ctx->pix_fmt = AV_PIX_FMT_YUV420P;
        ctx->time_base.num = (int)fps_den;
        ctx->time_base.den = (int)fps_num;
        ctx->framerate.num = (int)fps_num;
        ctx->framerate.den = (int)fps_den;
        ctx->bit_rate = bitrate_bps == 0 ? 2000000 : (int64_t)bitrate_bps;
        ctx->gop_size = 30;
        ctx->max_b_frames = 0;
        ctx->flags |= AV_CODEC_FLAG_LOW_DELAY;
        if (ctx->priv_data != NULL) {
            av_opt_set(ctx->priv_data, "deadline", "realtime", 0);
            av_opt_set(ctx->priv_data, "cpu-used", "8", 0);
        }
    }

    if (avcodec_open2(ctx, codec, NULL) < 0) {
        uya_ffmpeg_codec_handle_free(handle);
        return NULL;
    }
    return handle;
}

void uya_ffmpeg_codec_encoder_close(void *handle) {
    uya_ffmpeg_codec_handle_free((UyaFfmpegCodecHandle *)handle);
}

void *uya_ffmpeg_codec_decoder_open(
    uint8_t media_kind,
    uint16_t codec_id,
    uint32_t sample_rate_hz,
    uint8_t channels,
    uint32_t width,
    uint32_t height
) {
    UyaFfmpegCodecHandle *handle;
    const AVCodec *codec;
    AVCodecContext *ctx;

    codec = NULL;
    if (media_kind == UYA_MEDIA_KIND_AUDIO && codec_id == UYA_CODEC_ID_OPUS) {
        codec = avcodec_find_decoder(AV_CODEC_ID_OPUS);
    } else if (media_kind == UYA_MEDIA_KIND_VIDEO && codec_id == UYA_CODEC_ID_VP8) {
        codec = avcodec_find_decoder(AV_CODEC_ID_VP8);
    } else {
        return NULL;
    }
    if (codec == NULL) {
        return NULL;
    }

    handle = (UyaFfmpegCodecHandle *)calloc(1, sizeof(UyaFfmpegCodecHandle));
    if (handle == NULL) {
        return NULL;
    }
    ctx = avcodec_alloc_context3(codec);
    handle->ctx = ctx;
    handle->frame = av_frame_alloc();
    handle->packet = av_packet_alloc();
    handle->media_kind = media_kind;
    handle->codec_id = codec_id;
    handle->is_encoder = 0;
    if (ctx == NULL || handle->frame == NULL || handle->packet == NULL) {
        uya_ffmpeg_codec_handle_free(handle);
        return NULL;
    }

    if (media_kind == UYA_MEDIA_KIND_AUDIO) {
        ctx->sample_rate = (int)sample_rate_hz;
#if LIBAVUTIL_VERSION_MAJOR >= 57
        av_channel_layout_default(&ctx->ch_layout, channels);
#else
        ctx->channels = channels;
        ctx->channel_layout = av_get_default_channel_layout(channels);
#endif
    } else {
        ctx->width = (int)width;
        ctx->height = (int)height;
        ctx->pix_fmt = AV_PIX_FMT_YUV420P;
    }

    if (avcodec_open2(ctx, codec, NULL) < 0) {
        uya_ffmpeg_codec_handle_free(handle);
        return NULL;
    }
    return handle;
}

void uya_ffmpeg_codec_decoder_close(void *handle) {
    uya_ffmpeg_codec_handle_free((UyaFfmpegCodecHandle *)handle);
}

int32_t uya_ffmpeg_codec_encode_audio(
    void *handle_raw,
    const uint8_t *pcm_s16le,
    size_t pcm_len,
    uint64_t timestamp_us,
    uint32_t duration_us,
    uint8_t *out_packet,
    size_t out_capacity,
    size_t *out_len
) {
    UyaFfmpegCodecHandle *handle = (UyaFfmpegCodecHandle *)handle_raw;
    int rc;
    if (handle == NULL || handle->ctx == NULL || !handle->is_encoder || handle->media_kind != UYA_MEDIA_KIND_AUDIO ||
        pcm_s16le == NULL || out_packet == NULL || out_len == NULL || duration_us == 0) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    rc = fill_audio_frame_from_s16le(handle, pcm_s16le, pcm_len);
    if (rc != UYA_FFMPEG_STATUS_OK) {
        return rc;
    }
    handle->frame->pts = (int64_t)((timestamp_us * (uint64_t)handle->ctx->sample_rate) / 1000000ULL);
    if (avcodec_send_frame(handle->ctx, handle->frame) < 0) {
        return UYA_FFMPEG_STATUS_ENCODE_FAILED;
    }
    return handle_receive_packet(handle, out_packet, out_capacity, out_len);
}

int32_t uya_ffmpeg_codec_encode_video_i420(
    void *handle_raw,
    const uint8_t *i420,
    size_t i420_len,
    uint64_t timestamp_us,
    uint32_t duration_us,
    uint8_t *out_packet,
    size_t out_capacity,
    size_t *out_len,
    int32_t *out_keyframe
) {
    UyaFfmpegCodecHandle *handle = (UyaFfmpegCodecHandle *)handle_raw;
    int rc;
    (void)duration_us;
    if (handle == NULL || handle->ctx == NULL || !handle->is_encoder || handle->media_kind != UYA_MEDIA_KIND_VIDEO ||
        i420 == NULL || out_packet == NULL || out_len == NULL || out_keyframe == NULL) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    rc = fill_video_frame_from_i420(handle, i420, i420_len);
    if (rc != UYA_FFMPEG_STATUS_OK) {
        return rc;
    }
    handle->frame->pts = (int64_t)((timestamp_us * (uint64_t)handle->ctx->time_base.den) / ((uint64_t)handle->ctx->time_base.num * 1000000ULL));
    if (avcodec_send_frame(handle->ctx, handle->frame) < 0) {
        return UYA_FFMPEG_STATUS_ENCODE_FAILED;
    }
    *out_keyframe = 0;
    av_packet_unref(handle->packet);
    rc = avcodec_receive_packet(handle->ctx, handle->packet);
    if (rc < 0) {
        return UYA_FFMPEG_STATUS_ENCODE_FAILED;
    }
    if ((size_t)handle->packet->size > out_capacity) {
        av_packet_unref(handle->packet);
        return UYA_FFMPEG_STATUS_OUTPUT_TOO_SMALL;
    }
    memcpy(out_packet, handle->packet->data, (size_t)handle->packet->size);
    *out_len = (size_t)handle->packet->size;
    *out_keyframe = (handle->packet->flags & AV_PKT_FLAG_KEY) != 0 ? 1 : 0;
    av_packet_unref(handle->packet);
    return UYA_FFMPEG_STATUS_OK;
}

static int copy_audio_frame_to_s16le(AVCodecContext *ctx, AVFrame *frame, uint8_t *out_pcm_s16le, size_t out_capacity, size_t *out_len) {
    int channels = audio_channels(ctx, frame);
    int samples;
    int sample_index;
    int channel_index;
    size_t required;
    enum AVSampleFormat fmt;
    if (frame == NULL || out_pcm_s16le == NULL || out_len == NULL || channels <= 0) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    samples = frame->nb_samples;
    required = (size_t)samples * (size_t)channels * 2U;
    if (required > out_capacity) {
        return UYA_FFMPEG_STATUS_OUTPUT_TOO_SMALL;
    }
    fmt = (enum AVSampleFormat)frame->format;
    if (fmt == AV_SAMPLE_FMT_S16) {
        memcpy(out_pcm_s16le, frame->data[0], required);
    } else if (fmt == AV_SAMPLE_FMT_S16P) {
        int16_t *dst = (int16_t *)out_pcm_s16le;
        for (sample_index = 0; sample_index < samples; sample_index++) {
            for (channel_index = 0; channel_index < channels; channel_index++) {
                dst[sample_index * channels + channel_index] = ((int16_t *)frame->data[channel_index])[sample_index];
            }
        }
    } else if (fmt == AV_SAMPLE_FMT_FLT) {
        float *src = (float *)frame->data[0];
        int16_t *dst = (int16_t *)out_pcm_s16le;
        for (sample_index = 0; sample_index < samples * channels; sample_index++) {
            dst[sample_index] = clamp_float_s16(src[sample_index]);
        }
    } else if (fmt == AV_SAMPLE_FMT_FLTP) {
        int16_t *dst = (int16_t *)out_pcm_s16le;
        for (sample_index = 0; sample_index < samples; sample_index++) {
            for (channel_index = 0; channel_index < channels; channel_index++) {
                dst[sample_index * channels + channel_index] = clamp_float_s16(((float *)frame->data[channel_index])[sample_index]);
            }
        }
    } else {
        return UYA_FFMPEG_STATUS_UNSUPPORTED_CODEC;
    }
    *out_len = required;
    return UYA_FFMPEG_STATUS_OK;
}

int32_t uya_ffmpeg_codec_decode_audio(
    void *handle_raw,
    const uint8_t *packet,
    size_t packet_len,
    uint8_t *out_pcm_s16le,
    size_t out_capacity,
    size_t *out_len
) {
    UyaFfmpegCodecHandle *handle = (UyaFfmpegCodecHandle *)handle_raw;
    int rc;
    if (handle == NULL || handle->ctx == NULL || handle->is_encoder || handle->media_kind != UYA_MEDIA_KIND_AUDIO ||
        packet == NULL || packet_len == 0 || out_pcm_s16le == NULL || out_len == NULL) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    *out_len = 0;
    av_packet_unref(handle->packet);
    if (av_new_packet(handle->packet, (int)packet_len) < 0) {
        return UYA_FFMPEG_STATUS_DECODE_FAILED;
    }
    memcpy(handle->packet->data, packet, packet_len);
    if (avcodec_send_packet(handle->ctx, handle->packet) < 0) {
        av_packet_unref(handle->packet);
        return UYA_FFMPEG_STATUS_DECODE_FAILED;
    }
    av_packet_unref(handle->packet);
    av_frame_unref(handle->frame);
    rc = avcodec_receive_frame(handle->ctx, handle->frame);
    if (rc < 0) {
        return UYA_FFMPEG_STATUS_DECODE_FAILED;
    }
    return copy_audio_frame_to_s16le(handle->ctx, handle->frame, out_pcm_s16le, out_capacity, out_len);
}

int32_t uya_ffmpeg_codec_decode_video_i420(
    void *handle_raw,
    const uint8_t *packet,
    size_t packet_len,
    uint8_t *out_i420,
    size_t out_capacity,
    size_t *out_len
) {
    UyaFfmpegCodecHandle *handle = (UyaFfmpegCodecHandle *)handle_raw;
    int rc;
    int row;
    size_t y_len;
    size_t uv_len;
    if (handle == NULL || handle->ctx == NULL || handle->is_encoder || handle->media_kind != UYA_MEDIA_KIND_VIDEO ||
        packet == NULL || packet_len == 0 || out_i420 == NULL || out_len == NULL) {
        return UYA_FFMPEG_STATUS_INVALID_ARGUMENT;
    }
    *out_len = 0;
    av_packet_unref(handle->packet);
    if (av_new_packet(handle->packet, (int)packet_len) < 0) {
        return UYA_FFMPEG_STATUS_DECODE_FAILED;
    }
    memcpy(handle->packet->data, packet, packet_len);
    if (avcodec_send_packet(handle->ctx, handle->packet) < 0) {
        av_packet_unref(handle->packet);
        return UYA_FFMPEG_STATUS_DECODE_FAILED;
    }
    av_packet_unref(handle->packet);
    av_frame_unref(handle->frame);
    rc = avcodec_receive_frame(handle->ctx, handle->frame);
    if (rc < 0 || handle->frame->format != AV_PIX_FMT_YUV420P) {
        return UYA_FFMPEG_STATUS_DECODE_FAILED;
    }
    y_len = (size_t)handle->frame->width * (size_t)handle->frame->height;
    uv_len = y_len / 4U;
    if (y_len + uv_len + uv_len > out_capacity) {
        return UYA_FFMPEG_STATUS_OUTPUT_TOO_SMALL;
    }
    for (row = 0; row < handle->frame->height; row++) {
        memcpy(out_i420 + (size_t)row * (size_t)handle->frame->width,
               handle->frame->data[0] + (size_t)row * (size_t)handle->frame->linesize[0],
               (size_t)handle->frame->width);
    }
    for (row = 0; row < handle->frame->height / 2; row++) {
        memcpy(out_i420 + y_len + (size_t)row * (size_t)(handle->frame->width / 2),
               handle->frame->data[1] + (size_t)row * (size_t)handle->frame->linesize[1],
               (size_t)(handle->frame->width / 2));
        memcpy(out_i420 + y_len + uv_len + (size_t)row * (size_t)(handle->frame->width / 2),
               handle->frame->data[2] + (size_t)row * (size_t)handle->frame->linesize[2],
               (size_t)(handle->frame->width / 2));
    }
    *out_len = y_len + uv_len + uv_len;
    return UYA_FFMPEG_STATUS_OK;
}
