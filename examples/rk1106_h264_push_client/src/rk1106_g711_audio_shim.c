#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#define UYA_RK1106_AUDIO_PCM_DUMP_DEFAULT_PATH "/userdata/sender.pcm"

#define UYA_RK1106_G711_AUDIO_STATUS_OK 0
#define UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT -1
#define UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED -2
#define UYA_RK1106_G711_AUDIO_STATUS_READ_FAILED -3
#define UYA_RK1106_G711_AUDIO_STATUS_BUFFER_TOO_SMALL -4
#define UYA_RK1106_G711_AUDIO_STATUS_UNSUPPORTED_CODEC -5

#define UYA_RK1106_G711_AUDIO_CODEC_PCMU 8
#define UYA_RK1106_G711_AUDIO_CODEC_PCMA 9

int uya_rk1106_g711_audio_open(
    uint32_t codec_id,
    uint32_t sample_rate,
    uint32_t channels,
    uint32_t frame_samples,
    size_t *out_handle);
int uya_rk1106_g711_audio_read_packet(
    size_t handle,
    unsigned char *out_payload,
    size_t out_capacity,
    size_t *out_len,
    uint64_t *out_pts_us);
int uya_rk1106_g711_audio_close(size_t handle);

static FILE *uya_rk1106_g711_pcm_dump_open(void)
{
    const char *path = getenv("UYA_RK1106_AUDIO_PCM_DUMP_PATH");
    FILE *file;

    if (!path || !path[0])
        path = UYA_RK1106_AUDIO_PCM_DUMP_DEFAULT_PATH;
    file = fopen(path, "wb");
    if (file)
        fprintf(stderr, "rk1106_g711_audio_shim: PCM dump -> %s\n", path);
    else
        fprintf(stderr, "rk1106_g711_audio_shim: failed to open PCM dump %s\n", path);
    return file;
}

static void uya_rk1106_g711_pcm_dump_write(FILE *file, const void *data, size_t len)
{
    if (!file || !data || len == 0)
        return;
    if (fwrite(data, 1, len, file) != len)
        fprintf(stderr, "rk1106_g711_audio_shim: PCM dump write failed\n");
    fflush(file);
}

static void uya_rk1106_g711_pcm_dump_silence(FILE *file, uint32_t frame_samples, uint32_t channels)
{
    size_t bytes;
    unsigned char *zeros;

    if (!file || frame_samples == 0 || channels == 0)
        return;
    bytes = (size_t)frame_samples * (size_t)channels * sizeof(int16_t);
    zeros = (unsigned char *)calloc(1, bytes);
    if (!zeros)
        return;
    uya_rk1106_g711_pcm_dump_write(file, zeros, bytes);
    free(zeros);
}

static int uya_rk1106_g711_env_enabled(const char *name)
{
    const char *value = getenv(name);
    if (!value || !value[0])
        return 0;
    if (strcmp(value, "0") == 0 || strcmp(value, "false") == 0 || strcmp(value, "False") == 0 ||
        strcmp(value, "FALSE") == 0 || strcmp(value, "no") == 0 || strcmp(value, "No") == 0 ||
        strcmp(value, "NO") == 0)
        return 0;
    return 1;
}

