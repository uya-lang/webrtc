// Minimal V4L2 capture helper for RV1103B/RK1106 boards.
//
// Captures NV12/YUYV/UYVY/YU12/YV12 frames from a V4L2 node and writes compact
// I420 frames to stdout, a regular file, or a FIFO consumed by Uya WebRTC.

#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef VIDEO_MAX_PLANES
#define VIDEO_MAX_PLANES 8
#endif

struct buffer {
    void *start[VIDEO_MAX_PLANES];
    size_t length[VIDEO_MAX_PLANES];
    unsigned int plane_count;
};

struct capture_config {
    enum v4l2_buf_type type;
    uint32_t pixfmt;
    uint32_t y_stride;
    uint32_t uv_stride;
    unsigned int plane_count;
};

struct options {
    const char *device;
    const char *output;
    uint32_t width;
    uint32_t height;
    uint32_t fps;
    uint32_t pixfmt;
    uint64_t frames;
};

static void usage(const char *argv0) {
    fprintf(stderr,
            "usage: %s [--device /dev/video7] [--width 320] [--height 180]\n"
            "          [--fps 10] [--format nv12|nv12m|yuyv|uyvy|i420|i420m|yv12|yv12m]\n"
            "          [--frames N] [--output path|-]\n",
            argv0);
}

static int xioctl(int fd, unsigned long request, void *arg) {
    int rc;
    do {
        rc = ioctl(fd, request, arg);
    } while (rc < 0 && errno == EINTR);
    return rc;
}

static uint32_t parse_format(const char *name) {
    if (strcmp(name, "nv12") == 0) return V4L2_PIX_FMT_NV12;
#ifdef V4L2_PIX_FMT_NV12M
    if (strcmp(name, "nv12m") == 0) return V4L2_PIX_FMT_NV12M;
#endif
    if (strcmp(name, "yuyv") == 0) return V4L2_PIX_FMT_YUYV;
    if (strcmp(name, "uyvy") == 0) return V4L2_PIX_FMT_UYVY;
    if (strcmp(name, "i420") == 0 || strcmp(name, "yu12") == 0) return V4L2_PIX_FMT_YUV420;
#ifdef V4L2_PIX_FMT_YUV420M
    if (strcmp(name, "i420m") == 0 || strcmp(name, "yu12m") == 0) return V4L2_PIX_FMT_YUV420M;
#endif
    if (strcmp(name, "yv12") == 0) return V4L2_PIX_FMT_YVU420;
#ifdef V4L2_PIX_FMT_YVU420M
    if (strcmp(name, "yv12m") == 0) return V4L2_PIX_FMT_YVU420M;
#endif
    return 0;
}

static const char *format_name(uint32_t fmt) {
    switch (fmt) {
    case V4L2_PIX_FMT_NV12: return "nv12";
#ifdef V4L2_PIX_FMT_NV12M
    case V4L2_PIX_FMT_NV12M: return "nv12m";
#endif
    case V4L2_PIX_FMT_YUYV: return "yuyv";
    case V4L2_PIX_FMT_UYVY: return "uyvy";
    case V4L2_PIX_FMT_YUV420: return "i420";
#ifdef V4L2_PIX_FMT_YUV420M
    case V4L2_PIX_FMT_YUV420M: return "i420m";
#endif
    case V4L2_PIX_FMT_YVU420: return "yv12";
#ifdef V4L2_PIX_FMT_YVU420M
    case V4L2_PIX_FMT_YVU420M: return "yv12m";
#endif
    default: return "unknown";
    }
}

