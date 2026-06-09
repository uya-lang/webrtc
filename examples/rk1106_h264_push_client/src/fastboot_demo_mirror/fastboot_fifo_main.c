#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define main uya_fastboot_demo_original_main
#include "fastboot_demo.c"
#undef main

static const char *resolve_out_path(void) {
    const char *path = getenv("FASTBOOT_H264_OUT");
    if (path && path[0]) return path;
    return "/tmp/fastboot.h264";
}

int main(int argc, char **argv) {
    g_fastboot_out_path = resolve_out_path();
    fprintf(stderr, "fastboot_h264_fifo: output=%s\n", g_fastboot_out_path);
    fflush(stderr);
    return uya_fastboot_demo_original_main(argc, argv);
}