static int uya_rk1106_g711_fill_silence_packet(
    uint32_t codec_id,
    uint32_t sample_rate,
    uint32_t frame_samples,
    uint64_t *pts_us,
    unsigned char *out_payload,
    size_t out_capacity,
    size_t *out_len,
    uint64_t *out_pts_us)
{
    size_t index;
    unsigned char silence;

    if (!out_payload || !out_len || !out_pts_us || !pts_us)
        return UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT;
    if (out_capacity < frame_samples)
        return UYA_RK1106_G711_AUDIO_STATUS_BUFFER_TOO_SMALL;

    silence = codec_id == UYA_RK1106_G711_AUDIO_CODEC_PCMU ? 0xffu : 0xd5u;
    for (index = 0; index < frame_samples; index++)
        out_payload[index] = silence;
    *out_len = frame_samples;
    *out_pts_us = *pts_us;
    *pts_us += ((uint64_t)frame_samples * 1000000ULL) / sample_rate;
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

#if defined(UYA_RK1106_G711_AUDIO_ENABLE_MPI) || defined(UYA_RK1106_G711_AUDIO_STATIC_MPI)

#include "rk_common.h"
#include "rk_comm_aio.h"
#include "rk_comm_aenc.h"
#include "rk_mpi_ai.h"
#include "rk_mpi_aenc.h"
#include "rk_mpi_mb.h"
#include "rk_mpi_sys.h"

typedef RK_S32 (*uya_rk_sys_init_fn)(RK_VOID);
typedef RK_S32 (*uya_rk_sys_exit_fn)(RK_VOID);
typedef RK_S32 (*uya_rk_sys_bind_fn)(const MPP_CHN_S *, const MPP_CHN_S *);
typedef RK_S32 (*uya_rk_ai_set_pub_attr_fn)(AUDIO_DEV, const AIO_ATTR_S *);
typedef RK_S32 (*uya_rk_ai_enable_fn)(AUDIO_DEV);
typedef RK_S32 (*uya_rk_ai_disable_fn)(AUDIO_DEV);
typedef RK_S32 (*uya_rk_ai_enable_chn_fn)(AUDIO_DEV, AI_CHN);
typedef RK_S32 (*uya_rk_ai_disable_chn_fn)(AUDIO_DEV, AI_CHN);
typedef RK_S32 (*uya_rk_ai_set_chn_param_fn)(AUDIO_DEV, AI_CHN, const AI_CHN_PARAM_S *);
typedef RK_S32 (*uya_rk_ai_set_track_mode_fn)(AUDIO_DEV, AUDIO_TRACK_MODE_E);
typedef RK_S32 (*uya_rk_aenc_create_chn_fn)(AENC_CHN, const AENC_CHN_ATTR_S *);
typedef RK_S32 (*uya_rk_aenc_destroy_chn_fn)(AENC_CHN);
typedef RK_S32 (*uya_rk_aenc_get_stream_fn)(AENC_CHN, AUDIO_STREAM_S *, RK_S32);
typedef RK_S32 (*uya_rk_aenc_release_stream_fn)(AENC_CHN, const AUDIO_STREAM_S *);
typedef RK_S32 (*uya_rk_ai_save_file_fn)(AUDIO_DEV, AI_CHN, const AUDIO_SAVE_FILE_INFO_S *);
typedef RK_VOID *(*uya_rk_mb_handle_to_addr_fn)(MB_BLK);

typedef struct UyaRkMpiAudioApi {
    void *lib;
    uya_rk_sys_init_fn sys_init;
    uya_rk_sys_exit_fn sys_exit;
    uya_rk_sys_bind_fn sys_bind;
    uya_rk_sys_bind_fn sys_unbind;
    uya_rk_ai_set_pub_attr_fn ai_set_pub_attr;
    uya_rk_ai_enable_fn ai_enable;
    uya_rk_ai_disable_fn ai_disable;
    uya_rk_ai_enable_chn_fn ai_enable_chn;
    uya_rk_ai_disable_chn_fn ai_disable_chn;
    uya_rk_ai_set_chn_param_fn ai_set_chn_param;
    uya_rk_ai_set_track_mode_fn ai_set_track_mode;
    uya_rk_aenc_create_chn_fn aenc_create_chn;
    uya_rk_aenc_destroy_chn_fn aenc_destroy_chn;
    uya_rk_aenc_get_stream_fn aenc_get_stream;
    uya_rk_aenc_release_stream_fn aenc_release_stream;
    uya_rk_ai_save_file_fn ai_save_file;
    uya_rk_mb_handle_to_addr_fn mb_handle_to_addr;
} UyaRkMpiAudioApi;

typedef struct UyaRk1106G711Audio {
    UyaRkMpiAudioApi api;
    AUDIO_DEV ai_dev;
    AI_CHN ai_chn;
    AENC_CHN aenc_chn;
    uint32_t codec_id;
    uint32_t sample_rate;
    uint32_t channels;
    uint32_t frame_samples;
    uint64_t fallback_pts_us;
    int synthetic_silence;
    int sys_inited;
    int ai_enabled;
    int ai_chn_enabled;
    int aenc_created;
    int bound;
    int pcm_save_enabled;
    FILE *pcm_dump;
} UyaRk1106G711Audio;

static int16_t uya_rk1106_g711_ulaw_decode(unsigned char ulaw)
{
    int sign;
    int exponent;
    int mantissa;
    int sample;

    ulaw = (unsigned char)~ulaw;
    sign = (ulaw & 0x80) ? -1 : 1;
    exponent = (ulaw >> 4) & 0x07;
    mantissa = ulaw & 0x0F;
    sample = ((mantissa << 3) + 0x84) << exponent;
    sample = (sample - 0x84) * sign;
    return (int16_t)sample;
}

static int16_t uya_rk1106_g711_alaw_decode(unsigned char alaw)
{
    int sign;
    int exponent;
    int mantissa;
    int sample;

    alaw ^= 0x55u;
    sign = (alaw & 0x80) ? -1 : 1;
    exponent = (alaw >> 4) & 0x07;
    mantissa = alaw & 0x0F;
    if (exponent == 0)
        sample = (mantissa << 4) + 8;
    else
        sample = ((mantissa << 4) + 0x108) << (exponent - 1);
    return (int16_t)(sample * sign);
}

static void uya_rk1106_g711_pcm_dump_g711_frame(
    FILE *file,
    uint32_t codec_id,
    const unsigned char *payload,
    size_t len)
{
    size_t index;
    int16_t sample;

    if (!file || !payload || len == 0)
        return;
    for (index = 0; index < len; index++) {
        if (codec_id == UYA_RK1106_G711_AUDIO_CODEC_PCMU)
            sample = uya_rk1106_g711_ulaw_decode(payload[index]);
        else
            sample = uya_rk1106_g711_alaw_decode(payload[index]);
        if (fwrite(&sample, sizeof(sample), 1, file) != 1) {
            fprintf(stderr, "rk1106_g711_audio_shim: PCM dump write failed\n");
            return;
        }
    }
    fflush(file);
}

static int uya_rk1106_g711_codec_to_rk(uint32_t codec_id, RK_CODEC_ID_E *out_type)
{
    if (!out_type)
        return UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT;
    if (codec_id == UYA_RK1106_G711_AUDIO_CODEC_PCMU) {
        *out_type = RK_AUDIO_ID_PCM_MULAW;
        return UYA_RK1106_G711_AUDIO_STATUS_OK;
    }
    if (codec_id == UYA_RK1106_G711_AUDIO_CODEC_PCMA) {
        *out_type = RK_AUDIO_ID_PCM_ALAW;
        return UYA_RK1106_G711_AUDIO_STATUS_OK;
    }
    return UYA_RK1106_G711_AUDIO_STATUS_UNSUPPORTED_CODEC;
}

#if defined(UYA_RK1106_G711_AUDIO_STATIC_MPI)

static int uya_rk1106_g711_load_api(UyaRkMpiAudioApi *api)
{
    if (!api)
        return UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT;
    memset(api, 0, sizeof(*api));
    api->sys_init = (uya_rk_sys_init_fn)RK_MPI_SYS_Init;
    api->sys_exit = (uya_rk_sys_exit_fn)RK_MPI_SYS_Exit;
    api->sys_bind = (uya_rk_sys_bind_fn)RK_MPI_SYS_Bind;
    api->sys_unbind = (uya_rk_sys_bind_fn)RK_MPI_SYS_UnBind;
    api->ai_set_pub_attr = (uya_rk_ai_set_pub_attr_fn)RK_MPI_AI_SetPubAttr;
    api->ai_enable = (uya_rk_ai_enable_fn)RK_MPI_AI_Enable;
    api->ai_disable = (uya_rk_ai_disable_fn)RK_MPI_AI_Disable;
    api->ai_enable_chn = (uya_rk_ai_enable_chn_fn)RK_MPI_AI_EnableChn;
    api->ai_disable_chn = (uya_rk_ai_disable_chn_fn)RK_MPI_AI_DisableChn;
    api->ai_set_chn_param = (uya_rk_ai_set_chn_param_fn)RK_MPI_AI_SetChnParam;
    api->ai_set_track_mode = (uya_rk_ai_set_track_mode_fn)RK_MPI_AI_SetTrackMode;
    api->aenc_create_chn = (uya_rk_aenc_create_chn_fn)RK_MPI_AENC_CreateChn;
    api->aenc_destroy_chn = (uya_rk_aenc_destroy_chn_fn)RK_MPI_AENC_DestroyChn;
    api->aenc_get_stream = (uya_rk_aenc_get_stream_fn)RK_MPI_AENC_GetStream;
    api->aenc_release_stream = (uya_rk_aenc_release_stream_fn)RK_MPI_AENC_ReleaseStream;
    api->ai_save_file = (uya_rk_ai_save_file_fn)RK_MPI_AI_SaveFile;
    api->mb_handle_to_addr = (uya_rk_mb_handle_to_addr_fn)RK_MPI_MB_Handle2VirAddr;
    fprintf(stderr, "rk1106_g711_audio_shim: using static Rockchip MPI audio symbols\n");
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

#else

#include <dlfcn.h>

static void *uya_rk1106_g711_dlsym(void *lib, const char *name)
{
    void *sym = NULL;
#ifdef RTLD_DEFAULT
    sym = dlsym(RTLD_DEFAULT, name);
#endif
    if (!sym && lib)
        sym = dlsym(lib, name);
    return sym;
}

static void *uya_rk1106_g711_open_mpi_library(void)
{
    const char *override = getenv("UYA_RK1106_MPI_LIB");
    const char *libs[] = {
        "./lib/librockit.so",
        "/userdata/rk1106-h264-push-client/lib/librockit.so",
        "/userdata/lib/librockit.so",
        "/oem/usr/lib/librockit.so",
        "/oem/lib/librockit.so",
        "librockit.so",
        "librockit.so.0",
        "/usr/lib/librockit.so",
        "/usr/lib/librockit.so.0",
        "./lib/librockchip_mpp.so",
        "/userdata/rk1106-h264-push-client/lib/librockchip_mpp.so",
        "/userdata/rk1106-h264-push-client/lib/librockchip_mpp.so.1",
        "/userdata/lib/librockchip_mpp.so",
        "/userdata/lib/librockchip_mpp.so.1",
        "/oem/usr/lib/librockchip_mpp.so",
        "/oem/usr/lib/librockchip_mpp.so.1",
        "/oem/lib/librockchip_mpp.so",
        "/oem/lib/librockchip_mpp.so.1",
        "librockchip_mpp.so",
        "librockchip_mpp.so.1",
        "librockchip_mpp.so.0",
        "/usr/lib/librockchip_mpp.so",
        "/usr/lib/librockchip_mpp.so.1",
        "/usr/lib/librockchip_mpp.so.0",
        NULL,
    };
    int index;
    void *lib;

    if (override && override[0]) {
        lib = dlopen(override, RTLD_NOW | RTLD_GLOBAL);
        if (lib)
            return lib;
        fprintf(stderr, "rk1106_g711_audio_shim: dlopen %s failed: %s\n", override, dlerror());
    }

    for (index = 0; libs[index]; index++) {
        lib = dlopen(libs[index], RTLD_NOW | RTLD_GLOBAL);
        if (lib) {
            fprintf(stderr, "rk1106_g711_audio_shim: dlopen %s ok\n", libs[index]);
            return lib;
        }
        fprintf(stderr, "rk1106_g711_audio_shim: dlopen %s failed: %s\n", libs[index], dlerror());
    }
    fprintf(stderr, "rk1106_g711_audio_shim: failed to dlopen Rockchip MPI library\n");
    return NULL;
}

static int uya_rk1106_g711_load_api(UyaRkMpiAudioApi *api)
{
    if (!api)
        return UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT;
    memset(api, 0, sizeof(*api));
    api->lib = uya_rk1106_g711_open_mpi_library();
    if (!api->lib)
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;

    api->sys_init = (uya_rk_sys_init_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_SYS_Init");
    api->sys_exit = (uya_rk_sys_exit_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_SYS_Exit");
    api->sys_bind = (uya_rk_sys_bind_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_SYS_Bind");
    api->sys_unbind = (uya_rk_sys_bind_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_SYS_UnBind");
    api->ai_set_pub_attr = (uya_rk_ai_set_pub_attr_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AI_SetPubAttr");
    api->ai_enable = (uya_rk_ai_enable_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AI_Enable");
    api->ai_disable = (uya_rk_ai_disable_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AI_Disable");
    api->ai_enable_chn = (uya_rk_ai_enable_chn_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AI_EnableChn");
    api->ai_disable_chn = (uya_rk_ai_disable_chn_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AI_DisableChn");
    api->ai_set_chn_param = (uya_rk_ai_set_chn_param_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AI_SetChnParam");
    api->ai_set_track_mode = (uya_rk_ai_set_track_mode_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AI_SetTrackMode");
    api->aenc_create_chn = (uya_rk_aenc_create_chn_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AENC_CreateChn");
    api->aenc_destroy_chn = (uya_rk_aenc_destroy_chn_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AENC_DestroyChn");
    api->aenc_get_stream = (uya_rk_aenc_get_stream_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AENC_GetStream");
    api->aenc_release_stream = (uya_rk_aenc_release_stream_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AENC_ReleaseStream");
    api->ai_save_file = (uya_rk_ai_save_file_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_AI_SaveFile");
    api->mb_handle_to_addr = (uya_rk_mb_handle_to_addr_fn)uya_rk1106_g711_dlsym(api->lib, "RK_MPI_MB_Handle2VirAddr");

    if (!api->sys_init || !api->sys_exit || !api->sys_bind || !api->sys_unbind ||
        !api->ai_set_pub_attr || !api->ai_enable || !api->ai_disable ||
        !api->ai_enable_chn || !api->ai_disable_chn || !api->ai_set_chn_param ||
        !api->ai_set_track_mode || !api->aenc_create_chn || !api->aenc_destroy_chn ||
        !api->aenc_get_stream || !api->aenc_release_stream ||
        !api->ai_save_file || !api->mb_handle_to_addr) {
        fprintf(stderr, "rk1106_g711_audio_shim: missing Rockchip MPI audio symbols\n");
        dlclose(api->lib);
        memset(api, 0, sizeof(*api));
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    }
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

#endif

static int uya_rk1106_g711_check(int rc, const char *what)
{
    if (rc == RK_SUCCESS)
        return UYA_RK1106_G711_AUDIO_STATUS_OK;
    fprintf(stderr, "rk1106_g711_audio_shim: %s failed rc=0x%08x\n", what, rc);
    return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
}

static void uya_rk1106_g711_fill_ai_attr(AIO_ATTR_S *attr, uint32_t sample_rate, uint32_t channels, uint32_t frame_samples)
{
    const char *card = getenv("UYA_RK1106_AI_CARD");
    if (!card || !card[0])
        card = "hw:0,0";
    memset(attr, 0, sizeof(*attr));
    snprintf((char *)attr->u8CardName, sizeof(attr->u8CardName), "%s", card);
    attr->soundCard.channels = 2;
    attr->soundCard.sampleRate = sample_rate;
    attr->soundCard.bitWidth = AUDIO_BIT_WIDTH_16;
    attr->enSamplerate = (AUDIO_SAMPLE_RATE_E)sample_rate;
    attr->enBitwidth = AUDIO_BIT_WIDTH_16;
    attr->enSoundmode = channels == 1 ? AUDIO_SOUND_MODE_MONO : AUDIO_SOUND_MODE_STEREO;
    attr->u32FrmNum = 4;
    attr->u32PtNumPerFrm = frame_samples;
    attr->u32EXFlag = 0;
    attr->u32ChnCnt = 2;
}

static void uya_rk1106_g711_split_pcm_path(
    const char *full_path,
    char *dir,
    size_t dir_sz,
    char *name,
    size_t name_sz)
{
    const char *slash;

    if (!full_path || !full_path[0] || !dir || !name || dir_sz == 0 || name_sz == 0)
        return;
    slash = strrchr(full_path, '/');
    if (!slash) {
        snprintf(dir, dir_sz, ".");
        snprintf(name, name_sz, "%s", full_path);
        return;
    }
    if (slash == full_path) {
        snprintf(dir, dir_sz, "/");
        snprintf(name, name_sz, "%s", slash + 1);
        return;
    }
    snprintf(dir, dir_sz, "%.*s", (int)(slash - full_path), full_path);
    snprintf(name, name_sz, "%s", slash + 1);
}

static int uya_rk1106_g711_start_pcm_save(UyaRk1106G711Audio *audio)
{
    const char *full_path = getenv("UYA_RK1106_AUDIO_PCM_DUMP_PATH");
    AUDIO_SAVE_FILE_INFO_S save;
    char dir[MAX_AUDIO_FILE_PATH_LEN];
    char name[MAX_AUDIO_FILE_NAME_LEN];
    int rc;

    if (!audio || !audio->api.ai_save_file)
        return UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT;
    if (!full_path || !full_path[0])
        full_path = UYA_RK1106_AUDIO_PCM_DUMP_DEFAULT_PATH;

    uya_rk1106_g711_split_pcm_path(full_path, dir, sizeof(dir), name, sizeof(name));
    memset(&save, 0, sizeof(save));
    save.bCfg = RK_TRUE;
    save.u32FileSize = 65536;
    snprintf((char *)save.aFilePath, sizeof(save.aFilePath), "%s", dir);
    snprintf((char *)save.aFileName, sizeof(save.aFileName), "%s", name);
    rc = audio->api.ai_save_file(audio->ai_dev, audio->ai_chn, &save);
    if (rc != RK_SUCCESS) {
        fprintf(stderr, "rk1106_g711_audio_shim: RK_MPI_AI_SaveFile failed rc=0x%08x path=%s/%s\n",
            rc, dir, name);
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    }
    audio->pcm_save_enabled = 1;
    fprintf(stderr, "rk1106_g711_audio_shim: PCM save via MPI -> %s/%s\n", dir, name);
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

static void uya_rk1106_g711_fill_aenc_attr(AENC_CHN_ATTR_S *attr, RK_CODEC_ID_E type, uint32_t sample_rate, uint32_t channels)
{
    memset(attr, 0, sizeof(*attr));
    attr->enType = type;
    attr->u32BufCount = 4;
    attr->u32Depth = 4;
    attr->stCodecAttr.enType = type;
    attr->stCodecAttr.enBitwidth = AUDIO_BIT_WIDTH_16;
    attr->stCodecAttr.u32Channels = channels;
    attr->stCodecAttr.u32SampleRate = sample_rate;
}

static int uya_rk1106_g711_audio_init(UyaRk1106G711Audio *audio)
{
    RK_CODEC_ID_E rk_codec;
    AIO_ATTR_S ai_attr;
    AI_CHN_PARAM_S ai_params;
    AENC_CHN_ATTR_S aenc_attr;
    MPP_CHN_S ai_chn;
    MPP_CHN_S aenc_chn;
    int rc;

    rc = uya_rk1106_g711_codec_to_rk(audio->codec_id, &rk_codec);
    if (rc != UYA_RK1106_G711_AUDIO_STATUS_OK)
        return rc;

    rc = audio->api.sys_init();
    if (uya_rk1106_g711_check(rc, "RK_MPI_SYS_Init") != UYA_RK1106_G711_AUDIO_STATUS_OK)
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    audio->sys_inited = 1;

    uya_rk1106_g711_fill_ai_attr(&ai_attr, audio->sample_rate, audio->channels, audio->frame_samples);
    rc = audio->api.ai_set_pub_attr(audio->ai_dev, &ai_attr);
    if (uya_rk1106_g711_check(rc, "RK_MPI_AI_SetPubAttr") != UYA_RK1106_G711_AUDIO_STATUS_OK)
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    rc = audio->api.ai_enable(audio->ai_dev);
    if (uya_rk1106_g711_check(rc, "RK_MPI_AI_Enable") != UYA_RK1106_G711_AUDIO_STATUS_OK)
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    audio->ai_enabled = 1;

    memset(&ai_params, 0, sizeof(ai_params));
    ai_params.enLoopbackMode = AUDIO_LOOPBACK_NONE;
    ai_params.s32UsrFrmDepth = 4;
    ai_params.u32MapPtNumPerFrm = audio->frame_samples;
    ai_params.enSamplerate = (AUDIO_SAMPLE_RATE_E)audio->sample_rate;
    (void)audio->api.ai_set_chn_param(audio->ai_dev, audio->ai_chn, &ai_params);
    if (audio->channels == 1)
        (void)audio->api.ai_set_track_mode(audio->ai_dev, AUDIO_TRACK_FRONT_LEFT);
    else
        (void)audio->api.ai_set_track_mode(audio->ai_dev, AUDIO_TRACK_NORMAL);

    rc = audio->api.ai_enable_chn(audio->ai_dev, audio->ai_chn);
    if (uya_rk1106_g711_check(rc, "RK_MPI_AI_EnableChn") != UYA_RK1106_G711_AUDIO_STATUS_OK)
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    audio->ai_chn_enabled = 1;
    if (uya_rk1106_g711_start_pcm_save(audio) != UYA_RK1106_G711_AUDIO_STATUS_OK)
        fprintf(stderr, "rk1106_g711_audio_shim: warning: PCM save disabled, G711 push continues\n");

    uya_rk1106_g711_fill_aenc_attr(&aenc_attr, rk_codec, audio->sample_rate, audio->channels);
    rc = audio->api.aenc_create_chn(audio->aenc_chn, &aenc_attr);
    if (uya_rk1106_g711_check(rc, "RK_MPI_AENC_CreateChn") != UYA_RK1106_G711_AUDIO_STATUS_OK)
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    audio->aenc_created = 1;

    memset(&ai_chn, 0, sizeof(ai_chn));
    memset(&aenc_chn, 0, sizeof(aenc_chn));
    ai_chn.enModId = RK_ID_AI;
    ai_chn.s32DevId = audio->ai_dev;
    ai_chn.s32ChnId = audio->ai_chn;
    aenc_chn.enModId = RK_ID_AENC;
    aenc_chn.s32DevId = 0;
    aenc_chn.s32ChnId = audio->aenc_chn;
    rc = audio->api.sys_bind(&ai_chn, &aenc_chn);
    if (uya_rk1106_g711_check(rc, "RK_MPI_SYS_Bind AI->AENC") != UYA_RK1106_G711_AUDIO_STATUS_OK)
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    audio->bound = 1;
    audio->pcm_dump = uya_rk1106_g711_pcm_dump_open();
    fprintf(stderr, "rk1106_g711_audio_shim: AI->AENC G711 ready codec=%u sample_rate=%u frame_samples=%u\n",
        audio->codec_id, audio->sample_rate, audio->frame_samples);
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

int uya_rk1106_g711_audio_open(
    uint32_t codec_id,
    uint32_t sample_rate,
    uint32_t channels,
    uint32_t frame_samples,
    size_t *out_handle)
{
    UyaRk1106G711Audio *audio;
    int status;

    if (out_handle)
        *out_handle = 0;
    if (!out_handle || sample_rate != 8000 || channels != 1 || frame_samples == 0)
        return UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT;
    if (codec_id != UYA_RK1106_G711_AUDIO_CODEC_PCMU && codec_id != UYA_RK1106_G711_AUDIO_CODEC_PCMA)
        return UYA_RK1106_G711_AUDIO_STATUS_UNSUPPORTED_CODEC;

    audio = (UyaRk1106G711Audio *)calloc(1, sizeof(*audio));
    if (!audio)
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    audio->ai_dev = 0;
    audio->ai_chn = 0;
    audio->aenc_chn = 0;
    audio->codec_id = codec_id;
    audio->sample_rate = sample_rate;
    audio->channels = channels;
    audio->frame_samples = frame_samples;

    if (uya_rk1106_g711_env_enabled("UYA_RK1106_G711_AUDIO_SILENCE")) {
        audio->synthetic_silence = 1;
        fprintf(stderr, "rk1106_g711_audio_shim: synthetic G711 silence enabled (PCM will be all zeros)\n");
        *out_handle = (size_t)audio;
        return UYA_RK1106_G711_AUDIO_STATUS_OK;
    }

    status = uya_rk1106_g711_load_api(&audio->api);
    if (status == UYA_RK1106_G711_AUDIO_STATUS_OK)
        status = uya_rk1106_g711_audio_init(audio);
    if (status != UYA_RK1106_G711_AUDIO_STATUS_OK) {
        (void)uya_rk1106_g711_audio_close((size_t)audio);
        return status;
    }

    *out_handle = (size_t)audio;
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

int uya_rk1106_g711_audio_read_packet(
    size_t handle,
    unsigned char *out_payload,
    size_t out_capacity,
    size_t *out_len,
    uint64_t *out_pts_us)
{
    UyaRk1106G711Audio *audio = (UyaRk1106G711Audio *)handle;
    AUDIO_STREAM_S stream;
    void *payload;

    if (out_len)
        *out_len = 0;
    if (out_pts_us)
        *out_pts_us = 0;
    if (!audio || !out_payload || !out_len || !out_pts_us || out_capacity == 0)
        return UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT;

    if (audio->synthetic_silence)
        return uya_rk1106_g711_fill_silence_packet(audio->codec_id, audio->sample_rate, audio->frame_samples,
            &audio->fallback_pts_us, out_payload, out_capacity, out_len, out_pts_us);

    memset(&stream, 0, sizeof(stream));
    if (audio->api.aenc_get_stream(audio->aenc_chn, &stream, 100) != RK_SUCCESS)
        return UYA_RK1106_G711_AUDIO_STATUS_READ_FAILED;

    if (!stream.pMbBlk || stream.u32Len == 0) {
        audio->api.aenc_release_stream(audio->aenc_chn, &stream);
        return UYA_RK1106_G711_AUDIO_STATUS_READ_FAILED;
    }
    payload = audio->api.mb_handle_to_addr(stream.pMbBlk);
    if (!payload) {
        audio->api.aenc_release_stream(audio->aenc_chn, &stream);
        return UYA_RK1106_G711_AUDIO_STATUS_READ_FAILED;
    }
    if (stream.u32Len > out_capacity) {
        audio->api.aenc_release_stream(audio->aenc_chn, &stream);
        return UYA_RK1106_G711_AUDIO_STATUS_BUFFER_TOO_SMALL;
    }

    memcpy(out_payload, payload, stream.u32Len);
    *out_len = stream.u32Len;
    *out_pts_us = stream.u64TimeStamp;
    if (*out_pts_us == 0) {
        *out_pts_us = audio->fallback_pts_us;
        audio->fallback_pts_us += ((uint64_t)audio->frame_samples * 1000000ULL) / audio->sample_rate;
    }
    uya_rk1106_g711_pcm_dump_g711_frame(audio->pcm_dump, audio->codec_id, out_payload, *out_len);
    audio->api.aenc_release_stream(audio->aenc_chn, &stream);
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

int uya_rk1106_g711_audio_close(size_t handle)
{
    UyaRk1106G711Audio *audio = (UyaRk1106G711Audio *)handle;
    if (!audio)
        return UYA_RK1106_G711_AUDIO_STATUS_OK;
    audio->pcm_save_enabled = 0;
    if (audio->pcm_dump) {
        fclose(audio->pcm_dump);
        audio->pcm_dump = NULL;
    }
    if (audio->bound) {
        MPP_CHN_S ai_chn;
        MPP_CHN_S aenc_chn;
        memset(&ai_chn, 0, sizeof(ai_chn));
        memset(&aenc_chn, 0, sizeof(aenc_chn));
        ai_chn.enModId = RK_ID_AI;
        ai_chn.s32DevId = audio->ai_dev;
        ai_chn.s32ChnId = audio->ai_chn;
        aenc_chn.enModId = RK_ID_AENC;
        aenc_chn.s32DevId = 0;
        aenc_chn.s32ChnId = audio->aenc_chn;
        (void)audio->api.sys_unbind(&ai_chn, &aenc_chn);
    }
    if (audio->aenc_created)
        (void)audio->api.aenc_destroy_chn(audio->aenc_chn);
    if (audio->ai_chn_enabled)
        (void)audio->api.ai_disable_chn(audio->ai_dev, audio->ai_chn);
    if (audio->ai_enabled)
        (void)audio->api.ai_disable(audio->ai_dev);
    if (audio->sys_inited)
        (void)audio->api.sys_exit();
#if !defined(UYA_RK1106_G711_AUDIO_STATIC_MPI)
    if (audio->api.lib)
        dlclose(audio->api.lib);
#endif
    free(audio);
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

#else

#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

typedef struct UyaHostG711Audio {
    uint32_t codec_id;
    uint32_t sample_rate;
    uint32_t channels;
    uint32_t frame_samples;
    uint64_t pts_us;
    FILE *fifo;
    int fifo_fallback_silence;
} UyaHostG711Audio;

int uya_rk1106_g711_audio_open(
    uint32_t codec_id,
    uint32_t sample_rate,
    uint32_t channels,
    uint32_t frame_samples,
    size_t *out_handle)
{
    UyaHostG711Audio *audio;
    const char *fifo_path;

    if (out_handle)
        *out_handle = 0;
    if (!out_handle || sample_rate != 8000 || channels != 1 || frame_samples == 0)
        return UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT;
    if (codec_id != UYA_RK1106_G711_AUDIO_CODEC_PCMU && codec_id != UYA_RK1106_G711_AUDIO_CODEC_PCMA)
        return UYA_RK1106_G711_AUDIO_STATUS_UNSUPPORTED_CODEC;
    audio = (UyaHostG711Audio *)calloc(1, sizeof(*audio));
    if (!audio)
        return UYA_RK1106_G711_AUDIO_STATUS_OPEN_FAILED;
    audio->codec_id = codec_id;
    audio->sample_rate = sample_rate;
    audio->channels = channels;
    audio->frame_samples = frame_samples;

    /* Hardcoded FIFO path — avoids shell env-var propagation issues on busybox */
    fifo_path = "/tmp/fastboot.g711";
    audio->fifo = fopen(fifo_path, "rb");
    if (!audio->fifo) {
        fprintf(stderr, "rk1106_g711_audio_shim: FIFO open failed path=%s errno=%d, falling back to silence\n",
                fifo_path, errno);
        audio->fifo_fallback_silence = 1;
    } else {
        fprintf(stderr, "rk1106_g711_audio_shim: FIFO reader opened (blocking) path=%s codec=%u frame_bytes=%u\n",
                fifo_path, codec_id, frame_samples);
    }

    *out_handle = (size_t)audio;
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

int uya_rk1106_g711_audio_read_packet(
    size_t handle,
    unsigned char *out_payload,
    size_t out_capacity,
    size_t *out_len,
    uint64_t *out_pts_us)
{
    UyaHostG711Audio *audio = (UyaHostG711Audio *)handle;
    int status;
    size_t frame_bytes;

    if (out_len)
        *out_len = 0;
    if (out_pts_us)
        *out_pts_us = 0;
    if (!audio || !out_payload || !out_len || !out_pts_us)
        return UYA_RK1106_G711_AUDIO_STATUS_INVALID_ARGUMENT;

    frame_bytes = audio->frame_samples;

    /* Try FIFO read first */
    if (audio->fifo && !audio->fifo_fallback_silence) {
        size_t n = fread(out_payload, 1, frame_bytes, audio->fifo);
        if (n == frame_bytes) {
            *out_len = frame_bytes;
            *out_pts_us = audio->pts_us;
            audio->pts_us += ((uint64_t)frame_bytes * 1000000ULL) / audio->sample_rate;
            return UYA_RK1106_G711_AUDIO_STATUS_OK;
        }
        if (n > 0) {
            /* partial read -- clear and retry next time */
            clearerr(audio->fifo);
        }
        /* FIFO empty or partial: fall through to silence for this frame */
    }

    /* Fallback: synthetic silence */
    status = uya_rk1106_g711_fill_silence_packet(audio->codec_id, audio->sample_rate, audio->frame_samples,
        &audio->pts_us, out_payload, out_capacity, out_len, out_pts_us);
    return status;
}

int uya_rk1106_g711_audio_close(size_t handle)
{
    UyaHostG711Audio *audio = (UyaHostG711Audio *)handle;
    if (!audio)
        return UYA_RK1106_G711_AUDIO_STATUS_OK;
    if (audio->fifo) {
        fclose(audio->fifo);
        audio->fifo = NULL;
    }
    free(audio);
    return UYA_RK1106_G711_AUDIO_STATUS_OK;
}

#endif