static int format_compatible(uint32_t requested, uint32_t actual) {
    if (requested == actual) return 1;
#ifdef V4L2_PIX_FMT_NV12M
    if (requested == V4L2_PIX_FMT_NV12 && actual == V4L2_PIX_FMT_NV12M) return 1;
    if (requested == V4L2_PIX_FMT_NV12M && actual == V4L2_PIX_FMT_NV12) return 1;
#endif
#ifdef V4L2_PIX_FMT_YUV420M
    if (requested == V4L2_PIX_FMT_YUV420 && actual == V4L2_PIX_FMT_YUV420M) return 1;
    if (requested == V4L2_PIX_FMT_YUV420M && actual == V4L2_PIX_FMT_YUV420) return 1;
#endif
#ifdef V4L2_PIX_FMT_YVU420M
    if (requested == V4L2_PIX_FMT_YVU420 && actual == V4L2_PIX_FMT_YVU420M) return 1;
    if (requested == V4L2_PIX_FMT_YVU420M && actual == V4L2_PIX_FMT_YVU420) return 1;
#endif
    return 0;
}

static uint32_t parse_u32(const char *text, const char *label) {
    char *end = NULL;
    unsigned long value = strtoul(text, &end, 10);
    if (text[0] == '\0' || (end && *end != '\0') || value == 0 || value > UINT32_MAX) {
        fprintf(stderr, "invalid %s: %s\n", label, text);
        exit(2);
    }
    return (uint32_t)value;
}

static uint64_t parse_u64(const char *text, const char *label) {
    char *end = NULL;
    unsigned long long value = strtoull(text, &end, 10);
    if (text[0] == '\0' || (end && *end != '\0')) {
        fprintf(stderr, "invalid %s: %s\n", label, text);
        exit(2);
    }
    return (uint64_t)value;
}

static struct options parse_args(int argc, char **argv) {
    struct options opt;
    opt.device = "/dev/video7";
    opt.output = "-";
    opt.width = 320;
    opt.height = 180;
    opt.fps = 10;
    opt.pixfmt = V4L2_PIX_FMT_NV12;
    opt.frames = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--device") == 0 && i + 1 < argc) {
            opt.device = argv[++i];
        } else if (strcmp(argv[i], "--output") == 0 && i + 1 < argc) {
            opt.output = argv[++i];
        } else if (strcmp(argv[i], "--width") == 0 && i + 1 < argc) {
            opt.width = parse_u32(argv[++i], "width");
        } else if (strcmp(argv[i], "--height") == 0 && i + 1 < argc) {
            opt.height = parse_u32(argv[++i], "height");
        } else if (strcmp(argv[i], "--fps") == 0 && i + 1 < argc) {
            opt.fps = parse_u32(argv[++i], "fps");
        } else if (strcmp(argv[i], "--frames") == 0 && i + 1 < argc) {
            opt.frames = parse_u64(argv[++i], "frames");
        } else if (strcmp(argv[i], "--format") == 0 && i + 1 < argc) {
            opt.pixfmt = parse_format(argv[++i]);
            if (opt.pixfmt == 0) {
                fprintf(stderr, "unsupported format: %s\n", argv[i]);
                exit(2);
            }
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            usage(argv[0]);
            exit(0);
        } else {
            usage(argv[0]);
            exit(2);
        }
    }

    if ((opt.width & 1U) != 0 || (opt.height & 1U) != 0) {
        fprintf(stderr, "I420 output requires even dimensions, got %ux%u\n", opt.width, opt.height);
        exit(2);
    }
    return opt;
}

static int open_output(const char *path) {
    if (strcmp(path, "-") == 0) return STDOUT_FILENO;
    int flags = O_WRONLY | O_CREAT | O_TRUNC;
    struct stat st;
    if (stat(path, &st) == 0 && S_ISFIFO(st.st_mode)) {
        flags = O_WRONLY;
    }
    int fd = open(path, flags, 0644);
    if (fd < 0) {
        fprintf(stderr, "open output %s failed: %s\n", path, strerror(errno));
        exit(1);
    }
    return fd;
}

static void write_all(int fd, const uint8_t *data, size_t len) {
    size_t off = 0;
    while (off < len) {
        ssize_t n = write(fd, data + off, len - off);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) {
            fprintf(stderr, "write output failed: %s\n", n < 0 ? strerror(errno) : "short write");
            exit(1);
        }
        off += (size_t)n;
    }
}

static void convert_nv12_to_i420_planes(
    const uint8_t *src_y,
    const uint8_t *src_uv,
    uint8_t *dst,
    uint32_t w,
    uint32_t h,
    uint32_t y_stride,
    uint32_t uv_stride
) {
    if (y_stride < w) y_stride = w;
    if (uv_stride < w) uv_stride = w;
    uint8_t *dst_y = dst;
    uint8_t *dst_u = dst_y + (size_t)w * h;
    uint8_t *dst_v = dst_u + ((size_t)w * h) / 4;

    for (uint32_t y = 0; y < h; y++) {
        memcpy(dst_y + (size_t)y * w, src_y + (size_t)y * y_stride, w);
    }
    for (uint32_t y = 0; y < h / 2; y++) {
        const uint8_t *row = src_uv + (size_t)y * uv_stride;
        for (uint32_t x = 0; x < w / 2; x++) {
            dst_u[(size_t)y * (w / 2) + x] = row[x * 2];
            dst_v[(size_t)y * (w / 2) + x] = row[x * 2 + 1];
        }
    }
}

static void convert_yuyv_like_to_i420(const uint8_t *src, uint8_t *dst, uint32_t w, uint32_t h, uint32_t stride, int uyvy) {
    uint32_t min_stride = w * 2;
    if (stride < min_stride) stride = min_stride;
    uint8_t *dst_y = dst;
    uint8_t *dst_u = dst_y + (size_t)w * h;
    uint8_t *dst_v = dst_u + ((size_t)w * h) / 4;

    for (uint32_t y = 0; y < h; y += 2) {
        const uint8_t *row0 = src + (size_t)y * stride;
        const uint8_t *row1 = src + (size_t)(y + 1) * stride;
        for (uint32_t x = 0; x < w; x += 2) {
            const uint8_t *p0 = row0 + (size_t)x * 2;
            const uint8_t *p1 = row1 + (size_t)x * 2;
            uint8_t y00 = uyvy ? p0[1] : p0[0];
            uint8_t y01 = uyvy ? p0[3] : p0[2];
            uint8_t y10 = uyvy ? p1[1] : p1[0];
            uint8_t y11 = uyvy ? p1[3] : p1[2];
            uint8_t u0 = uyvy ? p0[0] : p0[1];
            uint8_t v0 = uyvy ? p0[2] : p0[3];
            uint8_t u1 = uyvy ? p1[0] : p1[1];
            uint8_t v1 = uyvy ? p1[2] : p1[3];

            dst_y[(size_t)y * w + x] = y00;
            dst_y[(size_t)y * w + x + 1] = y01;
            dst_y[(size_t)(y + 1) * w + x] = y10;
            dst_y[(size_t)(y + 1) * w + x + 1] = y11;
            dst_u[(size_t)(y / 2) * (w / 2) + (x / 2)] = (uint8_t)(((uint32_t)u0 + u1 + 1U) / 2U);
            dst_v[(size_t)(y / 2) * (w / 2) + (x / 2)] = (uint8_t)(((uint32_t)v0 + v1 + 1U) / 2U);
        }
    }
}

static void convert_yuv420_to_i420_planes(
    const uint8_t *src_y,
    const uint8_t *src_u,
    const uint8_t *src_v,
    uint8_t *dst,
    uint32_t w,
    uint32_t h,
    uint32_t y_stride,
    uint32_t uv_stride
) {
    if (y_stride < w) y_stride = w;
    if (uv_stride < w / 2) uv_stride = w / 2;
    uint8_t *dst_y = dst;
    uint8_t *dst_u = dst_y + (size_t)w * h;
    uint8_t *dst_v = dst_u + ((size_t)w * h) / 4;

    for (uint32_t y = 0; y < h; y++) {
        memcpy(dst_y + (size_t)y * w, src_y + (size_t)y * y_stride, w);
    }
    for (uint32_t y = 0; y < h / 2; y++) {
        memcpy(dst_u + (size_t)y * (w / 2), src_u + (size_t)y * uv_stride, w / 2);
        memcpy(dst_v + (size_t)y * (w / 2), src_v + (size_t)y * uv_stride, w / 2);
    }
}

static void convert_yuv420_to_i420_packed(const uint8_t *src, uint8_t *dst, uint32_t w, uint32_t h, uint32_t stride, int yv12) {
    if (stride < w) stride = w;
    uint32_t uv_stride = stride / 2;
    if (uv_stride < w / 2) uv_stride = w / 2;
    size_t y_plane_bytes = (size_t)stride * h;
    size_t uv_plane_bytes = (size_t)uv_stride * (h / 2);
    const uint8_t *src_y = src;
    const uint8_t *src_a = src + y_plane_bytes;
    const uint8_t *src_b = src_a + uv_plane_bytes;
    const uint8_t *src_u = yv12 ? src_b : src_a;
    const uint8_t *src_v = yv12 ? src_a : src_b;
    convert_yuv420_to_i420_planes(src_y, src_u, src_v, dst, w, h, stride, uv_stride);
}

static void convert_frame(const struct buffer *buf, uint8_t *dst, const struct options *opt, const struct capture_config *cfg) {
    const uint8_t *plane0 = (const uint8_t *)buf->start[0];
    if (!plane0) {
        fprintf(stderr, "capture buffer has no plane 0\n");
        exit(1);
    }
    switch (cfg->pixfmt) {
    case V4L2_PIX_FMT_NV12:
        if (buf->plane_count >= 2 && buf->start[1]) {
            convert_nv12_to_i420_planes(plane0, (const uint8_t *)buf->start[1], dst, opt->width, opt->height, cfg->y_stride, cfg->uv_stride);
        } else {
            convert_nv12_to_i420_planes(plane0, plane0 + (size_t)cfg->y_stride * opt->height, dst, opt->width, opt->height, cfg->y_stride, cfg->y_stride);
        }
        break;
#ifdef V4L2_PIX_FMT_NV12M
    case V4L2_PIX_FMT_NV12M:
        if (buf->plane_count < 2 || !buf->start[1]) {
            fprintf(stderr, "nv12m requires two mapped V4L2 planes\n");
            exit(1);
        }
        convert_nv12_to_i420_planes(plane0, (const uint8_t *)buf->start[1], dst, opt->width, opt->height, cfg->y_stride, cfg->uv_stride);
        break;
#endif
    case V4L2_PIX_FMT_YUYV:
        convert_yuyv_like_to_i420(plane0, dst, opt->width, opt->height, cfg->y_stride, 0);
        break;
    case V4L2_PIX_FMT_UYVY:
        convert_yuyv_like_to_i420(plane0, dst, opt->width, opt->height, cfg->y_stride, 1);
        break;
    case V4L2_PIX_FMT_YUV420:
        if (buf->plane_count >= 3 && buf->start[1] && buf->start[2]) {
            convert_yuv420_to_i420_planes(plane0, (const uint8_t *)buf->start[1], (const uint8_t *)buf->start[2], dst, opt->width, opt->height, cfg->y_stride, cfg->uv_stride);
        } else {
            convert_yuv420_to_i420_packed(plane0, dst, opt->width, opt->height, cfg->y_stride, 0);
        }
        break;
#ifdef V4L2_PIX_FMT_YUV420M
    case V4L2_PIX_FMT_YUV420M:
        if (buf->plane_count < 3 || !buf->start[1] || !buf->start[2]) {
            fprintf(stderr, "i420m requires three mapped V4L2 planes\n");
            exit(1);
        }
        convert_yuv420_to_i420_planes(plane0, (const uint8_t *)buf->start[1], (const uint8_t *)buf->start[2], dst, opt->width, opt->height, cfg->y_stride, cfg->uv_stride);
        break;
#endif
    case V4L2_PIX_FMT_YVU420:
        if (buf->plane_count >= 3 && buf->start[1] && buf->start[2]) {
            convert_yuv420_to_i420_planes(plane0, (const uint8_t *)buf->start[2], (const uint8_t *)buf->start[1], dst, opt->width, opt->height, cfg->y_stride, cfg->uv_stride);
        } else {
            convert_yuv420_to_i420_packed(plane0, dst, opt->width, opt->height, cfg->y_stride, 1);
        }
        break;
#ifdef V4L2_PIX_FMT_YVU420M
    case V4L2_PIX_FMT_YVU420M:
        if (buf->plane_count < 3 || !buf->start[1] || !buf->start[2]) {
            fprintf(stderr, "yv12m requires three mapped V4L2 planes\n");
            exit(1);
        }
        convert_yuv420_to_i420_planes(plane0, (const uint8_t *)buf->start[2], (const uint8_t *)buf->start[1], dst, opt->width, opt->height, cfg->y_stride, cfg->uv_stride);
        break;
#endif
    default:
        fprintf(stderr, "format conversion not implemented: 0x%08x\n", cfg->pixfmt);
        exit(1);
    }
}

static int is_mplane(enum v4l2_buf_type type) {
    return type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
}

static uint32_t alternate_format_for_type(uint32_t pixfmt, enum v4l2_buf_type type) {
    if (is_mplane(type)) {
#ifdef V4L2_PIX_FMT_NV12M
        if (pixfmt == V4L2_PIX_FMT_NV12) return V4L2_PIX_FMT_NV12M;
#endif
#ifdef V4L2_PIX_FMT_YUV420M
        if (pixfmt == V4L2_PIX_FMT_YUV420) return V4L2_PIX_FMT_YUV420M;
#endif
#ifdef V4L2_PIX_FMT_YVU420M
        if (pixfmt == V4L2_PIX_FMT_YVU420) return V4L2_PIX_FMT_YVU420M;
#endif
    } else {
#ifdef V4L2_PIX_FMT_NV12M
        if (pixfmt == V4L2_PIX_FMT_NV12M) return V4L2_PIX_FMT_NV12;
#endif
#ifdef V4L2_PIX_FMT_YUV420M
        if (pixfmt == V4L2_PIX_FMT_YUV420M) return V4L2_PIX_FMT_YUV420;
#endif
#ifdef V4L2_PIX_FMT_YVU420M
        if (pixfmt == V4L2_PIX_FMT_YVU420M) return V4L2_PIX_FMT_YVU420;
#endif
    }
    return pixfmt;
}

static unsigned int default_plane_count(uint32_t pixfmt) {
    switch (pixfmt) {
#ifdef V4L2_PIX_FMT_NV12M
    case V4L2_PIX_FMT_NV12M:
        return 2;
#endif
#ifdef V4L2_PIX_FMT_YUV420M
    case V4L2_PIX_FMT_YUV420M:
        return 3;
#endif
#ifdef V4L2_PIX_FMT_YVU420M
    case V4L2_PIX_FMT_YVU420M:
        return 3;
#endif
    default:
        return 1;
    }
}

static uint32_t default_uv_stride(uint32_t pixfmt, uint32_t y_stride, uint32_t width) {
    switch (pixfmt) {
    case V4L2_PIX_FMT_YUV420:
    case V4L2_PIX_FMT_YVU420:
#ifdef V4L2_PIX_FMT_YUV420M
    case V4L2_PIX_FMT_YUV420M:
#endif
#ifdef V4L2_PIX_FMT_YVU420M
    case V4L2_PIX_FMT_YVU420M:
#endif
        return y_stride / 2U > width / 2U ? y_stride / 2U : width / 2U;
    default:
        return y_stride > width ? y_stride : width;
    }
}

static void prepare_v4l2_buffer(
    struct v4l2_buffer *buf,
    struct v4l2_plane planes[VIDEO_MAX_PLANES],
    enum v4l2_buf_type type,
    unsigned int plane_count,
    unsigned int index
) {
    memset(buf, 0, sizeof(*buf));
    buf->type = type;
    buf->memory = V4L2_MEMORY_MMAP;
    buf->index = index;
    if (is_mplane(type)) {
        memset(planes, 0, sizeof(struct v4l2_plane) * VIDEO_MAX_PLANES);
        buf->length = plane_count;
        buf->m.planes = planes;
    }
}

static void init_device(int fd, const struct options *opt, struct capture_config *cfg, struct buffer **out_buffers, unsigned int *out_count) {
    struct v4l2_capability cap;
    memset(&cap, 0, sizeof(cap));
    if (xioctl(fd, VIDIOC_QUERYCAP, &cap) < 0) {
        fprintf(stderr, "VIDIOC_QUERYCAP failed: %s\n", strerror(errno));
        exit(1);
    }

    uint32_t caps = cap.capabilities;
    if ((cap.capabilities & V4L2_CAP_DEVICE_CAPS) != 0) {
        caps = cap.device_caps;
    }

    memset(cfg, 0, sizeof(*cfg));
    if ((caps & V4L2_CAP_VIDEO_CAPTURE_MPLANE) != 0) {
        cfg->type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    } else if ((caps & V4L2_CAP_VIDEO_CAPTURE) != 0) {
        cfg->type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    } else {
        fprintf(stderr,
                "%s is not a V4L2 capture device (capabilities=0x%08x device_caps=0x%08x effective=0x%08x)\n",
                opt->device, cap.capabilities, cap.device_caps, caps);
        exit(1);
    }
    if ((caps & V4L2_CAP_STREAMING) == 0) {
        fprintf(stderr, "%s does not support V4L2 streaming mmap capture (effective capabilities=0x%08x)\n",
                opt->device, caps);
        exit(1);
    }

    struct v4l2_streamparm parm;
    memset(&parm, 0, sizeof(parm));
    parm.type = cfg->type;
    parm.parm.capture.timeperframe.numerator = 1;
    parm.parm.capture.timeperframe.denominator = opt->fps;
    (void)xioctl(fd, VIDIOC_S_PARM, &parm);

    struct v4l2_format fmt;
    memset(&fmt, 0, sizeof(fmt));
    uint32_t attempts[2];
    attempts[0] = opt->pixfmt;
    attempts[1] = alternate_format_for_type(opt->pixfmt, cfg->type);
    int set_fmt_ok = 0;
    int set_fmt_errno = 0;
    for (unsigned int attempt = 0; attempt < 2; attempt++) {
        if (attempt == 1 && attempts[1] == attempts[0]) {
            continue;
        }
        memset(&fmt, 0, sizeof(fmt));
        fmt.type = cfg->type;
        if (is_mplane(cfg->type)) {
            fmt.fmt.pix_mp.width = opt->width;
            fmt.fmt.pix_mp.height = opt->height;
            fmt.fmt.pix_mp.pixelformat = attempts[attempt];
            fmt.fmt.pix_mp.field = V4L2_FIELD_ANY;
        } else {
            fmt.fmt.pix.width = opt->width;
            fmt.fmt.pix.height = opt->height;
            fmt.fmt.pix.pixelformat = attempts[attempt];
            fmt.fmt.pix.field = V4L2_FIELD_ANY;
        }
        if (xioctl(fd, VIDIOC_S_FMT, &fmt) == 0) {
            set_fmt_ok = 1;
            break;
        }
        set_fmt_errno = errno;
    }
    if (!set_fmt_ok) {
        fprintf(stderr, "VIDIOC_S_FMT %ux%u %s failed on %s: %s\n",
                opt->width, opt->height, format_name(opt->pixfmt), opt->device, strerror(set_fmt_errno));
        exit(1);
    }

    uint32_t actual_width;
    uint32_t actual_height;
    uint32_t actual_pixfmt;
    if (is_mplane(cfg->type)) {
        actual_width = fmt.fmt.pix_mp.width;
        actual_height = fmt.fmt.pix_mp.height;
        actual_pixfmt = fmt.fmt.pix_mp.pixelformat;
        cfg->y_stride = fmt.fmt.pix_mp.plane_fmt[0].bytesperline;
        if (cfg->y_stride == 0) cfg->y_stride = opt->width;
        cfg->uv_stride = fmt.fmt.pix_mp.plane_fmt[1].bytesperline;
        if (cfg->uv_stride == 0) cfg->uv_stride = default_uv_stride(actual_pixfmt, cfg->y_stride, opt->width);
        cfg->plane_count = fmt.fmt.pix_mp.num_planes;
        if (cfg->plane_count == 0) cfg->plane_count = default_plane_count(actual_pixfmt);
        if (cfg->plane_count > VIDEO_MAX_PLANES) {
            fprintf(stderr, "device returned too many V4L2 planes: %u\n", cfg->plane_count);
            exit(1);
        }
    } else {
        actual_width = fmt.fmt.pix.width;
        actual_height = fmt.fmt.pix.height;
        actual_pixfmt = fmt.fmt.pix.pixelformat;
        cfg->y_stride = fmt.fmt.pix.bytesperline ? fmt.fmt.pix.bytesperline : opt->width;
        cfg->uv_stride = default_uv_stride(actual_pixfmt, cfg->y_stride, opt->width);
        cfg->plane_count = 1;
    }
    if (actual_width != opt->width || actual_height != opt->height || !format_compatible(opt->pixfmt, actual_pixfmt)) {
        fprintf(stderr, "device adjusted format to %ux%u %s; set WIDTH/HEIGHT/PIXEL_FORMAT to match\n",
                actual_width, actual_height, format_name(actual_pixfmt));
        exit(1);
    }
    if (cfg->plane_count == 0) cfg->plane_count = 1;
    cfg->pixfmt = actual_pixfmt;

    fprintf(stderr, "capture %s %s %ux%u %s planes=%u stride=%u uv_stride=%u fps=%u\n",
            opt->device,
            is_mplane(cfg->type) ? "mplane" : "single-plane",
            opt->width,
            opt->height,
            format_name(cfg->pixfmt),
            cfg->plane_count,
            cfg->y_stride,
            cfg->uv_stride,
            opt->fps);

    struct v4l2_requestbuffers req;
    memset(&req, 0, sizeof(req));
    req.count = 4;
    req.type = cfg->type;
    req.memory = V4L2_MEMORY_MMAP;
    if (xioctl(fd, VIDIOC_REQBUFS, &req) < 0) {
        fprintf(stderr, "VIDIOC_REQBUFS failed: %s\n", strerror(errno));
        exit(1);
    }
    if (req.count < 2) {
        fprintf(stderr, "V4L2 returned too few buffers: %u\n", req.count);
        exit(1);
    }

    struct buffer *buffers = calloc(req.count, sizeof(*buffers));
    if (!buffers) {
        fprintf(stderr, "calloc buffers failed\n");
        exit(1);
    }

    for (unsigned int i = 0; i < req.count; i++) {
        struct v4l2_buffer buf;
        struct v4l2_plane planes[VIDEO_MAX_PLANES];
        prepare_v4l2_buffer(&buf, planes, cfg->type, cfg->plane_count, i);
        if (xioctl(fd, VIDIOC_QUERYBUF, &buf) < 0) {
            fprintf(stderr, "VIDIOC_QUERYBUF failed: %s\n", strerror(errno));
            exit(1);
        }

        if (is_mplane(cfg->type)) {
            unsigned int plane_count = buf.length;
            if (plane_count == 0 || plane_count > VIDEO_MAX_PLANES) {
                fprintf(stderr, "VIDIOC_QUERYBUF returned invalid plane count: %u\n", plane_count);
                exit(1);
            }
            buffers[i].plane_count = plane_count;
            for (unsigned int p = 0; p < plane_count; p++) {
                buffers[i].length[p] = planes[p].length;
                buffers[i].start[p] = mmap(NULL, planes[p].length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, planes[p].m.mem_offset);
                if (buffers[i].start[p] == MAP_FAILED) {
                    fprintf(stderr, "mmap buffer plane %u failed: %s\n", p, strerror(errno));
                    exit(1);
                }
            }
        } else {
            buffers[i].plane_count = 1;
            buffers[i].length[0] = buf.length;
            buffers[i].start[0] = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, buf.m.offset);
            if (buffers[i].start[0] == MAP_FAILED) {
                fprintf(stderr, "mmap buffer failed: %s\n", strerror(errno));
                exit(1);
            }
        }
    }

    for (unsigned int i = 0; i < req.count; i++) {
        struct v4l2_buffer buf;
        struct v4l2_plane planes[VIDEO_MAX_PLANES];
        prepare_v4l2_buffer(&buf, planes, cfg->type, buffers[i].plane_count, i);
        if (xioctl(fd, VIDIOC_QBUF, &buf) < 0) {
            fprintf(stderr, "VIDIOC_QBUF failed: %s\n", strerror(errno));
            exit(1);
        }
    }

    enum v4l2_buf_type type = cfg->type;
    if (xioctl(fd, VIDIOC_STREAMON, &type) < 0) {
        fprintf(stderr, "VIDIOC_STREAMON failed: %s\n", strerror(errno));
        exit(1);
    }

    *out_buffers = buffers;
    *out_count = req.count;
}

int main(int argc, char **argv) {
    struct options opt = parse_args(argc, argv);
    int in_fd = open(opt.device, O_RDWR | O_NONBLOCK, 0);
    if (in_fd < 0) {
        fprintf(stderr, "open %s failed: %s\n", opt.device, strerror(errno));
        return 1;
    }
    int out_fd = open_output(opt.output);

    struct capture_config cfg;
    struct buffer *buffers = NULL;
    unsigned int buffer_count = 0;
    init_device(in_fd, &opt, &cfg, &buffers, &buffer_count);

    size_t i420_bytes = ((size_t)opt.width * opt.height * 3U) / 2U;
    uint8_t *i420 = malloc(i420_bytes);
    if (!i420) {
        fprintf(stderr, "malloc I420 buffer failed\n");
        return 1;
    }

    uint64_t captured = 0;
    while (opt.frames == 0 || captured < opt.frames) {
        fd_set fds;
        FD_ZERO(&fds);
        FD_SET(in_fd, &fds);
        struct timeval tv;
        tv.tv_sec = 2;
        tv.tv_usec = 0;
        int rc = select(in_fd + 1, &fds, NULL, NULL, &tv);
        if (rc < 0 && errno == EINTR) continue;
        if (rc <= 0) {
            fprintf(stderr, "timeout waiting for V4L2 frame\n");
            continue;
        }

        struct v4l2_buffer buf;
        struct v4l2_plane planes[VIDEO_MAX_PLANES];
        prepare_v4l2_buffer(&buf, planes, cfg.type, cfg.plane_count, 0);
        if (xioctl(in_fd, VIDIOC_DQBUF, &buf) < 0) {
            if (errno == EAGAIN) continue;
            fprintf(stderr, "VIDIOC_DQBUF failed: %s\n", strerror(errno));
            return 1;
        }
        if (buf.index >= buffer_count) {
            fprintf(stderr, "bad V4L2 buffer index: %u\n", buf.index);
            return 1;
        }

        convert_frame(&buffers[buf.index], i420, &opt, &cfg);
        write_all(out_fd, i420, i420_bytes);
        captured++;

        if (is_mplane(cfg.type)) {
            buf.length = buffers[buf.index].plane_count;
            buf.m.planes = planes;
        }
        if (xioctl(in_fd, VIDIOC_QBUF, &buf) < 0) {
            fprintf(stderr, "VIDIOC_QBUF requeue failed: %s\n", strerror(errno));
            return 1;
        }
    }

    enum v4l2_buf_type type = cfg.type;
    (void)xioctl(in_fd, VIDIOC_STREAMOFF, &type);
    for (unsigned int i = 0; i < buffer_count; i++) {
        for (unsigned int p = 0; p < buffers[i].plane_count; p++) {
            if (buffers[i].start[p] && buffers[i].start[p] != MAP_FAILED) {
                munmap(buffers[i].start[p], buffers[i].length[p]);
            }
        }
    }
    free(buffers);
    free(i420);
    if (out_fd != STDOUT_FILENO) close(out_fd);
    close(in_fd);
    return 0;
}
